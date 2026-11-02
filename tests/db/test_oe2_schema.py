"""Esquema OE2: concordancia ORM ↔ migración, restricciones del DDL y seguridad.

Cada caso se ejecuta en SQLite temporal. Si existe DENGUEKAY_PG_PRUEBAS_URL
(BD PostgreSQL desechable), los mismos casos y los de RLS/roles se repiten
en PostgreSQL; al terminar, esa BD vuelve a la revisión base.
"""

from datetime import date, datetime, timezone
import json
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

from backend_support import migrar, url_pg_pruebas
from denguekay.db.models import (Alert, Base, District, Run, VariableImportance,
                            WeeklyObservation, SystemParameter, Prediction, Province,
                            EpiWeek, ModelVersion)
from denguekay.db.session import make_engine, transaction

TABLAS_OE2 = {"provincia", "distrito", "semana_epidemiologica", "observacion_semanal",
              "version_modelo", "ejecucion", "prediccion", "alerta", "parametro_sistema"}
TABLAS_0002 = {"carga_datos", "distrito", "ejecucion_prediccion", "version_modelo",
               "activacion_modelo", "importancia_variable", "observacion_semanal",
               "prediccion", "alerta"}
# Orden de borrado que respeta las claves foráneas; parametro_sistema conserva sus semillas.
ORDEN_LIMPIEZA = (Alert, Prediction, VariableImportance, ModelVersion, WeeklyObservation,
                  Run, EpiWeek, District, Province)
SHA = "a" * 64
# Motivos esperados en el mensaje del motor (SQLite y PostgreSQL).
FK = r"foreign key"
UNICA = r"unique|duplicate key"


