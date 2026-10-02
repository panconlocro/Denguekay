"""Esquema portable; el historial de modelos y predicciones no se elimina."""

from datetime import date, datetime, timezone
import re

from sqlalchemy import (Boolean, CheckConstraint, Date, DateTime, Float,
                        ForeignKey, Index, Integer, JSON, MetaData, String,
                        Text, UniqueConstraint, text)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, validates, relationship


def ahora_utc():
    """Instante de actualización, separado del corte epidemiológico."""
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


def restriccion_ubigeo():
    """Verifica seis dígitos también ante inserciones SQL directas."""
    partes = ["length(ubigeo) = 6"] + [
        f"substr(ubigeo, {i}, 1) BETWEEN '0' AND '9'" for i in range(1, 7)]
    return CheckConstraint(" AND ".join(partes), name="ubigeo_seis_digitos")


class ConUbigeo:
    @validates("ubigeo")
    def validar_ubigeo(self, _, valor):
        """Rechaza enteros, códigos cortos y letras sin normalización implícita."""
        if not isinstance(valor, str) or re.fullmatch(r"[0-9]{6}", valor) is None:
            raise ValueError("ubigeo debe ser texto de seis dígitos")
        return valor


class Distrito(ConUbigeo, Base):
    __tablename__ = "distrito"
    __table_args__ = (restriccion_ubigeo(),
                     CheckConstraint("lat BETWEEN -90 AND 90", name="lat_valida"),
                     CheckConstraint("lon BETWEEN -180 AND 180", name="lon_valida"))
    ubigeo: Mapped[str] = mapped_column(String(6), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100))
    provincia: Mapped[str] = mapped_column(String(100))
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    geometria: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    motivo_geometria: Mapped[str | None] = mapped_column(Text)
    fecha_actualizacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora_utc)


class CargaDatos(Base):
    """Trazabilidad e idempotencia de la carga validada de fuentes."""
    __tablename__ = "carga_datos"
    id: Mapped[int] = mapped_column(primary_key=True)
    huella: Mapped[str] = mapped_column(String(64), unique=True)
    hashes_entrada: Mapped[dict] = mapped_column(JSON)
    validacion_gx: Mapped[dict] = mapped_column(JSON)
    fecha_corte_datos: Mapped[date] = mapped_column(Date)
    filas_distritos: Mapped[int] = mapped_column(Integer)
    filas_observaciones: Mapped[int] = mapped_column(Integer)
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora_utc)


