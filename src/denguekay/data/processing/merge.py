"""
Silver per source -> integrated silver: merges meteo + socio, then + epi.
The result still has no feature engineering, which is why it lives in
data/silver/integrado/ and not in gold.
"""

import pandas as pd

from denguekay.data.keys import normalize


def diagnose_unmatched_districts(meteo: pd.DataFrame, annual_socio: pd.DataFrame) -> None:
    """Print which distrito_key values are in one source and not in the other (before merging)."""
    meteo_only = set(meteo["distrito_key"]) - set(annual_socio["distrito_key"])
    socio_only = set(annual_socio["distrito_key"]) - set(meteo["distrito_key"])
    print("En meteo pero no en socio:", meteo_only)
    print("En socio pero no en meteo:", socio_only)


def merge_meteo_socio(meteo: pd.DataFrame, annual_socio: pd.DataFrame) -> pd.DataFrame:
    """Join weekly weather with yearly sociodemographic variables by distrito_key + year."""
    final = meteo.merge(
        annual_socio.drop(columns=["departamento", "provincia", "distrito"]),
        on=["distrito_key", "anio"],
        how="left",
    )

    missing = final[final["poblacion"].isna()]
    print(len(missing), "filas sin match sociodemográfico")
    return final


def merge_with_epi(final_dataset: pd.DataFrame, df_cases: pd.DataFrame) -> pd.DataFrame:
    """Join historical cases; years not yet covered by the source stay null."""
    final_dataset = final_dataset.copy()
    df_cases = df_cases.copy()

    # ubigeo is a 6-digit code (with leading zeros), not a
    # quantity -- same rule as fill_component()/epi_sala.py/integrated_expectations.py.
    # Casting to int here broke with IntCastingNaNError as soon as a single
    # district had no match in the previous merge (meteo+socio), and it also lost
    # the leading zeros if a ubigeo already arrived as an int.
    final_dataset["ubigeo"] = final_dataset["ubigeo"].astype("string").str.zfill(6)
    df_cases["ubigeo"] = df_cases["ubigeo"].astype("string").str.zfill(6)

    without_ubigeo = final_dataset[final_dataset["ubigeo"].isna()]
    if len(without_ubigeo) > 0:
        affected_districts = sorted(without_ubigeo["distrito_key"].unique())
        raise ValueError(
            f"{len(without_ubigeo)} filas de dataset_final no tienen ubigeo (no encontraron "
            f"match sociodemográfico en el merge anterior). Distrito_key involucrados: "
            f"{affected_districts}. Corre diagnosticar_distritos_sin_match(meteo, socio_anual) "
            f"para ver a qué se debe el desfase de nombres y corrígelo antes de este merge."
        )

    model_dataset = final_dataset.merge(df_cases, on=["ubigeo", "anio", "semana"], how="left")
    covered_years = set(pd.to_numeric(df_cases["anio"], errors="raise").astype(int))
    covered = model_dataset["anio"].isin(covered_years)
    model_dataset.loc[covered, "casos_Dengue"] = model_dataset.loc[covered, "casos_Dengue"].fillna(0)
    model_dataset["casos_Dengue"] = model_dataset["casos_Dengue"].astype("Int64")

    print(model_dataset.shape)
    print(model_dataset["casos_Dengue"].describe())
    return model_dataset


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
