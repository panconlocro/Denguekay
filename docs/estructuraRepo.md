# Estructura del repositorio — Tesis Dengue Piura

Esta guía explica cómo está organizado el repo y **dónde va cada archivo nuevo** que agreguemos (código, datos, modelos, docs). La idea es que cualquiera del equipo (o alguien que se sume después) sepa en 30 segundos dónde poner algo sin tener que preguntar.

## Árbol completo

```
tesis-dengue-piura/
├── README.md
├── CLAUDE.md                  # contexto y reglas para Claude Code
├── _claude_setup/             # configuración versionada para Claude Code
├── AGENTS.md                  # contexto y reglas para Codex
├── .codex/skills/             # workflows de Codex (feature engineering)
├── .gitignore
├── environment.yml            # o requirements.txt
├── config/
│   └── config.yaml
│
├── data/
│   ├── bronze/
│   ├── silver/
│   │   └── integrado/     # merges entre fuentes, sin features
│   ├── gold/              # dos datasets por horizonte y manifiesto de fase 6
│   └── reference/
│
├── src/
│   ├── ingestion/
│   ├── processing/
│   ├── validation/
│   ├── eda/
│   ├── modeling/
│   ├── utils/
│   └── update_dataset_module.py
│
├── notebooks/
├── great_expectations/        # contexto de GX generado (gx/ no se versiona)
├── models/
├── mlflow.db                  # tracking de MLflow (generado, no se versiona)
├── mlartifacts/               # artefactos de MLflow (generado, no se versiona)
└── docs/
    ├── eda/
    ├── feature_engineering/   # plan, evidencia, decisiones y PDF de referencia
    └── modeling/              # diseño y resultados del entrenamiento
```

---

## 1. La regla de oro: `src/` vs `notebooks/`

Antes de explicar carpeta por carpeta, esta es la decisión que más se repite y la que más dudas genera:

> **Si el código lo volverías a necesitar en otro notebook, o tiene más de ~10 líneas de lógica (loops, reintentos, parsing, cálculos), va en `src/`. Si es "cargar esto, llamar esa función, mostrar el resultado", se queda en el notebook.**

- `src/` = el motor. Funciones puras, reutilizables, testeables. No saben nada de Drive, de Colab, ni de en qué orden se ejecutan.
- `notebooks/` = el tablero de control. Pocas líneas, importan funciones de `src/`, deciden el orden, muestran resultados y verificaciones puntuales (`print`, `.describe()`, gráficos exploratorios).

Nada de lógica se duplica entre los dos. Si corriges un bug, lo corriges en un solo lugar (`src/`), no en cinco notebooks distintos.

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

**`silver/integrado/`:** el resultado de cualquier merge entre fuentes silver (notebooks `08_silver_merge_*` y `09_silver_merge_*`, y el actualizador `src/update_dataset_module.py`). Siguen siendo datos limpios sin features derivadas, por eso **no van en gold**. Si agregas una versión nueva (ej. extendida a 2026), no sobrescribas el archivo viejo — nómbralo distinto (`meteo_socio_epi_piura_2017_2026.csv`) para poder comparar versiones.

### `data/gold/` — solo el dataset con feature engineering
```
gold/
├── .gitkeep
├── meteo_socio_epi_piura_2017_2025_h2_gold.csv
├── meteo_socio_epi_piura_2017_2025_h4_gold.csv
└── manifest_fase6.json
```
**Va acá:** únicamente el dataset con el feature engineering ya aplicado, listo para entrenar el modelo. Un merge entre fuentes **no** es gold: eso va en `silver/integrado/`.

El plan de construcción está en `docs/feature_engineering/plan.md`. La entrada silver se conserva sin modificar; la fase 6 aprobada genera y valida las dos salidas gold. El manifiesto documenta fuentes y límites de disponibilidad. Gold contiene candidatos y la etiqueta `brote` (media histórica + 1,5 DE), sin estadísticas predictoras aprendidas con datos de prueba. `brote` y `umbral_brote_casos` son objetivo/metadato, no predictores.

### `data/reference/` — catálogos que casi no cambian
```
reference/
└── distritos_piura_coords.csv   # 65 distritos, ubigeo, lat/lon
```
**Va acá:** tablas maestras chicas que usan varios notebooks (catálogos, diccionarios de códigos, listas de distritos). A diferencia de bronze/silver/gold, esta carpeta **sí se puede subir a Git** porque es chica y cambia poco — es la excepción a la regla de "data/ no se versiona".

---

## 3. `src/` — el motor del proyecto

