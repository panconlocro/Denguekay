"""Audit regional climate coverage and evaluate a separate temperature fill."""

import argparse
from pathlib import Path

from affine import Affine
import numpy as np
import pandas as pd
import rasterio

from pilot_climate_exposure import (
    CHIRTS_WEEKS, DAY, PILOT, VARS, fetch_cells, grid_weights, pilot_geometry, sha256, write_json,
)

OUTPUT = PILOT / "fuentes_costa"
CORE_WEEK = CHIRTS_WEEKS[0]
PISCO_WEEK = "2020-03-15"
ERA5_GRID = Affine(.25, 0, -81.625, 0, -.25, -3.875)
ERA5_SHAPE = (12, 13)
VALUES = list(VARS.values())
STATIONS = {"Piura": "84401099999", "Talara": "84390099999"}


def cell_keys(weights):
    return weights[["lat", "lon"]].drop_duplicates()


def daily_grid(model, weights, folder):
    path = folder / f"{model}_regional_{CORE_WEEK.replace('-', '')}.csv"
    weather = pd.read_csv(path, parse_dates=["fecha"]) if path.exists() else None
    coords = cell_keys(weights)
    need = coords if weather is None else coords.merge(cell_keys(weather), how="left", indicator=True).loc[
        lambda d: d._merge.eq("left_only"), ["lat", "lon"]]
    if not need.empty:
        end = (pd.Timestamp(CORE_WEEK) + 6 * DAY).date().isoformat()
        fetched = fetch_cells(need.itertuples(index=False, name=None), CORE_WEEK, end, timezone="GMT", model=model)
        weather = pd.concat([weather, fetched], ignore_index=True)
        weather.to_csv(path, index=False)
    weather = weather.merge(coords, on=["lat", "lon"], validate="many_to_one")
    days = pd.date_range(CORE_WEEK, periods=7)
    sizes = weather.groupby(["lat", "lon"]).fecha.agg(lambda dates: tuple(sorted(dates)))
    if len(sizes) != len(coords) or not sizes.map(lambda dates: dates == tuple(days)).all():
        raise ValueError(f"Panel diario incompleto en {model}")
    return weather


def mask_audit(land, mask_path):
    cells = land.groupby(["lat", "lon"], as_index=False)[VALUES].agg(lambda s: s.notna().all())
    if len(cells) != len(land) // 7:
        raise ValueError("La muestra de ERA5-Land requiere siete días por celda")
    xy = list(zip(cells.lon, cells.lat))
    with rasterio.open(mask_path) as src:
        for lon, lat in xy:
            row, col = src.index(lon, lat)
            if not np.allclose(src.xy(row, col), (lon, lat), atol=1e-6, rtol=0):
                raise ValueError("La máscara oficial usa otra grilla")
        cells["fraccion_tierra_cds"] = [float(value[0]) for value in src.sample(xy)]
    if not cells.fraccion_tierra_cds.between(0, 1).all():
        raise ValueError("Máscara fuera de [0,1]")
    cells["completa"] = cells[VALUES].all(axis=1)
    return cells


def summarize(weather, weights, columns, source):
    merged = weights.merge(weather, on=["lat", "lon"], validate="many_to_many")
    if len(merged) != len(weights) * weather.fecha.nunique():
        raise ValueError(f"Celdas sin fila de {source}")
    rows = []
    for (district, date), g in merged.groupby(["ubigeo", "fecha"]):
        for field in columns:
            ok = g[field].notna()
            persons = g.loc[ok, "personas"].sum()
            rows.append({
                "fuente": source, "ubigeo": district, "fecha": date, "variable": field,
                "fraccion_poblacion": persons / g.personas.sum(),
                "fraccion_area": g.loc[ok, "area_m2"].sum() / g.area_m2.sum(),
                "media_poblacion": np.average(g.loc[ok, field], weights=g.loc[ok, "personas"]) if persons else np.nan,
            })
    return pd.DataFrame(rows)


def chirts_grid(districts, pop, folder):
    files = [(f"t{kind}", date, folder / f"CHIRTS-ERA5.daily_T{kind}.{date:%Y.%m.%d}.tif")
             for start in CHIRTS_WEEKS for date in pd.date_range(start, periods=7) for kind in ("max", "min")]
    with rasterio.open(files[0][2]) as first:
        transform, shape = first.transform, first.shape
    weights = grid_weights(districts, pop, transform, shape, 5)
    cells = weights[["lat", "lon"]].drop_duplicates()
    rows = []
    for field, day, path in files:
        with rasterio.open(path) as src:
            if src.transform != transform or src.shape != shape:
                raise ValueError(f"Grilla CHIRTS distinta en {path.name}")
            values = [float(v[0]) for v in src.sample(zip(cells.lon, cells.lat))]
        rows.append(cells.assign(variable=field, fecha=day, valor=np.where(np.array(values) == -9999, np.nan, values)))
    data = pd.concat(rows).pivot(index=["lat", "lon", "fecha"], columns="variable", values="valor").reset_index()
    return data, weights


