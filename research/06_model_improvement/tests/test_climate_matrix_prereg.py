"""Tests of the climate matrix preregistration (columns, simplicity order, number of comparisons, base selection)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

import preregistration as pr  # noqa: E402

NINO = "nino12_anom_media3"


class TestMatrix(unittest.TestCase):
    def test_variants_and_columns(self):
        v = pr.MATRIX_VARIANTS
        self.assertEqual(len(v), 12)
        self.assertEqual(set(v), set(pr.MATRIX_SIMPLICITY))
        self.assertEqual(v["b4"], [c for c in v["b3"] if c != NINO])
        self.assertEqual(v["d2"], [*v["d1"], NINO])
        self.assertEqual(v["e2"], [*v["e1"], NINO])
        self.assertEqual(v["n1"], v["b3"])
        self.assertTrue(set(v["d3"]) | set(v["d4"]) | set(v["d5"]) == set(v["d1"]))
        self.assertEqual(len(v["e1"]), len(v["d1"]))
        self.assertEqual(pr.MATRIX_MONOTONE, {"n1": {NINO: 1}})

    def test_simplicity_order(self):
        """Fewer columns first; with equal columns, without Niño before with Niño."""
        v = pr.MATRIX_VARIANTS
        key = [(len(v[x]), NINO in v[x]) for x in pr.MATRIX_SIMPLICITY]
        self.assertEqual(key, sorted(key))
        self.assertLess(pr.MATRIX_SIMPLICITY.index("b3"), pr.MATRIX_SIMPLICITY.index("n1"))

    def test_number_of_comparisons(self):
        self.assertEqual(pr.matrix_comparisons(0), 15)
        self.assertEqual(pr.matrix_comparisons(3), 18)
        self.assertEqual(pr.matrix_comparisons(12), 81)

    def test_select_base(self):
        wins = {("d1", "b4"): True, ("e2", "d1"): False}
        beats = lambda a, b: wins.get((a, b), False)
        self.assertIsNone(pr.select_matrix_base([], beats))
        self.assertEqual(pr.select_matrix_base(["b4"], beats), "b4")
        self.assertEqual(pr.select_matrix_base(["e2", "d1", "b4"], beats), "d1")
        self.assertEqual(pr.select_matrix_base(["d1", "b4"], lambda a, b: False), "b4")   # a tie keeps the simpler

    def test_record(self):
        m = pr.CLIMATE_MATRIX
        self.assertIn("DESPUÉS de ver los resultados de la temporada 2026", m["estado"])
        self.assertTrue(any("por azar" in d for d in m["declaraciones"]))
        self.assertEqual(pr.MATRIX_FIXED_CROSSES, (("d1", "b3"), ("d2", "b3"), ("e1", "b3")))


if __name__ == "__main__":
    unittest.main()
