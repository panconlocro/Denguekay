"""Probabilidad, riesgo visible y umbral F1 son criterios distintos."""

import math


def nivel_riesgo(probabilidad, cortes):
    """Clasifica los bordes por intervalos cerrados a la izquierda."""
    if probabilidad is None:
        return "Sin datos"
    if not math.isfinite(probabilidad) or not 0 <= probabilidad <= 1:
        raise ValueError("La probabilidad debe ser finita y estar entre cero y uno")
    if probabilidad >= cortes["muy_alto"]:
        return "Muy alto"
    if probabilidad >= cortes["alto"]:
        return "Alto"
    if probabilidad >= cortes["medio"]:
        return "Medio"
    return "Bajo"


def genera_alerta(nivel, minimo="Alto"):
    """La alerta visible usa el nivel configurado, independiente del F1."""
    if minimo not in ("Alto", "Muy alto"):
        raise ValueError("Nivel mínimo de alerta inválido")
    return nivel in (("Alto", "Muy alto") if minimo == "Alto" else ("Muy alto",))


def disponibilidad_modelo(version, servir_no_validadas):
    """No presenta una versión experimental como validada ni rellena faltantes."""
    if version is None:
        return {"disponible": False, "motivo": "No hay versión de modelo disponible"}
    if not servir_no_validadas and version.estado_validacion == "experimental":
        return {"disponible": False, "motivo": "Predicción no disponible: modelo no validado"}
    return {"disponible": True, "motivo": None}
