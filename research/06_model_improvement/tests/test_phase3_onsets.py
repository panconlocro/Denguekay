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


if __name__ == "__main__":
    unittest.main()
