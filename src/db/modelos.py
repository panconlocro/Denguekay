"""Esquema del almacén operacional según el documento OE2 (Anexo B, ddl_oe2.sql).

Portable: en PostgreSQL usa ENUM nativos, jsonb, identity y CHECK con regex;
en SQLite (solo pruebas) los ENUM son CHECK y el formato se valida en el ORM.
La autoridad del esquema es la migración ``0003_oe2``; este módulo la refleja.
"""

from datetime import date, datetime, timezone
import re

from sqlalchemy import (BigInteger, Boolean, CHAR, CheckConstraint, Date, DateTime,
                        Enum, ForeignKey, Identity, Index, Integer, JSON, MetaData,
                        Numeric, SmallInteger, String, Text, UniqueConstraint, func, text)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, validates


def ahora_utc():
    """Instante con zona UTC; en SQLite evita fechas sin zona."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Nombres deterministas para constraints y migraciones."""
    metadata = MetaData(naming_convention={
        "ix": "ix_%(table_name)s_%(column_0_name)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    })


# Valores de los ENUM del DDL. El orden se conserva: en PostgreSQL define el orden del tipo.
FUENTE_CASOS = ("excel_historico", "sala_situacional")
COBERTURA = ("verificado", "sin_registro", "pendiente")
TAREA = ("clasificacion", "regresion")
ESTADO_VERSION = ("candidata", "activa", "archivada", "rechazada")
TIPO_EJECUCION = ("ingesta", "inferencia", "reentrenamiento", "mantenimiento")
ESTADO_EJECUCION = ("en_curso", "exitosa", "fallida")
NIVEL_RIESGO = ("bajo", "medio", "alto", "muy_alto")
ESTADO_PREDICCION = ("disponible", "no_disponible")
ESTADO_ALERTA = ("activa", "retirada")
CAMBIO_ALERTA = ("nueva", "se_mantiene", "sube_nivel", "baja_nivel")
HORIZONTES = (2, 3, 4)


def enum(valores, nombre):
    """ENUM nativo en PostgreSQL; CHECK en SQLite. Rechaza textos ajenos en Python."""
    return Enum(*valores, name=nombre, native_enum=True, create_constraint=True,
                validate_strings=True)


JSONB_PORTABLE = JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql")
# SQLite solo autoincrementa con INTEGER PRIMARY KEY.
BIGINT_ID = BigInteger().with_variant(Integer(), "sqlite")


def solo_postgresql(condicion, nombre):
    """CHECK con sintaxis propia de PostgreSQL (regex, aritmética de fechas)."""
    return CheckConstraint(condicion, name=nombre).ddl_if(dialect="postgresql")


def solo_sqlite(condicion, nombre):
    return CheckConstraint(condicion, name=nombre).ddl_if(dialect="sqlite")


def digitos_sqlite(columna, n):
    """Equivalente portable de ``columna ~ '^[0-9]{n}$'`` para SQLite."""
    partes = [f"length({columna}) = {n}"] + [
        f"substr({columna}, {i}, 1) BETWEEN '0' AND '9'" for i in range(1, n + 1)]
    return " AND ".join(partes)


def restricciones_digitos(columna, n, nombre):
    return (solo_postgresql(f"{columna} ~ '^[0-9]{{{n}}}$'", nombre),
            solo_sqlite(digitos_sqlite(columna, n), nombre))


def _validar_digitos(valor, n, campo):
    if not isinstance(valor, str) or re.fullmatch(rf"[0-9]{{{n}}}", valor) is None:
        raise ValueError(f"{campo} debe ser texto de {'seis' if n == 6 else 'cuatro'} dígitos")
    return valor


class ConUbigeo:
    @validates("ubigeo")
    def validar_ubigeo(self, _, valor):
        """Rechaza enteros, códigos cortos y letras sin normalización implícita."""
        return _validar_digitos(valor, 6, "ubigeo")


class Provincia(Base):
    __tablename__ = "provincia"
    __table_args__ = restricciones_digitos("ubigeo_provincia", 4, "ubigeo_provincia_formato")
    ubigeo_provincia: Mapped[str] = mapped_column(CHAR(4), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80))

    @validates("ubigeo_provincia")
    def validar_codigo(self, _, valor):
        return _validar_digitos(valor, 4, "ubigeo_provincia")


class Distrito(ConUbigeo, Base):
    __tablename__ = "distrito"
    __table_args__ = (
        *restricciones_digitos("ubigeo", 6, "ubigeo_formato"),
        CheckConstraint("latitud BETWEEN -6.5 AND -3.5", name="latitud_piura"),
        CheckConstraint("longitud BETWEEN -81.5 AND -79.0", name="longitud_piura"),
        CheckConstraint("poblacion_censo_2017 > 0", name="poblacion_positiva"),
    )
    ubigeo: Mapped[str] = mapped_column(CHAR(6), primary_key=True)
    ubigeo_provincia: Mapped[str] = mapped_column(CHAR(4), ForeignKey("provincia.ubigeo_provincia"))
    nombre: Mapped[str] = mapped_column(String(80))
    latitud: Mapped[float] = mapped_column(Numeric(9, 6, asdecimal=False))
    longitud: Mapped[float] = mapped_column(Numeric(9, 6, asdecimal=False))
    poblacion_censo_2017: Mapped[int | None] = mapped_column(Integer)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    provincia: Mapped[Provincia] = relationship()


class SemanaEpidemiologica(Base):
    """Calendario MMWR; ``id_semana = anio*100 + semana``."""
    __tablename__ = "semana_epidemiologica"
    __table_args__ = (
        UniqueConstraint("anio", "semana"),
        CheckConstraint("semana BETWEEN 1 AND 53", name="semana_valida"),
        solo_postgresql("fecha_fin = fecha_inicio + 6", "fecha_fin_valida"),
        solo_sqlite("fecha_fin = date(fecha_inicio, '+6 days')", "fecha_fin_valida"),
    )
    id_semana: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    anio: Mapped[int] = mapped_column(SmallInteger)
    semana: Mapped[int] = mapped_column(SmallInteger)
    fecha_inicio: Mapped[date] = mapped_column(Date)
    fecha_fin: Mapped[date] = mapped_column(Date)
    temporada: Mapped[int] = mapped_column(SmallInteger)


class Ejecucion(Base):
    """Cargas, inferencias, reentrenamientos y mantenimiento; evidencia en ``detalle``."""
    __tablename__ = "ejecucion"
    __table_args__ = (
        # Extensión aprobada: idempotencia de cargas por la huella guardada en el detalle.
        Index("ux_ejecucion_huella_ingesta", text("(detalle ->> 'huella')"), unique=True,
              postgresql_where=text("tipo = 'ingesta' AND estado = 'exitosa'")).ddl_if(dialect="postgresql"),
    )
    id_ejecucion: Mapped[int] = mapped_column(BIGINT_ID, Identity(always=True), primary_key=True)
    tipo: Mapped[str] = mapped_column(enum(TIPO_EJECUCION, "tipo_ejecucion_t"))
    estado: Mapped[str] = mapped_column(enum(ESTADO_EJECUCION, "estado_ejecucion_t"),
                                        default="en_curso", server_default="en_curso")
    id_semana_corte: Mapped[int | None] = mapped_column(ForeignKey("semana_epidemiologica.id_semana"))
    inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora_utc,
                                             server_default=func.now())
    fin: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    detalle: Mapped[dict | None] = mapped_column(JSONB_PORTABLE)
    mensaje_error: Mapped[str | None] = mapped_column(Text)


