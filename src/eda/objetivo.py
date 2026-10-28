"""
Análisis de la variable objetivo (EDA, fase 2): concentración, episodios y
definiciones candidatas de brote.

Todo se calcula en memoria para *describir* el objetivo. Nada de esto es una
feature ni se guarda en data/: la definición de brote la decide el equipo.
"""

import numpy as np
import pandas as pd

OBJETIVO = "casos_Dengue"


def tasa_100k(casos: pd.Series, poblacion: pd.Series) -> pd.Series:
    """Casos por 100 000 habitantes."""
    return casos / poblacion * 1e5


def curva_concentracion(valores: pd.Series) -> pd.DataFrame:
    """
    Curva de concentración: unidades ordenadas de mayor a menor y proporción
    acumulada del total. Devuelve columnas `prop_unidades` y `prop_acumulada`.
    """
    v = valores.sort_values(ascending=False)
    total = v.sum()
    return pd.DataFrame({
        "prop_unidades": np.arange(1, len(v) + 1) / len(v),
        "prop_acumulada": (v.cumsum() / total).to_numpy() if total > 0 else np.zeros(len(v)),
    }, index=v.index)


def unidades_para_fraccion(valores: pd.Series, fraccion: float) -> int:
    """Mínimo número de unidades (ordenadas de mayor a menor) que suman `fraccion` del total."""
    acumulada = valores.sort_values(ascending=False).cumsum() / valores.sum()
    return int((acumulada < fraccion).sum() + 1)


def rachas(df: pd.DataFrame, marca: str, grupo: str = "ubigeo", fecha: str = "semana_inicio") -> pd.DataFrame:
    """
    Episodios = rachas de semanas consecutivas con `marca` verdadera dentro de
    cada `grupo`. `df` debe estar ordenado por grupo y fecha, sin huecos.
    Devuelve una fila por episodio: grupo, inicio, fin, duración (semanas) y
    casos totales y máximos si la columna objetivo está presente.
    """
    d = df[[grupo, fecha, marca] + ([OBJETIVO] if OBJETIVO in df else [])].copy()
    d[marca] = d[marca].astype(bool)
    nuevo = d[marca] & ~d.groupby(grupo)[marca].shift(fill_value=False)
    d["_id"] = nuevo.groupby(d[grupo]).cumsum()
    d = d[d[marca]]
    agg = {"inicio": (fecha, "min"), "fin": (fecha, "max"), "duracion": (fecha, "size")}
    if OBJETIVO in d:
        agg.update(casos=(OBJETIVO, "sum"), casos_max=(OBJETIVO, "max"))
    return d.groupby([grupo, "_id"]).agg(**agg).reset_index().drop(columns="_id")


# --- Definiciones candidatas de brote (todas devuelven una Serie booleana alineada a df) ---

def brote_umbral_tasa(df: pd.DataFrame, umbral: float) -> pd.Series:
    """D1: tasa semanal por 100 000 hab. mayor o igual a `umbral`."""
    return tasa_100k(df[OBJETIVO], df["poblacion"]) >= umbral


def brote_percentil_distrito(df: pd.DataFrame, q: float = 0.9) -> pd.Series:
    """
    D2: casos por encima del percentil `q` de la serie completa del propio
    distrito, y al menos 1 caso. Usa todo el periodo (incluye el futuro): sirve
    para describir, pero en el modelado el percentil debe salir solo de datos
    de entrenamiento.
    """
    p = df.groupby("ubigeo")[OBJETIVO].transform(lambda s: s.quantile(q))
    return (df[OBJETIVO] > p) & (df[OBJETIVO] >= 1)


def umbral_canal_endemico(df: pd.DataFrame, historia: pd.DataFrame, anios_previos: int = 5) -> pd.Series:
    """
    Tercer cuartil (Q3) de los casos de la misma semana epidemiológica en los
    `anios_previos` años anteriores, por distrito. Solo usa el pasado: para un
    año del panel se toman los años previos de `historia` y del propio panel.

    `historia` son casos (ubigeo, anio, semana, casos_Dengue) de los años
    anteriores al panel; las filas ausentes se tratan como 0. En la historia,
    los casos de la semana 53 se suman a la semana 52, y la semana 53 del panel
    se compara con el canal de la semana 52. Devuelve una Serie alineada a `df`.
    """
    todo = pd.concat([historia[["ubigeo", "anio", "semana", OBJETIVO]],
                      df[["ubigeo", "anio", "semana", OBJETIVO]]], ignore_index=True)
    todo = todo.groupby(["ubigeo", "anio", "semana"], as_index=False)[OBJETIVO].sum()
    todo["semana"] = todo["semana"].clip(upper=52)
    todo = todo.groupby(["ubigeo", "anio", "semana"], as_index=False)[OBJETIVO].sum()
    ancho = todo.pivot_table(index=["ubigeo", "semana"], columns="anio", values=OBJETIVO, fill_value=0)
    ubigeos = df["ubigeo"].unique()
    anios_hist = range(df["anio"].min() - anios_previos, df["anio"].max() + 1)
    ancho = ancho.reindex(columns=anios_hist, fill_value=0)
    ancho = ancho.reindex(pd.MultiIndex.from_product([ubigeos, range(1, 53)], names=["ubigeo", "semana"]), fill_value=0)
    q3 = {}
    for anio in sorted(df["anio"].unique()):
        previos = ancho[[a for a in range(anio - anios_previos, anio)]]
        q3[anio] = previos.quantile(0.75, axis=1)
    q3 = pd.DataFrame(q3).stack().rename("q3").reset_index().rename(columns={"level_2": "anio"})
    clave = df[["ubigeo", "anio"]].assign(semana=df["semana"].clip(upper=52))
    return pd.Series(clave.merge(q3, on=["ubigeo", "semana", "anio"], how="left")["q3"].to_numpy(), index=df.index)