def bajar_una_revision(motor, destino="0002_serving"):
    """alembic downgrade hasta ``destino`` (por defecto, la revisión anterior a 0003_oe2)."""
    from alembic import command
    from alembic.config import Config
    from denguekay.config.paths import ALEMBIC_CONFIG
    config = Config(str(ALEMBIC_CONFIG))
    config.attributes["motor"] = motor
    command.downgrade(config, destino)


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
        with transaction(self.motor) as s:
            s.add(Province(ubigeo_provincia="2001", nombre="Piura"))
            s.flush()
            s.add(District(ubigeo="200101", ubigeo_provincia="2001", nombre="Piura",
                           latitud=-5.194, longitud=-80.632, poblacion_censo_2017=158495))
            for id_semana, inicio in ((202551, date(2025, 12, 14)), (202552, date(2025, 12, 21)),
                                      (202553, date(2025, 12, 28))):
                s.add(EpiWeek(id_semana=id_semana, anio=2025, semana=id_semana % 100,
                                           fecha_inicio=inicio, fecha_fin=date.fromordinal(inicio.toordinal() + 6),
                                           temporada=2026))
            s.flush()
            ejecucion = Run(tipo="ingesta", estado="exitosa", detalle={"huella": "h1"})
            s.add(ejecucion)
            s.flush()
            self.id_ejecucion = ejecucion.id_ejecucion

    def tearDown(self):
        with transaction(self.motor) as s:
            for modelo in ORDEN_LIMPIEZA:
                s.execute(delete(modelo))

    # --- utilidades -------------------------------------------------------

    def insertar(self, modelo, **fila):
        with transaction(self.motor) as s:
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
        consulta = insertar(Prediction.__table__).values(**fila)
        actualizables = {c: consulta.excluded[c] for c in fila if c not in ("ubigeo", "id_semana_corte", "horizonte")}
        with transaction(self.motor) as s:
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
        with transaction(self.motor) as s:
            valores = {p.clave: p.valor for p in s.scalars(select(SystemParameter))}
        # Semillas del DDL (0003_oe2), el horizonte por defecto (0004_v1), el nivel del intervalo (0005_v1) y la
        # fila vacía de la selección experimental (0006_v1: la fija la publicación, sin datos de modelos).
        self.assertEqual(set(valores), {"regla_brote", "cortes_riesgo", "umbrales_aceptacion", "horizonte_por_defecto",
                                        "nivel_intervalo_casos", "seleccion_experimental"})
        self.assertEqual(valores["seleccion_experimental"], {})
        self.assertEqual(valores["horizonte_por_defecto"], {"horizonte": 4})
        self.assertEqual(valores["nivel_intervalo_casos"], {"nivel": 0.80})
        self.assertEqual(valores["regla_brote"], {"anios_previos": 5, "k_desviaciones": 1.5, "minimo_casos": 2})
        self.assertEqual(valores["cortes_riesgo"], {"medio": 0.25, "alto": 0.50, "muy_alto": 0.75})
        self.assertEqual(valores["umbrales_aceptacion"]["bloque"], "temporada_2024")
        self.assertEqual(valores["umbrales_aceptacion"]["razon_error_base"], 0.85)

    # --- CHECK, uno por caso inválido --------------------------------------

    def test_checks_de_catalogo_y_calendario(self):
        casos = [
            (Province, "ubigeo_provincia_formato", {"ubigeo_provincia": "20a1", "nombre": "X"}),
            (District, "ubigeo_formato", {"ubigeo": "2001a1", "ubigeo_provincia": "2001", "nombre": "X",
                                          "latitud": -5, "longitud": -80}),
            (District, "latitud_piura", {"ubigeo": "200102", "ubigeo_provincia": "2001", "nombre": "X",
                                         "latitud": -12.0, "longitud": -80}),
            (District, "longitud_piura", {"ubigeo": "200103", "ubigeo_provincia": "2001", "nombre": "X",
                                          "latitud": -5, "longitud": -77.0}),
            (District, "poblacion_positiva", {"ubigeo": "200104", "ubigeo_provincia": "2001", "nombre": "X",
                                              "latitud": -5, "longitud": -80, "poblacion_censo_2017": 0}),
            (District, FK, {"ubigeo": "200105", "ubigeo_provincia": "9999", "nombre": "X",
                            "latitud": -5, "longitud": -80}),
            (EpiWeek, "semana_valida", {"id_semana": 202554, "anio": 2025, "semana": 54,
                "fecha_inicio": date(2026, 1, 4), "fecha_fin": date(2026, 1, 10), "temporada": 2026}),
            (EpiWeek, "fecha_fin_valida", {"id_semana": 202601, "anio": 2026, "semana": 1,
                "fecha_inicio": date(2026, 1, 4), "fecha_fin": date(2026, 1, 11), "temporada": 2026}),
            (EpiWeek, UNICA, {"id_semana": 202599, "anio": 2025, "semana": 52,
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
                self.assert_rechaza(WeeklyObservation, motivo, **self.fila_observacion(**cambio))
        self.insertar(WeeklyObservation, **self.fila_observacion(casos_dengue=None))
        self.assert_rechaza(WeeklyObservation, UNICA, **self.fila_observacion())  # PK (ubigeo, id_semana)

    def test_observacion_conserva_cero_y_nulo(self):
        self.insertar(WeeklyObservation, **self.fila_observacion(casos_dengue=0))
        self.insertar(WeeklyObservation, **self.fila_observacion(id_semana=202551, casos_dengue=None))
        with transaction(self.motor) as s:
            casos = dict(s.execute(select(WeeklyObservation.id_semana, WeeklyObservation.casos_dengue)).all())
        self.assertEqual(casos, {202552: 0, 202551: None})

    def test_enum_invalido_rechazado_por_la_bd(self):
        fila = self.fila_observacion(fuente_casos="otra_fuente")
        columnas = ", ".join(fila)
        marcadores = ", ".join(f":{c}" for c in fila)
        with self.assertRaises((IntegrityError, DBAPIError)) as error, transaction(self.motor) as s:
            s.execute(text(f"INSERT INTO observacion_semanal ({columnas}) VALUES ({marcadores})"), fila)
        self.assertRegex(str(error.exception.orig), r"fuente_casos_t")
        with self.assertRaises(StatementError):
            self.insertar(WeeklyObservation, **self.fila_observacion(estado_cobertura="desconocido"))

    def test_checks_de_version_modelo(self):
        casos = [("horizonte_valido", {"horizonte": 5}), ("umbral_valido", {"umbral_probabilidad": 1.5}),
                 ("activa_cumple_umbrales", {"estado": "activa", "cumple_umbrales": False})]
        for i, (motivo, cambio) in enumerate(casos):
            with self.subTest(cambio=cambio):
                self.assert_rechaza(ModelVersion, motivo, **fila_version(codigo=f"v{i}", **cambio))
        id_version = self.insertar(ModelVersion, **fila_version())
        self.assert_rechaza(ModelVersion, UNICA, **fila_version())  # codigo único
        for cambio in ({"importancia": -0.1}, {"rango": 0}):
            with self.subTest(importancia=cambio):
                self.assert_rechaza(VariableImportance, "importancia_valida", **{
                    "id_version": id_version, "variable": "casos_lag_4", "importancia": 1.0, "rango": 1, **cambio})

    def test_una_sola_version_activa_por_tarea_y_horizonte(self):
        self.insertar(ModelVersion, **fila_version(codigo="a", estado="activa", cumple_umbrales=True))
        self.assert_rechaza(ModelVersion, UNICA, **fila_version(codigo="b", estado="activa", cumple_umbrales=True))
        # Otra tarea, otro horizonte y versiones no activas sí conviven.
        self.insertar(ModelVersion, **fila_version(codigo="c", tarea="regresion", estado="activa",
                                                    cumple_umbrales=True, umbral_probabilidad=None))
        self.insertar(ModelVersion, **fila_version(codigo="d", horizonte=2, estado="activa", cumple_umbrales=True))
        self.insertar(ModelVersion, **fila_version(codigo="e", estado="archivada"))
        self.insertar(ModelVersion, **fila_version(codigo="f", estado="archivada"))

    def test_checks_de_prediccion(self):
        casos = [("horizonte_valido", {"horizonte": 1}), ("probabilidad_valida", {"probabilidad_brote": 1.2}),
                 ("casos_no_negativos", {"casos_estimados": -1.0}), (FK, {"id_semana_objetivo": 209901}),
                 (FK, {"ubigeo": "200199"})]
        for motivo, cambio in casos:
            with self.subTest(cambio=cambio):
                self.assert_rechaza(Prediction, motivo, **self.fila_prediccion(**cambio))

    def test_coherencia_disponible_no_disponible(self):
        invalidas = [
            {"nivel_riesgo": None},
            {"probabilidad_brote": None},
            {"estado": "no_disponible", "motivo_no_disponible": "sin modelo"},
            {"estado": "no_disponible", "probabilidad_brote": None, "nivel_riesgo": None},
        ]
        for cambio in invalidas:
            with self.subTest(cambio=cambio):
                self.assert_rechaza(Prediction, "estado_coherente", **self.fila_prediccion(**cambio))
        self.insertar(Prediction, **self.fila_prediccion(
            estado="no_disponible", probabilidad_brote=None, nivel_riesgo=None, casos_estimados=None,
            motivo_no_disponible="sin modelo para h=3", horizonte=3))
        self.insertar(Prediction, **self.fila_prediccion())

    def test_upsert_de_prediccion_por_clave_del_documento(self):
        self.upsert(self.fila_prediccion())
        self.upsert(self.fila_prediccion(probabilidad_brote=0.8, nivel_riesgo="muy_alto"))
        with transaction(self.motor) as s:
            filas = s.execute(select(Prediction.probabilidad_brote, Prediction.nivel_riesgo)).all()
        self.assertEqual(len(filas), 1)
        self.assertAlmostEqual(filas[0][0], 0.8)
        self.assertEqual(filas[0][1], "muy_alto")
        self.assert_rechaza(Prediction, UNICA, **self.fila_prediccion())  # insert simple duplicado
        self.upsert(self.fila_prediccion(horizonte=4))  # otra clave: nueva fila
        with transaction(self.motor) as s:
            self.assertEqual(s.scalar(select(func.count()).select_from(Prediction)), 2)

    def test_alerta_solo_alto_o_muy_alto_y_retiro_con_fecha(self):
        id_prediccion = self.insertar(Prediction, **self.fila_prediccion())
        base = {"id_prediccion": id_prediccion, "ubigeo": "200101", "nivel": "alto", "cambio": "nueva"}
        for nivel in ("bajo", "medio"):
            with self.subTest(nivel=nivel):
                self.assert_rechaza(Alert, "nivel_alerta", **{**base, "nivel": nivel})
        self.assert_rechaza(Alert, "retiro_con_fecha", **{**base, "estado": "retirada"})
        self.insertar(Alert, **base)
        self.assert_rechaza(Alert, UNICA, **{**base, "nivel": "muy_alto"})  # una alerta por predicción

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
                District(ubigeo=valor)
        with self.assertRaisesRegex(ValueError, "cuatro dígitos"):
            Province(ubigeo_provincia=2001)
        for modelo in (ModelVersion, Prediction):
            with self.subTest(modelo=modelo.__name__), self.assertRaisesRegex(ValueError, "2, 3 o 4"):
                modelo(horizonte=5)


class TestEsquemaOE2SQLite(EsquemaOE2, unittest.TestCase):
    @classmethod
    def crear_motor(cls):
        from sqlalchemy.engine import URL
        cls.carpeta = tempfile.TemporaryDirectory()
        return make_engine(URL.create("sqlite", database=str(Path(cls.carpeta.name) / "oe2.db")))

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

    def test_migracion_0004_solo_datos_y_reversible(self):
        """0004_v1 siembra horizonte_por_defecto y su downgrade lo quita sin tocar el esquema."""
        consulta = text("SELECT valor FROM parametro_sistema WHERE clave = 'horizonte_por_defecto'")
        tablas = set(inspect(self.motor).get_table_names())
        bajar_una_revision(self.motor, "0003_oe2")
        with self.motor.connect() as conexion:
            self.assertIsNone(conexion.execute(consulta).first())
        self.assertEqual(set(inspect(self.motor).get_table_names()), tablas)
        migrar(self.motor)
        with self.motor.connect() as conexion:
            self.assertEqual(json.loads(conexion.execute(consulta).scalar_one()), {"horizonte": 4})

    def test_migracion_0005_intervalo_y_reversible(self):
        """0005_v1 agrega el intervalo con su CHECK y el nivel; el downgrade los quita."""
        columnas = lambda: {c["name"] for c in inspect(self.motor).get_columns("prediccion")}
        intervalo = {"casos_intervalo_inferior", "casos_intervalo_superior"}
        self.assertLessEqual(intervalo, columnas())
        with self.motor.connect() as conexion:
            sql = conexion.execute(text("SELECT sql FROM sqlite_master WHERE name = 'prediccion'")).scalar_one()
        self.assertIn("ck_prediccion_intervalo_coherente", sql)
        bajar_una_revision(self.motor, "0004_v1")
        self.assertFalse(intervalo & columnas())
        with self.motor.connect() as conexion:
            self.assertIsNone(conexion.execute(text(
                "SELECT valor FROM parametro_sistema WHERE clave = 'nivel_intervalo_casos'")).first())
        migrar(self.motor)
        self.assertLessEqual(intervalo, columnas())

    def test_migracion_0006_fila_vacia_y_reversible(self):
        """0006_v1 crea la fila vacía; el downgrade solo la borra si sigue vacía (una selección fijada se conserva)."""
        consulta = text("SELECT valor FROM parametro_sistema WHERE clave = 'seleccion_experimental'")
        bajar_una_revision(self.motor, "0005_v1")
        with self.motor.connect() as conexion:
            self.assertIsNone(conexion.execute(consulta).first())
        migrar(self.motor)
        with transaction(self.motor) as s:
            s.get(SystemParameter, "seleccion_experimental").valor = {"2": {"clasificacion": "a", "regresion": "b"}}
        bajar_una_revision(self.motor, "0005_v1")
        with self.motor.connect() as conexion:
            self.assertEqual(json.loads(conexion.execute(consulta).scalar_one())["2"]["regresion"], "b")
        migrar(self.motor)
        with transaction(self.motor) as s:
            s.get(SystemParameter, "seleccion_experimental").valor = {}


@unittest.skipUnless(url_pg_pruebas(), "Sin DENGUEKAY_PG_PRUEBAS_URL: se omiten las pruebas en PostgreSQL")
class TestEsquemaOE2PostgreSQL(EsquemaOE2, unittest.TestCase):
    @classmethod
    def crear_motor(cls):
        motor = make_engine(url_pg_pruebas())
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
        self.assert_rechaza(Run, r"generated always|cannot insert", id_ejecucion=999, tipo="ingesta")

    def test_check_regex_de_ubigeo(self):
        # CHAR(6) rellena con espacios un código corto; la regex lo rechaza.
        self.assert_rechaza(District, "ubigeo_formato", ubigeo="20011", ubigeo_provincia="2001", nombre="X",
                            latitud=-5, longitud=-80)

    def test_rls_politicas_y_roles(self):
        rls = dict(self.consulta("SELECT relname, relrowsecurity FROM pg_class WHERE relkind = 'r' "
                                 "AND relnamespace = 'public'::regnamespace"))
        for tabla in TABLAS_OE2 | {"importancia_variable"}:
            with self.subTest(tabla=tabla):
                self.assertTrue(rls[tabla])
        politicas = {r[0] for r in self.consulta("SELECT policyname FROM pg_policies WHERE schemaname = 'public'")}
        self.assertEqual(politicas, {f"servicio_{t}" for t in TABLAS_OE2 | {"importancia_variable"}}
                         | {"pipeline_seleccion_experimental"})
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

    def test_pipeline_solo_actualiza_la_seleccion_experimental(self):
        """0006_v1: rol_pipeline actualiza la fila seleccion_experimental y ninguna otra de parametro_sistema."""
        puede = self.consulta("SELECT rolsuper OR pg_has_role(current_user, 'rol_pipeline', 'SET') "
                              "FROM pg_roles WHERE rolname = current_user")[0][0]
        if not puede:
            self.skipTest("El usuario de la BD de pruebas no puede asumir rol_pipeline (en el CI es superusuario)")
        nuevo = '{"2": {"clasificacion": "v2-clf-h2-1", "regresion": "v2-reg-h2-1"}}'
        with self.motor.connect() as conexion:
            transaccion = conexion.begin()
            try:
                conexion.execute(text("SET LOCAL ROLE rol_pipeline"))
                filas = conexion.execute(text(f"UPDATE parametro_sistema SET valor = '{nuevo}'::jsonb "
                                              "WHERE clave = 'seleccion_experimental'")).rowcount
                self.assertEqual(filas, 1)
                # El RLS filtra las demás filas: la actualización no toca ninguna.
                filas = conexion.execute(text("UPDATE parametro_sistema SET valor = '{}'::jsonb "
                                              "WHERE clave = 'cortes_riesgo'")).rowcount
                self.assertEqual(filas, 0)
                with self.assertRaisesRegex(Exception, "row-level security|permission denied"):
                    with conexion.begin_nested():
                        conexion.execute(text("UPDATE parametro_sistema SET clave = 'otra' "
                                              "WHERE clave = 'seleccion_experimental'"))
                with self.assertRaisesRegex(Exception, "permission denied"):
                    with conexion.begin_nested():
                        conexion.execute(text("INSERT INTO parametro_sistema (clave, valor) VALUES ('x', '{}'::jsonb)"))
            finally:
                transaccion.rollback()
        def tiene(rol, columna):
            return self.consulta(f"SELECT has_column_privilege('{rol}', 'parametro_sistema', '{columna}', 'UPDATE')")[0][0]
        self.assertEqual((tiene("rol_pipeline", "valor"), tiene("rol_pipeline", "clave"), tiene("rol_api", "valor")),
                         (True, False, False))

    def test_huella_de_ingesta_unica(self):
        # setUp ya creó una ingesta exitosa con huella h1.
        self.assert_rechaza(Run, r"\"ux_ejecucion_huella_ingesta\"", tipo="ingesta", estado="exitosa",
                            detalle={"huella": "h1"})
        self.insertar(Run, tipo="ingesta", estado="fallida", detalle={"huella": "h1"})
        self.insertar(Run, tipo="inferencia", estado="exitosa", detalle={"huella": "h1"})


if __name__ == "__main__":
    unittest.main()
