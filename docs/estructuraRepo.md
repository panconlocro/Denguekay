# Estructura del repositorio — Tesis Dengue Piura

Esta guía explica cómo está organizado el repo y **dónde va cada archivo nuevo** que agreguemos (código, datos, modelos, docs). La idea es que cualquiera del equipo (o alguien que se sume después) sepa en 30 segundos dónde poner algo sin tener que preguntar.

## Árbol completo

```
tesis-dengue-piura/
├── README.md
├── CONTRIBUTING.md            # ramas, commits, PR, tags e idioma del código
├── .mailmap                   # unifica las identidades de autor en git log/shortlog
├── CLAUDE.md                  # contexto y reglas para Claude Code
├── _claude_setup/             # configuración versionada para Claude Code
├── .claude/agents/            # subagentes auditores versionados (revisor-backend, revisor-modelado)
├── AGENTS.md                  # contexto y reglas para Codex
├── .codex/skills/             # workflows de Codex (feature engineering)
├── .gitignore
├── .env.example               # conexión y secretos sin valores reales
├── alembic.ini                # migraciones del backend, sin credenciales
├── pyproject.toml             # paquete instalable denguekay (pip install -e .); dependencias = requirements.txt
├── .coveragerc                # cobertura de API/serving/db, umbral de CI
├── .github/workflows/         # tests (SQLite y PostgreSQL) y cobertura en push/PR; sin despliegue
├── requirements.txt
├── configs/
│   └── config.yaml
│
├── data/                      # solo lectura para el código; no se versiona salvo reference/
│   ├── bronze/
│   ├── silver/
│   │   └── integrado/         # merges entre fuentes, sin features
│   ├── gold/                  # dos datasets por horizonte y manifiesto de fase 6
│   └── reference/
│
├── src/denguekay/             # paquete instalable del producto (código en inglés)
│   ├── config/                # paths.py: todas las rutas del proyecto
│   ├── data/                  # calendario, llaves, carga y temporadas
│   │   ├── ingestion/         # descargas y scraping
│   │   ├── processing/        # bronze -> silver -> integrado
│   │   └── validation/        # comprobaciones estrictas y suites de Great Expectations
│   ├── features/              # variables del modelo y gold
│   ├── model/                 # entrenamiento XGBoost, dispositivo, MLflow, configuración congelada
│   ├── evaluation/            # métricas, protocolos y estudios reutilizables
│   ├── db/                    # ORM, configuración, sesiones y migraciones Alembic
│   ├── serving/               # carga, inferencia real y publicación batch
│   └── pipelines/             # actualización semanal selectiva del integrado
│
├── apps/api/                  # aplicación FastAPI (no se instala; corre desde la raíz)
│   ├── routers/
│   └── tools/                 # benchmark, export_openapi, smoke_test
│
├── pipelines/notebooks/       # pipeline: 01–09 (bronze/silver) y 10_silver_to_gold
├── research/                  # estudios congelados: 01_eda … 05_fe_hyperparameters (README por estudio)
├── great_expectations/        # contexto de GX generado (gx/ no se versiona)
├── models/
├── tests/                     # misma estructura que el paquete: tests/<subpaquete>/ y tests/api/
│   ├── fixtures/backend/      # muestra agregada real, pequeña y versionada
│   └── fixtures/equivalence/  # línea base de las guardas de la reestructuración (no se regenera)
├── mlflow.db                  # tracking de MLflow (generado, no se versiona)
├── mlartifacts/               # artefactos de MLflow (generado, no se versiona)
└── docs/
    ├── modeling/              # guía de MLflow/GX, diccionario de variables y métricas que lee serving (V0)
    ├── decisions/             # ADR numerados (0001: reestructuración en monorepo)
    └── backend/               # operación y evidencia del backend por fase
```

Dependencias en un solo sentido ([ADR 0001](decisions/0001-repo-restructure.md)): `apps/` y los
notebooks del pipeline importan `denguekay`; `research/` puede importar `denguekay`; `denguekay` no
importa ni `apps` ni `research`. `tests/test_layout.py` lo comprueba, junto con que no queden
referencias al antiguo paquete `src`.