Index("ix_ejecucion_tipo_inicio", Ejecucion.tipo, Ejecucion.inicio.desc())



class ObservacionSemanal(ConUbigeo, Base):
    __tablename__ = "observacion_semanal"
    __table_args__ = (
        CheckConstraint("casos_dengue >= 0", name="casos_no_negativos"),
        CheckConstraint("umbral_brote_casos >= 0", name="umbral_no_negativo"),
        CheckConstraint("precip_total_mm BETWEEN 0 AND 1500", name="precipitacion_valida"),
        CheckConstraint("hum_rel_media_pct BETWEEN 0 AND 100", name="humedad_valida"),
        CheckConstraint("temp_min_c <= temp_media_c AND temp_media_c <= temp_max_c",
                        name="temperaturas_ordenadas"),
        Index("ix_obs_semana", "id_semana"),
    )
    ubigeo: Mapped[str] = mapped_column(CHAR(6), ForeignKey("distrito.ubigeo"), primary_key=True)
    id_semana: Mapped[int] = mapped_column(ForeignKey("semana_epidemiologica.id_semana"), primary_key=True)
    casos_dengue: Mapped[int | None] = mapped_column(Integer)  # NULL = sin dato; 0 = cero real
    umbral_brote_casos: Mapped[float | None] = mapped_column(Numeric(10, 2, asdecimal=False))
    brote: Mapped[bool | None] = mapped_column(Boolean)
    temp_media_c: Mapped[float | None] = mapped_column(Numeric(5, 2, asdecimal=False))
    temp_min_c: Mapped[float | None] = mapped_column(Numeric(5, 2, asdecimal=False))
    temp_max_c: Mapped[float | None] = mapped_column(Numeric(5, 2, asdecimal=False))
    precip_total_mm: Mapped[float | None] = mapped_column(Numeric(7, 2, asdecimal=False))
    hum_rel_media_pct: Mapped[float | None] = mapped_column(Numeric(5, 2, asdecimal=False))
    fuente_casos: Mapped[str] = mapped_column(enum(FUENTE_CASOS, "fuente_casos_t"))
    estado_cobertura: Mapped[str] = mapped_column(enum(COBERTURA, "cobertura_t"))
    fecha_extraccion: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    id_ejecucion: Mapped[int] = mapped_column(ForeignKey("ejecucion.id_ejecucion"))


