"""
Relación clima-casos (EDA, fase 5): anomalías respecto de la climatología,
correlación cruzada con rezagos y remuestreo por bloques.

Todo se calcula en memoria para describir. Las anomalías usan la
climatología de todo el periodo: sirven para quitar el calendario al
describir, pero en el modelado una climatología solo puede salir de datos de
entrenamiento.
"""

import numpy as np
import pandas as pd


def anomalia(df: pd.DataFrame, columna: str, por: tuple[str, ...] = ("ubigeo", "semana")) -> pd.Series:
    """
    `columna` menos su media por grupo (por defecto distrito × semana
    epidemiológica). La semana 53 se agrupa con la 52.
    """
    claves = [df[c].clip(upper=52) if c == "semana" else df[c] for c in por]
    return df[columna] - df.groupby(claves)[columna].transform("mean")


def rezagar(df: pd.DataFrame, columna: str, rezago: int, grupo: str = "ubigeo") -> pd.Series:
    """Valor de `columna` `rezago` semanas antes, dentro de cada grupo (df ordenado por grupo y fecha)."""
    return df.groupby(grupo)[columna].shift(rezago)


def correlacion_rezagada(df: pd.DataFrame, x: str, y: str, rezagos: range, grupo: str | None = "ubigeo",
                         metodo: str = "spearman", min_obs: int = 30) -> pd.DataFrame:
    """
    Correlación entre y(t) y x(t - rezago) para cada rezago. Con `grupo`, se
    calcula dentro de cada grupo (filas = grupo, columnas = rezago); sin
    grupo, sobre toda la serie (una fila). Grupos con menos de `min_obs`
    pares o sin variación devuelven NaN.
    """
    def una(g):
        fila = {}
        for r in rezagos:
            xs = g[x].shift(r)
            m = xs.notna() & g[y].notna()
            if m.sum() < min_obs or xs[m].nunique() < 2 or g.loc[m, y].nunique() < 2:
                fila[r] = np.nan
            else:
                fila[r] = xs[m].corr(g.loc[m, y], method=metodo)
        return pd.Series(fila)

    if grupo is None:
        return una(df).to_frame().T
    return pd.DataFrame({k: una(g) for k, g in df.groupby(grupo)}).T


def bootstrap_bloques(datos: pd.DataFrame, bloque: str, estadistico, n: int = 1000, semilla: int = 42) -> np.ndarray:
    """Remuestrea bloques completos (p. ej. temporadas) con reemplazo y devuelve el estadístico de cada réplica."""
    rng = np.random.default_rng(semilla)
    grupos = {k: g for k, g in datos.groupby(bloque)}
    claves = list(grupos)
    return np.array([estadistico(pd.concat([grupos[k] for k in rng.choice(claves, len(claves), replace=True)]))
                     for _ in range(n)])


def correlacion_parcial_spearman(x: pd.Series, y: pd.Series, z: pd.Series) -> float:
    """
    Correlación parcial de Spearman entre x e y controlando por z: se pasan
    las tres a rangos, se quita a x e y la parte lineal explicada por z y se
    correlacionan los residuos. Filas con nulos se descartan.
    """
    d = pd.DataFrame({"x": x, "y": y, "z": z}).dropna().rank()
    if len(d) < 10:
        return np.nan
    zc = d["z"] - d["z"].mean()
    res = {c: (d[c] - d[c].mean()) - zc * ((d[c] - d[c].mean()) @ zc) / (zc @ zc) for c in ("x", "y")}
    return float(np.corrcoef(res["x"], res["y"])[0, 1])


def centro_estacional(valores: pd.Series) -> float:
    """
    Semana "centro de masa" circular de un perfil semanal (índice = semana
    1..52, valores >= 0). Resume en qué momento del año se concentra la
    variable, sin depender de un pico puntual.
    """
    w = np.asarray(valores, float)
    ang = 2 * np.pi * (np.asarray(valores.index, float) - 1) / 52
    a = np.arctan2((w * np.sin(ang)).sum(), (w * np.cos(ang)).sum())
    return float((a % (2 * np.pi)) * 52 / (2 * np.pi) + 1)
