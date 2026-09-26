"""
Bronze (Excel epidemiológico, 1 fila por caso reportado) -> Silver
(epi_piura_semanal.csv: conteo de casos por ubigeo/distrito/año/semana).
"""

import pandas as pd


def cargar_crudo(path_excel) -> pd.DataFrame:
    return pd.read_excel(path_excel)


def construir_casos_semanales(df_epi_raw: pd.DataFrame) -> pd.DataFrame:
    """Formatea llaves y cuenta cuántos casos hay por distrito/año/semana."""
    df_epi_raw = df_epi_raw.copy()
    df_epi_raw["ubigeo"] = df_epi_raw["ubigeo"].astype(int)
    df_epi_raw["ano"] = pd.to_numeric(df_epi_raw["ano"], errors="coerce")

    df_casos = (
        df_epi_raw.groupby(["ubigeo", "distrito", "ano", "semana"])
        .size()
        .reset_index(name="casos_Dengue")
        .rename(columns={"ano": "anio"})
    )
    return df_casos


def deduplicar_casos(df_casos: pd.DataFrame) -> pd.DataFrame:
    """Si un ubigeo-año-semana se repite (reportado en más de una fila), suma los casos."""
    dup = df_casos.duplicated(subset=["ubigeo", "anio", "semana"], keep=False)
    print(f"{dup.sum()} filas con ubigeo-año-semana repetido")

    return (
        df_casos.groupby(["ubigeo", "anio", "semana"], as_index=False)["casos_Dengue"]
        .sum()
    )
