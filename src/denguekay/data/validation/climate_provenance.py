"""Source, product and extraction date of every climate source (HU0002-1).

Read-only. The date of each source comes from where the pipeline already leaves it:

- NOAA CPC (Niño 1+2): the date in the name of the raw file ``sstoi_AAAAMMDD.indices`` (one file per download).
- CHIRPS v3: the manifests that the downloads write next to the data (``escrito_utc`` for Earth Engine and
  ``fecha_descarga`` for the CHC FTP).
- ERA5-Land of the recent weeks: the folder ``AAAA-MM-DD`` is the last day of data, not the extraction; the weekly update
  writes the UTC instant of the extraction in ``AAAA-MM-DD.captura.json`` next to it (without it, the folder name is
  shown and marked as the last day of data).
- The historical Open-Meteo and ERA5-Land caches have no extraction date on record: they are shown with the freeze
  date of the Release ``model/v4`` and marked as such (an upper bound, not the day they were downloaded).
"""

from datetime import date, datetime
import json
from pathlib import Path
import re

from denguekay.config.paths import (
    BRONZE_CHIRPS_EE_FINAL, BRONZE_CHIRPS_FINAL_FTP, BRONZE_CHIRPS_PRELIM, BRONZE_ENSO, CACHE_METEO,
    CACHE_METEO_ERA5_LAND_2000_2016, CACHE_METEO_ERA5_LAND_2017_2025, CACHE_METEO_ERA5_LAND_2026,
    CACHE_METEO_ERA5_LAND_RECENT, MODEL_REGISTRY,
)

FREEZE_KIND = "congelamiento del Release model/v4 (la fecha real de extracción no se registró)"
CAPTURE_KIND = "captura registrada"
LAST_DAY_KIND = "último día de datos del caché (la fecha real de extracción no se registró)"
ENSO_NAME = re.compile(r"^sstoi_(\d{8})\.indices$")
DAY_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CHIRPS_PRODUCTS = {
    "final_ee": "CHIRPS v3.0 diario final, desagregación sat (Earth Engine, UCSB-CHC/CHIRPS/V3/DAILY_SAT, banda "
                "precipitation)",
    "final_ftp": "CHIRPS v3.0 diario final, desagregación sat (GeoTIFF por FTP del CHC)",
    "prelim_ftp": "CHIRPS v3.0 diario preliminar, desagregación sat (GeoTIFF por FTP del CHC)",
}


def freeze_date(registry=MODEL_REGISTRY):
    """Freeze date of the V4 (``fecha_congelamiento`` of its card), or ``None``."""
    path = Path(registry) / "v4" / "ficha.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8")).get("fecha_congelamiento")


def _iso(text):
    """``AAAAMMDD...`` or ``AAAA-MM-DD...`` -> ISO date, or ``None``."""
    text = str(text or "")
    if re.match(r"^\d{8}", text):
        return datetime.strptime(text[:8], "%Y%m%d").date().isoformat()
    if re.match(r"^\d{4}-\d{2}-\d{2}", text):
        return date.fromisoformat(text[:10]).isoformat()
    return None


def _row(source, product, dates, kind, reference):
    dates = sorted(set(d for d in dates if d))
    return {"fuente": source, "producto": product, "fecha_extraccion": dates[-1] if dates else None,
            "capturas": len(dates), "tipo_de_fecha": kind if dates else "sin capturas", "referencia": reference}


def _manifests(folder, pattern, key):
    dates = []
    for path in sorted(Path(folder).glob(pattern)) if Path(folder).is_dir() else []:
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if manifest.get("estado") == "completa":
            dates.append(_iso(manifest.get(key)))
    return dates


