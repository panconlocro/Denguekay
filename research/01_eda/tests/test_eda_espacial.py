"""Tests de src/eda/espacial.py con datos sintéticos (no dependen de data/)."""

import unittest

import numpy as np
import pandas as pd

from src.eda.espacial import (
    distancias_km, estado_vecinos_rezagado, mantel, moran_i, pesos_inverso_distancia, pesos_knn, rr_mantel_haenszel,
)


class DistanciasTests(unittest.TestCase):
    def test_un_grado_de_latitud(self):
        d = distancias_km(np.array([0.0, 1.0]), np.array([0.0, 0.0]))
        self.assertAlmostEqual(d[0, 1], 111.19, places=1)
        self.assertEqual(d[0, 0], 0.0)


class PesosTests(unittest.TestCase):
    def test_knn_filas_suman_uno_y_sin_diagonal(self):
        d = distancias_km(np.array([0, 0, 0, 5.0]), np.array([0, 0.1, 0.2, 0]))
        w = pesos_knn(d, 2)
        np.testing.assert_allclose(w.sum(axis=1), 1)
        self.assertTrue((np.diag(w) == 0).all())
        self.assertEqual(w[0, 3], 0)  # el punto lejano no es vecino de 0

    def test_inverso_distancia(self):
        d = np.array([[0, 1, 2], [1, 0, 1], [2, 1, 0]], float)
        w = pesos_inverso_distancia(d)
        np.testing.assert_allclose(w[0], [0, 2 / 3, 1 / 3])


class MoranTests(unittest.TestCase):
    def test_agrupado_positivo_y_significativo(self):
        lat = np.r_[np.zeros(10), np.full(10, 5.0)]
        lon = np.r_[np.linspace(0, 1, 10), np.linspace(0, 1, 10)]
        x = np.r_[np.ones(10), np.zeros(10)] + np.random.default_rng(1).normal(0, 0.01, 20)
        r = moran_i(x, pesos_knn(distancias_km(lat, lon), 3), permutaciones=199)
        self.assertGreater(r["I"], 0.8)
        self.assertLess(r["p_valor"], 0.05)


class VecinosTests(unittest.TestCase):
    def test_usa_solo_el_pasado(self):
        fechas = pd.date_range("2017-01-01", periods=3, freq="7D")
        df = pd.DataFrame({"ubigeo": ["a"] * 3 + ["b"] * 3, "semana_inicio": list(fechas) * 2,
                           "m": [0, 0, 0, 1, 0, 0]})
        w = np.array([[0, 1.0], [1.0, 0]])
        v = estado_vecinos_rezagado(df, "m", w, ["a", "b"], h=1)
        self.assertTrue(np.isnan(v.iloc[0]))
        self.assertEqual(v.iloc[1], 1.0)   # a en la semana 2 ve a b en la semana 1
        self.assertEqual(v.iloc[4], 0.0)   # b ve a a, que siempre es 0


class RiesgoTests(unittest.TestCase):
    def test_rr_mantel_haenszel_estrato_unico_igual_al_crudo(self):
        e = pd.Series([1] * 10 + [0] * 10)
        y = pd.Series([1] * 4 + [0] * 6 + [1] * 2 + [0] * 8)
        self.assertAlmostEqual(rr_mantel_haenszel(e, y, pd.Series(["a"] * 20)), 2.0)

    def test_rr_mantel_haenszel_omite_estratos_sin_contraste(self):
        e = pd.Series([1, 1, 0, 0, 0, 0])
        y = pd.Series([1, 0, 0, 1, 1, 1])
        s = pd.Series(["a", "a", "a", "a", "b", "b"])  # el estrato b no tiene expuestos
        self.assertAlmostEqual(rr_mantel_haenszel(e, y, s), 1.0)

    def test_mantel_detecta_relacion(self):
        rng = np.random.default_rng(0)
        pts = rng.uniform(size=(12, 2))
        dist = np.sqrt(((pts[:, None] - pts[None]) ** 2).sum(-1))
        r = mantel(-dist, dist, permutaciones=199)
        self.assertAlmostEqual(r["rho"], -1.0)
        self.assertLess(r["p_valor"], 0.05)


if __name__ == "__main__":
    unittest.main()
