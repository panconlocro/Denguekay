"""Schema, coverage, and value checks for the integrated district-week dataset (silver/integrado)."""

import csv
from pathlib import Path

import pandas as pd

from src.processing.socio_interpolacion import SOCIO_COLUMNS
from src.processing.epi_sala import load_ubigeo_catalog
from src.utils.calendario import semana_epi_mmwr
from src.utils.keys import normalizar_sala
from src.utils.paths import UBIGEO_CATALOG

KEY = ["ubigeo", "anio", "semana"]
CORE_COLUMNS = ["provincia", "distrito", "lat", "lon", "ubigeo", "anio", "semana", "semana_inicio"]
WEATHER_COLUMNS = [
    "temp_media", "temp_max", "temp_min", "precip_total_mm", "lluvia_total_mm",
    "hum_rel_media", "viento_max", "radiacion_total", "et0_total",
]
COMPONENT_COLUMNS = {
    "epidemiological": ["casos_Dengue"],
    "weather": WEATHER_COLUMNS,
    "demographic": SOCIO_COLUMNS,
}
Coverage = dict[tuple[str, int, int], int]


def _case_int(value) -> int:
    numeric = float(value)
    if not numeric.is_integer() or numeric < 0:
        raise ValueError(f"Dengue cases must be nonnegative integers: {value}")
    return int(numeric)


def coverage_path(dataset_path: Path) -> Path:
    """Return the sidecar path associated with a model CSV."""
    return dataset_path.with_name(dataset_path.stem + ".coverage.csv")


