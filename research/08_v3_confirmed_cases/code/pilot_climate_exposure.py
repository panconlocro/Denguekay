"""Compare three ERA5-Land exposures and test CHIRTS-ERA5 on selected weeks."""

import argparse
from pathlib import Path
import time

from affine import Affine
import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import Transformer
import rasterio
from rasterio.windows import Window, from_bounds
import requests
from shapely.geometry import box
from shapely.ops import transform as project

from denguekay.config.paths import DISTRICT_BOUNDARIES, DISTRICT_COORDS, SILVER_CHIRPS_PRECIP, SILVER_METEO_ERA5_LAND_2000_2026
from denguekay.data.ingestion.chirps_ee import coverage_weights
from denguekay.data.ingestion.openmeteo import ERA5_LAND_DAILY_VARS, URL
from denguekay.data.processing.chirps_precipitation import pentad_publication
from run_experiment import OUTPUT, sha256, write_json

PILOT = OUTPUT / "piloto_clima"
DISTRICTS = {"200101": "costa", "200105": "costa", "200501": "costa",
             "200201": "sierra", "200301": "sierra", "200302": "sierra"}
LIMA_PERIODS = (("2023-03-12", "2023-04-08"), ("2023-07-09", "2023-08-05"))
CHIRTS_WEEKS = ("2023-03-12", "2026-10-18")
GRID = Affine(0.1, 0, -81.45, 0, -0.1, -3.95)
SHAPE = (28, 26)
DAY = pd.Timedelta(days=1)
EQUAL_AREA = Transformer.from_crs("EPSG:4326", "EPSG:6933", always_xy=True)
VARS = dict(zip(ERA5_LAND_DAILY_VARS, ["tmedia", "tmax", "tmin", "hr"]))


def population_on_polygon(geometry, population, transform):
    if geometry.is_empty or geometry.area == 0:
        return 0.0
    r, c, fraction = coverage_weights(geometry, transform, population.shape)
    values = population[r, c]
    return float(np.dot(values.filled(0), fraction))


def grid_weights(districts, raster, grid=GRID, shape=SHAPE, decimals=1):
    """Intersect district, ERA5 grid and WorldPop pixels without resampling counts."""
    with rasterio.open(raster) as pop:
        if pop.crs.to_epsg() != 4326:
            raise ValueError("WorldPop debe usar EPSG:4326")
        w = from_bounds(-81.50, -6.80, -78.70, -3.85, pop.transform)
        window = Window(int(w.col_off), int(w.row_off), int(w.width) + 2, int(w.height) + 2)
        data = pop.read(1, window=window, masked=True)
        if (data.compressed() < 0).any():
            raise ValueError("WorldPop contiene conteos negativos")
        transform = pop.window_transform(window)
    parts = []
    for row in districts.itertuples(index=False):
        geometry = row.geometry
        if not geometry.is_valid:
            raise ValueError(f"Polígono inválido: {row.ubigeo}")
        rr, cc, _ = coverage_weights(geometry, grid, shape)
        total = population_on_polygon(geometry, data, transform)
        for r, c in zip(rr, cc):
            left, top = grid * (c, r)
            right, bottom = grid * (c + 1, r + 1)
            intersection = geometry.intersection(box(left, bottom, right, top))
            parts.append({
                "ubigeo": row.ubigeo, "distrito": row.distrito, "lat": round((top + bottom) / 2, decimals),
                "lon": round((left + right) / 2, decimals), "area_m2": project(EQUAL_AREA.transform, intersection).area,
                "personas": population_on_polygon(intersection, data, transform),
            })
        observed = sum(p["personas"] for p in parts if p["ubigeo"] == row.ubigeo)
        if total <= 0 or not np.isclose(total, observed, rtol=1e-8, atol=1e-6):
            raise ValueError(f"Los pesos de población no reproducen el total en {row.ubigeo}")
    return pd.DataFrame(parts)


