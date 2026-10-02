"""Fallos operativos y huellas reales sin fuentes completas ni respuestas simuladas."""

from contextlib import redirect_stderr
from dataclasses import replace
import hashlib
from io import StringIO
from pathlib import Path
import tempfile
import unittest

from sqlalchemy.engine import URL

from backend_soporte import datos_muestra, entorno_bd, motor_temporal
from src.db.modelos import Distrito
from src.db.sesion import transaccion
from src.serving.artefactos import huella_json
from src.serving.cargar_datos import main as cargar_cli, persistir_carga
from src.serving.publicar import hashes_codigo, main as publicar_cli
from src.utils.paths import ROOT


class TestOperacionServing(unittest.TestCase):
    def test_huella_incluye_codigo_real_y_detecta_su_contenido(self):
        hashes = hashes_codigo()
        self.assertIn("src/serving/publicar.py", hashes)
        self.assertIn("src/db/modelos.py", hashes)
        for ruta, huella in hashes.items():
            self.assertEqual(huella, hashlib.sha256((ROOT / ruta).read_bytes()).hexdigest())
            self.assertNotIn("\\", ruta)

    def test_cli_no_configurado_y_horizonte_no_disponible_no_publican(self):
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
                    hashes={**datos.hashes, "presentacion_catalogo": huella_json(distritos)})
                with transaccion(motor) as s:
                    primera = persistir_carga(s, previa)
                with transaccion(motor) as s:
                    segunda = persistir_carga(s, datos)
                    self.assertNotEqual(primera["carga_id"], segunda["carga_id"])
                    for d in datos.distritos:
                        self.assertEqual(s.get(Distrito, d["ubigeo"]).nombre, d["nombre"])
            finally:
                motor.dispose()