---

## 1. La regla de oro: paquete vs notebooks

Antes de explicar carpeta por carpeta, esta es la decisión que más se repite y la que más dudas genera:

> **Si el código lo volverías a necesitar en otro notebook, o tiene más de ~10 líneas de lógica (loops, reintentos, parsing, cálculos), va en `src/denguekay/`. Si es "cargar esto, llamar esa función, mostrar el resultado", se queda en el notebook.**

- `src/denguekay/` = el motor. Funciones puras, reutilizables, testeables. No saben nada de Drive, de Colab, ni de en qué orden se ejecutan.
- `pipelines/notebooks/` = el tablero de control. Pocas líneas, importan funciones de `denguekay`, deciden el orden, muestran resultados y verificaciones puntuales (`print`, `.describe()`, gráficos exploratorios).

Nada de lógica se duplica entre los dos. Si corriges un bug, lo corriges en un solo lugar (`src/denguekay/`), no en cinco notebooks distintos.

Idioma: el código del paquete y de `apps/` está en inglés. Siguen en español, porque son contratos: las tablas y columnas de la BD (documento OE2), las columnas de los datos, los campos de la API y, por la decisión D2, los handlers y esquemas Pydantic de `apps/api/` (forman el contrato OpenAPI), los nombres de artefactos registrados y la ruta `models/storage/`.

---

## 2. `data/` — arquitectura medallón (bronze / silver / gold)

**Esta carpeta NO se sube a Git** (va en `.gitignore`, ver sección 6). Los datos pesados viven en Drive/Supabase; el repo solo versiona el código que los genera.

### `data/bronze/` — crudo, tal cual llega de la fuente
Nada de limpieza, nada de validación. Un subfolder por fuente:
```
bronze/
├── meteo/cache_meteo/       # un parquet por distrito, tal cual responde Open-Meteo
├── socio/                   # el Excel del censo/proyecciones, sin tocar
└── epi/                     # Excel y respuestas crudas de la Sala Situacional MINSA
```
**Va acá:** cualquier archivo nuevo que baje de una API, scraping o que alguien te pase como fuente original. Si dudas si algo es "bronze", pregúntate: ¿esto es exactamente lo que devolvió la fuente, sin que yo lo haya tocado? Si sí, es bronze.

### `data/silver/` — limpio, normalizado e integrado (sin feature engineering)
Silver tiene dos niveles:
```
silver/
├── meteo_semanal_distrital.csv     # por fuente
├── socio_anual.csv
├── epi_piura_semanal.csv
├── epi_sala_semanal.csv            # exportación normalizada por ejecución
└── integrado/                      # fuentes silver unidas entre sí
    ├── meteo_socio_piura_2017_2025.csv                   # meteo + socio
    ├── meteo_socio_epi_base_piura_2017_2025.csv          # + epi histórico (entrada del actualizador)
    ├── meteo_socio_epi_piura_2017_2025.csv               # + epi completado por el actualizador
    └── meteo_socio_epi_piura_2017_2025.coverage.csv      # cobertura de casos verificados
```
**Por fuente (raíz de `silver/`):** ya pasaron por normalización de nombres de distrito (`distrito_key`), tipos de dato correctos, deduplicación, y (idealmente) una corrida de Great Expectations. Es la salida de cualquier notebook `0X_bronze_to_silver_*`. Si agregas una fuente nueva (ej. datos de un hospital, otro sensor climático), su versión limpia va acá con su propio nombre de archivo.

**`silver/integrado/`:** el resultado de cualquier merge entre fuentes silver (notebooks `08_silver_merge_*` y `09_silver_merge_*`, y el actualizador `src/denguekay/pipelines/weekly_update.py`). Siguen siendo datos limpios sin features derivadas, por eso **no van en gold**. Si agregas una versión nueva (ej. extendida a 2026), no sobrescribas el archivo viejo — nómbralo distinto (`meteo_socio_epi_piura_2017_2026.csv`) para poder comparar versiones.

