"""Build the source and integrated silver tables for V4."""

from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory

import pandas as pd

from denguekay.config.paths import (
    BRONZE_CHIRPS_EE_FINAL, BRONZE_CHIRPS_FINAL, BRONZE_CHIRPS_FINAL_FTP, BRONZE_CHIRPS_PRELIM, BRONZE_ENSO, BRONZE_EPI_CSV,
    BRONZE_SALA, BRONZE_SOCIO, CACHE_METEO, CACHE_METEO_ERA5_LAND_2000_2016, CACHE_METEO_ERA5_LAND_2017_2025,
    CACHE_METEO_ERA5_LAND_2026, CACHE_METEO_ERA5_LAND_RECENT, DISTRICT_COORDS, ROOT, UBIGEO_CATALOG,
    V4_CHIRPS, V4_ENSO, V4_ERA5_LAND, V4_FROZEN, V4_GEOGRAPHY, V4_HISTORY, V4_INTEGRATED, V4_PANEL_WEATHER, V4_SALA,
    V4_SOCIO, V4_WEATHER_SOCIO,
)
from denguekay.data.ingestion import chirps, chirps_ee, chirps_prelim, openmeteo, release_bundles
from denguekay.data.ingestion.enso import download_sstoi
from denguekay.data.ingestion.minsa_sala_scraper import SalaYearWithoutWeeks, confirmed_weekly_points, scrape_sala
from denguekay.data.keys import normalize
from denguekay.data.processing import chirps_precipitation as rain
from denguekay.data.processing import socio_interpolation as socio
from denguekay.data.processing.chirps_snapshots import archive_snapshot
from denguekay.data.processing.enso_index import nino12_monthly
from denguekay.data.processing.epi_cases import build_weekly_cases, load_raw
from denguekay.data.processing.epi_sala import SALA_FIRST_YEAR, load_ubigeo_catalog, normalize_sala_records
from denguekay.data.processing.merge import V4_NAME_ALIASES, merge_meteo_socio, merge_with_epi
from denguekay.data.processing.weekly_aggregation import (
    aggregate_available_to_weekly, aggregate_to_weekly, clean_names_for_join, latest_snapshot, load_daily_from_caches,
)
from denguekay.data.validation.integrated_expectations import coverage_path, trusted_baseline_coverage
from denguekay.data.validation.v4_panel import validate_confirmed_panel
from denguekay.features.long_history import week_grid
from denguekay.pipelines.versions import V4_CUTOFF, clip_enso, clip_sala, clip_weekly


def utc_today():
    """The UTC day: the date that names a capture and tells when it was extracted (never the local date of the PC)."""
    return datetime.now(timezone.utc).date()


ERA5_CAPTURE_SUFFIX = ".captura.json"


def era5_capture_file(folder):
    """Sidecar of a recent ERA5-Land cache folder (named by its last day of data, not by the extraction)."""
    folder = Path(folder)
    return folder.with_name(folder.name + ERA5_CAPTURE_SUFFIX)


def record_era5_capture(folder, last_day):
    """Write, once, the UTC instant at which the cache folder was complete (the real extraction date).

    Limit: the stamp is the moment of this call. A folder that was already complete without a sidecar (downloaded before
    this record existed) is stamped by the first run that finds it, so for it the date is an upper bound of the extraction,
    not the extraction itself."""
    path = era5_capture_file(folder)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"extraido_utc": datetime.now(timezone.utc).isoformat(), "ultimo_dia_de_datos": last_day,
                   "producto": "ERA5-Land 0,1° vía Open-Meteo (archive API, models=era5_land)"}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


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


def download_era5_land(*, max_hourly_waits=None):
    """ERA5-Land caches from 2000 to the latest available day (the weekly operation calls only this part).

    ``max_hourly_waits`` limits the waits after Open-Meteo's hourly limit; ``None`` keeps the downloader's default.
    A run that stops resumes from the caches on the next call."""
    districts = pd.read_csv(DISTRICT_COORDS, float_precision="round_trip")
    ranges = _weather_caches()
    end = openmeteo.era5_land_end_date()
    if end >= openmeteo.ERA5_LAND_RECENT_START:
        ranges.append((openmeteo.ERA5_LAND_RECENT_START, end, CACHE_METEO_ERA5_LAND_RECENT / end))
    limit = {} if max_hourly_waits is None else {"max_hourly_waits": max_hourly_waits}
    for first, last, folder in ranges:
        pending = openmeteo.download_all(districts, start_date=first, end_date=last, models="era5_land",
                                         cache_dir=folder, daily_vars=openmeteo.ERA5_LAND_DAILY_VARS, **limit)
        if pending:
            raise RuntimeError(f"Incomplete ERA5-Land cache {folder.name}; resume V4 at step 02")
        if folder == CACHE_METEO_ERA5_LAND_RECENT / end:   # the folder is named by its last day of data
            record_era5_capture(folder, end)
    return {"distritos": len(districts), "caches": len(ranges)}


