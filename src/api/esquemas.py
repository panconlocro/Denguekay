"""Contrato público en español; los campos faltantes son anulables y explicados."""

from datetime import date, datetime, timezone
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

T = TypeVar("T")


class Esquema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="after")
    @classmethod
    def preservar_utc(cls, valor):
        """SQLite omite la zona al leer instantes que el backend guardó en UTC."""
        return valor.replace(tzinfo=timezone.utc) if isinstance(valor, datetime) and valor.tzinfo is None else valor


class ErrorRespuesta(Esquema):
    """Error homogéneo, sin credenciales ni SQL interno."""
    codigo: str
    mensaje: str
    detalle: list[dict] | dict | str | None = None


class Disponibilidad(Esquema):
    disponible: bool = Field(description="Indica que existe un valor utilizable; cero sí es un valor")
    motivo: str | None = Field(default=None, description="Explicación de la ausencia o restricción")


class Metadatos(Disponibilidad):
    fecha_corte_datos: date | None = Field(description="Último cierre de las fuentes; no es la fecha del servidor")
    fecha_actualizacion: datetime | None


class Pagina(Metadatos, Generic[T]):
    elementos: list[T]
    total: int = Field(ge=0, description="Cantidad real de registros que cumplen el filtro")
    pagina: int = Field(ge=1)
    tamano_pagina: int = Field(ge=1)


class DistritoRespuesta(Metadatos):
    ubigeo: str = Field(pattern=r"^[0-9]{6}$", description="Código distrital de seis dígitos como texto")
    distrito: str
    provincia: str
    lat: float | None
    lon: float | None
    geometria: dict | None
    motivo_geometria: str | None
    fecha_actualizacion: datetime


class DatoSemanal(Metadatos):
    ubigeo: str = Field(pattern=r"^[0-9]{6}$")
    distrito: str
    anio: int
    semana_epi: int = Field(ge=1, le=53, description="Semana MMWR de domingo a sábado")
    semana_inicio: date
    horizonte: int | None = Field(description="Anticipación en semanas; no aplica a una observación")
    tipo_dato: Literal["observado", "pronosticado"]
    estado_validacion: str = Field(description="validado, experimental, sin_modelo o no_aplica")
    version_modelo_id: int | None = Field(description="Versión de clasificación; no aplica a observaciones")


class ObservacionRespuesta(DatoSemanal):
    casos: int | None
    brote: bool | None
    umbral_brote_casos: float | None
    procedencia: str | None


class PrediccionRespuesta(DatoSemanal):
    id: int | None
    tipo: str | None = Field(description="vigente o retrospectiva; vigente respecto del corte de datos")
    origen_cierre: date | None
    probabilidad: float | None = Field(ge=0, le=1)
    nivel_riesgo: str
    casos_estimados: float | None = Field(ge=0)
    casos_persistencia: float | None = Field(ge=0)
    alerta_modelo: bool | None = Field(description="Comparación con umbral F1; independiente de alerta visible")
    alerta_visible: bool | None
    version_regresion_id: int | None
    version_persistencia_id: int | None
    ejecucion_id: int | None
    componentes: dict[str, Disponibilidad]


class ModeloRespuesta(Metadatos):
    id: int
    horizonte: int
    tipo: str
    variante: str
    origen: str
    bloque: str | None
    activa: bool
    estado_validacion: str
    puede_activarse: bool
    artefacto_disponible: bool
    motivo_artefacto: str | None
    umbral_probabilidad: float | None
    entrenamiento_inicio: date
    entrenamiento_corte: date
    fecha_creacion: datetime
    mlflow_run_id: str | None
    device: str
    version_xgboost: str | None
    plataforma: str | None
    nota_activacion: str


class ModeloDetalle(ModeloRespuesta):
    columnas: list[str]
    hiperparametros: dict
    metricas_evaluacion: dict
    criterios_validacion: dict
    detalle_validacion: dict
    particion_temporal: dict
    sha256_gold: str
    sha256_manifiesto: str
    sha256_artefacto: str | None


class SaludRespuesta(Metadatos):
    estado: str
    conexion_bd: bool
    versiones_activas: list[ModeloRespuesta]
    ultima_ejecucion: dict | None


class GeojsonRespuesta(Metadatos):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[dict]


class MapaDistrito(Esquema):
    distrito: DistritoRespuesta
    prediccion: PrediccionRespuesta | None
    disponible: bool
    motivo: str | None
    nivel_riesgo: str


class MapaRespuesta(Metadatos):
    horizonte: int
    semana_objetivo: date | None
    leyenda: list[dict]
    alerta_nivel_minimo: str
    distritos: list[MapaDistrito]


class SerieSemana(Esquema):
    semana_inicio: date
    anio: int
    semana_epi: int
    observado: ObservacionRespuesta
    pronosticado: PrediccionRespuesta


class SeriesRespuesta(Metadatos):
    ubigeo: str
    distrito: str
    horizonte: int
    desde: date | None
    hasta: date | None
    elementos: list[SerieSemana]


class Indicador(Disponibilidad):
    valor: int | float | None


class TableroRespuesta(Metadatos):
    horizonte: int
    semana_objetivo: date | None
    estado_validacion: str
    indicadores: dict[str, Indicador]
    niveles_riesgo: dict[str, int]
    cobertura: dict[str, int]
    nota: str


class AlertaRespuesta(Metadatos):
    id: int
    ubigeo: str
    distrito: str
    horizonte: int
    semana_objetivo: date
    nivel: str | None
    estado: str
    estado_validacion: str
    fecha_generacion: datetime
    fecha_retiro: datetime | None
    motivo_estado: str | None
    indicadores: PrediccionRespuesta


class VariablesRespuesta(Metadatos):
    version_modelo_id: int
    elementos: list[dict]
    nota: str


class ReevaluacionRespuesta(Esquema):
    ejecucion_id: int
    operacion: str
    horizonte: int
    fecha_corte_datos: date
    fecha_actualizacion: datetime
    filas_generadas: int
    versiones_usadas: list[int]
    alertas: dict[str, int]
    duracion_segundos: float
    estado_validacion: str