### `data/gold/` — solo el dataset con feature engineering
```
gold/
├── .gitkeep
├── meteo_socio_epi_piura_2017_2025_h2_gold.csv
├── meteo_socio_epi_piura_2017_2025_h4_gold.csv
└── manifest_fase6.json
```
**Va acá:** únicamente el dataset con el feature engineering ya aplicado, listo para entrenar el modelo. Un merge entre fuentes **no** es gold: eso va en `silver/integrado/`.

El plan de construcción está en `research/02_feature_engineering/docs/plan.md`. La entrada silver se conserva sin modificar; la fase 6 aprobada genera y valida las dos salidas gold. El manifiesto documenta fuentes y límites de disponibilidad. Gold contiene candidatos y la etiqueta `brote` (media histórica + 1,5 DE), sin estadísticas predictoras aprendidas con datos de prueba. `brote` y `umbral_brote_casos` son objetivo/metadato, no predictores.

### `data/reference/` — catálogos que casi no cambian
```
reference/
├── catalogo_ubigeos_piura.csv   # provincia, distrito y UBIGEO
└── distritos_piura_coords.csv   # 65 centroides; se cruza con el catálogo
```
**Va acá:** tablas maestras chicas que usan varios notebooks (catálogos, diccionarios de códigos, listas de distritos). A diferencia de bronze/silver/gold, esta carpeta **sí se puede subir a Git** porque es chica y cambia poco — es la excepción a la regla de "data/ no se versiona".

---

## 3. `src/denguekay/` — el motor del proyecto

Cada subpaquete tiene sus tests en `tests/<subpaquete>/`.

### `config/`
```
config/
└── paths.py        # ROOT, DATA, GOLD, CONFIG (configs/config.yaml), MODELS, STORAGE...: todas las rutas
```
**Va acá:** cualquier ruta nueva. Nada de rutas absolutas en el código.

### `data/` — calendario, carga, ingesta, procesamiento y validación
```
data/
├── calendar.py      # mmwr_epi_week(): numeración compartida domingo-sábado
├── keys.py          # normalización de nombres de distrito y de la Sala
├── loading.py       # load_integrated(): lee silver/integrado, valida el panel, ubigeo como string
├── seasons.py       # temporadas epidemiológicas del panel
├── ingestion/
│   ├── openmeteo.py            # clima diario de Open-Meteo por distrito
│   ├── gadm_districts.py       # límites distritales GADM y centroides
│   ├── drive_download.py       # descarga desde Google Drive (reemplaza drive.mount de Colab)
│   └── minsa_sala_scraper.py   # series distrito-año de la Sala Situacional MINSA/DGE
├── processing/
│   ├── weekly_aggregation.py   # diario -> semanal por distrito
│   ├── socio_interpolation.py  # interpolación 2017-2025
│   ├── epi_cases.py            # Excel epidemiológico (un caso por fila) -> silver semanal
│   ├── epi_sala.py             # normalización y conciliación de la Sala
│   └── merge.py                # merges meteo + socio + epi y relleno selectivo
└── validation/
    ├── integrated_expectations.py  # cobertura y validación del integrado + suite GX silver_integrado
    ├── gold_expectations.py        # suite GX gold_h2/gold_h4 (esquema, llave, rangos, sin fuga temporal)
    ├── gx_quality.py               # contexto GX, ejecución de suites, Data Docs y CLI
    └── forecast_contract.py        # origen temporal y disponibilidad al pronosticar
```
**Va acá:** una función que hable con una API o haga scraping (`ingestion/`); limpieza, agregación, interpolación o joins (`processing/`); cualquier comprobación de rangos, nulos, duplicados o conteos (`validation/`, un archivo por dataset: `<dataset>_expectations.py`). Las suites de GX se definen en código; `great_expectations/gx/` lo regenera GX y no se versiona. Guía: `docs/modeling/mlflow_great_expectations.md`.

