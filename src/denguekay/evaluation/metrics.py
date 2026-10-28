"""Comparable metrics for counts and high-week alerts."""

import numpy as np
from sklearn.metrics import average_precision_score


def alerts_from_counts(
    counts: np.ndarray, thresholds: np.ndarray, minimo_casos: int,
) -> np.ndarray:
    """Apply to case forecasts the rule used to label gold."""
    pred = np.asarray(counts, dtype=float)
    threshold = np.asarray(thresholds, dtype=float)
    if pred.shape != threshold.shape or not np.isfinite(pred).all() or not np.isfinite(threshold).all():
        raise ValueError("Conteos y umbrales deben ser finitos y estar alineados")
    if minimo_casos < 1:
        raise ValueError("minimo_casos debe ser positivo")
    return (pred > threshold) & (pred >= minimo_casos)


def count_metrics(real: np.ndarray, pred: np.ndarray) -> dict[str, float]:
    """Compute count errors on a single partition."""
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


def alert_metrics(
    real: np.ndarray, pred: np.ndarray, *, score: np.ndarray | None = None,
) -> dict[str, float | int | None]:
    """Report hits, false alarms, precision, recall, F1 and AUPRC.

    AUPRC is undefined if there are no actual positives. ``score`` may be a
    classification probability or a case margin over the historical threshold.
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
    if score is not None:
        s = np.asarray(score, dtype=float)
        if s.shape != y.shape or not np.isfinite(s).all():
            raise ValueError("Puntajes de alerta inválidos")
        if y.any():
            auprc = float(average_precision_score(y, s))
    return {
        "n": len(y), "positivos": int(y.sum()), "vp": vp, "fp": fp,
        "fn": fn, "vn": vn, "precision": precision, "recall": recall,
        "f1": f1, "auprc": auprc,
    }


def select_f1_threshold(
    real: np.ndarray, probability: np.ndarray,
    candidates: np.ndarray | None = None,
) -> dict[str, float]:
    """Set the threshold only with out-of-sample validation predictions.

    On F1 ties, the highest threshold (fewer false alarms) is chosen.
    """
    y = np.asarray(real)
    p = np.asarray(probability, dtype=float)
    if y.shape != p.shape or not len(y) or not np.isin(y, [0, 1]).all() or not np.isfinite(p).all() or not ((0 <= p) & (p <= 1)).all():
        raise ValueError("Validación binaria/probabilidades inválidas")
    if not np.any(y == 1):
        raise ValueError("No hay positivos de validación para fijar umbral")
    if candidates is None:
        candidates = np.arange(0.05, 0.951, 0.025)
    options = sorted(float(x) for x in candidates)
    if not options or options[0] <= 0 or options[-1] >= 1:
        raise ValueError("Los umbrales candidatos deben pertenecer a (0, 1)")
    evaluated = [(alert_metrics(y, p >= t)["f1"], t) for t in options]
    best_f1, best_threshold = max(evaluated, key=lambda pair: (pair[0], pair[1]))
    return {"umbral": best_threshold, "f1_validacion_agregado": float(best_f1)}
