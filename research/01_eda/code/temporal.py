"""
Dinámica temporal del objetivo (EDA, fase 3): autocorrelación, perfil
estacional, temporadas epidemiológicas y líneas base ingenuas.

Todo se calcula en memoria para describir la serie; las líneas base solo
dimensionan la dificultad del pronóstico, no son modelos del proyecto.
"""

import numpy as np
import pandas as pd

OBJETIVO = "casos_Dengue"


def acf_simple(x: np.ndarray, nlags: int) -> np.ndarray:
    """Autocorrelación muestral (rezagos 0..nlags) de una serie sin nulos."""
    x = np.asarray(x, dtype=float) - np.mean(x)
    den = np.sum(x ** 2)
    if den == 0:
        return np.full(nlags + 1, np.nan)
    return np.array([1.0] + [np.sum(x[k:] * x[:-k]) / den for k in range(1, nlags + 1)])


def acf_por_grupo(df: pd.DataFrame, columna: str, nlags: int, grupo: str = "ubigeo") -> pd.DataFrame:
    """ACF de `columna` dentro de cada grupo (filas = grupo, columnas = rezago)."""
    return pd.DataFrame({g: acf_simple(s.to_numpy(), nlags) for g, s in df.groupby(grupo)[columna]}).T


def perfil_normalizado(df: pd.DataFrame) -> pd.DataFrame:
    """Casos regionales por semana epidemiológica (filas) y año (columnas), divididos por el máximo de cada año."""
    tabla = df.groupby(["anio", "semana"])[OBJETIVO].sum().unstack("anio")
    return tabla / tabla.max()


def semana_valle(perfil: pd.DataFrame, desde: int = 27) -> int:
    """Semana epidemiológica (>= `desde`) con la menor mediana del perfil normalizado entre años."""
    mediana = perfil.median(axis=1)
    return int(mediana.loc[desde:52].idxmin())


def asignar_temporada(anio: pd.Series, semana: pd.Series, semana_inicio: int) -> pd.Series:
    """
    Temporada epidemiológica: de la semana `semana_inicio` del año Y-1 a la
    semana `semana_inicio` - 1 del año Y; se etiqueta con Y.
    """
    return anio + (semana >= semana_inicio).astype(int)


def prediccion_persistencia(df: pd.DataFrame, columna: str, h: int) -> pd.Series:
    """Predicción ingenua para la fila t: el valor observado h semanas antes en el mismo distrito."""
    return df.groupby("ubigeo")[columna].shift(h)


def prediccion_estacional(df: pd.DataFrame, columna: str) -> pd.Series:
    """
    Predicción ingenua estacional para la fila t: el valor del mismo distrito en
    la misma semana epidemiológica del año anterior (alinea por anio/semana, no
    por número de filas, para que la semana 53 de 2020 no desplace a 2021). La
    semana 53 se compara con la semana 52 del año anterior.
    """
    previo = df[["ubigeo", "anio", "semana", columna]].rename(columns={columna: "_prev"})
    previo = previo.assign(anio=previo["anio"] + 1)
    clave = df[["ubigeo", "anio"]].assign(semana=df["semana"].clip(upper=52))
    return pd.Series(clave.merge(previo, on=["ubigeo", "anio", "semana"], how="left")["_prev"].to_numpy(), index=df.index)


def metricas_binarias(real: pd.Series, pred: pd.Series) -> dict:
    """
    Precisión, sensibilidad (recall) y F1 de una predicción binaria; ignora
    filas con nulos. Sin positivos predichos la precisión no está definida
    (NaN); sin positivos reales, ni la sensibilidad ni el F1 lo están (NaN).
    Con positivos reales y ningún acierto, el F1 es 0.
    """
    m = real.notna() & pred.notna()
    r, p = real[m].astype(bool), pred[m].astype(bool)
    vp, fp, fn = int((r & p).sum()), int((~r & p).sum()), int((r & ~p).sum())
    precision = vp / (vp + fp) if vp + fp else np.nan
    recall = vp / (vp + fn) if vp + fn else np.nan
    if np.isnan(recall):
        f1 = np.nan
    elif vp == 0:
        f1 = 0.0
    else:
        f1 = 2 * precision * recall / (precision + recall)
    return {"n": int(m.sum()), "positivos": int(r.sum()), "precision": precision, "recall": recall, "f1": f1}
