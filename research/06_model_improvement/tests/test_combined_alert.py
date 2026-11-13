"""Tests of the combined alert (preregistration COMBINED_ALERT and phase_combined_alert)."""

import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

import phase_combined_alert as ca  # noqa: E402
import preregistration as pr  # noqa: E402

BLOCKS = [pr.block_name(s) for s in pr.SEASON_2026_DECIDING]


def _frames(f1_delta, prec_delta, lead_delta, h=2):
    ref = pd.DataFrame({"horizonte": h, "bloque": BLOCKS, "f1_050": 0.6, "precision_050": 0.7})
    cand = ref.assign(f1_050=0.6 + pd.Series(f1_delta), precision_050=0.7 + pd.Series(prec_delta))
    ranges = ref.assign(f1_050=0.01, precision_050=0.01)
    lead = pd.DataFrame([{"horizonte": h, **{f"diferencia_{b}": d for b, d in zip(BLOCKS, lead_delta)},
                          **{f"episodios_{b}": 10 for b in BLOCKS}}])
    return cand, ref, ranges, lead


class TestRule(unittest.TestCase):
    def test_win(self):
        v = pr.decide_combined_alert(*_frames([0.05] * 5 + [0.0], [0.0] * 6, [0.2] * 6), {2: 89})
        self.assertEqual(v.veredicto[0], "gana")
        self.assertEqual(v.temporadas[0], 6)

    def test_precision_veto(self):
        v = pr.decide_combined_alert(*_frames([0.05] * 6, [-0.05] * 4 + [0.0] * 2, [0.0] * 6), {2: 89})
        self.assertEqual(v.veredicto[0], "compensa (empate)")
        self.assertEqual(v.vetos[0], "precision_050")

    def test_lead_time_alone_does_not_win(self):
        v = pr.decide_combined_alert(*_frames([0.0] * 6, [0.0] * 6, [0.5] * 6), {2: 89})
        self.assertEqual(v.veredicto[0], "empate")

    def test_lose(self):
        v = pr.decide_combined_alert(*_frames([-0.05] * 6, [0.0] * 6, [0.0] * 6), {2: 89})
        self.assertEqual(v.veredicto[0], "pierde")

    def test_adoption(self):
        v = lambda *x: pd.DataFrame({"horizonte": [2, 3, 4], "veredicto": list(x)})
        self.assertTrue(pr.adopt_combined_alert(v("gana", "gana", "empate")))
        self.assertFalse(pr.adopt_combined_alert(v("gana", "empate", "empate")))
        self.assertFalse(pr.adopt_combined_alert(v("gana", "gana", "compensa (empate)")))


class TestCombine(unittest.TestCase):
    def test_superset(self):
        d = pd.DataFrame({"alerta_050": [True, False, False, True], "alerta_persistencia": [False, True, False, True]})
        c = ca.combine(d)
        self.assertEqual(c.alerta_050.tolist(), [True, True, False, True])
        self.assertEqual(c.alerta_050_sola.tolist(), d.alerta_050.tolist())

    def test_false_alarms_by_regime(self):
        sola = pd.DataFrame({"horizonte": 2, "bloque": ["temporada_2010", "temporada_2017", "posterior_2026"],
                             "fp_050": [1, 2, 3], "vp_050": [5, 5, 5]})
        comb = sola.assign(fp_050=[4, 3, 3], vp_050=[5, 7, 6])
        r = ca.false_alarms_by_regime(ca.added_false_alarms(sola, comb)).set_index("regimen")
        self.assertEqual(r.at["normales", "fp_anadidas"], 3)
        self.assertEqual(r.at["nino", "fp_anadidas"], 1)
        self.assertEqual(r.at["nino", "vp_anadidos"], 3)


if __name__ == "__main__":
    unittest.main()
