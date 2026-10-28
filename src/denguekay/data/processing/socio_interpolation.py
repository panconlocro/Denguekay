"""
Bronze (sociodemographic Excel, one row per district with _2017/_2025 columns)
-> Silver (socio_anual.csv: one row per district x year, 2017-2025).

Variables with data in 2017 and 2025 are interpolated linearly year by year.
Variables with a single available year (e.g. fraccion_menores_5 only 2017,
fraccion_60_mas only 2025) are dropped from the final dataset: there is no way
to interpolate them or to assume they stayed constant for 8 years, so they
are excluded instead of filled with an unreliable assumption.
Decision taken; it closes the item that was pending in docs/estructuraRepo.md,
section 8.
"""

import re
import logging
from pathlib import Path

import pandas as pd

from denguekay.data.keys import normalize

YEARS = list(range(2017, 2026))
SOCIO_COLUMNS = [
    "poblacion", "fraccion_rural", "fraccion_mujeres", "fraccion_menores_15",
    "fraccion_sin_seguro", "fraccion_analfabeta_15_mas", "fraccion_pared_precaria",
    "fraccion_piso_tierra", "fraccion_agua_red", "fraccion_agua_cisterna",
    "fraccion_desague_red", "fraccion_sin_saneamiento", "fraccion_alumbrado_red",
    "fraccion_hogares_refrigeradora", "fraccion_hogares_celular",
    "fraccion_hogares_lena",
]

# District with a repeated name in the original Excel (see clean_duplicates)
DUPLICATE_DISTRICT_FIX = {52: "SALITRAL_S"}


def load_raw(excel_path) -> pd.DataFrame:
    return pd.read_excel(excel_path)


def clean_duplicates(df_pop: pd.DataFrame) -> pd.DataFrame:
    """
    Drop duplicated "_consulta" columns and fix the district that
    appears twice with the same name (same rule as in meteo:
    an _S suffix to disambiguate).
    """
    df_pop = df_pop.copy()
    # Same rule as in epi_sala.py / fill_component(): ubigeo as a 6-digit
    # 6-digit string, never an int, so the leading zeros are not lost.
    df_pop["ubigeo"] = df_pop["ubigeo"].astype("string").str.zfill(6)
    df_pop["distrito_key"] = df_pop["distrito"].apply(normalize)
    df_pop = df_pop.drop(columns=["pob_censada_2025_consulta", "fraccion_mujeres_2025_consulta"])

    for idx, new_name in DUPLICATE_DISTRICT_FIX.items():
        if idx in df_pop.index:
            df_pop.loc[idx, "distrito"] = new_name

    df_pop["distrito_key"] = df_pop["distrito"].apply(normalize)

    assert df_pop["distrito_key"].is_unique, "Hay distritos duplicados en el Excel"
    assert df_pop["ubigeo"].is_unique
    return df_pop


def _build_long_population(df_pop: pd.DataFrame, id_cols: list[str]) -> pd.DataFrame:
    """Population: 2017 = census, 2018-2025 = projected. Returns long format (one row per year)."""
    population = df_pop[id_cols].copy()
    population["pob_2017"] = df_pop["pob_censada_2017"]
    for a in range(2018, 2026):
        population[f"pob_{a}"] = df_pop[f"pob_proyectada_{a}"]

    pop_long = population.melt(
        id_vars=id_cols, value_vars=[f"pob_{a}" for a in YEARS],
        var_name="anio", value_name="poblacion",
    )
    pop_long["anio"] = pop_long["anio"].str.replace("pob_", "").astype(int)
    return pop_long


