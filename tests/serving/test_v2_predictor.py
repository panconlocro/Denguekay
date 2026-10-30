"""Predictor v2_e3_s4: vector, probability, interval, package and publication (phase 4).

The publication trains a real E3 regressor on the 6 districts of tests/fixtures/v2_serving/ (no data/);
the parity with the frozen configuration is in test_v2_parity.py.
"""

from dataclasses import replace
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

import numpy as np
import pandas as pd
from scipy import stats
from sqlalchemy import func, select

import v2_support as vs
from backend_support import datos_muestra, motor_temporal
from serving_support import V0_SELECCION, preparar_muestra, publish_sample
from apps.api.main import create_app
from denguekay.db.models import Prediction, Run, SystemParameter, VariableImportance, ModelVersion
from denguekay.db.session import transaction
from denguekay.evaluation import protocol as pa
from denguekay.model.frozen_configs import CONFIG_2026
from denguekay.serving import inference, parameters
from denguekay.serving.artifacts import InvalidArtifact
from denguekay.serving.inputs import CLIMATE, ServingInputs
from denguekay.serving.predictors import v2_e3_s4 as v2
from denguekay.serving.predictors.base import InferenceUnavailable
from denguekay.serving.storage import LocalStorage

COLUMNS = list(CONFIG_2026["columnas"])
RULE = {"anios_previos": 5, "k_desviaciones": 1.5, "minimo_casos": 2}


def memory_inputs(close, panel=None):
    """ServingInputs of the fixtures closed at ``close``, without a database."""
    panel = vs.read("panel_muestra.csv") if panel is None else panel
    closed = panel.loc[(panel.semana_inicio + pd.Timedelta(days=6)).le(pd.Timestamp(close))]
    cases = closed[["ubigeo", "anio", "semana", "semana_inicio", "casos_Dengue"]].astype({"casos_Dengue": float})
    climate = closed[["ubigeo", "anio", "semana", "semana_inicio", *CLIMATE.values()]]
    return ServingInputs(cases.reset_index(drop=True), climate.reset_index(drop=True), None, None, RULE)


def cutoff(close):
    return SimpleNamespace(fecha_fin=pd.Timestamp(close).date())