def climate_sources(*, enso=BRONZE_ENSO, chirps_ee=BRONZE_CHIRPS_EE_FINAL, chirps_final=BRONZE_CHIRPS_FINAL_FTP,
                    chirps_prelim=BRONZE_CHIRPS_PRELIM, era5_recent=CACHE_METEO_ERA5_LAND_RECENT,
                    historical=None, frozen=None):
    """Table of climate sources: source, product, extraction date, kind of date and reference."""
    frozen = freeze_date() if frozen is None else frozen
    historical = historical or {
        "Open-Meteo (clima del panel 2017-2025)": CACHE_METEO,
        "ERA5-Land 2000-2016": CACHE_METEO_ERA5_LAND_2000_2016,
        "ERA5-Land 2017-2025": CACHE_METEO_ERA5_LAND_2017_2025,
        "ERA5-Land 2026 (hasta el 31 de octubre)": CACHE_METEO_ERA5_LAND_2026,
    }
    enso_dates = [_iso(m.group(1)) for m in (ENSO_NAME.match(p.name) for p in
                                              (Path(enso).iterdir() if Path(enso).is_dir() else [])) if m]
    recent_files = list(Path(era5_recent).iterdir()) if Path(era5_recent).is_dir() else []
    recent_folders = [_iso(p.name) for p in recent_files if p.is_dir() and DAY_NAME.match(p.name)]
    recent_extracted = []
    for path in recent_files:   # ``AAAA-MM-DD.captura.json``: the UTC instant at which the folder was complete
        if path.name.endswith(".captura.json"):
            try:
                recent_extracted.append(_iso(json.loads(path.read_text(encoding="utf-8")).get("extraido_utc")))
            except (OSError, ValueError):
                continue
    rows = [
        _row("NOAA CPC", "Niño 1+2: anomalía mensual de la TSM (OISST v2.1, sstoi.indices)", enso_dates, CAPTURE_KIND,
             "fecha del nombre del archivo sstoi_AAAAMMDD.indices (bronze/enso)"),
        _row("CHIRPS v3 (Earth Engine)", CHIRPS_PRODUCTS["final_ee"], _manifests(chirps_ee, "manifiesto_ee_*.json",
                                                                            "escrito_utc"), CAPTURE_KIND,
             "manifiesto_ee_*.json (bronze/chirps/v3_sat/ee_final)"),
        _row("CHIRPS v3 (FTP del CHC)", CHIRPS_PRODUCTS["final_ftp"],
             _manifests(chirps_final, "manifiesto_ftp_final_*.json", "fecha_descarga"), CAPTURE_KIND,
             "manifiesto_ftp_final_*.json (bronze/chirps/v3_sat/final_ftp)"),
        _row("CHIRPS v3 preliminar (FTP del CHC)", CHIRPS_PRODUCTS["prelim_ftp"],
             _manifests(chirps_prelim, "manifiesto_ftp_prelim_*.json", "fecha_descarga"), CAPTURE_KIND,
             "manifiesto_ftp_prelim_*.json (bronze/chirps/v3_sat/prelim)"),
        _row("ERA5-Land (semanas recientes)",
             "ERA5-Land 0,1° vía Open-Meteo (archive API, models=era5_land), variables diarias",
             recent_extracted or recent_folders, CAPTURE_KIND if recent_extracted else LAST_DAY_KIND,
             "AAAA-MM-DD.captura.json (extraido_utc) junto a la carpeta (bronze/meteo/cache_meteo_era5_land_reciente)"
             if recent_extracted else "nombre de la carpeta AAAA-MM-DD (bronze/meteo/cache_meteo_era5_land_reciente)"),
    ]
    for label, folder in historical.items():
        present = Path(folder).is_dir() and any(Path(folder).iterdir())
        product = ("Open-Meteo archive API (sin models), variables diarias" if label.startswith("Open-Meteo")
                   else "ERA5-Land 0,1° vía Open-Meteo (archive API, models=era5_land), variables diarias")
        rows.append(_row(label, product, [_iso(frozen)] if present else [], FREEZE_KIND,
                         f"caché histórica ({Path(folder).name}); fecha de congelamiento de la ficha de la V4"))
    return rows
