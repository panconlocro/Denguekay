"""No behaviour change for v0 (phase 3): the pluggable serving writes exactly the baseline rows.

The baseline (tests/fixtures/pluggable_predictor/v0_predictions.json) was recorded with the code before
the refactor; it is never re-recorded. A difference means a behaviour change.
"""

import json
import unittest

import pluggable_support as ps


class TestV0Parity(unittest.TestCase):
    def test_versions_and_predictions_equal_the_baseline(self):
        baseline = json.loads(ps.BASELINE.read_text(encoding="utf-8"))
        measured = ps.v0_database_predictions_in_subprocess()
        self.assertEqual(measured["versiones"], baseline["versiones"])
        self.assertEqual(len(measured["predicciones"]), len(baseline["predicciones"]))
        for got, expected in zip(measured["predicciones"], baseline["predicciones"]):
            self.assertEqual(got, expected)


if __name__ == "__main__":
    unittest.main()
