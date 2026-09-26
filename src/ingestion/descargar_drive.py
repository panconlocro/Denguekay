"""
Reemplaza el montaje de Google Drive (drive.mount) que usábamos en Colab.

Ahora, corriendo local en VS Code, bajamos los Excel crudos de epi y
socio directo desde Google Drive con `gdown`, usando el ID del archivo
(no la carpeta). Los IDs van en config/config.yaml — no hardcodeados acá.

Cómo conseguir el ID: en el link de Drive
  https://drive.google.com/file/d/AAAA.../view?usp=sharing
el ID es la parte "AAAA...".

Instalar: pip install gdown
"""

from pathlib import Path

import gdown

from src.utils.paths import BRONZE_EPI, BRONZE_SOCIO


def descargar_desde_drive(file_id: str, destino: Path, forzar: bool = False) -> Path:
    """
    Descarga un archivo de Drive por su file_id hacia `destino` (bronze).
    Si el archivo ya existe y `forzar=False`, no lo vuelve a descargar
    (mismo criterio de "resume" que usamos para el cache de meteo).
    """
    destino.parent.mkdir(parents=True, exist_ok=True)

    if destino.exists() and not forzar:
        print(f"Ya existe, no se vuelve a descargar: {destino}")
        return destino

    url = f"https://drive.google.com/uc?id={file_id}"
    gdown.download(url, str(destino), quiet=False)
    return destino


def descargar_epi(file_id: str, nombre_archivo: str = "PiuraDengue.xlsx", forzar: bool = False) -> Path:
    """Descarga el Excel crudo epidemiológico a data/bronze/epi/."""
    return descargar_desde_drive(file_id, BRONZE_EPI / nombre_archivo, forzar=forzar)


def descargar_socio(file_id: str, nombre_archivo: str = "data_socio_2017_2025.xlsx", forzar: bool = False) -> Path:
    """Descarga el Excel crudo sociodemográfico a data/bronze/socio/."""
    return descargar_desde_drive(file_id, BRONZE_SOCIO / nombre_archivo, forzar=forzar)