def build_annual_socio(df_pop: pd.DataFrame) -> pd.DataFrame:
    """
    Convert the sociodemographic Excel (wide, one row per district) to long
    format (one row per district x year), interpolating linearly the variables
    that have a value in 2017 and 2025.
    """
    pop_cols = [c for c in df_pop.columns if c.startswith("pob_")]
    id_cols = ["ubigeo", "departamento", "provincia", "distrito", "distrito_key"]
    rest_cols = [c for c in df_pop.columns if c not in pop_cols + id_cols]

    pop_long = _build_long_population(df_pop, id_cols)

    # Detect base variables and the years in which they exist (columns like "<base>_2017" / "<base>_2025")
    pattern = re.compile(r"^(.*)_(2017|2025)$")
    pairs: dict[str, dict[int, str]] = {}
    for c in rest_cols:
        m = pattern.match(c)
        if not m:
            continue
        base, year = m.group(1), int(m.group(2))
        pairs.setdefault(base, {})[year] = c

    single_year = {b: list(d.keys()) for b, d in pairs.items() if len(d) == 1}
    if single_year:
        print("Variables con un solo año disponible (se descartan, no se interpolan):")
        for b, years in single_year.items():
            print(f"  - {b} (solo {years[0]})")

    interpolable_pairs = {b: d for b, d in pairs.items() if len(d) == 2}

    frames = [pop_long.set_index(id_cols + ["anio"])]

    for base, d in interpolable_pairs.items():
        table = pd.DataFrame(index=df_pop.index)
        v17 = df_pop[d[2017]].values
        v25 = df_pop[d[2025]].values
        for a in YEARS:
            frac = (a - 2017) / (2025 - 2017)
            table[a] = v17 + (v25 - v17) * frac

        table[id_cols] = df_pop[id_cols]
        table_long = table.melt(
            id_vars=id_cols, value_vars=YEARS, var_name="anio", value_name=base,
        )
        table_long["anio"] = table_long["anio"].astype(int)
        frames.append(table_long.set_index(id_cols + ["anio"]))

    annual_socio = pd.concat(frames, axis=1).reset_index()
    print(annual_socio.shape)  # expected: 65 districts x 9 years = 585 rows
    return annual_socio


def socio_for_keys(
    keys: set[tuple[str, int]], silver_path: Path, bronze_path: Path,
    *, prefer_bronze: bool = False,
) -> pd.DataFrame:
    """Return only requested UBIGEO-years; extrapolate beyond 2025 if needed."""
    if not keys:
        return pd.DataFrame(columns=["ubigeo", "anio", *SOCIO_COLUMNS])
    if prefer_bronze:
        if not bronze_path.exists():
            raise FileNotFoundError(f"Required raw demographic source is unavailable: {bronze_path}")
        source = build_annual_socio(clean_duplicates(load_raw(bronze_path)))
    elif silver_path.exists():
        source = pd.read_csv(silver_path, dtype={"ubigeo": "string"})
    elif bronze_path.exists():
        source = build_annual_socio(clean_duplicates(load_raw(bronze_path)))
    else:
        raise FileNotFoundError(f"Required demographic source is unavailable: {silver_path} or {bronze_path}")
    missing_columns = set(["ubigeo", "anio", *SOCIO_COLUMNS]) - set(source)
    if missing_columns:
        raise ValueError(f"Demographic source lacks columns: {sorted(missing_columns)}")
    source = source.copy()
    source["ubigeo"] = source["ubigeo"].astype("string").str.zfill(6)
    source["anio"] = source["anio"].astype(int)
    if source.duplicated(["ubigeo", "anio"]).any():
        raise ValueError("Demographic source contains duplicate UBIGEO-years")
    indexed = source.set_index(["ubigeo", "anio"])
    result = []
    for ubigeo, year in sorted(keys):
        if year <= 2025:
            if (ubigeo, year) not in indexed.index:
                raise ValueError(f"Demographic source has no district-year: {ubigeo}, {year}")
            values = indexed.loc[(ubigeo, year), SOCIO_COLUMNS].to_dict()
        else:
            if (ubigeo, 2017) not in indexed.index or (ubigeo, 2025) not in indexed.index:
                raise ValueError(f"Demographic endpoints missing for {ubigeo}")
            first = indexed.loc[(ubigeo, 2017), SOCIO_COLUMNS]
            last = indexed.loc[(ubigeo, 2025), SOCIO_COLUMNS]
            values = {}
            for column in SOCIO_COLUMNS:
                estimate = float(last[column]) + (year - 2025) * (float(last[column]) - float(first[column])) / 8
                if column.startswith("fraccion_"):
                    capped = min(1.0, max(0.0, estimate))
                    if capped != estimate:
                        logging.info(
                            "Clamped demographic value: district=%s period=%s variable=%s original=%s final=%s",
                            ubigeo, year, column, estimate, capped,
                        )
                    values[column] = capped
                else:
                    values[column] = int(round(estimate))
                    if values[column] <= 0:
                        raise ValueError(f"Projected population is nonpositive: {ubigeo}, {year}")
        if any(pd.isna(values[column]) for column in SOCIO_COLUMNS):
            raise ValueError(f"Demographic source has missing values: {ubigeo}, {year}")
        result.append({"ubigeo": ubigeo, "anio": year, **values})
    return pd.DataFrame(result)
