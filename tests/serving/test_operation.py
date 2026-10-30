"""Fallos operativos y huellas reales sin fuentes completas ni respuestas simuladas."""

from contextlib import redirect_stderr
from dataclasses import replace
import hashlib
from io import StringIO
from pathlib import Path
import tempfile
import unittest

from sqlalchemy.engine import URL

from backend_support import datos_muestra, entorno_bd, motor_temporal
from denguekay.db.models import District
from denguekay.db.session import transaction
from denguekay.serving.artifacts import json_fingerprint
from denguekay.serving.load_data import main as cargar_cli, persist_load
from denguekay.serving.publish import code_hashes, main as publicar_cli
from denguekay.config.paths import ROOT


class TestOperacionServing(unittest.TestCase):
    def test_huella_incluye_codigo_real_y_detecta_su_contenido(self):
        hashes = code_hashes()
        self.assertIn("src/denguekay/serving/publish.py", hashes)
        self.assertIn("src/denguekay/db/models.py", hashes)
        for ruta, huella in hashes.items():
            self.assertEqual(huella, hashlib.sha256((ROOT / ruta).read_bytes()).hexdigest())
            self.assertNotIn("\\", ruta)

    def test_cli_no_configurado_y_horizonte_no_disponible_no_publican(self):
        """With the v0 package (no gold for h=3) the CLI rejects h=3 before reading any source."""
        from unittest import mock

        from serving_support import configuracion_v0

        with mock.patch("denguekay.serving.publish.service_settings", configuracion_v0):
            self._cli_no_configurado_y_horizonte_no_disponible()

    def _cli_no_configurado_y_horizonte_no_disponible(self):
        with entorno_bd(""), redirect_stderr(StringIO()) as error:
            self.assertEqual(publicar_cli(["--horizontes", "3"]), 1)
        self.assertIn("Falta DATABASE_URL", error.getvalue())
        with tempfile.TemporaryDirectory() as carpeta:
            motor = motor_temporal(Path(carpeta))
            try:
                with entorno_bd(str(motor.url)), redirect_stderr(StringIO()) as error:
                    self.assertEqual(publicar_cli(["--horizontes", "3"]), 1)
                self.assertIn("No hay gold", error.getvalue())
            finally:
                motor.dispose()

    def test_cli_carga_bd_inaccesible_no_filtra_url(self):
        with tempfile.TemporaryDirectory() as carpeta:
            url = URL.create("sqlite", database=str(Path(carpeta) / "carpeta_ausente" / "base.db"))
            with entorno_bd(str(url)), redirect_stderr(StringIO()) as error:
                self.assertEqual(cargar_cli([]), 1)
            self.assertIn("revise conexión", error.getvalue())
            self.assertNotIn("carpeta_ausente", error.getvalue())

    def test_cambio_de_metadatos_reales_preserva_auditoria_y_restaura_catalogo(self):
        with tempfile.TemporaryDirectory() as carpeta:
            datos = datos_muestra(Path(carpeta))
            motor = motor_temporal(Path(carpeta))
            try:
                # Otra presentación del mismo nombre real permite comprobar actualización del catálogo.
                distritos = [{**d, "nombre": d["nombre"].title()} for d in datos.distritos]
                previa = replace(datos, distritos=distritos,
                    hashes={**datos.hashes, "presentacion_catalogo": json_fingerprint(distritos)})
                with transaction(motor) as s:
                    primera = persist_load(s, previa)
                with transaction(motor) as s:
                    segunda = persist_load(s, datos)
                    self.assertNotEqual(primera["id_ejecucion"], segunda["id_ejecucion"])
                    for d in datos.distritos:
                        self.assertEqual(s.get(District, d["ubigeo"]).nombre, d["nombre"])
            finally:
                motor.dispose()
