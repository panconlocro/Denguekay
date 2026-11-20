"""Metadata the V4 publication registers (HU0008-3 and HU0008-4): SHAP importances and the temporal partition.

The metadata never touches the booster, the parameters or the forecasts: the synthetic tests compare the prepared
package with the archived one, and the Release tests rebuild the frozen training matrix with the real inputs."""

from dataclasses import replace
from datetime import date
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from sqlalchemy import select

from backend_support import motor_temporal
from serving.test_demo_b3_v4 import HORIZONS, SEED, synthetic_bundle
from denguekay.config.paths import CONFIG, UBIGEO_CATALOG, V4_FROZEN
from denguekay.data.calendar import mmwr_epi_week
from denguekay.data.processing.epi_sala import load_ubigeo_catalog
from denguekay.db.models import ModelVersion, Prediction, VariableImportance
from denguekay.db.session import transaction
from denguekay.model import refit_v4 as refit
from denguekay.pipelines.v4_weekly import serving_ready
from denguekay.serving import demo_b3_v4 as demo, load_data
from denguekay.serving.inference import package_of, select_versions
from denguekay.serving.models import thresholds
from denguekay.serving.predictors import v2_e3_s4 as v2, v4_b3_live as v4
from denguekay.serving import publish as publish_module
from denguekay.serving.publish import publish
from denguekay.serving.settings import service_settings
from denguekay.serving.storage import LocalStorage

CRITERIA = {"bloques": ["temporada_2025"], "recall_minimo": 0.0, "precision_minima": 0.0, "f1_minimo": 0.0,
            "proporcion_error_persistencia": 10.0}


def prepared_synthetic(root):
    """``v4.prepare`` of a synthetic package, and the archived package built from the same folder."""
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
    with patch.multiple(v4, V4_FROZEN=folder, V4_DATA_MANIFEST=manifest, V4_GEOGRAPHY=geo, ROOT=root):
        prepared = v4.prepare(HORIZONS, {})
    config, digest = demo.read_bundle(folder)
    _, observations = demo.prepare_observations(folder, config, digest)
    return folder, config, prepared.package, demo.build_package(folder, config, digest, observations)