class VersionModelo(Base):
    __tablename__ = "version_modelo"
    __table_args__ = (
        CheckConstraint("horizonte IN (2, 3, 4)", name="horizonte_valido"),
        CheckConstraint("umbral_probabilidad BETWEEN 0 AND 1", name="umbral_valido"),
        CheckConstraint("estado <> 'activa' OR cumple_umbrales", name="activa_cumple_umbrales"),
        Index("ux_version_activa", "tarea", "horizonte", unique=True,
              postgresql_where=text("estado = 'activa'"), sqlite_where=text("estado = 'activa'")),
    )
    id_version: Mapped[int] = mapped_column(Integer, Identity(always=True), primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20), unique=True)
    tarea: Mapped[str] = mapped_column(enum(TAREA, "tarea_t"))
    horizonte: Mapped[int] = mapped_column(SmallInteger)
    algoritmo: Mapped[str] = mapped_column(String(40))
    variables: Mapped[list] = mapped_column(JSONB_PORTABLE)
    hiperparametros: Mapped[dict] = mapped_column(JSONB_PORTABLE)
    metricas: Mapped[dict] = mapped_column(JSONB_PORTABLE)
    umbral_probabilidad: Mapped[float | None] = mapped_column(Numeric(4, 3, asdecimal=False))
    cumple_umbrales: Mapped[bool] = mapped_column(Boolean)
    estado: Mapped[str] = mapped_column(enum(ESTADO_VERSION, "estado_version_t"),
                                        default="candidata", server_default="candidata")
    mlflow_run_id: Mapped[str] = mapped_column(String(64))
    ruta_artefacto: Mapped[str] = mapped_column(Text)
    sha256_artefacto: Mapped[str] = mapped_column(CHAR(64))
    sha256_dataset: Mapped[str] = mapped_column(CHAR(64))
    fecha_registro: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora_utc,
                                                     server_default=func.now())
    fecha_activacion: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Extensión: device, versión de XGBoost, plataforma, partición temporal y fechas de entrenamiento.
    reproducibilidad: Mapped[dict | None] = mapped_column(JSONB_PORTABLE)

    @validates("horizonte")
    def validar_horizonte(self, _, valor):
        if valor not in HORIZONTES or isinstance(valor, bool):
            raise ValueError("horizonte debe ser 2, 3 o 4")
        return valor


class ImportanciaVariable(Base):
    """Extensión aprobada (HU0008-4): importancia gain del booster de servicio."""
    __tablename__ = "importancia_variable"
    __table_args__ = (UniqueConstraint("id_version", "variable"),
                     CheckConstraint("importancia >= 0 AND rango >= 1", name="importancia_valida"))
    id_importancia: Mapped[int] = mapped_column(Integer, Identity(always=True), primary_key=True)
    id_version: Mapped[int] = mapped_column(ForeignKey("version_modelo.id_version"))
    variable: Mapped[str] = mapped_column(String(100))
    importancia: Mapped[float] = mapped_column(Numeric(asdecimal=False))
    rango: Mapped[int] = mapped_column(Integer)


