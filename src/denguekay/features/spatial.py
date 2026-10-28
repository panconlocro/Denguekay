"""
Spatial weights between district centroids (great-circle distances, k nearest
neighbours and inverse distance), computed in memory with numpy.

The rest of the EDA's spatial analysis (Moran's I, lagged neighbour status,
Mantel tests) is frozen in research/01_eda/code/espacial.py.
"""

import numpy as np

EARTH_RADIUS_KM = 6371.0


def distances_km(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """Great-circle (haversine) distance matrix between points, in km."""
    la, lo = np.radians(np.asarray(lat, float)), np.radians(np.asarray(lon, float))
    dla = la[:, None] - la[None, :]
    dlo = lo[:, None] - lo[None, :]
    h = np.sin(dla / 2) ** 2 + np.cos(la[:, None]) * np.cos(la[None, :]) * np.sin(dlo / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(h, 0, 1)))


def knn_weights(dist: np.ndarray, k: int) -> np.ndarray:
    """Weights of the k nearest neighbours (excluding the point itself), row-standardised."""
    n = dist.shape[0]
    d = dist.copy()
    np.fill_diagonal(d, np.inf)
    w = np.zeros_like(d)
    idx = np.argsort(d, axis=1)[:, :k]
    w[np.arange(n)[:, None], idx] = 1.0
    return w / w.sum(axis=1, keepdims=True)


def inverse_distance_weights(dist: np.ndarray, power: float = 1.0) -> np.ndarray:
    """Weights 1/d^power (zero diagonal), row-standardised."""
    with np.errstate(divide="ignore"):
        w = 1.0 / dist ** power
    np.fill_diagonal(w, 0.0)
    return w / w.sum(axis=1, keepdims=True)
