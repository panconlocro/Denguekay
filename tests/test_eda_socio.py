"""Tests de src/eda/socio.py con datos sintéticos (no dependen de data/)."""

import unittest

import numpy as np
import pandas as pd

from src.eda.socio import componentes_principales, limites_embudo, spearman_bootstrap, vif


class VifTests(unittest.TestCase):
    def test_independientes_cerca_de_1_y_colineal_alto(self):
        rng = np.random.default_rng(0)
        a, b = rng.normal(size=300), rng.normal(size=300)
        X = pd.DataFrame({"a": a, "b": b, "c": a + b + rng.normal(0, 0.05, 300)})
        v = vif(X)
        self.assertGreater(v["c"], 50)
        v2 = vif(X[["a", "b"]])
        self.assertLess(v2.max(), 1.1)


class PcaTests(unittest.TestCase):
    def test_un_factor_domina(self):
        rng = np.random.default_rng(1)
        f = rng.normal(size=200)
        X = pd.DataFrame({f"x{i}": f + rng.normal(0, 0.1, 200) for i in range(5)})
        var, cargas, puntajes = componentes_principales(X, n=2)
        self.assertGreater(var["CP1"], 0.9)
        self.assertTrue((cargas["CP1"] > 0).all())
        self.assertGreater(np.corrcoef(puntajes["CP1"], f)[0, 1], 0.95)


class BootstrapTests(unittest.TestCase):
    def test_ic_contiene_rho_y_reproducible(self):
        rng = np.random.default_rng(2)
        x = pd.Series(rng.normal(size=60))
        y = x + pd.Series(rng.normal(0, 1, 60))
        r1, r2 = spearman_bootstrap(x, y, n=300, semilla=5), spearman_bootstrap(x, y, n=300, semilla=5)
        self.assertEqual(r1, r2)
        self.assertLess(r1["ic95_inf"], r1["rho"])
        self.assertGreater(r1["ic95_sup"], r1["rho"])


class EmbudoTests(unittest.TestCase):
    def test_limites_se_estrechan_con_la_poblacion(self):
        lo, hi = limites_embudo(np.array([1_000, 100_000]), tasa_global=0.01)
        self.assertGreater(hi[0] - lo[0], hi[1] - lo[1])
        self.assertTrue((lo <= 0.01).all() and (hi >= 0.01).all())


if __name__ == "__main__":
    unittest.main()