class TestVectorAndProbability(unittest.TestCase):
    close = "2025-06-07"

    def test_platt_coefficients_equal_logistic_regression(self):
        rng = np.random.default_rng(17)
        p = rng.uniform(0, 1, 4000)
        y = (rng.uniform(0, 1, 4000) < p ** 1.3).astype(int)
        model = pa.fit_platt(p, y)
        q = np.concatenate([rng.uniform(0, 1, 500), [0.0, 1.0, 1e-9, 1 - 1e-9]])
        served = v2.platt(q, float(model.coef_[0, 0]), float(model.intercept_[0]))
        self.assertLessEqual(np.abs(served - model.predict_proba(pa.platt_logit(q).reshape(-1, 1))[:, 1]).max(), 1e-12)
        self.assertLessEqual(np.abs(served - pa.fit_calibrator(p, y)(q)).max(), 1e-12)

    def test_interval_is_the_central_nb2_interval(self):
        mu, alpha = np.array([0.0, 0.4, 3.0, 25.0]), 0.9
        low, high = v2.interval(mu, alpha, 0.80)
        r = 1 / alpha
        dist = stats.nbinom(r, r / (r + np.clip(mu, 1e-9, None)))
        np.testing.assert_array_equal(low, dist.ppf(0.10))
        np.testing.assert_array_equal(high, dist.ppf(0.90))
        self.assertTrue((low <= high).all() and (low >= 0).all())
        wider = v2.interval(mu, alpha, 0.95)
        self.assertTrue((wider[0] <= low).all() and (wider[1] >= high).all())

    def test_threshold_comes_from_the_cases(self):
        inputs = memory_inputs(self.close)
        vectors, reasons = v2.origin_vectors(inputs, cutoff(self.close), COLUMNS)
        self.assertEqual(reasons, {})
        from denguekay.features.outbreak_label import future_outbreak_threshold

        origin = v2.origin_week(cutoff(self.close))
        for h in v2.HORIZONS:
            week = pd.Timestamp(origin) + pd.Timedelta(weeks=h)
            from denguekay.data.calendar import mmwr_epi_week

            cal = mmwr_epi_week(pd.Series([week])).iloc[0]
            targets = pd.DataFrame({"ubigeo": list(vectors.index), "anio": int(cal.anio_epi), "semana": int(cal.semana_epi)})
            expected = future_outbreak_threshold(inputs.cases, None, targets, multiplicador=1.5, anios_previos=5)
            np.testing.assert_array_equal(vectors[h].to_numpy(), expected.to_numpy())

    def test_missing_climate_makes_the_district_unavailable(self):
        panel = vs.read("panel_muestra.csv")
        last = panel.semana_inicio.eq(pd.Timestamp(self.close) - pd.Timedelta(days=6)) & panel.ubigeo.eq("200101")
        panel.loc[last, "precip_total_mm"] = np.nan
        vectors, reasons = v2.origin_vectors(memory_inputs(self.close, panel), cutoff(self.close), COLUMNS)
        self.assertEqual(reasons, {"200101": v2.NO_CLIMATE_REASON})
        self.assertNotIn("200101", vectors.index)
        self.assertEqual(len(vectors), len(vs.DISTRICTS) - 1)

    def test_an_old_gap_only_shortens_the_climate_run(self):
        panel = vs.read("panel_muestra.csv")
        panel.loc[panel.semana_inicio.eq(pd.Timestamp("2019-03-03")) & panel.ubigeo.eq("200101"), "hum_rel_media"] = np.nan
        vectors, reasons = v2.origin_vectors(memory_inputs(self.close, panel), cutoff(self.close), COLUMNS)
        reference, _ = v2.origin_vectors(memory_inputs(self.close), cutoff(self.close), COLUMNS)
        self.assertEqual(reasons, {})
        self.assertAlmostEqual(vectors.loc["200101", "hum_rel_media_media5_h2"],
                               reference.loc["200101", "hum_rel_media_media5_h2"], places=10)

    def test_rule_of_another_model_is_rejected(self):
        inputs = replace(memory_inputs(self.close), outbreak_rule={**RULE, "minimo_casos": 1})
        with self.assertRaisesRegex(InferenceUnavailable, "regla de brote"):
            v2.origin_vectors(inputs, cutoff(self.close), COLUMNS)

    def test_no_cases_is_unavailable(self):
        inputs = memory_inputs("2016-12-31")
        with self.assertRaises(InferenceUnavailable):
            v2.origin_vectors(inputs, cutoff("2016-12-31"), COLUMNS)


