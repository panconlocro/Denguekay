"""
Carga de solo lectura del dataset integrado (data/silver/integrado) para el EDA.

Todo notebook de EDA debe cargar los datos con cargar_integrado() y no con
pd.read_csv directo: así el ubigeo siempre entra como string de 6 dígitos y el
panel distrito-semana se valida antes de analizar nada.
"""

from pathlib import Path

import pandas as pd

from src.utils.paths import SILVER_INTEGRADO

OBJETIVO = "casos_Dengue"
LLAVE = ["ubigeo", "anio", "semana"]
COLUMNAS_CLIMA = [
    "temp_media", "temp_max", "temp_min", "precip_total_mm", "lluvia_total_mm",
    "hum_rel_media", "viento_max", "radiacion_total", "et0_total",
]
COLUMNAS_GEO = ["provincia", "distrito", "distrito_key", "ubigeo", "lat", "lon"]


def columnas_socio(df: pd.DataFrame) -> list[str]:
    """Población y todas las fracciones sociodemográficas presentes en el dataset."""
    return ["poblacion"] + [c for c in df.columns if c.startswith("fraccion_")]


def validar_panel(df: pd.DataFrame) -> list[str]:
    """
    Revisa la estructura del panel distrito x semana. Devuelve una lista de
    problemas encontrados (vacía si el panel es consistente). No corrige nada.
    """
    problemas = []
    faltan = [c for c in LLAVE + ["semana_inicio", OBJETIVO] if c not in df.columns]
    if faltan:
        return [f"Faltan columnas obligatorias: {faltan}"]

    if not df["ubigeo"].astype("string").str.fullmatch(r"\d{6}").all():
        problemas.append("ubigeo no es siempre un string de 6 dígitos")
    if df[LLAVE + ["semana_inicio", OBJETIVO]].isna().any().any():
        problemas.append("Hay nulos en llave, semana_inicio o casos_Dengue")
    if df.duplicated(LLAVE).any():
        problemas.append(f"Llave {LLAVE} duplicada en {int(df.duplicated(LLAVE).sum())} filas")

    semanas_por_distrito = df.groupby("ubigeo").size()
    if semanas_por_distrito.nunique() > 1:
        problemas.append("Los distritos no tienen el mismo número de semanas (panel desbalanceado)")

    fechas = pd.to_datetime(df["semana_inicio"])
    for ubigeo, g in df.assign(_f=fechas).groupby("ubigeo"):
        saltos = g["_f"].sort_values().diff().dropna().dt.days
        if not (saltos == 7).all():
            problemas.append(f"Distrito {ubigeo}: semanas no consecutivas (huecos o repetidas)")
            break
    return problemas


def cargar_integrado(path: Path = SILVER_INTEGRADO) -> pd.DataFrame:
    """
    Lee el dataset integrado (meteo + socio + epi, sin feature engineering),
    valida el panel y lo devuelve ordenado por distrito y semana.
    Lanza ValueError si el panel no es consistente.
    """
    df = pd.read_csv(path, dtype={"ubigeo": "string"}, parse_dates=["semana_inicio"])
    problemas = validar_panel(df)
    if problemas:
        raise ValueError("Panel inconsistente:\n- " + "\n- ".join(problemas))
    return df.sort_values(["ubigeo", "semana_inicio"]).reset_index(drop=True)
