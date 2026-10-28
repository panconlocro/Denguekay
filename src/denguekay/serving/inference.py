"""Inference per cutoff week from the database, alerts and import of OOS predictions.

The feature vector is rebuilt in memory from ``observacion_semanal`` and
``distrito.poblacion_censo_2017`` with the same modelling functions
(``build_future_rows``); it is not persisted.
"""

from time import perf_counter

import numpy as np
import pandas as pd
from sqlalchemy import select

from denguekay.db.models import (Alert, District, Run, WeeklyObservation, Prediction,
                            EpiWeek, ModelVersion, utc_now)
from denguekay.db.session import upsert
from denguekay.model.future_rows import build_future_rows
from denguekay.features.sociodemographics import DIRECT
from denguekay.serving import parameters as parametros
from denguekay.serving.artifacts import predict_with_version
from denguekay.serving.risk import ALERT_LEVELS, alert_change, risk_level

TASKS = ("clasificacion", "regresion")
OOS_BLOCKS = ("temporada_2022", "temporada_2023", "temporada_2024", "calendario_2025")
H3_REASON = "sin modelo para h=3"


class InferenceUnavailable(ValueError):
    """The request cannot be served with the data or models in the database (HTTP 409)."""


# --- calendar and data ------------------------------------------------------

def week(sesion, id_semana):
    row = sesion.get(EpiWeek, id_semana)
    if row is None:
        raise InferenceUnavailable(f"La semana {id_semana} no está en el calendario epidemiológico")
    return row


def target_week(sesion, cutoff, horizon):
    start = cutoff.fecha_inicio + pd.Timedelta(weeks=horizon).to_pytimedelta()
    row = sesion.scalar(select(EpiWeek).where(EpiWeek.fecha_inicio == start))
    if row is None:
        raise InferenceUnavailable("La semana objetivo no está en el calendario; recargue los datos")
    return row


def last_observed_week(sesion):
    value = sesion.scalar(select(WeeklyObservation.id_semana).order_by(WeeklyObservation.id_semana.desc()).limit(1))
    if value is None:
        raise InferenceUnavailable("No hay observaciones cargadas")
    return value


def panel_from_db(sesion, end):
    """Minimal panel (cases per district and week) closed at date ``end``."""
    rows = sesion.execute(select(
        WeeklyObservation.ubigeo, EpiWeek.anio, EpiWeek.semana,
        EpiWeek.fecha_inicio, WeeklyObservation.casos_dengue
    ).join(EpiWeek, EpiWeek.id_semana == WeeklyObservation.id_semana
    ).where(EpiWeek.fecha_fin <= end)).all()
    panel = pd.DataFrame(rows, columns=["ubigeo", "anio", "semana", "semana_inicio", "casos_Dengue"])
    panel["ubigeo"] = panel.ubigeo.astype("string")
    panel["semana_inicio"] = pd.to_datetime(panel.semana_inicio)
    panel["casos_Dengue"] = panel.casos_Dengue.astype(float)
    return panel.sort_values(["ubigeo", "semana_inicio"]).reset_index(drop=True)


def reference_from_db(sesion):
    """2017 census reference from ``distrito``.

    ``build_sociodemography`` also requires three 2017 fractions; the serving
    models only use ``log_poblacion_censo_2017``, so those fractions are filled
    with 0 and do not enter the vector (they are dropped).
    """
    rows = sesion.execute(select(District.ubigeo, District.poblacion_censo_2017).where(
        District.poblacion_censo_2017.is_not(None))).all()
    reference = pd.DataFrame(rows, columns=["ubigeo", "poblacion"])
    reference["ubigeo"] = reference.ubigeo.astype("string")
    for column in DIRECT:
        reference[column] = 0.0
    return reference


def vectors_from_db(sesion, horizon, id_semana_corte, columns):
    """Vectors of the target cutoff+h, writing nothing. Returns (rows, reasons)."""
    cutoff = week(sesion, id_semana_corte)
    panel = panel_from_db(sesion, cutoff.fecha_fin)
    if panel.empty:
        raise InferenceUnavailable("No hay observaciones cerradas al corte solicitado")
    try:
        rows, reasons = build_future_rows(panel, horizon, columns=columns,
                                                 cutoff_date=pd.Timestamp(cutoff.fecha_fin),
                                                 reference=reference_from_db(sesion))
    except ValueError as error:
        raise InferenceUnavailable(str(error)) from error
    return rows, {m["ubigeo"]: m["motivo"] for m in reasons}


