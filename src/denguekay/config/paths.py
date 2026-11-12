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
# Separate caches of study 06 (phase 1b): weather with the model fixed, so the
# "resume" of a download never mistakes them for the 2017-2025 cache.
CACHE_METEO_ERA5_2017_2025 = BRONZE_METEO / "cache_meteo_era5_2017_2025"
CACHE_METEO_ERA5_LAND_2017_2025 = BRONZE_METEO / "cache_meteo_era5_land_2017_2025"   # study 06, 1b: ERA5-Land check
CACHE_METEO_2000_2016 = BRONZE_METEO / "cache_meteo_2000_2016"
CACHE_METEO_ERA5_LAND_2000_2016 = BRONZE_METEO / "cache_meteo_era5_land_2000_2016"   # study 06, 1b'
# ERA5-Land of 2026 up to 2026-10-31 (study 06) and the later downloads, one snapshot per end date
# (cache_meteo_era5_land_reciente/<YYYY-MM-DD>/, notebook 02, cell C).
CACHE_METEO_ERA5_LAND_2026 = BRONZE_METEO / "cache_meteo_era5_land_2026"
CACHE_METEO_ERA5_LAND_RECENT = BRONZE_METEO / "cache_meteo_era5_land_reciente"
BRONZE_SOCIO = BRONZE / "socio"
BRONZE_EPI = BRONZE / "epi"
BRONZE_SALA = BRONZE_EPI / "sala"
BRONZE_ENSO = BRONZE / "enso"   # raw NOAA CPC sstoi.indices, one file per download date
# CHIRPS v3 daily, sat disaggregation: one GeoTIFF per day with the Piura window, plus the run manifests
BRONZE_CHIRPS = BRONZE / "chirps" / "v3_sat"
BRONZE_CHIRPS_FINAL = BRONZE_CHIRPS / "final"
BRONZE_CHIRPS_FINAL_FTP = BRONZE_CHIRPS / "final_ftp"   # CHC final by FTP (2026-11-08): Piura windows, as prelim/
BRONZE_CHIRPS_PRELIM = BRONZE_CHIRPS / "prelim"   # CHC preliminary: Piura windows of the days without final
# Earth Engine (UCSB-CHC/CHIRPS/V3/DAILY_SAT): monthly reduceRegions responses per district polygon, as they arrive
BRONZE_CHIRPS_EE_FINAL = BRONZE_CHIRPS / "ee_final"
# Peru COD-AB (IGN, published by OCHA on HDX, CC BY-IGO): the downloaded archive as is, with its manifest
BRONZE_BOUNDARIES = BRONZE / "limites" / "hdx_cod_ab_per"
SILVER_SALA = SILVER / "epi_sala_semanal.csv"
SILVER_METEO_2000_2016 = SILVER / "meteo_semanal_distrital_2000_2016.csv"   # study 06, phase 1b
# Study 06, 1b': humidity and temperature from ERA5-Land 2000-2025 (no precipitation), apart from the silver in use.
SILVER_METEO_ERA5_LAND_2000_2025 = SILVER / "meteo_humedad_era5_land_2000_2025.csv"
# ERA5-Land weekly temperature and humidity from 2000 to the latest download (notebook 03): input of the v3 (d3).
SILVER_METEO_ERA5_LAND = SILVER / "meteo_humedad_era5_land_desde_2000.csv"
# The frozen input of the v3 (2000 to the week of 2026-10-25), in datos_v3.zip of the model/v3 Release; used when
# SILVER_METEO_ERA5_LAND does not exist yet (features.climate.era5_land_silver).
SILVER_METEO_ERA5_LAND_2000_2026 = SILVER / "meteo_humedad_era5_land_2000_2026.csv"
# Weekly precipitation per district from CHIRPS v3 sat (polygon mean; final from Earth Engine, preliminary from
# the CHC for the weeks without final), with version and fecha_disponible; apart from the V2 silver
SILVER_CHIRPS_PRECIP = SILVER / "precip_chirps_v3_semanal_desde_2000.csv"
SILVER_ENSO = SILVER / "enso_nino12_mensual.csv"   # monthly Niño 1+2 with the date it becomes usable

# Integrated silver: silver sources already joined (meteo + socio + epi),
# still WITHOUT feature engineering. Gold is reserved for the dataset with
# the features ready for the model.
SILVER_INTEGRATED_DIR = SILVER / "integrado"
SILVER_METEO_SOCIO = SILVER_INTEGRATED_DIR / "meteo_socio_piura_2017_2025.csv"
SILVER_INTEGRATED_BASE = SILVER_INTEGRATED_DIR / "meteo_socio_epi_base_piura_2017_2025.csv"
SILVER_INTEGRATED = SILVER_INTEGRATED_DIR / "meteo_socio_epi_piura_2017_2025.csv"

UBIGEO_CATALOG = REFERENCE / "catalogo_ubigeos_piura.csv"
DISTRICT_COORDS = REFERENCE / "distritos_piura_coords.csv"
# The 65 Piura district polygons (from the COD-AB) for the area-weighted CHIRPS mean; versioned
DISTRICT_BOUNDARIES = REFERENCE / "distritos_piura_limites.geojson"
GOLD_MANIFEST = GOLD / "manifest_fase6.json"
# Gold before the cleanup (all the candidates, h=2 and h=4): the input of the v0 and of study 03. Only copy.
GOLD_BACKUP = GOLD / "respaldo_pre_b3"

MODELS = ROOT / "models"
SERVING_MODELS = MODELS / "serving"
# Local artifact storage (modelos/geodatos/reportes buckets of the OE2 document); not versioned.
STORAGE = MODELS / "storage"
# Model registry: one card per version (v0, v1, v2) and CHANGELOG.md; versioned in git, artifacts are not.
MODEL_REGISTRY = MODELS / "registry"
# Data bundles of the frozen V3 (zips attached to the GitHub Release of model/v3): files, rows and SHA-256.
V3_DATA_MANIFEST = MODEL_REGISTRY / "v3" / "manifiesto_datos.json"
# Frozen out-of-sample predictions of the v3 (5 seeds, every block; predicciones_v3.zip of the Release): the v3
# package fits Platt and the 5a mixture with them and publishes their 2022-2025 blocks as its OOS.
V3_REFERENCE_PREDICTIONS = MODELS / "experimentos" / "mejora_modelo" / "v3" / "predicciones_v3.csv.gz"
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
# Frozen v1 contract without database examples (guard of tests/test_contract_v1_guards.py).
OPENAPI_V1_JSON = BACKEND_DOCS / "openapi_v1.json"
# Demo database for the frontend (decision D1); not versioned.
DEMO_DIR = SERVING_MODELS / "demo"
DEMO_V4_DIR = SERVING_MODELS / "demo_v4"
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
