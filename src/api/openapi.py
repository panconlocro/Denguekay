"""Especificación OpenAPI con ejemplos obtenidos de la BD configurada."""

from datetime import timedelta

from fastapi.encoders import jsonable_encoder
from fastapi.openapi.utils import get_openapi
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from src.api import consultas as q
from src.api.esquemas import (AlertaRespuesta, DistritoRespuesta, GeojsonRespuesta, MapaRespuesta, ModeloDetalle,
    ModeloRespuesta, ObservacionRespuesta, Pagina, PrediccionRespuesta, ReevaluacionRespuesta,
    SaludRespuesta, SeriesRespuesta, TableroRespuesta, VariablesRespuesta)
from src.db.modelos import Alerta, Distrito, EjecucionPrediccion, ObservacionSemanal, Prediccion, VersionModelo


def ejemplos_reales(sesion, cfg):
    """Devuelve ejemplos verificables; si falta un recurso, omite su ejemplo."""
    ejemplos = {}
    def agregar(ruta, datos, esquema=None, metodo="get"):
        if esquema is not None:
            datos = esquema.model_validate(datos)
        ejemplos[ruta, metodo] = jsonable_encoder(datos)
    agregar("/salud", q.salud(sesion), SaludRespuesta)
    d = sesion.scalar(select(Distrito).order_by(Distrito.ubigeo).limit(1))
    if d:
        agregar("/distritos", q.paginar(sesion, select(Distrito).order_by(Distrito.ubigeo), 1, 1,
            lambda f: q.distrito_dto(f, q.metadatos(sesion))), Pagina[DistritoRespuesta])
        agregar("/distritos/{ubigeo}", q.distrito_dto(d, q.metadatos(sesion)), DistritoRespuesta)
        agregar("/distritos/geojson", q.geojson(sesion), GeojsonRespuesta)
    o = sesion.scalar(select(ObservacionSemanal).order_by(ObservacionSemanal.id).limit(1))
    if o:
        agregar("/observaciones", q.paginar(sesion, select(ObservacionSemanal).order_by(ObservacionSemanal.id), 1, 1,
            lambda f: q.observacion_dto(f, q.distrito_existente(sesion, f.ubigeo), q.metadatos(sesion))), Pagina[ObservacionRespuesta])
    v = sesion.scalar(select(VersionModelo).where(VersionModelo.activa.is_(True),
        VersionModelo.tipo == "clasificacion").order_by(VersionModelo.horizonte, VersionModelo.id).limit(1))
    if v:
        agregar("/modelos", q.paginar(sesion, select(VersionModelo).order_by(VersionModelo.id), 1, 1,
            lambda f: q.modelo_dto(f, q.metadatos(sesion))), Pagina[ModeloRespuesta])
        agregar("/modelos/{identificador}", q.modelo_dto(v, q.metadatos(sesion), True), ModeloDetalle)
        agregar("/modelos/{identificador}/variables", q.variables(sesion, v.id), VariablesRespuesta)
        consulta, fuente = q.consulta_predicciones(sesion, v.horizonte)
        agregar("/predicciones", q.paginar(sesion, consulta, 1, 1, lambda p: q.prediccion_dto(p,
            q.distrito_existente(sesion, p.ubigeo), cfg, q.metadatos(sesion), fuente)), Pagina[PrediccionRespuesta])
        agregar("/mapa", q.mapa(sesion, v.horizonte, cfg), MapaRespuesta)
        agregar("/tablero", q.tablero(sesion, v.horizonte, cfg), TableroRespuesta)
        p = sesion.scalar(consulta.limit(1))
        if p:
            agregar("/series/{ubigeo}", q.series(sesion, p.ubigeo, p.horizonte,
                p.semana_inicio - timedelta(weeks=2), p.semana_inicio, cfg), SeriesRespuesta)
    a = sesion.scalar(select(Alerta).order_by(Alerta.id).limit(1))
    if a:
        agregar("/alertas", q.paginar(sesion, q.consulta_alertas(None, None, None), 1, 1,
            lambda fila: q.alerta_dto(sesion, fila, cfg)), Pagina[AlertaRespuesta])
        agregar("/alertas/{identificador}", q.alerta_dto(sesion, a, cfg), AlertaRespuesta)
    for operacion, ruta in (("reevaluacion_api", "/predicciones/recalcular"), ("activacion_api", "/modelos/{identificador}/activar")):
        # Filtrado portable en Python: no depende de operadores JSON de PostgreSQL.
        for e in sesion.scalars(select(EjecucionPrediccion).where(EjecucionPrediccion.estado == "completada").order_by(EjecucionPrediccion.id.desc())):
            if e.resumen.get("operacion") == operacion:
                agregar(ruta, e.resumen, ReevaluacionRespuesta, "post")
                break
    return ejemplos


