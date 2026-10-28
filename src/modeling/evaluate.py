"""Métricas comparables para conteos y alertas de semana elevada."""

import numpy as np
from sklearn.metrics import average_precision_score


def alertas_desde_conteos(
    conteos: np.ndarray, umbrales: np.ndarray, minimo_casos: int,
) -> np.ndarray:
    """Aplica a pronósticos de casos la regla usada para etiquetar gold."""
    pred = np.asarray(conteos, dtype=float)
    umbral = np.asarray(umbrales, dtype=float)
    if pred.shape != umbral.shape or not np.isfinite(pred).all() or not np.isfinite(umbral).all():
        raise ValueError("Conteos y umbrales deben ser finitos y estar alineados")
    if minimo_casos < 1:
        raise ValueError("minimo_casos debe ser positivo")
    return (pred > umbral) & (pred >= minimo_casos)


def metricas_conteos(real: np.ndarray, pred: np.ndarray) -> dict[str, float]:
    """Calcula errores de conteo sobre una misma partición."""
    real, pred = np.asarray(real, float), np.asarray(pred, float)
    if real.shape != pred.shape or not len(real) or not np.isfinite(real).all() or not np.isfinite(pred).all():
        raise ValueError("Conteos reales y predichos inválidos")
    if (real < 0).any() or (pred < 0).any():
        raise ValueError("Los conteos no pueden ser negativos")
    return {
        "mae": float(np.mean(np.abs(real - pred))),
        "rmse": float(np.sqrt(np.mean((real - pred) ** 2))),
        "mae_log1p": float(np.mean(np.abs(np.log1p(real) - np.log1p(pred)))),
        "sesgo_medio": float(np.mean(pred - real)),
    }


def metricas_alerta(
    real: np.ndarray, pred: np.ndarray, *, puntaje: np.ndarray | None = None,
) -> dict[str, float | int | None]:
    """Reporta aciertos, falsos avisos, precisión, recall, F1 y AUPRC.

    AUPRC queda indefinida si no hay positivos reales. ``puntaje`` puede ser
    probabilidad de clasificación o margen de casos sobre el umbral histórico.
    """
    y, z = np.asarray(real), np.asarray(pred)
    if y.shape != z.shape or not len(y) or not np.isin(y, [0, 1]).all() or not np.isin(z, [0, 1]).all():
        raise ValueError("Las alertas deben ser binarias y estar alineadas")
    y, z = y.astype(bool), z.astype(bool)
    vp = int(np.sum(y & z))
    fp = int(np.sum(~y & z))
    fn = int(np.sum(y & ~z))
    vn = int(np.sum(~y & ~z))
    precision = vp / (vp + fp) if vp + fp else None
    recall = vp / (vp + fn) if vp + fn else None
    f1 = 2 * vp / (2 * vp + fp + fn) if 2 * vp + fp + fn else None
    auprc = None
    if puntaje is not None:
        s = np.asarray(puntaje, dtype=float)
        if s.shape != y.shape or not np.isfinite(s).all():
            raise ValueError("Puntajes de alerta inválidos")
        if y.any():
            auprc = float(average_precision_score(y, s))
    return {
        "n": len(y), "positivos": int(y.sum()), "vp": vp, "fp": fp,
        "fn": fn, "vn": vn, "precision": precision, "recall": recall,
        "f1": f1, "auprc": auprc,
    }


def seleccionar_umbral_f1(
    real: np.ndarray, probabilidad: np.ndarray,
    candidatos: np.ndarray | None = None,
) -> dict[str, float]:
    """Fija el umbral solo con predicciones fuera de muestra de validación.

    Si hay empates de F1, elige el umbral más alto (menos falsos avisos).
    """
    y = np.asarray(real)
    p = np.asarray(probabilidad, dtype=float)
    if y.shape != p.shape or not len(y) or not np.isin(y, [0, 1]).all() or not np.isfinite(p).all() or not ((0 <= p) & (p <= 1)).all():
        raise ValueError("Validación binaria/probabilidades inválidas")
    if not np.any(y == 1):
        raise ValueError("No hay positivos de validación para fijar umbral")
    if candidatos is None:
        candidatos = np.arange(0.05, 0.951, 0.025)
    opciones = sorted(float(x) for x in candidatos)
    if not opciones or opciones[0] <= 0 or opciones[-1] >= 1:
        raise ValueError("Los umbrales candidatos deben pertenecer a (0, 1)")
    evaluados = [(metricas_alerta(y, p >= t)["f1"], t) for t in opciones]
    mejor_f1, mejor_umbral = max(evaluados, key=lambda par: (par[0], par[1]))
    return {"umbral": mejor_umbral, "f1_validacion_agregado": float(mejor_f1)}