class ObservacionSemanal(ConUbigeo, Base):
    __tablename__ = "observacion_semanal"
    __table_args__ = (
        UniqueConstraint("ubigeo", "anio", "semana"), restriccion_ubigeo(),
        CheckConstraint("semana BETWEEN 1 AND 53", name="semana_valida"),
        CheckConstraint("casos >= 0", name="casos_no_negativos"),
        CheckConstraint("umbral_brote_casos >= 0", name="umbral_no_negativo"),
        CheckConstraint("casos IS NOT NULL OR motivo IS NOT NULL", name="faltante_con_motivo"),
        Index("ix_observacion_distrito_fecha", "ubigeo", "semana_inicio"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    ubigeo: Mapped[str] = mapped_column(String(6), ForeignKey("distrito.ubigeo"))
    anio: Mapped[int] = mapped_column(Integer)
    semana: Mapped[int] = mapped_column(Integer)
    semana_inicio: Mapped[date] = mapped_column(Date)
    casos: Mapped[int | None] = mapped_column(Integer)
    brote: Mapped[bool | None] = mapped_column(Boolean)
    umbral_brote_casos: Mapped[float | None] = mapped_column(Float)
    procedencia: Mapped[str] = mapped_column(String(80))
    motivo: Mapped[str | None] = mapped_column(Text)
    carga_id: Mapped[int] = mapped_column(ForeignKey("carga_datos.id"))
    fecha_corte_datos: Mapped[date] = mapped_column(Date)
    fecha_actualizacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora_utc)


class VersionModelo(Base):
    __tablename__ = "version_modelo"
    __table_args__ = (
        CheckConstraint("horizonte BETWEEN 2 AND 4", name="horizonte_valido"),
        CheckConstraint("tipo IN ('clasificacion','regresion','persistencia')", name="tipo_valido"),
        CheckConstraint("umbral_probabilidad BETWEEN 0 AND 1", name="umbral_valido"),
        CheckConstraint("origen IN ('servicio','retrospectiva')", name="origen_valido"),
        CheckConstraint("NOT activa OR (artefacto IS NOT NULL AND origen = 'servicio')", name="activa_con_artefacto"),
        Index("ix_version_horizonte_tipo", "horizonte", "tipo", "activa"),
        Index("uq_version_activa", "horizonte", "tipo", unique=True,
              sqlite_where=text("activa = 1"), postgresql_where=text("activa")),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    huella: Mapped[str] = mapped_column(String(64), unique=True)
    origen: Mapped[str] = mapped_column(String(20), default="servicio")
    bloque: Mapped[str | None] = mapped_column(String(50))
    horizonte: Mapped[int] = mapped_column(Integer)
    tipo: Mapped[str] = mapped_column(String(20))
    variante: Mapped[str] = mapped_column(String(80))
    columnas: Mapped[list] = mapped_column(JSON)
    hiperparametros: Mapped[dict] = mapped_column(JSON)
    umbral_probabilidad: Mapped[float | None] = mapped_column(Float)
    entrenamiento_inicio: Mapped[date] = mapped_column(Date)
    entrenamiento_corte: Mapped[date] = mapped_column(Date)
    metricas_evaluacion: Mapped[dict] = mapped_column(JSON)
    criterios_validacion: Mapped[dict] = mapped_column(JSON, default=dict)
    particion_temporal: Mapped[dict] = mapped_column(JSON)
    mlflow_run_id: Mapped[str | None] = mapped_column(String(64))
    sha256_gold: Mapped[str] = mapped_column(String(64))
    sha256_manifiesto: Mapped[str] = mapped_column(String(64))
    device: Mapped[str] = mapped_column(String(40))
    version_xgboost: Mapped[str | None] = mapped_column(String(40))
    plataforma: Mapped[str | None] = mapped_column(String(200))
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora_utc)
    activa: Mapped[bool] = mapped_column(Boolean, default=False)
    artefacto: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    motivo_artefacto: Mapped[str | None] = mapped_column(Text)

    @property
    def detalle_validacion(self):
        """Resultado siempre derivado de las métricas y política guardadas."""
        from src.validation.validacion_modelo import evaluar_validacion_modelo
        return evaluar_validacion_modelo(self.tipo, self.metricas_evaluacion or {}, self.criterios_validacion or {})

    @property
    def estado_validacion(self):
        return self.detalle_validacion["estado_validacion"]

    @property
    def puede_activarse(self):
        return self.origen == "servicio" and bool(self.artefacto)


class ImportanciaVariable(Base):
    __tablename__ = "importancia_variable"
    __table_args__ = (UniqueConstraint("version_modelo_id", "variable"),
                     CheckConstraint("importancia >= 0 AND rango >= 1", name="importancia_valida"))
    id: Mapped[int] = mapped_column(primary_key=True)
    version_modelo_id: Mapped[int] = mapped_column(ForeignKey("version_modelo.id"))
    variable: Mapped[str] = mapped_column(String(100))
    importancia: Mapped[float] = mapped_column(Float)
    rango: Mapped[int] = mapped_column(Integer)


class EjecucionPrediccion(Base):
    __tablename__ = "ejecucion_prediccion"
    id: Mapped[int] = mapped_column(primary_key=True)
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora_utc)
    fecha_corte_datos: Mapped[date] = mapped_column(Date)
    versiones_usadas: Mapped[list] = mapped_column(JSON)
    hashes_entrada: Mapped[dict] = mapped_column(JSON)
    huella: Mapped[str] = mapped_column(String(64), unique=True)
    estado: Mapped[str] = mapped_column(String(20))
    filas_generadas: Mapped[int] = mapped_column(Integer)
    duracion_segundos: Mapped[float] = mapped_column(Float)
    motivo: Mapped[str | None] = mapped_column(Text)
    resumen: Mapped[dict] = mapped_column(JSON, default=dict)


