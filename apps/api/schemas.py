"""Public contract in Spanish (Table 2 of the OE2 document); missing values are null with a reason.

Schema names and docstrings are part of the OpenAPI contract (decision D2): they stay in Spanish."""

from datetime import date, datetime, timezone
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

T = TypeVar("T")
Nivel = Literal["bajo", "medio", "alto", "muy_alto"]
EstadoPrediccion = Literal["disponible", "no_disponible"]
Posicion = Annotated[list[float], Field(min_length=2, max_length=3, description="[longitud, latitud] en grados (WGS 84)")]


class Esquema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="after")
    @classmethod
    def preservar_utc(cls, value):
        """SQLite drops the zone when reading instants that the backend saved in UTC."""
        return value.replace(tzinfo=timezone.utc) if isinstance(value, datetime) and value.tzinfo is None else value


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
    estado: EstadoPrediccion
    probabilidad_brote: float | None = Field(ge=0, le=1)
    nivel_riesgo: Nivel | None
    nivel_riesgo_etiqueta: str | None
    casos_estimados: float | None = Field(ge=0)
    casos_intervalo_inferior: float | None = Field(ge=0, description="Límite inferior del intervalo de casos; null si el modelo no lo estima")
    casos_intervalo_superior: float | None = Field(ge=0, description="Límite superior del intervalo de casos; null si el modelo no lo estima")
    nivel_intervalo: float | None = Field(gt=0, lt=1, description="Probabilidad nominal del intervalo (0,80)")
    motivo_intervalo: str | None = Field(description="Por qué el intervalo es null")
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


class ElementoLeyenda(Esquema):
    nivel: Nivel | None = Field(description="null = Sin datos")
    etiqueta: str
    desde: float | None = Field(description="Probabilidad mínima del nivel (incluida)")
    hasta: float | None = Field(description="Probabilidad máxima del nivel (excluida, salvo 1)")


class GeometriaPunto(Esquema):
    type: Literal["Point"]
    coordinates: Posicion


class GeometriaPoligono(Esquema):
    type: Literal["Polygon"]
    coordinates: list[list[Posicion]]


class GeometriaMultiPoligono(Esquema):
    type: Literal["MultiPolygon"]
    coordinates: list[list[list[Posicion]]]


Geometria = Annotated[GeometriaPunto | GeometriaPoligono | GeometriaMultiPoligono, Field(discriminator="type")]


class PropiedadesDistrito(Esquema):
    ubigeo: str = Field(pattern=r"^[0-9]{6}$")
    distrito: str
    provincia: str
    estado: EstadoPrediccion
    nivel_riesgo: Nivel | None
    nivel_riesgo_etiqueta: str = Field(description="Etiqueta del nivel o «Sin datos»")
    probabilidad_brote: float | None = Field(ge=0, le=1)
    casos_estimados: float | None = Field(ge=0)
    casos_intervalo_inferior: float | None = Field(ge=0)
    casos_intervalo_superior: float | None = Field(ge=0)
    nivel_intervalo: float | None = Field(gt=0, lt=1)
    experimental: bool
    motivo: str | None


class FeatureDistrito(Esquema):
    type: Literal["Feature"] = "Feature"
    id: str = Field(pattern=r"^[0-9]{6}$", description="ubigeo del distrito")
    geometry: Geometria = Field(description="Hoy Point (centroide); Polygon o MultiPolygon cuando haya límites con licencia")
    properties: PropiedadesDistrito


class MapaRiesgoRespuesta(Metadatos):
    """GeoJSON FeatureCollection; los demás campos son miembros extra permitidos por RFC 7946."""
    type: Literal["FeatureCollection"] = "FeatureCollection"
    horizonte: int
    semana_corte: SemanaRespuesta | None
    semana_objetivo: SemanaRespuesta | None
    experimental: bool
    leyenda: list[ElementoLeyenda]
    features: list[FeatureDistrito]


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
    version_api: str = Field(description="Versión de la aplicación; la del contrato va en X-Version-Contrato")
    ultima_ejecucion: dict | None


class CortesRiesgo(Esquema):
    medio: float = Field(gt=0, lt=1)
    alto: float = Field(gt=0, lt=1)
    muy_alto: float = Field(gt=0, lt=1)


class NivelRiesgo(Esquema):
    nivel: Nivel
    etiqueta: str


class HorizonteConfiguracion(Disponibilidad):
    horizonte: int = Field(ge=2, le=4)
    semana_corte_vigente: SemanaRespuesta | None = Field(description="Último corte publicado; null si no hay")
    experimental: bool = Field(description="El modelo en uso para el horizonte no cumple los umbrales")


class ConfiguracionRespuesta(Metadatos):
    """Todo lo que el frontend necesita para no tener valores en código duro."""
    version_contrato: str
    horizontes_disponibles: list[int] = Field(description="Horizontes con un modelo en uso")
    horizonte_por_defecto: int = Field(ge=2, le=4, description="parametro_sistema.horizonte_por_defecto")
    horizontes: list[HorizonteConfiguracion]
    cortes_riesgo: CortesRiesgo
    niveles: list[NivelRiesgo]
    leyenda: list[ElementoLeyenda]
    experimental: bool
    nota: str


class SolicitudInferencia(Esquema):
    horizonte: int = Field(ge=2, le=4, description="2, 3 o 4; un horizonte sin modelo responde 409")
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
