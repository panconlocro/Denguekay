"""Read the public ERA5 archive for the grid cells intersecting Piura."""

import argparse
from pathlib import Path

import icechunk
import numpy as np
import pandas as pd
import xarray as xr

START = "2000-01-02T05:00"
LAST_HOUR = "2026-06-30T04:00"


def extract(points, start=START, last=LAST_HOUR):
    storage = icechunk.s3_storage(bucket="earthmover-icechunk-era5", prefix="icechunkV2",
                                  region="us-east-1", anonymous=True)
    repository = icechunk.Repository.open(storage)
    session = repository.readonly_session("main")
    archive = xr.open_zarr(session.store, group="single/temporal", chunks=None, consolidated=False)
    longitude = points.lon.to_numpy() % 360
    latitude = points.lat.to_numpy()
    box = archive[["t2m", "d2m"]].sel(valid_time=slice(start, last),
                                       latitude=slice(latitude.max(), latitude.min()),
                                       longitude=slice(longitude.min(), longitude.max()))
    print(f"Leyendo {box.sizes['valid_time']} horas de ERA5 en la ventana de Piura", flush=True)
    box.load()
    timestamps = pd.DatetimeIndex(box.valid_time.values)
    if not timestamps.equals(pd.date_range(start, last, freq="h")) or len(timestamps) % 24:
        raise ValueError("El archivo no cubre todos los días completos solicitados")
    y = pd.Index(box.latitude.values).get_indexer(latitude)
    x = pd.Index(box.longitude.values).get_indexer(longitude)
    if (y < 0).any() or (x < 0).any():
        raise ValueError("Las coordenadas no coinciden con la grilla ERA5")
    temperature = box.t2m.transpose("valid_time", "latitude", "longitude").values[:, y, x] - np.float32(273.15)
    dewpoint = box.d2m.transpose("valid_time", "latitude", "longitude").values[:, y, x] - np.float32(273.15)
    if not np.isfinite(temperature).all() or not np.isfinite(dewpoint).all():
        raise ValueError("La serie de ERA5 tiene celdas sin datos")
    if np.max(dewpoint - temperature) > 0.5:
        raise ValueError("El punto de rocío excede de forma sustancial la temperatura")
    humidity = np.exp(17.67 * (dewpoint / (dewpoint + 243.5) - temperature / (temperature + 243.5)))
    humidity = 100 * np.minimum(humidity, 1)
    shape = (-1, 24, len(points))
    daily_t = temperature.reshape(shape)
    daily_rh = humidity.reshape(shape)
    return {
        "fecha": ((timestamps[::24] - pd.Timedelta(hours=5)).normalize()).to_numpy(),
        "lat": latitude, "lon": points.lon.to_numpy(),
        "tmedia": daily_t.mean(axis=1), "tmax": daily_t.max(axis=1), "tmin": daily_t.min(axis=1),
        "hr": daily_rh.mean(axis=1),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pesos", type=Path)
    parser.add_argument("salida", type=Path)
    args = parser.parse_args()
    points = pd.read_csv(args.pesos, usecols=["lat", "lon"]).drop_duplicates().reset_index(drop=True)
    result = extract(points)
    np.savez_compressed(args.salida, **result)
    print(f"{len(result['fecha'])} días completos y {len(points)} celdas guardados", flush=True)


if __name__ == "__main__":
    main()
