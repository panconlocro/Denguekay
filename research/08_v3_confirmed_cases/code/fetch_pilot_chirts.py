"""Fetch only the Piura windows of the CHIRTS-ERA5 pilot dates."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from time import sleep

import pandas as pd
import rasterio
from rasterio.windows import Window, from_bounds
import requests

from pilot_climate_exposure import CHIRTS_WEEKS

FOLDER_URL = "https://data.chc.ucsb.edu/experimental/CHIRTS-ERA5"
BOUNDS = (-81.45, -6.50, -79.10, -3.95)
MAX_BYTES = 32 * 1024**2


def crop(source_path, destination, url):
    with rasterio.open(source_path) as source:
        bounds = from_bounds(*BOUNDS, source.transform)
        window = Window(int(bounds.col_off), int(bounds.row_off), int(bounds.width) + 2, int(bounds.height) + 2)
        array = source.read(1, window=window)
        if array.shape != (int(window.height), int(window.width)):
            raise ValueError(f"Recorte incompleto para {url}")
        profile = source.profile.copy()
        profile.update(height=array.shape[0], width=array.shape[1], transform=source.window_transform(window),
                       nodata=-9999)
    with rasterio.open(destination, "w", **profile) as cropped:
        cropped.write(array, 1)
        cropped.update_tags(url=url)


def download_one(kind, day, folder, allow_full):
    name = f"CHIRTS-ERA5.daily_T{kind}.{day:%Y.%m.%d}.tif"
    url = f"{FOLDER_URL}/t{kind}/tifs/daily/{day:%Y}/{name}"
    destination = folder / name
    if destination.exists():
        with rasterio.open(destination) as saved:
            if saved.tags().get("url") == url:
                return
        raise ValueError(f"El recorte previo no coincide con {url}")
    with TemporaryDirectory(dir=folder) as work:
        pending = Path(work) / "recorte.tif"
        with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
                          GDAL_HTTP_TIMEOUT="20", GDAL_HTTP_MAX_RETRY="1", CPL_VSIL_CURL_CHUNK_SIZE="524288",
                          GDAL_HTTP_MULTIRANGE="SERIAL", CPL_VSIL_CURL_USE_HEAD="NO"):
            try:
                crop("/vsicurl/" + url, pending, url)
            except rasterio.errors.RasterioError:
                if not allow_full:
                    raise
                print(f"Reintentando {name} con el archivo original", flush=True)
                whole = Path(work) / "original.tif"
                with requests.get(url, stream=True, timeout=(20, 45)) as response, whole.open("wb") as output:
                    response.raise_for_status()
                    for chunk in response.iter_content(1024 * 1024):
                        if output.tell() + len(chunk) > MAX_BYTES:
                            raise ValueError(f"El archivo supera el límite del piloto: {url}")
                        output.write(chunk)
                crop(whole, pending, url)
                sleep(2)
        pending.replace(destination)
    print(name, flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("carpeta", type=Path)
    parser.add_argument("--permitir-tiff-completo", action="store_true")
    args = parser.parse_args()
    args.carpeta.mkdir(parents=True, exist_ok=True)
    days = [day for start in CHIRTS_WEEKS for day in pd.date_range(start, periods=7)]
    with ThreadPoolExecutor(max_workers=1 if args.permitir_tiff_completo else 4) as pool:
        tasks = [pool.submit(download_one, kind, day, args.carpeta, args.permitir_tiff_completo)
                 for day in days for kind in ("max", "min")]
        for task in tasks:
            task.result()


if __name__ == "__main__":
    main()
