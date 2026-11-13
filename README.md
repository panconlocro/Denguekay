# Denguekay

Aplicación de Machine Learning para **pronosticar brotes de dengue por distrito y semana epidemiológica
en Piura (Perú)**, con al menos dos semanas de anticipación y cuatro como objetivo principal (horizontes 2, 3 y
4). Es la tesis de Rosa y Nicolás (UPC), con metodología CRISP-DM.

El estado actual del proyecto (qué versión se sirve, qué está congelado y qué falta) está en
**[STATUS.md](STATUS.md)**.

## Qué hay en el repositorio

- **Datos:** panel de los 65 distritos de Piura × semana epidemiológica. Casos confirmados de dengue (Excel
  epidemiológico de MINSA/CDC hasta 2024 y Sala Situacional desde 2025; la historia de casos llega a 2000),
  clima de Open-Meteo y ERA5-Land, lluvia CHIRPS v3, índice Niño 1+2 (NOAA) y sociodemografía del censo.
  Esquema medallion (bronze → silver → gold); detalle en [docs/pipeline.md](docs/pipeline.md).
- **Modelo:** XGBoost multisalida (conteo Poisson para t+2, t+3 y t+4, probabilidad de brote con binomial
  negativa NB2 y calibración de Platt). Cada versión tiene su ficha en [models/registry/](models/registry/CHANGELOG.md):

  | Versión | Estado |
  |---|---|
  | [v4](models/registry/v4/ficha.md) | `b3_obs` con casos confirmados; congelada para el paper (12/11/2026) y servida en la demo V4 |
  | [v3](models/registry/v3/ficha.md) | L + 5a + d3; la que construye la publicación del backend (experimental) |
  | [v2](models/registry/v2/ficha.md), [v1](models/registry/v1/ficha.md), [v0](models/registry/v0/ficha.md) | reemplazadas; siguen registradas y se pueden reentrenar |

- **Backend:** PostgreSQL con el esquema del documento OE2, carga validada con Great Expectations, seguimiento de
  experimentos en MLflow y una API FastAPI (contrato `1.1.0`). El repo está preparado para desplegar en Render,
  Supabase y Vercel ([despliegue](docs/backend/despliegue.md)); el despliegue se hace a mano.
- **Frontend:** tablero web en [apps/web/](apps/web/README.md) (React, Vite y TypeScript) que solo consume la API.

## Estructura

Monorepo ([ADR 0001](docs/decisions/0001-repo-restructure.md)); el mapa completo está en
[docs/architecture.md](docs/architecture.md):

| Ruta | Contenido |
|---|---|
| `src/denguekay/` | Paquete instalable: `config`, `data`, `features`, `model`, `evaluation`, `db`, `serving`, `pipelines` |
| `apps/api/` | API FastAPI; `apps/api/tools/` con el benchmark, la exportación OpenAPI y la prueba de humo |
| `apps/web/` | Frontend React (tablero, mapa, detalle distrital, avisos, desempeño y ayuda) |
| `pipelines/notebooks/` | Notebooks del pipeline de datos: 01–09 (bronze → silver) y `10_silver_to_gold` |
| `models/registry/` | Ficha de cada versión de modelo (v0–v4) y `CHANGELOG.md` |
| `research/` | Estudios congelados (01–08); el producto no los importa. Índice en [research/README.md](research/README.md) |
| `configs/`, `scripts/` | `config.yaml` del proyecto; scripts de instalación (`setup.ps1`, `setup.sh`) |
| `tests/` | Tests, con la misma estructura que el paquete (`tests/<subpaquete>/`, `tests/api/`) |
| `docs/` | Arquitectura, decisiones (ADR), backend (OE2, contrato de la API, operación), modelado y reproducibilidad |

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
(`pip install -e .`). Para reproducir resultados con las versiones exactas, instala con `constraints.txt`
(ver [docs/reproducibilidad.md](docs/reproducibilidad.md)). Para el backend, copia `.env.example` como `.env` y
define `DATABASE_URL` (PostgreSQL local) y `API_KEY`. Los comandos de abajo usan la ruta de Windows
(`.\.venv\Scripts\python`); en macOS/Linux es `.venv/bin/python`.

## Pipeline de datos

Todo `data/` se regenera desde las fuentes públicas con:

```powershell
.\.venv\Scripts\python -m denguekay.pipelines.run_all
```

Los notebooks de `pipelines/notebooks/` también se pueden ejecutar uno por uno, en orden; el 10 regenera gold:

```powershell
.\.venv\Scripts\python -m jupyter nbconvert --to notebook --execute --inplace pipelines/notebooks/10_silver_to_gold.ipynb
```

Para completar semanas nuevas del integrado sin rehacer todo existe el actualizador selectivo
(`python -m denguekay.pipelines.weekly_update`, con `--dry-run` para ver qué consultaría). Detalle del pipeline,
la cobertura de casos y la procedencia de los datos: [docs/pipeline.md](docs/pipeline.md). Calidad de datos con
Great Expectations: [docs/modeling/mlflow_great_expectations.md](docs/modeling/mlflow_great_expectations.md).

