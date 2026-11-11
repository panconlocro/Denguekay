"""Prepare destination geography and archived daily weather for the northern transfer."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from time import sleep

import geopandas as gpd
import numpy as np
import pandas as pd
import requests

from audit_northern_transfer_inputs import DEPARTMENTS
from denguekay.data.ingestion import chirps_ee, openmeteo
from denguekay.data.ingestion.chirps_prelim import FtpSource
from denguekay.data.ingestion.district_boundaries import ADM3_LAYER, compact_key, pcode_to_ubigeo
from denguekay.features.long_history import week_grid

FIELDS = ["temperature_2m_mean", "relative_humidity_2m_mean"]


def climate_days(year: int) -> pd.DatetimeIndex:
    weeks = week_grid(year, year).semana_inicio
    first = weeks.iloc[0] - pd.Timedelta(weeks=11)
    last = weeks.iloc[37] - pd.Timedelta(days=8)
    return pd.date_range(first, last)


def districts_and_points(cod_ab: Path, gadm: Path) -> tuple[gpd.GeoDataFrame, pd.DataFrame]:
    boundaries = gpd.read_file(f"zip://{cod_ab.resolve()}!{ADM3_LAYER}").to_crs(4326)
    districts = boundaries.loc[boundaries.adm1_pcode.isin(f"PE{v}" for v in DEPARTMENTS.values())].copy()
    districts["ubigeo"] = pcode_to_ubigeo(districts.adm3_pcode)
    if districts.ubigeo.duplicated().any() or len(districts) != 51:
        raise ValueError("Incomplete or duplicate destination boundaries")
    gadm_areas = gpd.read_file(f"zip://{gadm.resolve()}").query("NAME_1 in ['Lambayeque', 'Tumbes']").copy()
    for table, fields in (
        (districts, ("adm1_name", "adm2_name", "adm3_name")),
        (gadm_areas, ("NAME_1", "NAME_2", "NAME_3")),
    ):
        table["match"] = list(zip(*(table[field].map(compact_key) for field in fields)))
    gadm_points = gadm_areas.to_crs(32717).centroid.to_crs(4326)
    cod_points = districts.to_crs(32717).centroid.to_crs(4326)
    coords = pd.DataFrame({"match": gadm_areas.match, "lat": gadm_points.y, "lon": gadm_points.x})
    if not set(coords.match).issubset(set(districts.match)):
        raise ValueError("GADM districts do not reconcile to COD-AB")
    joined = districts[["ubigeo", "match"]].assign(cod_lat=cod_points.y, cod_lon=cod_points.x)
    joined = joined.merge(coords, on="match", how="left", validate="one_to_one")
    joined["fuente_centroide"] = np.where(joined.lat.isna(), "COD-AB", "GADM")
    joined["lat"] = joined.lat.fillna(joined.cod_lat)
    joined["lon"] = joined.lon.fillna(joined.cod_lon)
    return districts.sort_values("ubigeo"), joined[["ubigeo", "lat", "lon", "fuente_centroide"]].sort_values("ubigeo")


def download_era(points: pd.DataFrame, folder: Path, days: pd.DatetimeIndex) -> None:
    def coordinates(frame: pd.DataFrame) -> dict:
        return {"latitude": ",".join(map(str, frame.lat)), "longitude": ",".join(map(str, frame.lon))}

    elevation_url = "https://api.open-meteo.com/v1/elevation"
    response = requests.get(elevation_url, params=coordinates(points), timeout=60)
    response.raise_for_status()
    elevation = np.asarray(response.json()["elevation"], dtype=float)
    if len(elevation) != len(points) or not np.isfinite(elevation).all():
        raise ValueError("Incomplete Open-Meteo elevation results")
    geo = points.assign(elevacion_dem90=elevation)
    geo.to_csv(folder / "geografia.csv", index=False)
    chunks = []
    for start in range(0, len(points), 8):
        batch = points.iloc[start:start + 8]
        params = {**coordinates(batch), "start_date": str(days[0].date()),
                  "end_date": str(days[-1].date()), "timezone": "America/Lima",
                  "models": "era5_land", "daily": ",".join(FIELDS)}
        response = requests.get(openmeteo.URL, params=params, timeout=90)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            data = [data]
        if len(data) != len(batch):
            raise ValueError("Incomplete Open-Meteo coordinate batch")
        for district, series in zip(batch.ubigeo, data, strict=True):
            daily = pd.DataFrame(series["daily"]).assign(ubigeo=district)
            if not pd.DatetimeIndex(daily.time).equals(days) or daily[FIELDS].isna().any().any():
                raise ValueError(f"Incomplete ERA5-Land coverage for {district}")
            chunks.append(daily)
        print(f"ERA5-Land {min(start + 8, len(points))}/{len(points)}", flush=True)
    pd.concat(chunks, ignore_index=True).to_csv(folder / "era5_land_diario.csv", index=False)


def download_rain(districts: gpd.GeoDataFrame, folder: Path, days: pd.DatetimeIndex) -> None:
    cache = folder / "chirps_diario"
    cache.mkdir(exist_ok=True)
    bounds = tuple(districts.total_bounds + np.array([-.10, -.10, .10, .10]))
    pending = [day for day in days if not (cache / f"{day:%Y-%m-%d}.npz").exists()]

    def fetch_batch(days):
        import rasterio
        from rasterio.windows import from_bounds

        with TemporaryDirectory(dir=folder) as scratch, FtpSource(timeout=35) as source:
            for day in days:
                item = source.fetch(day.date(), "final", Path(scratch))
                raster = Path(item["ruta_temporal"])
                with rasterio.open(raster) as dataset:
                    window = from_bounds(*bounds, transform=dataset.transform).round_offsets().round_lengths()
                    data = dataset.read(1, window=window)
                    transform = dataset.window_transform(window)
                raster.unlink()
                target = cache / f"{day:%Y-%m-%d}.npz"
                temp = target.with_suffix(".part.npz")
                np.savez_compressed(temp, data=data, transform=tuple(transform)[:6], sha256=item["sha256"])
                temp.replace(target)
                sleep(1)

    for start in range(0, len(pending), 36):
        batch = pending[start:start + 36]
        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(fetch_batch, (batch[i::3] for i in range(min(3, len(batch))))))
        print(f"CHIRPS {len(days) - len(pending) + start + len(batch)}/{len(days)}", flush=True)
    from affine import Affine

    windows = {}
    transform = None
    for day in days:
        with np.load(cache / f"{day:%Y-%m-%d}.npz") as raster:
            current_transform = Affine(*raster["transform"])
            if transform is not None and transform != current_transform:
                raise ValueError(f"CHIRPS grid changed on {day.date()}")
            transform = current_transform
            windows[day.date()] = raster["data"]
    daily = chirps_ee.local_district_means(windows, transform, districts)
    if daily.precip_mm.isna().any() or daily.precip_mm.lt(0).any():
        raise ValueError("Missing or negative CHIRPS precipitation")
    daily.to_csv(folder / "chirps_diario.csv", index=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cod-ab", type=Path, required=True)
    parser.add_argument("--gadm", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", choices=("era5", "chirps"), required=True)
    parser.add_argument("--year", type=int, choices=(2025, 2026), default=2025)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    districts, points = districts_and_points(args.cod_ab, args.gadm)
    days = climate_days(args.year)
    if args.source == "era5":
        download_era(points, args.output, days)
    else:
        download_rain(districts, args.output, days)


if __name__ == "__main__":
    main()