class TestPreparedSyntheticPackage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = TemporaryDirectory()
        cls.addClassCleanup(directory.cleanup)
        cls.folder, cls.config, cls.built, cls.archived = prepared_synthetic(Path(directory.name))

    def test_the_six_versions_carry_ranked_importances_shared_by_both_tasks_of_a_horizon(self):
        columns = self.config["columnas"]["b3_obs"]
        self.assertEqual(len(self.built.versions), 6)
        by_horizon = {}
        for spec in self.built.versions:
            with self.subTest(task=spec.tarea, horizon=spec.horizonte):
                self.assertTrue(spec.importances)
                self.assertEqual([row["rango"] for row in spec.importances], list(range(1, len(columns) + 1)))
                self.assertEqual(sorted(row["variable"] for row in spec.importances), sorted(columns))
                self.assertTrue(all(np.isfinite(row["importancia"]) and row["importancia"] >= 0
                                    for row in spec.importances))
                by_horizon.setdefault(spec.horizonte, []).append(spec.importances)
        for h, (first, second) in by_horizon.items():
            self.assertEqual(first, second, f"h={h}")

    def test_reproducibility_has_the_training_calibration_interval_and_partition(self):
        for spec in self.built.versions:
            with self.subTest(task=spec.tarea, horizon=spec.horizonte):
                repro = spec.data["reproducibilidad"]
                for key in ("entrenamiento_inicio", "entrenamiento_corte", "filas_entrenamiento", "calibracion",
                            "intervalo", "tipo_importancia", "nota_importancias", "particion_temporal",
                            "configuracion", "semilla", "sha256_paquete_paper", "alcance"):
                    self.assertIn(key, repro)
                self.assertEqual(repro["tipo_importancia"], v2.IMPORTANCE)
                self.assertIn("comparten booster", repro["nota_importancias"])
                self.assertEqual(repro["filas_entrenamiento"], self.config["modelos"][f"b3_obs_s{SEED}"]
                                 ["filas_entrenamiento"])
                platt = self.config["modelos"][f"b3_obs_s{SEED}"]["por_horizonte"][str(spec.horizonte)]
                self.assertEqual(repro["calibracion_parametros"]["peso_modelo"], platt["peso_modelo"])
                self.assertEqual(repro["calibracion_parametros"]["platt"]["a"], platt["platt"]["a"])
                blocks = repro["particion_temporal"]["bloques"]
                published = spec.data["metricas"]["bloques"]
                self.assertEqual(set(blocks), set(published))
                for name, block in blocks.items():
                    self.assertEqual(block["n_prueba"], published[name]["n"])
                    self.assertLessEqual(block["primera_semana_objetivo"], block["ultima_semana_objetivo"])

    def test_the_partition_blocks_carry_the_fit_cutoff_or_the_rule_as_text(self):
        blocks = self.built.versions[0].data["reproducibilidad"]["particion_temporal"]["bloques"]
        # The synthetic OOS has one target week (2024-12-29) at the three horizons: the earliest origin is h=4's.
        season = blocks["temporada_2025"]
        self.assertEqual((season["corte_ajuste"], season["primera_semana_objetivo"], season["ultima_semana_objetivo"],
                          season["n_prueba"]), ("2024-12-07", "2024-12-29", "2024-12-29", 65))
        pooled = blocks[demo.ACCEPTANCE_BLOCK]
        self.assertIsNone(pooled["corte_ajuste"])
        self.assertIn("cada temporada se ajusta una vez", pooled["regla_ajuste"])
        self.assertEqual(set(pooled["cortes_por_temporada"]), {"2025"})

    def test_the_metadata_does_not_change_files_forecasts_metrics_or_thresholds(self):
        """The prepared package equals the archived one in everything that produces or measures a forecast."""
        for name, content in self.archived.files.items():
            if name != v4.frozen.SNAPSHOT:
                self.assertEqual(self.built.files[name], content, name)
        pd.testing.assert_frame_equal(self.built.oos, self.archived.oos)
        self.assertEqual(self.built.horizons, self.archived.horizons)
        self.assertEqual(self.built.variables, self.archived.variables)
        for new, old in zip(self.built.versions, self.archived.versions, strict=True):
            self.assertEqual((new.tarea, new.horizonte, new.code_prefix), (old.tarea, old.horizonte, old.code_prefix))
            self.assertEqual({k: v for k, v in new.data.items() if k != "reproducibilidad"},
                             {k: v for k, v in old.data.items() if k != "reproducibilidad"})
        self.assertEqual(thresholds(self.built, CRITERIA), thresholds(self.archived, CRITERIA))

    def test_new_metadata_changes_the_manifest_options_so_a_republication_registers_new_versions(self):
        self.assertIn("huella_metadatos", self.built.options)
        self.assertEqual({k: v for k, v in self.built.options.items() if k != "huella_metadatos"},
                         self.archived.options)

    def test_a_refit_package_without_the_importances_file_is_refused(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / "reajuste"
            folder.mkdir()
            synthetic_bundle(folder)
            config = json.loads((folder / "paquete.json").read_text())
            config["archivos"].pop(refit.IMPORTANCES_FILE)
            (folder / refit.IMPORTANCES_FILE).unlink()
            (folder / "paquete.json").write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "no trae importancias_b3_obs_s17.json"):
                v4.training_importances(folder, config, (folder / f"b3_obs_s{SEED}.ubj").read_bytes())


def live_batch(folder, districts):
    """The database load a publication reads (the observations of the synthetic package up to its cutoff)."""
    config, _ = demo.read_bundle(folder)
    template, _ = demo.prepare_observations(folder, config, "a" * 64)
    cutoff = date(2025, 1, 18)
    calendar = mmwr_epi_week(pd.Series(pd.date_range("2019-01-06", cutoff, freq="W-SUN")))
    observations = [
        {"ubigeo": u, "id_semana": load_data.week_id(w.anio_epi, w.semana_epi), "casos_dengue": 4,
         "brote": False, "umbral_brote_casos": 4, "casos_solo_confirmados": True,
         "fuente_casos": "sala_situacional", "estado_cobertura": "verificado"}
        for w in calendar.itertuples() for u in districts]
    return replace(template, observaciones=observations, fecha_corte_datos=cutoff)


def forecasts(motor):
    with transaction(motor) as session:
        return session.execute(select(Prediction.ubigeo, Prediction.horizonte, Prediction.id_semana_corte,
                                      Prediction.probabilidad_brote, Prediction.casos_estimados, Prediction.nivel_riesgo)
                               .order_by(Prediction.horizonte, Prediction.ubigeo)).all()


