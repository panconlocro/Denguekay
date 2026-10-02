"""Especificación OpenAPI con ejemplos obtenidos de la BD configurada."""

from fastapi.encoders import jsonable_encoder
from fastapi.openapi.utils import get_openapi
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from src.api import consultas as q
from src.api.esquemas import (AlertaRespuesta, DistritoRespuesta, MapaRiesgoRespuesta, ModeloDetalle,
                              ModelosActivosRespuesta, ObservacionRespuesta, Pagina, PrediccionRespuesta,
                              SaludRespuesta, SeriesRespuesta, TableroRespuesta, VariablesRespuesta)
from src.db.modelos import Alerta, Distrito, Prediccion, VersionModelo

DESCRIPCIONES = {
    "Disponibilidad": "Distingue valores existentes, incluidos ceros, de valores ausentes con motivo",
    "Metadatos": "Disponibilidad, corte de las fuentes y fin de la última ejecución exitosa",
    "DistritoRespuesta": "Catálogo distrital real con provincia, centroide y población censal 2017",
    "SemanaRespuesta": "Semana epidemiológica MMWR (id_semana = anio*100 + semana)",
    "ObservacionRespuesta": "Casos, etiqueta de brote y clima observados; un faltante conserva null",
    "PrediccionRespuesta": "Probabilidad, nivel de riesgo, magnitud, línea base y trazabilidad del modelo",
    "SeriesRespuesta": "Semanas continuas con observado y predicción anulables",
    "TableroRespuesta": "Indicadores del corte vigente; la suma regional es null si falta un distrito",
    "MapaRiesgoRespuesta": "GeoJSON FeatureCollection de centroides con nivel de riesgo o Sin datos",
    "AlertaRespuesta": "Alerta alto/muy_alto con cambio respecto del corte anterior y su predicción",
    "ModeloEnUso": "Versión en uso (activa o selección experimental) por tarea y horizonte",
    "ModeloDetalle": "Métricas por bloque, variables, hashes y reproducibilidad de una versión",
    "VariablesRespuesta": "Importancias gain reales; no constituyen relaciones causales",
    "InferenciaRespuesta": "Resumen de la ejecución de inferencia confirmada en la BD",
    "ActivacionRespuesta": "Activación auditada como ejecución de mantenimiento",
}


def ejemplos_reales(sesion, cfg, version_api):
    """Devuelve ejemplos verificables; si falta un recurso, omite su ejemplo."""
    ejemplos = {}

    def agregar(ruta, datos, esquema):
        ejemplos[ruta] = jsonable_encoder(esquema.model_validate(datos))

    agregar("/salud", q.salud(sesion, version_api), SaludRespuesta)
    d = sesion.scalar(select(Distrito).order_by(Distrito.ubigeo).limit(1))
    if d is None:
        return ejemplos
    agregar("/distritos", q.paginar(sesion, select(Distrito).order_by(Distrito.ubigeo), 1, 1,
                                    lambda filas: [q.distrito_dto(x) for x in filas]), Pagina[DistritoRespuesta])
    agregar("/distritos/{ubigeo}", q.distrito_dto(d), DistritoRespuesta)
    agregar("/observaciones", q.paginar(sesion, q.consulta_observaciones(), 1, 1,
                                        lambda filas: q.observacion_dtos(sesion, filas)), Pagina[ObservacionRespuesta])
    h = sesion.scalar(select(Prediccion.horizonte).order_by(Prediccion.horizonte).limit(1))
    if h is not None:
        corte = q.corte_vigente(sesion, h)
        if corte is not None:
            agregar("/predicciones", q.paginar(sesion, q.consulta_predicciones(h, corte), 1, 1,
                                               lambda filas: q.prediccion_dtos(sesion, filas)), Pagina[PrediccionRespuesta])
            agregar("/series/{ubigeo}", q.series(sesion, d.ubigeo, h, None, None), SeriesRespuesta)
            agregar("/tablero/resumen", q.tablero(sesion, h), TableroRespuesta)
            mapa = q.mapa_riesgo(sesion, h)
            agregar("/mapa-riesgo", {**mapa, "features": mapa["features"][:1]}, MapaRiesgoRespuesta)
    agregar("/modelos/activo", q.modelos_en_uso(sesion, None, cfg.servir_no_validadas), ModelosActivosRespuesta)
    v = sesion.scalar(select(VersionModelo).order_by(VersionModelo.id_version).limit(1))
    if v is not None:
        agregar("/modelos/{identificador}", q.modelo_dto(v, True), ModeloDetalle)
        agregar("/modelos/{identificador}/variables", q.variables(sesion, v.id_version), VariablesRespuesta)
    a = sesion.scalar(select(Alerta).order_by(Alerta.id_alerta).limit(1))
    if a is not None:
        agregar("/alertas", q.paginar(sesion, q.consulta_alertas(), 1, 1,
                                      lambda filas: q.alerta_dtos(sesion, filas)), Pagina[AlertaRespuesta])
        agregar("/alertas/{identificador}", q.alerta_dtos(sesion, [a])[0], AlertaRespuesta)
    return ejemplos


def especificacion(app):
    """La documentación sigue disponible si la BD cae; no inventa ejemplos de respaldo."""
    if app.openapi_schema is not None:
        return app.openapi_schema
    schema = get_openapi(title=app.title, version=app.version, description=app.description, routes=app.routes)
    descripciones = {"ubigeo": "Código distrital de seis dígitos como texto",
                     "estado": "Estado de alerta: activa o retirada"}
    for nombre, esquema in schema["components"]["schemas"].items():
        if nombre.startswith("Pagina_"):
            esquema.setdefault("description", "Listado paginado con disponibilidad, total y corte de datos")
        elif nombre in DESCRIPCIONES:
            esquema.setdefault("description", DESCRIPCIONES[nombre])
    for metodos in schema["paths"].values():
        for operacion in metodos.values():
            for parametro in operacion.get("parameters", []):
                if parametro["name"] in descripciones:
                    parametro.setdefault("description", descripciones[parametro["name"]])
    fabrica = app.state.fabrica_sesiones
    if fabrica is not None:
        try:
            with fabrica() as sesion:
                for ruta, ejemplo in ejemplos_reales(sesion, app.state.cfg, app.version).items():
                    schema["paths"]["/api/v1" + ruta]["get"]["responses"]["200"]["content"]["application/json"]["examples"] = {
                        "bd_real": {"summary": "Ejemplo obtenido de la base de datos configurada", "value": ejemplo}}
        except SQLAlchemyError:
            pass
    app.openapi_schema = schema
    return schema
