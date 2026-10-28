"""Esquema OE2: concordancia ORM ↔ migración, restricciones del DDL y seguridad.

Cada caso se ejecuta en SQLite temporal. Si existe DENGUEKAY_PG_PRUEBAS_URL
(BD PostgreSQL desechable), los mismos casos y los de RLS/roles se repiten
en PostgreSQL; al terminar, esa BD vuelve a la revisión base.
"""

from datetime import date, datetime, timezone
from pathlib import Path
import re
import tempfile
import unittest
import warnings

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import delete, func, inspect, select, text
from sqlalchemy.dialects.postgresql import insert as insert_postgresql
from sqlalchemy.dialects.sqlite import insert as insert_sqlite
from sqlalchemy.exc import DBAPIError, IntegrityError, StatementError
from sqlalchemy.schema import CreateTable

from backend_soporte import migrar, url_pg_pruebas
from src.db.modelos import (Alerta, Base, Distrito, Ejecucion, ImportanciaVariable,
                            ObservacionSemanal, ParametroSistema, Prediccion, Provincia,
                            SemanaEpidemiologica, VersionModelo)
from src.db.sesion import crear_motor, transaccion

TABLAS_OE2 = {"provincia", "distrito", "semana_epidemiologica", "observacion_semanal",
              "version_modelo", "ejecucion", "prediccion", "alerta", "parametro_sistema"}
TABLAS_0002 = {"carga_datos", "distrito", "ejecucion_prediccion", "version_modelo",
               "activacion_modelo", "importancia_variable", "observacion_semanal",
               "prediccion", "alerta"}
# Orden de borrado que respeta las claves foráneas; parametro_sistema conserva sus semillas.
ORDEN_LIMPIEZA = (Alerta, Prediccion, ImportanciaVariable, VersionModelo, ObservacionSemanal,
                  Ejecucion, SemanaEpidemiologica, Distrito, Provincia)
SHA = "a" * 64
# Motivos esperados en el mensaje del motor (SQLite y PostgreSQL).
FK = r"foreign key"
UNICA = r"unique|duplicate key"


def bajar_una_revision(motor):
    """alembic downgrade -1 sobre el motor de la prueba."""
    from alembic import command
    from alembic.config import Config
    from src.utils.paths import ALEMBIC_CONFIG
    config = Config(str(ALEMBIC_CONFIG))
    config.attributes["motor"] = motor
    command.downgrade(config, "-1")


def fila_version(**cambios):
    return {"codigo": "clf-h4-v1", "tarea": "clasificacion", "horizonte": 4, "algoritmo": "xgboost",
            "variables": ["casos_lag_4"], "hiperparametros": {"max_depth": 3}, "metricas": {},
            "umbral_probabilidad": 0.3, "cumple_umbrales": False, "estado": "candidata",
            "mlflow_run_id": "run", "ruta_artefacto": "modelos/clf-h4-v1.json",
            "sha256_artefacto": SHA, "sha256_dataset": SHA, **cambios}


