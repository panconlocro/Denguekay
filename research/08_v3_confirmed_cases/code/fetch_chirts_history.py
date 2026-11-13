"""Download only CHIRTS chunks that intersect the verified Piura window."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import time

from numcodecs import Zstd
import numpy as np
import pandas as pd
import requests

REVISION = "35669afbbd1c6ab84dcc496f2f95b7cbbf75867f"
ROOT = f"https://huggingface.co/datasets/aaguilar90/chirts-era5-daily/resolve/{REVISION}/chirts-era5-daily.zarr"
START, END = "2004-11-07", "2026-10-03"
CHUNK = (128, 300, 300)
Y_WINDOW, X_WINDOW = slice(1478, 1530), slice(1970, 2018)
PRODUCTS = ("Tmax", "Tmin")


def get(key):
    for attempt in range(4):
        try:
            with requests.get(f"{ROOT}/{key}", timeout=(15, 75)) as response:
                if response.status_code == 429:
                    delay = response.headers.get("Retry-After", "")
                    time.sleep(max(10, int(delay)) if delay.isdigit() else 15 * (attempt + 1))
                    continue
                if response.status_code < 500:
                    response.raise_for_status()
                    return response.content
        except (requests.Timeout, requests.ConnectionError):
            if attempt == 3:
                raise
        time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"No se pudo leer {key} tras reintentos acotados")


def axis(name):
    meta = json.loads(get(f"{name}/zarr.json"))
    width = meta["chunk_grid"]["configuration"]["chunk_shape"][0]
    size = meta["shape"][0]
    dtype = np.dtype(meta["data_type"]).newbyteorder("<")
    parts = [np.frombuffer(Zstd().decode(get(f"{name}/c/{i}")), dtype=dtype)
             for i in range((size + width - 1) // width)]
    return np.concatenate(parts)[:size], meta["attributes"]


def tiles(dim, size):
    for chunk in range(dim.start // size, (dim.stop - 1) // size + 1):
        start = max(dim.start, chunk * size)
        stop = min(dim.stop, (chunk + 1) * size)
        yield chunk, slice(start - chunk * size, stop - chunk * size), slice(start - dim.start, stop - dim.start)


def read_chunk(task):
    product, t, cache = task
    path = cache / f"{product}_{t}.npz"
    if path.exists():
        with np.load(path) as previous:
            if str(previous["revision"]) == REVISION:
                return path
    crop = np.empty((CHUNK[0], Y_WINDOW.stop-Y_WINDOW.start, X_WINDOW.stop-X_WINDOW.start), dtype=np.int16)
    sha, sizes = {}, {}
    for y, ys, yd in tiles(Y_WINDOW, CHUNK[1]):
        for x, xs, xd in tiles(X_WINDOW, CHUNK[2]):
            key = f"{product}/c/{t}/{y}/{x}"
            compressed = get(key)
            values = np.frombuffer(Zstd().decode(compressed), dtype="<i2").reshape(CHUNK)
            crop[:, yd, xd] = values[:, ys, xs]
            sha[key] = hashlib.sha256(compressed).hexdigest()
            sizes[key] = len(compressed)
    temp = path.with_suffix(".tmp.npz")
    np.savez_compressed(temp, data=crop, sha=json.dumps(sha), bytes=json.dumps(sizes), revision=REVISION)
    temp.replace(path)
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--sample", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        (t, meta), (lat, _), (lon, _) = pool.map(axis, ("time", "lat", "lon"))
    if meta["units"] != "days since 1980-01-01":
        raise ValueError("Origen temporal inesperado")
    dates = pd.DatetimeIndex(pd.Timestamp("1980-01-01") + pd.to_timedelta(t, unit="D"))
    if not dates.equals(pd.date_range(dates[0], dates[-1])):
        raise ValueError("El eje temporal del archivo tiene saltos")
    if not (np.allclose(lat[Y_WINDOW][[0, -1]], [-3.925, -6.475], atol=1e-4)
            and np.allclose(lon[X_WINDOW][[0, -1]], [-81.475, -79.125], atol=1e-4)):
        raise ValueError("La ventana no coincide con los recortes CHC")
    start, end = dates.get_indexer([START, END])
    if start < 0 or end < 0:
        raise ValueError("El archivo no alcanza el periodo requerido")
    chunk_indices = range(start // CHUNK[0], end // CHUNK[0] + 1)
    if args.sample:
        chunk_indices = sorted({int(dates.get_loc(d) // CHUNK[0]) for d in ("2023-03-12", "2026-10-18")})
    tasks = [(p, i, args.output) for i in chunk_indices for p in PRODUCTS]
    for product in PRODUCTS:
        m = json.loads(get(f"{product}/zarr.json"))
        if (tuple(m["chunk_grid"]["configuration"]["chunk_shape"]) != CHUNK
                or m["data_type"] != "int16" or m["attributes"]["scale_factor"] != .1
                or m["attributes"]["_FillValue"] != -32768 or m["shape"][0] != len(dates)):
            raise ValueError(f"Metadatos no compatibles para {product}")
    with ThreadPoolExecutor(max_workers=6) as pool:
        paths = []
        for n, path in enumerate(pool.map(read_chunk, tasks), 1):
            paths.append(path)
            if n % 10 == 0 or n == len(tasks):
                print(f"Recortes CHIRTS: {n}/{len(tasks)}", flush=True)
    if args.sample:
        return
    data, hashes, sizes = {}, {}, {}
    for product in PRODUCTS:
        slices = []
        for i in chunk_indices:
            with np.load(args.output / f"{product}_{i}.npz") as chunk:
                slices.append(chunk["data"])
                hashes.update(json.loads(str(chunk["sha"])))
                sizes.update(json.loads(str(chunk["bytes"])))
        data[product] = np.concatenate(slices)[start % CHUNK[0]:start % CHUNK[0]+end-start+1]
    np.savez_compressed(args.output / "chirts_piura_diario.npz", fecha=dates[start:end+1].to_numpy(),
                        lat=lat[Y_WINDOW], lon=lon[X_WINDOW], **data)
    (args.output / "descarga.json").write_text(json.dumps({
        "revision": REVISION, "source": ROOT, "start": START, "end": END,
        "bytes_comprimidos": sum(sizes.values()), "sha256": hashes,
    }, indent=2) + "\n")
    print(f"CHIRTS histórico: {end-start+1} días en la ventana de Piura", flush=True)


if __name__ == "__main__":
    main()
