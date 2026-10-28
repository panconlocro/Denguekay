"""
Bronze (epidemiological Excel, one row per reported case) -> Silver
(epi_piura_semanal.csv: case counts per ubigeo/district/year/week).
"""

import pandas as pd


def load_raw(excel_path) -> pd.DataFrame:
    return pd.read_excel(excel_path)


def build_weekly_cases(df_epi_raw: pd.DataFrame) -> pd.DataFrame:
    """Format the keys and count the cases per district/year/week."""
    df_epi_raw = df_epi_raw.copy()
    # Same rule as in epi_sala.py / fill_component(): ubigeo as a 6-digit
    # string, never an int.
    df_epi_raw["ubigeo"] = df_epi_raw["ubigeo"].astype("string").str.zfill(6)
    df_epi_raw["ano"] = pd.to_numeric(df_epi_raw["ano"], errors="coerce")

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