### `src/ingestion/`
Una función (o archivo) por fuente de datos externa.
```
ingestion/
├── fetch_openmeteo.py         # descarga clima de Open-Meteo
├── fetch_distritos_gadm.py    # descarga límites distritales + centroides
└── scrape_minsa_dengue.py     # extracción semanal de la Sala Situacional
```
**Va acá:** cualquier función que hable con una API, descargue un archivo, o haga scraping. Regla práctica: si la función usa `requests`, `BeautifulSoup`, o un SDK de algún servicio externo, va acá.

### `src/processing/`
Transformación y merge de datos ya descargados.
```
processing/
├── agregacion_semanal.py      # diario -> semanal por distrito
├── socio_interpolacion.py     # interpolación 2017-2025
├── epi_sala.py                # normalización y conciliación de la Sala
└── merge_datasets.py          # merges y relleno selectivo
```
**Va acá:** funciones de limpieza, agregación, interpolación, joins. Si el modelo nuevo necesita, por ejemplo, calcular lags (temperatura de la semana -1, -2, -3), esa función va en un archivo nuevo acá, ej. `processing/features_lag.py`.

### `src/validation/`
Suites de Great Expectations y comprobaciones estrictas (`assert`/`raise`) de los datasets.
```
validation/
├── expectations_meteo.py
├── expectations_integrado.py  # cobertura y validación del integrado + suite GX silver_integrado
├── expectations_gold.py       # suite GX gold_h2/gold_h4 (esquema, llave, rangos, sin fuga temporal)
├── calidad_gx.py              # contexto GX, ejecución de suites, Data Docs y CLI
└── contrato_pronostico.py     # origen temporal y disponibilidad al pronosticar
```
Las suites se definen en código; `great_expectations/gx/` es el contexto que GX regenera (suites, resultados y Data Docs HTML) y no se versiona. Guía: `docs/modeling/mlflow_great_expectations.md`.
**Va acá:** cualquier función `validar_*()` que revise rangos, nulos, duplicados, conteos esperados. Un archivo por dataset que valides (`expectations_socio.py`, `expectations_epi.py`, `expectations_integrado.py`).

### `src/eda/`
Funciones reutilizables del análisis exploratorio (solo lectura sobre `data/`).
```
eda/
├── carga.py      # cargar_integrado(): lee silver/integrado, valida el panel, ubigeo como string
├── estilo.py     # estilo de gráficos, guardar_figura(), guardar_metricas()
├── calidad.py    # chequeos de integridad: calendario MMWR, reglas de consistencia, extremos (fase 1)
├── objetivo.py   # concentración, episodios y definiciones candidatas de brote, solo en memoria (fase 2)
├── temporal.py   # autocorrelación, perfil estacional, temporadas y líneas base ingenuas (fase 3)
├── espacial.py   # distancias entre centroides, pesos espaciales, I de Moran, estado rezagado de vecinos (fase 4)
├── clima.py      # anomalías climáticas, correlación con rezagos y bootstrap por bloques (fase 5)
└── socio.py      # VIF, componentes principales, Spearman con bootstrap y límites de embudo (fase 6)
```
**Va acá:** helpers de carga, estadística y gráficos que se repiten entre notebooks de EDA (ej. correlación cruzada con rezagos, climatología y anomalías, curvas de concentración). **No va acá:** nada que construya features para el modelo (eso es `src/modeling/features.py`) ni nada que escriba en `data/`.

