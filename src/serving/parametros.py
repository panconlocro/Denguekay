"""Lectura de ``parametro_sistema``: la BD es la autoridad de umbrales y cortes."""

from sqlalchemy import select

from src.db.modelos import ParametroSistema, ahora_utc
from src.db.sesion import upsert


class ParametroFaltante(ValueError):
    """La BD no tiene un parámetro obligatorio (¿falta alembic upgrade head?)."""


def leer(sesion, clave):
    valor = sesion.scalar(select(ParametroSistema.valor).where(ParametroSistema.clave == clave))
    if valor is None:
        raise ParametroFaltante(f"Falta el parámetro {clave} en parametro_sistema")
    return valor


def cortes_riesgo(sesion):
    cortes = leer(sesion, "cortes_riesgo")
    if not 0 < cortes["medio"] < cortes["alto"] < cortes["muy_alto"] < 1:
        raise ValueError("cortes_riesgo debe ser creciente y estar entre 0 y 1")
    return cortes


def criterios_aceptacion(sesion):
    """Traduce umbrales_aceptacion al formato de src.validation.validacion_modelo."""
    u = leer(sesion, "umbrales_aceptacion")
    return {"bloques": [u["bloque"]], "recall_minimo": u["recall"], "precision_minima": u["precision"],
            "f1_minimo": u["f1"], "proporcion_error_persistencia": u["razon_error_base"]}


def seleccion_experimental(sesion):
    """{horizonte: {tarea: codigo}}; vacío si no se sembró."""
    valor = sesion.scalar(select(ParametroSistema.valor).where(ParametroSistema.clave == "seleccion_experimental"))
    return {int(h): v for h, v in (valor or {}).items()}


def sembrar_seleccion_experimental(sesion, seleccion):
    """Siembra desde config.yaml sin pisar un valor ya existente (ON CONFLICT DO NOTHING)."""
    upsert(sesion, ParametroSistema.__table__, [{
        "clave": "seleccion_experimental", "valor": {str(h): v for h, v in seleccion.items()},
        "descripcion": "Desviación temporal: versiones candidatas que se sirven como experimentales "
                       "mientras no haya una versión activa que cumpla los umbrales",
        "fecha_actualizacion": ahora_utc()}], ["clave"], actualizar=())