def temperature_fill(land, era5):
    # Explicitly compare a raw fill at the closest ERA5 cell to the original ERA5-Land value.
    mapped = land.assign(lat_era5=lambda d: (4 * d.lat).round() / 4, lon_era5=lambda d: (4 * d.lon).round() / 4)
    replacement = era5[["lat", "lon", "fecha", "tmedia"]].rename(
        columns={"lat": "lat_era5", "lon": "lon_era5", "tmedia": "tmedia_era5"})
    both = mapped.merge(replacement, on=["lat_era5", "lon_era5", "fecha"], how="left", validate="many_to_one")
    if both.loc[both.tmedia.isna(), "tmedia_era5"].isna().any():
        raise ValueError("El relleno piloto requiere la celda ERA5 correspondiente")
    return both.assign(tmedia=lambda d: d.tmedia.fillna(d.tmedia_era5))


def station_audit(folder, products, start=CORE_WEEK, suffix=""):
    observations = []
    fields = {"MAX": "tmax", "MIN": "tmin", "TEMP": "tmedia"}
    for name in STATIONS:
        path = folder / f"{name} NOAA{suffix}"
        noaa = pd.read_csv(path, parse_dates=["DATE"])
        noaa = noaa[noaa.DATE.between(start, pd.Timestamp(start) + 6 * DAY)].copy()
        if len(noaa) != 7 or noaa.DATE.duplicated().any():
            raise ValueError(f"Faltan fechas de estación {name}")
        lat, lon = noaa[["LATITUDE", "LONGITUDE"]].iloc[0]
        for source, product in products.items():
            xy = product[["lat", "lon"]].drop_duplicates()
            i = ((xy.lat-lat)**2 + (xy.lon-lon)**2).idxmin()
            x, y = xy.loc[i, ["lat", "lon"]]
            hit = product.loc[product.lat.eq(x) & product.lon.eq(y)]
            same = noaa.merge(hit, left_on="DATE", right_on="fecha", validate="one_to_one")
            for col, field in fields.items():
                if field not in same:
                    continue
                valid = same[col].between(-30, 140) & same[field].notna()
                for row in same.loc[valid].itertuples(index=False):
                    observations.append({
                        "estacion": name, "fecha": row.fecha, "fuente": source, "variable": field,
                        "lat_estacion": lat, "lon_estacion": lon, "lat_celda": x, "lon_celda": y,
                        "observado_c": (getattr(row, col) - 32) * 5 / 9, "estimado_c": getattr(row, field),
                    })
    return pd.DataFrame(observations).assign(error=lambda d: d.estimado_c-d.observado_c)