def download_weather(*, era5_land=True):
    """Open-Meteo caches of the 2017–2025 panel and, with ``era5_land`` (v3 and V4), the ERA5-Land ones from 2000."""
    districts = pd.read_csv(DISTRICT_COORDS, float_precision="round_trip")
    if openmeteo.download_all(districts, cache_dir=CACHE_METEO):
        raise RuntimeError("Incomplete 2017–2025 weather cache; resume at the weather download step")
    if not era5_land:
        return {"distritos": len(districts), "caches": 1}
    return download_era5_land()


def read_district_coords():
    """The district coordinates as the frozen silver files carry them.

    The Release (datos_v4.zip) was written from the coordinates read with the default pandas float parser; the exact
    ``round_trip`` parser differs by one ulp in two districts (Arenal and Miguel Checa), which breaks the match of
    the ERA5-Land centroids with the panel (``features.climate.era5_land_weekly``) and the byte equality.

    That holds for pandas 3.0.x, the version ``constraints.txt`` pins. From pandas 3.1 the parser is always exact
    (``float_precision`` is deprecated and ignored), so the two latitudes are the exact ones: the run is consistent
    with itself but its ERA5-Land silver differs from the Release by one ulp in those two districts."""
    return pd.read_csv(DISTRICT_COORDS)


def _era5_land_weekly(districts):
    """Weekly ERA5-Land of every cache and of the latest recent snapshot, with every day available."""
    folders = [folder for _, _, folder in _weather_caches()]
    if recent := latest_snapshot(CACHE_METEO_ERA5_LAND_RECENT):
        folders.append(recent)
    daily_era = load_daily_from_caches(folders, len(districts))
    weekly = clean_names_for_join(aggregate_available_to_weekly(daily_era, districts,
                                                               openmeteo.ERA5_LAND_DAILY_VARS))
    if weekly.duplicated(["id_distrito", "semana_inicio"]).any() or weekly.empty:
        raise ValueError("ERA5-Land has duplicate or missing district-weeks")
    return weekly


def era5_land_silver(*, cutoff=V4_CUTOFF, output=None):
    """ERA5-Land weekly silver trimmed to ``cutoff`` (``None`` keeps every week) and written to ``output``.

    The default output is the V4 silver of the Release; the weekly operation passes its own, without cutoff."""
    weekly = _era5_land_weekly(read_district_coords())
    return write_silver(clip_weekly(weekly, cutoff), output or V4_ERA5_LAND)


def weather_silver(*, cutoff=V4_CUTOFF, era5_land=True):
    """Weekly Open-Meteo panel and, with ``era5_land`` (v3 and V4), the ERA5-Land weekly silver trimmed to ``cutoff``."""
    districts = read_district_coords()
    daily_panel = load_daily_from_caches([CACHE_METEO], len(districts))
    panel_weekly = clean_names_for_join(aggregate_to_weekly(daily_panel, districts))
    if not era5_land:
        return [write_silver(panel_weekly, V4_PANEL_WEATHER, line_ending="\n")]
    weekly = _era5_land_weekly(districts)   # validated before anything is written
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
    today = utc_today()
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


def climate_silver(*, offline=False, cutoff=V4_CUTOFF, enso_output=None, chirps_output=None):
    """Niño 1+2 and CHIRPS silver trimmed to ``cutoff`` (``None`` keeps everything), written to the V4 files of the
    Release unless the caller names its own outputs."""
    enso_candidates = sorted(BRONZE_ENSO.glob("sstoi_????????.indices"))
    if offline:
        if not enso_candidates:
            raise FileNotFoundError("No NOAA CPC raw snapshot in bronze")
        raw = enso_candidates[-1]
    else:
        raw = BRONZE_ENSO / f"sstoi_{utc_today():%Y%m%d}.indices"
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
    result["series"] = [write_silver(clip_enso(enso, cutoff), enso_output or V4_ENSO),
                        write_silver(clip_weekly(weekly, cutoff), chirps_output or V4_CHIRPS)]
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


