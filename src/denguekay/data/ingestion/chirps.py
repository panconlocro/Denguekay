"""
Download CHIRPS v3 daily precipitation (final, ``sat`` disaggregation) for the Piura window only.

Each day is a global Cloud Optimized GeoTIFF on the CHC server; GDAL reads just the internal block that
holds Piura through HTTP range requests (about 112 KiB per day instead of ~17 MiB). Each day's window is
saved as is (values untouched, -9999 included) in data/bronze/chirps/v3_sat/final/AAAA/. A file is first
written under a temporary name and renamed when complete, and existing files are never overwritten, so a
cut run resumes by skipping the days already saved.

The server answers HTTP 429 after a burst of requests and publishes no rate policy: the first
``CALIBRATION_DAYS`` days measure it, the pause between days is adjusted from that, and the run stops if
the corrected estimate exceeds ``MAX_HOURS``. Every run leaves a manifest in data/bronze/chirps/v3_sat/.

Source: https://www.chc.ucsb.edu/data/chirps3 (CC BY 4.0).
"""

import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from denguekay.config.paths import BRONZE_CHIRPS, BRONZE_CHIRPS_FINAL, ROOT

PRODUCT = "CHIRPS v3.0 diario final, desagregación sat (COG)"
FINAL_URL = "https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/final/sat/cogs/{y}/chirps-v3.0.sat.{y}.{m:02d}.{d:02d}.cog"
FILE_NAME = "chirps-v3.0.sat.{y}.{m:02d}.{d:02d}.tif"
# Piura department: bounds of the GADM 4.1 level-3 polygons of Piura (64 districts) plus a 0.05° margin,
# computed on 2026-11-04 (lon_min, lat_min, lon_max, lat_max). It falls in one 512x512 block of the COG.
PIURA_BOUNDS = (-81.3804, -6.5268, -79.1604, -4.0326)
PIXEL_SIZE = 0.05
NODATA = -9999.0  # the files declare no nodata; the sea comes as -9999
USER_AGENT = "Denguekay-UPC-tesis/0.1 (+https://github.com/panconlocro/Denguekay)"
GDAL_ENV = {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "GDAL_HTTP_USERAGENT": USER_AGENT,
            "GDAL_HTTP_MAX_RETRY": "0", "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".cog,.tif"}

INITIAL_PAUSE = 2.0          # seconds between days until the calibration ends
CALIBRATION_DAYS = 50
MAX_HOURS = 16.0             # corrected estimate above this: stop and report
SAFETY = 0.8                 # keep the pace at 80 % of the rate measured before a 429
BACKOFF_START, BACKOFF_MAX = 120.0, 960.0
MAX_CONSECUTIVE_ERRORS = 5   # errors other than 429


class RateLimited(Exception):
    """The server answered HTTP 429."""


def day_url(day: date) -> str:
    return FINAL_URL.format(y=day.year, m=day.month, d=day.day)


def day_path(day: date, folder: Path = BRONZE_CHIRPS_FINAL) -> Path:
    return folder / f"{day.year}" / FILE_NAME.format(y=day.year, m=day.month, d=day.day)


def read_window(url: str, bounds: tuple = PIURA_BOUNDS) -> tuple[np.ndarray, dict]:
    """Read only ``bounds`` of a remote COG. Returns the array and its profile (transform, crs, size, nodata tag)."""
    import rasterio
    from rasterio.errors import RasterioIOError
    from rasterio.windows import from_bounds

    try:
        with rasterio.Env(**GDAL_ENV), rasterio.open("/vsicurl/" + url) as src:
            window = from_bounds(*bounds, transform=src.transform).round_offsets().round_lengths()
            data = src.read(1, window=window)
            profile = {"driver": "GTiff", "dtype": data.dtype.name, "count": 1, "height": data.shape[0],
                       "width": data.shape[1], "crs": src.crs, "transform": src.window_transform(window),
                       "nodata_declarado": src.nodata, "resolucion": src.res}
    except RasterioIOError as exc:
        if "429" in str(exc):
            raise RateLimited(str(exc)) from exc
        raise
    return data, profile


def save_window(data: np.ndarray, profile: dict, path: Path) -> bool:
    """Write the window as GeoTIFF (temporary name, then rename). Never overwrites: False if it exists."""
    import rasterio

    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    meta = {k: v for k, v in profile.items() if k not in ("nodata_declarado", "resolucion")}
    with rasterio.open(tmp, "w", **meta) as dst:
        dst.write(data, 1)
    os.replace(tmp, path)
    return True


def centroid_cells(transform, districts: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Row and column of each district centroid (lat/lon of the reference file) in a window."""
    from rasterio.transform import rowcol

    rows, cols = rowcol(transform, districts.lon.to_numpy(), districts.lat.to_numpy())
    return np.asarray(rows), np.asarray(cols)


def check_window(data: np.ndarray, profile: dict, districts: pd.DataFrame) -> dict:
    """Pixel size, no-data tag, values (>= 0 or -9999) and centroids on valid pixels of one day."""
    rows, cols = centroid_cells(profile["transform"], districts)
    inside = (rows >= 0) & (rows < data.shape[0]) & (cols >= 0) & (cols < data.shape[1])
    values = np.full(len(districts), np.nan)
    values[inside] = data[rows[inside], cols[inside]]
    res = profile.get("resolucion") or (profile["transform"].a, -profile["transform"].e)
    return {
        "forma": list(data.shape),
        "resolucion_ok": bool(np.allclose(np.abs(res), PIXEL_SIZE, atol=1e-6)),
        "nodata_declarado": profile.get("nodata_declarado"),
        "pixeles_sin_dato": int((data == NODATA).sum()),
        "otros_negativos": int(((data < 0) & (data != NODATA)).sum()),
        "centroides_fuera": districts.loc[~inside, "distrito"].tolist(),
        "centroides_sin_dato": districts.loc[inside & (values == NODATA), "distrito"].tolist(),
        "mascara_mar": (data == NODATA),
    }


def check_sample_days(days: list[date], districts: pd.DataFrame, reader=None) -> dict:
    """Run-start check on a few days (e.g. one of 2000 and one of 2025): the same -9999 sea mask and tag,
    the same shape and pixel size, values >= 0 or -9999, no centroid outside or on -9999. ``ok`` False: stop."""
    reader = reader or (lambda d: read_window(day_url(d)))
    checks = {d.isoformat(): check_window(*reader(d), districts) for d in days}
    first = next(iter(checks.values()))
    problems = []
    for name, c in checks.items():
        if not c["resolucion_ok"]:
            problems.append(f"{name}: tamaño de píxel distinto de {PIXEL_SIZE}")
        if c["otros_negativos"]:
            problems.append(f"{name}: {c['otros_negativos']} valores negativos distintos de -9999")
        if c["pixeles_sin_dato"] == 0:
            problems.append(f"{name}: no aparece -9999 (el mar debería venir así)")
        if c["centroides_fuera"] or c["centroides_sin_dato"]:
            problems.append(f"{name}: centroides fuera {c['centroides_fuera']} o sin dato {c['centroides_sin_dato']}")
        if c["forma"] != first["forma"] or c["nodata_declarado"] != first["nodata_declarado"]:
            problems.append(f"{name}: forma o nodata declarado distintos del primer día")
        elif not np.array_equal(c["mascara_mar"], first["mascara_mar"]):
            problems.append(f"{name}: la máscara de -9999 cambia respecto del primer día")
    summary = {k: {kk: vv for kk, vv in v.items() if kk != "mascara_mar"} for k, v in checks.items()}
    return {"ok": not problems, "problemas": problems, "dias": summary}


@dataclass
class Pacer:
    """Pause between days, measured during the first ``calibration_days`` days."""

    pause: float = INITIAL_PAUSE
    calibration_days: int = CALIBRATION_DAYS
    safety: float = SAFETY
    ok_times: list = field(default_factory=list)      # clock time of each successful day
    limited_times: list = field(default_factory=list)  # clock time of each 429
    read_seconds: list = field(default_factory=list)
    calibrated: bool = False

    def sustained_rate(self) -> float | None:
        """Days per minute between the start (or the last 429) and the next 429, median over those stretches."""
        if not self.limited_times:
            return None
        rates, start = [], self.ok_times[0] if self.ok_times else None
        for hit in self.limited_times:
            done = [t for t in self.ok_times if start is not None and start <= t <= hit]
            if len(done) >= 2 and hit > done[0]:
                rates.append(len(done) / ((hit - done[0]) / 60))
            later = [t for t in self.ok_times if t > hit]
            start = later[0] if later else None
        return float(np.median(rates)) if rates else None

    def calibrate(self) -> dict:
        """Set the pause from the measured rate (SAFETY of it) and return the measurement."""
        read = float(np.mean(self.read_seconds)) if self.read_seconds else 0.0
        rate = self.sustained_rate()
        if rate:
            self.pause = max(self.pause, 60.0 / (self.safety * rate) - read)
        self.calibrated = True
        return {"dias_medidos": len(self.ok_times), "respuestas_429": len(self.limited_times),
                "dias_por_minuto_antes_del_429": rate, "lectura_media_s": read, "pausa_s": self.pause,
                "peticiones_por_dia": 2}

    def seconds_per_day(self) -> float:
        return (float(np.mean(self.read_seconds)) if self.read_seconds else 0.0) + self.pause


def git_commit(root: Path = ROOT) -> str:
    try:
        out = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
        dirty = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"],
                               capture_output=True, text=True, check=True).stdout.strip()
        return out.stdout.strip() + (" (con cambios sin commitear)" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return "desconocido"


def write_manifest(summary: dict, folder: Path = BRONZE_CHIRPS) -> Path:
    """One JSON per run (never overwritten): code commit, product, range, days downloaded and failed, run date."""
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    path = folder / f"manifiesto_final_{stamp}.json"
    n = 1
    while path.exists():
        path = folder / f"manifiesto_final_{stamp}_{n}.json"
        n += 1
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return path


def download_final(start: str = "2000-01-01", end: str = "2025-12-31", *, folder: Path = BRONZE_CHIRPS_FINAL,
                   manifest_folder: Path = BRONZE_CHIRPS, reader=None, saver=save_window, sleep=time.sleep,
                   clock=time.monotonic, pacer: Pacer | None = None, max_hours: float = MAX_HOURS,
                   progress_every: int = 50) -> dict:
    """Download every missing day of [start, end]; resumable. Returns the run summary (also the manifest).

    States: "completa", "detenida_estimacion" (corrected estimate > max_hours after the calibration),
    "detenida_errores" (MAX_CONSECUTIVE_ERRORS errors in a row other than 429).
    """
    reader = reader or (lambda d: read_window(day_url(d)))
    pacer = pacer or Pacer()
    days = [d.date() for d in pd.date_range(start, end, freq="D")]
    pending = [d for d in days if not day_path(d, folder).exists()]
    summary = {"producto": PRODUCT, "url_ejemplo": day_url(days[0]), "ventana_lon_lat": PIURA_BOUNDS,
               "rango": [start, end], "dias_en_rango": len(days), "ya_existian": len(days) - len(pending),
               "descargados": 0, "fallidos": [], "commit": git_commit(), "user_agent": USER_AGENT,
               "inicio": datetime.now().isoformat(timespec="seconds"), "estado": "completa"}
    print(f"Días en el rango: {len(days)} | ya guardados: {summary['ya_existian']} | pendientes: {len(pending)}")
    errors, backoff, i = 0, BACKOFF_START, 0
    while i < len(pending):
        day = pending[i]
        t0 = clock()
        try:
            data, profile = reader(day)
        except RateLimited:
            pacer.limited_times.append(clock())
            print(f"HTTP 429 en {day}: espera {backoff / 60:.0f} min y reintenta")
            sleep(backoff)
            backoff = min(backoff * 2, BACKOFF_MAX)
            continue
        except Exception as exc:  # noqa: BLE001 - any other failure is recorded and the day skipped
            errors += 1
            summary["fallidos"].append({"dia": day.isoformat(), "error": str(exc)[:200]})
            print(f"Error en {day}: {exc}")
            if errors >= MAX_CONSECUTIVE_ERRORS:
                summary["estado"] = "detenida_errores"
                break
            i += 1
            continue
        pacer.read_seconds.append(clock() - t0)
        saver(data, profile, day_path(day, folder))
        pacer.ok_times.append(clock())
        summary["descargados"] += 1
        errors, backoff, i = 0, BACKOFF_START, i + 1
        if not pacer.calibrated and summary["descargados"] >= pacer.calibration_days:
            summary["calibracion"] = pacer.calibrate()
            hours = (len(pending) - i) * pacer.seconds_per_day() / 3600
            summary["estimacion_horas_restantes"] = round(hours, 2)
            print(f"Calibración: {summary['calibracion']} -> estimación restante {hours:.1f} h")
            if hours > max_hours:
                summary["estado"] = "detenida_estimacion"
                print(f"La estimación supera {max_hours} h: se detiene para revisar con Rosa.")
                break
        if summary["descargados"] % progress_every == 0:
            print(f"{summary['descargados']} días bajados en esta corrida; último {day}; quedan {len(pending) - i}")
        if i < len(pending):
            sleep(pacer.pause)
    summary["fin"] = datetime.now().isoformat(timespec="seconds")
    summary["pendientes_al_final"] = sum(not day_path(d, folder).exists() for d in days)
    summary["manifiesto"] = str(write_manifest(summary, manifest_folder))
    print(f"Estado: {summary['estado']} | bajados: {summary['descargados']} | fallidos: {len(summary['fallidos'])} | "
          f"pendientes: {summary['pendientes_al_final']} | manifiesto: {summary['manifiesto']}")
    return summary