## API

Con la BD creada y `.env` configurado:

```powershell
.\.venv\Scripts\python -m alembic upgrade head
.\.venv\Scripts\python -m denguekay.serving.load_data
.\.venv\Scripts\python -m denguekay.serving.publish --seleccionar-experimental
.\.venv\Scripts\python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

La publicación construye el paquete que indica `serving.paquete` en `configs/config.yaml` (hoy la v3). La API
queda en `http://127.0.0.1:8000/api/v1` (documentación interactiva en `/docs`; contrato en
[docs/backend/openapi.json](docs/backend/openapi.json)). Con uvicorn levantado,
`.\.venv\Scripts\python -m apps.api.tools.smoke_test` llama a cada endpoint y deja la evidencia en
`docs/backend/evidencia/`.

Ninguna versión se sirve como validada: se publican como `experimental: true` mediante
`parametro_sistema.seleccion_experimental`. Operación, respaldo y benchmark:
[docs/backend/operacion.md](docs/backend/operacion.md). Contrato y decisiones:
[contrato API](docs/backend/contrato_api.md), [arquitectura del backend](docs/backend/arquitectura.md),
[especificación OE2](docs/backend/especificacion_oe2.md) y [desviaciones](docs/backend/desviaciones_oe2.md).

## Frontend

Requiere Node.js 20.19 o superior y la API levantada ([guía](docs/backend/guia_frontend.md)). Desde `apps/web`:

```bash
npm ci
npm run dev
```

La demo local con la v4 (BD SQLite aislada, de solo lectura) se arma desde la raíz con
`python -m denguekay.serving.demo_database --paquete-v4 <carpeta del paquete>` y se abre con `npm run dev:demo`;
los pasos completos están en [apps/web/README.md](apps/web/README.md).

## Tests

```powershell
.\.venv\Scripts\python -m unittest discover -s tests
.\.venv\Scripts\python -m coverage run -m unittest discover -s tests
.\.venv\Scripts\python -m coverage report -m
```

Los tests usan SQLite temporal y, si existe `DENGUEKAY_PG_PRUEBAS_URL` (una BD desechable cuyo nombre contiene
«prueba»), repiten esquema e inferencia en PostgreSQL. Nunca usan `DATABASE_URL`. Las pruebas que necesitan
`data/` o `models/experimentos/` se omiten si faltan, como en el CI. La suite incluye las guardas de la
reestructuración: `tests/test_equivalence.py` (su línea base en `tests/fixtures/equivalence/` no se regenera),
`tests/test_layout.py` (el producto nunca importa `research/`) y `tests/model/test_registry.py` (las fichas
coinciden con el paquete).

El CI tiene dos flujos: `backend.yml` corre la suite en Linux, Windows y macOS sobre SQLite y en Linux contra
PostgreSQL 18, con cobertura mínima del 80 % en `apps/api`, `denguekay.serving` y `denguekay.db`; `frontend.yml`
comprueba el contrato OpenAPI, lint, formato, pruebas unitarias, build y E2E con fixtures.

## Reproducibilidad

**Punto de entrada único: [docs/reproducibilidad.md](docs/reproducibilidad.md).** Explica cómo obtener los datos
exactos de cada versión (Releases de sus tags, verificados con SHA-256), cómo reentrenar y verificar v0–v3
(`python -m denguekay.model.reproduce <versión>`), cómo reproducir cada estudio desde su tag y cómo regenerar
`data/` desde las fuentes. La v3 tiene su guía propia ([reproducir_v3.md](docs/modeling/reproducir_v3.md)) y su
protocolo ([protocolo_v3.md](docs/modeling/protocolo_v3.md)). La v4 se reproduce con
[research/08_v3_confirmed_cases/congelamiento_b3_v4.md](research/08_v3_confirmed_cases/congelamiento_b3_v4.md).

XGBoost entrena en una GPU NVIDIA (CUDA) si la encuentra y, si no, en CPU (sección `xgboost` de
`configs/config.yaml`; `python -m denguekay.model.device --comparar` muestra qué detecta tu equipo). GPU y CPU dan
decimales distintos, por eso las huellas de las versiones congeladas se guardan por entorno. Los experimentos se
registran en MLflow local: `.venv\Scripts\mlflow ui --backend-store-uri sqlite:///mlflow.db --workers 1`.

## Contribuir

`main` es producción y `develop` integración: todo cambio sale de `develop` y vuelve a `develop` por PR
([ADR 0002](docs/decisions/0002-develop-branch.md)). Las reglas del proyecto, las ramas, los commits, los PR, los
tags y el idioma del código están en [CONTRIBUTING.md](CONTRIBUTING.md).
