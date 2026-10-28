"""Queries and DTOs from the OE2 database; batches are resolved without N+1 queries."""

from datetime import timedelta

from sqlalchemy import func, select

from apps.api.errors import APIError
from denguekay.db.models import (Alert, District, Run, VariableImportance, WeeklyObservation,
                            Prediction, EpiWeek, ModelVersion)
from denguekay.serving import parameters
from denguekay.serving.inference import H3_REASON, TASKS, select_versions
from denguekay.serving.risk import LABELS, LEVELS

EXPERIMENTAL_NOTE = ("Demo experimental: ningún modelo cumple todavía los umbrales de aceptación; "
                     "las predicciones marcadas experimental: true no son un modelo validado.")


# --- general utilities -------------------------------------------------------

def metadata(session, available=True, reason=None):
    """Cutoff of the last ingestion and end of the last successful run."""
    ingestion = session.scalar(select(Run).where(Run.tipo == "ingesta", Run.estado == "exitosa")
                            .order_by(Run.id_ejecucion.desc()).limit(1))
    end_time = session.scalar(select(func.max(Run.fin)).where(Run.estado == "exitosa"))
    cutoff = ((ingestion.detalle or {}).get("resumen") or {}).get("fecha_corte_datos") if ingestion else None
    return {"disponible": available, "motivo": reason, "fecha_corte_datos": cutoff, "fecha_actualizacion": end_time}


def paginate(session, query, page, size, transform, meta=None):
    """``transform`` receives the list of rows of the page (a batch)."""
    total = session.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    rows = list(session.scalars(query.offset((page - 1) * size).limit(size)))
    meta = meta or metadata(session)
    return {**meta, "elementos": transform(rows), "total": total, "pagina": page, "tamano_pagina": size}


def week_dto(s):
    return None if s is None else {"id_semana": s.id_semana, "anio": s.anio, "semana": s.semana,
                                   "fecha_inicio": s.fecha_inicio, "fecha_fin": s.fecha_fin}


def weeks(session, ids):
    ids = set(ids)
    if not ids:
        return {}
    return {s.id_semana: s for s in session.scalars(select(EpiWeek).where(EpiWeek.id_semana.in_(ids)))}


# --- districts and observations --------------------------------------------------

def existing_district(session, ubigeo):
    d = session.get(District, ubigeo)
    if d is None:
        raise APIError(404, "distrito_no_encontrado", "El ubigeo no pertenece al catálogo de Piura")
    return d


def district_dto(d):
    return {"ubigeo": d.ubigeo, "nombre": d.nombre, "ubigeo_provincia": d.ubigeo_provincia,
            "provincia": d.provincia.nombre, "latitud": d.latitud, "longitud": d.longitud,
            "poblacion_censo_2017": d.poblacion_censo_2017, "activo": d.activo}


def district_names(session):
    return dict(session.execute(select(District.ubigeo, District.nombre)).all())


def observation_dtos(session, rows):
    names, cal = district_names(session), weeks(session, (o.id_semana for o in rows))
    return [{"ubigeo": o.ubigeo, "distrito": names[o.ubigeo], "semana": week_dto(cal[o.id_semana]),
             "casos_dengue": o.casos_dengue, "brote": o.brote, "umbral_brote_casos": o.umbral_brote_casos,
             "temp_media_c": o.temp_media_c, "temp_min_c": o.temp_min_c, "temp_max_c": o.temp_max_c,
             "precip_total_mm": o.precip_total_mm, "hum_rel_media_pct": o.hum_rel_media_pct,
             "fuente_casos": o.fuente_casos, "estado_cobertura": o.estado_cobertura} for o in rows]