def fetch_cells(points, start, end, *, timezone="America/Lima", legacy=False, model="era5_land"):
    """Fetch batches with strict returned cell, unit and date checks."""
    points = list(points)
    days = pd.date_range(start, end)
    frames = []
    for offset in range(0, len(points), 16):
        batch = points[offset:offset + 16]
        params = {
            "latitude": ",".join(str(lat) for lat, lon in batch),
            "longitude": ",".join(str(lon) for lat, lon in batch),
            "start_date": start, "end_date": end, "daily": ",".join(VARS),
            "timezone": timezone, "models": model,
        }
        if not legacy:
            params.update(elevation=",".join(["nan"] * len(batch)), cell_selection="nearest")
        response = requests.get(URL, params=params, timeout=90)
        response.raise_for_status()
        body = response.json()
        answers = body if isinstance(body, list) else [body]
        if len(answers) != len(batch):
            raise ValueError("Número inesperado de celdas en la respuesta")
        for i, ((lat, lon), data) in enumerate(zip(batch, answers)):
            actual = (data["latitude"], data["longitude"])
            units = data["daily_units"]
            if (data.get("location_id", 0) != i or
                    data["utc_offset_seconds"] != (-18000 if timezone == "America/Lima" else 0) or
                    any(units[v] != ("%" if name == "hr" else "°C") for v, name in VARS.items())):
                raise ValueError(f"Orden, zona horaria o unidades inesperadas en {(lat, lon)}")
            if not legacy and not np.allclose(actual, (lat, lon), atol=2e-5, rtol=0):
                raise ValueError(f"La celda solicitada {(lat, lon)} fue sustituida por {actual}")
            daily = pd.DataFrame(data["daily"]).rename(columns={"time": "fecha", **VARS})
            daily["fecha"] = pd.to_datetime(daily.fecha)
            if not pd.DatetimeIndex(daily.fecha).equals(days):
                raise ValueError(f"Días inesperados en {(lat, lon)}")
            frames.append(daily.assign(lat=lat, lon=lon, lat_respuesta=actual[0], lon_respuesta=actual[1]))
        time.sleep(1.8)
    return pd.concat(frames, ignore_index=True)


def combine_weights(weather, weights, points):
    """Keep spatial support fixed across weather variables on every day."""
    vars = list(VARS.values())
    raw = weights.merge(weather, on=["lat", "lon"], validate="many_to_many")
    raw["valida"] = raw[vars].notna().all(axis=1)
    rows = []
    for (district, day), group in raw.groupby(["ubigeo", "fecha"]):
        valid = group.loc[group.valida]
        if valid.empty:
            raise ValueError(f"No hay celdas válidas para {district}, {day}")
        for label, col in (("area", "area_m2"), ("poblacion", "personas")):
            mass = valid[col].sum()
            exposure = {v: float(np.average(valid[v], weights=valid[col])) if mass > 0 else np.nan for v in vars}
            rows.append({
                "ubigeo": district, "fecha": day, "metodo": label,
                "fraccion_area_valida": valid.area_m2.sum() / group.area_m2.sum(),
                "fraccion_poblacion_valida": valid.personas.sum() / group.personas.sum(),
                **exposure,
            })
    area = pd.DataFrame(rows)
    centroid = points.merge(weather, on=["lat", "lon"], validate="many_to_many")
    return pd.concat([area, centroid.assign(metodo="centroide_01")[["ubigeo", "fecha", "metodo", *vars]]],
                     ignore_index=True)


def to_weekly(data, variables):
    if not np.isfinite(data[variables].to_numpy(dtype=float)).all():
        raise ValueError("La agregación semanal requiere datos válidos para los siete días")
    grouped = data.assign(semana_inicio=data.fecha.dt.to_period("W-SAT").dt.start_time).groupby(
        ["ubigeo", "metodo", "semana_inicio"], as_index=False)
    weekly = grouped[variables].mean()
    if not grouped.fecha.size()["size"].eq(7).all():
        raise ValueError("Hay una semana que no contiene exactamente siete días")
    return weekly