# --- version selection ----------------------------------------------------

def select_versions(sesion, horizon, servir_no_validadas):
    """Active version per task; if there is none, the experimental selection (temporary deviation).

    Returns ({task: ModelVersion}, reason); the dict is incomplete when some task
    has no usable version.
    """
    versions = {v.tarea: v for v in sesion.scalars(select(ModelVersion).where(
        ModelVersion.horizonte == horizon, ModelVersion.estado == "activa"))}
    missing = [t for t in TASKS if t not in versions]
    if missing and servir_no_validadas:
        codes = parametros.experimental_selection(sesion).get(horizon, {})
        for task in missing:
            code = codes.get(task)
            version = code and sesion.scalar(select(ModelVersion).where(ModelVersion.codigo == code))
            if version is not None and version.tarea == task and version.horizonte == horizon:
                versions[task] = version
    if all(t in versions for t in TASKS):
        return versions, None
    if not servir_no_validadas:
        return versions, "Predicción no disponible: no hay un modelo activo que cumpla los umbrales"
    return versions, f"Predicción no disponible: no hay versiones utilizables para h={horizon}"


def is_experimental(versions):
    return any(not v.cumple_umbrales for v in versions.values())


# --- inference -----------------------------------------------------------------

def _record(ubigeo, cutoff, target, horizon, run, versions, probability, cases, reason, cutoffs):
    available = probability is not None
    probability = round(float(probability), 4) if available else None  # numeric(5,4) of the DDL
    return {"ubigeo": ubigeo, "id_semana_corte": cutoff, "id_semana_objetivo": target,
            "horizonte": horizon, "probabilidad_brote": probability,
            "nivel_riesgo": risk_level(probability, cutoffs) if available else None,
            "casos_estimados": round(float(cases), 2) if available and cases is not None else None,
            "estado": "disponible" if available else "no_disponible",
            "motivo_no_disponible": None if available else reason,
            "id_version_clasificador": versions["clasificacion"].id_version if "clasificacion" in versions else None,
            "id_version_regresor": versions["regresion"].id_version if "regresion" in versions else None,
            "id_ejecucion": run, "fecha_generacion": utc_now()}


def infer(sesion, horizon, id_semana_corte=None, *, storage, servir_no_validadas, origin="api"):
    """Generate (UPSERT) each district's prediction for a cutoff and horizon.

    It creates an ``ejecucion`` of type ``inferencia``; the caller commits the
    transaction. Without a usable version, the rows stay ``no_disponible``.
    """
    start = perf_counter()
    if horizon == 3:
        raise InferenceUnavailable(H3_REASON)
    if horizon not in (2, 4):
        raise ValueError("horizonte debe ser 2, 3 o 4")
    id_semana_corte = id_semana_corte or last_observed_week(sesion)
    cutoff = week(sesion, id_semana_corte)
    if sesion.scalar(select(WeeklyObservation.id_semana).where(
            WeeklyObservation.id_semana == id_semana_corte).limit(1)) is None:
        raise InferenceUnavailable(f"No hay observaciones para la semana de corte {id_semana_corte}")
    target = target_week(sesion, cutoff, horizon)
    cutoffs = parametros.risk_cutoffs(sesion)
    versions, reason = select_versions(sesion, horizon, servir_no_validadas)
    run = Run(tipo="inferencia", estado="en_curso", id_semana_corte=id_semana_corte,
                          detalle={"origen": origin, "horizonte": horizon})
    sesion.add(run)
    sesion.flush()
    districts = list(sesion.scalars(select(District.ubigeo).where(District.activo.is_(True)).order_by(District.ubigeo)))
    probabilities, cases, reasons = {}, {}, {}
    if reason is None:
        columns = sorted({c for v in versions.values() for c in v.variables})
        rows, reasons = vectors_from_db(sesion, horizon, id_semana_corte, columns)
        if not rows.empty:
            p = predict_with_version(versions["clasificacion"], rows, storage)
            c = predict_with_version(versions["regresion"], rows, storage)
            probabilities = dict(zip(rows.ubigeo, map(float, p)))
            cases = dict(zip(rows.ubigeo, map(float, c)))
    records = [_record(u, id_semana_corte, target.id_semana, horizon, run.id_ejecucion, versions,
                           probabilities.get(u), cases.get(u),
                           reason or reasons.get(u, "No hay vector de características para el distrito"), cutoffs)
                 for u in districts]
    upsert(sesion, Prediction.__table__, records, ["ubigeo", "id_semana_corte", "horizonte"])
    sesion.flush()
    alerts = update_alerts(sesion, horizon, id_semana_corte)
    experimental = reason is None and is_experimental(versions)
    available = sum(r["estado"] == "disponible" for r in records)
    run.estado = "exitosa"
    run.fin = utc_now()
    run.detalle = {
        "origen": origin, "horizonte": horizon, "id_semana_corte": id_semana_corte,
        "id_semana_objetivo": target.id_semana, "experimental": experimental,
        "seleccion": "experimental" if experimental else ("activa" if reason is None else None),
        "versiones": {t: v.codigo for t, v in versions.items()}, "motivo": reason,
        "predicciones": len(records), "disponibles": available,
        "no_disponibles": len(records) - available, "alertas": alerts,
        "duracion_segundos": round(perf_counter() - start, 3)}
    sesion.flush()
    return {"id_ejecucion": run.id_ejecucion, **run.detalle}


