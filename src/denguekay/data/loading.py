"""
Read-only loading of the integrated dataset (data/silver/integrado).

Every consumer must load the data with load_integrated() rather than a direct
pd.read_csv: that way ubigeo always comes in as a 6-digit string and the
district-week panel is validated before anything else.
"""

from pathlib import Path

import pandas as pd

from denguekay.config.paths import SILVER_INTEGRATED
from denguekay.data.calendar import mmwr_epi_week

TARGET = "casos_Dengue"
PANEL_KEY = ["ubigeo", "anio", "semana"]
CLIMATE_COLUMNS = [
    "temp_media", "temp_max", "temp_min", "precip_total_mm", "lluvia_total_mm",
    "hum_rel_media", "viento_max", "radiacion_total", "et0_total",
]
GEO_COLUMNS = ["provincia", "distrito", "distrito_key", "ubigeo", "lat", "lon"]


def socio_columns(df: pd.DataFrame) -> list[str]:
    """Population and every sociodemographic fraction present in the dataset."""
    return ["poblacion"] + [c for c in df.columns if c.startswith("fraccion_")]


def validate_panel(df: pd.DataFrame) -> list[str]:
    """
    Check the structure of the district x week panel. Returns the list of
    problems found (empty when the panel is consistent). It fixes nothing.
    """
    problems = []
    missing = [c for c in PANEL_KEY + ["semana_inicio", TARGET] if c not in df.columns]
    if missing:
        return [f"Faltan columnas obligatorias: {missing}"]

    if not df["ubigeo"].astype("string").str.fullmatch(r"\d{6}").all():
        problems.append("ubigeo no es siempre un string de 6 dígitos")
    if df[PANEL_KEY + ["semana_inicio", TARGET]].isna().any().any():
        problems.append("Hay nulos en llave, semana_inicio o casos_Dengue")
    if df.duplicated(PANEL_KEY).any():
        problems.append(f"Llave {PANEL_KEY} duplicada en {int(df.duplicated(PANEL_KEY).sum())} filas")

    weeks_per_district = df.groupby("ubigeo").size()
    if weeks_per_district.nunique() > 1:
        problems.append("Los distritos no tienen el mismo número de semanas (panel desbalanceado)")

    dates = pd.to_datetime(df["semana_inicio"])
    if dates.isna().any() or dates.dt.weekday.ne(6).any():
        problems.append("semana_inicio debe contener domingos sin fechas faltantes")
    else:
        calendar = mmwr_epi_week(dates)
        if (pd.to_numeric(df.anio, errors="coerce").ne(calendar.anio_epi)
                | pd.to_numeric(df.semana, errors="coerce").ne(calendar.semana_epi)).any():
            problems.append("anio/semana no coinciden con el calendario epidemiológico MMWR de semana_inicio")
    for ubigeo, g in df.assign(_f=dates).groupby("ubigeo"):
        gaps = g["_f"].sort_values().diff().dropna().dt.days
        if not (gaps == 7).all():
            problems.append(f"Distrito {ubigeo}: semanas no consecutivas (huecos o repetidas)")
            break
    return problems


def load_integrated(path: Path = SILVER_INTEGRATED) -> pd.DataFrame:
    """
    Read the integrated dataset (meteo + socio + epi, no feature engineering),
    validate the panel and return it sorted by district and week.
    Raises ValueError when the panel is not consistent.
    """
    df = pd.read_csv(path, dtype={"ubigeo": "string"}, parse_dates=["semana_inicio"])
    problems = validate_panel(df)
    if problems:
        raise ValueError("Panel inconsistente:\n- " + "\n- ".join(problems))
    return df.sort_values(["ubigeo", "semana_inicio"]).reset_index(drop=True)