### `src/modeling/`
```
modeling/
├── __init__.py
├── historia_calendario.py   # candidatos causales de historia propia y calendario (fase 2)
├── vecinos_jerarquia.py     # contexto espacial y provincial/regional rezagado (fase 3)
├── clima.py                 # ventanas climáticas y climatología ajustada por corte (fase 4)
├── diagnostico.py           # ridge fijo compartido en ablaciones exploratorias
├── diagnostico_clima.py     # ablación temporal exploratoria del clima (fase 4)
├── sociodemografia.py       # referencia 2017, demografía anual y eje urbano por fold (fase 5)
├── diagnostico_socio.py     # ablación temporal exploratoria de variantes fijas y anuales (fase 5)
├── etiqueta_brote.py        # regla de semana elevada con historia previa
├── features.py              # integración y validación de gold para h=2/4 (fase 6)
├── contrato_xgboost.py      # candidatos, exclusiones y auditoría de traspaso (fase 7)
├── dispositivo.py           # elige GPU NVIDIA (CUDA) o CPU para XGBoost según config.yaml
├── evaluate.py              # métricas de conteos y alertas
├── train.py                 # cortes temporales y primer XGBoost de ambos objetivos
├── ablacion_espacial.py     # compara bloques de vecinos y jerarquía en validación
├── ablacion_clima.py        # compara clima observado y anomalías ajustadas por fold
├── ablacion_sociodemografica.py # compara referencia fija y anual reconstruida
├── ablacion_fracciones.py   # criba individualmente 15 fracciones fijas y anuales
├── ablacion_poblacion_sin_seguro.py # compara dos rasgos censales solos y juntos
├── validacion_temporal_compacta.py # calibra umbrales con temporadas previas
└── seguimiento_mlflow.py    # registra cada reporte de experimento en MLflow (runs anidados)
```
**Va acá:** el feature engineering para el modelo y todo lo relacionado con entrenamiento y evaluación. `features.py` integra los candidatos de fase 6; `train.py` entrena los dos primeros objetivos XGBoost, `evaluate.py` contiene métricas compartidas, `ablacion_espacial.py` contrasta vecinos y jerarquía, `ablacion_clima.py` contrasta clima observado y anomalías, `ablacion_sociodemografica.py` compara bloques demográficos, `ablacion_fracciones.py` criba las 15 fracciones una por una, `ablacion_poblacion_sin_seguro.py` compara las dos candidatas fijas por separado y juntas, y `validacion_temporal_compacta.py` calibra umbrales con temporadas previas y compara matrices pequeñas. Cuando prueben un modelo nuevo, la lógica compartida (split train/test, métricas) se conserva en un solo lugar. `seguimiento_mlflow.py` registra en MLflow el reporte de cualquier experimento con la forma estándar `horizontes → variantes → folds`.

### `src/utils/`
Funciones chicas que usa más de un módulo.
```
utils/
└── keys.py    # normalizar(), separar_camel(), semana_epi()
```
**Va acá:** helpers genéricos sin dueño claro — si una función la usan tanto `ingestion/` como `processing/`, vive acá para evitar que ambos la dupliquen.

---

## 4. `notebooks/` — orquestación, numerados en orden de ejecución

```
notebooks/
├── 01_ingesta_distritos.ipynb
├── 02_ingesta_meteo.ipynb
├── 03_bronze_to_silver_meteo.ipynb
├── 04_ingesta_socio.ipynb
├── 05_bronze_to_silver_socio.ipynb
├── 06_ingesta_epi.ipynb
├── 07_bronze_to_silver_epi.ipynb
├── 08_silver_merge_meteo_socio.ipynb
├── 09_silver_merge_epi.ipynb
├── 10_eda_integridad_calidad.ipynb
├── 11_eda_variable_objetivo.ipynb
├── 12_eda_temporal.ipynb
├── 13_eda_espacial.ipynb
├── 14_eda_clima.ipynb
├── 15_eda_sociodemografico.ipynb
├── 16_eda_sintesis.ipynb
├── 17_fe_contrato_objetivo.ipynb
├── 18_fe_historia_calendario.ipynb
├── 19_fe_vecinos_jerarquia.ipynb
├── 20_fe_clima.ipynb
├── 21_fe_sociodemografia.ipynb
├── 22_fe_integracion.ipynb
├── 23_fe_sintesis.ipynb
├── 24_modelado_xgboost_dos_objetivos.ipynb
├── 25_modelado_ablacion_espacial.ipynb
├── 26_modelado_ablacion_clima.ipynb
├── 27_modelado_ablacion_sociodemografica.ipynb
├── 28_modelado_ablacion_fracciones.ipynb
├── 29_modelado_ablacion_poblacion_sin_seguro.ipynb
└── 30_modelado_validacion_temporal_compacta.ipynb
```

Los notebooks `10`–`16` son el EDA (Hito 2, Data Understanding) y **leen** `silver/integrado/`; no escriben en `data/`. El notebook `17` audita el contrato temporal y el objetivo de la primera fase de feature engineering. El `18` construye y compara historia propia y calendario en memoria para la segunda fase. El `19` construye y audita vecinos y contexto provincial/regional rezagado. El `20` construye ventanas climáticas y compara su aporte en cortes temporales, con climatologías ajustadas antes de cada prueba. El `21` compara rasgos fijos de 2017 y anuales reconstruidos, con CP1 ajustado por fold. El `22` genera y valida gold por horizonte. El `23` audita los archivos persistidos, sintetiza variables y entrega el contrato de modelado. El `24` orquesta el primer XGBoost de conteos y alerta; el `25` compara bloques espaciales, el `26` compara clima con anomalías ajustadas por fold, el `27` compara demografía fija y anual reconstruida, el `28` criba las 15 fracciones individualmente, el `29` contrasta población censal fija y fracción sin seguro de 2017, solas y juntas, y el `30` evalúa matrices compactas con calibración progresiva. El plan y los criterios de cierre del FE están en `docs/feature_engineering/plan.md`.

