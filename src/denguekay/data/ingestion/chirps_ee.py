"""
CHIRPS v3 daily final (sat) from Google Earth Engine: area-weighted mean per district polygon (study 06, step b-IV).

Collection ``UCSB-CHC/CHIRPS/V3/DAILY_SAT`` (band ``precipitation``, mm/d, 0.05 deg; public domain; cite CHIRPS3
Data Repository, doi:10.15780/G2JQ0P). For each month, the daily images become one image with a band per day
(``pAAAAMMDD``) and ``reduceRegions`` takes the mean over each polygon of data/reference/distritos_piura_limites.geojson
on the native grid (no resampling). Earth Engine weights each pixel by the fraction of it inside the polygon,
so the result is the area-weighted mean. The response of each month is saved in bronze as it arrives
(``ee_final/AAAA/AAAA-MM.json``), with one manifest per run; the run resumes and stops at the first error.

Method guard (before writing anything), on the 24 final days already downloaded from the CHC COGs:
(a) pixel: Earth Engine's values on the Piura window equal the CHC file, on the same grid;
(b) polygon: Earth Engine's area-weighted mean equals the same mean computed here from the polygons.
The tolerances below were fixed and committed before running the guard; they are not loosened.

Authentication is the user's (``ee.Authenticate`` stores the credentials in the user profile, outside the repo);
this module only calls ``ee.Initialize(project=...)``. ``ee`` is imported inside the functions so that the
package and its tests never need it nor the network.
"""

from __future__ import annotations

import calendar
import hashlib
import json
import os
import time
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from denguekay.config.paths import BRONZE_CHIRPS_EE_FINAL, DISTRICT_BOUNDARIES

COLLECTION = "UCSB-CHC/CHIRPS/V3/DAILY_SAT"
BAND = "precipitation"
EE_PROJECT = os.environ.get("DENGUEKAY_EE_PROJECT", "denguekay")
NODATA = -9999.0
FIRST_MONTH = "2000-01"
LAST_MONTH = "2026-09"   # last final day in Earth Engine on 2026-11-06: 2026-09-30

# --- Method-guard tolerances (fixed before running the guard; do not loosen) -------------------------------
# (a) pixel: float32 values copied from the same source; any difference above this is not rounding.
PIXEL_TOLERANCE_MM = 1e-4
# Grid: the CHC window must lie on Earth Engine's native grid (same pixel size; origin offset an integer number
# of pixels). The CHC GeoTIFF stores its geotransform with float32-like rounding (-81.3999985 for -81.40).
GRID_TOLERANCE_DEG = 1e-5
# (b) polygon mean, per district and day: |EE - local| <= max(abs, rel * |local|). Earth Engine stores the pixel
# coverage as 8-bit weights (1/256), so small districts split between pixels can differ slightly.
POLYGON_TOLERANCE_ABS_MM = 0.05
POLYGON_TOLERANCE_REL = 0.02
# Pixel fractions below this are floating-point noise along edges (not part of the guard tolerances).
MIN_FRACTION = 1e-9


# --- Months and band names ---------------------------------------------------------------------------------

def months(first: str = FIRST_MONTH, last: str = LAST_MONTH) -> list[str]:
    """Inclusive list of ``AAAA-MM`` months."""
    out = []
    y, m = map(int, first.split("-"))
    ly, lm = map(int, last.split("-"))
    while (y, m) <= (ly, lm):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def month_days(month: str) -> list[date]:
    y, m = map(int, month.split("-"))
    return [date(y, m, d) for d in range(1, calendar.monthrange(y, m)[1] + 1)]


def band_name(day: date) -> str:
    return f"p{day:%Y%m%d}"


def month_path(month: str, folder: Path = BRONZE_CHIRPS_EE_FINAL) -> Path:
    return folder / month[:4] / f"{month}.json"


# --- Local area-weighted mean (the reference of guard b and of the preliminary) -----------------------------

