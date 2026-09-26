"""
Rutas centrales del proyecto.

Antes en Colab usábamos BASE = Path("/content/drive/MyDrive/Data Tesinha/...").
Ahora que todo corre local en VS Code, todo cuelga de la raíz del repo y de
la carpeta data/ con arquitectura medallón (bronze/silver/gold/reference).

Cualquier notebook o script que necesite una ruta de datos debe importar
de acá en vez de hardcodear paths nuevos.
"""

from pathlib import Path

# Raíz del repo (este archivo vive en src/utils/paths.py -> subir 2 niveles)
ROOT = Path(__file__).resolve().parents[2]

DATA = ROOT / "data"

BRONZE = DATA / "bronze"
SILVER = DATA / "silver"
GOLD = DATA / "gold"
REFERENCE = DATA / "reference"

# Subcarpetas de bronze por fuente
BRONZE_METEO = BRONZE / "meteo"
CACHE_METEO = BRONZE_METEO / "cache_meteo"   # antes: Drive -> ahora local
BRONZE_SOCIO = BRONZE / "socio"
BRONZE_EPI = BRONZE / "epi"

MODELS = ROOT / "models"


def asegurar_carpetas() -> None:
    """Crea todas las carpetas de datos si no existen (bronze/silver/gold/reference/models)."""
    for carpeta in (CACHE_METEO, BRONZE_SOCIO, BRONZE_EPI, SILVER, GOLD, REFERENCE, MODELS):
        carpeta.mkdir(parents=True, exist_ok=True)
