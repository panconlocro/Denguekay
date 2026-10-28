"""Pruebas de la caché del notebook de arquitectura: invalidación y forzado."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from denguekay.evaluation import cache as ce


class TestCacheExperimentos(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.llamadas = 0

    def tearDown(self):
        self.tmp.cleanup()

    def _calcular(self):
        self.llamadas += 1
        return {"valor": self.llamadas}

    def test_reutiliza_con_la_misma_huella_y_recalcula_si_cambia(self):
        a = ce.load_or_compute("x", self._calcular, fingerprint="h1", directory=self.dir)
        b = ce.load_or_compute("x", self._calcular, fingerprint="h1", directory=self.dir)
        self.assertEqual((a, b, self.llamadas), ({"valor": 1}, {"valor": 1}, 1))
        c = ce.load_or_compute("x", self._calcular, fingerprint="h2", directory=self.dir)
        self.assertEqual((c, self.llamadas), ({"valor": 2}, 2))

    def test_forzar_recalcula_siempre(self):
        ce.load_or_compute("x", self._calcular, fingerprint="h1", directory=self.dir)
        d = ce.load_or_compute("x", self._calcular, fingerprint="h1", directory=self.dir, force=True)
        self.assertEqual((d, self.llamadas), ({"valor": 2}, 2))
        # Lo forzado queda guardado y se reutiliza después.
        e = ce.load_or_compute("x", self._calcular, fingerprint="h1", directory=self.dir)
        self.assertEqual((e, self.llamadas), ({"valor": 2}, 2))

    def test_huella_cambia_con_el_contenido_de_un_archivo(self):
        archivo = self.dir / "insumo.py"
        archivo.write_text("a = 1\n", encoding="utf-8")
        h1 = ce.files_fingerprint([archivo])
        self.assertEqual(h1, ce.files_fingerprint([archivo]))
        archivo.write_text("a = 2\n", encoding="utf-8")
        self.assertNotEqual(h1, ce.files_fingerprint([archivo]))
        with self.assertRaises(FileNotFoundError):
            ce.files_fingerprint([self.dir / "no_existe.csv"])

    def test_insumos_cubren_datos_configuracion_y_codigo(self):
        nombres = {p.name for p in ce.study_inputs()}
        self.assertTrue({"config.yaml", "manifest_fase6.json", "probabilistic_output.py",
                         "protocol.py", "forecast_contract.py"} <= nombres)

    def test_forzar_desde_entorno(self):
        with mock.patch.dict(os.environ, {ce.FORCE_VARIABLE: "1"}):
            self.assertTrue(ce.force_from_env())
        with mock.patch.dict(os.environ, {ce.FORCE_VARIABLE: "0"}):
            self.assertFalse(ce.force_from_env())


if __name__ == "__main__":
    unittest.main()
