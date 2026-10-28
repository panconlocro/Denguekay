"""Risk level and alert change according to the parameters of the OE2 document."""

import math

LEVELS = ("bajo", "medio", "alto", "muy_alto")
ALERT_LEVELS = ("alto", "muy_alto")
LABELS = {"bajo": "Bajo", "medio": "Medio", "alto": "Alto", "muy_alto": "Muy alto"}


def risk_level(probability, cutoffs):
    """Left-closed intervals with the parametro_sistema cutoffs."""
    if probability is None:
        return None
    if not math.isfinite(probability) or not 0 <= probability <= 1:
        raise ValueError("La probabilidad debe ser finita y estar entre cero y uno")
    if probability >= cutoffs["muy_alto"]:
        return "muy_alto"
    if probability >= cutoffs["alto"]:
        return "alto"
    if probability >= cutoffs["medio"]:
        return "medio"
    return "bajo"


def alert_change(previous_level, current_level):
    """Compare with the active alert of the previous cutoff of the same district and horizon."""
    if previous_level is None:
        return "nueva"
    if previous_level == current_level:
        return "se_mantiene"
    return "sube_nivel" if LEVELS.index(current_level) > LEVELS.index(previous_level) else "baja_nivel"
