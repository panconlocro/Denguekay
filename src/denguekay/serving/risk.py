"""Nivel de riesgo y cambio de alerta según los parámetros del documento OE2."""

import math

NIVELES = ("bajo", "medio", "alto", "muy_alto")
NIVELES_ALERTA = ("alto", "muy_alto")
ETIQUETAS = {"bajo": "Bajo", "medio": "Medio", "alto": "Alto", "muy_alto": "Muy alto"}


def nivel_riesgo(probabilidad, cortes):
    """Intervalos cerrados a la izquierda con los cortes de parametro_sistema."""
    if probabilidad is None:
        return None
    if not math.isfinite(probabilidad) or not 0 <= probabilidad <= 1:
        raise ValueError("La probabilidad debe ser finita y estar entre cero y uno")
    if probabilidad >= cortes["muy_alto"]:
        return "muy_alto"
    if probabilidad >= cortes["alto"]:
        return "alto"
    if probabilidad >= cortes["medio"]:
        return "medio"
    return "bajo"


def cambio_alerta(nivel_anterior, nivel_actual):
    """Compara con la alerta activa del corte anterior del mismo distrito y horizonte."""
    if nivel_anterior is None:
        return "nueva"
    if nivel_anterior == nivel_actual:
        return "se_mantiene"
    return "sube_nivel" if NIVELES.index(nivel_actual) > NIVELES.index(nivel_anterior) else "baja_nivel"