class EsquemaOE2:
    """Casos comunes; las subclases definen el motor."""

    motor = None

    @classmethod
    def crear_motor(cls):
        raise NotImplementedError

    @classmethod
    def setUpClass(cls):
        cls.motor = cls.crear_motor()
        migrar(cls.motor)

    def setUp(self):
        with transaccion(self.motor) as s:
            s.add(Provincia(ubigeo_provincia="2001", nombre="Piura"))
            s.flush()
            s.add(Distrito(ubigeo="200101", ubigeo_provincia="2001", nombre="Piura",
                           latitud=-5.194, longitud=-80.632, poblacion_censo_2017=158495))
            for id_semana, inicio in ((202551, date(2025, 12, 14)), (202552, date(2025, 12, 21)),
                                      (202553, date(2025, 12, 28))):
                s.add(SemanaEpidemiologica(id_semana=id_semana, anio=2025, semana=id_semana % 100,
                                           fecha_inicio=inicio, fecha_fin=date.fromordinal(inicio.toordinal() + 6),
                                           temporada=2026))
            s.flush()
            ejecucion = Ejecucion(tipo="ingesta", estado="exitosa", detalle={"huella": "h1"})
            s.add(ejecucion)
            s.flush()
            self.id_ejecucion = ejecucion.id_ejecucion

    def tearDown(self):
        with transaccion(self.motor) as s:
            for modelo in ORDEN_LIMPIEZA:
                s.execute(delete(modelo))

    # --- utilidades -------------------------------------------------------

    def insertar(self, modelo, **fila):
        with transaccion(self.motor) as s:
            resultado = s.execute(modelo.__table__.insert().values(**fila))
            return resultado.inserted_primary_key[0]

    def assert_rechaza(self, modelo, motivo, **fila):
        """La BD (no Python) rechaza la fila por el motivo esperado.

        ``motivo`` es el nombre de la CHECK (sin el prefijo ``ck_<tabla>_``) o una
        expresión de FK/UNIQUE; evita que un caso pase por otra restricción.
        """
        with self.assertRaises((IntegrityError, DBAPIError)) as error:
            self.insertar(modelo, **fila)
        if re.fullmatch(r"[a-z0-9_]+", motivo):
            motivo = f"ck_{modelo.__tablename__}_{motivo}"
        self.assertRegex(str(error.exception.orig), re.compile(motivo, re.IGNORECASE))

    def fila_observacion(self, **cambios):
        return {"ubigeo": "200101", "id_semana": 202552, "casos_dengue": 3, "umbral_brote_casos": 2.5,
                "brote": True, "temp_media_c": 25.0, "temp_min_c": 21.0, "temp_max_c": 31.0,
                "precip_total_mm": 4.0, "hum_rel_media_pct": 70.0, "fuente_casos": "sala_situacional",
                "estado_cobertura": "verificado", "fecha_extraccion": datetime.now(timezone.utc),
                "id_ejecucion": self.id_ejecucion, **cambios}

    def fila_prediccion(self, **cambios):
        return {"ubigeo": "200101", "id_semana_corte": 202551, "id_semana_objetivo": 202553,
                "horizonte": 2, "probabilidad_brote": 0.6, "nivel_riesgo": "alto",
                "casos_estimados": 4.5, "estado": "disponible", "id_ejecucion": self.id_ejecucion, **cambios}

    def upsert(self, fila):
        """UPSERT por la clave única del documento (ubigeo, id_semana_corte, horizonte)."""
        insertar = insert_postgresql if self.motor.dialect.name == "postgresql" else insert_sqlite
        consulta = insertar(Prediccion.__table__).values(**fila)
        actualizables = {c: consulta.excluded[c] for c in fila if c not in ("ubigeo", "id_semana_corte", "horizonte")}
        with transaccion(self.motor) as s:
            s.execute(consulta.on_conflict_do_update(
                index_elements=["ubigeo", "id_semana_corte", "horizonte"], set_=actualizables))

    # --- concordancia y semillas -----------------------------------------

    def test_migracion_coincide_con_orm(self):
        with warnings.catch_warnings():
            # SQLite no refleja índices por expresión (huella de ingesta, solo PostgreSQL).
            warnings.filterwarnings("ignore", message=".*expression-based index.*")
            with self.motor.connect() as conexion:
                diferencias = compare_metadata(MigrationContext.configure(conexion), Base.metadata)
        self.assertEqual(diferencias, [])
        tablas = set(inspect(self.motor).get_table_names())
        self.assertEqual(tablas, TABLAS_OE2 | {"importancia_variable", "alembic_version"})
        indices = {i["name"] for t in tablas for i in inspect(self.motor).get_indexes(t)}
        self.assertLessEqual({"ix_pred_objetivo", "ix_alerta_estado", "ix_obs_semana",
                              "ix_ejecucion_tipo_inicio", "ux_version_activa"}, indices)

    def test_semillas_de_parametros(self):
        with transaccion(self.motor) as s:
            valores = {p.clave: p.valor for p in s.scalars(select(ParametroSistema))}
        self.assertEqual(set(valores), {"regla_brote", "cortes_riesgo", "umbrales_aceptacion"})
        self.assertEqual(valores["regla_brote"], {"anios_previos": 5, "k_desviaciones": 1.5, "minimo_casos": 2})
        self.assertEqual(valores["cortes_riesgo"], {"medio": 0.25, "alto": 0.50, "muy_alto": 0.75})
        self.assertEqual(valores["umbrales_aceptacion"]["bloque"], "temporada_2024")
        self.assertEqual(valores["umbrales_aceptacion"]["razon_error_base"], 0.85)

    # --- CHECK, uno por caso inválido --------------------------------------

    def test_checks_de_catalogo_y_calendario(self):
        casos = [
            (Provincia, "ubigeo_provincia_formato", {"ubigeo_provincia": "20a1", "nombre": "X"}),
            (Distrito, "ubigeo_formato", {"ubigeo": "2001a1", "ubigeo_provincia": "2001", "nombre": "X",
                                          "latitud": -5, "longitud": -80}),
            (Distrito, "latitud_piura", {"ubigeo": "200102", "ubigeo_provincia": "2001", "nombre": "X",
                                         "latitud": -12.0, "longitud": -80}),
            (Distrito, "longitud_piura", {"ubigeo": "200103", "ubigeo_provincia": "2001", "nombre": "X",
                                          "latitud": -5, "longitud": -77.0}),
            (Distrito, "poblacion_positiva", {"ubigeo": "200104", "ubigeo_provincia": "2001", "nombre": "X",
                                              "latitud": -5, "longitud": -80, "poblacion_censo_2017": 0}),
            (Distrito, FK, {"ubigeo": "200105", "ubigeo_provincia": "9999", "nombre": "X",
                            "latitud": -5, "longitud": -80}),
            (SemanaEpidemiologica, "semana_valida", {"id_semana": 202554, "anio": 2025, "semana": 54,
                "fecha_inicio": date(2026, 1, 4), "fecha_fin": date(2026, 1, 10), "temporada": 2026}),
            (SemanaEpidemiologica, "fecha_fin_valida", {"id_semana": 202601, "anio": 2026, "semana": 1,
                "fecha_inicio": date(2026, 1, 4), "fecha_fin": date(2026, 1, 11), "temporada": 2026}),
            (SemanaEpidemiologica, UNICA, {"id_semana": 202599, "anio": 2025, "semana": 52,
                "fecha_inicio": date(2025, 12, 21), "fecha_fin": date(2025, 12, 27), "temporada": 2026}),
        ]
        for modelo, motivo, fila in casos:
            with self.subTest(tabla=modelo.__tablename__, motivo=motivo):
                self.assert_rechaza(modelo, motivo, **fila)

    def test_checks_de_observacion(self):
        casos = [("casos_no_negativos", {"casos_dengue": -1}), ("umbral_no_negativo", {"umbral_brote_casos": -0.5}),
                 ("precipitacion_valida", {"precip_total_mm": 1500.5}), ("precipitacion_valida", {"precip_total_mm": -1}),
                 ("humedad_valida", {"hum_rel_media_pct": 100.5}), ("temperaturas_ordenadas", {"temp_min_c": 26.0}),
                 ("temperaturas_ordenadas", {"temp_max_c": 24.0}), (FK, {"id_semana": 209901})]
        for motivo, cambio in casos:
            with self.subTest(cambio=cambio):
                self.assert_rechaza(ObservacionSemanal, motivo, **self.fila_observacion(**cambio))
        self.insertar(ObservacionSemanal, **self.fila_observacion(casos_dengue=None))
        self.assert_rechaza(ObservacionSemanal, UNICA, **self.fila_observacion())  # PK (ubigeo, id_semana)

    def test_observacion_conserva_cero_y_nulo(self):
        self.insertar(ObservacionSemanal, **self.fila_observacion(casos_dengue=0))
        self.insertar(ObservacionSemanal, **self.fila_observacion(id_semana=202551, casos_dengue=None))
        with transaccion(self.motor) as s:
            casos = dict(s.execute(select(ObservacionSemanal.id_semana, ObservacionSemanal.casos_dengue)).all())
        self.assertEqual(casos, {202552: 0, 202551: None})

    def test_enum_invalido_rechazado_por_la_bd(self):
        fila = self.fila_observacion(fuente_casos="otra_fuente")
        columnas = ", ".join(fila)
        marcadores = ", ".join(f":{c}" for c in fila)
        with self.assertRaises((IntegrityError, DBAPIError)) as error, transaccion(self.motor) as s:
            s.execute(text(f"INSERT INTO observacion_semanal ({columnas}) VALUES ({marcadores})"), fila)
        self.assertRegex(str(error.exception.orig), r"fuente_casos_t")
        with self.assertRaises(StatementError):
            self.insertar(ObservacionSemanal, **self.fila_observacion(estado_cobertura="desconocido"))

    def test_checks_de_version_modelo(self):
        casos = [("horizonte_valido", {"horizonte": 5}), ("umbral_valido", {"umbral_probabilidad": 1.5}),
                 ("activa_cumple_umbrales", {"estado": "activa", "cumple_umbrales": False})]
        for i, (motivo, cambio) in enumerate(casos):
            with self.subTest(cambio=cambio):
                self.assert_rechaza(VersionModelo, motivo, **fila_version(codigo=f"v{i}", **cambio))
        id_version = self.insertar(VersionModelo, **fila_version())
        self.assert_rechaza(VersionModelo, UNICA, **fila_version())  # codigo único
        for cambio in ({"importancia": -0.1}, {"rango": 0}):
            with self.subTest(importancia=cambio):
                self.assert_rechaza(ImportanciaVariable, "importancia_valida", **{
                    "id_version": id_version, "variable": "casos_lag_4", "importancia": 1.0, "rango": 1, **cambio})

    def test_una_sola_version_activa_por_tarea_y_horizonte(self):
        self.insertar(VersionModelo, **fila_version(codigo="a", estado="activa", cumple_umbrales=True))
        self.assert_rechaza(VersionModelo, UNICA, **fila_version(codigo="b", estado="activa", cumple_umbrales=True))
        # Otra tarea, otro horizonte y versiones no activas sí conviven.
        self.insertar(VersionModelo, **fila_version(codigo="c", tarea="regresion", estado="activa",
                                                    cumple_umbrales=True, umbral_probabilidad=None))
        self.insertar(VersionModelo, **fila_version(codigo="d", horizonte=2, estado="activa", cumple_umbrales=True))
        self.insertar(VersionModelo, **fila_version(codigo="e", estado="archivada"))
        self.insertar(VersionModelo, **fila_version(codigo="f", estado="archivada"))

    def test_checks_de_prediccion(self):
        casos = [("horizonte_valido", {"horizonte": 1}), ("probabilidad_valida", {"probabilidad_brote": 1.2}),
                 ("casos_no_negativos", {"casos_estimados": -1.0}), (FK, {"id_semana_objetivo": 209901}),
                 (FK, {"ubigeo": "200199"})]
        for motivo, cambio in casos:
            with self.subTest(cambio=cambio):
                self.assert_rechaza(Prediccion, motivo, **self.fila_prediccion(**cambio))

    def test_coherencia_disponible_no_disponible(self):
        invalidas = [
            {"nivel_riesgo": None},
            {"probabilidad_brote": None},
            {"estado": "no_disponible", "motivo_no_disponible": "sin modelo"},
            {"estado": "no_disponible", "probabilidad_brote": None, "nivel_riesgo": None},
        ]
        for cambio in invalidas:
            with self.subTest(cambio=cambio):
                self.assert_rechaza(Prediccion, "estado_coherente", **self.fila_prediccion(**cambio))
        self.insertar(Prediccion, **self.fila_prediccion(
            estado="no_disponible", probabilidad_brote=None, nivel_riesgo=None, casos_estimados=None,
            motivo_no_disponible="sin modelo para h=3", horizonte=3))
        self.insertar(Prediccion, **self.fila_prediccion())

    def test_upsert_de_prediccion_por_clave_del_documento(self):
        self.upsert(self.fila_prediccion())
        self.upsert(self.fila_prediccion(probabilidad_brote=0.8, nivel_riesgo="muy_alto"))
        with transaccion(self.motor) as s:
            filas = s.execute(select(Prediccion.probabilidad_brote, Prediccion.nivel_riesgo)).all()
        self.assertEqual(len(filas), 1)
        self.assertAlmostEqual(filas[0][0], 0.8)
        self.assertEqual(filas[0][1], "muy_alto")
        self.assert_rechaza(Prediccion, UNICA, **self.fila_prediccion())  # insert simple duplicado
        self.upsert(self.fila_prediccion(horizonte=4))  # otra clave: nueva fila
        with transaccion(self.motor) as s:
            self.assertEqual(s.scalar(select(func.count()).select_from(Prediccion)), 2)

    def test_alerta_solo_alto_o_muy_alto_y_retiro_con_fecha(self):
        id_prediccion = self.insertar(Prediccion, **self.fila_prediccion())
        base = {"id_prediccion": id_prediccion, "ubigeo": "200101", "nivel": "alto", "cambio": "nueva"}
        for nivel in ("bajo", "medio"):
            with self.subTest(nivel=nivel):
                self.assert_rechaza(Alerta, "nivel_alerta", **{**base, "nivel": nivel})
        self.assert_rechaza(Alerta, "retiro_con_fecha", **{**base, "estado": "retirada"})
        self.insertar(Alerta, **base)
        self.assert_rechaza(Alerta, UNICA, **{**base, "nivel": "muy_alto"})  # una alerta por predicción

    def test_nombres_de_check_iguales_en_orm_y_bd(self):
        """La migración no debe duplicar el prefijo de la convención de nombres."""
        inspector = inspect(self.motor)
        for tabla in Base.metadata.sorted_tables:
            ddl = str(CreateTable(tabla).compile(dialect=self.motor.dialect))
            esperados = set(re.findall(r"CONSTRAINT (ck_\w+) CHECK", ddl))
            reales = {c["name"] for c in inspector.get_check_constraints(tabla.name)}
            with self.subTest(tabla=tabla.name):
                self.assertEqual(reales, esperados)

    def test_validacion_en_python(self):
        for valor in (200101, "20101", "1234a6", "٢٠٠١٠١"):
            with self.subTest(valor=valor), self.assertRaisesRegex(ValueError, "seis dígitos"):
                Distrito(ubigeo=valor)
        with self.assertRaisesRegex(ValueError, "cuatro dígitos"):
            Provincia(ubigeo_provincia=2001)
        for modelo in (VersionModelo, Prediccion):
            with self.subTest(modelo=modelo.__name__), self.assertRaisesRegex(ValueError, "2, 3 o 4"):
                modelo(horizonte=5)


