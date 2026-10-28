"""Selección del dispositivo de XGBoost (GPU NVIDIA si existe, si no CPU)."""

import os
import unittest
from unittest import mock

from src.modeling import dispositivo


class DispositivoTests(unittest.TestCase):
    def setUp(self):
        dispositivo.configuracion_xgboost.cache_clear()

    def tearDown(self):
        dispositivo.configuracion_xgboost.cache_clear()

    def configurar(self, **env):
        with mock.patch.dict(os.environ, env):
            return dispositivo.configuracion_xgboost()

    def test_cpu_forzado_y_hilos_numericos(self):
        self.assertEqual(self.configurar(DENGUEKAY_XGB_DEVICE="cpu", DENGUEKAY_XGB_NJOBS="3"),
                         {"device": "cpu", "n_jobs": 3})

    def test_auto_usa_todos_los_nucleos(self):
        config = self.configurar(DENGUEKAY_XGB_DEVICE="cpu", DENGUEKAY_XGB_NJOBS="auto")
        self.assertEqual(config["n_jobs"], os.cpu_count() or 1)

    def test_auto_elige_gpu_solo_si_existe(self):
        with mock.patch.object(dispositivo, "cuda_disponible", return_value=False):
            self.assertEqual(self.configurar(DENGUEKAY_XGB_DEVICE="auto")["device"], "cpu")
        dispositivo.configuracion_xgboost.cache_clear()
        with mock.patch.object(dispositivo, "cuda_disponible", return_value=True):
            self.assertEqual(self.configurar(DENGUEKAY_XGB_DEVICE="auto")["device"], "cuda")

    def test_cuda_pedido_sin_gpu_falla_claro(self):
        with mock.patch.object(dispositivo, "cuda_disponible", return_value=False):
            with self.assertRaises(RuntimeError):
                self.configurar(DENGUEKAY_XGB_DEVICE="cuda")

    def test_valor_invalido(self):
        with self.assertRaises(ValueError):
            self.configurar(DENGUEKAY_XGB_DEVICE="metal")

    def test_deteccion_real_no_rompe(self):
        self.assertIsInstance(dispositivo.cuda_disponible(), bool)


if __name__ == "__main__":
    unittest.main()