def chirps_audit():
    rain = pd.read_csv(SILVER_CHIRPS_PRECIP, dtype={"ubigeo": str},
                       parse_dates=["semana_inicio", "fecha_disponible"])
    keys = ["ubigeo", "semana_inicio"]
    if (rain.duplicated(keys).any() or not rain.precip_total_mm.ge(0).all()
            or not rain.groupby("semana_inicio").ubigeo.nunique().eq(65).all()):
        raise ValueError("Llaves o datos de CHIRPS inválidos")
    close = rain.semana_inicio + 6 * DAY
    if not rain.fecha_disponible.eq(pentad_publication(close)).all():
        raise ValueError("La fecha CHIRPS difiere del proxy de publicación")
    lag = (rain.fecha_disponible - close).dt.days
    cuts = pd.read_csv(OUTPUT / "revision_protocolo" / "cortes.csv",
                       parse_dates=["primer_origen", "ultimo_origen"])
    closes = pd.date_range(cuts.primer_origen.min(), cuts.ultimo_origen.max(), freq="W-SAT")
    distinct = rain.drop_duplicates("semana_inicio").sort_values("semana_inicio")
    for date, group in rain.groupby("semana_inicio"):
        if group.fecha_disponible.nunique() != 1:
            raise ValueError(f"Fechas de publicación distintas por distrito en {date}")
    published = distinct.set_index(close.loc[distinct.index]).fecha_disponible
    counts = {}
    for weeks in (0, 1, 2):
        series = published.reindex(closes - pd.Timedelta(weeks=weeks))
        if series.isna().any():
            raise ValueError("Faltan fechas de lluvia para auditar los cortes")
        counts[str(weeks)] = int((series.to_numpy() > closes.to_numpy()).sum())
    return {"filas": len(rain), "versiones": rain.version.value_counts().to_dict(),
            "dias_proxy_minimo": int(lag.min()), "dias_proxy_maximo": int(lag.max()),
            "fecha_es_proxy_preliminar": True, "origenes_semanales": len(closes),
            "origenes_posteriores_al_corte_por_rezago_semanal": counts}


def chirts_weekly(folder, districts):
    dates = [d for start in CHIRTS_WEEKS for d in pd.date_range(start, periods=7)]
    rows = []
    checksums = {}
    for kind in ("max", "min"):
        for date in dates:
            path = folder / f"CHIRTS-ERA5.daily_T{kind}.{date:%Y.%m.%d}.tif"
            checksums[path.name] = sha256(path)
            with rasterio.open(path) as ds:
                values = ds.read(1, masked=True)
                valid = ~np.ma.getmaskarray(values) & np.isfinite(values.data) & (values.data != -9999)
                for district in districts.itertuples(index=False):
                    r, c, _ = coverage_weights(district.geometry, ds.transform, values.shape)
                    area = []
                    for y, x in zip(r, c):
                        left, top = ds.transform * (x, y)
                        right, bottom = ds.transform * (x + 1, y + 1)
                        intersection = district.geometry.intersection(box(left, bottom, right, top))
                        area.append(project(EQUAL_AREA.transform, intersection).area)
                    weights = np.asarray(area)
                    keep = valid[r, c]
                    rows.append({
                        "ubigeo": district.ubigeo, "fecha": date, "metodo": "chirts_area",
                        "variable": f"t{kind}", "cobertura": float(weights[keep].sum() / weights.sum()),
                        "temperatura": float(np.average(values.data[r[keep], c[keep]], weights=weights[keep]))
                        if keep.any() else np.nan,
                    })
    daily = pd.DataFrame(rows)
    paired = daily.pivot(index=["ubigeo", "fecha", "metodo"], columns="variable", values="temperatura").reset_index()
    if paired[["tmax", "tmin"]].isna().any().any() or not paired.tmax.ge(paired.tmin).all():
        raise ValueError("CHIRTS no tiene Tmin/Tmax válidas en todo el piloto")
    return to_weekly(paired, ["tmax", "tmin"]), daily, checksums


