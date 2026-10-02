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
SRC = ROOT / "src"

CONFIG = ROOT / "config" / "config.yaml"

DATA = ROOT / "data"

BRONZE = DATA / "bronze"
SILVER = DATA / "silver"
SILVER_EPI_HISTORICO = SILVER / "epi_piura_semanal.csv"
GOLD = DATA / "gold"   # datasets derivados por horizonte y manifiesto de linaje
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
DISTRITOS_COORDS = REFERENCE / "distritos_piura_coords.csv"
GOLD_MANIFEST = GOLD / "manifest_fase6.json"

MODELS = ROOT / "models"
SERVING_MODELS = MODELS / "serving"
ENV_FILE = ROOT / ".env"
ALEMBIC_CONFIG = ROOT / "alembic.ini"
DB_MIGRACIONES = ROOT / "src" / "db" / "migraciones"
BACKEND_FIXTURES = ROOT / "tests" / "fixtures" / "backend"

# Seguimiento de experimentos (MLflow) y calidad de datos (Great Expectations).
# La base SQLite y los artefactos de MLflow son locales y no se versionan.
MLFLOW_DB = ROOT / "mlflow.db"
MLFLOW_ARTEFACTOS = ROOT / "mlartifacts"
GX_DIR = ROOT / "great_expectations"

# Salidas del EDA (versionadas en Git: son texto y figuras chicas, no datos)
DOCS = ROOT / "docs"
BACKEND_DOCS = DOCS / "backend"
METRICAS_COMPACTAS = DOCS / "modeling" / "metricas" / "validacion_temporal_compacta.json"
PREDICCIONES_COMPACTAS = MODELS / "experimentos" / "validacion_temporal_compacta" / "predicciones_por_bloque.csv"
SERVING_EJECUCIONES = SERVING_MODELS / "ejecuciones"
SERVING_PROTOCOLO_REGENERADO = SERVING_MODELS / "protocolo_regenerado"
EDA_DOCS = DOCS / "eda"
EDA_FIGURAS = EDA_DOCS / "figuras"
EDA_METRICAS = EDA_DOCS / "metricas"


def asegurar_carpetas() -> None:
    """Crea todas las carpetas de datos si no existen (bronze/silver/gold/reference/models)."""
    for carpeta in (CACHE_METEO, BRONZE_SOCIO, BRONZE_EPI, SILVER, SILVER_INTEGRADO_DIR, GOLD, REFERENCE, MODELS):
        carpeta.mkdir(parents=True, exist_ok=True)