**Va acá:** cualquier notebook nuevo, con un número que refleje en qué paso del pipeline entra. Si agregas un paso intermedio, usa notación tipo `04b_` en vez de renumerar todo lo que sigue.

Cada notebook debería poder leerse como una bitácora corta: "cargo tal cosa → llamo tal función de `src/` → guardo el resultado → imprimo una verificación". Si un notebook empieza a crecer con lógica pesada pegada en las celdas, esa lógica probablemente debería moverse a `src/`.

Para actualizaciones incrementales del dataset ya consolidado, usar
`python -m src.update_dataset_module --input ... --output ...`. El módulo
detecta componentes incompletos por `ubigeo`/año/semana y llama solo a las
fuentes necesarias. El CSV lateral `<dataset>.coverage.csv` diferencia un
cero epidemiológico ya verificado de un cero en una fila nueva sin cobertura.
El notebook 09 reconstruye la base histórica y delega la salida final a este
módulo.

---

## 5. `models/` y `docs/`

- **`models/`**: modelos entrenados serializados; `models/experimentos/` guarda JSON de XGBoost y predicciones por fold. Los artefactos generados no se suben a Git.
- **`docs/`**: documentos de la tesis en sí (Acta Constitucional, Plan de Dirección, este mismo archivo). Estos **sí se versionan** en Git porque son texto y chicos.
- **`docs/eda/`**: salidas del EDA, también versionadas (texto y figuras chicas): `hallazgos.md` (conclusiones por fase), `informe_eda.md` (síntesis final), `problemas_y_decisiones.md` (problemas de datos y decisiones pendientes, consolidados al cierre del EDA), `figuras/<fase>/` (PNG) y `metricas/<fase>.json` (cifras citadas en los hallazgos).
- **`docs/feature_engineering/`**: plan de fases, informes, `metricas/<fase>.json` y `figuras/<fase>/` sobre las variables del modelo; se versiona. Su subcarpeta `references/` conserva el PDF de investigación aportado por Rosa para futuras sesiones. La skill local `.codex/skills/feature-engineering-dengue/` y `AGENTS.md` describen el flujo de Codex. Ninguno contiene datos generados del panel.
- **`docs/modeling/`**: diseño y métricas versionadas de entrenamiento y evaluación temporal; las predicciones por fila quedan en `models/experimentos/`.

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
| Script que descarga de una API/scraping | `src/ingestion/` |
| Función que limpia, agrega o mergea datos | `src/processing/` |
| Chequeo de calidad de datos | `src/validation/` |
| Código de entrenamiento/evaluación de modelo | `src/modeling/` |
| Función chica usada por varios módulos | `src/utils/` |
| Notebook que orquesta un paso del pipeline | `notebooks/`, numerado |
| Dato tal cual vino de la fuente | `data/bronze/<fuente>/` |
| Dato limpio de una sola fuente | `data/silver/` |
| Merge de varias fuentes silver (sin features) | `data/silver/integrado/` |
| Dataset con feature engineering, listo para modelar | `data/gold/` |
| Catálogo chico que casi no cambia | `data/reference/` (sí se sube a Git) |
| Función reutilizable de análisis exploratorio | `src/eda/` |
| Notebook de EDA | `notebooks/`, rango `10_eda_*` a `16_eda_*` |
| Figura, cifra o conclusión del EDA | `docs/eda/` |
| Modelo entrenado | `models/` |
| Suite de Great Expectations | `src/validation/expectations_<dataset>.py` |
| Registro de experimentos en MLflow | `src/modeling/seguimiento_mlflow.py` (no crear otro tracker) |
| Documento de tesis / explicación de arquitectura | `docs/` |
| Plan y hallazgos de feature engineering | `docs/feature_engineering/` |
| Instrucciones de Codex y skill local | `AGENTS.md` y `.codex/skills/` |

---

## 8. Pendientes conocidos (no perder de vista)

- **Variables con un solo año censal**: `socio_interpolacion.py` las excluye del dataset final; solo interpola fracciones con valores en ambos extremos, 2017 y 2025.
- **Actualización 2026+**: el actualizador extrapola las fracciones desde esos extremos y acota sus valores a `[0, 1]`; extrapola población con la misma pendiente. Es un supuesto metodológico hasta contar con nuevas proyecciones.
- **Semanas de la Sala fuera del calendario del modelo**: se conservan en `data/silver/epi_sala_semanal.csv` y se reportan, sin asignar sus casos a otra semana.
