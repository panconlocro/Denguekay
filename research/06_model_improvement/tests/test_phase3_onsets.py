"""Tests of phase 3 (onsets): weights, state at the origin and the weighted block loop (synthetic data)."""

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

import phase0_diagnosis as d  # noqa: E402
import phase1_history as p1  # noqa: E402
import phase3_onsets as p3  # noqa: E402
import preregistration as pr  # noqa: E402
from test_phase1_history import _cases  # noqa: E402

BLOCKS = [("temporada_2006", "temporada", 2006), ("temporada_2007", "temporada", 2007)]


def _inputs(seed: int = 0):
    cases = _cases(seed=seed)
    labels = d.long_labels(cases)
    matrices = p1.long_matrices(cases, labels)
    origins = p1.long_origins(cases, matrices[2])
    series = labels[["ubigeo", "anio", "semana", "semana_inicio", "casos_Dengue", "brote"]].copy()
    series["semana_inicio"] = pd.to_datetime(series.semana_inicio)
    return cases, matrices, origins, series


class TestWeights(unittest.TestCase):
    def test_onset_weeks_are_clean_starts(self):
        series = pd.DataFrame({"ubigeo": "200101", "semana_inicio": pd.date_range("2006-01-01", periods=30, freq="7D"),
                               "brote": [0] * 10 + [1, 1, 1] + [0] * 10 + [1, 1] + [0] * 5})
        weeks = p3.onset_weeks(series)
        starts = series.semana_inicio
        self.assertEqual(weeks, {("200101", starts[10]), ("200101", starts[11]), ("200101", starts[23]),
                                 ("200101", starts[24])})
        # The second episode needs >= 8 weeks without outbreak: with a 5-week gap it is not clean.
        short = series.copy()
        short.loc[18:22, "brote"] = 0
        short.loc[16, "brote"] = 1
        self.assertNotIn(("200101", starts[23]), p3.onset_weeks(short))

    def test_onset_weights(self):
        train = pd.DataFrame({"ubigeo": ["a", "b"], **{f"semana_inicio_h{h}": pd.to_datetime(["2006-01-01"] * 2)
                                                       for h in p3.H}})
        w = p3.onset_weights(train, {("a", pd.Timestamp("2006-01-01"))})
        np.testing.assert_array_equal(w, [p3.ONSET_WEIGHT, 1.0])

    def test_season_weights_downweight_heavy_seasons(self):
        weeks = pd.to_datetime(["2006-01-01", "2007-01-07", "2008-01-06"])  # three seasons
        train = pd.DataFrame({"semana_inicio_h2": weeks, "casos_Dengue_h2": [10.0, 40.0, 0.0]})
        np.testing.assert_allclose(p3.season_weights(train), [1.0, 0.25, 1.0])

    def test_weights_ignore_labels_after_the_cutoff(self):
        """G9: perturbing data after the cut-off does not change the training weights."""
        _, _, origins, series = _inputs(seed=5)
        cutoff = pd.Timestamp("2006-08-26")
        altered = series.copy()
        later = altered.semana_inicio.gt(cutoff)
        altered.loc[later, "brote"] = 1 - altered.loc[later, "brote"]
        train = p3._training(origins, cutoff)
        for weights in (lambda s: p3.onset_weights(train, p3.onset_weeks(s)),):
            np.testing.assert_array_equal(weights(series), weights(altered))
        self.assertTrue(len(train) > 100)


