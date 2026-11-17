"""Build the source and integrated silver tables for V4."""

from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from denguekay.config.paths import (
    BRONZE_CHIRPS_EE_FINAL, BRONZE_CHIRPS_FINAL, BRONZE_CHIRPS_FINAL_FTP, BRONZE_CHIRPS_PRELIM, BRONZE_ENSO, BRONZE_EPI_CSV,
    BRONZE_SALA, BRONZE_SOCIO, CACHE_METEO, CACHE_METEO_ERA5_LAND_2000_2016, CACHE_METEO_ERA5_LAND_2017_2025,
    CACHE_METEO_ERA5_LAND_2026, CACHE_METEO_ERA5_LAND_RECENT, DISTRICT_COORDS, ROOT, UBIGEO_CATALOG,
    V4_CHIRPS, V4_ENSO, V4_ERA5_LAND, V4_HISTORY, V4_INTEGRATED, V4_PANEL_WEATHER, V4_SALA, V4_SOCIO,
    V4_WEATHER_SOCIO,
)
from denguekay.data.ingestion import chirps, chirps_ee, chirps_prelim, openmeteo, release_bundles
from denguekay.data.ingestion.enso import download_sstoi
from denguekay.data.ingestion.minsa_sala_scraper import confirmed_weekly_points, scrape_sala
from denguekay.data.keys import normalize
from denguekay.data.processing import chirps_precipitation as rain
from denguekay.data.processing import socio_interpolation as socio
from denguekay.data.processing.chirps_snapshots import archive_snapshot
from denguekay.data.processing.enso_index import nino12_monthly
from denguekay.data.processing.epi_cases import build_weekly_cases, load_raw
from denguekay.data.processing.epi_sala import SALA_FIRST_YEAR, load_ubigeo_catalog, normalize_sala_records
from denguekay.data.processing.merge import merge_meteo_socio, merge_with_epi
from denguekay.data.processing.weekly_aggregation import (
    aggregate_available_to_weekly, aggregate_to_weekly, clean_names_for_join, latest_snapshot, load_daily_from_caches,
)
from denguekay.data.validation.integrated_expectations import coverage_path, trusted_baseline_coverage
from denguekay.data.validation.v4_panel import validate_confirmed_panel
from denguekay.features.long_history import week_grid
from denguekay.pipelines.versions import V4_CUTOFF, clip_enso, clip_sala, clip_weekly


def write_silver(frame, output, *, line_ending="\r\n"):
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as folder:
        candidate = Path(folder) / output.name
        frame.to_csv(candidate, index=False, lineterminator=line_ending)
        candidate.replace(output)
    return {"archivo": output.name, "filas": len(frame)}


def _weather_caches():
    return [
        ("2000-01-01", "2016-12-31", CACHE_METEO_ERA5_LAND_2000_2016),
        ("2017-01-01", "2025-12-31", CACHE_METEO_ERA5_LAND_2017_2025),
        ("2026-01-01", "2026-10-31", CACHE_METEO_ERA5_LAND_2026),
    ]


def restore_published_bronze():
    """Restore verified historical climate snapshots without installing any archived silver or gold."""
    sources = (
        (release_bundles.manifest_path(study="06_model_improvement"), "bronze_estudio06.zip",
         (CACHE_METEO, *(cache for _, _, cache in _weather_caches()), BRONZE_CHIRPS_FINAL,
          BRONZE_CHIRPS_FINAL_FTP, BRONZE_CHIRPS_PRELIM)),
        (release_bundles.manifest_path(version="v3"), "datos_v3.zip", (BRONZE_CHIRPS_EE_FINAL,)),
    )
    for manifest, name, folders in sources:
        prefixes = tuple(folder.relative_to(ROOT).as_posix() for folder in folders)
        report = release_bundles.fetch(manifest, only=[name], prefixes=prefixes)[name]
        if not (report["extraidos"] or report["ya_estaban"]):
            raise ValueError(f"No historical climate inputs in {name}")
        print(f"{name}: {report['extraidos']} extraídos y {report['ya_estaban']} ya verificados", flush=True)


def download_weather():
    districts = pd.read_csv(DISTRICT_COORDS, float_precision="round_trip")
    if openmeteo.download_all(districts, cache_dir=CACHE_METEO):
        raise RuntimeError("Incomplete 2017–2025 weather cache; resume V4 at step 02")
    ranges = _weather_caches()
    end = openmeteo.era5_land_end_date()
    if end >= openmeteo.ERA5_LAND_RECENT_START:
        ranges.append((openmeteo.ERA5_LAND_RECENT_START, end, CACHE_METEO_ERA5_LAND_RECENT / end))
    for first, last, folder in ranges:
        pending = openmeteo.download_all(districts, start_date=first, end_date=last, models="era5_land",
                                         cache_dir=folder, daily_vars=openmeteo.ERA5_LAND_DAILY_VARS)
        if pending:
            raise RuntimeError(f"Incomplete ERA5-Land cache {folder.name}; resume V4 at step 02")
    return {"distritos": len(districts), "caches": len(ranges)}


