"""Tests of the hyperparameter tuning preregistration (HP_TUNING) and phase_hp_tuning."""

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

import phase_hp_tuning as ht  # noqa: E402
import preregistration as pr  # noqa: E402
from denguekay.evaluation import tuning as t05  # noqa: E402


class TestSeparation(unittest.TestCase):
    def test_tuning_seasons_are_disjoint(self):
        decided = set(pr.SEASON_2026_DECIDING) | set(pr.COMBINED_ALERT_REPORTED)   # deciding + LOSO filter seasons
        self.assertFalse(set(pr.HP_TUNING_TRAIN_SEASONS) & decided)
        self.assertTrue(set(pr.HP_TUNING_OBJECTIVE_SEASONS) <= set(pr.HP_TUNING_TRAIN_SEASONS))

    def test_tuning_blocks(self):
        names = [b[0] for b in ht.tuning_blocks()]
        self.assertEqual(names, [pr.block_name(s) for s in pr.HP_TUNING_TRAIN_SEASONS])


class TestSpace(unittest.TestCase):
    def test_space_contains_study_05_and_inherited(self):
        self.assertEqual(set(pr.HP_TUNING_SPACE), set(t05.SPACE))
        for k, (_, lo, hi, _) in pr.HP_TUNING_SPACE.items():
            lo5, hi5 = t05.SPACE[k][1], t05.SPACE[k][2]
            self.assertLessEqual(lo, lo5)
            self.assertGreaterEqual(hi, hi5)
        h = {**ht.inherited(), "reg_alpha": 1e-3}
        for k, (_, lo, hi, _) in pr.HP_TUNING_SPACE.items():
            self.assertTrue(lo <= h[k] <= hi, k)


class TestObjective(unittest.TestCase):
    def _cells(self, scale=1.0):
        rows = [{"horizonte": h, "bloque": pr.block_name(s), "brier": 0.05 * (1 + i) * scale}
                for i, s in enumerate(pr.HP_TUNING_OBJECTIVE_SEASONS) for h in (2, 3, 4)]
        return pd.DataFrame(rows)

    def test_relative(self):
        ref = self._cells()
        self.assertAlmostEqual(ht.relative_objective(ref, ref), 1.0)
        self.assertAlmostEqual(ht.relative_objective(self._cells(0.9), ref), 0.9)

    def test_missing_cell_is_nan(self):
        ref = self._cells()
        self.assertTrue(np.isnan(ht.relative_objective(ref.iloc[1:], ref)))


class TestRule(unittest.TestCase):
    def test_choose(self):
        self.assertEqual(pr.hp_tuning_choose({12: 0.97, 40: 0.95, 7: 0.95}), 7)

    def test_adoption(self):
        v = lambda *x: pd.DataFrame({"horizonte": [2, 3, 4], "veredicto": list(x)})
        win, tie = v("gana", "gana", "empate"), v("empate", "empate", "empate")
        self.assertTrue(pr.adopt_hp_tuning(win, tie, tie, 16, 0.97))
        self.assertFalse(pr.adopt_hp_tuning(win, tie, tie, 15, 0.97))
        self.assertFalse(pr.adopt_hp_tuning(win, tie, tie, 20, 1.01))
        self.assertFalse(pr.adopt_hp_tuning(tie, tie, tie, 24, 0.9))   # a tie keeps the inherited

    def test_record(self):
        self.assertIn("aprobado por Rosa", pr.HP_TUNING["estado"])
        self.assertEqual(pr.HP_TUNING_N_TRIALS, 300)
        self.assertEqual(pr.HP_TUNING_TIMEOUT_S, 36000)
        self.assertEqual(pr.HP_TUNING["estudio"]["tope_de_pared_s"], 36000)
        self.assertTrue(any("Niño fuerte" in x for x in pr.HP_TUNING["agregado_de_rosa"]))
        self.assertNotIn(2017, pr.HP_TUNING_TRAIN_SEASONS)

    def test_study_columns(self):
        cols = ht.study_columns()
        self.assertEqual(cols[-4:], pr.MATRIX_VARIANTS["d3"])
        self.assertEqual(len(cols), len(set(cols)))


if __name__ == "__main__":
    unittest.main()