def observations_query(ubigeo=None, start=None, end=None):
    query = select(WeeklyObservation).join(
        EpiWeek, EpiWeek.id_semana == WeeklyObservation.id_semana)
    if ubigeo:
        query = query.where(WeeklyObservation.ubigeo == ubigeo)
    if start:
        query = query.where(EpiWeek.fecha_inicio >= start)
    if end:
        query = query.where(EpiWeek.fecha_inicio <= end)
    return query.order_by(WeeklyObservation.id_semana, WeeklyObservation.ubigeo)


# --- predictions -----------------------------------------------------------------

def oos_runs(session):
    return [e.id_ejecucion for e in session.scalars(select(Run).where(Run.tipo == "inferencia"))
            if (e.detalle or {}).get("origen") == "oos_protocolo"]


def current_cutoff(session, horizon):
    """Last cutoff published by an operational inference (not by the OOS import)."""
    query = select(func.max(Prediction.id_semana_corte)).where(Prediction.horizonte == horizon)
    oos = oos_runs(session)
    if oos:
        query = query.where(Prediction.id_ejecucion.not_in(oos))
    return session.scalar(query)


def prediction_dtos(session, rows):
    """Batched DTOs: weeks, versions, runs and persistence in few queries."""
    if not rows:
        return []
    names = district_names(session)
    cal = weeks(session, [p.id_semana_corte for p in rows] + [p.id_semana_objetivo for p in rows])
    versions = {v.id_version: v for v in session.scalars(select(ModelVersion))}
    details = dict(session.execute(select(Run.id_ejecucion, Run.detalle).where(
        Run.id_ejecucion.in_({p.id_ejecucion for p in rows}))).all())
    persistence = dict(((u, s), c) for u, s, c in session.execute(select(
        WeeklyObservation.ubigeo, WeeklyObservation.id_semana, WeeklyObservation.casos_dengue).where(
        WeeklyObservation.id_semana.in_({p.id_semana_corte for p in rows}),
        WeeklyObservation.ubigeo.in_({p.ubigeo for p in rows}))))
    current = {h: current_cutoff(session, h) for h in {p.horizonte for p in rows}}
    result = []
    for p in rows:
        clf, reg = versions.get(p.id_version_clasificador), versions.get(p.id_version_regresor)
        used = [v for v in (clf, reg) if v is not None]
        experimental = (any(not v.cumple_umbrales for v in used) if used
                        else bool((details.get(p.id_ejecucion) or {}).get("experimental", True)))
        available = p.estado == "disponible"
        result.append({
            "disponible": available, "motivo": p.motivo_no_disponible,
            "id_prediccion": p.id_prediccion, "ubigeo": p.ubigeo, "distrito": names[p.ubigeo],
            "horizonte": p.horizonte, "semana_corte": week_dto(cal[p.id_semana_corte]),
            "semana_objetivo": week_dto(cal[p.id_semana_objetivo]),
            "tipo": "vigente" if p.id_semana_corte == current[p.horizonte] else "retrospectiva",
            "estado": p.estado, "probabilidad_brote": p.probabilidad_brote, "nivel_riesgo": p.nivel_riesgo,
            "nivel_riesgo_etiqueta": LABELS.get(p.nivel_riesgo), "casos_estimados": p.casos_estimados,
            "casos_persistencia": persistence.get((p.ubigeo, p.id_semana_corte)),
            "alerta_modelo": (p.probabilidad_brote >= clf.umbral_probabilidad
                              if available and clf is not None and clf.umbral_probabilidad is not None else None),
            "experimental": experimental, "id_version_clasificador": p.id_version_clasificador,
            "id_version_regresor": p.id_version_regresor, "id_ejecucion": p.id_ejecucion,
            "fecha_generacion": p.fecha_generacion})
    return result


def predictions_query(horizon, cutoff, ubigeo=None):
    query = select(Prediction).where(Prediction.horizonte == horizon, Prediction.id_semana_corte == cutoff)
    if ubigeo:
        query = query.where(Prediction.ubigeo == ubigeo)
    return query.order_by(Prediction.ubigeo)


