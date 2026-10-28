"""
Análisis espacial del objetivo (EDA, fase 4): distancias entre centroides,
pesos espaciales, I de Moran y estado rezagado de los vecinos.

Todo se calcula en memoria con numpy (sin librerías espaciales). El estado de
los vecinos se usa para describir; construirlo como feature le corresponde al
feature engineering.
"""

import numpy as np
import pandas as pd

RADIO_TIERRA_KM = 6371.0


def distancias_km(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """Matriz de distancias de gran círculo (haversine) entre puntos, en km."""
    la, lo = np.radians(np.asarray(lat, float)), np.radians(np.asarray(lon, float))
    dla = la[:, None] - la[None, :]
    dlo = lo[:, None] - lo[None, :]
    h = np.sin(dla / 2) ** 2 + np.cos(la[:, None]) * np.cos(la[None, :]) * np.sin(dlo / 2) ** 2
    return 2 * RADIO_TIERRA_KM * np.arcsin(np.sqrt(np.clip(h, 0, 1)))


def pesos_knn(dist: np.ndarray, k: int) -> np.ndarray:
    """Pesos de los k vecinos más cercanos (sin sí mismo), estandarizados por fila."""
    n = dist.shape[0]
    d = dist.copy()
    np.fill_diagonal(d, np.inf)
    w = np.zeros_like(d)
    idx = np.argsort(d, axis=1)[:, :k]
    w[np.arange(n)[:, None], idx] = 1.0
    return w / w.sum(axis=1, keepdims=True)


def pesos_inverso_distancia(dist: np.ndarray, potencia: float = 1.0) -> np.ndarray:
    """Pesos 1/d^potencia (diagonal 0), estandarizados por fila."""
    with np.errstate(divide="ignore"):
        w = 1.0 / dist ** potencia
    np.fill_diagonal(w, 0.0)
    return w / w.sum(axis=1, keepdims=True)


def moran_i(x: np.ndarray, w: np.ndarray, permutaciones: int = 999, semilla: int = 42) -> dict:
    """
    I de Moran global con prueba por permutación (dos colas sobre la
    distribución permutada). `w` no necesita ser simétrica.
    """
    x = np.asarray(x, float)
    z = x - x.mean()
    n, s0 = len(x), w.sum()

    def estadistico(v):
        return (n / s0) * (v @ w @ v) / (v @ v)

    i_obs = estadistico(z)
    rng = np.random.default_rng(semilla)
    perm = np.array([estadistico(rng.permutation(z)) for _ in range(permutaciones)])
    esperado = -1.0 / (n - 1)
    p = (np.sum(np.abs(perm - perm.mean()) >= abs(i_obs - perm.mean())) + 1) / (permutaciones + 1)
    return {"I": float(i_obs), "esperado": esperado, "p_valor": float(p),
            "media_perm": float(perm.mean()), "sd_perm": float(perm.std())}


def estado_vecinos_rezagado(df: pd.DataFrame, marca: str, w: np.ndarray, ubigeos: list[str], h: int) -> pd.Series:
    """
    Para cada fila (distrito, semana t): promedio ponderado por `w` de `marca`
    en los demás distritos en la semana t − h. `ubigeos` fija el orden de las
    filas/columnas de `w`. Solo usa información pasada (t − h).
    """
    ancho = df.pivot(index="semana_inicio", columns="ubigeo", values=marca)[ubigeos].astype(float)
    vecinos = pd.DataFrame(ancho.to_numpy() @ w.T, index=ancho.index,
                           columns=pd.Index(ubigeos, name="ubigeo")).shift(h)
    largo = vecinos.stack().rename("_v").reset_index()
    return df[["semana_inicio", "ubigeo"]].merge(largo, on=["semana_inicio", "ubigeo"], how="left")["_v"].set_axis(df.index)


def rr_mantel_haenszel(expuesto: pd.Series, desenlace: pd.Series, estrato: pd.Series) -> float:
    """
    Razón de riesgos de Mantel-Haenszel: sum(a*n0/N) / sum(c*n1/N) sobre los
    estratos, con a/c = desenlaces en expuestos/no expuestos y n1/n0 sus
    tamaños. Omite estratos sin expuestos o sin no expuestos.
    """
    d = pd.DataFrame({"e": expuesto.astype(bool), "y": desenlace.astype(bool), "s": estrato})
    num = den = 0.0
    for _, g in d.groupby("s", observed=True):
        n1, n0 = int(g["e"].sum()), int((~g["e"]).sum())
        if n1 == 0 or n0 == 0:
            continue
        N = n1 + n0
        num += g.loc[g["e"], "y"].sum() * n0 / N
        den += g.loc[~g["e"], "y"].sum() * n1 / N
    return num / den if den else np.nan


def mantel(a: np.ndarray, b: np.ndarray, permutaciones: int = 999, semilla: int = 42) -> dict:
    """
    Prueba de Mantel: correlación de Spearman entre los triángulos superiores
    de dos matrices cuadradas, con p-valor por permutación conjunta de filas y
    columnas de `a` (dos colas).
    """
    from scipy.stats import spearmanr
    n = a.shape[0]
    iu = np.triu_indices(n, 1)
    obs = spearmanr(a[iu], b[iu]).statistic
    rng = np.random.default_rng(semilla)
    perm = []
    for _ in range(permutaciones):
        p = rng.permutation(n)
        perm.append(spearmanr(a[np.ix_(p, p)][iu], b[iu]).statistic)
    perm = np.array(perm)
    pval = (np.sum(np.abs(perm) >= abs(obs)) + 1) / (permutaciones + 1)
    return {"rho": float(obs), "p_valor": float(pval)}
