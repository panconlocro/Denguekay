"""OpenAPI specification with examples taken from the configured database."""

from fastapi.encoders import jsonable_encoder
from fastapi.openapi.utils import get_openapi
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from apps.api import queries as q
from apps.api.schemas import (AlertaRespuesta, DistritoRespuesta, MapaRiesgoRespuesta, ModeloDetalle,
                              ModelosActivosRespuesta, ObservacionRespuesta, Pagina, PrediccionRespuesta,
                              SaludRespuesta, SeriesRespuesta, TableroRespuesta, VariablesRespuesta)
from denguekay.db.models import Alert, District, Prediction, ModelVersion

DESCRIPTIONS = {
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


def real_examples(session, cfg, api_version):
    """Return verifiable examples; if a resource is missing, its example is omitted."""
    examples = {}

    def add(path, data, schema_model):
        examples[path] = jsonable_encoder(schema_model.model_validate(data))

    add("/salud", q.health(session, api_version), SaludRespuesta)
    d = session.scalar(select(District).order_by(District.ubigeo).limit(1))
    if d is None:
        return examples
    add("/distritos", q.paginate(session, select(District).order_by(District.ubigeo), 1, 1,
                                    lambda rows: [q.district_dto(x) for x in rows]), Pagina[DistritoRespuesta])
    add("/distritos/{ubigeo}", q.district_dto(d), DistritoRespuesta)
    add("/observaciones", q.paginate(session, q.observations_query(), 1, 1,
                                        lambda rows: q.observation_dtos(session, rows)), Pagina[ObservacionRespuesta])
    h = session.scalar(select(Prediction.horizonte).order_by(Prediction.horizonte).limit(1))
    if h is not None:
        cutoff = q.current_cutoff(session, h)
        if cutoff is not None:
            add("/predicciones", q.paginate(session, q.predictions_query(h, cutoff), 1, 1,
                                               lambda rows: q.prediction_dtos(session, rows)), Pagina[PrediccionRespuesta])
            add("/series/{ubigeo}", q.series(session, d.ubigeo, h, None, None), SeriesRespuesta)
            add("/tablero/resumen", q.dashboard(session, h), TableroRespuesta)
            risk_map_dto = q.risk_map(session, h)
            add("/mapa-riesgo", {**risk_map_dto, "features": risk_map_dto["features"][:1]}, MapaRiesgoRespuesta)
    add("/modelos/activo", q.models_in_use(session, None, cfg.servir_no_validadas), ModelosActivosRespuesta)
    v = session.scalar(select(ModelVersion).order_by(ModelVersion.id_version).limit(1))
    if v is not None:
        add("/modelos/{identificador}", q.model_dto(v, True), ModeloDetalle)
        add("/modelos/{identificador}/variables", q.variables(session, v.id_version), VariablesRespuesta)
    a = session.scalar(select(Alert).order_by(Alert.id_alerta).limit(1))
    if a is not None:
        add("/alertas", q.paginate(session, q.alerts_query(), 1, 1,
                                      lambda rows: q.alert_dtos(session, rows)), Pagina[AlertaRespuesta])
        add("/alertas/{identificador}", q.alert_dtos(session, [a])[0], AlertaRespuesta)
    return examples


def specification(app):
    """The documentation stays available if the database is down; it does not invent fallback examples."""
    if app.openapi_schema is not None:
        return app.openapi_schema
    schema = get_openapi(title=app.title, version=app.version, description=app.description, routes=app.routes)
    descriptions = {"ubigeo": "Código distrital de seis dígitos como texto",
                     "estado": "Estado de alerta: activa o retirada"}
    for name, schema_model in schema["components"]["schemas"].items():
        if name.startswith("Pagina_"):
            schema_model.setdefault("description", "Listado paginado con disponibilidad, total y corte de datos")
        elif name in DESCRIPTIONS:
            schema_model.setdefault("description", DESCRIPTIONS[name])
    for methods in schema["paths"].values():
        for operation in methods.values():
            for parameter in operation.get("parameters", []):
                if parameter["name"] in descriptions:
                    # Assigned, not setdefault: newer FastAPI versions already copy the Field description of
                    # the Ubigeo alias into path parameters, and the published contract keeps this text.
                    parameter["description"] = descriptions[parameter["name"]]
    factory = app.state.session_factory
    if factory is not None:
        try:
            with factory() as session:
                for path, example in real_examples(session, app.state.cfg, app.version).items():
                    schema["paths"]["/api/v1" + path]["get"]["responses"]["200"]["content"]["application/json"]["examples"] = {
                        "bd_real": {"summary": "Ejemplo obtenido de la base de datos configurada", "value": example}}
        except SQLAlchemyError:
            pass
    app.openapi_schema = schema
    return schema
