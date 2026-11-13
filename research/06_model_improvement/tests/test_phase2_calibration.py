"""Tests of the phase 2 calibration variants (synthetic predictions; guards G5 to G7 and the decision)."""

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

import phase2_calibration as p2  # noqa: E402
import preregistration as pr  # noqa: E402
from denguekay.evaluation import protocol as pa  # noqa: E402

SEASONS = (2008, 2009, 2010, 2011)


def _pred(seed: int = 0, districts: int = 12) -> pd.DataFrame:
    """Three horizons, one block per calendar year, origin = target week - (h + 1) weeks."""
    rng = np.random.default_rng(seed)
    weeks = pd.date_range("2008-01-06", "2011-12-25", freq="7D")
    rows = []
    for d in range(districts):
        risk = rng.normal(0, 1, len(weeks))
        y = (risk + rng.normal(0, 1, len(weeks)) > 1.2).astype(int)
        for h in (2, 3, 4):
            p = 1 / (1 + np.exp(-(1.5 * risk - 2 + rng.normal(0, 0.3, len(weeks)))))
            p[rng.random(len(weeks)) < 0.05] = 1e-9  # a few probabilities below the 1e-6 clip
            for i, w in enumerate(weeks):
                rows.append({"ubigeo": f"20{d:04d}", "anio": w.year, "semana": i % 52 + 1, "semana_inicio": w,
                             "origen_cierre": w - pd.Timedelta(weeks=h + 1), "horizonte": h,
                             "bloque": f"temporada_{w.year}", "casos_Dengue": 3 * y[i], "brote": y[i],
                             "umbral_brote_casos": 1.0, "persistencia": 0.0, "probabilidad_brote": p[i],
                             "casos_predichos": 1.0})
    return pd.DataFrame(rows)


class TestReproducesProtocol(unittest.TestCase):
    def test_g5_platt_per_horizon_is_bit_identical(self):
        g5 = p2.reproduces_protocol(_pred())
        self.assertTrue(g5["pasa"], g5)

    def test_smaller_clip_changes_the_calibration(self):
        a, _ = p2.calibrate_variant(_pred(), "platt", 1e-6)
        b, _ = p2.calibrate_variant(_pred(), "platt", 1e-15)
        self.assertFalse(np.allclose(a.probabilidad_calibrada.dropna(), b.probabilidad_calibrada.dropna()))


class TestNoLeakage(unittest.TestCase):
    """G7: labels that close after a block's cut-off do not change that block's calibration."""

    def _check(self, method, pooled):
        base = _pred(seed=1)
        first = base[base.bloque.eq("temporada_2010")]
        cutoffs = {h: pa.block_cutoff(g) for h, g in first.groupby("horizonte")}
        # Per horizon each horizon has its own cut-off; pooled, the earliest of the three applies to all.
        for h in (2, 3, 4):
            cut = min(cutoffs.values()) if pooled else cutoffs[h]
            altered = base.copy()
            later = (altered.semana_inicio + pd.Timedelta(days=6)).gt(cut)  # labels not closed by the cut-off
            altered.loc[later, "brote"] = 1 - altered.loc[later, "brote"]
            a, _ = p2.calibrate_variant(base, method, 1e-6, pooled)
            b, _ = p2.calibrate_variant(altered, method, 1e-6, pooled)
            block = a.bloque.eq("temporada_2010") & a.horizonte.eq(h)
            np.testing.assert_array_equal(a.loc[block, "probabilidad_calibrada"].to_numpy(),
                                          b.loc[block, "probabilidad_calibrada"].to_numpy())
            # Not vacuous: the next block does see the altered labels.
            nxt = a.bloque.eq("temporada_2011") & a.horizonte.eq(h)
            self.assertFalse(np.array_equal(a.loc[nxt, "probabilidad_calibrada"].to_numpy(),
                                            b.loc[nxt, "probabilidad_calibrada"].to_numpy()))

    def test_per_horizon(self):
        for method in ("platt", "beta"):
            self._check(method, pooled=False)

    def test_pooled(self):
        self._check("platt", pooled=True)