def weather_silver(*, cutoff=V4_CUTOFF):
    districts = pd.read_csv(DISTRICT_COORDS, float_precision="round_trip")
    daily_panel = load_daily_from_caches([CACHE_METEO], len(districts))
    panel_weekly = clean_names_for_join(aggregate_to_weekly(daily_panel, districts))
    folders = [folder for _, _, folder in _weather_caches()]
    if recent := latest_snapshot(CACHE_METEO_ERA5_LAND_RECENT):
        folders.append(recent)
    daily_era = load_daily_from_caches(folders, len(districts))
    weekly = clean_names_for_join(aggregate_available_to_weekly(daily_era, districts,
                                                               openmeteo.ERA5_LAND_DAILY_VARS))
    if weekly.duplicated(["id_distrito", "semana_inicio"]).any() or weekly.empty:
        raise ValueError("ERA5-Land has duplicate or missing district-weeks")
    return [write_silver(panel_weekly, V4_PANEL_WEATHER, line_ending="\n"),
            write_silver(clip_weekly(weekly, cutoff), V4_ERA5_LAND)]


def _download_chirps(ee_final):
    first = date(2000, 1, 1)
    if not ee_final.empty:
        first = pd.to_datetime(ee_final.fecha).max().date() + timedelta(days=1)
    seed = chirps.day_path(date(2000, 1, 1))
    if not seed.exists():
        chirps.download_final("2000-01-01", "2000-01-01")
    ref = chirps_prelim.reference_grid()
    today = date.today()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    with chirps_prelim.FtpSource() as source, TemporaryDirectory(prefix="denguekay-chirps-") as scratch:
        final_days = sorted(day for year in range(first.year, today.year + 1)
                            for day in source.listing("final", year) if first <= day <= today)
        pending = [day for day in final_days if not chirps_prelim.ftp_target(day, "final").exists()]
        latest_final = max(final_days, default=first - timedelta(days=1))
        # Fetch the complete first preliminary week, including days after the last complete final Sunday.
        preliminary_start = latest_final - timedelta(days=(latest_final.weekday() + 1) % 7)
        prelim_days = sorted(day for year in range(preliminary_start.year, today.year + 1)
                             for day in source.listing("prelim", year) if preliminary_start <= day <= today)
        for version, days in (("final", pending), ("prelim", prelim_days)):
            if not days:
                continue
            summary = chirps_prelim.download_ftp(days, version, source=source, tmp_dir=Path(scratch),
                                                ref=ref, stamp=stamp)
            chirps_prelim.write_ftp_manifest(summary, {"fecha_descarga": stamp, "version_pipeline": "v4"}, version)
            if summary["estado"] != "completa":
                raise RuntimeError(summary["error"])


def climate_silver(*, offline=False, cutoff=V4_CUTOFF):
    enso_candidates = sorted(BRONZE_ENSO.glob("sstoi_????????.indices"))
    if offline:
        if not enso_candidates:
            raise FileNotFoundError("No NOAA CPC raw snapshot in bronze")
        raw = enso_candidates[-1]
    else:
        raw = BRONZE_ENSO / f"sstoi_{date.today():%Y%m%d}.indices"
        if not raw.exists():
            raw = download_sstoi()
    enso = nino12_monthly(raw.read_text(encoding="utf-8"))
    districts = chirps_ee.load_districts()
    ee = (rain.daily_final_from_ee(BRONZE_CHIRPS_EE_FINAL)
          if any(BRONZE_CHIRPS_EE_FINAL.glob("*/????-??.json")) else pd.DataFrame())
    if not offline:
        _download_chirps(ee)
    ftp_final = rain.daily_from_windows(BRONZE_CHIRPS_FINAL_FTP, districts, "final", "chirps-v3.0.sat.*.tif")
    if not ee.empty:
        days = pd.to_datetime(ee.fecha).dt.date
        ftp_final = ftp_final.loc[~pd.to_datetime(ftp_final.fecha).dt.date.isin(days)]
    final = pd.concat([frame for frame in (ee, ftp_final) if not frame.empty], ignore_index=True) if (
        not ee.empty or not ftp_final.empty) else ftp_final
    prelim = rain.daily_from_windows(BRONZE_CHIRPS_PRELIM, districts, "prelim", "chirps-v3.0.prelim.*.tif")
    if final.empty:
        raise ValueError("CHIRPS bronze contains no final historical rainfall")
    daily = rain.combine_daily_by_week(final, prelim)
    weekly, discarded = rain.weekly_by_version(daily)
    if weekly.empty:
        raise ValueError("CHIRPS bronze has no complete weeks")
    result = {"semanas_distritales_incompletas": len(discarded)}
    if not offline:
        result["captura_chirps"] = archive_snapshot(weekly, observed_at=datetime.now(timezone.utc)).name
    result["series"] = [write_silver(clip_enso(enso, cutoff), V4_ENSO),
                        write_silver(clip_weekly(weekly, cutoff), V4_CHIRPS)]
    return result