La auditoría de la corrección del calendario está en `research/02_feature_engineering/docs/correccion_calendario.md`. El resto del EDA (estilo, calidad, objetivo, clima, socio) está congelado en `research/01_eda/code/`; un análisis nuevo va en `research/`, no en el paquete.

### `features/` — variables del modelo
```
features/
├── history_calendar.py      # historia propia y calendario (fase 2 del feature engineering)
├── neighbors.py             # contexto espacial y provincial/regional rezagado (fase 3)
├── spatial.py               # distancias entre centroides y pesos espaciales
├── climate.py               # ventanas climáticas y climatología ajustada por corte (fase 4)
├── sociodemographics.py     # referencia 2017, demografía anual y eje urbano por fold (fase 5)
├── outbreak_label.py        # regla de semana elevada con historia previa; umbral para semanas fuera del panel
├── gold.py                  # integración y validación de gold; persiste solo h=2/4, construye h=1..6 en memoria
├── model_input_contract.py  # candidatos, exclusiones y auditoría de traspaso (fase 7)
├── variant_registry.py      # lista cerrada de variantes A/B del estudio de FE
└── onset_features.py        # variables B1–B5 en memoria desde el estado de la semana de origen
```
**Va acá:** el feature engineering. Las variables nuevas se calculan en memoria con un test de no fuga; si una entra a la configuración final se propone el cambio en `gold.py` y el equipo regenera gold con el notebook 10.

### `model/` — entrenamiento
```
model/
├── train.py                 # cortes temporales y XGBoost de ambos objetivos
├── device.py                # elige GPU NVIDIA (CUDA) o CPU para XGBoost según config.yaml
├── tracking.py              # registra cada reporte de experimento en MLflow (runs anidados)
├── horizon_strategies.py    # matrices h=1..6 en memoria y estrategias E1/E2/E3
├── probabilistic_output.py  # formulaciones S1–S5 (conteo, base_margin, binomial negativa, calibración)
├── future_rows.py           # filas futuras en memoria, sin fuga ni escritura en data/
├── frozen_configs.py        # configuraciones congeladas V1/V2 y su fingerprint() de comportamiento (D1)
└── variable_dictionary.py   # diccionario de las variables finales (genera docs/modeling/diccionario_variables.md)
```

### `evaluation/` — métricas y protocolos
```
evaluation/
├── metrics.py               # métricas de conteos y alertas
├── compact_validation.py    # calibra umbrales con temporadas previas (protocolo de V0)
├── protocol.py              # protocolo preregistrado del estudio multi-horizonte
├── acceptance.py            # umbrales de aceptación HU0007-4 sobre métricas guardadas
├── episodes.py              # diagnóstico de errores (estudio de arquitectura, fase 1)
├── onsets.py                # inicios limpios, controles y perfiles previos (estudio de FE, fase 1)
├── variants.py              # envoltura del estudio de FE e hiperparámetros sobre E3·S4_s2
├── tuning.py                # preregistro, espacio, objetivo y estudio TPE (HU0007-3)
├── climate_complement.py    # complemento preregistrado: clima de gold (A3) sobre la configuración final
└── cache.py                 # caché de cálculos caros con huella de datos, config y código
```
**Va acá:** la lógica compartida de evaluación (split, métricas, protocolos) que usa el producto o un estudio futuro. Las ablaciones y los diagnósticos lineales están congelados en `research/`.

### `db/`, `serving/` y `pipelines/`
```text
src/denguekay/db/
├── settings.py               # DATABASE_URL desde .env o entorno
├── session.py                # motores, claves foráneas, transacciones y UPSERT portable
├── models.py                 # esquema OE2 (docs/backend/ddl_oe2.sql) portable
├── export_migration_sql.py   # evidencia alembic upgrade --sql sin conexión
└── migrations/               # revisiones Alembic; 0003_oe2 es el esquema vigente
src/denguekay/serving/
├── load_data.py              # ingesta: provincia, distrito, calendario, observaciones
├── settings.py               # horizontes, variantes y selección experimental (config.yaml)
├── parameters.py             # lectura de parametro_sistema (autoridad de umbrales y cortes)
├── storage.py                # puerto Storage + adaptador local models/storage/
├── protocol.py               # importa y verifica los resultados temporales de Rosa
├── models.py                 # ajuste final con train.py y registro de versiones
├── artifacts.py              # booster en Storage, verificación SHA-256 e inferencia
├── risk.py                   # nivel de riesgo y cambio de alerta
├── inference.py              # vector desde la BD, UPSERT de predicciones, alertas, OOS
└── publish.py                # CLI: carga, ajuste, MLflow, versiones, OOS e inferencia
src/denguekay/pipelines/
└── weekly_update.py          # actualización selectiva del integrado (la usa el notebook 09)
```

