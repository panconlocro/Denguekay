"""Contrato relacional, configuración y migraciones con fuentes reales."""

from datetime import date
from pathlib import Path
import tempfile
import unittest

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from backend_soporte import datos_muestra, entorno_bd, migrar, motor_temporal
from src.db.configuracion import ConfiguracionBDInvalida, obtener_url
from src.db.modelos import Base, CargaDatos, Distrito, ObservacionSemanal
from src.db.sesion import crear_motor, transaccion
from src.serving.cargar_datos import persistir_carga


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


class TestEsquemaBD(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.carpeta_fixture = tempfile.TemporaryDirectory()
        cls.datos = datos_muestra(Path(cls.carpeta_fixture.name))

    @classmethod
    def tearDownClass(cls):
        cls.carpeta_fixture.cleanup()

    def setUp(self):
        self.carpeta = tempfile.TemporaryDirectory()
        self.motor = motor_temporal(Path(self.carpeta.name))

    def tearDown(self):
        self.motor.dispose()
        self.carpeta.cleanup()

    def cargar(self):
        with transaccion(self.motor) as sesion:
            return persistir_carga(sesion, self.datos)

    def test_migracion_coincide_con_orm_y_tiene_indices(self):
        with self.motor.connect() as conexion:
            diferencias = compare_metadata(MigrationContext.configure(conexion), Base.metadata)
        self.assertEqual(diferencias, [])
        self.assertEqual(set(inspect(self.motor).get_table_names()), set(Base.metadata.tables) | {"alembic_version"})
        indices = {r["name"] for r in inspect(self.motor).get_indexes("prediccion")}
        self.assertIn("ix_prediccion_horizonte_fecha", indices)
        self.assertIn("ix_prediccion_ubigeo_horizonte", indices)

    def test_migracion_reversible_en_base_temporal_vacia(self):
        migrar(self.motor, "base")
        self.assertEqual(inspect(self.motor).get_table_names(), ["alembic_version"])
        migrar(self.motor)
        self.assertIn("observacion_semanal", inspect(self.motor).get_table_names())

    def test_ubigeo_en_python_rechaza_entero_corto_y_letras(self):
        for valor in (200101, "20101", "1234a6", "٢٠٠١٠١"):
            with self.subTest(valor=valor), self.assertRaisesRegex(ValueError, "seis dígitos"):
                Distrito(ubigeo=valor)

    def test_ubigeo_en_sql_rechaza_letras(self):
        registro = {**self.datos.distritos[0], "ubigeo": "1234a6"}
        with self.assertRaises(IntegrityError), transaccion(self.motor) as sesion:
            sesion.execute(Distrito.__table__.insert(), registro)

    def test_unicidad_observacion_y_casos_no_negativos(self):
        r = self.cargar()
        base = {**self.datos.observaciones[0], "carga_id": r["carga_id"]}
        with self.assertRaises(IntegrityError), transaccion(self.motor) as sesion:
            sesion.execute(ObservacionSemanal.__table__.insert(), base)
        with self.assertRaises(IntegrityError), transaccion(self.motor) as sesion:
            sesion.execute(ObservacionSemanal.__table__.insert(), {**base, "semana": 22, "casos": -1})

    def test_casos_nulos_requieren_motivo_y_ceros_se_conservan(self):
        self.cargar()
        with transaccion(self.motor) as sesion:
            observacion = sesion.scalar(select(ObservacionSemanal).where(ObservacionSemanal.casos == 0))
            clave = observacion.id
            self.assertIsNone(observacion.motivo)
            observacion.casos = None
            observacion.motivo = "Observación no disponible en la fuente"
        with transaccion(self.motor) as sesion:
            observacion = sesion.get(ObservacionSemanal, clave)
            self.assertIsNone(observacion.casos)
            observacion.motivo = None
            with self.assertRaises(IntegrityError):
                sesion.flush()
            sesion.rollback()

    def test_claves_foraneas_impiden_borrar_distrito_con_observaciones(self):
        self.cargar()
        with self.assertRaises(IntegrityError), transaccion(self.motor) as sesion:
            registro = self.datos.observaciones[0]
            sesion.delete(sesion.get(Distrito, registro["ubigeo"]))

    def test_json_y_corte_son_persistidos(self):
        resultado = self.cargar()
        with transaccion(self.motor) as sesion:
            carga = sesion.get(CargaDatos, resultado["carga_id"])
            self.assertEqual(carga.hashes_entrada, self.datos.hashes)
            self.assertTrue(carga.validacion_gx["exito"])
            self.assertEqual(carga.fecha_corte_datos, date(2025, 12, 27))


if __name__ == "__main__":
    unittest.main()
