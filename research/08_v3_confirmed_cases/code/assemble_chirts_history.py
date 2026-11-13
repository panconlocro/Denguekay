"""Aggregate CHIRTS at native and coarsened resolutions with common support."""

import argparse
from pathlib import Path

from affine import Affine
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix

from assemble_era5_candidate import OUTPUT as ERA5_OUTPUT, YEARS
from chirts_resolution import CROP, coarsen
from pilot_climate_exposure import EQUAL_AREA, PILOT, grid_weights, pilot_geometry, sha256, write_json

OUTPUT = PILOT / "resolucion_chirts" / "historico"
COLS = ("tmax_fina", "tmin_fina", "tmax_gruesa", "tmin_gruesa")
MIN_POPULATION = .95
MIN_DAYS = 5


def daily_weather(path):
    with np.load(path) as raw:
        dates = pd.DatetimeIndex(raw["fecha"])
        lat, lon = raw["lat"], raw["lon"]
        if not (dates.equals(pd.date_range(dates.min(), dates.max()))
                and np.allclose(np.diff(lat), -.05, atol=1e-4)
                and np.allclose(np.diff(lon), .05, atol=1e-4)):
            raise ValueError("Grilla CHIRTS diaria no regular")
        high, low = [raw[field].astype(np.float32) * .1 for field in ("Tmax", "Tmin")]
    numeric = (high >= -90) & (high <= 57) & (low >= -90) & (low <= 57)
    valid = numeric & (low <= high)
    missing_day = ~(valid[:, CROP[0], CROP[1]].any(axis=(1, 2)))
    transform = Affine(.05, 0, round(float(lon[0])-.025, 4), 0, -.05, round(float(lat[0])+.025, 4))
    lat_edges = transform.f + transform.e * np.arange(CROP[0].start, CROP[0].stop+1)
    _, ys = EQUAL_AREA.transform(np.zeros_like(lat_edges), lat_edges)
    area = np.abs(np.diff(ys))
    weather = {}
    for name, values in (("tmax", high), ("tmin", low)):
        fine = np.where(valid, values, np.nan)[:, CROP[0], CROP[1]]
        weather[f"{name}_fina"] = fine
        weather[f"{name}_gruesa"] = np.stack([coarsen(frame, area) for frame in fine]).astype(np.float32)
    diagnostics = {"dias_vacios_en_ventana": dates[missing_day].strftime("%Y-%m-%d").tolist(),
                   "pares_celda_dia_invertidos": int((numeric & (high < low)).sum())}
    return dates, transform, high.shape[1:], weather, diagnostics


def weighted_daily(dates, transform, shape, weather):
    districts, _, _ = pilot_geometry()
    ubigeos = sorted(districts.ubigeo)
    population = {y: ERA5_OUTPUT / "insumos" / f"worldpop{y}.tif" for y in YEARS[:-1]}
    population[2020] = PILOT / "insumos" / "worldpop2020.tif"
    weeks = dates.to_period("W-SAT").start_time
    epoch = np.asarray(YEARS)[np.searchsorted(YEARS, weeks.year, side="right")-1]
    parts = []
    for year in YEARS:
        select = epoch == year
        if not select.any():
            continue
        weights = grid_weights(districts, population[year], transform, shape, 5)
        xy = (~transform) * (weights.lon.to_numpy(), weights.lat.to_numpy())
        r = np.floor(xy[1]).astype(int) - CROP[0].start
        c = np.floor(xy[0]).astype(int) - CROP[1].start
        h, w = weather[COLS[0]].shape[1:]
        if not ((r >= 0) & (r < h) & (c >= 0) & (c < w)).all():
            raise ValueError("Celdas distritales fuera de la ventana CHIRTS")
        district_index = pd.Index(ubigeos).get_indexer(weights.ubigeo)
        pop = weights.personas / weights.groupby("ubigeo").personas.transform("sum")
        matrix = csr_matrix((pop, (district_index, r*w+c)), shape=(len(ubigeos), h*w))
        np.testing.assert_allclose(np.asarray(matrix.sum(axis=1)).ravel(), 1, atol=1e-10, rtol=0)
        support = np.isfinite(weather[COLS[0]][select].reshape(-1, h*w))
        coverage = (matrix @ support.T).T
        rows = pd.MultiIndex.from_product([dates[select], ubigeos], names=["fecha", "ubigeo"]).to_frame(index=False)
        rows["cobertura_poblacion"] = coverage.ravel()
        for col in COLS:
            values = weather[col][select].reshape(-1, h*w)
            np.testing.assert_array_equal(np.isfinite(values), support)
            sums = (matrix @ np.where(support, values, 0).T).T
            rows[col] = np.divide(sums, coverage, out=np.full_like(sums, np.nan),
                                  where=coverage >= MIN_POPULATION).ravel()
        parts.append(rows)
    return pd.concat(parts, ignore_index=True), population


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("daily", type=Path)
    args = parser.parse_args()
    dates, transform, shape, weather, diagnostics = daily_weather(args.daily)
    daily, population = weighted_daily(dates, transform, shape, weather)
    daily["semana_inicio"] = daily.fecha.dt.to_period("W-SAT").dt.start_time
    groups = daily.groupby(["semana_inicio", "ubigeo"], sort=True)
    if not groups.size().eq(7).all():
        raise ValueError("Semana CHIRTS incompleta en el calendario")
    weekly = groups[list(COLS)].mean()
    weekly["dias_validos"] = groups[COLS[0]].count()
    weekly["cobertura_minima"] = groups.cobertura_poblacion.min()
    weekly.loc[weekly.dias_validos.lt(MIN_DAYS), list(COLS)] = np.nan
    weekly = weekly.reset_index()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    weekly.to_csv(OUTPUT / "chirts_resoluciones_semanal.csv.gz", index=False)
    counts = weekly.dias_validos.value_counts().sort_index().to_dict()
    write_json(OUTPUT / "manifiesto.json", {
        "semanas": int(weekly.semana_inicio.nunique()), "distritos": int(weekly.ubigeo.nunique()),
        "filas": len(weekly), "dias_validos_por_fila": {str(k): int(v) for k, v in counts.items()},
        "cobertura_poblacion_minima_diaria": MIN_POPULATION, "dias_minimos_semana": MIN_DAYS,
        **diagnostics, "sha256_diario": sha256(args.daily),
        "sha256_poblacion": {str(y): sha256(p) for y, p in population.items()},
    })
    print("CHIRTS semanal", len(weekly), counts, diagnostics, flush=True)


if __name__ == "__main__":
    main()
