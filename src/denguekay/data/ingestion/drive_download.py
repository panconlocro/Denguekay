"""
Replaces the Google Drive mount (drive.mount) we used on Colab.

Running locally, the raw epi and socio Excel files are downloaded straight
from Google Drive with `gdown`, using the file ID (not the folder ID).
The IDs live in configs/config.yaml, never hardcoded here.

How to get the ID: in the Drive link
  https://drive.google.com/file/d/AAAA.../view?usp=sharing
the ID is the "AAAA..." part.

Install: pip install gdown
"""

from pathlib import Path

import gdown

from denguekay.config.paths import BRONZE_EPI, BRONZE_SOCIO


def download_from_drive(file_id: str, destination: Path, force: bool = False) -> Path:
    """
    Download a Drive file by its file_id into `destination` (bronze).
    If the file already exists and `force=False`, it is not downloaded again
    (the same "resume" rule used for the meteo cache).
    """
    destination.parent.mkdir(parents=True, exist_ok=True)

    if destination.exists() and not force:
        print(f"Ya existe, no se vuelve a descargar: {destination}")
        return destination

    url = f"https://drive.google.com/uc?id={file_id}"
    gdown.download(url, str(destination), quiet=False)
    return destination


def download_epi(file_id: str, file_name: str = "PiuraDengue.xlsx", force: bool = False) -> Path:
    """Download the raw epidemiological Excel into data/bronze/epi/."""
    return download_from_drive(file_id, BRONZE_EPI / file_name, force=force)


def download_socio(file_id: str, file_name: str = "data_socio_2017_2025.xlsx", force: bool = False) -> Path:
    """Download the raw sociodemographic Excel into data/bronze/socio/."""
    return download_from_drive(file_id, BRONZE_SOCIO / file_name, force=force)