def pilot_geometry():
    districts = gpd.read_file(DISTRICT_BOUNDARIES)
    districts["ubigeo"] = districts.ubigeo.astype(str)
    geo = districts.loc[districts.ubigeo.isin(DISTRICTS)]
    points = pd.read_csv(DISTRICT_COORDS).merge(geo[["ubigeo", "distrito", "provincia"]],
                                               on=["distrito", "provincia"], validate="one_to_one")
    if len(districts) != 65 or len(points) != len(DISTRICTS):
        raise ValueError("Catálogo y polígonos del piloto inconsistentes")
    return districts, geo, points


def audit_regional_support(weights):
    """Check coastal mask and population support on one complete pilot week."""
    week = LIMA_PERIODS[0][0]
    end = (pd.Timestamp(week) + 6 * DAY).date().isoformat()
    cells = weights[["lat", "lon"]].drop_duplicates()
    weather = fetch_cells(cells.itertuples(index=False, name=None), week, end)
    weather["valida"] = weather[list(VARS.values())].notna().all(axis=1)
    if not weather.groupby(["lat", "lon"]).valida.nunique().eq(1).all():
        raise ValueError("La máscara de ERA5-Land cambia dentro de la semana")
    mask = weather[["lat", "lon", "valida"]].drop_duplicates()
    regional = weights.merge(mask, on=["lat", "lon"], validate="many_to_one")
    regional = regional.assign(area_valida=lambda d: d.area_m2 * d.valida,
                               poblacion_valida=lambda d: d.personas * d.valida)
    report = regional.groupby(["ubigeo", "distrito"], as_index=False).agg(
        celdas=("lat", "size"), celdas_validas=("valida", "sum"),
        area=("area_m2", "sum"), area_valida=("area_valida", "sum"),
        poblacion=("personas", "sum"), poblacion_valida=("poblacion_valida", "sum"),
    )
    report["fraccion_area_valida"] = report.area_valida / report.area
    report["fraccion_poblacion_valida"] = report.poblacion_valida / report.poblacion
    report.to_csv(PILOT / "cobertura_regional_era5.csv", index=False)
    print(f"Máscara regional verificada en {len(mask)} celdas para la semana {week}", flush=True)


def chirts_comparison(folder, geo, points, weights):
    pilot = weights.loc[weights.ubigeo.isin(DISTRICTS)]
    snapped = points[["ubigeo", "lat", "lon"]].assign(lat=lambda d: d.lat.round(1), lon=lambda d: d.lon.round(1))
    cells = pd.concat([pilot[["lat", "lon"]], snapped[["lat", "lon"]]]).drop_duplicates()
    candidate = list(cells.itertuples(index=False, name=None))
    chirts, support, hashes = chirts_weekly(folder, geo)
    utc = []
    for start in CHIRTS_WEEKS:
        end = (pd.Timestamp(start) + 6 * DAY).date().isoformat()
        utc.append(combine_weights(fetch_cells(candidate, start, end, timezone="GMT"), pilot, snapped))
    matched = pd.concat([chirts, to_weekly(pd.concat(utc), ["tmax", "tmin"])], ignore_index=True)
    matched.to_csv(PILOT / "chirts_era5_semanal_utc.csv", index=False)
    support.to_csv(PILOT / "chirts_cobertura_diaria.csv", index=False)
    print("Piloto CHIRTS-ERA5 en dos semanas UTC guardado", flush=True)
    return {"semanas": CHIRTS_WEEKS, "sha256_ventanas": hashes}