class Prediccion(ConUbigeo, Base):
    __tablename__ = "prediccion"
    __table_args__ = (
        UniqueConstraint("ubigeo", "id_semana_corte", "horizonte"),
        CheckConstraint("horizonte IN (2, 3, 4)", name="horizonte_valido"),
        CheckConstraint("probabilidad_brote BETWEEN 0 AND 1", name="probabilidad_valida"),
        CheckConstraint("casos_estimados >= 0", name="casos_no_negativos"),
        CheckConstraint(
            "(estado = 'disponible' AND probabilidad_brote IS NOT NULL AND nivel_riesgo IS NOT NULL)"
            " OR (estado = 'no_disponible' AND probabilidad_brote IS NULL AND nivel_riesgo IS NULL"
            " AND motivo_no_disponible IS NOT NULL)", name="estado_coherente"),
        Index("ix_pred_objetivo", "id_semana_objetivo", "horizonte"),
    )
    id_prediccion: Mapped[int] = mapped_column(BIGINT_ID, Identity(always=True), primary_key=True)
    ubigeo: Mapped[str] = mapped_column(CHAR(6), ForeignKey("distrito.ubigeo"))
    id_semana_corte: Mapped[int] = mapped_column(ForeignKey("semana_epidemiologica.id_semana"))
    id_semana_objetivo: Mapped[int] = mapped_column(ForeignKey("semana_epidemiologica.id_semana"))
    horizonte: Mapped[int] = mapped_column(SmallInteger)
    probabilidad_brote: Mapped[float | None] = mapped_column(Numeric(5, 4, asdecimal=False))
    nivel_riesgo: Mapped[str | None] = mapped_column(enum(NIVEL_RIESGO, "nivel_riesgo_t"))
    casos_estimados: Mapped[float | None] = mapped_column(Numeric(10, 2, asdecimal=False))
    estado: Mapped[str] = mapped_column(enum(ESTADO_PREDICCION, "estado_prediccion_t"))
    motivo_no_disponible: Mapped[str | None] = mapped_column(Text)
    id_version_clasificador: Mapped[int | None] = mapped_column(ForeignKey("version_modelo.id_version"))
    id_version_regresor: Mapped[int | None] = mapped_column(ForeignKey("version_modelo.id_version"))
    id_ejecucion: Mapped[int] = mapped_column(ForeignKey("ejecucion.id_ejecucion"))
    fecha_generacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora_utc,
                                                       server_default=func.now())
    version_clasificador: Mapped[VersionModelo | None] = relationship(foreign_keys=[id_version_clasificador])
    version_regresor: Mapped[VersionModelo | None] = relationship(foreign_keys=[id_version_regresor])

    @validates("horizonte")
    def validar_horizonte(self, _, valor):
        if valor not in HORIZONTES or isinstance(valor, bool):
            raise ValueError("horizonte debe ser 2, 3 o 4")
        return valor


class Alerta(ConUbigeo, Base):
    __tablename__ = "alerta"
    __table_args__ = (
        UniqueConstraint("id_prediccion"),
        CheckConstraint("nivel IN ('alto', 'muy_alto')", name="nivel_alerta"),
        CheckConstraint("estado = 'activa' OR fecha_retiro IS NOT NULL", name="retiro_con_fecha"),
        Index("ix_alerta_estado", "estado", "nivel"),
    )
    id_alerta: Mapped[int] = mapped_column(BIGINT_ID, Identity(always=True), primary_key=True)
    id_prediccion: Mapped[int] = mapped_column(ForeignKey("prediccion.id_prediccion"))
    ubigeo: Mapped[str] = mapped_column(CHAR(6), ForeignKey("distrito.ubigeo"))
    nivel: Mapped[str] = mapped_column(enum(NIVEL_RIESGO, "nivel_riesgo_t"))
    estado: Mapped[str] = mapped_column(enum(ESTADO_ALERTA, "estado_alerta_t"),
                                        default="activa", server_default="activa")
    cambio: Mapped[str] = mapped_column(enum(CAMBIO_ALERTA, "cambio_alerta_t"))
    fecha_generacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora_utc,
                                                       server_default=func.now())
    fecha_retiro: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    motivo: Mapped[str | None] = mapped_column(Text)  # Extensión aprobada: explica el retiro.
    prediccion: Mapped[Prediccion] = relationship()


class ParametroSistema(Base):
    """Parámetros que leen la API y el pipeline; ``config.yaml`` solo siembra."""
    __tablename__ = "parametro_sistema"
    clave: Mapped[str] = mapped_column(String(60), primary_key=True)
    valor: Mapped[dict] = mapped_column(JSONB_PORTABLE)
    descripcion: Mapped[str] = mapped_column(Text)
    fecha_actualizacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora_utc,
                                                          server_default=func.now())


# Semillas del DDL; ``bloque`` en umbrales_aceptacion es una corrección aprobada del documento.
PARAMETROS_INICIALES = (
    {"clave": "regla_brote",
     "valor": {"anios_previos": 5, "k_desviaciones": 1.5, "minimo_casos": 2},
     "descripcion": "Umbral = media de la misma semana en 5 años previos + k DE; mínimo de casos"},
    {"clave": "cortes_riesgo",
     "valor": {"medio": 0.25, "alto": 0.50, "muy_alto": 0.75},
     "descripcion": "Cortes de probabilidad para el nivel de riesgo"},
    {"clave": "umbrales_aceptacion",
     "valor": {"recall": 0.80, "precision": 0.60, "f1": 0.70, "razon_error_base": 0.85,
               "bloque": "temporada_2024"},
     "descripcion": "Criterios para promover un modelo"},
)
