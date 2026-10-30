"""Configuración de la conexión; el esquema OE2 se prueba en test_esquema_oe2."""

import os
import unittest
from unittest import mock

from sqlalchemy import text

from backend_support import entorno_bd
from denguekay.db.settings import InvalidDatabaseSettings, get_url, migration_url, prepared_statements
from denguekay.db.session import make_engine


class TestConfiguracionBD(unittest.TestCase):
    def test_url_ausente_error_en_espanol(self):
        with entorno_bd(""), self.assertRaisesRegex(InvalidDatabaseSettings, "Falta DATABASE_URL"):
            get_url()

    def test_url_invalida_no_expone_secreto(self):
        with entorno_bd("secreto_que_no_debe_imprimirse"):
            with self.assertRaises(InvalidDatabaseSettings) as error:
                get_url()
            self.assertNotIn("secreto", str(error.exception))

    def test_postgres_normalizado_a_psycopg3(self):
        for prefijo in ("postgres", "postgresql", "postgresql+psycopg"):
            with self.subTest(prefijo=prefijo), entorno_bd(f"{prefijo}://usuario:clave@localhost/pruebas"):
                self.assertEqual(get_url().drivername, "postgresql+psycopg")

    def test_motor_no_admitido_y_postgres_sin_base(self):
        for valor in ("mysql://localhost/base", "postgresql://localhost"):
            with self.subTest(valor=valor), entorno_bd(valor), self.assertRaises(InvalidDatabaseSettings):
                get_url()

    def test_sqlite_motor_compartido_y_claves_foraneas(self):
        with entorno_bd("sqlite://"):
            motor = make_engine()
        try:
            with motor.connect() as conexion:
                self.assertEqual(conexion.scalar(text("PRAGMA foreign_keys")), 1)
        finally:
            motor.dispose()


    def test_alembic_usa_la_url_del_dueno_si_existe(self):
        dueno = "postgresql://dueno:clave@localhost/pruebas"
        with mock.patch("denguekay.db.settings.load_dotenv"), entorno_bd("sqlite://"):
            with mock.patch.dict(os.environ, {"MIGRATION_DATABASE_URL": dueno}):
                self.assertEqual(migration_url().username, "dueno")
            with mock.patch.dict(os.environ, {"MIGRATION_DATABASE_URL": " "}):
                self.assertEqual(migration_url().get_backend_name(), "sqlite")
            with mock.patch.dict(os.environ, {"MIGRATION_DATABASE_URL": "mysql://x/y"}),                     self.assertRaisesRegex(InvalidDatabaseSettings, "MIGRATION_DATABASE_URL"):
                migration_url()

    def test_sentencias_preparadas_desactivables_para_el_pooler(self):
        with mock.patch("denguekay.db.settings.load_dotenv"):
            for valor, esperado in (("", True), ("true", True), ("FALSE", False), ("0", False)):
                with self.subTest(valor=valor), mock.patch.dict(os.environ, {"DB_PREPARED_STATEMENTS": valor}):
                    self.assertIs(prepared_statements(), esperado)
            with mock.patch.dict(os.environ, {"DB_PREPARED_STATEMENTS": "a veces"}),                     self.assertRaises(InvalidDatabaseSettings):
                prepared_statements()
            url = "postgresql+psycopg://usuario:clave@localhost:6543/pruebas"
            for valor, preparadas in (("false", False), ("true", True)):
                with self.subTest(valor=valor), mock.patch.dict(os.environ, {"DB_PREPARED_STATEMENTS": valor}),                         mock.patch("denguekay.db.session.create_engine") as crear:
                    make_engine(url)
                    argumentos = crear.call_args.kwargs["connect_args"]
                    self.assertEqual("prepare_threshold" in argumentos, not preparadas)
                    if not preparadas:
                        self.assertIsNone(argumentos["prepare_threshold"])


class TestEvidenciaSQL(unittest.TestCase):
    def test_sql_offline_de_la_migracion_sin_credenciales(self):
        import tempfile
        from pathlib import Path
        from denguekay.db.export_migration_sql import export
        with tempfile.TemporaryDirectory() as carpeta:
            sql = export(Path(carpeta) / "migracion.sql").read_text(encoding="utf-8")
        self.assertEqual(sql.count("CREATE TYPE"), 10)
        self.assertIn("CREATE POLICY servicio_prediccion", sql)
        self.assertIn("ux_ejecucion_huella_ingesta", sql)
        self.assertNotIn("CONSTRAINT ck_provincia_ck_", sql)
        self.assertNotIn("password", sql.lower())


if __name__ == "__main__":
    unittest.main()