class TestPackage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.built = vs.build_sample(cutoff=vs.package_meta()["corte_bloque"], trained=vs.frozen_fit())

    def package(self, **files):
        """The package with some files replaced (None removes one); the manifest is the original one."""
        from denguekay.serving.package import Package, build_manifest

        manifest = build_manifest(self.built, {(s.horizonte, s.tarea): False for s in self.built.versions})
        content = {k: v for k, v in {**self.built.files, **files}.items() if v is not None}
        return Package(manifest=manifest, files=content, sha256="x" * 64, path="modelos/x/manifest.json")

    def test_manifest_declares_level_formulation_and_files(self):
        self.assertEqual(self.built.interval_level, 0.80)
        self.assertEqual(self.built.options, {"configuracion": "v2", "formulacion": "S4_s3", "nivel_intervalo": 0.80})
        self.assertEqual(set(self.built.files), {v2.BOOSTER, v2.DISPERSION, v2.PLATT})
        self.assertEqual(len(self.built.versions), 6)
        clf = [s for s in self.built.versions if s.tarea == "clasificacion"]
        self.assertTrue(all(s.data["umbral_probabilidad"] == 0.50 and s.data["algoritmo"] == v2.ALGORITHM for s in clf))
        self.assertTrue(all(s.data["umbral_probabilidad"] is None for s in self.built.versions if s.tarea == "regresion"))
        for spec in self.built.versions:
            self.assertEqual(sorted(i["variable"] for i in spec.importances), sorted(COLUMNS))
            self.assertEqual([i["rango"] for i in spec.importances], list(range(1, len(COLUMNS) + 1)))
            self.assertEqual(spec.data["reproducibilidad"]["tipo_importancia"], v2.IMPORTANCE)
            self.assertEqual(spec.data["reproducibilidad"]["grupo_artefacto"], self.built.code)

    def test_invalid_packages_are_rejected(self):
        cases = {"sin platt": {v2.PLATT: None},
                 "alfa no positiva": {v2.DISPERSION: json.dumps({"alfa": {"2": 0, "3": 1, "4": 1}}).encode()},
                 "platt incompleto": {v2.PLATT: json.dumps({"coeficientes": {"2": [1], "3": [1, 0], "4": [1, 0]}}).encode()},
                 "json roto": {v2.DISPERSION: b"{"}, "booster roto": {v2.BOOSTER: b"no es un booster"}}
        for name, files in cases.items():
            with self.subTest(name), self.assertRaises(InvalidArtifact):
                v2.Predictor.from_package(self.package(**files))

    def test_formulation_must_be_s4(self):
        built = replace(self.built, options={**self.built.options, "formulacion": "S1"})
        from denguekay.serving.package import Package, build_manifest

        manifest = build_manifest(built, {(s.horizonte, s.tarea): False for s in built.versions})
        with self.assertRaisesRegex(InvalidArtifact, "S4"):
            v2.Predictor.from_package(Package(manifest=manifest, files=built.files, sha256="x" * 64, path="m"))

    def test_horizon_outside_the_package(self):
        built = vs.build_sample(cutoff=vs.package_meta()["corte_bloque"], trained=vs.frozen_fit(), horizons=(2, 4))
        from denguekay.serving.package import Package, build_manifest

        manifest = build_manifest(built, {(s.horizonte, s.tarea): False for s in built.versions})
        predictor = v2.Predictor.from_package(Package(manifest=manifest, files=built.files, sha256="y" * 64, path="m"))
        with self.assertRaisesRegex(InferenceUnavailable, "sin modelo para h=3"):
            predictor.predict(memory_inputs("2025-06-07"), cutoff("2025-06-07"), (3,))

    def test_frozen_shap_rows_are_the_fit_e3_rows(self):
        """service_rows (SHAP of a frozen booster) selects exactly the rows fit_e3 trains with."""
        prepared = vs.sample_prepared()
        for close in (vs.package_meta()["corte_bloque"], vs.SERVICE_CUTOFF):
            _, _, train = v2.fit_service(prepared, pd.Timestamp(close))
            pd.testing.assert_frame_equal(v2.service_rows(prepared, close), train)

    def test_validate_options(self):
        for horizons, options in (((2, 3, 4), {"configuracion": "v1", "nivel_intervalo": 0.8}),
                                  ((2, 3, 4), {"configuracion": "v2", "nivel_intervalo": 1.0}),
                                  ((5,), vs.options()), ((), vs.options())):
            with self.subTest(horizons=horizons, options=options), self.assertRaises(ValueError):
                v2.validate(horizons, options)
        v2.validate((2, 3, 4), vs.options())


