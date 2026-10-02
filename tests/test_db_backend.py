"""Configuración de la conexión; el esquema OE2 se prueba en test_esquema_oe2."""

import unittest

from sqlalchemy import text

from backend_soporte import entorno_bd
from src.db.configuracion import ConfiguracionBDInvalida, obtener_url
from src.db.sesion import crear_motor


class TestConfiguracionBD(unittest.TestCase):
    def test_url_ausente_error_en_espanol(self):
        with entorno_bd(""), self.assertRaisesRegex(ConfiguracionBDInvalida, "Falta DATABASE_URL"):
            obtener_url()

    def test_url_invalida_no_expone_secreto(self):
        with entorno_bd("secreto_que_no_debe_imprimirse"):
            with self.assertRaises(ConfiguracionBDInvalida) as error:
                obtener_url()
            self.assertNotIn("secreto", str(error.exception))

    def test_postgres_normalizado_a_psycopg3(self):
        for prefijo in ("postgres", "postgresql", "postgresql+psycopg"):
            with self.subTest(prefijo=prefijo), entorno_bd(f"{prefijo}://usuario:clave@localhost/pruebas"):
                self.assertEqual(obtener_url().drivername, "postgresql+psycopg")

    def test_motor_no_admitido_y_postgres_sin_base(self):
        for valor in ("mysql://localhost/base", "postgresql://localhost"):
            with self.subTest(valor=valor), entorno_bd(valor), self.assertRaises(ConfiguracionBDInvalida):
                obtener_url()

    def test_sqlite_motor_compartido_y_claves_foraneas(self):
        with entorno_bd("sqlite://"):
            motor = crear_motor()
        try:
            with motor.connect() as conexion:
                self.assertEqual(conexion.scalar(text("PRAGMA foreign_keys")), 1)
        finally:
            motor.dispose()


if __name__ == "__main__":
    unittest.main()
