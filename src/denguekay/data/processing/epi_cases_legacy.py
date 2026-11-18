"""Notified-case ingestion of v0-v3, restored from ``model/v3`` (``src/denguekay/data/processing/epi_cases.py``).

Bronze (epidemiological Excel ``PiuraDengue.xlsx``, one row per reported case) -> Silver
(``epi_piura_semanal.csv``: case counts per ubigeo/district/year/week). V4 counts confirmed cases from the CSV
instead (``epi_cases.py``); the two definitions are never mixed in one file.
"""

import pandas as pd


def load_raw(excel_path) -> pd.DataFrame:
    return pd.read_excel(excel_path)


def build_weekly_cases(df_epi_raw: pd.DataFrame) -> pd.DataFrame:
    """Format the keys and count the cases per district/year/week.

    Restored from model/v3 with one fix: the Excel that Drive serves now ends with blank rows (no ubigeo, year or week),
    which make pandas read those columns as float (``100101.0``). Rows without keys are ignored and the keys are
    integers again; with an Excel without blank rows the result is the same as in model/v3."""
    df_epi_raw = df_epi_raw.dropna(subset=["ubigeo", "ano", "semana"]).copy()
    # Same rule as in epi_sala.py / fill_component(): ubigeo as a 6-digit
    # string, never an int.
    numeric_ubigeo = pd.to_numeric(df_epi_raw["ubigeo"], errors="coerce")
    if numeric_ubigeo.isna().any():
        raise ValueError("The epidemiological Excel has a non-numeric ubigeo")
    df_epi_raw["ubigeo"] = numeric_ubigeo.astype("int64").astype("string").str.zfill(6)
    df_epi_raw["ano"] = pd.to_numeric(df_epi_raw["ano"], errors="coerce")
    df_epi_raw["semana"] = pd.to_numeric(df_epi_raw["semana"], errors="coerce")
    df_epi_raw = df_epi_raw.dropna(subset=["ano", "semana"]).astype({"ano": "int64", "semana": "int64"})

    df_cases = (
        df_epi_raw.groupby(["ubigeo", "distrito", "ano", "semana"])
        .size()
        .reset_index(name="casos_Dengue")
        .rename(columns={"ano": "anio"})
    )
    return df_cases


def deduplicate_cases(df_cases: pd.DataFrame) -> pd.DataFrame:
    """When a ubigeo-year-week repeats (reported in more than one row), add up the cases."""
    dup = df_cases.duplicated(subset=["ubigeo", "anio", "semana"], keep=False)
    print(f"{dup.sum()} filas con ubigeo-año-semana repetido")

    return (
        df_cases.groupby(["ubigeo", "anio", "semana"], as_index=False)["casos_Dengue"]
        .sum()
    )
