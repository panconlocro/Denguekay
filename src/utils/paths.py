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
GOLD = DATA / "gold"   # solo el dataset con feature engineering (vacío por ahora)
REFERENCE = DATA / "reference"

# Subcarpetas de bronze por fuente
BRONZE_METEO = BRONZE / "meteo"
CACHE_METEO = BRONZE_METEO / "cache_meteo"   # antes: Drive -> ahora local
BRONZE_SOCIO = BRONZE / "socio"
BRONZE_EPI = BRONZE / "epi"
BRONZE_SALA = BRONZE_EPI / "sala"
SILVER_SALA = SILVER / "epi_sala_semanal.csv"

# Silver integrado: fuentes silver ya unidas entre sí (meteo + socio + epi),
# todavía SIN feature engineering. Gold queda reservado para el dataset con
# features listo para el modelo.
SILVER_INTEGRADO_DIR = SILVER / "integrado"
SILVER_METEO_SOCIO = SILVER_INTEGRADO_DIR / "meteo_socio_piura_2017_2025.csv"
SILVER_INTEGRADO_BASE = SILVER_INTEGRADO_DIR / "meteo_socio_epi_base_piura_2017_2025.csv"
SILVER_INTEGRADO = SILVER_INTEGRADO_DIR / "meteo_socio_epi_piura_2017_2025.csv"

UBIGEO_CATALOG = REFERENCE / "catalogo_ubigeos_piura.csv"

MODELS = ROOT / "models"


def asegurar_carpetas() -> None:
    """Crea todas las carpetas de datos si no existen (bronze/silver/gold/reference/models)."""
    for carpeta in (CACHE_METEO, BRONZE_SOCIO, BRONZE_EPI, SILVER, SILVER_INTEGRADO_DIR, GOLD, REFERENCE, MODELS):
        carpeta.mkdir(parents=True, exist_ok=True)
