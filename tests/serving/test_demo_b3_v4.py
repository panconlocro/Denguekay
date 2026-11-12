"""Publish and serve a synthetic frozen B3 package without local research files."""

from datetime import date
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import numpy as np
import pandas as pd
from sqlalchemy.engine import URL
from xgboost import XGBRegressor

from apps.api.main import create_app
from denguekay.config.paths import UBIGEO_CATALOG
from denguekay.data.calendar import mmwr_epi_week
from denguekay.data.processing.epi_sala import load_ubigeo_catalog
from denguekay.db.session import make_engine
from denguekay.serving import demo_database
from denguekay.serving.settings import service_settings
from denguekay.serving.storage import LocalStorage


CUTOFF = date(2025, 1, 11)
HORIZONS = (2, 3, 4)
SEED = 17


def synthetic_bundle(folder):
    districts = load_ubigeo_catalog(UBIGEO_CATALOG).ubigeo.tolist()
    cases = np.arange(len(districts)) % 5
    vectors = pd.DataFrame({"hist_lag_a": cases})
    margin = np.repeat(np.log(cases + 0.5)[:, None], len(HORIZONS), axis=1)
    model = XGBRegressor(objective="count:poisson", n_estimators=2, max_depth=2, tree_method="hist",
                         multi_strategy="multi_output_tree", random_state=SEED, n_jobs=1)
    model.fit(vectors, np.column_stack([cases + h for h in HORIZONS]), base_margin=margin)
    model.save_model(folder / f"b3_obs_s{SEED}.ubj")
    vectors.assign(ubigeo=districts, umbral_h2=2, umbral_h3=3, umbral_h4=4).to_csv(
        folder / "origen.csv", index=False,
    )
    starts = pd.date_range("2024-12-01", CUTOFF, freq="W-SUN")
    calendar = mmwr_epi_week(pd.Series(starts))
    observed = [
        {"ubigeo": district, "semana_inicio": start, "anio": week.anio_epi, "semana": week.semana_epi,
         "casos_Dengue": int(count), "brote": int(count >= 2), "umbral_brote_casos": 2}
        for start, week in zip(starts, calendar.itertuples())
        for district, count in zip(districts, cases)
    ]
    pd.DataFrame(observed).to_csv(folder / "observaciones.csv.gz", index=False)
    target = pd.Timestamp("2024-12-29")
    forecasts = [
        {"ubigeo": district, "semana_inicio": target, "horizonte": h, "bloque": "temporada_2025",
         "origen_cierre": target + pd.Timedelta(days=6, weeks=-h),
         "probabilidad_calibrada": (count + 1) / 6, "conteo_publicado": float(count)}
        for h in HORIZONS for district, count in zip(districts, cases)
    ]
    pd.DataFrame(forecasts).to_csv(folder / f"oos_b3_s{SEED}.csv.gz", index=False)
    config = {
        "version": "v4-b3", "corte": CUTOFF.isoformat(), "congelado_utc": "2025-01-12T00:00:00+00:00",
        "horizontes": list(HORIZONS), "corte_alerta": 0.5, "semilla_demo": SEED,
        "formulacion": "E3", "hiperparametros": {"n_estimators": 2}, "validaciones": {},
        "columnas": {"b3_obs": ["hist_lag_a"]},
        "modelos": {f"b3_obs_s{SEED}": {
            "alphas": [0.7, 1.0, 1.3],
            "por_horizonte": {str(h): {"platt": {"a": 1.0, "b": 0.0}, "peso_modelo": 0.75} for h in HORIZONS},
        }},
        "archivos": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in folder.iterdir()},
    }
    (folder / "paquete.json").write_text(json.dumps(config), encoding="utf-8")


class TestFrozenB3Demo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(directory.cleanup)
        cls.root = Path(directory.name)
        cls.bundle = cls.root / "bundle"
        cls.bundle.mkdir()
        synthetic_bundle(cls.bundle)

    def test_publishes_the_frozen_bundle_and_serves_every_horizon(self):
        with patch("denguekay.serving.demo_b3_v4.log_report", return_value="run-prueba"):
            result = demo_database.build(self.root / "demo", package_v4=self.bundle)
        self.assertEqual(result["fecha_corte_datos"], CUTOFF.isoformat())
        self.assertEqual(set(result["versiones"]), {f"v4-{task}-h{h}-1" for h in HORIZONS for task in ("clf", "reg")})
        self.assertEqual(result["inferencias_vigentes"], [
            {"horizonte": h, "id_semana_corte": 202502, "disponibles": 65} for h in HORIZONS
        ])
        engine = make_engine(URL.create("sqlite", database=result["bd"]))
        self.addCleanup(engine.dispose)
        app = create_app(engine, service_settings(), api_key="", storage=LocalStorage(result["storage"]))
        with TestClient(app) as client:
            for h in HORIZONS:
                with self.subTest(horizon=h):
                    response = client.get("/api/v1/predicciones", params={"horizonte": h, "tamano_pagina": 100})
                    self.assertEqual(response.status_code, 200)
                    rows = response.json()["elementos"]
                    self.assertEqual(len(rows), 65)
                    self.assertEqual({row["semana_objetivo"]["id_semana"] for row in rows}, {202502 + h})
                    self.assertTrue(all(row["disponible"] and row["experimental"] for row in rows))
                    self.assertTrue(all(0 <= row["probabilidad_brote"] <= 1 and row["casos_estimados"] >= 0
                                        for row in rows))
                    self.assertTrue(all(row["nivel_intervalo"] is None for row in rows))

    def test_refuses_a_corrupted_bundle(self):
        from shutil import copytree

        invalid = copytree(self.bundle, self.root / "invalid")
        (invalid / "origen.csv").write_text("corrupted", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Artefacto V4 distinto al manifiesto: origen.csv"):
            demo_database.build(self.root / "rejected-demo", package_v4=invalid)
