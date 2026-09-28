"""Selectively update the Piura district-week dengue model dataset.

Run ``python -m src.update_dataset_module --input INPUT.csv --output OUTPUT.csv``.
"""

import argparse
import asyncio
import csv
import logging
import os
import tempfile
from collections import defaultdict
from datetime import date, timedelta, timezone, datetime
from pathlib import Path
from typing import Callable

import pandas as pd

from src.ingestion.fetch_openmeteo import DAILY_VARS, fetch_district
from src.ingestion.scrape_minsa_dengue import scrape_sala
from src.processing.agregacion_semanal import agregar_a_semanal
from src.processing.epi_sala import load_ubigeo_catalog, normalize_sala_records, upsert_sala_silver
from src.processing.merge_datasets import fill_component
from src.processing.socio_interpolacion import SOCIO_COLUMNS, generar_socio_para_claves
from src.utils.paths import BRONZE_SALA, BRONZE_SOCIO, GOLD, REFERENCE, SILVER, SILVER_SALA, UBIGEO_CATALOG
from src.validation.expectations_gold import (
    KEY, WEATHER_COLUMNS, coverage_path, detect_missing_components,
    load_case_coverage, prepare_dataset, trusted_baseline_coverage,
    validate_complete, validate_geography,
)

DistrictWeek = tuple[str, int, int]
Provider = Callable[[pd.DataFrame, set[DistrictWeek]], pd.DataFrame]


def _rows_for_keys(frame: pd.DataFrame, keys: set[DistrictWeek]) -> pd.DataFrame:
    selected = frame[frame.apply(lambda row: (str(row["ubigeo"]), int(row["anio"]), int(row["semana"])) in keys, axis=1)]
    if len(selected) != len(keys):
        raise ValueError("Requested district-weeks are absent or duplicated in the input")
    return selected


def run_epidemiological(frame: pd.DataFrame, keys: set[DistrictWeek]) -> pd.DataFrame:
    """Scrape only requested district-years and return their weekly case rows."""
    catalog = load_ubigeo_catalog(UBIGEO_CATALOG)
    by_code = catalog.set_index("ubigeo")
    unknown = {key[0] for key in keys} - set(by_code.index)
    if unknown:
        raise ValueError(f"No Sala district mapping for UBIGEO: {sorted(unknown)}")
    by_year: dict[int, set[str]] = defaultdict(set)
    for ubigeo, year, _ in keys:
        by_year[year].add(ubigeo)
    batches = []
    for year, codes in sorted(by_year.items()):
        labels = {
            (by_code.loc[code, "provincia_sala"], by_code.loc[code, "distrito_sala"])
            for code in codes
        }
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        artifact_dir = BRONZE_SALA / f"{year}_{stamp}"
        logging.info("Sala: %s, %s requested districts", year, len(codes))
        records, controls = asyncio.run(scrape_sala(year, labels, artifact_dir))
        normalized = normalize_sala_records(records, controls, catalog)
        batches.append(normalized)
    result = pd.concat(batches, ignore_index=True)
    requested = _rows_for_keys(result, keys)
    upsert_sala_silver(SILVER_SALA, result)
    extra = len(result) - len(requested)
    if extra:
        logging.info("Sala returned %s additional district-weeks; retained in %s", extra, SILVER_SALA)
    return requested[KEY + ["casos_Dengue"]]


def _contiguous_ranges(starts: list[date]) -> list[tuple[date, date]]:
    """Group consecutive Sunday week starts into inclusive daily API ranges."""
    ranges = []
    for start in sorted(set(starts)):
        if ranges and start == ranges[-1][1] + timedelta(days=1):
            ranges[-1] = (ranges[-1][0], start + timedelta(days=6))
        else:
            ranges.append((start, start + timedelta(days=6)))
    return ranges