class TestPackageRegisteredBeforeTheMetadata(unittest.TestCase):
    """After the release, the weekly update runs the new code against the package published today (without the
    metadata fingerprint in its manifest): it must load it and give the very same forecasts."""

    @staticmethod
    def as_develop_built_it(real_prepare):
        """``prepare`` as develop did it: the manifest options without ``huella_metadatos`` and the origin as the
        only reproducibility, with no importances. The files (booster, parameters, geography) are the same."""
        def prepare(horizons, options):
            prepared = real_prepare(horizons, options)
            built = prepared.package
            versions = [replace(spec, importances=[], data={**spec.data, "reproducibilidad": built.oos_detail})
                        for spec in built.versions]
            options_before = {k: v for k, v in built.options.items() if k != "huella_metadatos"}
            return replace(prepared, package=replace(built, versions=versions, options=options_before))
        return prepare

    def test_it_loads_serves_and_emits_exactly_the_forecasts_of_the_new_package(self):
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
            batch = live_batch(folder, districts)
            cfg = service_settings(CONFIG, environ={})
            real_prepare = v4.prepare
            patches = dict(V4_FROZEN=folder, V4_DATA_MANIFEST=manifest, V4_GEOGRAPHY=geo, ROOT=root)
            runs = {}
            for name, prepare in (("old", self.as_develop_built_it(real_prepare)), ("new", real_prepare)):
                (root / name).mkdir()
                runs[name] = (motor_temporal(root / name), LocalStorage(root / name / "storage"))
                cleanup.callback(runs[name][0].dispose)
                # The publication identity includes the hash of the code, which differs between develop and this branch.
                code = {"src/denguekay/serving/old_release.py": "0" * 64} if name == "old" else publish_module.code_hashes()
                with patch.multiple(v4, **patches), patch.object(v4, "prepare", prepare), \
                        patch.object(v4, "prepare_load", return_value=batch), \
                        patch.object(v4, "source_hashes", return_value=batch.hashes), \
                        patch.object(publish_module, "code_hashes", return_value=code), \
                        patch("denguekay.serving.publish.log_report", return_value="test"):
                    publish(runs[name][0], cfg=cfg, storage=runs[name][1], run_inference=True, select_experimental=True)
            (old, old_storage), (new, _) = runs["old"], runs["new"]

            with transaction(old) as session:
                versions, reason = select_versions(session, 2, True)
                self.assertIsNone(reason)
                loaded = package_of(versions, old_storage)
            self.assertNotIn("huella_metadatos", loaded.manifest["opciones"])
            self.assertEqual(loaded.kind, v4.KIND)
            self.assertEqual(serving_ready(old, cfg, old_storage), (True, None))
            old_rows, new_rows = forecasts(old), forecasts(new)
            self.assertEqual(sum(row.id_semana_corte == 202503 for row in old_rows), 65 * len(HORIZONS))   # current cutoff
            self.assertEqual(old_rows, new_rows)   # probabilities, cases and risk levels: exactly the same

            # The republication that follows the release registers new versions with the metadata and keeps the
            # forecasts of the old ones untouched until the next emission.
            with patch.multiple(v4, **patches), patch.object(v4, "prepare_load", return_value=batch), \
                    patch.object(v4, "source_hashes", return_value=batch.hashes), \
                    patch("denguekay.serving.publish.log_report", return_value="test"):
                again = publish(old, cfg=cfg, storage=old_storage, select_experimental=True)
            self.assertFalse(again["reutilizada"])
            self.assertEqual(serving_ready(old, cfg, old_storage), (True, None))
            self.assertEqual(forecasts(old), old_rows)
            with transaction(old) as session:
                versions_now = list(session.scalars(select(ModelVersion).order_by(ModelVersion.id_version)))
                self.assertEqual(len(versions_now), 12)   # the six old ones stay and six new ones are added
                with_importances = {row.id_version for row in session.scalars(select(VariableImportance))}
                self.assertEqual(with_importances, {v.id_version for v in versions_now[6:]})
                self.assertTrue(all("particion_temporal" in v.reproducibilidad for v in versions_now[6:]))
                self.assertTrue(all("particion_temporal" not in v.reproducibilidad for v in versions_now[:6]))


class TestTemporalPartition(unittest.TestCase):
    def tables(self):
        """Two seasons of 3 districts; the second season's earliest origin (any horizon) is its fit cutoff."""
        rows = []
        for block, first in (("temporada_2024", "2023-08-27"), ("temporada_2025", "2024-08-25")):
            for h in HORIZONS:
                for week in range(3):
                    target = pd.Timestamp(first) + pd.Timedelta(weeks=week)
                    rows.append({"bloque": block, "horizonte": h, "ubigeo": "200101", "semana_inicio": target,
                                 "origen_cierre": target + pd.Timedelta(days=6, weeks=-h)})
        archive = pd.DataFrame(rows)
        return archive, archive.iloc[:-1]   # the last row has no observation: it leaves the test table

    def test_the_cutoff_is_the_earliest_origin_of_the_block_over_the_three_horizons(self):
        archive, table = self.tables()
        partition = demo.temporal_partition(archive, table)
        block = partition[2]["temporada_2025"]
        self.assertEqual(block["corte_ajuste"], "2024-08-03")   # h=4 of the first target week 2024-08-25
        self.assertEqual((block["primera_semana_objetivo"], block["ultima_semana_objetivo"]), ("2024-08-25", "2024-09-08"))
        self.assertEqual(block["n_prueba"], 3)
        self.assertEqual(partition[4]["temporada_2025"]["n_prueba"], 2)   # counted from the test table, as the metrics are

    def test_the_pooled_block_has_no_single_cutoff_but_lists_each_season(self):
        archive, table = self.tables()
        pooled = demo.temporal_partition(archive, table)[2][demo.ACCEPTANCE_BLOCK]
        self.assertIsNone(pooled["corte_ajuste"])
        self.assertEqual(pooled["cortes_por_temporada"], {"2024": "2023-08-05", "2025": "2024-08-03"})
        self.assertEqual(pooled["n_prueba"], 6)   # three target weeks of each season at h=2