def especificacion(app):
    """La documentación sigue disponible si la BD cae; no inventa ejemplos de respaldo."""
    if app.openapi_schema is not None:
        return app.openapi_schema
    schema = get_openapi(title=app.title, version=app.version,
                         description=app.description, routes=app.routes)
    descripciones = {"ubigeo": "Código distrital de seis dígitos como texto",
                    "estado": "Estado de alerta: activa o retirada"}
    esquemas = {
        "Disponibilidad": "Distingue valores existentes, incluidos ceros, de valores ausentes con motivo",
        "Metadatos": "Disponibilidad, cierre de las fuentes y fecha de actualización",
        "DistritoRespuesta": "Catálogo distrital real, centroides y geometría si está disponible",
        "DatoSemanal": "Identidad distrital y temporal compartida por observaciones y pronósticos",
        "ObservacionRespuesta": "Casos observados, brote, umbral y procedencia; un faltante conserva null",
        "PrediccionRespuesta": "Probabilidad y magnitud por componente, riesgo, umbral F1 y trazabilidad del modelo",
        "ModeloRespuesta": "Versión de modelo y selección para inferencia, sin equivalencia automática con validación",
        "ModeloDetalle": "Evaluación por bloque, partición temporal, contrato y hashes del modelo",
        "SaludRespuesta": "Conexión real a BD, versiones activas y última ejecución completada",
        "GeojsonRespuesta": "Geometrías reales o centroides Point con explicación de ausencia de polígonos",
        "MapaDistrito": "Distrito del catálogo con riesgo disponible o Sin datos y motivo",
        "MapaRespuesta": "Todos los distritos, semana objetivo y leyenda de umbrales configurados",
        "SerieSemana": "Semana MMWR con observación y predicción anulables e independientes",
        "SeriesRespuesta": "Comparación semanal continua, con huecos explícitos y pronósticos OOS",
        "Indicador": "Valor consolidado utilizable o null acompañado de su motivo",
        "TableroRespuesta": "Indicadores del periodo, cobertura y distinción entre sumas parciales y regionales",
        "AlertaRespuesta": "Alerta conservada o retirada con indicadores, fechas y estado de validación",
        "VariablesRespuesta": "Importancias gain reales; no constituyen relaciones causales",
        "ReevaluacionRespuesta": "Ejecución confirmada atómicamente desde artefactos y vectores de la BD",
    }
    for nombre, esquema in schema["components"]["schemas"].items():
        if nombre.startswith("Pagina_"):
            esquema.setdefault("description", "Listado paginado con disponibilidad, total y corte de datos")
        elif nombre in esquemas:
            esquema.setdefault("description", esquemas[nombre])
    for metodos in schema["paths"].values():
        for operacion in metodos.values():
            for parametro in operacion.get("parameters", []):
                if parametro["name"] in descripciones:
                    parametro.setdefault("description", descripciones[parametro["name"]])
    fabrica = app.state.fabrica_sesiones
    if fabrica is not None:
        try:
            with fabrica() as sesion:
                ejemplos = ejemplos_reales(sesion, app.state.cfg)
                for (ruta, metodo), ejemplo in ejemplos.items():
                    schema["paths"]["/api/v1" + ruta][metodo]["responses"]["200"]["content"]["application/json"]["examples"] = {
                        "bd_real": {"summary": "Ejemplo obtenido de la base de datos configurada", "value": ejemplo}}
        except SQLAlchemyError:
            pass
    app.openapi_schema = schema
    return schema
