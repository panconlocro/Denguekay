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
    """Cruza casos históricos; deja nulos los años aún no cubiertos por la fuente."""
    dataset_final = dataset_final.copy()
    df_casos = df_casos.copy()

    # ubigeo es un código de 6 dígitos (con ceros a la izquierda), no una
    # cantidad -- mismo criterio que fill_component()/epi_sala.py/expectations_gold.py.
    # Castear a int aquí rompía con IntCastingNaNError apenas quedaba un solo
    # distrito sin match en el merge anterior (meteo+socio), y de paso perdía
    # los ceros a la izquierda si algún ubigeo llegaba ya como int.
    dataset_final["ubigeo"] = dataset_final["ubigeo"].astype("string").str.zfill(6)
    df_casos["ubigeo"] = df_casos["ubigeo"].astype("string").str.zfill(6)

    sin_ubigeo = dataset_final[dataset_final["ubigeo"].isna()]
    if len(sin_ubigeo) > 0:
        distritos_afectados = sorted(sin_ubigeo["distrito_key"].unique())
        raise ValueError(
            f"{len(sin_ubigeo)} filas de dataset_final no tienen ubigeo (no encontraron "
            f"match sociodemográfico en el merge anterior). Distrito_key involucrados: "
            f"{distritos_afectados}. Corre diagnosticar_distritos_sin_match(meteo, socio_anual) "
            f"para ver a qué se debe el desfase de nombres y corrígelo antes de este merge."
        )

    dataset_modelo = dataset_final.merge(df_casos, on=["ubigeo", "anio", "semana"], how="left")
    covered_years = set(pd.to_numeric(df_casos["anio"], errors="raise").astype(int))
    covered = dataset_modelo["anio"].isin(covered_years)
    dataset_modelo.loc[covered, "casos_Dengue"] = dataset_modelo.loc[covered, "casos_Dengue"].fillna(0)
    dataset_modelo["casos_Dengue"] = dataset_modelo["casos_Dengue"].astype("Int64")

    print(dataset_modelo.shape)
    print(dataset_modelo["casos_Dengue"].describe())
    return dataset_modelo


def fill_component(
    dataset: pd.DataFrame, updates: pd.DataFrame, columns: list[str],
    requested: set[tuple[str, int, int]], *,
    force_keys: set[tuple[str, int, int]] | None = None,
) -> pd.DataFrame:
    """Fill selected district-weeks without joins, row growth, or suffix columns."""
    keys = ["ubigeo", "anio", "semana"]
    absent = set(keys + columns) - set(updates)
    if absent:
        raise ValueError(f"Source lacks columns: {sorted(absent)}")
    if updates.duplicated(keys).any():
        raise ValueError("Source contains duplicate district-week keys")
    result = dataset.copy()
    for column in columns:
        if column not in result:
            result[column] = pd.NA
        result[column] = result[column].astype(object)
    source = updates.copy()
    source["ubigeo"] = source["ubigeo"].astype("string").str.zfill(6)
    source["anio"] = source["anio"].astype(int)
    source["semana"] = source["semana"].astype(int)
    source = source.set_index(keys)
    absent_keys = requested - set(source.index)
    if absent_keys:
        raise ValueError(f"Source has no data for {len(absent_keys)} requested district-weeks: {sorted(absent_keys)[:5]}")
    row_index = {
        (str(row.ubigeo), int(row.anio), int(row.semana)): index
        for index, row in result[keys].iterrows()
    }
    force_keys = force_keys or set()
    for key in requested:
        if key not in row_index:
            raise ValueError(f"Requested key is not in the model dataset: {key}")
        source_row = source.loc[key]
        index = row_index[key]
        for column in columns:
            value = source_row[column]
            if pd.isna(value):
                raise ValueError(f"Source value is missing: {key}, {column}")
            if key in force_keys or pd.isna(result.at[index, column]):
                result.at[index, column] = value
    if len(result) != len(dataset):
        raise ValueError("Component fill unexpectedly changed row count")
    return result
