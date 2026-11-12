"""Get recent ERA5 cells and compare the overlap with the public AWS archive."""

import argparse
from pathlib import Path
import time

import numpy as np
import pandas as pd
import requests

from denguekay.data.ingestion.openmeteo import URL

START = "2026-06-22"
END = "2026-11-01"
FIELDS = ("temperature_2m", "dew_point_2m")


def daily_from_hourly(hourly):
    temp = hourly[FIELDS[0]].to_numpy(dtype=float).reshape(-1, 24)
    dew = hourly[FIELDS[1]].to_numpy(dtype=float).reshape(-1, 24)
    if not np.isfinite(temp).all() or not np.isfinite(dew).all() or np.max(dew-temp) > .5:
        raise ValueError("Serie horaria inválida")
    rh = np.exp(17.67 * (dew / (dew + 243.5) - temp / (temp + 243.5)))
    return np.column_stack([temp.mean(axis=1), temp.max(axis=1), temp.min(axis=1),
                            100*np.minimum(rh, 1).mean(axis=1)])


def fetch(points):
    start = pd.Timestamp(START) + pd.Timedelta(hours=5)
    end = pd.Timestamp(END) + pd.Timedelta(hours=4)
    hours = pd.date_range(start, end, freq="h")
    arrays = []
    with requests.Session() as session:
        for offset in range(0, len(points), 8):
            part = points.iloc[offset:offset+8]
            options = {
                "latitude": ",".join(part.lat.astype(str)), "longitude": ",".join(part.lon.astype(str)),
                "models": "era5", "cell_selection": "nearest", "elevation": ",".join(["nan"]*len(part)),
                "hourly": ",".join(FIELDS), "start_date": START, "end_date": END, "timezone": "GMT",
            }
            r = session.get(URL, params=options, timeout=90)
            r.raise_for_status()
            body = r.json()
            if len(body) != len(part):
                raise ValueError("Número de celdas ERA5 inesperado")
            for i, ((lat, lon), item) in enumerate(zip(part.itertuples(index=False, name=None), body)):
                if (item.get("location_id", 0) != i or item["utc_offset_seconds"] != 0 or
                        not np.allclose((item["latitude"], item["longitude"]), (lat, lon), atol=2e-5, rtol=0)):
                    raise ValueError("Celda devuelta distinta de la requerida")
                if any(item["hourly_units"][field] != "°C" for field in FIELDS):
                    raise ValueError("Unidades ERA5 inesperadas")
                daily = pd.DataFrame(item["hourly"]).assign(time=lambda d: pd.to_datetime(d.time))
                daily = daily[daily.time.between(start, end)]
                if not pd.DatetimeIndex(daily.time).equals(hours):
                    raise ValueError("Horas ERA5 faltantes")
                arrays.append(daily_from_hourly(daily))
            print(f"ERA5 reciente: {len(arrays)}/{len(points)} celdas", flush=True)
            if offset+8 < len(points):
                time.sleep(9)
    return (hours[::24] - pd.Timedelta(hours=5)).normalize().to_numpy(), np.stack(arrays, axis=1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pesos", type=Path)
    parser.add_argument("salida", type=Path)
    args = parser.parse_args()
    points = pd.read_csv(args.pesos, usecols=["lat", "lon"]).drop_duplicates().reset_index(drop=True)
    dates, data = fetch(points)
    np.savez_compressed(args.salida, fecha=dates, lat=points.lat, lon=points.lon,
                        **{var:data[:, :, i] for i,var in enumerate(["tmedia","tmax","tmin","hr"])})


if __name__ == "__main__":
    main()
