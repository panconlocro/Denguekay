# Denguekay

Aplicación de Machine Learning para **pronosticar brotes de dengue por distrito y semana epidemiológica
en Piura (Perú)**, con al menos dos semanas de anticipación y cuatro como objetivo principal. Es la tesis
de Rosa y Nicolás (UPC), con metodología CRISP-DM.

- **Datos:** panel de los 65 distritos de Piura × semana epidemiológica, 2017–2025. Clima de Open-Meteo,
  sociodemografía del censo y casos de dengue (Excel epidemiológico hasta 2024 y Sala Situacional
  MINSA/DGE para 2025).
- **Modelo:** XGBoost. La configuración vigente es la [v2](models/registry/v2/ficha.md) y la que sirve hoy
  el backend es la [v0](models/registry/v0/ficha.md), como experimental. Historial en
  [models/registry/CHANGELOG.md](models/registry/CHANGELOG.md).
- **Backend:** PostgreSQL con el esquema del documento OE2, carga validada con Great Expectations,
  seguimiento en MLflow y una API FastAPI. En TB1 todo corre en local (sin Supabase ni Render).
- **Frontend:** planificado en [apps/web/](apps/web/README.md) (React + Vite).

## Estructura

Monorepo ([ADR 0001](docs/decisions/0001-repo-restructure.md)); el mapa completo está en
[docs/architecture.md](docs/architecture.md):

| Ruta | Contenido |
|---|---|
| `src/denguekay/` | Paquete instalable: `config`, `data`, `features`, `model`, `evaluation`, `db`, `serving`, `pipelines` |
| `apps/api/` | API FastAPI; `apps/api/tools/` con el benchmark, la exportación OpenAPI y la prueba de humo |
| `apps/web/` | Plan del frontend (todavía sin código) |
| `pipelines/notebooks/` | Notebooks del pipeline de datos: 01–09 (bronze → silver) y `10_silver_to_gold` |
| `models/registry/` | Ficha de cada versión de modelo (v0, v1, v2) y `CHANGELOG.md` |
| `research/` | Estudios congelados (EDA, feature engineering, modelado); el producto no los importa |
| `configs/`, `scripts/` | `config.yaml` del proyecto; scripts de instalación |
| `tests/` | Tests, con la misma estructura que el paquete (`tests/<subpaquete>/`, `tests/api/`) |
| `docs/` | Arquitectura, decisiones (ADR), backend (OE2, contrato de la API, operación) y modelado |

`data/` no se versiona (salvo `data/reference/`) y el código lo trata como **solo lectura**.

## Instalación

Requiere Python 3.12 o superior. Desde la raíz del repositorio:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

```bash
./scripts/setup.sh
```

Los dos crean `.venv`, instalan `requirements.txt` y el paquete `denguekay` en modo editable
(`pip install -e .`). Para el backend, copia `.env.example` como `.env` y define `DATABASE_URL`
(PostgreSQL local) y `API_KEY`. Los comandos de abajo usan la ruta de Windows del entorno
(`.\.venv\Scripts\python`); en macOS/Linux es `.venv/bin/python`.

## Pipeline de datos

Los notebooks de `pipelines/notebooks/` se ejecutan en orden y escriben bronze, silver, el integrado y,
con el 10, gold:

```powershell
.\.venv\Scripts\python -m jupyter nbconvert --to notebook --execute --inplace pipelines/notebooks/10_silver_to_gold.ipynb
```

Para completar semanas nuevas del integrado sin rehacer todo, existe el actualizador selectivo
(`--dry-run` solo informa qué fuentes consultaría):

```powershell
.\.venv\Scripts\python -m denguekay.pipelines.weekly_update --input data/silver/integrado/meteo_socio_epi_piura_2017_2025.csv --output data/silver/integrado/meteo_socio_epi_piura_2017_2025.csv --dry-run
```

Detalle del actualizador, la cobertura de casos verificados y la procedencia de los datos de 2025:
[docs/pipeline.md](docs/pipeline.md). Calidad de datos con Great Expectations:
`python -m denguekay.data.validation.gx_quality` (guía en
[docs/modeling/mlflow_great_expectations.md](docs/modeling/mlflow_great_expectations.md)).

