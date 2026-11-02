"""Schema of the operational store according to the OE2 document (Annex B, ddl_oe2.sql).

Portable: on PostgreSQL it uses native ENUMs, jsonb, identity and CHECK with regex;
on SQLite (tests only) the ENUMs are CHECKs and the format is validated in the ORM.
The authority of the schema is the Alembic migrations (``0003_oe2`` and later); this module mirrors them.
"""

from datetime import date, datetime, timezone
import re

from sqlalchemy import (BigInteger, Boolean, CHAR, CheckConstraint, Date, DateTime, Double,
                        Enum, ForeignKey, Identity, Index, Integer, JSON, MetaData,
                        Numeric, SmallInteger, String, Text, UniqueConstraint, func, text)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, validates


def utc_now():
    """Instant with the UTC zone; on SQLite it avoids naive dates."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Deterministic names for constraints and migrations."""
    metadata = MetaData(naming_convention={
        "ix": "ix_%(table_name)s_%(column_0_name)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    })


# ENUM values of the DDL. The order is kept: on PostgreSQL it defines the type's order.
CASE_SOURCE = ("excel_historico", "sala_situacional")
COVERAGE = ("verificado", "sin_registro", "pendiente")
TASK = ("clasificacion", "regresion")
VERSION_STATUS = ("candidata", "activa", "archivada", "rechazada")
RUN_TYPE = ("ingesta", "inferencia", "reentrenamiento", "mantenimiento")
RUN_STATUS = ("en_curso", "exitosa", "fallida")
RISK_LEVEL = ("bajo", "medio", "alto", "muy_alto")
PREDICTION_STATUS = ("disponible", "no_disponible")
ALERT_STATUS = ("activa", "retirada")
ALERT_CHANGE = ("nueva", "se_mantiene", "sube_nivel", "baja_nivel")
HORIZONS = (2, 3, 4)


def enum(values, name):
    """Native ENUM on PostgreSQL; CHECK on SQLite. Rejects foreign texts in Python."""
    return Enum(*values, name=name, native_enum=True, create_constraint=True,
                validate_strings=True)


JSONB_PORTABLE = JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql")
# SQLite only autoincrements with INTEGER PRIMARY KEY.
BIGINT_ID = BigInteger().with_variant(Integer(), "sqlite")


def postgresql_only(condition, name):
    """CHECK with PostgreSQL-specific syntax (regex, date arithmetic)."""
    return CheckConstraint(condition, name=name).ddl_if(dialect="postgresql")


def sqlite_only(condition, name):
    return CheckConstraint(condition, name=name).ddl_if(dialect="sqlite")


def sqlite_digits(column, n):
    """Portable SQLite equivalent of ``column ~ '^[0-9]{n}$'``."""
    parts = [f"length({column}) = {n}"] + [
        f"substr({column}, {i}, 1) BETWEEN '0' AND '9'" for i in range(1, n + 1)]
    return " AND ".join(parts)


def digit_constraints(column, n, name):
    return (postgresql_only(f"{column} ~ '^[0-9]{{{n}}}$'", name),
            sqlite_only(sqlite_digits(column, n), name))


def _validate_digits(value, n, field):
    if not isinstance(value, str) or re.fullmatch(rf"[0-9]{{{n}}}", value) is None:
        raise ValueError(f"{field} debe ser texto de {'seis' if n == 6 else 'cuatro'} dígitos")
    return value


class WithUbigeo:
    @validates("ubigeo")
    def validate_ubigeo(self, _, value):
        """Reject integers, short codes and letters without implicit normalisation."""
        return _validate_digits(value, 6, "ubigeo")


class Province(Base):
    __tablename__ = "provincia"
    __table_args__ = digit_constraints("ubigeo_provincia", 4, "ubigeo_provincia_formato")
    ubigeo_provincia: Mapped[str] = mapped_column(CHAR(4), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80))

    @validates("ubigeo_provincia")
    def validate_code(self, _, value):
        return _validate_digits(value, 4, "ubigeo_provincia")


class District(WithUbigeo, Base):
    __tablename__ = "distrito"
    __table_args__ = (
        *digit_constraints("ubigeo", 6, "ubigeo_formato"),
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
    provincia: Mapped[Province] = relationship()


class EpiWeek(Base):
    """MMWR calendar; ``id_semana = anio*100 + semana``."""
    __tablename__ = "semana_epidemiologica"
    __table_args__ = (
        UniqueConstraint("anio", "semana"),
        CheckConstraint("semana BETWEEN 1 AND 53", name="semana_valida"),
        postgresql_only("fecha_fin = fecha_inicio + 6", "fecha_fin_valida"),
        sqlite_only("fecha_fin = date(fecha_inicio, '+6 days')", "fecha_fin_valida"),
    )
    id_semana: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    anio: Mapped[int] = mapped_column(SmallInteger)
    semana: Mapped[int] = mapped_column(SmallInteger)
    fecha_inicio: Mapped[date] = mapped_column(Date)
    fecha_fin: Mapped[date] = mapped_column(Date)
    temporada: Mapped[int] = mapped_column(SmallInteger)


class Run(Base):
    """Loads, inferences, retrainings and maintenance; evidence in ``detalle``."""
    __tablename__ = "ejecucion"
    __table_args__ = (
        # Approved extension: idempotent loads through the fingerprint saved in the detail.
        Index("ux_ejecucion_huella_ingesta", text("(detalle ->> 'huella')"), unique=True,
              postgresql_where=text("tipo = 'ingesta' AND estado = 'exitosa'")).ddl_if(dialect="postgresql"),
    )
    id_ejecucion: Mapped[int] = mapped_column(BIGINT_ID, Identity(always=True), primary_key=True)
    tipo: Mapped[str] = mapped_column(enum(RUN_TYPE, "tipo_ejecucion_t"))
    estado: Mapped[str] = mapped_column(enum(RUN_STATUS, "estado_ejecucion_t"),
                                        default="en_curso", server_default="en_curso")
    id_semana_corte: Mapped[int | None] = mapped_column(ForeignKey("semana_epidemiologica.id_semana"))
    inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now,
                                             server_default=func.now())
    fin: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    detalle: Mapped[dict | None] = mapped_column(JSONB_PORTABLE)
    mensaje_error: Mapped[str | None] = mapped_column(Text)


Index("ix_ejecucion_tipo_inicio", Run.tipo, Run.inicio.desc())



class WeeklyObservation(WithUbigeo, Base):
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
    casos_dengue: Mapped[int | None] = mapped_column(Integer)  # NULL = no data; 0 = a real zero
    umbral_brote_casos: Mapped[float | None] = mapped_column(Numeric(10, 2, asdecimal=False))
    brote: Mapped[bool | None] = mapped_column(Boolean)
    temp_media_c: Mapped[float | None] = mapped_column(Numeric(5, 2, asdecimal=False))
    temp_min_c: Mapped[float | None] = mapped_column(Numeric(5, 2, asdecimal=False))
    temp_max_c: Mapped[float | None] = mapped_column(Numeric(5, 2, asdecimal=False))
    precip_total_mm: Mapped[float | None] = mapped_column(Numeric(7, 2, asdecimal=False))
    # double precision since 0005_v1 (decision M5); SQLite keeps its declared NUMERIC, which stores the full REAL.
    hum_rel_media_pct: Mapped[float | None] = mapped_column(
        Double().with_variant(Numeric(5, 2, asdecimal=False), "sqlite"))
    fuente_casos: Mapped[str] = mapped_column(enum(CASE_SOURCE, "fuente_casos_t"))
    estado_cobertura: Mapped[str] = mapped_column(enum(COVERAGE, "cobertura_t"))
    fecha_extraccion: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    id_ejecucion: Mapped[int] = mapped_column(ForeignKey("ejecucion.id_ejecucion"))


class ModelVersion(Base):
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
    tarea: Mapped[str] = mapped_column(enum(TASK, "tarea_t"))
    horizonte: Mapped[int] = mapped_column(SmallInteger)
    algoritmo: Mapped[str] = mapped_column(String(40))
    variables: Mapped[list] = mapped_column(JSONB_PORTABLE)
    hiperparametros: Mapped[dict] = mapped_column(JSONB_PORTABLE)
    metricas: Mapped[dict] = mapped_column(JSONB_PORTABLE)
    umbral_probabilidad: Mapped[float | None] = mapped_column(Numeric(4, 3, asdecimal=False))
    cumple_umbrales: Mapped[bool] = mapped_column(Boolean)
    estado: Mapped[str] = mapped_column(enum(VERSION_STATUS, "estado_version_t"),
                                        default="candidata", server_default="candidata")
    mlflow_run_id: Mapped[str] = mapped_column(String(64))
    ruta_artefacto: Mapped[str] = mapped_column(Text)
    sha256_artefacto: Mapped[str] = mapped_column(CHAR(64))
    sha256_dataset: Mapped[str] = mapped_column(CHAR(64))
    fecha_registro: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now,
                                                     server_default=func.now())
    fecha_activacion: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Extension: device, XGBoost version, platform, time partition and training dates.
    reproducibilidad: Mapped[dict | None] = mapped_column(JSONB_PORTABLE)

    @validates("horizonte")
    def validate_horizon(self, _, value):
        if value not in HORIZONS or isinstance(value, bool):
            raise ValueError("horizonte debe ser 2, 3 o 4")
        return value