def no_prediction_reason(session, horizon):
    """Reason when there are no predictions for the horizon (h=3 or not published yet)."""
    if horizon == 3:
        return H3_REASON
    return "Aún no hay predicciones publicadas para este horizonte"


# --- series, dashboard and map ---------------------------------------------------

def series(session, ubigeo, horizon, start, end):
    """Continuous calendar weeks with observed values and predictions (null when missing)."""
    d = existing_district(session, ubigeo)
    if end is None:
        last = session.scalar(select(func.max(EpiWeek.fecha_inicio)).join(
            Prediction, Prediction.id_semana_objetivo == EpiWeek.id_semana).where(
            Prediction.ubigeo == ubigeo, Prediction.horizonte == horizon))
        last = last or session.scalar(select(func.max(EpiWeek.fecha_inicio)).join(
            WeeklyObservation, WeeklyObservation.id_semana == EpiWeek.id_semana))
        if last is None:
            raise APIError(409, "sin_datos", "No hay observaciones ni predicciones cargadas")
        end = last
    start = start or end - timedelta(weeks=25)
    if (end - start).days > 7 * 520:
        raise APIError(422, "rango_invalido", "El rango de la serie no puede superar 10 años")
    cal = list(session.scalars(select(EpiWeek).where(
        EpiWeek.fecha_inicio >= start, EpiWeek.fecha_inicio <= end
    ).order_by(EpiWeek.id_semana)))
    ids = [s.id_semana for s in cal]
    obs = {o.id_semana: o for o in session.scalars(select(WeeklyObservation).where(
        WeeklyObservation.ubigeo == ubigeo, WeeklyObservation.id_semana.in_(ids)))} if ids else {}
    preds = list(session.scalars(select(Prediction).where(
        Prediction.ubigeo == ubigeo, Prediction.horizonte == horizon, Prediction.id_semana_objetivo.in_(ids)))) if ids else []
    dtos = {dto["semana_objetivo"]["id_semana"]: dto for dto in prediction_dtos(session, preds)}
    reason = H3_REASON if horizon == 3 else None
    return {**metadata(session, reason is None, reason), "ubigeo": ubigeo, "distrito": d.nombre,
            "horizonte": horizon, "desde": start, "hasta": end,
            "elementos": [{"semana": week_dto(s), "observado": s.id_semana in obs,
                           "casos_dengue": obs[s.id_semana].casos_dengue if s.id_semana in obs else None,
                           "brote": obs[s.id_semana].brote if s.id_semana in obs else None,
                           "prediccion": dtos.get(s.id_semana)} for s in cal]}


def current_predictions(session, horizon):
    cutoff = current_cutoff(session, horizon) if horizon != 3 else None
    if cutoff is None:
        return None, []
    return cutoff, prediction_dtos(session, list(session.scalars(predictions_query(horizon, cutoff))))


def dashboard(session, horizon):
    cutoff, dtos = current_predictions(session, horizon)
    available_rows = [p for p in dtos if p["disponible"]]
    levels = {n: sum(p["nivel_riesgo"] == n for p in available_rows) for n in LEVELS}
    total_districts = session.scalar(select(func.count()).select_from(District).where(District.activo.is_(True)))
    active = session.scalar(select(func.count()).select_from(Alert).join(
        Prediction, Prediction.id_prediccion == Alert.id_prediccion).where(
        Alert.estado == "activa", Prediction.horizonte == horizon))
    last_obs = session.scalar(select(func.max(WeeklyObservation.id_semana)))
    observed_cases = session.scalar(select(func.sum(WeeklyObservation.casos_dengue)).where(
        WeeklyObservation.id_semana == last_obs)) if last_obs else None
    complete = bool(dtos) and len(available_rows) == len(dtos)
    reason = None if dtos else no_prediction_reason(session, horizon)
    return {**metadata(session, bool(dtos), reason), "horizonte": horizon,
            "semana_corte": dtos[0]["semana_corte"] if dtos else None,
            "semana_objetivo": dtos[0]["semana_objetivo"] if dtos else None,
            "experimental": any(p["experimental"] for p in dtos),
            "distritos": total_districts, "distritos_con_prediccion": len(available_rows),
            "niveles_riesgo": levels, "alertas_activas": active,
            "casos_estimados_region": {
                "disponible": complete, "valor": round(sum(p["casos_estimados"] or 0 for p in available_rows), 2) if complete else None,
                "motivo": None if complete else "Falta la magnitud de algún distrito; no se suma una región parcial"},
            "casos_observados_ultima_semana": {"disponible": observed_cases is not None, "valor": observed_cases,
                                               "motivo": None if observed_cases is not None else "No hay observaciones"},
            "nota": EXPERIMENTAL_NOTE if any(p["experimental"] for p in dtos) else
                    "Predicciones de una versión activa que cumple los umbrales"}


