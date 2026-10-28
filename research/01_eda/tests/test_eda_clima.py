"""Tests de src/eda/clima.py con datos sintéticos (no dependen de data/)."""

import unittest

import numpy as np
import pandas as pd

from src.eda.clima import (
    anomalia, bootstrap_bloques, centro_estacional, correlacion_parcial_spearman, correlacion_rezagada, rezagar,
)


def panel(n=120, ubigeos=("a", "b"), semilla=0):
    rng = np.random.default_rng(semilla)
    filas = []
    for u in ubigeos:
        x = rng.normal(size=n)
        y = np.r_[np.zeros(3), x[:-3]] + rng.normal(0, 0.1, n)   # y responde a x con rezago 3
        filas.append(pd.DataFrame({"ubigeo": u, "anio": 2017 + np.arange(n) // 52,
                                   "semana": np.arange(n) % 52 + 1, "x": x, "y": y}))
    return pd.concat(filas, ignore_index=True)


class AnomaliaTests(unittest.TestCase):
    def test_media_por_grupo_es_cero(self):
        df = panel()
        a = anomalia(df, "x")
        medias = a.groupby([df["ubigeo"], df["semana"]]).mean()
        self.assertLess(medias.abs().max(), 1e-12)

    def test_semana_53_se_agrupa_con_52(self):
        df = pd.DataFrame({"ubigeo": "a", "semana": [52, 53, 52], "x": [1.0, 3.0, 2.0]})
        self.assertEqual(anomalia(df, "x").tolist(), [-1.0, 1.0, 0.0])


class RezagoTests(unittest.TestCase):
    def test_rezagar_no_cruza_grupos(self):
        df = panel(n=5)
        r = rezagar(df, "x", 1)
        self.assertTrue(np.isnan(r.iloc[5]))

    def test_correlacion_maxima_en_el_rezago_verdadero(self):
        df = panel()
        c = correlacion_rezagada(df, "x", "y", range(0, 6), metodo="pearson")
        self.assertTrue((c.idxmax(axis=1) == 3).all())
        c_reg = correlacion_rezagada(df[df["ubigeo"] == "a"], "x", "y", range(0, 6), grupo=None)
        self.assertEqual(int(c_reg.iloc[0].idxmax()), 3)


class BootstrapTests(unittest.TestCase):
    def test_reproducible_y_por_bloques(self):
        df = pd.DataFrame({"b": [1, 1, 2, 2, 3, 3], "v": [1, 1, 5, 5, 9, 9]})
        r1 = bootstrap_bloques(df, "b", lambda d: d["v"].mean(), n=50, semilla=1)
        r2 = bootstrap_bloques(df, "b", lambda d: d["v"].mean(), n=50, semilla=1)
        np.testing.assert_array_equal(r1, r2)
        # cada réplica promedia 3 bloques enteros: la media es (v1 + v2 + v3) / 3 con v en {1, 5, 9}
        posibles = {round((a + b + c) / 3, 6) for a in (1, 5, 9) for b in (1, 5, 9) for c in (1, 5, 9)}
        self.assertTrue(set(np.round(r1, 6)) <= posibles)


class ParcialYCentroTests(unittest.TestCase):
    def test_parcial_anula_relacion_explicada_por_z(self):
        rng = np.random.default_rng(3)
        z = pd.Series(rng.normal(size=500))
        x = z + rng.normal(0, 0.3, 500)
        y = z + rng.normal(0, 0.3, 500)
        self.assertGreater(x.corr(y, method="spearman"), 0.8)
        self.assertLess(abs(correlacion_parcial_spearman(x, y, z)), 0.15)

    def test_centro_estacional(self):
        perfil = pd.Series(0.0, index=range(1, 53))
        perfil[10] = 1.0
        self.assertAlmostEqual(centro_estacional(perfil), 10.0)
        perfil2 = pd.Series(0.0, index=range(1, 53))
        perfil2[[51, 52, 1, 2]] = 1.0          # centrado en el cambio de año
        self.assertAlmostEqual(centro_estacional(perfil2) % 52, 0.5, places=5)


if __name__ == "__main__":
    unittest.main()
