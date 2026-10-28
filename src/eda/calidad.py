"""
Chequeos de integridad y calidad del panel distrito-semana (EDA, fase 1).

Todas las funciones son de solo lectura: reciben un DataFrame, devuelven
tablas o conteos de problemas y no modifican ni corrigen los datos.
"""

import numpy as np
import pandas as pd

# Conserva el import utilizado por los notebooks y consumidores anteriores.
from src.utils.calendario import semana_epi_mmwr


def columnas_identicas(df: pd.DataFrame, columnas: list[str] | None = None) -> list[tuple[str, str]]:
    """Pares de columnas con exactamente los mismos valores en todas las filas."""
    columnas = columnas or list(df.columns)
    pares = []
    for i, a in enumerate(columnas):
        for b in columnas[i + 1:]:
            if df[a].equals(df[b]):
                pares.append((a, b))
    return pares


def distritos_con_serie_identica(df: pd.DataFrame, columna: str,
                                 decimales: int = 6) -> list[list[str]]:
    """
    Grupos de distritos (ubigeo) cuya serie semanal de `columna` es idéntica
    en todas las semanas. Útil para detectar distritos que comparten la misma
    celda de la rejilla climática.
    """
    ancho = df.pivot(index="semana_inicio", columns="ubigeo", values=columna).round(decimales)
    firmas = ancho.T.apply(lambda fila: hash(tuple(fila)), axis=1)
    grupos = [sorted(v) for v in firmas.groupby(firmas).groups.values() if len(v) > 1]
    return sorted(grupos)


def resumen_variabilidad(df: pd.DataFrame, columnas: list[str]) -> pd.DataFrame:
    """
    Para cada columna: valores distintos, proporción del valor más frecuente y
    proporción de ceros. Sirve para detectar columnas constantes o casi constantes.
    """
    filas = []
    for c in columnas:
        s = df[c]
        filas.append({
            "columna": c,
            "n_distintos": int(s.nunique()),
            "prop_moda": float(s.value_counts(normalize=True).iloc[0]),
            "prop_ceros": float((s == 0).mean()),
        })
    return pd.DataFrame(filas).set_index("columna")


def reglas_consistencia(df: pd.DataFrame) -> pd.Series:
    """
    Número de filas que violan cada regla física o de consistencia interna.
    Solo evalúa las reglas cuyas columnas existen en `df`.
    """
    fr = [c for c in df.columns if c.startswith("fraccion_")]
    reglas = {
        "temp_min > temp_media": lambda d: d["temp_min"] > d["temp_media"],
        "temp_media > temp_max": lambda d: d["temp_media"] > d["temp_max"],
        "hum_rel_media fuera de [0, 100]": lambda d: ~d["hum_rel_media"].between(0, 100),
        "precip_total_mm < 0": lambda d: d["precip_total_mm"] < 0,
        "lluvia_total_mm > precip_total_mm": lambda d: d["lluvia_total_mm"] > d["precip_total_mm"],
        "viento_max < 0": lambda d: d["viento_max"] < 0,
        "radiacion_total < 0": lambda d: d["radiacion_total"] < 0,
        "et0_total < 0": lambda d: d["et0_total"] < 0,
        "poblacion <= 0": lambda d: d["poblacion"] <= 0,
        "alguna fraccion_* fuera de [0, 1]": lambda d: ~d[fr].apply(lambda s: s.between(0, 1)).all(axis=1),
        "agua_red + agua_cisterna > 1": lambda d: d["fraccion_agua_red"] + d["fraccion_agua_cisterna"] > 1,
        "desague_red + sin_saneamiento > 1": lambda d: d["fraccion_desague_red"] + d["fraccion_sin_saneamiento"] > 1,
        "casos_Dengue negativo o no entero": lambda d: (d["casos_Dengue"] < 0) | (d["casos_Dengue"] % 1 != 0),
    }
    resultado = {}
    for nombre, regla in reglas.items():
        try:
            resultado[nombre] = int(regla(df).sum())
        except KeyError:
            continue
    return pd.Series(resultado, name="filas_que_violan")


def variacion_intra_anual(df: pd.DataFrame, columnas: list[str]) -> pd.Series:
    """
    Cuántos pares distrito-año tienen más de un valor distinto en cada columna.
    Para variables anuales (sociodemografía) lo esperado es 0.
    """
    n = df.groupby(["ubigeo", "anio"])[columnas].nunique()
    return (n > 1).sum().rename("distrito_anios_con_variacion")


def desvio_de_linea_recta(anual: pd.DataFrame, columnas: list[str],
                          anio_ini: int = 2017, anio_fin: int = 2025) -> pd.DataFrame:
    """
    Máxima diferencia absoluta, por distrito y columna, entre el valor anual y
    la recta que une `anio_ini` con `anio_fin`. `anual` debe tener una fila por
    (ubigeo, anio). Un valor ~0 indica interpolación lineal entre los extremos.
    """
    filas = []
    for ubigeo, g in anual.groupby("ubigeo"):
        g = g.set_index("anio").sort_index()
        t = (g.index - anio_ini) / (anio_fin - anio_ini)
        fila = {"ubigeo": ubigeo}
        for c in columnas:
            recta = g.loc[anio_ini, c] + t * (g.loc[anio_fin, c] - g.loc[anio_ini, c])
            fila[c] = float(np.abs(g[c].to_numpy() - np.asarray(recta)).max())
        filas.append(fila)
    return pd.DataFrame(filas).set_index("ubigeo")


def z_robusto(df: pd.DataFrame, columna: str, por: str | list[str]) -> pd.Series:
    """
    z robusto = (x - mediana) / (1.4826 * MAD), calculado dentro de cada grupo
    `por` (p. ej. el distrito o la semana). Grupos con MAD = 0 devuelven NaN.
    """
    g = df.groupby(por)[columna]
    mediana = g.transform("median")
    mad = (df[columna] - mediana).abs().groupby([df[p] for p in np.atleast_1d(por)]).transform("median")
    return (df[columna] - mediana) / (1.4826 * mad.replace(0, np.nan))
