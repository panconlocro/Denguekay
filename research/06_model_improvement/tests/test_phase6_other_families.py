"""Tests of phase 6 (other families): NB2 GLM, LightGBM and their block loop (synthetic data)."""

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

import phase3_onsets as p3  # noqa: E402
import phase6_other_families as p6  # noqa: E402
from test_phase3_onsets import BLOCKS, _inputs  # noqa: E402

from denguekay.model import frozen_configs as cf  # noqa: E402

COLUMNS = cf.CONFIG_2026_V1["columnas"]


class TestGLM(unittest.TestCase):
    def test_recovers_coefficients_with_offset(self):
        rng = np.random.default_rng(0)
        n = 4000
        train = pd.DataFrame({"a": rng.normal(size=n), "b": rng.normal(size=n)})
        offset = rng.normal(0, 0.3, n)
        mu = np.exp(0.5 + 0.8 * train.a - 0.4 * train.b + offset)
        y = rng.negative_binomial(2.0, 2.0 / (2.0 + mu))
        for h in p6.H:
            train[f"casos_Dengue_h{h}"] = y
        margin = np.repeat(offset[:, None], len(p6.H), axis=1)
        fitted = p6.fit_glm(train, ["a", "b"], margin, 0)
        self.assertTrue(all(fitted["convergio"]))
        # Coefficients on the standardised scale: slope = beta * std
        b = fitted["beta"][0]
        self.assertAlmostEqual(b[1] / fitted["scale"]["a"], 0.8, delta=0.1)
        self.assertAlmostEqual(b[2] / fitted["scale"]["b"], -0.4, delta=0.1)
        pred = p6.predict_glm(fitted, train, margin)
        self.assertEqual(pred.shape, (n, len(p6.H)))

    def test_poisson_glm_recovers_coefficients_and_reports_convergence(self):
        rng = np.random.default_rng(1)
        n = 4000
        train = pd.DataFrame({"a": rng.normal(size=n), "b": rng.normal(size=n)})
        offset = rng.normal(0, 0.3, n)
        y = rng.poisson(np.exp(0.3 + 0.6 * train.a - 0.2 * train.b + offset))
        for h in p6.H:
            train[f"casos_Dengue_h{h}"] = y
        margin = np.repeat(offset[:, None], len(p6.H), axis=1)
        fitted = p6.fit_glm_poisson(train, ["a", "b"], margin, 0)
        self.assertTrue(all(fitted["convergio"]))
        self.assertFalse(any(fitted["penalizado"]))
        b = fitted["beta"][0]
        self.assertAlmostEqual(b[1] / fitted["scale"]["a"], 0.6, delta=0.05)
        self.assertAlmostEqual(b[2] / fitted["scale"]["b"], -0.2, delta=0.05)
        # without convergence (1 iteration) the horizon is refitted with the L2 penalty and reported
        import preregistration as pr

        old, pr.PHASE6_GLM_MAXITER = pr.PHASE6_GLM_MAXITER, 1
        try:
            forced = p6.fit_glm_poisson(train, ["a", "b"], margin, 0)
        finally:
            pr.PHASE6_GLM_MAXITER = old
        self.assertTrue(all(forced["penalizado"]))
        self.assertFalse(any(forced["convergio"]))
        self.assertTrue(np.isfinite(p6.predict_glm(forced, train, margin)).all())


class TestBlockLoop(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, cls.matrices, cls.origins, _ = _inputs()

    def _run(self, family, origins, seed=17):
        return p6.predict_blocks_family(self.matrices, origins, BLOCKS, seed, COLUMNS, family)

    def test_same_training_as_l(self):
        """G14 on synthetic data: rows and cut-off per block are those of the L loop."""
        ref = p3.predict_blocks_weighted(self.matrices, self.origins, BLOCKS, 17, COLUMNS,
                                         cf.CONFIG_2026_V1["hiperparametros"]).attrs["ajustes"]
        for family in (*p6.FAMILIES, "6a_prima_poisson_glm"):
            ours = self._run(family, self.origins).attrs["ajustes"]
            np.testing.assert_array_equal(ours.filas_entrenamiento.to_numpy(), ref.filas_entrenamiento.to_numpy())
            np.testing.assert_array_equal(ours.corte.to_numpy(), ref.corte.to_numpy())

    def test_no_leakage_by_perturbation(self):
        """G15: targets of origins outside a block's training do not change its predictions."""
        from denguekay.model import horizon_strategies as eh

        block = BLOCKS[0]
        _, cutoff = eh._common_cutoffs(self.matrices, block[1], block[2])
        train = p3._training(self.origins, cutoff)
        altered = self.origins.copy()
        outside = ~altered.index.isin(train.index)
        for h in p6.H:
            altered.loc[outside, f"casos_Dengue_h{h}"] = altered.loc[outside, f"casos_Dengue_h{h}"] * 5 + 9
        for family in (*p6.FAMILIES, "6a_prima_poisson_glm"):
            a = p6.predict_blocks_family(self.matrices, self.origins, [block], 17, COLUMNS, family)
            b = p6.predict_blocks_family(self.matrices, altered, [block], 17, COLUMNS, family)
            for col in ("casos_predichos", "probabilidad_brote"):
                np.testing.assert_array_equal(a[col].to_numpy(), b[col].to_numpy(), err_msg=family)
            # the later block does see the change: the test is not vacuous
            c = p6.predict_blocks_family(self.matrices, self.origins, BLOCKS[1:], 17, COLUMNS, family)
            d = p6.predict_blocks_family(self.matrices, altered, BLOCKS[1:], 17, COLUMNS, family)
            self.assertFalse(np.array_equal(c.casos_predichos.to_numpy(), d.casos_predichos.to_numpy()), family)

    def test_lightgbm_is_deterministic(self):
        """G16 (first part): same seed, same predictions; another seed changes them."""
        a = self._run("6b_lightgbm", self.origins, 17)
        b = self._run("6b_lightgbm", self.origins, 17)
        c = self._run("6b_lightgbm", self.origins, 29)
        np.testing.assert_array_equal(a.casos_predichos.to_numpy(), b.casos_predichos.to_numpy())
        self.assertFalse(np.array_equal(a.casos_predichos.to_numpy(), c.casos_predichos.to_numpy()))

    def test_g14_detects_a_different_block(self):
        fits = pd.DataFrame({"bloque": ["temporada_2008"], "filas_entrenamiento": [10], "corte": ["2007-08-04"]})
        ref = fits.assign(semilla=17)
        self.assertTrue(p6.guard_g14(fits, ref)["pasa"])
        self.assertFalse(p6.guard_g14(fits.assign(filas_entrenamiento=11), ref)["pasa"])


if __name__ == "__main__":
    unittest.main()