class TestState(unittest.TestCase):
    def test_state_ignores_labels_after_the_origin(self):
        """G9: the regime of an origin only depends on the label of its origin week."""
        _, _, origins, series = _inputs(seed=6)
        base = p3.origin_state(origins, series)
        o = origins.sort_values("origen_cierre").iloc[len(origins) // 2]
        week = pd.Timestamp(o.origen_cierre) - pd.Timedelta(days=6)
        altered = series.copy()
        later = altered.semana_inicio.gt(week)
        altered.loc[later, "brote"] = 1 - altered.loc[later, "brote"]
        other = p3.origin_state(origins, altered)
        before = pd.to_datetime(origins.origen_cierre).le(o.origen_cierre).to_numpy()
        np.testing.assert_array_equal(base[before], other[before])
        self.assertFalse(np.array_equal(base[~before], other[~before]))


class TestBlockLoop(unittest.TestCase):
    """G8 on synthetic data: without weights nor regimes it is ``phase1_history.predict_blocks``."""

    def test_reproduces_predict_blocks(self):
        from denguekay.model import frozen_configs as cf

        _, matrices, origins, series = _inputs()
        c = cf.CONFIG_2026_V1
        a = p1.predict_blocks(matrices, origins, BLOCKS, 17, c["columnas"], c["hiperparametros"])
        b = p3.predict_blocks_weighted(matrices, origins, BLOCKS, 17, c["columnas"], c["hiperparametros"])
        for col in ("casos_predichos", "probabilidad_brote"):
            np.testing.assert_array_equal(a[col].to_numpy(), b[col].to_numpy())

    def test_regimes_cover_every_row_once(self):
        from denguekay.model import frozen_configs as cf

        _, matrices, origins, series = _inputs()
        c = cf.CONFIG_2026_V1
        state = p3.origin_state(origins, series)
        out = p3.predict_blocks_weighted(matrices, origins, BLOCKS, 17, c["columnas"], c["hiperparametros"],
                                         state=state)
        fits = out.attrs["ajustes"]
        self.assertEqual(sorted(fits.regimen.unique()), [0, 1])
        self.assertTrue(np.isfinite(out.probabilidad_brote).all())
        self.assertEqual(len(out), len(p1.predict_blocks(matrices, origins, BLOCKS, 17, c["columnas"],
                                                         c["hiperparametros"])))


class TestPhase3Record(unittest.TestCase):
    def test_adoption(self):
        v = lambda *xs: pd.DataFrame({"horizonte": [2, 3, 4], "veredicto": list(xs)})
        self.assertTrue(pr.adopt_phase3(v("gana", "gana", "empate")))
        self.assertFalse(pr.adopt_phase3(v("gana", "empate", "empate")))
        self.assertFalse(pr.adopt_phase3(v("gana", "gana", "pierde")))

    def test_constants_match_the_code(self):
        self.assertEqual(pr.PHASE3_ONSET_WEIGHT, p3.ONSET_WEIGHT)
        self.assertEqual(pr.PHASE3_SEASON_WEIGHT_CLIP, p3.SEASON_WEIGHT_CLIP)
        self.assertEqual(pr.PHASE3_MIN_REGIME_ROWS, p3.MIN_REGIME_ROWS)


HAS_DATA = d.SILVER_EPI_HISTORICAL.exists()


@unittest.skipUnless(HAS_DATA, "Sin datos")
class TestG10(unittest.TestCase):
    """G10: B1 and B2 on the long series."""

    @classmethod
    def setUpClass(cls):
        cls.panel = d.load_integrated()
        cases, _ = d.long_case_series(cls.panel)
        cls.cases = cases
        cls.labels = d.long_labels(cases)
        cls.columns = sum(p3._b1_b2_columns(), [])

    def test_same_formulas_as_weekly_status_on_2017_2025(self):
        from denguekay.evaluation import onsets as di

        cutoff = pd.Timestamp("2021-08-28")
        lab = self.labels.assign(semana_inicio=pd.to_datetime(self.labels.semana_inicio))
        s17 = lab[lab.semana_inicio.ge(pd.Timestamp(self.panel.semana_inicio.min()))].reset_index(drop=True)
        ours = p3.long_spatial_table(self.panel, s17, s17, cutoff).sort_values(["ubigeo", "semana_inicio"])
        ref = di.weekly_status(self.panel, s17, cutoff).sort_values(["ubigeo", "semana_inicio"])
        pd.testing.assert_frame_equal(ours[self.columns].reset_index(drop=True),
                                      ref[self.columns].reset_index(drop=True), check_dtype=False)

    def test_no_leakage_by_perturbation(self):
        cutoff, since = pd.Timestamp("2012-08-25"), pd.Timestamp("2013-03-03")
        base = p3.long_spatial_table(self.panel, self.cases, self.labels, cutoff)
        cases, labels = self.cases.copy(), self.labels.copy()
        later = pd.to_datetime(cases.semana_inicio).ge(since)
        cases.loc[later, "casos_Dengue"] = cases.loc[later, "casos_Dengue"] * 3 + 7
        later_l = pd.to_datetime(labels.semana_inicio).ge(since)
        labels.loc[later_l, "brote"] = 1 - labels.loc[later_l, "brote"]
        other = p3.long_spatial_table(self.panel, cases, labels, cutoff)
        sel = base.semana_inicio.lt(since)
        pd.testing.assert_frame_equal(base[sel].reset_index(drop=True), other[sel].reset_index(drop=True))
        self.assertFalse(base.loc[~sel, "vecinos_frac_en_brote"].equals(other.loc[~sel, "vecinos_frac_en_brote"]))

    def test_core_ranking_uses_only_closed_weeks(self):
        cutoff = pd.Timestamp("2012-08-25")
        base = p3.long_spatial_table(self.panel, self.cases, self.labels, cutoff)
        cases = self.cases.copy()
        later = pd.to_datetime(cases.semana_inicio).gt(cutoff)
        cases.loc[later, "casos_Dengue"] = cases.loc[later, "casos_Dengue"][::-1].to_numpy()
        other = p3.long_spatial_table(self.panel, cases, self.labels, cutoff)
        sel = base.semana_inicio.le(cutoff - pd.Timedelta(days=6))
        pd.testing.assert_frame_equal(base.loc[sel, ["nucleo_log_casos", "nucleo_frac_en_brote"]].reset_index(drop=True),
                                      other.loc[sel, ["nucleo_log_casos", "nucleo_frac_en_brote"]].reset_index(drop=True))

    def test_origins_since_2005_have_no_nulls(self):
        table = p3.long_spatial_table(self.panel, self.cases, self.labels, pd.Timestamp("2009-08-29"))
        t = table[table.semana_inicio.ge(pd.Timestamp("2005-01-02"))]
        self.assertFalse(t[self.columns].isna().any().any())


if __name__ == "__main__":
    unittest.main()
