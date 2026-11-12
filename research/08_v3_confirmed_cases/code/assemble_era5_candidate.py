"""Build a weekly, population-weighted ERA5 candidate for the paper."""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from compare_coastal_sources import ERA5_GRID, ERA5_SHAPE
from pilot_climate_exposure import DAY, PILOT, grid_weights, pilot_geometry, sha256, write_json

OUTPUT = PILOT / "candidato_era5"
YEARS = (2000, 2005, 2010, 2015, 2020)
VARIABLES = ("tmedia", "tmax", "tmin", "hr")
# Daily differences allowed between two deliveries of the same reanalysis.
LIMITS = {"tmedia": (.2, .5), "tmax": (.5, 1.0), "tmin": (.5, 1.0), "hr": (2.0, 4.0)}


def read_daily(path):
    with np.load(path) as source:
        data = {name: source[name] for name in ["fecha", "lat", "lon", *VARIABLES]}
    dates = pd.DatetimeIndex(data["fecha"])
    if not dates.equals(pd.date_range(dates.min(), dates.max())):
        raise ValueError(f"Días incompletos en {path.name}")
    for field in VARIABLES:
        if data[field].shape != (len(dates), len(data["lat"])) or not np.isfinite(data[field]).all():
            raise ValueError(f"Valores inválidos en {path.name}/{field}")
    if ((data["tmin"] > data["tmedia"]).any() or (data["tmedia"] > data["tmax"]).any()
            or not ((data["hr"] > 0) & (data["hr"] <= 100)).all()):
        raise ValueError(f"Extremos o humedad fuera del rango físico en {path.name}")
    return data, dates


def join_deliveries(hist_path, recent_path):
    hist, old_dates = read_daily(hist_path)
    recent, new_dates = read_daily(recent_path)
    for coord in ("lat", "lon"):
        np.testing.assert_array_equal(hist[coord], recent[coord])
    overlap = old_dates.intersection(new_dates)
    if len(overlap) < 7:
        raise ValueError("El solape de las entregas es menor que una semana")
    checks = {}
    for var, (limit_95, limit_max) in LIMITS.items():
        diff = recent[var][new_dates.get_indexer(overlap)] - hist[var][old_dates.get_indexer(overlap)]
        checks[var] = {"sesgo": float(diff.mean()), "p95_absoluto": float(np.quantile(abs(diff), .95)),
                       "maximo_absoluto": float(abs(diff).max()), "limites": [limit_95, limit_max]}
    print(f"Solape de {len(overlap)} días: {checks}", flush=True)
    if any(checks[var]["p95_absoluto"] > lim[0] or checks[var]["maximo_absoluto"] > lim[1]
           for var, lim in LIMITS.items()):
        raise ValueError("Las dos entregas de ERA5 difieren por encima de las tolerancias fijadas")
    use_recent = new_dates > old_dates[-1]
    dates = old_dates.append(new_dates[use_recent])
    if not dates.equals(pd.date_range("2000-01-02", "2026-10-31")):
        raise ValueError("La unión no cubre la serie diaria sin huecos")
    joined = {var: np.concatenate([hist[var], recent[var][use_recent]], axis=0) for var in VARIABLES}
    return pd.DataFrame({"lat": hist["lat"], "lon": hist["lon"]}), dates, joined, checks, old_dates[-1]


def aggregate(inputs):
    weights_2020 = PILOT / "insumos" / "worldpop2020.tif"
    population = {year: inputs / f"worldpop{year}.tif" for year in YEARS[:-1]}
    population[2020] = weights_2020
    hist = inputs / "era5_piura_2000_jun2026.npz"
    recent = inputs / "era5_piura_recent_2026.npz"
    points, dates, variables, overlap, last_hist = join_deliveries(hist, recent)
    districts, _, _ = pilot_geometry()
    ubigeos = sorted(districts.ubigeo)
    coords = pd.MultiIndex.from_frame(points)
    starts = dates[::7]
    refs = np.asarray(YEARS)[np.searchsorted(YEARS, starts.year, side="right") - 1]
    parts, weight_tables = [], []
    for year in YEARS:
        weights = grid_weights(districts, population[year], ERA5_GRID, ERA5_SHAPE, 2)
        weights["peso_poblacion"] = weights.personas / weights.groupby("ubigeo").personas.transform("sum")
        weights["peso_area"] = weights.area_m2 / weights.groupby("ubigeo").area_m2.transform("sum")
        weight_tables.append(weights.assign(anio_poblacion=year))
        sel = refs == year
        rows = pd.MultiIndex.from_product([starts[sel], ubigeos],
                                           names=["semana_inicio", "ubigeo"]).to_frame(index=False)
        for method, weight_field in (("poblacion", "peso_poblacion"), ("area", "peso_area")):
            matrix = weights.pivot(index="ubigeo", columns=["lat", "lon"], values=weight_field)
            matrix = matrix.reindex(index=ubigeos, columns=coords).fillna(0).to_numpy()
            np.testing.assert_allclose(matrix.sum(axis=1), 1, rtol=0, atol=1e-12)
            for variable, daily in variables.items():
                weekly = daily.reshape(-1, 7, len(points)).mean(axis=1)
                rows[f"{variable}_{method}"] = (weekly[sel] @ matrix.T).ravel()
        parts.append(rows.assign(anio_poblacion=year))
    result = pd.concat(parts, ignore_index=True)
    result["fecha_disponible_proxy"] = result.semana_inicio + 11*DAY
    result["entrega"] = np.select(
        [(result.semana_inicio + 6*DAY).le(last_hist), result.semana_inicio.gt(last_hist)],
        ["era5_earthmover", "era5_open_meteo"], default="era5_semana_empalme")
    if result.duplicated(["semana_inicio", "ubigeo"]).any() or len(result) != 91_000:
        raise ValueError("Llaves incorrectas en el panel semanal de ERA5")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUTPUT / "era5_piura_poligono_semanal.csv.gz", index=False)
    pd.concat(weight_tables, ignore_index=True).to_csv(OUTPUT / "pesos_era5_por_epoca.csv", index=False)
    write_json(OUTPUT / "manifiesto.json", {
        "metodo": "ERA5 horario en días de Perú; área o población; WorldPop por época",
        "fecha_disponible": "proxy sábado más cinco días, con disponibilidad histórica sin verificar",
        "filas": len(result), "distritos": len(ubigeos), "semanas": len(starts), "celdas": len(points),
        "solape": overlap, "ultimo_dia_historico": last_hist.date().isoformat(),
        "sha256": {p.name: sha256(p) for p in [hist, recent, *population.values()]},
    })
    print(f"{len(result)} filas distrito-semana guardadas en {OUTPUT}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("insumos", type=Path)
    aggregate(parser.parse_args().insumos)
