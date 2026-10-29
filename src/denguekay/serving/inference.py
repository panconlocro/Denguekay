"""Inference per cutoff week from the database, alerts and import of OOS predictions.

``infer`` knows no model: it loads the package of the versions in use, asks its predictor (the port in
``denguekay.serving.predictors``) for one row per district with the inputs it declares, rebuilt in memory
from the database (``denguekay.serving.inputs``), and writes ``prediccion`` and ``alerta``.
"""

from time import perf_counter

import numpy as np
import pandas as pd
from sqlalchemy import select

from denguekay.db.models import (HORIZONS, TASK, Alert, District, Run, WeeklyObservation, Prediction,
                                 EpiWeek, ModelVersion, utc_now)
from denguekay.db.session import upsert
from denguekay.serving import parameters as parametros
from denguekay.serving.artifacts import InvalidArtifact
from denguekay.serving.inputs import build_inputs
from denguekay.serving.package import load_package
from denguekay.serving.predictors import load_predictor
from denguekay.serving.predictors.base import InferenceUnavailable, validate_output
from denguekay.serving.risk import ALERT_LEVELS, alert_change, risk_level

NO_VECTOR_REASON = "No hay vector de características para el distrito"

__all__ = ["InferenceUnavailable", "infer", "import_oos", "select_versions", "update_alerts"]


def no_model_reason(horizon):
    return f"sin modelo para h={horizon}"


# --- calendar --------------------------------------------------------------------

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


# --- version selection ----------------------------------------------------

def select_versions(sesion, horizon, servir_no_validadas):
    """Active version per task; if there is none, the experimental selection (temporary deviation).

    Returns ({task: ModelVersion}, reason); the dict is incomplete when some task (of the DDL
    ENUM) has no usable version.
    """
    versions = {v.tarea: v for v in sesion.scalars(select(ModelVersion).where(
        ModelVersion.horizonte == horizon, ModelVersion.estado == "activa"))}
    missing = [t for t in TASK if t not in versions]
    if missing and servir_no_validadas:
        codes = parametros.experimental_selection(sesion).get(horizon, {})
        for task in missing:
            code = codes.get(task)
            version = code and sesion.scalar(select(ModelVersion).where(ModelVersion.codigo == code))
            if version is not None and version.tarea == task and version.horizonte == horizon:
                versions[task] = version
    if all(t in versions for t in TASK):
        return versions, None
    if not servir_no_validadas:
        return versions, "Predicción no disponible: no hay un modelo activo que cumpla los umbrales"
    return versions, f"Predicción no disponible: no hay versiones utilizables para h={horizon}"


def is_experimental(versions):
    return any(not v.cumple_umbrales for v in versions.values())


def package_of(versions, storage):
    """The package shared by the versions of one horizon (decision M3: both tasks come from one package)."""
    paths = {(v.ruta_artefacto, v.sha256_artefacto) for v in versions.values()}
    if len(paths) != 1:
        raise InvalidArtifact("Las versiones de clasificación y regresión en uso no pertenecen al mismo paquete")
    path, sha256 = paths.pop()
    return load_package(storage, path, sha256)


# --- inference -----------------------------------------------------------------

def _record(ubigeo, cutoff, target, horizon, run, versions, probability, cases, interval, reason, cutoffs):
    available = probability is not None
    probability = round(float(probability), 4) if available else None  # numeric(5,4) of the DDL
    low, high = interval if available and interval is not None else (None, None)
    return {"ubigeo": ubigeo, "id_semana_corte": cutoff, "id_semana_objetivo": target,
            "horizonte": horizon, "probabilidad_brote": probability,
            "nivel_riesgo": risk_level(probability, cutoffs) if available else None,
            "casos_estimados": round(float(cases), 2) if available and cases is not None else None,
            "casos_intervalo_inferior": None if low is None else round(float(low), 2),
            "casos_intervalo_superior": None if high is None else round(float(high), 2),
            "estado": "disponible" if available else "no_disponible",
            "motivo_no_disponible": None if available else reason,
            "id_version_clasificador": versions["clasificacion"].id_version if "clasificacion" in versions else None,
            "id_version_regresor": versions["regresion"].id_version if "regresion" in versions else None,
            "id_ejecucion": run, "fecha_generacion": utc_now()}


def predict_cutoff(sesion, versions, horizon, cutoff, storage):
    """Run the package's predictor for one horizon. Returns (package, {ubigeo: output row})."""
    package = package_of(versions, storage)
    if package.interval_level is not None:
        level = parametros.interval_level(sesion)
        if abs(float(package.interval_level) - level) > 1e-12:
            raise InferenceUnavailable(
                f"El paquete {package.code} calcula intervalos al nivel {package.interval_level} y "
                f"parametro_sistema.nivel_intervalo_casos es {level}: publique un paquete con ese nivel")
    predictor = load_predictor(package)
    output = predictor.predict(build_inputs(sesion, cutoff, predictor.required_inputs), cutoff, (horizon,))
    validate_output(output, (horizon,), package.interval_level)
    return package, {r.ubigeo: r for r in output.itertuples(index=False)}


