"""
Silver -> Gold: mergea meteo + socio, y luego + epi, para producir los
datasets finales que consume el modelo.
"""

import pandas as pd

from src.utils.keys import normalizar


def diagnosticar_distritos_sin_match(meteo: pd.DataFrame, socio_anual: pd.DataFrame) -> None:
    """Imprime qué distrito_key hay en una fuente y no en la otra (antes de mergear)."""
    solo_meteo = set(meteo["distrito_key"]) - set(socio_anual["distrito_key"])
    solo_socio = set(socio_anual["distrito_key"]) - set(meteo["distrito_key"])
    print("En meteo pero no en socio:", solo_meteo)
    print("En socio pero no en meteo:", solo_socio)


def merge_meteo_socio(meteo: pd.DataFrame, socio_anual: pd.DataFrame) -> pd.DataFrame:
    """Cruza clima semanal + variables sociodemográficas anuales por distrito_key + año."""
    final = meteo.merge(
        socio_anual.drop(columns=["departamento", "provincia", "distrito"]),
        on=["distrito_key", "anio"],
        how="left",
    )

    faltantes = final[final["poblacion"].isna()]
    print(len(faltantes), "filas sin match sociodemográfico")
    return final


def merge_con_epi(dataset_final: pd.DataFrame, df_casos: pd.DataFrame) -> pd.DataFrame:
    """Cruza el dataset meteo+socio con los casos de dengue (semana epidemiológica)."""
    dataset_final = dataset_final.copy()
    dataset_final["ubigeo"] = dataset_final["ubigeo"].astype(int)

    dataset_modelo = dataset_final.merge(df_casos, on=["ubigeo", "anio", "semana"], how="left")
    dataset_modelo["casos_Dengue"] = dataset_modelo["casos_Dengue"].fillna(0).astype(int)

    print(dataset_modelo.shape)
    print(dataset_modelo["casos_Dengue"].describe())
    return dataset_modelo
