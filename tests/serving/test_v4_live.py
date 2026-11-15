"""B3 reads the new origin from the database and keeps archived thresholds honest."""

from contextlib import ExitStack
from dataclasses import replace
from datetime import date
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import pandas as pd

from backend_support import motor_temporal
from serving.test_demo_b3_v4 import HORIZONS, synthetic_bundle
from denguekay.config.paths import UBIGEO_CATALOG
from denguekay.data.calendar import mmwr_epi_week
from denguekay.data.processing.epi_sala import load_ubigeo_catalog
from denguekay.db.models import SystemParameter, WeeklyObservation
from denguekay.db.session import transaction
from denguekay.features.b3 import NINO, climate_vector
from denguekay.serving import load_data
from denguekay.serving.predictors import v4_b3_live as v4
from denguekay.serving.publish import publish
from denguekay.serving.storage import LocalStorage


class TestB3Availability(unittest.TestCase):
    def test_unpublished_weather_and_future_nino_are_excluded(self):
        cutoff = pd.Timestamp("2026-10-17")
        weeks = pd.date_range("2026-08-30", "2026-10-18", freq="W-SUN")
        district = pd.Index(["200101"], name="ubigeo")
        weather = pd.DataFrame({"ubigeo": district[0], "semana_inicio": weeks, "temp_media": range(8),
                                "hum_rel_media": 60, "precip_total_mm": 9,
                                "fecha_era5_land_disponible": weeks + pd.Timedelta(days=13),
                                "fecha_chirps_disponible": weeks + pd.Timedelta(days=14)})
        enso = pd.DataFrame({"mes": pd.date_range("2026-07-01", periods=4, freq="MS"),
                             "nino12_anom": [1, 2, 3, 100]})
        enso["fecha_disponible"] = enso.mes + pd.offsets.MonthBegin(1) + pd.Timedelta(days=9)
        baseline = climate_vector(weather, enso, cutoff, district)
        self.assertEqual(baseline.loc[district[0], NINO], 2)
        self.assertEqual(baseline.loc[district[0], "temp_media_media5_h2_obs"], 2)
        weather.loc[weather.semana_inicio > pd.Timestamp("2026-09-27"), "temp_media"] = 99
        pd.testing.assert_frame_equal(climate_vector(weather, enso, cutoff, district), baseline)
        weather.loc[weather.semana_inicio.eq("2026-09-27"), "fecha_chirps_disponible"] = "2026-10-18"
        self.assertTrue(pd.isna(climate_vector(weather, enso, cutoff, district).iloc[0]["precip_total_mm_media5_h2_obs"]))


class TestLivePublication(unittest.TestCase):
    def test_republishes_after_threshold_changes_and_reads_a_new_week(self):
        with TemporaryDirectory() as directory, ExitStack() as cleanup:
            root = Path(directory)
            folder = root / "model"
            folder.mkdir()
            synthetic_bundle(folder)
            districts = load_ubigeo_catalog(UBIGEO_CATALOG).ubigeo.tolist()
            geo = root / "geografia.csv"
            pd.DataFrame({"ubigeo": districts, "lat": -5.0, "lon": -80.0, "elevacion_dem90": 100}).to_csv(geo, index=False)
            package = folder / "paquete.json"
            config = json.loads(package.read_text())
            config["fuentes"] = {"geografia": hashlib.sha256(geo.read_bytes()).hexdigest()}
            package.write_text(json.dumps(config), encoding="utf-8")
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"paquetes": [{"archivos": [{
                "ruta": package.relative_to(root).as_posix(), "sha256": hashlib.sha256(package.read_bytes()).hexdigest(),
            }]}]}), encoding="utf-8")

            from denguekay.serving.demo_b3_v4 import prepare_observations
            template, _ = prepare_observations(folder, config, "a" * 64)
            cutoff = date(2025, 1, 18)
            weeks = pd.Series(pd.date_range("2019-01-06", cutoff, freq="W-SUN"))
            calendar = mmwr_epi_week(weeks)
            observations = [
                {"ubigeo": u, "id_semana": load_data.week_id(w.anio_epi, w.semana_epi), "casos_dengue": 4,
                 "brote": False, "umbral_brote_casos": 4, "casos_solo_confirmados": True,
                 "fuente_casos": "sala_situacional", "estado_cobertura": "verificado"}
                for w in calendar.itertuples() for u in districts
            ]
            batch = replace(template, observaciones=observations, fecha_corte_datos=cutoff)
            motor = motor_temporal(root)
            cleanup.callback(motor.dispose)
            storage = LocalStorage(root / "storage")
            with patch.multiple(v4, V4_FROZEN=folder, V4_DATA_MANIFEST=manifest,
                                V4_GEOGRAPHY=geo, ROOT=root), \
                    patch.object(v4, "prepare_load", return_value=batch), \
                    patch.object(v4, "source_hashes", return_value=batch.hashes), \
                    patch("denguekay.serving.publish.log_report", return_value="test"):
                initial = publish(motor, storage=storage, run_inference=True, select_experimental=True)
                self.assertEqual(initial["paquete"]["tipo_predictor"], v4.KIND)
                self.assertEqual([(r["id_semana_corte"], r["disponibles"]) for r in initial["inferencias_vigentes"]],
                                 [(202503, 65)] * 3)
                with transaction(motor) as session:
                    parameter = session.get(SystemParameter, "umbrales_aceptacion")
                    parameter.valor = {**parameter.valor, "bloque": "temporada_2025",
                                       "precision": 0, "recall": 0, "f1": 0, "razon_error_base": 1}
                updated = publish(motor, storage=storage, select_experimental=True)
                self.assertFalse(updated["reutilizada"])
                self.assertNotEqual(initial["id_ejecucion"], updated["id_ejecucion"])
                self.assertTrue(all(row["cumple_umbrales"] for row in updated["versiones"]))
                self.assertEqual(initial["paquete"]["codigo"], updated["paquete"]["codigo"])
                self.assertTrue(publish(motor, storage=storage)["reutilizada"])

    def test_changes_in_cutoff_reload_the_same_source_files(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            bundle = folder / "model"
            bundle.mkdir()
            synthetic_bundle(bundle)
            from denguekay.serving.demo_b3_v4 import prepare_observations, read_bundle

            config, digest = read_bundle(bundle)
            first, _ = prepare_observations(bundle, config, digest)
            district = first.observaciones[0]["ubigeo"]
            first = replace(first, nino12=[{"mes": date(2024, 12, 1),
                                          "fecha_disponible": date(2025, 1, 10), "anomalia": -0.5}])
            extra = {**first.observaciones[0], "id_semana": 202503, "casos_solo_confirmados": True}
            second = replace(first, observaciones=[*first.observaciones, extra], fecha_corte_datos=date(2025, 1, 18))

            motor = motor_temporal(folder)
            try:
                with transaction(motor) as session:
                    load_data.persist_load(session, first)
                    result = load_data.persist_load(session, second)
                    self.assertFalse(result["reutilizada"])
                    self.assertEqual(result["id_semana_corte"], 202503)
                    self.assertTrue(session.get(WeeklyObservation, (district, 202503)).casos_solo_confirmados)
                    self.assertTrue(load_data.persist_load(session, second)["reutilizada"])
            finally:
                motor.dispose()

    def test_invalid_options_are_rejected(self):
        for options in ({"semanas_provisionales": -1}, {"sala": "../data.csv"}, {"configuracion": "v3"}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                v4.validate(HORIZONS, options)