class TestVariants(unittest.TestCase):
    def test_pooled_uses_the_three_horizons(self):
        _, own = p2.calibrate_variant(_pred(), "platt", 1e-6, pooled=False)
        _, pooled = p2.calibrate_variant(_pred(), "platt", 1e-6, pooled=True)
        key = ["horizonte", "bloque"]
        o = own.set_index(key).filas_calibracion
        q = pooled.set_index(key).filas_calibracion
        b = "temporada_2011"
        self.assertGreater(q[(2, b)], o[(2, b)])
        self.assertEqual(q[(2, b)], q[(4, b)])  # one calibrator for the three horizons

    def test_g6_monotone_calibrators(self):
        for method, pooled in (("platt", False), ("platt", True), ("beta", False)):
            data, _ = p2.calibrate_variant(_pred(), method, 1e-6, pooled)
            self.assertEqual(p2.monotone_violations(data), 0, (method, pooled))

    def test_beta_drops_a_negative_term(self):
        rng = np.random.default_rng(3)
        p = rng.uniform(0.01, 0.99, 4000)
        y = (rng.random(4000) < p ** 3).astype(int)  # convex in p: the -ln(1 - p) term alone is not enough
        f, params = p2.fit_beta(p, y)
        self.assertGreaterEqual(min(params["a"], params["b"]), 0)
        q = np.sort(p)
        self.assertTrue((np.diff(f(q)) >= -1e-12).all())

    def test_isotonic_falls_back_to_platt_with_few_positives(self):
        rng = np.random.default_rng(4)
        p = rng.uniform(0, 1, 2000)
        y = (rng.random(2000) < p * 0.2).astype(int)
        self.assertLess(y.sum(), p2.ISOTONIC_MIN_POSITIVES)
        f, params = p2.fit_isotonic(p, y)
        g, _ = p2.fit_platt(p, y)
        self.assertEqual(params["respaldo"], "platt")
        np.testing.assert_array_equal(f(p), g(p))

    def test_log_loss(self):
        data = pd.DataFrame({"horizonte": 2, "bloque": "b", "brote": [1, 0], "probabilidad_brote": [0.0, 0.0],
                             "probabilidad_calibrada": [0.5, 0.5]})
        ll = p2.log_loss_by_block(data).iloc[0]
        self.assertAlmostEqual(ll.log_loss, np.log(2))
        self.assertAlmostEqual(ll.log_loss_sin_calibrar, -np.log(1e-15) / 2)


BLOCKS = [pr.block_name(s) for s in pr.DECIDING_SEASONS]


def _metrics(f1, auprc=(0.5,) * 5):
    return pd.DataFrame([{"horizonte": 2, "bloque": b, "f1_050": f, "auprc": a, "brier": 0.1, "razon_mae": 1.0}
                         for b, f, a in zip(BLOCKS, f1, auprc)])


def _ranges():
    return pd.DataFrame([{"horizonte": 2, "bloque": b, "f1_050": 0.01, "auprc": 0.01, "brier": 0.01,
                          "razon_mae": 0.01} for b in BLOCKS])


def _lead():
    return pd.DataFrame([{"horizonte": 2, "ic95_inferior": -0.1, "ic95_superior": 0.1,
                          **{f"diferencia_{b}": 0.0 for b in BLOCKS}, **{f"episodios_{b}": 20 for b in BLOCKS}}])


class TestDecidePhase2(unittest.TestCase):
    ref = _metrics([0.5] * 5)

    def test_auprc_against_in_two_seasons_vetoes(self):
        cand = _metrics([0.55] * 5, auprc=(0.4, 0.4, 0.5, 0.5, 0.5))
        self.assertEqual(pr.decide_multi_season(cand, self.ref, _ranges(), _lead()).iloc[0].veredicto, "gana")
        v = pr.decide_phase2(cand, self.ref, _ranges(), _lead()).iloc[0]
        self.assertEqual(v.veredicto, "compensa (empate)")
        self.assertIn("auprc", v.vetos)

    def test_symmetric(self):
        cand = _metrics([0.55] * 5, auprc=(0.4, 0.4, 0.5, 0.5, 0.5))
        self.assertEqual(pr.decide_phase2(self.ref, cand, _ranges(), _lead()).iloc[0].veredicto,
                         "compensa (empate)")

    def test_auprc_against_in_one_season_does_not_veto(self):
        cand = _metrics([0.55] * 5, auprc=(0.4, 0.5, 0.5, 0.5, 0.5))
        self.assertEqual(pr.decide_phase2(cand, self.ref, _ranges(), _lead()).iloc[0].veredicto, "gana")

    def test_adoption(self):
        v = lambda *xs: pd.DataFrame({"horizonte": [2, 3, 4], "veredicto": list(xs)})
        ok = pd.Series([0, 0, 0])
        self.assertTrue(pr.adopt_phase2(v("gana", "gana", "empate"), ok))
        self.assertFalse(pr.adopt_phase2(v("gana", "empate", "empate"), ok))
        self.assertFalse(pr.adopt_phase2(v("gana", "gana", "compensa (empate)"), ok))
        self.assertFalse(pr.adopt_phase2(v("gana", "gana", "gana"), pd.Series([0, 3, 0])))

    def test_constants_match_the_code(self):
        self.assertEqual(pr.PHASE2_EPS_REFERENCE, p2.EPS_REFERENCE)
        self.assertEqual(pr.PHASE2_EPS_SMALL, p2.EPS_SMALL)
        self.assertEqual(pr.PHASE2_ISOTONIC_MIN_POSITIVES, p2.ISOTONIC_MIN_POSITIVES)
        self.assertEqual(pa.EPS, 1e-6)


if __name__ == "__main__":
    unittest.main()
