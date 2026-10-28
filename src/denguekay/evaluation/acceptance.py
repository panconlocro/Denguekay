"""HU0007-4 thresholds applied to saved metrics, without mixing blocks."""

import math


def evaluate_model_validation(kind, metrics, criteria):
    """Return status, criteria and reasons; 2025 does not decide by default.

    The time protocol is still the existing one. This function checks its
    saved results; it does not evaluate the final booster on training data.
    The choice of blocks and thresholds is kept in each version.
    """
    if kind == "persistencia":
        return {"estado_validacion": "referencia", "disponible": True,
                "motivo": "Línea base de comparación, sin validación como modelo operativo", "bloques": {}}
    results = {}
    blocks = criteria.get("bloques", [])
    if kind not in {"clasificacion", "regresion"} or not blocks:
        return {"estado_validacion": "experimental", "disponible": False,
                "motivo": "No hay criterios de validación completos", "bloques": {}}
    for name in blocks:
        fold = metrics.get("bloques", {}).get(name)
        checks, reasons = {}, []
        if not isinstance(fold, dict):
            reasons.append("No hay métricas guardadas para el bloque requerido")
        else:
            if kind == "clasificacion":
                values = fold.get(kind, {}).get("alerta_directa", {})
                pairs = [(m, values.get(m), criteria.get(c)) for m, c in
                         (("recall", "recall_minimo"), ("precision", "precision_minima"), ("f1", "f1_minimo"))]
            else:
                values = fold.get(kind, {}).get("conteos", {})
                reference = fold.get("persistencia", {}).get("conteos", {})
                factor = criteria.get("proporcion_error_persistencia")
                pairs = []
                for m in ("mae", "rmse"):
                    base = reference.get(m)
                    limit = factor * base if _finite(factor) and _finite(base) and base >= 0 else None
                    pairs.append((m, values.get(m), limit))
            for metric, value, limit in pairs:
                available = _finite(value) and _finite(limit) and value >= 0 and limit >= 0
                meets = available and (value >= limit if kind == "clasificacion" else value <= limit)
                checks[metric] = {"valor": value, "limite": limit,
                                  "disponible": available, "cumple": meets}
                if not available:
                    reasons.append(f"Métrica o referencia no disponible: {metric}")
                elif not meets:
                    reasons.append(f"No cumple el umbral de {metric}")
        results[name] = {"cumple": bool(checks) and all(c["cumple"] for c in checks.values()),
                              "criterios": checks, "motivos": reasons}
    approved = all(b["cumple"] for b in results.values())
    complete = all(b["criterios"] and all(c["disponible"] for c in b["criterios"].values()) for b in results.values())
    return {"estado_validacion": "validado" if approved else "experimental",
            "disponible": complete, "motivo": None if approved else "; ".join(
                f"{name}: {reason}" for name, b in results.items() for reason in b["motivos"]),
            "bloques": results}


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