## 3b. `apps/api/` — la API

```text
apps/api/                     # FastAPI: rutas de la Tabla 2 del documento OE2
├── main.py                   # create_app() y app (uvicorn apps.api.main:app)
├── dependencies.py, errors.py, queries.py, cache.py, openapi.py
├── schemas.py                # esquemas Pydantic (contrato; nombres en español, D2)
├── routers/                  # reference, data, surveillance, models y admin
└── tools/                    # benchmark.py, export_openapi.py, smoke_test.py
tests/
├── backend_support.py, serving_support.py, equivalence_support.py
├── db/, serving/, api/       # tests del backend
├── test_equivalence.py       # guardas de equivalencia de la reestructuración
├── test_layout.py            # sin restos del paquete src y dependencias en un solo sentido
└── fixtures/
    ├── backend/              # filas reales copiadas de silver/gold/Sala, con procedencia
    └── equivalence/          # línea base: predicciones V1/V2, esquemas, prueba de humo
docs/backend/                 # especificación OE2, desviaciones, operación y contrato
└── evidencia/                # SQL de la migración, prueba de humo TB1 (versionado)
models/storage/               # artefactos (buckets modelos/geodatos/reportes); no se versiona
models/serving/               # BD SQLite y ejecuciones locales; no se versionan
```

El esquema y la API siguen `docs/backend/especificacion_oe2.md` y `ddl_oe2.sql`;
toda diferencia está en `docs/backend/desviaciones_oe2.md`. El backend solo lee
`data/`. Cargas, inferencias, publicaciones y activaciones quedan como filas de
`ejecucion` (tipo + detalle). Las fixtures contienen datos agregados reales y
permiten ejecutar pruebas sin descargar todo el panel; sus metadatos documentan
la selección y los hashes de origen.
Las fixtures de fase 2 incluyen semanas temporales continuas, una muestra de
entrenamiento, referencia censal y predicciones OOS con métricas originales;
`procedencia_fase2.json` documenta su selección. Los cierres de fase 2 y sus
verificaciones SQLite/PostgreSQL viven en `docs/backend/fase2_*`.
El contrato y la evidencia de fase 3 viven en `docs/backend/contrato_api.md`,
`fase3_api.md`, `fase3_verificacion.json` y `openapi.json`. La copia SQLite
de verificación HTTP queda en `models/serving/fase3.sqlite`, sin versionar.
Fase 4: `docs/backend/arquitectura.md`, `decisiones_tecnicas.md`,
`trazabilidad_hu.md`, `fase4_calidad.md`, `fase4_verificacion.json` y los reportes `benchmark_*.json` documentan
la implementación y mediciones reales. La copia de benchmark SQLite vive en
`models/serving/fase4.sqlite`; las mediciones locales por defecto van en
`models/serving/benchmark.json`. `.github/workflows/backend.yml` ejecuta la
suite completa con fixtures versionadas, sin descargar gold/silver ni desplegar:
en Linux, Windows y macOS sobre SQLite, y en Linux contra un servicio PostgreSQL 18
desechable (`denguekay_pruebas`), que falla si las pruebas de PG se omiten.

---

## 4. `pipelines/notebooks/` — pipeline de datos, numerados en orden de ejecución