## API

Con la BD creada y `.env` configurado:

```powershell
.\.venv\Scripts\python -m alembic upgrade head
.\.venv\Scripts\python -m denguekay.serving.load_data
.\.venv\Scripts\python -m denguekay.serving.publish --horizontes 2 4
.\.venv\Scripts\python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

La API queda en `http://127.0.0.1:8000/api/v1` (documentación interactiva en `/docs`; contrato en
[docs/backend/openapi.json](docs/backend/openapi.json)). Con uvicorn levantado,
`.\.venv\Scripts\python -m apps.api.tools.smoke_test` llama a cada endpoint de la Tabla 2 y escribe
[evidencia_tb1.md](docs/backend/evidencia/evidencia_tb1.md).

Ninguna versión de modelo cumple todavía los umbrales de aceptación (HU0007-4): se sirven como
`experimental: true` mediante `parametro_sistema.seleccion_experimental`. Operación, respaldo y
benchmark: [docs/backend/operacion.md](docs/backend/operacion.md). Contrato y decisiones:
[contrato API](docs/backend/contrato_api.md), [arquitectura del backend](docs/backend/arquitectura.md),
[especificación OE2](docs/backend/especificacion_oe2.md) y [desviaciones](docs/backend/desviaciones_oe2.md).

## Tests

```powershell
.\.venv\Scripts\python -m unittest discover -s tests
.\.venv\Scripts\python -m coverage run -m unittest discover -s tests
.\.venv\Scripts\python -m coverage report -m
```

Los tests usan SQLite temporal y, si existe `DENGUEKAY_PG_PRUEBAS_URL` (una BD desechable cuyo nombre
contiene «prueba»), repiten esquema e inferencia en PostgreSQL. Nunca usan `DATABASE_URL`. Las pruebas
que necesitan `data/` o `models/experimentos/` se omiten si faltan, como en el CI.

La suite incluye las guardas de la reestructuración:

- `tests/test_equivalence.py`: predicciones de V1 y V2 idénticas bit a bit, contrato de
  `docs/backend/openapi.json`, esquema tras `alembic upgrade head` (SQLite y PostgreSQL) y prueba de humo
  contra uvicorn. Su línea base está en `tests/fixtures/equivalence/` y no se regenera.
- `tests/test_layout.py`: sin restos del antiguo paquete `src` y dependencias en un solo sentido (el
  producto nunca importa `research/`).
- `tests/model/test_registry.py`: las fichas del registro coinciden con el paquete.

El CI (`.github/workflows/backend.yml`) corre la suite en Linux, Windows y macOS sobre SQLite, y en Linux
contra PostgreSQL 18, con cobertura mínima del 80 % en `apps/api`, `denguekay.serving` y `denguekay.db`.

## Modelado e investigación

XGBoost entrena en una GPU NVIDIA (CUDA) si la encuentra y, si no, en CPU (sección `xgboost` de
`configs/config.yaml`; `python -m denguekay.model.device --comparar` muestra qué detecta tu equipo). GPU y
CPU, y distinto número de hilos en CPU, dan decimales distintos; por eso las huellas de las versiones
congeladas se guardan por entorno. Los experimentos se registran en MLflow (`mlflow.db` y `mlartifacts/`,
locales): `.venv\Scripts\mlflow ui --backend-store-uri sqlite:///mlflow.db --workers 1`.

Los estudios (EDA, feature engineering, primeros modelos y ablaciones, arquitectura multi-horizonte, y
feature engineering e hiperparámetros) están congelados en `research/<estudio>/`; cada uno tiene un README
con su pregunta, su decisión y el tag desde el que se reproduce. Índice: [research/README.md](research/README.md).
Las instrucciones de Codex están en `AGENTS.md` y `.codex/skills/`; las de Claude Code, en `CLAUDE.md`.

## Contribuir

Ramas, commits, PR, tags e idioma del código: [CONTRIBUTING.md](CONTRIBUTING.md).
