"""
Central project paths.

On Colab we used BASE = Path("/content/drive/MyDrive/Data Tesinha/...").
Now everything runs locally, so every path hangs from the repository root and
from the data/ folder with its medallion layout (bronze/silver/gold/reference).

Any notebook or script that needs a data path must import it from here
instead of hardcoding new paths.
"""

from pathlib import Path

# Repository root (this file lives in src/denguekay/config/paths.py -> go up 3 levels)
ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"

CONFIG = ROOT / "configs" / "config.yaml"

DATA = ROOT / "data"

BRONZE = DATA / "bronze"
SILVER = DATA / "silver"
SILVER_EPI_HISTORICAL = SILVER / "epi_piura_semanal.csv"
GOLD = DATA / "gold"   # datasets derived per horizon and the lineage manifest
REFERENCE = DATA / "reference"

# Bronze subfolders per source
BRONZE_METEO = BRONZE / "meteo"
CACHE_METEO = BRONZE_METEO / "cache_meteo"   # formerly on Drive, now local
BRONZE_SOCIO = BRONZE / "socio"
BRONZE_EPI = BRONZE / "epi"
BRONZE_SALA = BRONZE_EPI / "sala"
SILVER_SALA = SILVER / "epi_sala_semanal.csv"

# Integrated silver: silver sources already joined (meteo + socio + epi),
# still WITHOUT feature engineering. Gold is reserved for the dataset with
# the features ready for the model.
SILVER_INTEGRATED_DIR = SILVER / "integrado"
SILVER_METEO_SOCIO = SILVER_INTEGRATED_DIR / "meteo_socio_piura_2017_2025.csv"
SILVER_INTEGRATED_BASE = SILVER_INTEGRATED_DIR / "meteo_socio_epi_base_piura_2017_2025.csv"
SILVER_INTEGRATED = SILVER_INTEGRATED_DIR / "meteo_socio_epi_piura_2017_2025.csv"

UBIGEO_CATALOG = REFERENCE / "catalogo_ubigeos_piura.csv"
DISTRICT_COORDS = REFERENCE / "distritos_piura_coords.csv"
GOLD_MANIFEST = GOLD / "manifest_fase6.json"

MODELS = ROOT / "models"
SERVING_MODELS = MODELS / "serving"
# Local artifact storage (modelos/geodatos/reportes buckets of the OE2 document); not versioned.
STORAGE = MODELS / "storage"
# Model registry: one card per version (v0, v1, v2) and CHANGELOG.md; versioned in git, artifacts are not.
MODEL_REGISTRY = MODELS / "registry"
ENV_FILE = ROOT / ".env"
ALEMBIC_CONFIG = ROOT / "alembic.ini"
DB_MIGRATIONS = ROOT / "src" / "denguekay" / "db" / "migrations"
BACKEND_FIXTURES = ROOT / "tests" / "fixtures" / "backend"

# Experiment tracking (MLflow) and data quality (Great Expectations).
# The MLflow SQLite database and artifacts are local and not versioned.
MLFLOW_DB = ROOT / "mlflow.db"
MLFLOW_ARTIFACTS = ROOT / "mlartifacts"
GX_DIR = ROOT / "great_expectations"

# EDA outputs (versioned in Git: small text and figures, not data)
DOCS = ROOT / "docs"
BACKEND_DOCS = DOCS / "backend"
OPENAPI_JSON = BACKEND_DOCS / "openapi.json"
# Versioned evidence of the OE2 refactor (no credentials).
BACKEND_EVIDENCE = BACKEND_DOCS / "evidencia"
OE2_MIGRATION_SQL = BACKEND_EVIDENCE / "migracion_0003_oe2_postgresql.sql"
API_VERIFICATION = BACKEND_DOCS / "fase3_verificacion.json"
API_VERIFICATION_DB = SERVING_MODELS / "fase3.sqlite"
API_BENCHMARK_JSON = SERVING_MODELS / "benchmark.json"
API_BENCHMARK_DB = SERVING_MODELS / "fase4.sqlite"
BACKEND_PHASE4_VERIFICATION = BACKEND_DOCS / "fase4_verificacion.json"
BACKEND_BENCHMARK_SQLITE = BACKEND_DOCS / "benchmark_sqlite.json"
BACKEND_BENCHMARK_POSTGRESQL = BACKEND_DOCS / "benchmark_postgresql.json"
# Selection metrics of V0, read by serving (decision D5 of docs/decisions/0001-repo-restructure.md).
COMPACT_METRICS = MODEL_REGISTRY / "v0" / "validacion_temporal_compacta.json"
COMPACT_PREDICTIONS = MODELS / "experimentos" / "validacion_temporal_compacta" / "predicciones_por_bloque.csv"
# Research studies, frozen in research/<study>/ (docs/decisions/0001-repo-restructure.md).
RESEARCH = ROOT / "research"
RESEARCH_FIRST_MODELS = RESEARCH / "03_first_models_and_ablations"
# Multi-horizon architecture study (research/04_horizon_architecture/docs/plan_arquitectura_horizontes.md)
ARCHITECTURE_METRICS = RESEARCH / "04_horizon_architecture" / "docs" / "metricas" / "arquitectura_horizontes.json"
ARCHITECTURE_FIGURES = RESEARCH / "04_horizon_architecture" / "docs" / "figuras"
ARCHITECTURE_EXPERIMENTS = MODELS / "experimentos" / "arquitectura_horizontes"
# Feature engineering and hyperparameters study on E3·S4_s2 (research/05_fe_hyperparameters/docs/fe_hiperparametros.md)
FE_HYPERPARAMETERS_METRICS = RESEARCH / "05_fe_hyperparameters" / "docs" / "metricas" / "fe_hiperparametros.json"
FE_HYPERPARAMETERS_FIGURES = RESEARCH / "05_fe_hyperparameters" / "docs" / "figuras"
FE_HYPERPARAMETERS_EXPERIMENTS = MODELS / "experimentos" / "fe_hiperparametros"
VARIABLE_DICTIONARY = DOCS / "modeling" / "diccionario_variables.md"
SERVING_RUNS =SERVING_MODELS / "ejecuciones"
SERVING_REGENERATED_PROTOCOL = SERVING_MODELS / "protocolo_regenerado"
EDA_DOCS = RESEARCH / "01_eda" / "docs"
EDA_FIGURES = EDA_DOCS / "figuras"
EDA_METRICS = EDA_DOCS / "metricas"


def ensure_folders() -> None:
    """Create every data folder that does not exist yet (bronze/silver/gold/reference/models)."""
    for folder in (CACHE_METEO, BRONZE_SOCIO, BRONZE_EPI, SILVER, SILVER_INTEGRATED_DIR, GOLD, REFERENCE, MODELS):
        folder.mkdir(parents=True, exist_ok=True)
