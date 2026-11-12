"""Measure the effect of gridding CHIRTS more coarsely on the same land support."""

import numpy as np
import pandas as pd
import rasterio

from compare_coastal_sources import cell_keys, summarize
from pilot_climate_exposure import CHIRTS_WEEKS, EQUAL_AREA, PILOT, grid_weights, pilot_geometry, sha256, write_json

FACTOR = 5
# A complete set of 5x5 blocks that contains all districts inside the downloaded window.
CROP = (slice(0, 50), slice(3, 48))
OUTPUT = PILOT / "resolucion_chirts"


def coarsen(native, area_by_row):
    """Average each block over its valid fine cells, then retain the original mask."""
    valid = np.isfinite(native)
    r, c = native.shape
    shape = (r // FACTOR, FACTOR, c // FACTOR, FACTOR)
    area = np.where(valid, area_by_row[:, None], 0.0)
    mass = area.reshape(shape).sum(axis=(1, 3))
    integral = (np.where(valid, native, 0.0) * area).reshape(shape).sum(axis=(1, 3))
    block_mean = np.divide(integral, mass, out=np.full_like(integral, np.nan), where=mass > 0)
    expanded = block_mean.repeat(FACTOR, axis=0).repeat(FACTOR, axis=1)
    return np.where(valid, expanded, np.nan)


def main():
    folder = PILOT / "insumos" / "chirts"
    pop = PILOT / "insumos" / "worldpop2020.tif"
    districts, _, _ = pilot_geometry()
    dates = [d for start in CHIRTS_WEEKS for d in pd.date_range(start, periods=7)]
    paths = [(kind, day, folder / f"CHIRTS-ERA5.daily_T{kind}.{day:%Y.%m.%d}.tif")
             for kind in ("max", "min") for day in dates]
    with rasterio.open(paths[0][2]) as source:
        transform, shape = source.transform, source.shape
    weights = grid_weights(districts, pop, transform, shape, 5)
    cells = cell_keys(weights)
    xy = (~transform) * (cells.lon.to_numpy(), cells.lat.to_numpy())
    r = np.floor(xy[1]).astype(int) - CROP[0].start
    c = np.floor(xy[0]).astype(int) - CROP[1].start
    if not ((r >= 0) & (r < 50) & (c >= 0) & (c < 45)).all():
        raise ValueError("Hay celdas distritales fuera de los bloques completos")
    lat_edges = transform.f + transform.e * np.arange(CROP[0].start, CROP[0].stop + 1)
    _, ys = EQUAL_AREA.transform(np.zeros_like(lat_edges), lat_edges)
    area = np.abs(np.diff(ys))
    parts = []
    for kind, day, path in paths:
        with rasterio.open(path) as source:
            if source.transform != transform or source.shape != shape:
                raise ValueError(f"Grilla distinta en {path.name}")
            raw = source.read(1)[CROP].astype(float)
            native = np.where(raw == -9999, np.nan, raw)
        coarse = coarsen(native, area)
        for name, values in (("chirts_005", native), ("chirts_025", coarse)):
            parts.append(cells.assign(resolucion=name, variable=f"t{kind}", fecha=day, valor=values[r, c]))
    panel = pd.concat(parts, ignore_index=True).pivot(
        index=["resolucion", "lat", "lon", "fecha"], columns="variable", values="valor").reset_index()
    daily = pd.concat([summarize(g, weights, ["tmax", "tmin"], source)
                       for source, g in panel.groupby("resolucion")], ignore_index=True)
    keys = ["ubigeo", "fecha", "variable"]
    fine, coarse = [daily[daily.fuente.eq(name)].set_index(keys).sort_index()
                    for name in ("chirts_005", "chirts_025")]
    for field in ("fraccion_poblacion", "fraccion_area"):
        pd.testing.assert_series_equal(fine[field], coarse[field])
    if fine.media_poblacion.isna().any() or coarse.media_poblacion.isna().any():
        raise ValueError("La comparación perdió distritos")
    week = daily.assign(semana=daily.fecha.dt.to_period("W-SAT").dt.start_time).groupby(
        ["ubigeo", "semana", "variable", "fuente"], as_index=False).media_poblacion.mean()
    differences = week.pivot(index=["ubigeo", "semana", "variable"], columns="fuente", values="media_poblacion")
    differences = differences.assign(delta_c=lambda d: d.chirts_005 - d.chirts_025).reset_index()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    differences.to_csv(OUTPUT / "diferencias_semanales.csv", index=False)
    write_json(OUTPUT / "manifiesto.json", {
        "metodo": "CHIRTS nativo versus agregación 5 por 5; máscara y población comunes",
        "ventana_grilla_fina": [[s.start, s.stop] for s in CROP], "semanas": CHIRTS_WEEKS,
        "sha256_worldpop": sha256(pop), "sha256_ventanas": {p.name: sha256(p) for _, _, p in paths},
    })
    print(differences.groupby("variable").delta_c.agg(
        pares="size", mediana_abs=lambda v: v.abs().median(),
        max_abs=lambda v: v.abs().max(), mayores_a_un_grado=lambda v: v.abs().gt(1).sum()))


if __name__ == "__main__":
    main()