def run_weather(frame: pd.DataFrame, keys: set[DistrictWeek]) -> pd.DataFrame:
    """Fetch only missing full weeks and aggregate with the existing rules."""
    selected = _rows_for_keys(frame, keys)
    districts = []
    daily_frames = []
    for district_id, (ubigeo, group) in enumerate(selected.groupby("ubigeo"), start=1):
        first = group.iloc[0]
        lat, lon = float(first["lat"]), float(first["lon"])
        if pd.isna(lat) or pd.isna(lon):
            raise ValueError(f"Weather coordinates missing for UBIGEO {ubigeo}")
        districts.append({
            "id_distrito": district_id, "ubigeo": ubigeo,
            "provincia": first["provincia"], "distrito": first["distrito"],
            "lat": lat, "lon": lon,
        })
        starts = [pd.Timestamp(value).date() for value in group["semana_inicio"]]
        for start, end in _contiguous_ranges(starts):
            logging.info("Open-Meteo: UBIGEO %s, %s to %s", ubigeo, start, end)
            daily = fetch_district(lat, lon, start_date=start.isoformat(), end_date=end.isoformat())
            absent = set(["time", *DAILY_VARS]) - set(daily)
            if absent:
                raise ValueError(f"Open-Meteo response lacks columns for {ubigeo}: {sorted(absent)}")
            dates = pd.to_datetime(daily["time"], errors="raise").dt.date
            expected = set(pd.date_range(start, end).date)
            if len(dates) != len(expected) or set(dates) != expected:
                raise ValueError(f"Open-Meteo returned incomplete or duplicate dates for {ubigeo}, {start} to {end}")
            if daily[DAILY_VARS].isna().any().any():
                raise ValueError(f"Open-Meteo returned missing daily weather values for {ubigeo}")
            daily = daily.copy()
            daily["id_distrito"] = district_id
            daily_frames.append(daily)
    district_frame = pd.DataFrame(districts)
    aggregated = agregar_a_semanal(pd.concat(daily_frames, ignore_index=True), district_frame, include_id=True)
    id_to_code = district_frame.set_index("id_distrito")["ubigeo"].to_dict()
    aggregated["ubigeo"] = aggregated["id_distrito"].map(id_to_code)
    aggregated = aggregated[KEY + WEATHER_COLUMNS]
    return _rows_for_keys(aggregated, keys)


def run_demographic(
    frame: pd.DataFrame, keys: set[DistrictWeek], *, rebuild: bool = False,
) -> pd.DataFrame:
    """Generate only required district-years and broadcast to requested weeks."""
    annual_keys = {(ubigeo, year) for ubigeo, year, _ in keys}
    try:
        annual = generar_socio_para_claves(
            annual_keys, SILVER / "socio_anual.csv", BRONZE_SOCIO / "data_socio_2017_2025.xlsx",
            prefer_bronze=rebuild,
        )
    except (KeyError, OSError, ImportError) as exc:
        raise RuntimeError(f"Demographic generation failed: {exc}") from exc
    requested = pd.DataFrame(sorted(keys), columns=KEY)
    result = requested.merge(annual, on=["ubigeo", "anio"], how="left", validate="many_to_one")
    if len(result) != len(keys):
        raise ValueError("Demographic merge changed district-week row count")
    return result[KEY + SOCIO_COLUMNS]


def _write_outputs(
    frame: pd.DataFrame, coverage: dict[DistrictWeek, int], output: Path, *,
    write_dataset: bool, line_ending: str,
) -> None:
    """Validate before atomic replacement of the CSV and coverage sidecar."""
    output.parent.mkdir(parents=True, exist_ok=True)
    sidecar = coverage_path(output)
    temporary_dataset = None
    temporary_coverage = None
    try:
        if write_dataset:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=output.parent, suffix=".csv", delete=False) as file:
                temporary_dataset = Path(file.name)
                frame.to_csv(file, index=False, lineterminator=line_ending)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=output.parent, suffix=".csv", delete=False) as file:
            temporary_coverage = Path(file.name)
            writer = csv.writer(file)
            writer.writerow(["ubigeo", "anio", "semana", "casos_Dengue", "source"])
            for key, cases in sorted(coverage.items()):
                writer.writerow([*key, cases, "verified"])
        if temporary_dataset is not None:
            os.replace(temporary_dataset, output)
        os.replace(temporary_coverage, sidecar)
    finally:
        for path in (temporary_dataset, temporary_coverage):
            if path is not None:
                path.unlink(missing_ok=True)