def risk_map(session, horizon):
    """GeoJSON of centroids (Point): the project reference has no polygons."""
    cutoff, dtos = current_predictions(session, horizon)
    by_ubigeo = {p["ubigeo"]: p for p in dtos}
    general_reason = no_prediction_reason(session, horizon) if not dtos else None
    cutoffs = parameters.risk_cutoffs(session)
    features = []
    for d in session.scalars(select(District).where(District.activo.is_(True)).order_by(District.ubigeo)):
        p = by_ubigeo.get(d.ubigeo)
        features.append({"type": "Feature", "id": d.ubigeo,
            "geometry": {"type": "Point", "coordinates": [d.longitud, d.latitud]},
            "properties": {"ubigeo": d.ubigeo, "distrito": d.nombre, "provincia": d.provincia.nombre,
                           "estado": p["estado"] if p else "no_disponible",
                           "nivel_riesgo": p["nivel_riesgo"] if p else None,
                           "nivel_riesgo_etiqueta": (p["nivel_riesgo_etiqueta"] if p else None) or "Sin datos",
                           "probabilidad_brote": p["probabilidad_brote"] if p else None,
                           "casos_estimados": p["casos_estimados"] if p else None,
                           "experimental": p["experimental"] if p else False,
                           "motivo": (p["motivo"] if p else general_reason) or None}})
    legend = [{"nivel": "bajo", "etiqueta": "Bajo", "desde": 0.0, "hasta": cutoffs["medio"]},
               {"nivel": "medio", "etiqueta": "Medio", "desde": cutoffs["medio"], "hasta": cutoffs["alto"]},
               {"nivel": "alto", "etiqueta": "Alto", "desde": cutoffs["alto"], "hasta": cutoffs["muy_alto"]},
               {"nivel": "muy_alto", "etiqueta": "Muy alto", "desde": cutoffs["muy_alto"], "hasta": 1.0},
               {"nivel": None, "etiqueta": "Sin datos", "desde": None, "hasta": None}]
    return {**metadata(session, bool(dtos), general_reason), "type": "FeatureCollection", "horizonte": horizon,
            "semana_corte": dtos[0]["semana_corte"] if dtos else None,
            "semana_objetivo": dtos[0]["semana_objetivo"] if dtos else None,
            "experimental": any(p["experimental"] for p in dtos), "leyenda": legend, "features": features}


# --- alerts ----------------------------------------------------------------------

def alerts_query(horizon=None, ubigeo=None, nivel=None, estado=None):
    query = select(Alert).join(Prediction, Prediction.id_prediccion == Alert.id_prediccion)
    for condition in (Prediction.horizonte == horizon if horizon else None,
                      Alert.ubigeo == ubigeo if ubigeo else None,
                      Alert.nivel == nivel if nivel else None,
                      Alert.estado == estado if estado else None):
        if condition is not None:
            query = query.where(condition)
    # Active first, then muy_alto before alto, and the most recent on top.
    return query.order_by(Alert.estado, Alert.nivel.desc(), Alert.fecha_generacion.desc(), Alert.id_alerta.desc())