```
pipelines/notebooks/
├── 01_ingesta_distritos.ipynb
├── 02_ingesta_meteo.ipynb
├── 03_bronze_to_silver_meteo.ipynb
├── 04_ingesta_socio.ipynb
├── 05_bronze_to_silver_socio.ipynb
├── 06_ingesta_epi.ipynb
├── 07_bronze_to_silver_epi.ipynb
├── 08_silver_merge_meteo_socio.ipynb
├── 09_silver_merge_epi.ipynb
└── 10_silver_to_gold.ipynb      # genera y valida gold (antes notebooks/22_fe_integracion.ipynb, D3)
```

Los notebooks 01–09 escriben bronze, silver y el integrado; el 10 regenera gold. Importan el paquete
instalado (`pip install -e .`), así que no dependen de la carpeta desde la que se abren. Los notebooks
de investigación (los antiguos 10–21 y 23–35) están en `research/<estudio>/notebooks/` con su
numeración original:

| Notebooks | Estudio |
|---|---|
| 10–16 | `research/01_eda/` (EDA, Hito 2) |
| 17–21, 23 | `research/02_feature_engineering/` |
| 24–30 | `research/03_first_models_and_ablations/` |
| 31 | `research/04_horizon_architecture/` |
| 32–35 | `research/05_fe_hyperparameters/` |

Cada estudio tiene un README con su pregunta, su decisión, la versión de modelo resultante y el tag
desde el que se reproduce. No se vuelven a correr en `main` ni en el CI.

**Va acá:** un notebook nuevo del pipeline, con un número que refleje en qué paso entra (un notebook de análisis va en el estudio de `research/` al que pertenece). Si agregas un paso intermedio, usa notación tipo `04b_` en vez de renumerar todo lo que sigue.

Cada notebook debería poder leerse como una bitácora corta: "cargo tal cosa → llamo tal función de `denguekay` → guardo el resultado → imprimo una verificación". Si un notebook empieza a crecer con lógica pesada pegada en las celdas, esa lógica probablemente debería moverse a `src/denguekay/`.

Para actualizaciones incrementales del dataset ya consolidado, usar
`python -m denguekay.pipelines.weekly_update --input ... --output ...`. El módulo
detecta componentes incompletos por `ubigeo`/año/semana y llama solo a las
fuentes necesarias. El CSV lateral `<dataset>.coverage.csv` diferencia un
cero epidemiológico ya verificado de un cero en una fila nueva sin cobertura.
El notebook 09 reconstruye la base histórica y delega la salida final a este
módulo.

---

## 5. `models/` y `docs/`

- **`models/`**: modelos entrenados serializados; `models/experimentos/` guarda JSON de XGBoost y predicciones por fold. Los artefactos generados no se suben a Git.
- **`docs/`**: documentos de la tesis en sí (Acta Constitucional, Plan de Dirección, este mismo archivo). Estos **sí se versionan** en Git porque son texto y chicos.
- **`docs/modeling/`**: lo que sigue usando el producto: `mlflow_great_expectations.md` (guía de MLflow y GX), `diccionario_variables.md` (generado por `python -m denguekay.model.variable_dictionary`) y `metricas/validacion_temporal_compacta.json`, que lee serving para V0 (pasa a `models/registry/v0/` en la fase 4). Las predicciones por fila quedan en `models/experimentos/` (no versionado).
- **`docs/decisions/`**: decisiones de arquitectura del repositorio (ADR).
- **`research/<estudio>/docs/`**: informes, `metricas/` y `figuras/` de cada estudio cerrado (EDA, feature engineering, primeros modelos y ablaciones, arquitectura multi-horizonte, FE e hiperparámetros). La referencia PDF aportada por Rosa está en `research/02_feature_engineering/docs/references/`. La skill local `.codex/skills/feature-engineering-dengue/` y `AGENTS.md` describen el flujo de Codex.
---

## 6. `.gitignore` — qué NO se sube al repo

```gitignore
data/bronze/
data/silver/
data/gold/*
!data/gold/.gitkeep
trazabilidad_scraper_dengue_piura_2025/
trazabilidad_scraper_dengue_piura_2025.zip
models/*.pkl
models/*.joblib
models/experimentos/
models/serving/
__pycache__/
*.ipynb_checkpoints/
.env
mlflow.db
mlartifacts/
mlruns/
great_expectations/gx/
```

