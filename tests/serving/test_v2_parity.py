"""Model v2 served from the database = the frozen configuration (phase 4), with no training/serving skew.

Fixtures: tests/fixtures/v2_serving/ (tests/v2_support.py), recorded once with the code before phase 4
(commit ab8503b, CPU with 2 threads) on the full data; never re-recorded. Same scheme as the v0 parity
(XGBoost does not train bit for bit the same on every operating system, decision D1):

- ``TestV2VariableParity``: the vector the predictor builds from the database (base_6, B3, A3 and the
  outbreak threshold of t+2, t+3 and t+4) equals ``frozen_configs.origins`` (gold h=2 + B3 in memory) and the
  gold threshold, district by district, for every origin whose t+2 is in 2022 or later. Exact, except
  ``precip_total_mm_media5_h2``: the database stores the precipitation in numeric(7,2) and the mean of 5
  weeks differs from gold by up to 5.7e-14 (measured; it changes no prediction), so that column alone
  uses the agreed tolerance of 1e-9. Origins whose t+2 is in 2021 need 2016 for the threshold: they are
  unavailable with their reason (decision M4).
- ``TestV2ServingParity``: the model of block calendario_2025 trained on the full gold is frozen; served from
  the database it gives the probability (NB2 + Platt) and the cases of ``frozen_configs.predict`` +
  ``calibrate_chronologically`` (≤ 1e-9). Both run on every system of the CI.
- ``TestV2RefitParity``: it recomputes everything from data/ with the current code and the publication's
  ``fit_service``; only in the recording environment and with local data, otherwise skipped with the reason.
"""

import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd
from sqlalchemy import select

import equivalence_support as eq
import v2_support as vs
from backend_support import motor_temporal
from denguekay.db.models import EpiWeek, Prediction
from denguekay.db.session import transaction
from denguekay.model.frozen_configs import CONFIG_2026
from denguekay.serving import inference
from denguekay.serving.inputs import build_inputs
from denguekay.serving.predictors import v2_e3_s4 as v2
from denguekay.serving.predictors.base import InferenceUnavailable
from denguekay.serving.storage import LocalStorage

COLUMNS = list(CONFIG_2026["columnas"])
TOLERANT = {"precip_total_mm_media5_h2": 1e-9}
TOLERANCE = 1e-9


class DatabaseCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.engine = motor_temporal(Path(cls.folder.name))
        cls.storage = LocalStorage(Path(cls.folder.name) / "storage")

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()
        cls.folder.cleanup()

    def week(self, session, close):
        return session.scalar(select(EpiWeek).where(EpiWeek.fecha_fin == pd.Timestamp(close).date()))


