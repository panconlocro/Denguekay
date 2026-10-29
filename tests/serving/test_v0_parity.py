"""No behaviour change for v0 (phase 3): the pluggable serving writes exactly the baseline rows.

The baseline (tests/fixtures/pluggable_predictor/v0_predictions.json) was recorded with the code before
the refactor (commit 2d1c1a6) and is never re-recorded; a difference means a behaviour change.

Limitation (the same as decision D1 of the ADR 0001): XGBoost does not train bit for bit the same on
every operating system, even on CPU with 2 threads. So:

- ``test_serving_with_frozen_boosters`` loads the four boosters trained by the code before the refactor
  (``v0_boosters/``) without refitting: package, ServingInputs, prediction and the ``prediccion`` and
  ``alerta`` rows. It runs on every system of the CI.
- ``test_full_parity_with_refit`` also refits the boosters, so it only runs in the environment that
  recorded the baseline (``v0_predictions_entorno.json``: operating system, machine and XGBoost version;
  CPU with 2 threads in a subprocess); elsewhere it is skipped with that reason.
"""

import json
import platform
import unittest

import xgboost

import pluggable_support as ps


def recording_environment():
    return json.loads(ps.ENVIRONMENT.read_text(encoding="utf-8"))


def same_environment():
    recorded = recording_environment()
    return (platform.system(), platform.machine(), xgboost.__version__) == (
        recorded["sistema"], recorded["maquina"], recorded["xgboost"])


def skip_reason():
    recorded = recording_environment()
    return (f"La paridad con reentrenamiento solo es bit a bit en el entorno de grabación "
            f"({recorded['sistema']} {recorded['maquina']}, xgboost {recorded['xgboost']}, {recorded['configuracion']}); "
            f"aquí: {platform.system()} {platform.machine()}, xgboost {xgboost.__version__}. "
            f"La paridad del serving con los boosters congelados sí corre")


class TestV0Parity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = json.loads(ps.BASELINE.read_text(encoding="utf-8"))

    def check(self, measured):
        self.assertEqual(measured["versiones"], self.baseline["versiones"])
        self.assertEqual(len(measured["predicciones"]), len(self.baseline["predicciones"]))
        for got, expected in zip(measured["predicciones"], self.baseline["predicciones"]):
            self.assertEqual(got, expected)

    def test_serving_with_frozen_boosters(self):
        self.check(ps.v0_database_predictions_in_subprocess(frozen=True))

    @unittest.skipUnless(same_environment(), skip_reason())
    def test_full_parity_with_refit(self):
        self.check(ps.v0_database_predictions_in_subprocess(frozen=False))

    def test_frozen_boosters_come_from_the_recording_commit(self):
        recorded = recording_environment()
        self.assertEqual((recorded["commit"], recorded["configuracion"]), (ps.RECORDING_COMMIT, "device=cpu,n_jobs=2"))
        self.assertEqual(set(ps.frozen_artifacts()), {(h, t) for h in (2, 4) for t in ("clasificacion", "regresion")})


if __name__ == "__main__":
    unittest.main()
