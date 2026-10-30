"""Reading of ``parametro_sistema``: the database is the authority for thresholds and cutoffs."""

from sqlalchemy import select

from denguekay.db.models import SystemParameter, utc_now


class MissingParameter(ValueError):
    """The database lacks a mandatory parameter (missing alembic upgrade head?)."""


def read(sesion, key):
    value = sesion.scalar(select(SystemParameter.valor).where(SystemParameter.clave == key))
    if value is None:
        raise MissingParameter(f"Falta el parámetro {key} en parametro_sistema")
    return value


def risk_cutoffs(sesion):
    cutoffs = read(sesion, "cortes_riesgo")
    if not 0 < cutoffs["medio"] < cutoffs["alto"] < cutoffs["muy_alto"] < 1:
        raise ValueError("cortes_riesgo debe ser creciente y estar entre 0 y 1")
    return cutoffs


def default_horizon(sesion):
    """Horizon the frontend shows first (seeded by migration 0004_v1)."""
    value = read(sesion, "horizonte_por_defecto")
    horizon = value.get("horizonte") if isinstance(value, dict) else None
    if not isinstance(horizon, int) or isinstance(horizon, bool) or horizon not in (2, 3, 4):
        raise ValueError("horizonte_por_defecto debe indicar un horizonte entre 2 y 4")
    return horizon


def interval_level(sesion):
    """Nominal probability of the case intervals (seeded by migration 0005_v1)."""
    value = read(sesion, "nivel_intervalo_casos")
    level = value.get("nivel") if isinstance(value, dict) else None
    if not isinstance(level, (int, float)) or isinstance(level, bool) or not 0 < level < 1:
        raise ValueError("nivel_intervalo_casos debe ser una probabilidad entre 0 y 1")
    return float(level)


def acceptance_criteria(sesion):
    """Translate umbrales_aceptacion to the format of denguekay.evaluation.acceptance."""
    u = read(sesion, "umbrales_aceptacion")
    return {"bloques": [u["bloque"]], "recall_minimo": u["recall"], "precision_minima": u["precision"],
            "f1_minimo": u["f1"], "proporcion_error_persistencia": u["razon_error_base"]}


def experimental_selection(sesion):
    """{horizon: {task: code}}; empty if it was not seeded."""
    value = sesion.scalar(select(SystemParameter.valor).where(SystemParameter.clave == "seleccion_experimental"))
    return {int(h): v for h, v in (value or {}).items()}


def set_experimental_selection(sesion, selection):
    """Set the selection of some horizons ({horizon: {task: code}}), keeping the other horizons.

    Only UPDATE of the ``seleccion_experimental`` row (migration 0006_v1 seeds it empty and lets
    ``rol_pipeline`` update that row alone); which model is served is operational data, not a migration.
    """
    row = sesion.get(SystemParameter, "seleccion_experimental")
    if row is None:
        raise MissingParameter("Falta el parámetro seleccion_experimental en parametro_sistema")
    value = dict(row.valor or {})
    value.update({str(h): dict(v) for h, v in selection.items()})
    row.valor, row.fecha_actualizacion = value, utc_now()
    sesion.flush()
    return {int(h): v for h, v in value.items()}
