"""
Bronze notifications CSV -> weekly counts of confirmed cases in Piura.
"""

import pandas as pd

from denguekay.config.paths import UBIGEO_CATALOG
from denguekay.data.processing.epi_sala import load_ubigeo_catalog
from denguekay.data.validation.duplicates import duplicate_key_report

RAW_COLUMNS = ["departamento", "tipo_dx", "ubigeo", "ano", "semana"]


def load_raw(csv_path) -> pd.DataFrame:
    return pd.read_csv(csv_path, usecols=RAW_COLUMNS, dtype="string", encoding="utf-8-sig")


def build_weekly_cases(df_epi_raw: pd.DataFrame) -> pd.DataFrame:
    """Count confirmed Piura notifications per UBIGEO and epidemiological week."""
    absent = set(RAW_COLUMNS) - set(df_epi_raw)
    if absent:
        raise ValueError(f"Missing epidemiological columns: {sorted(absent)}")
    department = df_epi_raw["departamento"].astype("string").str.strip().str.upper()
    diagnosis = df_epi_raw["tipo_dx"].astype("string").str.strip().str.upper()
    cases = df_epi_raw.loc[department.eq("PIURA") & diagnosis.eq("C"), ["ubigeo", "ano", "semana"]].copy()
    if cases.empty:
        raise ValueError("No confirmed dengue notifications found for Piura")

    cases["ubigeo"] = cases["ubigeo"].astype("string").str.strip().str.zfill(6)
    catalogue = load_ubigeo_catalog(UBIGEO_CATALOG)
    if not cases["ubigeo"].isin(catalogue["ubigeo"]).all():
        raise ValueError("Confirmed Piura notifications contain an unknown or missing UBIGEO")
    for column, lower, upper in (("ano", 1000, 9999), ("semana", 1, 53)):
        numbers = pd.to_numeric(cases[column], errors="coerce")
        if numbers.isna().any() or not (numbers.between(lower, upper) & numbers.mod(1).eq(0)).all():
            raise ValueError(f"Confirmed Piura notifications contain an invalid {column}")
        cases[column] = numbers.astype(int)

    return (cases.groupby(["ubigeo", "ano", "semana"]).size()
            .rename("casos_Dengue").reset_index().rename(columns={"ano": "anio"}))


DUPLICATE_RULE = ("Las filas que repiten la llave (ubigeo, anio, semana) se suman en una sola fila; el resultado "
                  "tiene una fila por llave")


def deduplicate_cases_with_report(df_cases: pd.DataFrame, source: str = "casos semanales confirmados"):
    """Add up repeated ubigeo-year-week rows and return ``(cases, control)``.

    ``control`` is the result of the repeated-key control (HU0001-3): which keys repeat and the rule applied."""
    control = duplicate_key_report(df_cases, source=source, rule=DUPLICATE_RULE)
    cases = (
        df_cases.groupby(["ubigeo", "anio", "semana"], as_index=False)["casos_Dengue"]
        .sum()
    )
    return cases, control


def deduplicate_cases(df_cases: pd.DataFrame) -> pd.DataFrame:
    """When a ubigeo-year-week repeats (reported in more than one row), add up the cases.

    It prints the count as before; ``deduplicate_cases_with_report`` also returns the control."""
    cases, control = deduplicate_cases_with_report(df_cases)
    print(f"{control['filas_con_llave_repetida']} filas con ubigeo-año-semana repetido")
    return cases
