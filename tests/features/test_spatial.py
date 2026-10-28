"""Tests de src/denguekay/features/spatial.py con datos sintéticos (no dependen de data/)."""

import unittest

import numpy as np

from denguekay.features.spatial import distances_km, inverse_distance_weights, knn_weights


class DistanciasTests(unittest.TestCase):
    def test_un_grado_de_latitud(self):
        d = distances_km(np.array([0.0, 1.0]), np.array([0.0, 0.0]))
        self.assertAlmostEqual(d[0, 1], 111.19, places=1)
        self.assertEqual(d[0, 0], 0.0)


class PesosTests(unittest.TestCase):
    def test_knn_filas_suman_uno_y_sin_diagonal(self):
        d = distances_km(np.array([0, 0, 0, 5.0]), np.array([0, 0.1, 0.2, 0]))
        w = knn_weights(d, 2)
        np.testing.assert_allclose(w.sum(axis=1), 1)
        self.assertTrue((np.diag(w) == 0).all())
        self.assertEqual(w[0, 3], 0)  # el punto lejano no es vecino de 0

    def test_inverso_distancia(self):
        d = np.array([[0, 1, 2], [1, 0, 1], [2, 1, 0]], float)
        w = inverse_distance_weights(d)
        np.testing.assert_allclose(w[0], [0, 2 / 3, 1 / 3])


if __name__ == "__main__":
    unittest.main()