def replay_sala(folder, year, catalog):
    records = []
    for entry in sorted(folder.glob("*.json")):
        record = json.loads(entry.read_bytes())
        if record["anio"] != year or record.get("tipo_dx") != "C":
            raise ValueError(f"{entry.name} is not a confirmed Sala capture for {year}; rerun V4 step 05 with downloads")
        points = confirmed_weekly_points(record["chart"]["x"]["opts"], year)
        records.append({**record, "points": points})
    districts = [r for r in records if r["nivel"] == "distrito"]
    controls = [r for r in records if r["nivel"] != "distrito"]
    result = normalize_sala_records(districts, controls, catalog)
    if set(result.ubigeo) != set(catalog.ubigeo):
        raise ValueError("Sala snapshot does not cover all districts")
    return result.assign(tipo_dx="C")


async def sala_silver(*, offline=False, year=None, cutoff=V4_CUTOFF):
    """Capture or replay the confirmed Sala series under the caller's event loop."""
    catalog = load_ubigeo_catalog(UBIGEO_CATALOG)
    targets = set(zip(catalog.provincia_sala, catalog.distrito_sala))
    frames = []
    for item in range(SALA_FIRST_YEAR, (year or date.today().year) + 1):
        if offline:
            folders = sorted(BRONZE_SALA.glob(f"{item}_*"))
            if not folders:
                raise FileNotFoundError(f"No Sala bronze snapshot for {item}")
            folder = folders[-1]
        else:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            folder = BRONZE_SALA / f"{item}_{stamp}"
            await scrape_sala(item, targets, folder)
        frames.append(replay_sala(folder, item, catalog))
    sala = pd.concat(frames, ignore_index=True).sort_values(["ubigeo", "anio", "semana"])
    return write_silver(clip_sala(sala, cutoff), V4_SALA)


def historical_silver():
    return write_silver(build_weekly_cases(load_raw(BRONZE_EPI_CSV)), V4_HISTORY, line_ending="\n")


def socio_silver():
    raw = socio.load_raw(BRONZE_SOCIO / "data_socio_2017_2025.xlsx")
    return write_silver(socio.build_annual_socio(socio.clean_duplicates(raw)), V4_SOCIO, line_ending="\n")


def weather_socio_silver():
    weather = pd.read_csv(V4_PANEL_WEATHER, float_precision="round_trip")
    demographics = pd.read_csv(V4_SOCIO, dtype={"ubigeo": "string"}, float_precision="round_trip")
    aliases = {"El Carmendela Frontera": "El Carmen de la Frontera", "San Miguelde El Faique": "San Miguel de el Faique"}
    weather["distrito"] = weather.distrito.replace(aliases)
    weather["distrito_key"] = weather.distrito.map(normalize)
    return write_silver(merge_meteo_socio(weather, demographics), V4_WEATHER_SOCIO, line_ending="\n")


def integrate_confirmed():
    dtype = {"ubigeo": "string"}
    base = pd.read_csv(V4_WEATHER_SOCIO, dtype=dtype, float_precision="round_trip")
    history = pd.read_csv(V4_HISTORY, dtype=dtype)
    sala = pd.read_csv(V4_SALA, dtype=dtype)
    calendar = week_grid(2025, 2025)
    if not set(sala.loc[sala.anio.eq(2025), "semana"]).issuperset(calendar.semana):
        raise ValueError("The confirmed Sala snapshot does not contain all weeks of 2025")
    panel = merge_with_epi(base, history, sala_cases=sala)
    coverage = trusted_baseline_coverage(panel)
    validate_confirmed_panel(panel, coverage)
    coverage_frame = pd.DataFrame([(*key, value, "verified") for key, value in sorted(coverage.items())],
                                  columns=["ubigeo", "anio", "semana", "casos_Dengue", "source"])
    return [write_silver(panel, V4_INTEGRATED, line_ending="\n"),
            write_silver(coverage_frame, coverage_path(V4_INTEGRATED))]