def update_alerts(sesion, horizon, id_semana_corte):
    """Alerts of the cutoff for alto/muy_alto; at most one active per district and horizon.

    ``cambio`` compares with the level of the prediction of the previous cutoff
    week (cutoff - 1 week); without it, ``nueva``. It is idempotent: recomputing the
    same cutoff gives the same result. The active alert is always the one of the
    most recent cutoff; inferring a past cutoff neither reactivates old alerts nor
    leaves two active ones.
    """
    now = utc_now()
    current = list(sesion.scalars(select(Prediction).where(
        Prediction.horizonte == horizon, Prediction.id_semana_corte == id_semana_corte)))
    if not current:
        return {"nuevas_o_actualizadas": 0, "retiradas": 0}
    cutoff = week(sesion, id_semana_corte)
    previous = sesion.scalar(select(EpiWeek.id_semana).where(
        EpiWeek.fecha_inicio == cutoff.fecha_inicio - pd.Timedelta(weeks=1).to_pytimedelta()))
    previous_levels = dict(sesion.execute(select(Prediction.ubigeo, Prediction.nivel_riesgo).where(
        Prediction.horizonte == horizon, Prediction.id_semana_corte == previous)).all()) if previous else {}
    active = {}
    for alert, cutoff in sesion.execute(select(Alert, Prediction.id_semana_corte).join(
            Prediction, Prediction.id_prediccion == Alert.id_prediccion).where(
            Prediction.horizonte == horizon, Prediction.id_semana_corte != id_semana_corte,
            Alert.estado == "activa")):
        active.setdefault(alert.ubigeo, []).append((cutoff, alert))
    own_rows = {a.id_prediccion: a for a in sesion.scalars(select(Alert).where(
        Alert.id_prediccion.in_([p.id_prediccion for p in current])))}
    count = {"nuevas_o_actualizadas": 0, "retiradas": 0}

    def withdraw(alert, reason):
        if alert.estado == "activa":
            alert.estado, alert.fecha_retiro, alert.motivo = "retirada", now, reason
            count["retiradas"] += 1

    for p in current:
        others = active.get(p.ubigeo, [])
        later = any(cutoff > id_semana_corte for cutoff, _ in others)
        own = own_rows.get(p.id_prediccion)
        if p.estado == "disponible" and p.nivel_riesgo in ALERT_LEVELS:
            previous_value = previous_levels.get(p.ubigeo)
            change = alert_change(previous_value if previous_value in ALERT_LEVELS else None, p.nivel_riesgo)
            if own is None:
                own = Alert(id_prediccion=p.id_prediccion, ubigeo=p.ubigeo, nivel=p.nivel_riesgo,
                                estado="activa", cambio=change, fecha_generacion=now)
                sesion.add(own)
            else:
                own.nivel, own.cambio, own.estado = p.nivel_riesgo, change, "activa"
                own.fecha_generacion, own.fecha_retiro, own.motivo = now, None, None
            count["nuevas_o_actualizadas"] += 1
            if later:  # past cutoff: it stays as history and does not compete with the current one
                own.estado, own.fecha_retiro = "retirada", now
                own.motivo = "Corte anterior a una alerta activa más reciente"
        elif own is not None:
            withdraw(own, "La predicción recalculada ya no alcanza nivel alto")
        reason = (f"Sustituida por la alerta del corte {id_semana_corte}" if own is not None and own.estado == "activa"
                  else f"El riesgo del corte {id_semana_corte} ya no alcanza nivel alto")
        for cutoff, alert in others:
            if cutoff < id_semana_corte:
                withdraw(alert, reason)
    sesion.flush()
    return count