def pisco_comparison(folder, districts, population):
    frames, coords = [], None
    for field in ("tmax", "tmin"):
        with np.load(folder / f"pisco_{field}.npz") as archive:
            lat, lon, dates = archive["latitude"], archive["longitude"], archive["dates"]
            dates = pd.to_datetime(dates)
            if not dates.equals(pd.date_range(PISCO_WEEK, periods=7)):
                raise ValueError("Fechas inesperadas de PISCOt")
            if not np.allclose(np.diff(lat), -.01) or not np.allclose(np.diff(lon), .01):
                raise ValueError("Grilla inesperada de PISCOt")
            if coords is None:
                coords = (lat, lon)
            else:
                np.testing.assert_array_equal(coords[0], lat)
                np.testing.assert_array_equal(coords[1], lon)
            transform = Affine(.01, 0, lon[0]-.005, 0, -.01, lat[0]+.005)
            if not frames:
                weights = grid_weights(districts, population, transform, (len(lat), len(lon)), 2)
                cells = cell_keys(weights)
            r = np.rint((lat[0] - cells.lat.to_numpy())/.01).astype(int)
            c = np.rint((cells.lon.to_numpy() - lon[0])/.01).astype(int)
            frames.append(pd.concat([cells.assign(fecha=day, **{field: array[r,c]})
                                     for day, array in zip(dates, archive["values"])], ignore_index=True))
    pisco = frames[0].merge(frames[1], on=["lat", "lon", "fecha"], validate="one_to_one")
    inverted = pisco.tmax.lt(pisco.tmin)
    pisco.loc[inverted].to_csv(OUTPUT / "piscot_extremos_invertidos.csv", index=False)
    pisco.loc[inverted, ["tmax", "tmin"]] = np.nan
    summarize(pisco, weights, ["tmax", "tmin"], "piscot").to_csv(OUTPUT / "cobertura_piscot_2020.csv", index=False)
    records = [pd.read_csv(folder / f"{name} NOAA 2020", nrows=1)[["LATITUDE", "LONGITUDE"]] for name in STATIONS]
    xy = pd.concat(records, ignore_index=True).to_numpy()
    products = {"piscot": pisco}
    end = (pd.Timestamp(PISCO_WEEK) + 6 * DAY).date().isoformat()
    for model, step in (("era5", .25), ("era5_land", .1)):
        nearest = np.round(np.rint(xy/step)*step, 2)
        daily = fetch_cells([tuple(row) for row in nearest], PISCO_WEEK, end, timezone="GMT", model=model)
        products[model] = daily
    stations = station_audit(folder, products, PISCO_WEEK, " 2020")
    stations.to_csv(OUTPUT / "estaciones_noaa_2020.csv", index=False)
    print(f"PISCOt 2020 verificado sobre {len(cells)} celdas en Piura", flush=True)
    return {"semana": PISCO_WEEK, "celdas": len(cells), "extremos_invertidos": int(inverted.sum()), "sha256": {
        f"pisco_{field}.npz": sha256(folder / f"pisco_{field}.npz") for field in ("tmax", "tmin")}}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("insumos", type=Path)
    parser.add_argument("--pisco", action="store_true")
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    districts, _, _ = pilot_geometry()
    pop = PILOT / "insumos" / "worldpop2020.tif"
    wp = pd.read_csv(PILOT / "pesos_65_distritos.csv", dtype={"ubigeo": str})
    wg = grid_weights(districts, pop, ERA5_GRID, ERA5_SHAPE, 2)
    land = daily_grid("era5_land", wp, args.insumos)
    fill_cells = land.loc[land.tmedia.isna(), ["lat", "lon"]].assign(
        lat=lambda d: (4 * d.lat).round() / 4, lon=lambda d: (4 * d.lon).round() / 4)
    era5 = daily_grid("era5", pd.concat([wg[["lat", "lon"]], fill_cells], ignore_index=True), args.insumos)
    mask_path = args.insumos / "era5_land_mask.grb"
    mask = mask_audit(land, mask_path)
    chirts, fine_weights = chirts_grid(districts, pop, PILOT / "insumos" / "chirts")
    print(f"Grillas verificadas: ERA5-Land {len(mask)} celdas, ERA5 {len(cell_keys(wg))} celdas, CHIRTS {len(cell_keys(fine_weights))} celdas", flush=True)
    data = pd.concat([
        summarize(land, wp, VALUES, "era5_land"),
        summarize(era5, wg, VALUES, "era5"),
        summarize(chirts, fine_weights, ["tmin", "tmax"], "chirts"),
        summarize(temperature_fill(land, era5), wp, ["tmedia"], "relleno_exploratorio"),
    ], ignore_index=True)
    mask.to_csv(OUTPUT / "mascara_cds_vs_open_meteo.csv", index=False)
    data.to_csv(OUTPUT / "cobertura_y_temperatura_diaria.csv.gz", index=False)
    stations = station_audit(args.insumos, {"era5": era5, "era5_land": land, "chirts": chirts})
    stations.to_csv(OUTPUT / "estaciones_noaa_2023.csv", index=False)
    pisco = pisco_comparison(args.insumos, districts, pop) if args.pisco else None
    write_json(OUTPUT / "manifiesto.json", {
        "semana_comun": CORE_WEEK, "semana_reciente_chirts": CHIRTS_WEEKS[1],
        "sha256_mascara": sha256(mask_path), "sha256_worldpop": sha256(pop),
        "sha256_insumos": {f.name: sha256(f) for f in args.insumos.iterdir()
                           if f.name.endswith("regional_20230312.csv") or f.name.endswith("NOAA")},
        "celdas_sin_cobertura_era5_land": int((~mask.completa).sum()),
        "celdas_sin_cobertura_era5_land_por_variable": {col: int((~mask[col]).sum()) for col in VALUES},
        "estaciones": STATIONS, "pisco": pisco,
    })
    print(f"Comparación guardada en {OUTPUT}", flush=True)


if __name__ == "__main__":
    main()
