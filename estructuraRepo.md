# Estructura del repositorio — Tesis Dengue Piura

Esta guía explica cómo está organizado el repo y **dónde va cada archivo nuevo** que agreguemos (código, datos, modelos, docs). La idea es que cualquiera del equipo (o alguien que se sume después) sepa en 30 segundos dónde poner algo sin tener que preguntar.

## Árbol completo

```
tesis-dengue-piura/
├── README.md
├── .gitignore
├── environment.yml            # o requirements.txt
├── config/
│   └── config.yaml
│
├── data/
│   ├── bronze/
│   ├── silver/
│   ├── gold/
│   └── reference/
│
├── src/
│   ├── ingestion/
│   ├── processing/
│   ├── validation/
│   ├── modeling/
│   └── utils/
│
├── notebooks/
├── great_expectations/
├── models/
└── docs/
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
└── epi/                     # Excel o scrape crudo de la Sala Situacional MINSA
```
**Va acá:** cualquier archivo nuevo que baje de una API, scraping o que alguien te pase como fuente original. Si dudas si algo es "bronze", pregúntate: ¿esto es exactamente lo que devolvió la fuente, sin que yo lo haya tocado? Si sí, es bronze.

### `data/silver/` — limpio, normalizado, **un dataset por fuente**
```
silver/
├── meteo_semanal_distrital.csv
├── socio_anual.csv
└── epi_piura_semanal.csv
```
Acá ya pasaron por: normalización de nombres de distrito (`distrito_key`), tipos de dato correctos, deduplicación, y (idealmente) una corrida de Great Expectations. Todavía **no están mergeados entre sí**.

**Va acá:** la salida de cualquier notebook `0X_bronze_to_silver_*`. Si agregas una fuente nueva (ej. datos de un hospital, otro sensor climático), su versión limpia va acá con su propio nombre de archivo.

### `data/gold/` — listo para modelar
```
gold/
├── dataset_final_piura_2017_2025.csv     # meteo + socio
└── dataset_modelo_piura_2017_2025.csv    # meteo + socio + epi (el que usa el modelo)
```
**Va acá:** el resultado de cualquier merge entre fuentes silver. Si agregas una versión nueva (ej. con features adicionales, o extendida a 2026), no sobrescribas el archivo viejo — nómbralo distinto (`dataset_modelo_piura_2017_2026.csv`) para poder comparar versiones del dataset.

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
└── scrape_minsa_dengue.py     # scraping de la Sala Situacional (pendiente)
```
**Va acá:** cualquier función que hable con una API, descargue un archivo, o haga scraping. Regla práctica: si la función usa `requests`, `BeautifulSoup`, o un SDK de algún servicio externo, va acá.

### `src/processing/`
Transformación y merge de datos ya descargados.
```
processing/
├── agregacion_semanal.py      # diario -> semanal por distrito
├── socio_interpolacion.py     # interpolación 2017-2025
└── merge_datasets.py          # merges meteo+socio, +epi
```
**Va acá:** funciones de limpieza, agregación, interpolación, joins. Si el modelo nuevo necesita, por ejemplo, calcular lags (temperatura de la semana -1, -2, -3), esa función va en un archivo nuevo acá, ej. `processing/features_lag.py`.

### `src/validation/`
Suites de Great Expectations (o los `assert` livianos, según lo que decidamos usar).
```
validation/
└── expectations_meteo.py
```
**Va acá:** cualquier función `validar_*()` que revise rangos, nulos, duplicados, conteos esperados. Un archivo por dataset que valides (`expectations_socio.py`, `expectations_epi.py`, `expectations_gold.py`).

### `src/modeling/` *(la vamos a necesitar pronto)*
```
modeling/
├── features.py         # construcción de features finales para el modelo
├── train.py             # entrenamiento (XGBoost, etc.)
└── evaluate.py           # métricas, validación cruzada
```
**Va acá:** todo lo relacionado a entrenar y evaluar modelos. Cuando prueben un modelo nuevo (ej. otro algoritmo, otra arquitectura), la función de entrenamiento va en `train.py` o en un archivo nuevo si es sustancialmente distinta (`train_xgboost.py`, `train_lstm.py`), pero la lógica compartida (split train/test, métricas) se queda en un solo lugar para no repetirla.

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
├── 05_gold_merge_meteo_socio.ipynb
├── 06_gold_merge_epi.ipynb
├── 07_eda.ipynb
├── 08_validacion_ge.ipynb
├── 09_actualizacion_incremental.ipynb   # pendiente de diseño
└── 10_entrenamiento_modelo.ipynb        # pendiente
```

**Va acá:** cualquier notebook nuevo, con un número que refleje en qué paso del pipeline entra. Si agregas un paso intermedio, usa notación tipo `04b_` en vez de renumerar todo lo que sigue.

Cada notebook debería poder leerse como una bitácora corta: "cargo tal cosa → llamo tal función de `src/` → guardo el resultado → imprimo una verificación". Si un notebook empieza a crecer con lógica pesada pegada en las celdas, esa lógica probablemente debería moverse a `src/`.

---

## 5. `models/` y `docs/`

- **`models/`**: modelos entrenados serializados (`.pkl`, `.joblib`, checkpoints). No se sube a Git si pesan mucho — mismo criterio que `data/`.
- **`docs/`**: documentos de la tesis en sí (Acta Constitucional, Plan de Dirección, este mismo archivo). Estos **sí se versionan** en Git porque son texto y chicos.

---

## 6. `.gitignore` — qué NO se sube al repo

```gitignore
data/bronze/
data/silver/
data/gold/
models/*.pkl
models/*.joblib
__pycache__/
*.ipynb_checkpoints/
.env
```

`data/reference/` **no** está en esta lista a propósito — esa sí se versiona porque es chica y todos la necesitan para reproducir el pipeline sin tener que descargar nada primero.

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
| Dataset final para modelar | `data/gold/` |
| Catálogo chico que casi no cambia | `data/reference/` (sí se sube a Git) |
| Modelo entrenado | `models/` |
| Documento de tesis / explicación de arquitectura | `docs/` |

---

## 8. Pendientes conocidos (no perder de vista)

- **`socio_interpolacion.py`**: para las variables con un solo año censal (solo 2017 o solo 2025), el código actual las deja constantes en todo el rango 2017-2025. Falta decidir si se excluyen del dataset final o se mantienen así documentado como supuesto metodológico.
- **Actualización incremental (2026+)**: falta diseñar `scrape_minsa_dengue.py`, el notebook `09_actualizacion_incremental.ipynb`, y sobre todo cómo extender la data sociodemográfica más allá de 2025 (no hay censo nuevo para interpolar contra).