# --- OOS predictions (past cutoffs) --------------------------------------

def import_oos(sesion, protocol, horizons, cfg, service_versions):
    """Save the protocol's out-of-sample predictions as past cutoffs.

    One ``ejecucion`` of type ``inferencia`` per horizon and block, with the block
    and its origin in ``detalle``; ``id_version_*`` NULL because those boosters
    were not kept. They generate no alerts: they are history.
    """
    cutoffs = parametros.risk_cutoffs(sesion)
    calendar = pd.DataFrame(sesion.execute(select(
        EpiWeek.id_semana, EpiWeek.fecha_fin)).all(), columns=["id_semana", "fecha_fin"])
    cutoff_by_date = dict(zip(pd.to_datetime(calendar.fecha_fin), calendar.id_semana))
    end_by_id = dict(zip(calendar.id_semana, pd.to_datetime(calendar.fecha_fin)))
    summary = []
    for h in horizons:
        experimental = not all(service_versions[h, t].cumple_umbrales for t in TASKS)
        # load_protocol already checked each block's coverage against gold.
        present = set(protocol.predictions.loc[protocol.predictions.horizonte.eq(h), "bloque"])
        for block in [b for b in OOS_BLOCKS if b in present]:
            base = protocol.predictions.loc[protocol.predictions.horizonte.eq(h) & protocol.predictions.bloque.eq(block)]
            cls = base.loc[base.variante.eq(cfg.variantes["clasificacion"])].set_index(["ubigeo", "anio", "semana"]).sort_index()
            reg = base.loc[base.variante.eq(cfg.variantes["regresion"])].set_index(["ubigeo", "anio", "semana"]).sort_index()
            if cls.empty or not cls.index.equals(reg.index):
                raise ValueError(f"Clasificación y regresión OOS no comparten semanas en {block} h={h}")
            run = Run(tipo="inferencia", estado="en_curso", detalle={"origen": "oos_protocolo"})
            sesion.add(run)
            sesion.flush()
            records = []
            for (ubigeo, year, target_wk), row in cls.iterrows():
                cutoff = cutoff_by_date.get(pd.Timestamp(row.origen_cierre))
                if cutoff is None:
                    raise ValueError("El origen OOS no corresponde a un cierre del calendario")
                probability = float(row.probabilidad_brote)
                cases = float(reg.loc[(ubigeo, year, target_wk), "casos_predichos"])
                if not np.isfinite([probability, cases]).all() or cases < 0:
                    raise ValueError("No se importan predicciones OOS no finitas o negativas")
                target = int(year) * 100 + int(target_wk)
                if end_by_id.get(target) != pd.Timestamp(row.origen_cierre) + pd.Timedelta(weeks=h):
                    raise ValueError("La predicción OOS no respeta la distancia corte-objetivo h")
                records.append(_record(ubigeo, int(cutoff), target, h,
                                           run.id_ejecucion, {}, probability, cases, None, cutoffs))
            upsert(sesion, Prediction.__table__, records, ["ubigeo", "id_semana_corte", "horizonte"])
            run.estado, run.fin = "exitosa", utc_now()
            run.id_semana_corte = max(r["id_semana_corte"] for r in records)
            run.detalle = {"origen": "oos_protocolo", "horizonte": h, "bloque": block,
                                 "experimental": experimental, "predicciones": len(records),
                                 "variantes": dict(cfg.variantes),
                                 "sha256_protocolo": protocol.hashes,
                                 "nota": "Predicciones fuera de muestra del protocolo temporal; sin booster conservado"}
            summary.append({"horizonte": h, "bloque": block, "predicciones": len(records),
                            "id_ejecucion": run.id_ejecucion})
    sesion.flush()
    return summary
