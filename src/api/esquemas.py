"""Contrato público en español (Tabla 2 del documento OE2); los faltantes son null con motivo."""

from datetime import date, datetime, timezone
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

T = TypeVar("T")
Nivel = Literal["bajo", "medio", "alto", "muy_alto"]


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
    fecha_corte_datos: date | None = Field(description="Último cierre semanal de las fuentes cargadas")
    fecha_actualizacion: datetime | None = Field(description="Fin de la última ejecución exitosa")


class Pagina(Metadatos, Generic[T]):
    elementos: list[T]
    total: int = Field(ge=0, description="Cantidad real de registros que cumplen el filtro")
    pagina: int = Field(ge=1)
    tamano_pagina: int = Field(ge=1)


class DistritoRespuesta(Esquema):
    ubigeo: str = Field(pattern=r"^[0-9]{6}$", description="Código distrital de seis dígitos como texto")
    nombre: str
    ubigeo_provincia: str = Field(pattern=r"^[0-9]{4}$")
    provincia: str
    latitud: float
    longitud: float
    poblacion_censo_2017: int | None
    activo: bool


class SemanaRespuesta(Esquema):
    id_semana: int = Field(description="anio*100 + semana (MMWR, domingo a sábado)")
    anio: int
    semana: int = Field(ge=1, le=53)
    fecha_inicio: date
    fecha_fin: date


class ObservacionRespuesta(Esquema):
    ubigeo: str = Field(pattern=r"^[0-9]{6}$")
    distrito: str
    semana: SemanaRespuesta
    casos_dengue: int | None = Field(description="null = sin dato; 0 = cero notificado")
    brote: bool | None
    umbral_brote_casos: float | None
    temp_media_c: float | None
    temp_min_c: float | None
    temp_max_c: float | None
    precip_total_mm: float | None
    hum_rel_media_pct: float | None
    fuente_casos: Literal["excel_historico", "sala_situacional"]
    estado_cobertura: Literal["verificado", "sin_registro", "pendiente"]


class PrediccionRespuesta(Disponibilidad):
    id_prediccion: int
    ubigeo: str = Field(pattern=r"^[0-9]{6}$")
    distrito: str
    horizonte: int = Field(ge=2, le=4)
    semana_corte: SemanaRespuesta
    semana_objetivo: SemanaRespuesta
    tipo: Literal["vigente", "retrospectiva"] = Field(description="vigente = último corte publicado del horizonte")
    estado: Literal["disponible", "no_disponible"]
    probabilidad_brote: float | None = Field(ge=0, le=1)
    nivel_riesgo: Nivel | None
    nivel_riesgo_etiqueta: str | None
    casos_estimados: float | None = Field(ge=0)
    casos_persistencia: int | None = Field(description="Línea base: casos observados en la semana de corte")
    alerta_modelo: bool | None = Field(description="probabilidad >= umbral F1 de la versión; independiente de la alerta")
    experimental: bool = Field(description="La versión usada no cumple los umbrales de aceptación")
    id_version_clasificador: int | None
    id_version_regresor: int | None
    id_ejecucion: int
    fecha_generacion: datetime


class SerieSemana(Esquema):
    semana: SemanaRespuesta
    casos_dengue: int | None
    brote: bool | None
    observado: bool = Field(description="Hay observación cargada para la semana")
    prediccion: PrediccionRespuesta | None


class SeriesRespuesta(Metadatos):
    ubigeo: str
    distrito: str
    horizonte: int
    desde: date
    hasta: date
    elementos: list[SerieSemana]


class Indicador(Disponibilidad):
    valor: int | float | None


class TableroRespuesta(Metadatos):
    horizonte: int
    semana_corte: SemanaRespuesta | None
    semana_objetivo: SemanaRespuesta | None
    experimental: bool
    distritos: int
    distritos_con_prediccion: int
    niveles_riesgo: dict[str, int]
    alertas_activas: int
    casos_estimados_region: Indicador
    casos_observados_ultima_semana: Indicador
    nota: str


class MapaRiesgoRespuesta(Metadatos):
    """GeoJSON FeatureCollection; los demás campos son miembros extra permitidos por RFC 7946."""
    type: Literal["FeatureCollection"] = "FeatureCollection"
    horizonte: int
    semana_corte: SemanaRespuesta | None
    semana_objetivo: SemanaRespuesta | None
    experimental: bool
    leyenda: list[dict]
    features: list[dict]


class AlertaRespuesta(Esquema):
    id_alerta: int
    ubigeo: str = Field(pattern=r"^[0-9]{6}$")
    distrito: str
    horizonte: int
    nivel: Literal["alto", "muy_alto"]
    nivel_etiqueta: str
    estado: Literal["activa", "retirada"]
    cambio: Literal["nueva", "se_mantiene", "sube_nivel", "baja_nivel"]
    fecha_generacion: datetime
    fecha_retiro: datetime | None
    motivo: str | None
    experimental: bool
    prediccion: PrediccionRespuesta


class ModeloRespuesta(Esquema):
    id_version: int
    codigo: str
    tarea: Literal["clasificacion", "regresion"]
    horizonte: int
    algoritmo: str
    estado: Literal["candidata", "activa", "archivada", "rechazada"]
    cumple_umbrales: bool
    experimental: bool
    umbral_probabilidad: float | None
    mlflow_run_id: str
    fecha_registro: datetime
    fecha_activacion: datetime | None


class ModeloDetalle(ModeloRespuesta):
    variables: list[str]
    hiperparametros: dict
    metricas: dict
    ruta_artefacto: str
    sha256_artefacto: str
    sha256_dataset: str
    reproducibilidad: dict | None


class ModeloEnUso(ModeloRespuesta):
    seleccion: Literal["activa", "experimental"] = Field(
        description="activa = estado 'activa'; experimental = parametro_sistema.seleccion_experimental")


class ModelosActivosRespuesta(Metadatos):
    elementos: list[ModeloEnUso]
    nota: str


class VariablesRespuesta(Metadatos):
    id_version: int
    elementos: list[dict]
    nota: str


class SaludRespuesta(Metadatos):
    estado: str
    conexion_bd: bool
    version_api: str
    ultima_ejecucion: dict | None


class SolicitudInferencia(Esquema):
    horizonte: int = Field(ge=2, le=4, description="2 o 4; 3 responde 409 (sin modelo)")
    id_semana_corte: int | None = Field(default=None, ge=201701, le=209953,
                                        description="Semana de corte (anio*100+semana); por defecto, la última observada")


class InferenciaRespuesta(Esquema):
    id_ejecucion: int
    horizonte: int
    id_semana_corte: int
    id_semana_objetivo: int
    experimental: bool
    seleccion: str | None
    versiones: dict[str, str]
    motivo: str | None
    predicciones: int
    disponibles: int
    no_disponibles: int
    alertas: dict[str, int]
    duracion_segundos: float


class ActivacionRespuesta(Esquema):
    id_ejecucion: int
    activada: ModeloRespuesta
    archivada: ModeloRespuesta | None
    nota: str