def prepare_dataset(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize keys and add absent component columns without changing rows."""
    missing = set(CORE_COLUMNS) - set(frame)
    if missing:
        raise ValueError(f"Dataset lacks core columns: {sorted(missing)}")
    if frame.columns.duplicated().any() or any(column.endswith(("_x", "_y")) for column in frame):
        raise ValueError("Dataset contains duplicate or merge-suffixed columns")
    frame = frame.copy()
    if frame.empty:
        raise ValueError("Dataset contains no district-week rows")
    if frame[CORE_COLUMNS].isna().any().any():
        raise ValueError("Dataset has missing core geography or week values")
    frame["ubigeo"] = frame["ubigeo"].astype("string").str.zfill(6)
    if frame["ubigeo"].isna().any() or not frame["ubigeo"].str.fullmatch(r"\d{6}").all():
        raise ValueError("Dataset has missing or invalid six-digit UBIGEO codes")
    for column in ("anio", "semana"):
        frame[column] = pd.to_numeric(frame[column], errors="raise").astype(int)
    dates = pd.to_datetime(frame["semana_inicio"], errors="raise")
    if dates.isna().any() or (dates.dt.weekday != 6).any():
        raise ValueError("semana_inicio must be a Sunday for every row")
    calendario = semana_epi_mmwr(dates)
    if (calendario.anio_epi.to_numpy() != frame["anio"].to_numpy()).any() or (calendario.semana_epi.to_numpy() != frame["semana"].to_numpy()).any():
        raise ValueError("anio/semana no coinciden con el calendario epidemiológico MMWR de semana_inicio")
    if frame.duplicated(KEY).any():
        raise ValueError("Dataset contains duplicate UBIGEO-year-week rows")
    for column in ("provincia", "distrito", "lat", "lon"):
        if (frame.groupby("ubigeo")[column].nunique(dropna=False) > 1).any():
            raise ValueError(f"Conflicting {column} values for one UBIGEO")
    latitude = pd.to_numeric(frame["lat"], errors="coerce")
    longitude = pd.to_numeric(frame["lon"], errors="coerce")
    if latitude.isna().any() or longitude.isna().any() or not latitude.between(-90, 90).all() or not longitude.between(-180, 180).all():
        raise ValueError("Dataset contains invalid district coordinates")
    for group in COMPONENT_COLUMNS.values():
        for column in group:
            if column not in frame:
                frame[column] = pd.NA
            else:
                frame[column] = frame[column].replace(r"^\s*$", pd.NA, regex=True)
    return frame


def validate_geography(frame: pd.DataFrame, catalog_path: Path = UBIGEO_CATALOG) -> None:
    """Ensure each model UBIGEO matches its tracked Piura province and district."""
    catalog = load_ubigeo_catalog(catalog_path).set_index("ubigeo")
    for row in frame[["ubigeo", "provincia", "distrito"]].drop_duplicates().itertuples(index=False):
        code = str(row.ubigeo)
        if code not in catalog.index:
            raise ValueError(f"UBIGEO is absent from the Piura catalogue: {code}")
        expected = catalog.loc[code]
        actual_label = (
            normalizar_sala(row.provincia), normalizar_sala(row.distrito).removesuffix("_S"),
        )
        expected_label = (expected["provincia_sala"], expected["distrito_sala"])
        if actual_label != expected_label:
            raise ValueError(f"Geographic name does not match UBIGEO {code}: {actual_label} != {expected_label}")


def load_case_coverage(path: Path) -> Coverage | None:
    """Read recorded case coverage; None means a legacy baseline has no state."""
    if not path.exists():
        return None
    coverage: Coverage = {}
    with path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        if set(reader.fieldnames or []) != {"ubigeo", "anio", "semana", "casos_Dengue", "source"}:
            raise ValueError(f"Invalid coverage sidecar schema: {path}")
        for row in reader:
            key = (row["ubigeo"].zfill(6), int(row["anio"]), int(row["semana"]))
            if key in coverage:
                raise ValueError(f"Duplicate coverage key: {key}")
            coverage[key] = int(row["casos_Dengue"])
    return coverage


def trusted_baseline_coverage(frame: pd.DataFrame) -> Coverage:
    """Trust non-null case counts in the existing populated baseline."""
    result = {}
    for row in frame[KEY + ["casos_Dengue"]].itertuples(index=False, name=None):
        ubigeo, year, week, cases = row
        if pd.notna(cases):
            result[(str(ubigeo), int(year), int(week))] = _case_int(cases)
    return result


def detect_missing_components(
    frame: pd.DataFrame, coverage: Coverage, *,
    force: set[str] | None = None, force_start: str | None = None, force_end: str | None = None,
) -> dict[str, set[tuple[str, int, int]]]:
    """Find district-weeks missing each component; zeros require case coverage."""
    missing = {component: set() for component in COMPONENT_COLUMNS}
    force = force or set()
    start = pd.Timestamp(force_start) if force_start else None
    end = pd.Timestamp(force_end) if force_end else None
    if force and (start is None or end is None or start > end):
        raise ValueError("Force flags require a valid --start-date and --end-date")
    if force and (start.weekday() != 6 or end.weekday() != 6):
        raise ValueError("Force date boundaries must be Sunday week starts")
    for row in frame.itertuples(index=False):
        key = (str(row.ubigeo), int(row.anio), int(row.semana))
        row_date = pd.Timestamp(row.semana_inicio)
        in_force_window = start is not None and start <= row_date <= end
        cases = row.casos_Dengue
        if pd.isna(cases) or coverage.get(key) != _case_int(cases):
            missing["epidemiological"].add(key)
        for component, columns in COMPONENT_COLUMNS.items():
            if component == "epidemiological":
                continue
            if any(pd.isna(getattr(row, column)) for column in columns):
                missing[component].add(key)
        for component in force:
            if in_force_window:
                missing[component].add(key)
    return missing


def validate_complete(frame: pd.DataFrame, coverage: Coverage) -> None:
    """Reject a final dataset with missing or invalid components."""
    frame = prepare_dataset(frame)
    missing = detect_missing_components(frame, coverage)
    remaining = {component: len(keys) for component, keys in missing.items() if keys}
    if remaining:
        raise ValueError(f"Dataset remains incomplete: {remaining}")
    for column in WEATHER_COLUMNS + SOCIO_COLUMNS + ["casos_Dengue"]:
        values = pd.to_numeric(frame[column], errors="coerce")
        if values.isna().any():
            raise ValueError(f"Non-numeric values in {column}")
    if (pd.to_numeric(frame["poblacion"]) <= 0).any():
        raise ValueError("Population must be positive")
    for column in SOCIO_COLUMNS:
        if column.startswith("fraccion_") and not pd.to_numeric(frame[column]).between(0, 1).all():
            raise ValueError(f"Fractions outside [0, 1]: {column}")
    cases = pd.to_numeric(frame["casos_Dengue"])
    if (cases < 0).any() or (cases % 1 != 0).any():
        raise ValueError("Dengue cases must be nonnegative integers")


# ---------------------------------------------------------------------------
# Suite declarativa de Great Expectations para el panel integrado.
# Complementa (no reemplaza) prepare_dataset/validate_complete: deja un
# reporte legible en los Data Docs y se adjunta a las corridas de MLflow.
# GX se importa aquí dentro para no exigirlo al actualizador del dataset.
# ---------------------------------------------------------------------------

# Caja geográfica aproximada del departamento de Piura (grados decimales).
LAT_PIURA = (-6.5, -3.5)
LON_PIURA = (-81.5, -79.0)


def expectativas_integrado_gx(ubigeos: list[str]) -> list:
    """Expectativas de esquema, llave, geografía y rangos físicos del integrado."""
    import great_expectations as gx

    E = gx.expectations
    requeridas = CORE_COLUMNS + WEATHER_COLUMNS + SOCIO_COLUMNS + ["casos_Dengue"]
    exp = [E.ExpectColumnToExist(column=c) for c in requeridas]
    exp += [
        E.ExpectTableRowCountToBeBetween(min_value=1),
        E.ExpectCompoundColumnsToBeUnique(column_list=KEY),
        E.ExpectColumnValuesToMatchRegex(column="ubigeo", regex=r"^\d{6}$"),
        E.ExpectColumnValuesToBeInSet(column="ubigeo", value_set=ubigeos),
        E.ExpectColumnUniqueValueCountToBeBetween(
            column="ubigeo", min_value=len(ubigeos), max_value=len(ubigeos)),
        E.ExpectColumnValuesToBeBetween(column="anio", min_value=2017),
        E.ExpectColumnValuesToBeBetween(column="semana", min_value=1, max_value=53),
        E.ExpectColumnValuesToBeBetween(column="lat", min_value=LAT_PIURA[0], max_value=LAT_PIURA[1]),
        E.ExpectColumnValuesToBeBetween(column="lon", min_value=LON_PIURA[0], max_value=LON_PIURA[1]),
        # Clima semanal: rangos físicamente plausibles, no ajustados a los datos.
        *(E.ExpectColumnValuesToBeBetween(column=c, min_value=-10, max_value=45)
          for c in ("temp_media", "temp_max", "temp_min")),
        E.ExpectColumnPairValuesAToBeGreaterThanB(column_A="temp_max", column_B="temp_min", or_equal=True),
        E.ExpectColumnPairValuesAToBeGreaterThanB(column_A="temp_max", column_B="temp_media", or_equal=True),
        E.ExpectColumnPairValuesAToBeGreaterThanB(column_A="temp_media", column_B="temp_min", or_equal=True),
        E.ExpectColumnValuesToBeBetween(column="precip_total_mm", min_value=0, max_value=1500),
        E.ExpectColumnValuesToBeBetween(column="lluvia_total_mm", min_value=0, max_value=1500),
        E.ExpectColumnPairValuesAToBeGreaterThanB(
            column_A="precip_total_mm", column_B="lluvia_total_mm", or_equal=True),
        E.ExpectColumnValuesToBeBetween(column="hum_rel_media", min_value=0, max_value=100),
        E.ExpectColumnValuesToBeBetween(column="viento_max", min_value=0, max_value=200),
        E.ExpectColumnValuesToBeBetween(column="radiacion_total", min_value=0, max_value=350),
        E.ExpectColumnValuesToBeBetween(column="et0_total", min_value=0, max_value=100),
        # Sociodemografía y casos.
        E.ExpectColumnValuesToBeBetween(column="poblacion", min_value=1),
        E.ExpectColumnValuesToBeBetween(column="casos_Dengue", min_value=0),
    ]
    exp += [E.ExpectColumnValuesToBeBetween(column=c, min_value=0, max_value=1)
            for c in SOCIO_COLUMNS if c.startswith("fraccion_")]
    exp += [E.ExpectColumnValuesToNotBeNull(column=c) for c in requeridas]
    return exp