class TestEsquemaOE2SQLite(EsquemaOE2, unittest.TestCase):
    @classmethod
    def crear_motor(cls):
        from sqlalchemy.engine import URL
        cls.carpeta = tempfile.TemporaryDirectory()
        return crear_motor(URL.create("sqlite", database=str(Path(cls.carpeta.name) / "oe2.db")))

    @classmethod
    def tearDownClass(cls):
        cls.motor.dispose()
        cls.carpeta.cleanup()

    def test_migracion_reversible(self):
        bajar_una_revision(self.motor)
        self.assertEqual(set(inspect(self.motor).get_table_names()), TABLAS_0002 | {"alembic_version"})
        migrar(self.motor)
        self.assertLessEqual(TABLAS_OE2, set(inspect(self.motor).get_table_names()))
        self.setUp()  # el downgrade borró los datos de apoyo


@unittest.skipUnless(url_pg_pruebas(), "Sin DENGUEKAY_PG_PRUEBAS_URL: se omiten las pruebas en PostgreSQL")
class TestEsquemaOE2PostgreSQL(EsquemaOE2, unittest.TestCase):
    @classmethod
    def crear_motor(cls):
        motor = crear_motor(url_pg_pruebas())
        migrar(motor, "base")  # BD desechable: parte de cero aunque una corrida previa fallara
        return motor

    @classmethod
    def tearDownClass(cls):
        migrar(cls.motor, "base")
        cls.motor.dispose()

    def consulta(self, sql):
        with self.motor.connect() as conexion:
            return conexion.execute(text(sql)).all()

    def test_migracion_reversible(self):
        bajar_una_revision(self.motor)
        self.assertEqual(set(inspect(self.motor).get_table_names()), TABLAS_0002 | {"alembic_version"})
        self.assertEqual(self.consulta("SELECT count(*) FROM pg_type WHERE typtype = 'e' AND typname LIKE '%_t'")[0][0], 0)
        migrar(self.motor)  # vuelve a subir aunque los roles ya existan
        self.assertLessEqual(TABLAS_OE2, set(inspect(self.motor).get_table_names()))
        self.setUp()

    def test_enum_nativos_jsonb_e_identity(self):
        tipos = {r[0] for r in self.consulta("SELECT typname FROM pg_type WHERE typtype = 'e'")}
        self.assertLessEqual({"fuente_casos_t", "cobertura_t", "tarea_t", "estado_version_t",
                              "tipo_ejecucion_t", "estado_ejecucion_t", "nivel_riesgo_t",
                              "estado_prediccion_t", "estado_alerta_t", "cambio_alerta_t"}, tipos)
        columnas = dict(self.consulta(
            "SELECT table_name || '.' || column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = 'public' AND column_name IN ('detalle', 'valor', 'metricas', 'latitud', 'ubigeo')"))
        self.assertEqual(columnas["ejecucion.detalle"], "jsonb")
        self.assertEqual(columnas["version_modelo.metricas"], "jsonb")
        self.assertEqual(columnas["distrito.latitud"], "numeric")
        self.assertEqual(columnas["distrito.ubigeo"], "character")
        identidad = dict(self.consulta(
            "SELECT table_name, identity_generation FROM information_schema.columns "
            "WHERE table_schema = 'public' AND is_identity = 'YES'"))
        self.assertEqual(identidad["prediccion"], "ALWAYS")
        self.assert_rechaza(Ejecucion, r"generated always|cannot insert", id_ejecucion=999, tipo="ingesta")

    def test_check_regex_de_ubigeo(self):
        # CHAR(6) rellena con espacios un código corto; la regex lo rechaza.
        self.assert_rechaza(Distrito, "ubigeo_formato", ubigeo="20011", ubigeo_provincia="2001", nombre="X",
                            latitud=-5, longitud=-80)

    def test_rls_politicas_y_roles(self):
        rls = dict(self.consulta("SELECT relname, relrowsecurity FROM pg_class WHERE relkind = 'r' "
                                 "AND relnamespace = 'public'::regnamespace"))
        for tabla in TABLAS_OE2 | {"importancia_variable"}:
            with self.subTest(tabla=tabla):
                self.assertTrue(rls[tabla])
        politicas = {r[0] for r in self.consulta("SELECT policyname FROM pg_policies WHERE schemaname = 'public'")}
        self.assertEqual(politicas, {f"servicio_{t}" for t in TABLAS_OE2 | {"importancia_variable"}})
        roles = dict(self.consulta("SELECT rolname, rolcanlogin FROM pg_roles WHERE rolname IN ('rol_api', 'rol_pipeline')"))
        self.assertEqual(roles, {"rol_api": False, "rol_pipeline": False})

    def test_permisos_ampliados(self):
        def tiene(rol, tabla, privilegio):
            return self.consulta(f"SELECT has_table_privilege('{rol}', '{tabla}', '{privilegio}')")[0][0]
        for tabla in ("prediccion", "alerta", "ejecucion"):
            self.assertTrue(tiene("rol_api", tabla, "INSERT"))
        for tabla in ("observacion_semanal", "ejecucion", "provincia", "distrito",
                      "semana_epidemiologica", "version_modelo", "importancia_variable"):
            self.assertTrue(tiene("rol_pipeline", tabla, "INSERT"))
        self.assertFalse(tiene("rol_api", "version_modelo", "INSERT"))
        self.assertFalse(tiene("rol_api", "observacion_semanal", "INSERT"))
        columnas = self.consulta("SELECT has_column_privilege('rol_api', 'version_modelo', 'estado', 'UPDATE'), "
                                 "has_column_privilege('rol_api', 'version_modelo', 'metricas', 'UPDATE')")[0]
        self.assertEqual(columnas, (True, False))

    def test_huella_de_ingesta_unica(self):
        # setUp ya creó una ingesta exitosa con huella h1.
        self.assert_rechaza(Ejecucion, r"\"ux_ejecucion_huella_ingesta\"", tipo="ingesta", estado="exitosa",
                            detalle={"huella": "h1"})
        self.insertar(Ejecucion, tipo="ingesta", estado="fallida", detalle={"huella": "h1"})
        self.insertar(Ejecucion, tipo="inferencia", estado="exitosa", detalle={"huella": "h1"})


if __name__ == "__main__":
    unittest.main()