def update_dataset(
    input_path: Path, output_path: Path, *, dry_run: bool = False,
    force: set[str] | None = None, start_date: str | None = None, end_date: str | None = None,
    providers: dict[str, Provider] | None = None,
) -> dict[str, set[DistrictWeek]]:
    """Inspect, selectively fetch, validate, and write one model dataset update."""
    if not input_path.exists():
        raise FileNotFoundError(f"Input dataset not found: {input_path}")
    frame = prepare_dataset(pd.read_csv(input_path, dtype=str))
    validate_geography(frame)
    case_state = load_case_coverage(coverage_path(input_path))
    baseline = case_state is None
    coverage = trusted_baseline_coverage(frame) if baseline else case_state
    if baseline:
        logging.info("No coverage sidecar; trusting populated input values as the baseline")
    force = force or set()
    unknown_force = force - {"epidemiological", "weather", "demographic"}
    if unknown_force:
        raise ValueError(f"Unknown force components: {sorted(unknown_force)}")
    missing = detect_missing_components(
        frame, coverage, force=force, force_start=start_date, force_end=end_date,
    )
    logging.info("Dataset inspection: %s rows", len(frame))
    for component, keys in missing.items():
        periods = sorted({f"{year}-W{week:02d}" for _, year, week in keys})
        logging.info("%s: %s district-weeks missing/selected; periods=%s", component, len(keys), ", ".join(periods[:20]) + (" ..." if len(periods) > 20 else ""))
        logging.info("[%s] %s", "RUN" if keys else "SKIP", component)
    if dry_run:
        return missing

    providers = providers or {
        "epidemiological": run_epidemiological,
        "weather": run_weather,
        "demographic": lambda dataset, keys: run_demographic(
            dataset, keys, rebuild="demographic" in force,
        ),
    }
    refreshed = False
    for component, columns in (
        ("epidemiological", ["casos_Dengue"]),
        ("weather", WEATHER_COLUMNS),
        ("demographic", SOCIO_COLUMNS),
    ):
        keys = missing[component]
        if not keys:
            continue
        updates = providers[component](frame, keys)
        forced_keys = set()
        if component in force:
            starts = _rows_for_keys(frame, keys)
            forced_keys = {
                (str(row.ubigeo), int(row.anio), int(row.semana))
                for row in starts.itertuples(index=False)
                if pd.Timestamp(start_date) <= pd.Timestamp(row.semana_inicio) <= pd.Timestamp(end_date)
            }
        if component == "epidemiological":
            forced_keys = keys  # All unverified case values must be replaced by the verified source.
        frame = fill_component(frame, updates, columns, keys, force_keys=forced_keys)
        if component == "epidemiological":
            for row in _rows_for_keys(frame, keys).itertuples(index=False):
                coverage[(str(row.ubigeo), int(row.anio), int(row.semana))] = int(row.casos_Dengue)
        refreshed = True
    model_keys = set(zip(frame["ubigeo"].astype(str), frame["anio"].astype(int), frame["semana"].astype(int)))
    coverage = {key: cases for key, cases in coverage.items() if key in model_keys}
    validate_complete(frame, coverage)
    write_dataset = refreshed or input_path.resolve() != output_path.resolve()
    if write_dataset or baseline or not coverage_path(output_path).exists():
        with input_path.open("rb") as file:
            line_ending = "\r\n" if b"\r\n" in file.read(4096) else "\n"
        _write_outputs(frame, coverage, output_path, write_dataset=write_dataset, line_ending=line_ending)
    logging.info("Dataset update complete: %s rows, output=%s", len(frame), output_path)
    return missing


def main() -> None:
    """Command-line entry point for selective dataset updates."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force-epidemiological", action="store_true")
    parser.add_argument("--force-weather", action="store_true")
    parser.add_argument("--force-demographic", action="store_true")
    parser.add_argument("--start-date", help="First Sunday week start for a forced refresh")
    parser.add_argument("--end-date", help="Last Sunday week start for a forced refresh")
    args = parser.parse_args()
    force = {
        name for name, enabled in (
            ("epidemiological", args.force_epidemiological),
            ("weather", args.force_weather),
            ("demographic", args.force_demographic),
        ) if enabled
    }
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        update_dataset(
            args.input, args.output, dry_run=args.dry_run, force=force,
            start_date=args.start_date, end_date=args.end_date,
        )
    except (ValueError, RuntimeError, FileNotFoundError) as exc:
        parser.exit(1, f"Update failed: {exc}\n")


if __name__ == "__main__":
    main()