class Prediccion(ConUbigeo, Base):
    __tablename__ = "prediccion"
    __table_args__ = (
        UniqueConstraint("ejecucion_id", "ubigeo", "horizonte", "semana_inicio", "tipo"),
        restriccion_ubigeo(),
        CheckConstraint("horizonte BETWEEN 2 AND 4", name="horizonte_valido"),
        CheckConstraint("semana BETWEEN 1 AND 53", name="semana_valida"),
        CheckConstraint("probabilidad BETWEEN 0 AND 1", name="probabilidad_valida"),
        CheckConstraint("casos_estimados >= 0", name="casos_no_negativos"),
        CheckConstraint("origen_cierre < semana_inicio", name="origen_anterior_objetivo"),
        CheckConstraint("tipo IN ('vigente','retrospectiva')", name="tipo_valido"),
        Index("ix_prediccion_horizonte_fecha", "horizonte", "semana_inicio"),
        Index("ix_prediccion_ubigeo_horizonte", "ubigeo", "horizonte"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    ubigeo: Mapped[str] = mapped_column(String(6), ForeignKey("distrito.ubigeo"))
    horizonte: Mapped[int] = mapped_column(Integer)
    anio: Mapped[int] = mapped_column(Integer)
    semana: Mapped[int] = mapped_column(Integer)
    semana_inicio: Mapped[date] = mapped_column(Date)
    origen_cierre: Mapped[date] = mapped_column(Date)
    probabilidad: Mapped[float | None] = mapped_column(Float)
    nivel_riesgo: Mapped[str | None] = mapped_column(String(20))
    casos_estimados: Mapped[float | None] = mapped_column(Float)
    casos_persistencia: Mapped[float | None] = mapped_column(Float)
    alerta_modelo: Mapped[bool | None] = mapped_column(Boolean)
    tipo: Mapped[str] = mapped_column(String(20))
    version_clasificacion_id: Mapped[int | None] = mapped_column(ForeignKey("version_modelo.id"))
    version_regresion_id: Mapped[int | None] = mapped_column(ForeignKey("version_modelo.id"))
    version_persistencia_id: Mapped[int | None] = mapped_column(ForeignKey("version_modelo.id"))
    ejecucion_id: Mapped[int] = mapped_column(ForeignKey("ejecucion_prediccion.id"))
    caracteristicas: Mapped[dict] = mapped_column(JSON)
    motivo: Mapped[str | None] = mapped_column(Text)
    fecha_actualizacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora_utc)
    version_clasificacion: Mapped[VersionModelo | None] = relationship(foreign_keys=[version_clasificacion_id])
    version_regresion: Mapped[VersionModelo | None] = relationship(foreign_keys=[version_regresion_id])

    @property
    def estado_validacion(self):
        """Una predicción conjunta solo se valida si ambos componentes cumplen."""
        versiones = (self.version_clasificacion, self.version_regresion)
        if any(v is None for v in versiones):
            return "experimental"
        return "validado" if all(v.estado_validacion == "validado" for v in versiones) else "experimental"


class Alerta(ConUbigeo, Base):
    __tablename__ = "alerta"
    __table_args__ = (
        UniqueConstraint("prediccion_id"), restriccion_ubigeo(),
        CheckConstraint("estado IN ('activa','retirada')", name="estado_valido"),
        Index("ix_alerta_horizonte_estado", "horizonte", "estado"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    prediccion_id: Mapped[int] = mapped_column(ForeignKey("prediccion.id"))
    ubigeo: Mapped[str] = mapped_column(String(6), ForeignKey("distrito.ubigeo"))
    horizonte: Mapped[int] = mapped_column(Integer)
    semana_inicio: Mapped[date] = mapped_column(Date)
    nivel: Mapped[str] = mapped_column(String(20))
    estado: Mapped[str] = mapped_column(String(20))
    fecha_generacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora_utc)
    fecha_retiro: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    motivo: Mapped[str | None] = mapped_column(Text)
    prediccion: Mapped[Prediccion] = relationship()

    @property
    def estado_validacion(self):
        return self.prediccion.estado_validacion


class ActivacionModelo(Base):
    __tablename__ = "activacion_modelo"
    id: Mapped[int] = mapped_column(primary_key=True)
    version_anterior_id: Mapped[int | None] = mapped_column(ForeignKey("version_modelo.id"))
    version_nueva_id: Mapped[int] = mapped_column(ForeignKey("version_modelo.id"))
    ejecucion_id: Mapped[int] = mapped_column(ForeignKey("ejecucion_prediccion.id"))
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora_utc)
    motivo: Mapped[str] = mapped_column(Text)