def main():
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("--worldpop", type=Path)
    parser.add_argument("--chirts", type=Path)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--solo-cobertura-regional", action="store_true")
    modes.add_argument("--solo-chirts", action="store_true")
    args = parser.parse_args()
    PILOT.mkdir(parents=True, exist_ok=True)
    districts, geo, points = pilot_geometry()
    manifest_path = PILOT / "manifiesto.json"
    if args.solo_cobertura_regional or args.solo_chirts:
        manifest = json.loads(manifest_path.read_text())
        weights = pd.read_csv(PILOT / "pesos_65_distritos.csv", dtype={"ubigeo": str})
        if args.solo_cobertura_regional:
            audit_regional_support(weights)
            manifest["cobertura_regional_semana"] = LIMA_PERIODS[0][0]
        else:
            if args.chirts is None:
                parser.error("--solo-chirts requiere --chirts")
            manifest["chirts"] = chirts_comparison(args.chirts, geo, points, weights)
        manifest["chirps"] = chirps_audit()
        write_json(manifest_path, manifest)
        return
    if args.worldpop is None:
        parser.error("El piloto de exposición requiere --worldpop")
    weights = grid_weights(districts, args.worldpop)
    weights.to_csv(PILOT / "pesos_65_distritos.csv", index=False)
    print(f"Pesos verificados para los 65 distritos: {len(weights)} intersecciones", flush=True)
    pilot = weights.loc[weights.ubigeo.isin(DISTRICTS)]
    snapped = points[["ubigeo", "lat", "lon"]].assign(lat=lambda d: d.lat.round(1), lon=lambda d: d.lon.round(1))
    cells = pd.concat([pilot[["lat", "lon"]], snapped[["lat", "lon"]]]).drop_duplicates()
    candidate = list(cells.itertuples(index=False, name=None))
    original = list(points[["lat", "lon"]].itertuples(index=False, name=None))
    print(f"Consultando {len(candidate)} celdas ERA5-Land para seis distritos", flush=True)
    records = []
    for start, end in LIMA_PERIODS:
        weather = fetch_cells(candidate, start, end)
        ctrl = fetch_cells(original, start, end, legacy=True)
        legacy = points[["ubigeo", "lat", "lon"]].merge(ctrl, on=["lat", "lon"], validate="one_to_many")
        records.append(pd.concat([combine_weights(weather, pilot, snapped),
                                  legacy.assign(metodo="punto_original")], ignore_index=True))
    daily = pd.concat(records, ignore_index=True).assign(dtr=lambda d: d.tmax - d.tmin)
    daily.to_csv(PILOT / "era5_diario.csv.gz", index=False)
    weekly = to_weekly(daily, ["tmedia", "tmax", "tmin", "hr", "dtr"])
    weekly["zona"] = weekly.ubigeo.map(DISTRICTS)
    weekly.to_csv(PILOT / "era5_semanal.csv", index=False)
    frozen = pd.read_csv(SILVER_METEO_ERA5_LAND_2000_2026, parse_dates=["semana_inicio"])
    check = weekly[weekly.metodo.eq("punto_original")].merge(points[["ubigeo", "id_distrito"]], on="ubigeo").merge(
        frozen[["id_distrito", "semana_inicio", "temp_media", "hum_rel_media"]], on=["id_distrito", "semana_inicio"],
        validate="one_to_one")
    if len(check) != len(DISTRICTS) * 8:
        raise ValueError("Faltan semanas del control contra el silver archivado")
    check = check.assign(delta_temp=lambda d: d.tmedia - d.temp_media, delta_hr=lambda d: d.hr - d.hum_rel_media)
    check.to_csv(PILOT / "control_silver_original.csv", index=False)
    manifest = {
        "clima": "ERA5-Land via Open-Meteo", "worldpop": "2020 UN adjusted, 30 arc-seconds",
        "url_worldpop": "https://data.worldpop.org/GIS/Population/Global_2000_2020_1km_UNadj/2020/PER/per_ppp_2020_1km_Aggregated_UNadj.tif",
        "sha256_worldpop": sha256(args.worldpop), "sha256_limites": sha256(DISTRICT_BOUNDARIES),
        "sha256_coords": sha256(DISTRICT_COORDS), "periodos_locales": LIMA_PERIODS,
        "distritos": DISTRICTS, "celdas_era5_piloto": len(cells),
        "celdas_era5_region": len(weights[["lat", "lon"]].drop_duplicates()), "chirps": chirps_audit(),
    }
    write_json(PILOT / "manifiesto.json", manifest)
    print("Piloto ERA5-Land y auditoría CHIRPS guardados", flush=True)
    if args.chirts:
        manifest["chirts"] = chirts_comparison(args.chirts, geo, points, weights)
        write_json(manifest_path, manifest)


if __name__ == "__main__":
    main()