def brote_canal_endemico(df: pd.DataFrame, historia: pd.DataFrame, anios_previos: int = 5) -> pd.Series:
    """
    D3: canal endémico. Una semana es de brote si sus casos superan el Q3 de la
    misma semana en los `anios_previos` años anteriores (ver
    `umbral_canal_endemico`) y hay al menos 1 caso.
    """
    umbral = umbral_canal_endemico(df, historia, anios_previos)
    return (df[OBJETIVO] > umbral) & (df[OBJETIVO] >= 1)


def brote_aumento_sostenido(df: pd.DataFrame, factor: float = 2.0, ventana: int = 8,
                            k: int = 3, minimo: int = 5) -> pd.Series:
    """
    D4: aumento relativo sostenido. Una semana "sube" si sus casos son al
    menos `factor` veces la media de las `ventana` semanas previas del mismo
    distrito y al menos `minimo`. Se marcan las semanas que pertenecen a una
    racha de al menos `k` semanas consecutivas que suben. Solo usa el pasado
    para la referencia.
    """
    base = df.groupby("ubigeo")[OBJETIVO].transform(lambda s: s.shift(1).rolling(ventana, min_periods=ventana).mean())
    sube = (df[OBJETIVO] >= factor * base) & (df[OBJETIVO] >= minimo) & base.notna()
    grupo = (sube != sube.groupby(df["ubigeo"]).shift()).cumsum()
    largo = sube.groupby([df["ubigeo"], grupo]).transform("size")
    return sube & (largo >= k)


def resumen_definicion(df: pd.DataFrame, marca: pd.Series) -> dict:
    """Cifras para comparar definiciones de brote: positivos, episodios y concentración."""
    d = df.assign(_m=marca.to_numpy())
    ep = rachas(d, "_m")
    pos = int(marca.sum())
    return {
        "filas_positivas": pos,
        "pct_filas_positivas": round(100 * pos / len(df), 2),
        "razon_negativos_por_positivo": round((len(df) - pos) / pos, 1) if pos else None,
        "episodios": int(len(ep)),
        "duracion_mediana_semanas": float(ep["duracion"].median()) if len(ep) else None,
        "distritos_con_algun_positivo": int(d.loc[d["_m"], "ubigeo"].nunique()),
        "positivos_por_anio": {int(a): int(v) for a, v in d.groupby("anio")["_m"].sum().items()},
        "pct_positivos_en_2017_2023": round(100 * d.loc[d["_m"], "anio"].isin([2017, 2023]).mean(), 1) if pos else None,
        "pct_casos_cubiertos": round(100 * d.loc[d["_m"], OBJETIVO].sum() / d[OBJETIVO].sum(), 1),
    }


def marcar_arranque(df: pd.DataFrame, marca: str, ventana: int = 8, desde_rezago: int = 1) -> pd.Series:
    """
    Arranque: `marca` verdadera en t y ninguna marca en las `ventana` semanas
    que empiezan `desde_rezago` semanas antes (t - desde_rezago ... t -
    desde_rezago - ventana + 1) en el mismo distrito. Exige la ventana completa;
    si falta historia, devuelve False. Con `desde_rezago` = horizonte, la
    condición solo usa información disponible al momento de predecir.
    """
    m = df[marca].astype(float)
    previo = m.groupby(df["ubigeo"]).transform(
        lambda s: s.shift(desde_rezago).rolling(ventana, min_periods=ventana).max())
    return (m == 1) & (previo == 0)


def sin_marca_previa(df: pd.DataFrame, marca: str, ventana: int = 8, desde_rezago: int = 1) -> pd.Series:
    """Filas sin `marca` en la ventana previa definida como en `marcar_arranque` (ventana completa)."""
    m = df[marca].astype(float)
    previo = m.groupby(df["ubigeo"]).transform(
        lambda s: s.shift(desde_rezago).rolling(ventana, min_periods=ventana).max())
    return previo == 0
