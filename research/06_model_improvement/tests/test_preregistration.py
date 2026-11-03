"""Tests of the multi-season decision rule preregistered for the model improvement study."""

import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

import preregistration as pr  # noqa: E402

BLOCKS = [pr.block_name(s) for s in pr.DECIDING_SEASONS]


def _metrics(f1: list[float], **guards) -> pd.DataFrame:
    base = {"auprc": 0.5, "brier": 0.1, "razon_mae": 1.0}
    rows = [{"horizonte": 2, "bloque": b, "f1_050": f, **{m: guards.get(m, [v] * 5)[i] for m, v in base.items()}}
            for i, (b, f) in enumerate(zip(BLOCKS, f1))]
    return pd.DataFrame(rows)


def _ranges(value: float = 0.01) -> pd.DataFrame:
    return pd.DataFrame([{"horizonte": 2, "bloque": b, "f1_050": value, "auprc": value, "brier": value,
                          "razon_mae": value} for b in BLOCKS])


def _lead(diffs=(0, 0, 0, 0, 0), low=-0.1, high=0.1, n=20, blocks=BLOCKS) -> pd.DataFrame:
    """Lead-time differences with ``n`` clean onsets per season (neutral band ±1/n = ±0.05 by default)."""
    return pd.DataFrame([{"horizonte": 2, "ic95_inferior": low, "ic95_superior": high,
                          **{f"diferencia_{b}": d for b, d in zip(blocks, diffs)},
                          **{f"episodios_{b}": n for b in blocks}}])


def _verdict(cand, ref, lead=None, ranges=None):
    return pr.decide_multi_season(cand, ref, ranges if ranges is not None else _ranges(),
                                  lead if lead is not None else _lead()).iloc[0]


class TestDecideMultiSeason(unittest.TestCase):
    ref = _metrics([0.5] * 5)

    def test_four_in_favour_and_one_neutral_wins(self):
        cand = _metrics([0.55, 0.55, 0.55, 0.55, 0.505])  # the last delta is inside the tie threshold
        self.assertEqual(_verdict(cand, self.ref).veredicto, "gana")

    def test_one_season_against_blocks_the_win(self):
        cand = _metrics([0.55, 0.55, 0.55, 0.55, 0.45])
        self.assertEqual(_verdict(cand, self.ref).veredicto, "empate")

    def test_three_in_favour_is_a_tie(self):
        cand = _metrics([0.55, 0.55, 0.55, 0.5, 0.5])
        self.assertEqual(_verdict(cand, self.ref).veredicto, "empate")

    def test_rule_is_symmetric(self):
        cand = _metrics([0.55, 0.55, 0.55, 0.55, 0.5])
        self.assertEqual(_verdict(cand, self.ref).veredicto, "gana")
        self.assertEqual(_verdict(self.ref, cand).veredicto, "pierde")

    def test_guard_against_in_three_seasons_vetoes(self):
        cand = _metrics([0.55] * 5, brier=[0.2, 0.2, 0.2, 0.1, 0.1])  # Brier higher = worse
        v = _verdict(cand, self.ref)
        self.assertEqual(v.veredicto, "compensa (empate)")
        self.assertEqual(v.vetos, "brier")

    def test_guard_against_in_two_seasons_does_not_veto(self):
        cand = _metrics([0.55] * 5, brier=[0.2, 0.2, 0.1, 0.1, 0.1])
        self.assertEqual(_verdict(cand, self.ref).veredicto, "gana")

    def test_lead_time_needs_ci_and_four_seasons(self):
        same = _metrics([0.5] * 5)
        self.assertEqual(_verdict(same, self.ref, _lead((0.1, 0.1, 0.1, 0.1, 0), low=0.01)).veredicto, "gana")
        self.assertEqual(_verdict(same, self.ref, _lead((0.1, 0.1, 0.1, 0.1, -0.1), low=0.01)).veredicto,
                         "empate")
        self.assertEqual(_verdict(same, self.ref, _lead((0.1, 0.1, 0.1, 0.1, 0), low=-0.01)).veredicto, "empate")


    def test_lead_time_band_of_one_onset(self):
        same = _metrics([0.5] * 5)
        # -1/20 = -0.05 is inside the band: neutral, so the win stands.
        self.assertEqual(_verdict(same, self.ref, _lead((0.1, 0.1, 0.1, 0.1, -0.05), low=0.01)).veredicto, "gana")
        # +0.05 is not beyond the band: only 3 seasons in favour.
        self.assertEqual(_verdict(same, self.ref, _lead((0.1, 0.1, 0.1, 0.05, 0), low=0.01)).veredicto, "empate")

    def test_f1_up_and_lead_time_down_offsets(self):
        cand = _metrics([0.55] * 5)
        lead = _lead((-0.1,) * 5, low=-0.2, high=-0.01)
        self.assertEqual(_verdict(cand, self.ref, lead).veredicto, "compensa (empate)")


def _two(f1, **guards):
    """Metrics of 2022 and 2023 only (comparison 1a)."""
    m = _metrics(f1 + [0.5] * 3, **guards).iloc[:2]
    return m.assign(bloque=["temporada_2022", "temporada_2023"])


class TestPhase1a(unittest.TestCase):
    def _ranges(self):
        return _ranges().iloc[:2].assign(bloque=["temporada_2022", "temporada_2023"])

    def _decide(self, cand, ref, lead):
        return pr.decide_phase1a(cand, ref, self._ranges(), lead).iloc[0]

    def test_needs_both_seasons(self):
        lead = _lead((0, 0), blocks=["temporada_2022", "temporada_2023"])
        ref = _two([0.5, 0.5])
        self.assertEqual(self._decide(_two([0.55, 0.55]), ref, lead).veredicto, "gana")
        self.assertEqual(self._decide(_two([0.55, 0.5]), ref, lead).veredicto, "empate")
        self.assertEqual(self._decide(ref, _two([0.55, 0.55]), lead).veredicto, "pierde")

    def test_matches_protocol_decide_without_lead_time_change(self):
        from denguekay.evaluation import protocol as pa

        ref = _two([0.5, 0.5])
        lead = _lead((0, 0), blocks=["temporada_2022", "temporada_2023"])
        for f1, brier in (([0.55, 0.55], [0.1] * 5), ([0.55, 0.55], [0.2, 0.2, 0.1, 0.1, 0.1]),
                          ([0.45, 0.45], [0.1] * 5), ([0.55, 0.45], [0.1] * 5)):
            cand = _two(f1, brier=brier)
            ours = self._decide(cand, ref, lead).veredicto
            theirs = pa.decide(cand, ref, self._ranges(), lead).iloc[0].veredicto
            self.assertEqual(ours, theirs, (f1, brier))

    def test_adoption_set(self):
        self.assertEqual(pr.PHASE1A_ADOPT, ("gana", "empate"))


class TestPhase1Record(unittest.TestCase):
    def test_deciding_seasons_and_contrast(self):
        self.assertEqual(pr.DECIDING_SEASONS, (2010, 2015, 2016, 2022, 2023))
        self.assertNotIn(pr.CONTRAST_SEASON, pr.DECIDING_SEASONS)
        self.assertIn(pr.SEPARATE_SEASON, pr.DECIDING_SEASONS)
        self.assertEqual(pr.PHASE1["comparacion_1a"]["temporadas_que_deciden"], [2022, 2023])


if __name__ == "__main__":
    unittest.main()