def alert_dtos(session, rows):
    ids = {a.id_prediccion for a in rows}
    predictions = list(session.scalars(select(Prediction).where(Prediction.id_prediccion.in_(ids)))) if ids else []
    preds = {p["id_prediccion"]: p for p in prediction_dtos(session, predictions)}
    return [{"id_alerta": a.id_alerta, "ubigeo": a.ubigeo, "distrito": preds[a.id_prediccion]["distrito"],
             "horizonte": preds[a.id_prediccion]["horizonte"], "nivel": a.nivel,
             "nivel_etiqueta": LABELS[a.nivel], "estado": a.estado, "cambio": a.cambio,
             "fecha_generacion": a.fecha_generacion, "fecha_retiro": a.fecha_retiro, "motivo": a.motivo,
             "experimental": preds[a.id_prediccion]["experimental"], "prediccion": preds[a.id_prediccion]}
            for a in rows]


# --- models ----------------------------------------------------------------------

def existing_model(session, identifier):
    v = session.get(ModelVersion, identifier)
    if v is None:
        raise APIError(404, "modelo_no_encontrado", "La versión de modelo no existe")
    return v


def model_dto(v, detalle=False):
    dto = {"id_version": v.id_version, "codigo": v.codigo, "tarea": v.tarea, "horizonte": v.horizonte,
           "algoritmo": v.algoritmo, "estado": v.estado, "cumple_umbrales": v.cumple_umbrales,
           "experimental": not v.cumple_umbrales, "umbral_probabilidad": v.umbral_probabilidad,
           "mlflow_run_id": v.mlflow_run_id, "fecha_registro": v.fecha_registro,
           "fecha_activacion": v.fecha_activacion}
    if detalle:
        dto.update(variables=v.variables, hiperparametros=v.hiperparametros, metricas=v.metricas,
                   ruta_artefacto=v.ruta_artefacto, sha256_artefacto=v.sha256_artefacto,
                   sha256_dataset=v.sha256_dataset, reproducibilidad=v.reproducibilidad)
    return dto


def models_in_use(session, horizon, servir_no_validadas):
    horizontes = [horizon] if horizon else sorted(set(session.scalars(select(ModelVersion.horizonte))))
    items = []
    for h in horizontes:
        versions, _ = select_versions(session, h, servir_no_validadas)
        for task in TASKS:
            if task in versions:
                v = versions[task]
                items.append({**model_dto(v), "seleccion": "activa" if v.estado == "activa" else "experimental"})
    reason = None if items else (H3_REASON if horizon == 3 else "No hay versiones activas ni selección experimental utilizable")
    experimental = any(e["experimental"] for e in items)
    return {**metadata(session, bool(items), reason), "elementos": items,
            "nota": EXPERIMENTAL_NOTE if experimental else "Versiones activas que cumplen los umbrales de aceptación"}


def variables(session, identifier):
    existing_model(session, identifier)
    rows = list(session.scalars(select(VariableImportance).where(
        VariableImportance.id_version == identifier).order_by(VariableImportance.rango)))
    return {**metadata(session, bool(rows), None if rows else "La versión no tiene importancias guardadas"),
            "id_version": identifier,
            "elementos": [{"variable": f.variable, "importancia": f.importancia, "rango": f.rango} for f in rows],
            "nota": "Importancia gain del booster; no implica causalidad"}


# --- health ----------------------------------------------------------------------

def health(session, api_version):
    last = session.scalar(select(Run).where(Run.estado == "exitosa")
                           .order_by(Run.id_ejecucion.desc()).limit(1))
    return {**metadata(session), "estado": "ok", "conexion_bd": True, "version_api": api_version,
            "ultima_ejecucion": None if last is None else {
                "id_ejecucion": last.id_ejecucion, "tipo": last.tipo, "estado": last.estado,
                "id_semana_corte": last.id_semana_corte, "fin": last.fin}}