@unittest.skipUnless(os.getenv("DENGUEKAY_TEST_V4_RELEASE") == "1" or (
    (V4_FROZEN / "paquete.json").is_file() and all(p.is_file() for p in refit.frozen_sources().values())),
    "Requires the V4 Release inputs (release_bundles --version v4 --solo datos_v4.zip modelo_v4.zip)")
class TestFrozenV4Matrix(unittest.TestCase):
    """The real matrix: the one that must give 73 775 rows and the columns of columnas.b3_obs, or nothing is published."""

    @classmethod
    def setUpClass(cls):
        from xgboost import XGBRegressor

        cls.config = json.loads((V4_FROZEN / "paquete.json").read_text(encoding="utf-8"))
        cls.columns = cls.config["columnas"]["b3_obs"]
        cls.regressor = XGBRegressor()
        cls.regressor.load_model(V4_FROZEN / f"b3_obs_s{SEED}.ubj")
        cls.train = refit.frozen_training_matrix(cls.config, cls.regressor)

    def test_rows_and_columns_equal_the_package_record(self):
        self.assertEqual(len(self.train), 73775)
        self.assertEqual(len(self.train), self.config["modelos"][f"b3_obs_s{SEED}"]["filas_entrenamiento"])
        self.assertTrue(np.isfinite(self.train[self.columns].to_numpy(float)).all())
        self.assertEqual(self.regressor.get_booster().feature_names, self.columns)

    def test_importances_cover_every_column_in_each_horizon_with_rank_1_to_n(self):
        payload = refit.importances_payload(self.regressor, self.train, self.columns)
        self.assertEqual(set(payload["importancias"]), {"2", "3", "4"})
        for h, rows in payload["importancias"].items():
            with self.subTest(horizon=h):
                self.assertEqual(sorted(row["variable"] for row in rows), sorted(self.columns))
                self.assertEqual([row["rango"] for row in rows], list(range(1, len(self.columns) + 1)))
                values = [row["importancia"] for row in rows]
                self.assertEqual(values, sorted(values, reverse=True))

    def test_a_matrix_with_other_rows_is_refused(self):
        config = json.loads(json.dumps(self.config))
        config["modelos"][f"b3_obs_s{SEED}"]["filas_entrenamiento"] = 73774
        with self.assertRaisesRegex(ValueError, "73775 filas"):
            refit.frozen_training_matrix(config, self.regressor)

    def test_other_dispersions_are_refused(self):
        config = json.loads(json.dumps(self.config))
        config["modelos"][f"b3_obs_s{SEED}"]["alphas"][0] *= 1.01
        with self.assertRaisesRegex(ValueError, "dispersiones"):
            refit.frozen_training_matrix(config, self.regressor)

    def test_a_source_that_differs_from_the_package_is_refused(self):
        config = json.loads(json.dumps(self.config))
        config["fuentes"]["enso_nino12_mensual.csv"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "enso_nino12_mensual.csv difiere"):
            refit.frozen_training_matrix(config, self.regressor)

    def test_prepare_registers_importances_and_partition_without_touching_the_forecast_files(self):
        prepared = v4.prepare(HORIZONS, {})
        for spec in prepared.package.versions:
            self.assertEqual(len(spec.importances), len(self.columns))
            repro = spec.data["reproducibilidad"]
            self.assertEqual((repro["filas_entrenamiento"], repro["entrenamiento_inicio"]), (73775, "2005-01-02"))
            self.assertEqual(set(repro["particion_temporal"]["bloques"]), set(spec.data["metricas"]["bloques"]))
        for h in HORIZONS:
            first, second = [s.importances for s in prepared.package.versions if s.horizonte == h]
            self.assertEqual(first, second)
        self.assertEqual(prepared.package.files["booster.ubj"], (V4_FROZEN / f"b3_obs_s{SEED}.ubj").read_bytes())


if __name__ == "__main__":
    unittest.main()