def coverage_weights(geometry, transform, shape: tuple[int, int]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Rows, columns and fraction of each pixel of the grid covered by ``geometry`` (same CRS as the grid).

    The fraction is the planar intersection area over the pixel area, in the grid's own coordinates (degrees),
    as Earth Engine computes it on the native grid. Stops if the polygon is not fully inside the grid.
    """
    import shapely
    from shapely.geometry import box

    a, _, x0, _, e, y0 = transform[:6]
    height, width = shape
    minx, miny, maxx, maxy = geometry.bounds
    c0, c1 = int(np.floor((minx - x0) / a)), int(np.ceil((maxx - x0) / a))
    r0, r1 = int(np.floor((maxy - y0) / e)), int(np.ceil((miny - y0) / e))
    if c0 < 0 or r0 < 0 or c1 > width or r1 > height:
        raise ValueError("El polígono se sale de la ventana: la media quedaría incompleta.")
    rows, cols = np.meshgrid(np.arange(r0, r1), np.arange(c0, c1), indexing="ij")
    rows, cols = rows.ravel(), cols.ravel()
    boxes = [box(x0 + c * a, y0 + (r + 1) * e, x0 + (c + 1) * a, y0 + r * e) for r, c in zip(rows, cols)]
    frac = shapely.area(shapely.intersection(geometry, boxes)) / abs(a * e)
    keep = frac > MIN_FRACTION   # floating-point slivers along shared edges are not area
    covered = frac[keep].sum() * abs(a * e)
    if not np.isclose(covered, geometry.area, rtol=1e-9):
        raise ValueError("La cobertura de píxeles no suma el área del polígono.")
    return rows[keep], cols[keep], frac[keep]


def weighted_mean(data: np.ndarray, rows: np.ndarray, cols: np.ndarray, weights: np.ndarray) -> float:
    """Area-weighted mean of the valid pixels (``-9999`` and NaN are no data and weigh nothing)."""
    values = data[rows, cols].astype("float64")
    valid = np.isfinite(values) & (values != NODATA)
    if not valid.any():
        return float("nan")
    return float(np.sum(values[valid] * weights[valid]) / np.sum(weights[valid]))


def local_district_means(windows: dict[date, np.ndarray], transform, districts) -> pd.DataFrame:
    """Area-weighted mean per district and day from local windows; columns ``ubigeo``, ``fecha``, ``precip_mm``."""
    shape = next(iter(windows.values())).shape
    weights = {u: coverage_weights(g, transform, shape) for u, g in zip(districts["ubigeo"], districts.geometry)}
    rows = [{"ubigeo": u, "fecha": d, "precip_mm": weighted_mean(arr, *weights[u])}
            for d, arr in windows.items() for u in weights]
    return pd.DataFrame(rows)


# --- Guard checks (pure: they compare arrays and tables already in memory) ----------------------------------

def check_grid(window_transform, ee_transform: list[float]) -> dict:
    """The CHC window must sit on Earth Engine's native grid."""
    a, _, x0, _, e, y0 = window_transform[:6]
    ea, _, ex0, _, ee_, ey0 = ee_transform[:6]
    off_x, off_y = (x0 - ex0) / ea, (y0 - ey0) / ee_
    ok = (abs(a - ea) <= GRID_TOLERANCE_DEG and abs(e - ee_) <= GRID_TOLERANCE_DEG
          and abs(off_x - round(off_x)) * abs(ea) <= GRID_TOLERANCE_DEG
          and abs(off_y - round(off_y)) * abs(ee_) <= GRID_TOLERANCE_DEG)
    return {"pasa": bool(ok), "pixel_chc": [a, e], "pixel_ee": [ea, ee_],
            "desfase_pixeles": [off_x, off_y]}


def check_pixels(chc: dict[date, np.ndarray], ee_values: dict[date, np.ndarray]) -> dict:
    """Guard (a): same no-data mask and |EE - CHC| <= PIXEL_TOLERANCE_MM on every valid pixel of every day."""
    max_diff, mask_mismatch, n = 0.0, 0, 0
    for d, a in chc.items():
        b = ee_values[d]
        if a.shape != b.shape:
            raise ValueError(f"{d}: forma distinta {a.shape} frente a {b.shape}.")
        na, nb = (a == NODATA) | ~np.isfinite(a), (b == NODATA) | ~np.isfinite(b)
        mask_mismatch += int(np.sum(na != nb))
        both = ~na & ~nb
        n += int(both.sum())
        if both.any():
            max_diff = max(max_diff, float(np.max(np.abs(a[both].astype("float64") - b[both].astype("float64")))))
    return {"pasa": mask_mismatch == 0 and max_diff <= PIXEL_TOLERANCE_MM, "dif_max_mm": max_diff,
            "pixeles_comparados": n, "pixeles_mascara_distinta": mask_mismatch, "dias": len(chc),
            "tolerancia_mm": PIXEL_TOLERANCE_MM}


def check_polygon_means(local: pd.DataFrame, ee_means: pd.DataFrame) -> dict:
    """Guard (b): per district and day, |EE - local| <= max(abs, rel * |local|), and no nulls on either side."""
    m = local.merge(ee_means, on=["ubigeo", "fecha"], how="outer", suffixes=("_local", "_ee"), indicator=True)
    unmatched = int((m["_merge"] != "both").sum())
    nulls = int(m["precip_mm_local"].isna().sum() + m["precip_mm_ee"].isna().sum())
    diff = (m["precip_mm_ee"] - m["precip_mm_local"]).abs()
    allowed = np.maximum(POLYGON_TOLERANCE_ABS_MM, POLYGON_TOLERANCE_REL * m["precip_mm_local"].abs())
    over = diff > allowed
    worst = m.loc[diff.idxmax()] if diff.notna().any() else None
    rel = (diff / m["precip_mm_local"].abs()).where(m["precip_mm_local"].abs() >= 1.0)
    return {
        "pasa": unmatched == 0 and nulls == 0 and not bool(over.any()),
        "pares": int(len(m)), "sin_pareja": unmatched, "nulos": nulls, "fuera_de_tolerancia": int(over.sum()),
        "dif_max_mm": float(diff.max()), "dif_media_mm": float(diff.mean()),
        "dif_rel_max_si_local_ge_1mm": float(rel.max()) if rel.notna().any() else None,
        "peor": None if worst is None else {"ubigeo": worst["ubigeo"], "fecha": str(worst["fecha"]),
                                            "local": float(worst["precip_mm_local"]), "ee": float(worst["precip_mm_ee"])},
        "tolerancia": {"abs_mm": POLYGON_TOLERANCE_ABS_MM, "rel": POLYGON_TOLERANCE_REL},
    }


# --- Earth Engine side -------------------------------------------------------------------------------------

def initialize(project: str = EE_PROJECT):
    import ee

    ee.Initialize(project=project)
    return ee


def districts_fc(ee, districts):
    """FeatureCollection with the polygons and only ``ubigeo`` as property."""
    geo = json.loads(districts[["ubigeo", "geometry"]].to_json())
    return ee.FeatureCollection(geo)


def native_projection(ee) -> dict:
    """CRS and affine transform of the collection's native grid."""
    return ee.ImageCollection(COLLECTION).first().select(BAND).projection().getInfo()


def daily_image(ee, start: date, end_exclusive: date):
    """One image with a band ``pAAAAMMDD`` per day in [start, end_exclusive), and the list of days found."""
    col = ee.ImageCollection(COLLECTION).filterDate(start.isoformat(), end_exclusive.isoformat()).select(BAND)
    names = col.aggregate_array("system:time_start").map(
        lambda t: ee.String("p").cat(ee.Date(t).format("YYYYMMdd")))
    return col.toBands().rename(names), names


def ee_pixels(ee, image, window_transform, shape: tuple[int, int], band_names: list[str]) -> dict[str, np.ndarray]:
    """Guard (a): the pixels of ``image`` on the CHC window grid (no resampling: same grid), masked as -9999."""
    a, _, x0, _, e, y0 = window_transform[:6]
    height, width = shape
    arr = ee.data.computePixels({
        "expression": image.unmask(NODATA),
        "fileFormat": "NUMPY_NDARRAY",
        "grid": {"dimensions": {"width": width, "height": height},
                 "affineTransform": {"scaleX": a, "shearX": 0, "translateX": x0,
                                     "shearY": 0, "scaleY": e, "translateY": y0},
                 "crsCode": "EPSG:4326"},
    })
    return {b: np.asarray(arr[b]) for b in band_names}


def reduce_month_expression(ee, image, fc, projection: dict, band_names):
    """``reduceRegions`` with the weighted mean on the native grid, keeping only ``ubigeo`` and the day bands."""
    reduced = image.reduceRegions(collection=fc, reducer=ee.Reducer.mean(),
                                  crs=projection["crs"], crsTransform=projection["transform"])
    return reduced.select(ee.List(["ubigeo"]).cat(band_names), None, False)


def fetch_month(ee, fc, projection: dict, month: str):
    """Raw ``computeFeatures`` response for one month, plus the band names Earth Engine found."""
    days = month_days(month)
    start, end = days[0], date.fromordinal(days[-1].toordinal() + 1)
    image, names = daily_image(ee, start, end)
    names = names.getInfo()
    if not names:
        return None, []
    expr = reduce_month_expression(ee, image, fc, projection, names)
    return ee.data.computeFeatures({"expression": expr}), names


# --- Parsing the saved responses ---------------------------------------------------------------------------

def features_of(response) -> list[dict]:
    if isinstance(response, dict):
        return response.get("features", [])
    return list(response)


def month_to_frame(response) -> pd.DataFrame:
    """Long table ``ubigeo``, ``fecha``, ``precip_mm`` from one saved monthly response (missing values -> NaN)."""
    rows = []
    for f in features_of(response):
        props = f.get("properties", {})
        u = str(props.get("ubigeo"))
        for k, v in props.items():
            if k.startswith("p") and len(k) == 9 and k[1:].isdigit():
                rows.append({"ubigeo": u, "fecha": datetime.strptime(k[1:], "%Y%m%d").date(),
                             "precip_mm": np.nan if v is None else float(v)})
    return pd.DataFrame(rows, columns=["ubigeo", "fecha", "precip_mm"])


def check_month(response, month: str, ubigeos: list[str]) -> dict:
    """Districts, missing days and nulls of one monthly response."""
    df = month_to_frame(response)
    expected_days = set(month_days(month))
    got_days = set(df["fecha"])
    got_ub = set(df["ubigeo"])
    nulls = df[df["precip_mm"].isna()]
    return {"mes": month, "distritos": len(got_ub), "distritos_faltantes": sorted(set(ubigeos) - got_ub),
            "dias": len(got_days), "dias_faltantes": sorted(str(d) for d in expected_days - got_days),
            "nulos": [{"ubigeo": r.ubigeo, "fecha": str(r.fecha)} for r in nulls.itertuples()]}


# --- Download (resumable; stops at the first error) --------------------------------------------------------

def save_json(obj, path: Path) -> bool:
    """Atomic write; never overwrites (False if it exists)."""
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    return True


def file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def download_months(month_list: list[str], fetch, ubigeos: list[str], *, folder: Path = BRONZE_CHIRPS_EE_FINAL,
                    log=print) -> dict:
    """Fetch and save each month not yet in bronze, in order. ``fetch(month) -> (response, band_names)``.

    Stops at the first exception (quota, network or any other) and reports it; months already saved are skipped.
    """
    t0 = time.time()
    summary = {"guardados": [], "ya_estaban": [], "sin_imagenes": [], "revision": [], "error": None,
               "estado": "completa"}
    for month in month_list:
        path = month_path(month, folder)
        if path.exists():
            summary["ya_estaban"].append(month)
            continue
        try:
            response, names = fetch(month)
        except Exception as exc:  # noqa: BLE001 - stop on any failure and report it
            summary["error"] = {"mes": month, "tipo": type(exc).__name__, "mensaje": str(exc)[:500]}
            summary["estado"] = "detenida_error"
            log(f"{month}: error {type(exc).__name__}: {str(exc)[:200]}. Se detiene.")
            break
        if response is None:
            summary["sin_imagenes"].append(month)
            log(f"{month}: sin imágenes en la colección.")
            continue
        save_json(response, path)
        check = check_month(response, month, ubigeos)
        summary["guardados"].append(month)
        if check["distritos_faltantes"] or check["dias_faltantes"] or check["nulos"]:
            summary["revision"].append(check)
        log(f"{month}: {check['distritos']} distritos, {check['dias']} días, {len(check['nulos'])} nulos "
            f"({time.time() - t0:.0f} s)")
    summary["segundos"] = round(time.time() - t0, 1)
    return summary


def write_run_manifest(summary: dict, extra: dict, folder: Path = BRONZE_CHIRPS_EE_FINAL) -> Path:
    """One JSON per run, never overwritten."""
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    path = folder / f"manifiesto_ee_{stamp}.json"
    n = 1
    while path.exists():
        path = folder / f"manifiesto_ee_{stamp}_{n}.json"
        n += 1
    body = {**extra, **summary, "escrito_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    path.write_text(json.dumps(body, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return path


def load_districts(path: Path = DISTRICT_BOUNDARIES):
    import geopandas as gpd

    g = gpd.read_file(path)
    g["ubigeo"] = g["ubigeo"].astype(str)
    return g.sort_values("ubigeo").reset_index(drop=True)
