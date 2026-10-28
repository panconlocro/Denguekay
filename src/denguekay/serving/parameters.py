"""Reading of ``parametro_sistema``: the database is the authority for thresholds and cutoffs."""

from sqlalchemy import select

from denguekay.db.models import SystemParameter, utc_now
from denguekay.db.session import upsert


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


def acceptance_criteria(sesion):
    """Translate umbrales_aceptacion to the format of denguekay.evaluation.acceptance."""
    u = read(sesion, "umbrales_aceptacion")
    return {"bloques": [u["bloque"]], "recall_minimo": u["recall"], "precision_minima": u["precision"],
            "f1_minimo": u["f1"], "proporcion_error_persistencia": u["razon_error_base"]}


def experimental_selection(sesion):
    """{horizon: {task: code}}; empty if it was not seeded."""
    value = sesion.scalar(select(SystemParameter.valor).where(SystemParameter.clave == "seleccion_experimental"))
    return {int(h): v for h, v in (value or {}).items()}


def seed_experimental_selection(sesion, selection):
    """Seed from config.yaml without overwriting an existing value (ON CONFLICT DO NOTHING)."""
    upsert(sesion, SystemParameter.__table__, [{
        "clave": "seleccion_experimental", "valor": {str(h): v for h, v in selection.items()},
        "descripcion": "Desviación temporal: versiones candidatas que se sirven como experimentales "
                       "mientras no haya una versión activa que cumpla los umbrales",
        "fecha_actualizacion": utc_now()}], ["clave"], update=())
