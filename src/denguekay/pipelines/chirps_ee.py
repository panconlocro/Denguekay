"""
Unattended runs of the CHIRPS v3 ingestion from Earth Engine (study 06, step b-IV).

    python -u -m denguekay.pipelines.chirps_ee guard      # method guard in memory; writes nothing in data/
    python -u -m denguekay.pipelines.chirps_ee download   # monthly responses to bronze (resumable)

``download`` refuses to start unless ``guard`` passes in the same run.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date

from denguekay.config.paths import BRONZE_CHIRPS_EE_FINAL, BRONZE_CHIRPS_FINAL, DISTRICT_BOUNDARIES
from denguekay.data.ingestion import chirps_ee as ce
from denguekay.data.ingestion.chirps import git_commit

GUARD_DAYS = [date(2000, 1, d) for d in range(1, 25)]


def read_local_windows(days=GUARD_DAYS, folder=BRONZE_CHIRPS_FINAL):
    import rasterio

    windows, transform = {}, None
    for d in days:
        path = folder / f"{d.year}" / f"chirps-v3.0.sat.{d:%Y.%m.%d}.tif"
        with rasterio.open(path) as ds:
            windows[d] = ds.read(1)
            t = ds.transform
            if transform is not None and tuple(t)[:6] != tuple(transform)[:6]:
                raise ValueError(f"{path.name}: otra grilla.")
            transform = t
    return windows, tuple(transform)[:6]


def run_guard(ee, districts, log=print) -> dict:
    t0 = time.time()
    windows, transform = read_local_windows()
    shape = next(iter(windows.values())).shape
    projection = ce.native_projection(ee)
    grid = ce.check_grid(transform, projection["transform"])
    log(f"Grilla: {grid}")
    image, names = ce.daily_image(ee, GUARD_DAYS[0], date(2000, 1, 25))
    names = names.getInfo()
    expected = [ce.band_name(d) for d in GUARD_DAYS]
    if names != expected:
        raise RuntimeError(f"Earth Engine devolvió otros días: {names}")
    pix = ce.ee_pixels(ee, image, transform, shape, names)
    pixels = ce.check_pixels(windows, {d: pix[ce.band_name(d)] for d in GUARD_DAYS})
    log(f"(a) píxel: {pixels}")
    fc = ce.districts_fc(ee, districts)
    response = ee.data.computeFeatures({"expression": ce.reduce_month_expression(ee, image, fc, projection, names)})
    ee_means = ce.month_to_frame(response)
    local = ce.local_district_means(windows, transform, districts)
    polygons = ce.check_polygon_means(local, ee_means)
    log(f"(b) polígono: {polygons}")
    return {"pasa": grid["pasa"] and pixels["pasa"] and polygons["pasa"], "grilla": grid, "pixel": pixels,
            "poligono": polygons, "proyeccion_ee": projection, "segundos": round(time.time() - t0, 1)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("accion", choices=["guard", "download"])
    parser.add_argument("--desde", default=ce.FIRST_MONTH)
    parser.add_argument("--hasta", default=ce.LAST_MONTH)
    args = parser.parse_args(argv)

    import ee as ee_module

    ee = ce.initialize()
    districts = ce.load_districts()
    guard = run_guard(ee, districts)
    print(json.dumps({"guarda_pasa": guard["pasa"]}, ensure_ascii=False))
    if not guard["pasa"]:
        print("La guarda de método no pasa: no se baja nada.")
        return 1
    if args.accion == "guard":
        return 0

    fc = ce.districts_fc(ee, districts)
    projection = guard["proyeccion_ee"]
    month_list = ce.months(args.desde, args.hasta)
    summary = ce.download_months(month_list, lambda m: ce.fetch_month(ee, fc, projection, m),
                                 districts["ubigeo"].tolist())
    extra = {"coleccion": ce.COLLECTION, "banda": ce.BAND, "proyecto": ce.EE_PROJECT,
             "earthengine_api": ee_module.__version__, "meses_pedidos": [month_list[0], month_list[-1]],
             "reductor": "ee.Reducer.mean() ponderado por fracción de píxel, grilla nativa",
             "proyeccion": projection, "poligonos": str(DISTRICT_BOUNDARIES.name),
             "poligonos_sha256": ce.file_sha256(DISTRICT_BOUNDARIES), "commit": git_commit(),
             "guarda": guard}
    path = ce.write_run_manifest(summary, extra, BRONZE_CHIRPS_EE_FINAL)
    print(f"Manifiesto: {path}")
    print(json.dumps({k: summary[k] for k in ("estado", "error", "segundos")}, ensure_ascii=False))
    print(f"guardados {len(summary['guardados'])}, ya estaban {len(summary['ya_estaban'])}, "
          f"sin imágenes {summary['sin_imagenes']}, con observaciones {len(summary['revision'])}")
    return 0 if summary["estado"] == "completa" else 2


if __name__ == "__main__":
    sys.exit(main())