NEW_YEAR_GRACE_DAYS = 31   # a calendar year with no published week is tolerated only during its first month


def _latest_capture(year):
    folders = sorted(BRONZE_SALA.glob(f"{year}_*"))
    if not folders:
        raise FileNotFoundError(f"No Sala bronze snapshot for {year}")
    return folders[-1]


def _without_weeks(error):
    while error is not None:
        if isinstance(error, SalaYearWithoutWeeks):
            return True
        error = error.__cause__
    return False


async def sala_silver(*, offline=False, year=None, cutoff=V4_CUTOFF, refresh_years=None, output=None):
    """Capture or replay the confirmed Sala series under the caller's event loop.

    By default every year is scraped (or, with ``offline``, replayed from its newest capture). With ``refresh_years``
    only those years are scraped and the others are replayed from their newest capture, falling back to a live
    scrape of that year when there is none (or it does not replay). ``output`` replaces the V4 silver of the Release.

    During the first month of a calendar year the Sala may not have published any week of it yet; that last year is
    then skipped, provided the previous one was captured. Any other year without weeks is an error."""
    catalog = load_ubigeo_catalog(UBIGEO_CATALOG)
    targets = set(zip(catalog.provincia_sala, catalog.distrito_sala))
    last = year or date.today().year
    frames = []
    for item in range(SALA_FIRST_YEAR, last + 1):
        may_be_empty = (year is None and item == last and item > SALA_FIRST_YEAR and bool(frames)
                        and date.today() < date(item, 1, 1) + timedelta(days=NEW_YEAR_GRACE_DAYS))
        frame = None
        if offline or (refresh_years is not None and item not in refresh_years):
            try:
                frame = replay_sala(_latest_capture(item), item, catalog)
            except (FileNotFoundError, ValueError) as error:
                if offline:
                    if may_be_empty and isinstance(error, FileNotFoundError):
                        continue
                    raise
        if frame is None:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            folder = BRONZE_SALA / f"{item}_{stamp}"
            try:
                await scrape_sala(item, targets, folder)
            except RuntimeError as error:
                if not (may_be_empty and _without_weeks(error)):
                    raise
                if folder.is_dir() and not any(folder.glob("*.json")):
                    shutil.rmtree(folder)
                continue
            frame = replay_sala(folder, item, catalog)
        frames.append(frame)
    sala = pd.concat(frames, ignore_index=True).sort_values(["ubigeo", "anio", "semana"])
    return write_silver(clip_sala(sala, cutoff), output or V4_SALA)


def ensure_operational_release():
    """Extract from the Releases of the V4 only what the weekly operation reads and is still missing.

    The panel with its coverage file, the history and the district geography come from ``datos_v4.zip``; the frozen
    boosters from ``modelo_v4.zip``. A file that already exists is neither downloaded nor touched, and one that
    exists with other content stops the run (nothing is ever overwritten). The frozen silver of the sources that
    keep moving and ``data/gold/`` are not extracted: the operation writes its own sources apart."""
    manifest = release_bundles.manifest_path(version="v4")
    relative = lambda path: path.relative_to(ROOT).as_posix()
    data = [path for path in (V4_INTEGRATED, coverage_path(V4_INTEGRATED), V4_HISTORY, V4_GEOGRAPHY)
            if not path.is_file()]
    report = {}
    if data:
        report.update(release_bundles.fetch(manifest, only=["datos_v4.zip"],
                                            prefixes=tuple(relative(path) for path in data)))
    if not (V4_FROZEN / "paquete.json").is_file():
        report.update(release_bundles.fetch(manifest, only=["modelo_v4.zip"], prefixes=(relative(V4_FROZEN),)))
    return report


def historical_silver():
    return write_silver(build_weekly_cases(load_raw(BRONZE_EPI_CSV)), V4_HISTORY, line_ending="\n")


def socio_silver():
    raw = socio.load_raw(BRONZE_SOCIO / "data_socio_2017_2025.xlsx")
    return write_silver(socio.build_annual_socio(socio.clean_duplicates(raw)), V4_SOCIO, line_ending="\n")


def weather_socio_silver():
    weather = pd.read_csv(V4_PANEL_WEATHER, float_precision="round_trip")
    demographics = pd.read_csv(V4_SOCIO, dtype={"ubigeo": "string"}, float_precision="round_trip")
    weather["distrito"] = weather.distrito.replace(V4_NAME_ALIASES)
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
