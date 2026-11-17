"""HU0007-4 (US v1.4): the pooled block of the seasons 2022 to 2026 and the thresholds stored in the database."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.engine import URL

from apps.api.main import create_app
from backend_support import motor_temporal
from denguekay.db.session import make_engine, transaction
from denguekay.evaluation.acceptance import evaluate_model_validation
from denguekay.serving import demo_b3_v4, demo_database
from denguekay.serving import parameters as parametros
from denguekay.serving.settings import service_settings
from denguekay.serving.storage import LocalStorage
from serving.test_demo_b3_v4 import HORIZONS, synthetic_bundle

BLOCK = "temporadas_2022_2026"
# Aggregate figures of the frozen V4 (seed 17): recall, precision, F1 and the ratios to the persistence.
REFERENCE = {2: (0.769, 0.824, 0.795, 0.868, 0.861),
             3: (0.723, 0.827, 0.772, 0.824, 0.819),
             4: (0.666, 0.820, 0.735, 0.806, 0.787)}
PERSISTENCE = {"mae": 1.0, "rmse": 2.0}


def block_with(recall, precision, f1, mae_ratio, rmse_ratio):
    return {BLOCK: {
        "bloque": BLOCK,
        "clasificacion": {"alerta_directa": {"recall": recall, "precision": precision, "f1": f1}},
        "regresion": {"conteos": {"mae": mae_ratio * PERSISTENCE["mae"], "rmse": rmse_ratio * PERSISTENCE["rmse"]}},
        "persistencia": {"conteos": dict(PERSISTENCE)},
    }}


class TestThresholdsOfTheUs14(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = TemporaryDirectory()
        cls.addClassCleanup(directory.cleanup)
        cls.engine = motor_temporal(Path(directory.name))
        cls.addClassCleanup(cls.engine.dispose)
        with transaction(cls.engine) as session:
            cls.criteria = parametros.acceptance_criteria(session)

    def test_migration_0009_sets_the_us_v14_values(self):
        self.assertEqual(self.criteria, {
            "bloques": [BLOCK], "recall_minimo": 0.65, "precision_minima": 0.60, "f1_minimo": 0.70,
            "proporcion_error_persistencia": 0.90})

    def test_the_six_v4_versions_are_validated(self):
        for horizon, values in REFERENCE.items():
            metrics = {"bloques": block_with(*values)}
            for kind in ("clasificacion", "regresion"):
                with self.subTest(horizon=horizon, kind=kind):
                    result = evaluate_model_validation(kind, metrics, self.criteria)
                    self.assertEqual(result["estado_validacion"], "validado", result["motivo"])
                    self.assertTrue(result["disponible"])

    def test_a_metric_just_below_the_threshold_stays_experimental(self):
        below = {"recall": (0.6499, 0.824, 0.795, 0.868, 0.861), "precision": (0.769, 0.5999, 0.795, 0.868, 0.861),
                 "f1": (0.769, 0.824, 0.6999, 0.868, 0.861)}
        for name, values in below.items():
            with self.subTest(metric=name):
                result = evaluate_model_validation("clasificacion", {"bloques": block_with(*values)}, self.criteria)
                self.assertEqual(result["estado_validacion"], "experimental")
        for name, values in {"mae": (0.769, 0.824, 0.795, 0.9001, 0.861), "rmse": (0.769, 0.824, 0.795, 0.868, 0.9001)}.items():
            with self.subTest(metric=name):
                result = evaluate_model_validation("regresion", {"bloques": block_with(*values)}, self.criteria)
                self.assertEqual(result["estado_validacion"], "experimental")

    def test_a_season_block_alone_no_longer_decides(self):
        metrics = {"bloques": {"temporada_2024": block_with(*REFERENCE[2])[BLOCK]}}
        result = evaluate_model_validation("clasificacion", metrics, self.criteria)
        self.assertEqual(result["estado_validacion"], "experimental")


class TestPooledBlock(unittest.TestCase):
    def test_pooled_block_adds_the_seasons_2022_to_2026_and_leaves_the_others(self):
        import pandas as pd

        rows = []
        for year, brote in ((2021, 1), (2022, 1), (2023, 0), (2026, 1)):
            rows.append({"horizonte": 2, "bloque": f"temporada_{year}", "brote": brote, "probabilidad_brote": 0.9 if brote else 0.1,
                         "casos_Dengue": 4, "casos_estimados": 3.0, "persistencia": 2})
        table = pd.DataFrame(rows)
        seasons = table[table.bloque.isin(demo_b3_v4.ACCEPTANCE_SEASONS)]
        pooled = demo_b3_v4.block_metrics(BLOCK, seasons)
        self.assertEqual((pooled["n"], pooled["positivos"]), (3, 2))
        self.assertEqual(pooled["clasificacion"]["alerta_directa"]["recall"], 1.0)
        self.assertEqual(pooled["regresion"]["conteos"]["mae"], 1.0)
        self.assertEqual(pooled["persistencia"]["conteos"]["mae"], 2.0)


class TestActivationWithAValidatedVersion(unittest.TestCase):
    def test_a_validated_v4_is_published_without_experimental_flag_and_can_be_activated(self):
        real = demo_b3_v4.block_metrics

        def reference_for_the_pooled_block(block, group):
            horizon = int(group.horizonte.iloc[0])
            if block == BLOCK:
                return block_with(*REFERENCE[horizon])[BLOCK]
            return real(block, group)

        with TemporaryDirectory() as directory, patch.object(demo_b3_v4, "block_metrics", reference_for_the_pooled_block), \
                patch("denguekay.serving.demo_b3_v4.log_report", return_value="run-prueba"):
            root = Path(directory)
            (root / "bundle").mkdir()
            synthetic_bundle(root / "bundle")
            result = demo_database.build(root / "demo", package_v4=root / "bundle")
            engine = make_engine(URL.create("sqlite", database=result["bd"]))
            app = create_app(engine, service_settings(), api_key="clave", storage=LocalStorage(result["storage"]))
            try:
                client = TestClient(app).__enter__()
                models = client.get("/api/v1/modelos/activo").json()["elementos"]
                self.assertEqual(len(models), 2 * len(HORIZONS))
                self.assertTrue(all(not m["experimental"] for m in models))
                for horizon in HORIZONS:
                    prediction = client.get("/api/v1/predicciones", params={"horizonte": horizon}).json()["elementos"][0]
                    self.assertFalse(prediction["experimental"])
                clf = next(m["id_version"] for m in models if m["codigo"].startswith("v4-clf-h2"))
                response = client.post(f"/api/v1/admin/modelos/{clf}/activar", headers={"X-API-Key": "clave"})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["activada"]["estado"], "activa")
            finally:
                client.__exit__(None, None, None)
                engine.dispose()


if __name__ == "__main__":
    unittest.main()