class VariableImportance(Base):
    """Approved extension (HU0008-4): gain importance of the serving booster."""
    __tablename__ = "importancia_variable"
    __table_args__ = (UniqueConstraint("id_version", "variable"),
                     CheckConstraint("importancia >= 0 AND rango >= 1", name="importancia_valida"))
    id_importancia: Mapped[int] = mapped_column(Integer, Identity(always=True), primary_key=True)
    id_version: Mapped[int] = mapped_column(ForeignKey("version_modelo.id_version"))
    variable: Mapped[str] = mapped_column(String(100))
    importancia: Mapped[float] = mapped_column(Numeric(asdecimal=False))
    rango: Mapped[int] = mapped_column(Integer)


class Prediction(WithUbigeo, Base):
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
        CheckConstraint(
            "(casos_intervalo_inferior IS NULL AND casos_intervalo_superior IS NULL)"
            " OR (estado = 'disponible' AND casos_intervalo_inferior IS NOT NULL AND casos_intervalo_superior IS NOT NULL"
            " AND casos_intervalo_inferior >= 0 AND casos_intervalo_inferior <= casos_intervalo_superior)",
            name="intervalo_coherente"),
        Index("ix_pred_objetivo", "id_semana_objetivo", "horizonte"),
    )
    id_prediccion: Mapped[int] = mapped_column(BIGINT_ID, Identity(always=True), primary_key=True)
    ubigeo: Mapped[str] = mapped_column(CHAR(6), ForeignKey("distrito.ubigeo"))
    id_semana_corte: Mapped[int] = mapped_column(ForeignKey("semana_epidemiologica.id_semana"))
    id_semana_objetivo: Mapped[int] = mapped_column(ForeignKey("semana_epidemiologica.id_semana"))
    horizonte: Mapped[int] = mapped_column(SmallInteger)
    probabilidad_brote: Mapped[float | None] = mapped_column(Numeric(5, 4, asdecimal=False))
    nivel_riesgo: Mapped[str | None] = mapped_column(enum(RISK_LEVEL, "nivel_riesgo_t"))
    casos_estimados: Mapped[float | None] = mapped_column(Numeric(10, 2, asdecimal=False))
    # Extension (decision C3, migration 0005_v1): case interval at parametro_sistema.nivel_intervalo_casos.
    casos_intervalo_inferior: Mapped[float | None] = mapped_column(Numeric(10, 2, asdecimal=False))
    casos_intervalo_superior: Mapped[float | None] = mapped_column(Numeric(10, 2, asdecimal=False))
    estado: Mapped[str] = mapped_column(enum(PREDICTION_STATUS, "estado_prediccion_t"))
    motivo_no_disponible: Mapped[str | None] = mapped_column(Text)
    id_version_clasificador: Mapped[int | None] = mapped_column(ForeignKey("version_modelo.id_version"))
    id_version_regresor: Mapped[int | None] = mapped_column(ForeignKey("version_modelo.id_version"))
    id_ejecucion: Mapped[int] = mapped_column(ForeignKey("ejecucion.id_ejecucion"))
    fecha_generacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now,
                                                       server_default=func.now())
    version_clasificador: Mapped[ModelVersion | None] = relationship(foreign_keys=[id_version_clasificador])
    version_regresor: Mapped[ModelVersion | None] = relationship(foreign_keys=[id_version_regresor])

    @validates("horizonte")
    def validate_horizon(self, _, value):
        if value not in HORIZONS or isinstance(value, bool):
            raise ValueError("horizonte debe ser 2, 3 o 4")
        return value


class Alert(WithUbigeo, Base):
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
    nivel: Mapped[str] = mapped_column(enum(RISK_LEVEL, "nivel_riesgo_t"))
    estado: Mapped[str] = mapped_column(enum(ALERT_STATUS, "estado_alerta_t"),
                                        default="activa", server_default="activa")
    cambio: Mapped[str] = mapped_column(enum(ALERT_CHANGE, "cambio_alerta_t"))
    fecha_generacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now,
                                                       server_default=func.now())
    fecha_retiro: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    motivo: Mapped[str | None] = mapped_column(Text)  # Approved extension: explains the withdrawal.
    prediccion: Mapped[Prediction] = relationship()


class SystemParameter(Base):
    """Parameters read by the API and the pipeline; ``config.yaml`` only seeds them."""
    __tablename__ = "parametro_sistema"
    clave: Mapped[str] = mapped_column(String(60), primary_key=True)
    valor: Mapped[dict] = mapped_column(JSONB_PORTABLE)
    descripcion: Mapped[str] = mapped_column(Text)
    fecha_actualizacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now,
                                                          server_default=func.now())


# DDL seeds; ``bloque`` in umbrales_aceptacion is an approved correction of the document.
INITIAL_PARAMETERS = (
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