class TestPublication(unittest.TestCase):
    """Real fit on the 6 districts at the service cutoff, publication with the selection and inference."""

    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.engine = motor_temporal(Path(cls.folder.name))
        cls.storage = LocalStorage(Path(cls.folder.name) / "storage")
        cls.built = vs.build_sample()
        cls.summary = vs.publish_v2(cls.engine, cls.storage, cls.built, run_inference=True)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()
        cls.folder.cleanup()

    def test_six_candidate_versions_and_the_selection(self):
        codes = {(v["horizonte"], v["tarea"]): v["codigo"] for v in self.summary["versiones"]}
        self.assertEqual(codes, {(h, t): f"v2-{p}-h{h}-1" for h in (2, 3, 4)
                                 for t, p in (("clasificacion", "clf"), ("regresion", "reg"))})
        self.assertTrue(all(v["estado"] == "candidata" for v in self.summary["versiones"]))
        expected = {h: {"clasificacion": f"v2-clf-h{h}-1", "regresion": f"v2-reg-h{h}-1"} for h in (2, 3, 4)}
        self.assertEqual(self.summary["seleccion_experimental"], expected)
        with transaction(self.engine) as session:
            self.assertEqual(parameters.experimental_selection(session), expected)
            paths = {v.ruta_artefacto for v in session.scalars(select(ModelVersion))}
            self.assertEqual(len(paths), 1)
            self.assertEqual(session.scalar(select(func.count()).select_from(VariableImportance)), 6 * len(COLUMNS))

    def test_current_inference_for_the_three_horizons(self):
        self.assertEqual([r["horizonte"] for r in self.summary["inferencias_vigentes"]], [2, 3, 4])
        with transaction(self.engine) as session:
            rows = list(session.scalars(select(Prediction).where(
                Prediction.id_semana_corte == 202552, Prediction.estado == "disponible")))
            self.assertEqual(len(rows), 3 * len(vs.DISTRICTS))
            for row in rows:
                self.assertIsNotNone(row.casos_intervalo_inferior)
                self.assertLessEqual(row.casos_intervalo_inferior, row.casos_intervalo_superior)
                self.assertIsNotNone(row.id_version_clasificador)

    def test_oos_of_blocks_2022_2025(self):
        blocks = {(o["horizonte"], o["bloque"]) for o in self.summary["oos"]}
        self.assertEqual(blocks, {(h, b) for h in (2, 3, 4) for b in v2.OOS_BLOCKS})
        self.assertEqual(sum(o["predicciones"] for o in self.summary["oos"]), len(self.built.oos))

    def test_interval_level_of_the_package_must_match_the_parameter(self):
        with transaction(self.engine) as session:
            session.get(SystemParameter, "nivel_intervalo_casos").valor = {"nivel": 0.9}
            session.flush()
            versions, _ = inference.select_versions(session, 3, True)
            week = inference.week(session, 202552)
            with self.assertRaisesRegex(InferenceUnavailable, "nivel"):
                inference.predict_cutoff(session, versions, 3, week, self.storage)
            session.rollback()

    def test_api_serves_h3_with_intervals_and_shap_note(self):
        from fastapi.testclient import TestClient
        from serving_support import configuracion_v0

        with TestClient(create_app(self.engine, configuracion_v0(), api_key="k", storage=self.storage)) as client:
            config = client.get("/api/v1/configuracion").json()
            self.assertEqual(config["horizontes_disponibles"], [2, 3, 4])
            body = client.get("/api/v1/predicciones", params={"horizonte": 3}).json()
            available = [e for e in body["elementos"] if e["estado"] == "disponible"]
            self.assertEqual(len(available), len(vs.DISTRICTS))
            self.assertTrue(all(e["casos_intervalo_inferior"] is not None for e in available))
            with transaction(self.engine) as session:
                version = session.scalar(select(ModelVersion).where(ModelVersion.codigo == "v2-reg-h3-1"))
            note = client.get(f"/api/v1/modelos/{version.id_version}/variables").json()["nota"]
            self.assertIn("SHAP", note)


class TestOOSReplaceV0(unittest.TestCase):
    """M6: the v2 OOS replace the v0 ones in the series (same district, cutoff and horizon)."""

    def test_no_v0_oos_row_survives_in_h2_and_h4(self):
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            engine = motor_temporal(folder)
            storage = LocalStorage(folder / "storage")
            try:
                cfg, protocol, prepared = preparar_muestra()
                from denguekay.serving.load_data import persist_load

                data = datos_muestra(folder)
                with transaction(engine) as session:
                    persist_load(session, data)
                publish_sample(engine, data, cfg, protocol, prepared, storage, "run-v0", "huella-v0")
                with transaction(engine) as session:
                    v0_runs = [r.id_ejecucion for r in session.scalars(select(Run).where(Run.tipo == "inferencia"))
                               if (r.detalle or {}).get("origen") == "oos_protocolo"]
                    before = session.scalar(select(func.count()).select_from(Prediction).where(
                        Prediction.id_ejecucion.in_(v0_runs)))
                self.assertGreater(before, 0)
                vs.publish_v2(engine, storage, vs.build_sample(), select=True)
                with transaction(engine) as session:
                    left = session.scalar(select(func.count()).select_from(Prediction).where(
                        Prediction.id_ejecucion.in_(v0_runs)))
                    self.assertEqual(parameters.experimental_selection(session)[2]["clasificacion"], "v2-clf-h2-1")
                    self.assertEqual(parameters.experimental_selection(session)[4], {
                        "clasificacion": "v2-clf-h4-1", "regresion": "v2-reg-h4-1"})
                self.assertEqual(left, 0)
                self.assertNotEqual(V0_SELECCION[4]["clasificacion"], "v2-clf-h4-1")
            finally:
                engine.dispose()


if __name__ == "__main__":
    unittest.main()