def infer(sesion, horizon, id_semana_corte=None, *, storage, servir_no_validadas, origin="api"):
    """Generate (UPSERT) each district's prediction for a cutoff and horizon.

    It creates an ``ejecucion`` of type ``inferencia``; the caller commits the transaction. A horizon
    with no version at all answers 409; without a usable version the rows stay ``no_disponible``.
    """
    start = perf_counter()
    if horizon not in HORIZONS or isinstance(horizon, bool):
        raise ValueError("horizonte debe ser 2, 3 o 4")
    if sesion.scalar(select(ModelVersion.id_version).where(ModelVersion.horizonte == horizon).limit(1)) is None:
        raise InferenceUnavailable(no_model_reason(horizon))
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
    package, rows = None, {}
    if reason is None:
        package, rows = predict_cutoff(sesion, versions, horizon, cutoff, storage)

    def record(ubigeo):
        row = rows.get(ubigeo)
        if row is None or not pd.isna(row.motivo_no_disponible):
            why = reason or (row.motivo_no_disponible if row is not None else NO_VECTOR_REASON)
            return _record(ubigeo, id_semana_corte, target.id_semana, horizon, run.id_ejecucion, versions,
                           None, None, None, why, cutoffs)
        interval = (None if pd.isna(row.casos_intervalo_inferior)
                    else (row.casos_intervalo_inferior, row.casos_intervalo_superior))
        return _record(ubigeo, id_semana_corte, target.id_semana, horizon, run.id_ejecucion, versions,
                       row.probabilidad_brote, row.casos_estimados, interval, None, cutoffs)

    records = [record(u) for u in districts]
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
        "paquete": package.code if package else None,
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

def import_oos(sesion, oos, detail, versions):
    """Save a package's out-of-sample predictions as past cutoffs.

    ``oos`` has the columns of ``predictors.base.OOS_COLUMNS``; ``versions`` = {(horizon, task):
    ModelVersion} of the package. One ``ejecucion`` of type ``inferencia`` per horizon and block, with
    the block and ``detail`` in ``detalle``; ``id_version_*`` NULL because those boosters were not kept.
    They generate no alerts: they are history.
    """
    cutoffs = parametros.risk_cutoffs(sesion)
    calendar = pd.DataFrame(sesion.execute(select(
        EpiWeek.id_semana, EpiWeek.fecha_fin)).all(), columns=["id_semana", "fecha_fin"])
    cutoff_by_date = dict(zip(pd.to_datetime(calendar.fecha_fin), calendar.id_semana))
    end_by_id = dict(zip(calendar.id_semana, pd.to_datetime(calendar.fecha_fin)))
    summary = []
    for (h, block), part in oos.groupby(["horizonte", "bloque"], sort=False):
        h = int(h)
        experimental = not all(v.cumple_umbrales for (vh, _), v in versions.items() if vh == h)
        run = Run(tipo="inferencia", estado="en_curso", detalle={"origen": "oos_protocolo"})
        sesion.add(run)
        sesion.flush()
        records = []
        for row in part.itertuples(index=False):
            cutoff = cutoff_by_date.get(pd.Timestamp(row.origen_cierre))
            if cutoff is None:
                raise ValueError("El origen OOS no corresponde a un cierre del calendario")
            probability, cases = float(row.probabilidad_brote), float(row.casos_estimados)
            if not np.isfinite([probability, cases]).all() or cases < 0:
                raise ValueError("No se importan predicciones OOS no finitas o negativas")
            target = int(row.anio) * 100 + int(row.semana)
            if end_by_id.get(target) != pd.Timestamp(row.origen_cierre) + pd.Timedelta(weeks=h):
                raise ValueError("La predicción OOS no respeta la distancia corte-objetivo h")
            records.append(_record(row.ubigeo, int(cutoff), target, h, run.id_ejecucion, {},
                                   probability, cases, None, None, cutoffs))
        upsert(sesion, Prediction.__table__, records, ["ubigeo", "id_semana_corte", "horizonte"])
        run.estado, run.fin = "exitosa", utc_now()
        run.id_semana_corte = max(r["id_semana_corte"] for r in records)
        run.detalle = {"origen": "oos_protocolo", "horizonte": h, "bloque": block,
                       "experimental": experimental, "predicciones": len(records), **detail}
        summary.append({"horizonte": h, "bloque": block, "predicciones": len(records),
                        "id_ejecucion": run.id_ejecucion})
    sesion.flush()
    return summary