class TestV2VariableParity(DatabaseCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from denguekay.serving.load_data import persist_load

        with transaction(cls.engine) as session:
            persist_load(session, vs.load_batch())
        cls.origins = vs.origins()
        # The gold threshold in memory (the matrices of frozen_configs.predict), not the gold CSV: reading that
        # file with the default parser can lose the last bit.
        predictions = vs.predictions()
        cls.thresholds = predictions.set_index(["origen_cierre", "horizonte", "ubigeo"]).umbral_brote_casos

    def test_vector_and_threshold_equal_gold_from_2022(self):
        expected = self.origins.loc[self.origins.origen_cierre.ge(vs.FIRST_2022_TARGET_CUTOFF)]
        worst = dict.fromkeys(COLUMNS, 0.0)
        compared = thresholds = 0
        with transaction(self.engine) as session:
            for close, rows in expected.groupby("origen_cierre"):
                cutoff = self.week(session, close)
                inputs = build_inputs(session, cutoff, v2.Predictor.required_inputs)
                vectors, reasons = v2.origin_vectors(inputs, cutoff, COLUMNS)
                self.assertEqual(reasons, {}, close)
                rows = rows.set_index("ubigeo")
                self.assertEqual(sorted(vectors.index), sorted(rows.index), close)
                for column in COLUMNS:
                    got, want = vectors.loc[rows.index, column].to_numpy(float), rows[column].to_numpy(float)
                    diff = np.abs(got - want)
                    worst[column] = max(worst[column], float(diff.max()))
                    if column in TOLERANT:
                        self.assertLessEqual(diff.max(), TOLERANT[column], (close, column))
                    else:
                        np.testing.assert_array_equal(got, want, err_msg=f"{close} {column}")
                for h in v2.HORIZONS:
                    for ubigeo in rows.index:
                        if (close, h, ubigeo) in self.thresholds.index:
                            self.assertEqual(vectors.loc[ubigeo, h], self.thresholds[close, h, ubigeo], (close, ubigeo, h))
                            thresholds += 1
                compared += len(rows)
        self.assertGreater(compared, 6 * 200)
        self.assertGreater(thresholds, 3 * 6 * 150)
        # The measured difference of the rounded precipitation (numeric(7,2)): far below the tolerance.
        self.assertLess(worst["precip_total_mm_media5_h2"], 1e-12)

    def test_origins_with_targets_in_2021_are_unavailable(self):
        with transaction(self.engine) as session:
            for close in ("2021-09-04", "2021-12-18"):
                cutoff = self.week(session, close)
                inputs = build_inputs(session, cutoff, v2.Predictor.required_inputs)
                with self.subTest(close=close), self.assertRaisesRegex(InferenceUnavailable, "anteriores a 2017"):
                    v2.origin_vectors(inputs, cutoff, COLUMNS)


class TestV2ServingParity(DatabaseCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.meta = vs.package_meta()
        cls.built = vs.build_sample(cutoff=cls.meta["corte_bloque"], trained=vs.frozen_fit())
        cls.summary = vs.publish_v2(cls.engine, cls.storage, cls.built)
        predictions = vs.predictions()
        cls.expected = predictions.loc[predictions.bloque.eq(vs.PARITY_BLOCK[0])]

    def test_frozen_block_model_served_from_the_database(self):
        worst = {"probabilidad_brote": 0.0, "casos_estimados": 0.0}
        compared = 0
        with transaction(self.engine) as session:
            for (close, h), rows in self.expected.groupby(["origen_cierre", "horizonte"]):
                versions, reason = inference.select_versions(session, int(h), True)
                self.assertIsNone(reason)
                _, output = inference.predict_cutoff(session, versions, int(h), self.week(session, close), self.storage)
                for row in rows.itertuples(index=False):
                    served = output[row.ubigeo]
                    for column, want in (("probabilidad_brote", row.probabilidad_calibrada),
                                         ("casos_estimados", row.casos_predichos)):
                        worst[column] = max(worst[column], abs(getattr(served, column) - want))
                    self.assertLessEqual(served.casos_intervalo_inferior, served.casos_intervalo_superior)
                compared += len(rows)
        self.assertEqual(compared, len(self.expected))
        self.assertLessEqual(max(worst.values()), TOLERANCE, worst)

    def test_database_rows_round_the_served_values(self):
        close = self.expected.origen_cierre.max()
        with transaction(self.engine) as session:
            cutoff = self.week(session, close)
            for h in v2.HORIZONS:
                inference.infer(session, h, cutoff.id_semana, storage=self.storage, servir_no_validadas=True)
            rows = self.expected.loc[self.expected.origen_cierre.eq(close)]
            for row in rows.itertuples(index=False):
                stored = session.scalar(select(Prediction).where(
                    Prediction.ubigeo == row.ubigeo, Prediction.id_semana_corte == cutoff.id_semana,
                    Prediction.horizonte == int(row.horizonte)))
                self.assertEqual(stored.estado, "disponible")
                self.assertAlmostEqual(float(stored.probabilidad_brote), round(row.probabilidad_calibrada, 4), places=10)
                self.assertAlmostEqual(float(stored.casos_estimados), round(row.casos_predichos, 2), places=10)

    def test_platt_coefficients_reproduce_the_chronological_calibration(self):
        self.assertEqual(self.meta["platt_max_diferencia_con_calibrate_chronologically"], {"2": 0.0, "3": 0.0, "4": 0.0})


@unittest.skipUnless(vs.same_environment() and eq.data_available(), vs.skip_reason())
class TestV2RefitParity(unittest.TestCase):
    """Everything the fixtures hold from the model, recomputed now from data/ (CPU with 2 threads)."""

    def test_current_code_reproduces_the_recorded_model(self):
        result = vs.compute_frozen(vs.ROOT, vs.ROOT / "data")
        self.assertEqual(result["origenes"], (vs.FIXTURES / "origenes_muestra.csv").read_text(encoding="utf-8").replace("\r\n", "\n"))
        self.assertEqual(result["predicciones"], (vs.FIXTURES / "predicciones_muestra.csv").read_text(encoding="utf-8").replace("\r\n", "\n"))
        meta = vs.package_meta()
        self.assertEqual((result["alfa"], result["platt"], result["corte_bloque"]),
                         (meta["alfa"], meta["platt"], meta["corte_bloque"]))
        import base64

        self.assertEqual(base64.b64decode(result["booster"]), (vs.PACKAGE / "booster.json").read_bytes())

    def test_publication_fit_equals_the_block_model(self):
        """``fit_service`` at the block cutoff (the publication's fit) trains the frozen booster bit for bit."""
        code = ("import json, base64, pandas as pd, v2_support as vs\n"
                "from denguekay.serving.predictors import v2_e3_s4 as v2\n"
                "prepared = v2.prepare((2, 3, 4), vs.options())\n"
                "reg, alphas, train = v2.fit_service(prepared, pd.Timestamp(vs.package_meta()['corte_bloque']))\n"
                "print(json.dumps({'booster': base64.b64encode(bytes(reg.get_booster().save_raw(raw_format='json'))).decode(),"
                " 'alfa': {str(h): a for h, a in alphas.items()}, 'huella': prepared.fingerprint_matches}))")
        import subprocess
        import sys

        process = subprocess.run([sys.executable, "-c", code], cwd=vs.ROOT, env=eq.subprocess_env(**eq.CPU_SETUP),
                                 capture_output=True, text=True, timeout=3600)
        self.assertEqual(process.returncode, 0, process.stderr[-4000:])
        result = json.loads(process.stdout.strip().splitlines()[-1])
        import base64

        self.assertTrue(result["huella"])
        self.assertEqual(base64.b64decode(result["booster"]), (vs.PACKAGE / "booster.json").read_bytes())
        self.assertEqual(result["alfa"], vs.package_meta()["alfa"])


if __name__ == "__main__":
    unittest.main()
