"""
Sociodemografía (EDA, fase 6): colinealidad entre variables de corte
transversal, componentes principales, correlación con intervalo por
bootstrap y límites de embudo para tasas.

Todo se calcula en memoria sobre una fila por distrito; nada se guarda en data/.
"""

import numpy as np
import pandas as pd


def vif(X: pd.DataFrame) -> pd.Series:
    """
    Factor de inflación de la varianza de cada columna: 1 / (1 - R²) de la
    regresión lineal de esa columna sobre las demás (con intercepto).
    """
    A = X.to_numpy(float)
    salida = {}
    for j, c in enumerate(X.columns):
        y = A[:, j]
        Z = np.column_stack([np.ones(len(A)), np.delete(A, j, axis=1)])
        beta, *_ = np.linalg.lstsq(Z, y, rcond=None)
        r2 = 1 - ((y - Z @ beta) ** 2).sum() / ((y - y.mean()) ** 2).sum()
        salida[c] = np.inf if r2 >= 1 else 1 / (1 - r2)
    return pd.Series(salida, name="vif")


def componentes_principales(X: pd.DataFrame, n: int = 3) -> tuple[pd.Series, pd.DataFrame, pd.DataFrame]:
    """
    PCA sobre las columnas estandarizadas. Devuelve (proporción de varianza
    explicada por componente, cargas [columnas x componentes], puntajes
    [filas x componentes]). El signo de cada componente se fija para que su
    carga de mayor valor absoluto sea positiva.
    """
    Z = (X - X.mean()) / X.std(ddof=1)
    U, s, Vt = np.linalg.svd(Z.to_numpy(float), full_matrices=False)
    for k in range(len(s)):
        if Vt[k, np.argmax(np.abs(Vt[k]))] < 0:
            Vt[k] *= -1
            U[:, k] *= -1
    var = s ** 2 / (s ** 2).sum()
    nombres = [f"CP{i + 1}" for i in range(n)]
    cargas = pd.DataFrame(Vt[:n].T, index=X.columns, columns=nombres)
    puntajes = pd.DataFrame(U[:, :n] * s[:n], index=X.index, columns=nombres)
    return pd.Series(var[:n], index=nombres), cargas, puntajes


def spearman_bootstrap(x: pd.Series, y: pd.Series, n: int = 2000, semilla: int = 42) -> dict:
    """Spearman entre x e y con IC95 % por bootstrap de filas (distritos)."""
    d = pd.DataFrame({"x": x, "y": y}).dropna()
    rho = d["x"].corr(d["y"], method="spearman")
    rng = np.random.default_rng(semilla)
    boot = []
    for _ in range(n):
        m = d.iloc[rng.integers(0, len(d), len(d))]
        if m["x"].nunique() > 1 and m["y"].nunique() > 1:
            boot.append(m["x"].corr(m["y"], method="spearman"))
    lo, hi = np.percentile(boot, [2.5, 97.5])
    return {"rho": float(rho), "ic95_inf": float(lo), "ic95_sup": float(hi), "n": int(len(d))}


def limites_embudo(poblacion: np.ndarray, tasa_global: float, z: float = 1.96) -> tuple[np.ndarray, np.ndarray]:
    """
    Límites aproximados (Poisson, aproximación normal) de la tasa esperada
    para una exposición `poblacion` (persona-periodo) si todos los distritos
    tuvieran `tasa_global` (en la misma unidad, p. ej. casos por habitante).
    """
    p = np.asarray(poblacion, float)
    esperado = tasa_global * p
    de = np.sqrt(esperado)
    return np.clip(esperado - z * de, 0, None) / p, (esperado + z * de) / p