`mlflow.db`, `mlartifacts/` y `great_expectations/gx/` se regeneran al correr los experimentos y las validaciones; lo versionado es el código que los produce.

`data/gold/.gitkeep` se versiona solo para que la carpeta vacía exista en todos los clones. `data/reference/` **no** está en esta lista a propósito — esa sí se versiona porque es chica y todos la necesitan para reproducir el pipeline sin tener que descargar nada primero.

---

## 7. Checklist rápido: "tengo un archivo nuevo, ¿dónde va?"

| Es un... | Va en... |
|---|---|
| Script que descarga de una API/scraping | `src/denguekay/data/ingestion/` |
| Función que limpia, agrega o mergea datos | `src/denguekay/data/processing/` |
| Chequeo de calidad de datos | `src/denguekay/data/validation/` |
| Variable o feature engineering del modelo | `src/denguekay/features/` |
| Código de entrenamiento de modelo | `src/denguekay/model/` |
| Métrica o protocolo de evaluación | `src/denguekay/evaluation/` |
| ORM, conexión o migración de la BD | `src/denguekay/db/` |
| Carga/predicción/publicación del backend | `src/denguekay/serving/` |
| Router o esquema de la API | `apps/api/` (herramientas de línea de comandos en `apps/api/tools/`) |
| Paso del pipeline como módulo (no notebook) | `src/denguekay/pipelines/` |
| Ruta nueva del proyecto | `src/denguekay/config/paths.py` |
| Documentación y evidencia del backend | `docs/backend/` |
| Muestra real para pruebas del backend | `tests/fixtures/backend/` |
| Guarda de equivalencia de la reestructuración | `tests/test_equivalence.py` (línea base en `tests/fixtures/equivalence/`) |
| Test de un módulo del paquete | `tests/<subpaquete>/test_<módulo>.py` |
| Notebook que orquesta un paso del pipeline | `pipelines/notebooks/`, numerado |
| Dato tal cual vino de la fuente | `data/bronze/<fuente>/` |
| Dato limpio de una sola fuente | `data/silver/` |
| Merge de varias fuentes silver (sin features) | `data/silver/integrado/` |
| Dataset con feature engineering, listo para modelar | `data/gold/` |
| Catálogo chico que casi no cambia | `data/reference/` (sí se sube a Git) |
| Estudio nuevo (análisis o experimento) | `research/06_<nombre>/` con `README.md`, `notebooks/`, `code/`, `tests/` y `docs/`; importa el producto, nunca al revés |
| EDA congelado (notebooks, código, figuras, cifras) | `research/01_eda/` |
| Modelo entrenado | `models/` |
| Suite de Great Expectations | `src/denguekay/data/validation/<dataset>_expectations.py` |
| Registro de experimentos en MLflow | `src/denguekay/model/tracking.py` (no crear otro tracker) |
| Documento de tesis / explicación de arquitectura | `docs/` |
| Plan y hallazgos de feature engineering (congelado) | `research/02_feature_engineering/docs/` |
| Instrucciones de Codex y skill local | `AGENTS.md` y `.codex/skills/` |
| Convenciones de ramas, commits, PR y tags | `CONTRIBUTING.md` |
| Decisión de arquitectura del repo (ADR) | `docs/decisions/NNNN-<tema>.md` |

---

## 8. Pendientes conocidos (no perder de vista)

- **Variables con un solo año censal**: `socio_interpolation.py` las excluye del dataset final; solo interpola fracciones con valores en ambos extremos, 2017 y 2025.
- **Actualización 2026+**: el actualizador extrapola las fracciones desde esos extremos y acota sus valores a `[0, 1]`; extrapola población con la misma pendiente. Es un supuesto metodológico hasta contar con nuevas proyecciones.
- **Semanas de la Sala fuera del calendario del modelo**: se conservan en `data/silver/epi_sala_semanal.csv` y se reportan, sin asignar sus casos a otra semana.
