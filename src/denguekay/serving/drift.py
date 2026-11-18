"""Drift monitoring of the weekly emissions (HU0009-2, US v1.4).

It compares the closed weeks of the archived weekly emissions with the reference metrics of the same horizon: the
aggregate block of the HU0007-4 (``parametro_sistema.umbrales_aceptacion.bloque``, ``temporadas_2022_2026`` for the V4)
stored in the metrics of the served versions.

- Period metrics: Precision, Recall and F1 (alert when p >= 0.50), and MAE and RMSE of the cases, over the available
  predictions of the weekly update whose target week is already observed (``emissions.prospective_frame``).
- Relative degradation: Recall and F1, (reference - period) / reference; MAE and RMSE, (period - reference) / reference.
  Precision is reported with its reference but has no degradation rule in the criterion, so it is never flagged.
- With 8 closed weeks or more (per horizon), the metrics whose degradation is above 10 % are flagged; with fewer they
  are only recorded, without decisions. If the reference is 0 the relative degradation is not computed.

The result is a record for the data/ML engineer to review. It never retrains, never changes the version in use and
writes nothing to ``data/``. ``python -m denguekay.serving.drift`` runs it by hand (monthly) and records it as a
``mantenimiento`` run; the weekly update only adds it to its report.
"""

import argparse
import json
import sys

from sqlalchemy import func, select

from denguekay.db.models import Run, utc_now
from denguekay.db.session import make_engine, transaction
from denguekay.evaluation.metrics import alert_metrics, count_metrics
from denguekay.serving import emissions
from denguekay.serving import parameters as parametros
from denguekay.serving.inference import select_versions

ORIGIN = "monitoreo_deriva"
MIN_CLOSED_WEEKS = 8
DEGRADATION_LIMIT = 0.10
ALERT_PROBABILITY = 0.50
# True: a drop of the metric is degradation; False: a rise is; None: reported but never flagged.
WORSE_WHEN_LOWER = {"recall": True, "f1": True, "mae": False, "rmse": False, "precision": None}
METRICS = tuple(WORSE_WHEN_LOWER)


def period_metrics(frame):
    """The five metrics of the closed weeks of one horizon; ``None`` where the data do not define them."""
    values = dict.fromkeys(METRICS)
    classified = frame.dropna(subset=["p", "brote"])
    if not classified.empty:
        scores = alert_metrics(classified.brote.astype(int).to_numpy(),
                               (classified.p.astype(float) >= ALERT_PROBABILITY).astype(int).to_numpy())
        values.update({name: scores[name] for name in ("precision", "recall", "f1")})
    counted = frame.dropna(subset=["casos_estimados", "casos"])
    if not counted.empty:
        scores = count_metrics(counted.casos.astype(float).to_numpy(), counted.casos_estimados.astype(float).to_numpy())
        values.update({name: scores[name] for name in ("mae", "rmse")})
    return {name: None if value is None else float(value) for name, value in values.items()}


def reference_metrics(sesion, horizon, block):
    """(metrics, version codes) of the same horizon from the metrics of the served versions.

    The metrics are ``None`` if the versions or the aggregate block are missing."""
    versions, _ = select_versions(sesion, horizon, True)
    codes = {task: version.codigo for task, version in versions.items()}
    try:
        alert = versions["clasificacion"].metricas["bloques"][block]["clasificacion"]["alerta_directa"]
        counts = versions["regresion"].metricas["bloques"][block]["regresion"]["conteos"]
    except (AttributeError, KeyError, TypeError):
        return None, codes
    values = {name: alert.get(name) for name in ("recall", "precision", "f1")}
    values.update({name: counts.get(name) for name in ("mae", "rmse")})
    return {name: None if value is None else float(value) for name, value in values.items()}, codes


def relative_degradation(metric, period, reference):
    """Relative degradation of one metric; ``None`` if either value is missing or the reference is 0."""
    lower_is_worse = WORSE_WHEN_LOWER[metric]
    if lower_is_worse is None or period is None or reference is None or reference == 0:
        return None
    return (reference - period) / reference if lower_is_worse else (period - reference) / reference


def horizon_report(frame, reference, versions, block):
    weeks = int(frame.id_semana_objetivo.nunique())
    decides = weeks >= MIN_CLOSED_WEEKS
    period = period_metrics(frame)
    metrics, flagged = {}, []
    for name in METRICS:
        ref = None if reference is None else reference.get(name)
        degradation = relative_degradation(name, period[name], ref)
        degradation = None if degradation is None else round(degradation, 6)   # a drop of exactly 10 % is not above it
        mark = bool(decides and degradation is not None and degradation > DEGRADATION_LIMIT)
        if mark:
            flagged.append(name)
        metrics[name] = {"periodo": period[name], "referencia": ref,
                         "degradacion_relativa": degradation,
                         "marcada": mark,
                         "motivo": "referencia 0: no se calcula la degradación relativa" if ref == 0 else None}
    if not weeks:
        state = "sin_datos"
    elif reference is None:
        state = "sin_referencia"
    elif not decides:
        state = "solo_registro"
    else:
        state = "degradacion_detectada" if flagged else "sin_degradacion"
    return {"estado": state, "semanas_cerradas": weeks, "filas": int(len(frame)), "con_decision": decides,
            "bloque_referencia": block, "versiones": versions, "metricas": metrics, "marcadas": flagged}


def drift_report(sesion):
    """Drift record of the three horizons of the weekly update, read-only."""
    block = parametros.acceptance_criteria(sesion)["bloques"][0]
    frame = emissions.prospective_frame(sesion)
    horizons = {}
    for horizon in emissions.HORIZONS:
        reference, versions = reference_metrics(sesion, horizon, block)
        horizons[str(horizon)] = horizon_report(frame[frame.horizonte.eq(horizon)], reference, versions, block)
    flagged = {h: r["marcadas"] for h, r in horizons.items() if r["marcadas"]}
    return {"criterio": {"semanas_cerradas_minimas": MIN_CLOSED_WEEKS, "degradacion_maxima": DEGRADATION_LIMIT,
                         "probabilidad_de_alerta": ALERT_PROBABILITY, "bloque_referencia": block},
            "horizontes": horizons, "requiere_revision": bool(flagged), "metricas_marcadas": flagged,
            "nota": "Registro para revisión del Ingeniero de Datos / ML; no reentrena ni cambia la versión en uso."}


def latest_cutoff(sesion):
    """The newest cutoff week of the weekly update's predictions, or ``None``."""
    return sesion.scalar(select(func.max(Run.id_semana_corte)).where(Run.tipo == "inferencia", Run.estado == "exitosa"))


def register(sesion, report, cutoff=None):
    """Record the result as a ``mantenimiento`` run (the detail carries the origin ``monitoreo_deriva``)."""
    run = Run(tipo="mantenimiento", estado="exitosa", id_semana_corte=cutoff, fin=utc_now(),
              detalle={"origen": ORIGIN, **report})
    sesion.add(run)
    sesion.flush()
    return run.id_ejecucion


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sin-registrar", action="store_true", help="Calcula y muestra sin guardar la ejecución")
    args = parser.parse_args(argv)
    motor = make_engine()
    try:
        with transaction(motor) as sesion:
            report = drift_report(sesion)
            if not args.sin_registrar:
                report["id_ejecucion"] = register(sesion, report, latest_cutoff(sesion))
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return 0
    except Exception as error:   # the command reports and exits; it never touches the model
        print(f"Monitoreo de deriva rechazado: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    finally:
        motor.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
