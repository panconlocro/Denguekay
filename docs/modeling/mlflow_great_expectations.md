# MLflow y Great Expectations en el entrenamiento

**Estado al 1 de octubre de 2026.** Este documento explica cómo quedaron integrados **MLflow** (seguimiento de experimentos) y **Great Expectations** (calidad de datos) en el flujo de modelado, cómo usarlos y qué falta. Implementa la migración propuesta en el [inventario](inventario_entrenamiento_mlflow.md) **sin cambiar el protocolo estadístico**: cortes temporales, hiperparámetros, criterios de selección y métricas siguen definidos en `src/modeling/`.

Todavía **no hay modelo final**. Por eso no se usa el *Model Registry* de MLflow: cada corrida queda como experimento exploratorio comparable con las demás.

## 1. Qué cambia al ejecutar un experimento

Antes, cada módulo `ejecutar_*` leía gold, entrenaba y escribía el JSON de métricas y las predicciones. Ahora, con los mismos comandos y notebooks:

```text
gold h2/h4 (+ silver integrado si el módulo lo usa)
  → auditar_traspaso()                      (igual que antes)
  → Great Expectations: suites silver_integrado, gold_h2, gold_h4
        ↳ si alguna expectativa falla, el experimento se detiene antes de entrenar
  → entrenamiento y evaluación              (igual que antes)
  → docs/modeling/metricas/*.json + models/experimentos/*   (igual que antes)
  → MLflow: run padre + runs por variante + runs por fold
```

Los siete módulos están instrumentados: `train` (primer XGBoost), `ablacion_espacial`, `ablacion_clima`, `ablacion_sociodemografica`, `ablacion_fracciones`, `ablacion_poblacion_sin_seguro` y `validacion_temporal_compacta`. Los notebooks 24–30 llaman a esas funciones con los valores por defecto, así que **también registran en MLflow sin cambiar una línea**.

Se comprobó que la instrumentación no altera resultados: con el mismo equipo, los siete JSON de métricas generados antes y después de los cambios son idénticos (ver §7).

## 2. Instalación

```powershell
.\.venv\Scripts\python -m pip install -r requirements.txt
```

`requirements.txt` agrega `mlflow>=3,<4` y `great_expectations>=1.5,<2`. Se probó con MLflow 3.16.1 y Great Expectations 1.23.2 sobre Python 3.13. Great Expectations suele tardar en dar soporte a la versión más nueva de Python: si `pip` falla con Python 3.14, usar 3.12 o 3.13 para el `.venv`.

## 3. Great Expectations (calidad de datos)

### 3.1 Archivos

| Archivo | Contenido |
|---|---|
| [`src/validation/expectations_gold.py`](../../src/validation/expectations_gold.py) | Suite `gold_h{h}` para cada gold por horizonte. |
| [`src/validation/expectations_integrado.py`](../../src/validation/expectations_integrado.py) | Además de las comprobaciones previas del actualizador, `expectativas_integrado_gx()` define la suite `silver_integrado`. |
| [`src/validation/calidad_gx.py`](../../src/validation/calidad_gx.py) | Abre el contexto de GX, registra las suites, valida, genera Data Docs y expone la CLI y `validar_entradas_modelado()`. |
| `great_expectations/gx/` | Contexto generado por GX: suites, checkpoints, resultados y Data Docs. **No se versiona** (ver §3.4). |

Las suites son **complementarias** a los controles estrictos que ya existían (`preparar_gold`, `auditar_traspaso`, `validate_complete`). Esos controles detienen el código con un error puntual; GX deja además un reporte declarativo, legible en HTML, que se adjunta a cada run de MLflow. Las suites solo **leen** `data/`.

### 3.2 Qué valida cada suite

**`silver_integrado`** (107 expectativas sobre el panel de 30 485 filas):

- Existen las columnas núcleo, climáticas, sociodemográficas y `casos_Dengue`, sin nulos.
- Llave `(ubigeo, anio, semana)` única; `ubigeo` de seis dígitos, perteneciente al catálogo `data/reference/catalogo_ubigeos_piura.csv`, con exactamente 65 distritos.
- `anio ≥ 2017`; `semana` entre 1 y 53; coordenadas dentro de una caja aproximada de Piura (lat −6,5 a −3,5; lon −81,5 a −79,0).
- Clima con rangos **físicamente plausibles**, no ajustados a los datos: temperaturas entre −10 y 45 °C con `temp_max ≥ temp_media ≥ temp_min`; precipitación y lluvia entre 0 y 1500 mm/semana con `lluvia ≤ precipitación`; humedad relativa entre 0 y 100 %; viento 0–200; radiación 0–350; ET0 0–100.
- Población ≥ 1, fracciones entre 0 y 1, casos ≥ 0.

**`gold_h2` y `gold_h4`** (92 expectativas cada una):

- Esquema **exacto**: las columnas coinciden con `columnas_gold(h, con_brote=True)`.
- Llave única, `ubigeo` válido y del catálogo, 65 distritos, `anio ≥ 2017`, `semana` 1–53.
- Objetivos: `casos_Dengue ≥ 0`, `umbral_brote_casos ≥ 0`, `brote ∈ {0, 1}`.
- **Sin fuga temporal**: `semana_inicio > origen_cierre` en toda fila con origen.
- Identificadores, objetivos, calendario y rasgos sociodemográficos sin nulos. Los predictores rezagados (casos, vecinos, jerarquía, clima) pueden ser nulos solo en el arranque de cada distrito: se exige al menos 95 % poblado (hoy los nulos son menos del 2 %; la comprobación exacta del arranque sigue en `preparar_gold`).
- Rangos: conteos ≥ 0, semanas positivas entre 0 y 4, seno/coseno entre −1 y 1, humedad 0–100, todas las fracciones 0–1, log-poblaciones > 0.

Con los datos actuales las tres suites pasan al 100 %.

### 3.3 Cómo ejecutarlas

Desde la raíz del repo:

```powershell
.\.venv\Scripts\python -m src.validation.calidad_gx             # silver integrado + gold h2/h4
.\.venv\Scripts\python -m src.validation.calidad_gx --sin-gold  # solo silver integrado
```

Imprime `[OK]` o `[FALLA]` por suite con los ejemplos inesperados, y sale con código 1 si algo falla. El reporte HTML queda en `great_expectations/gx/uncommitted/data_docs/local_site/index.html` (abrir con el navegador).

Conviene correrlo después de regenerar silver (notebook 09 o `src.update_dataset_module`) o gold (notebook 22). Los módulos de entrenamiento lo ejecutan solos antes de entrenar.

### 3.4 Por qué `great_expectations/gx/` no se versiona

GX reescribe sus archivos de configuración con identificadores nuevos en cada ejecución, lo que generaría cambios en Git sin contenido real. La **fuente de verdad son las suites en `src/validation/`**: el contexto se reconstruye solo la primera vez que se ejecuta cualquier validación.

### 3.5 Agregar o cambiar una expectativa

Editar la lista que devuelve `expectativas_gold()` o `expectativas_integrado_gx()` y agregar un caso a `tests/test_calidad_gx.py`. No ajustar los límites a los valores observados para que "pase": cada límite debe tener una justificación física, lógica o del contrato de datos.

## 4. MLflow (seguimiento de experimentos)

### 4.1 Archivos y almacenamiento

| Archivo | Contenido |
|---|---|
| [`src/modeling/seguimiento_mlflow.py`](../../src/modeling/seguimiento_mlflow.py) | Recorre el reporte de cualquier experimento y lo registra. Contiene funciones puras de aplanado (testeadas) y `registrar_reporte()`. |
| `mlflow.db` | Base SQLite con experimentos, runs, parámetros, métricas y etiquetas. Local, no se versiona. |
| `mlartifacts/` | Archivos adjuntos a cada run (JSON de métricas, predicciones, modelos, resultado de GX). Local, no se versiona. |

Las rutas son absolutas desde `src/utils/paths.py`, así que un notebook (que corre desde `notebooks/`) y la CLI (desde la raíz) escriben en la misma base. Para usar un servidor compartido con Nicolás, basta definir la variable `MLFLOW_TRACKING_URI` antes de ejecutar; si no está definida, se usa la base local.

### 4.2 Estructura de los runs

| Nivel | Uno por… | Nombre de ejemplo | Qué contiene |
|---|---|---|---|
| Experimento | módulo | `denguekay/ablacion_clima` | Agrupa todas las ejecuciones del mismo módulo. |
| Run padre | ejecución | `ablacion_clima` | Parámetros de XGBoost (`xgb.*`), criterios y notas del reporte, filas por horizonte (`h2.filas_gold`…), hashes de gold/silver/manifiesto como etiquetas, commit de Git, versiones de librerías y plataforma, resultado de GX (`gx.<suite>.porcentaje_exito`), datasets gold (pestaña *Datasets*) y artefactos. |
| Run hijo | horizonte × variante | `h4 · mas_clima_observado` | Columnas usadas, umbral elegido, métricas de cada bloque (`temporada_2024.cls_f1`) y media de validación (`validacion_media.cls_f1`). Etiqueta `seleccionada_en_validacion` si el módulo la eligió (por ejemplo, `clasificacion` o, en las ablaciones por familia, `fija:regresion`). |
| Run nieto | horizonte × variante × bloque | `h4 · mas_clima_observado · temporada_2024` | Todas las métricas del fold, corte de ajuste, tamaños y positivos de entrenamiento, y los modelos XGBoost de ese fold cuando el módulo los guarda (solo prueba). |

Ambos enfoques (regresión y clasificación) comparten el mismo run porque se entrenan sobre las mismas filas del mismo fold; se distinguen por el prefijo de la métrica.

### 4.3 Nombres de métricas

| Prefijo | Origen en el reporte | Ejemplos |
|---|---|---|
| `reg_` | `regresion.conteos` y `regresion.alerta_derivada` | `reg_mae`, `reg_rmse`, `reg_f1`, `reg_auprc`, `reg_vp`, `reg_fp` |
| `cls_` | `clasificacion.alerta_directa`, `brier`, `umbral_probabilidad` | `cls_f1`, `cls_precision`, `cls_recall`, `cls_auprc`, `cls_brier`, `cls_umbral_probabilidad` |
| `pers_` | `persistencia` (línea base) | `pers_mae`, `pers_f1` |
| `cal_` | `calibracion` (solo validación progresiva) | `cal_umbral`, `cal_filas`, `cal_positivos` |

En el run hijo, cada métrica lleva delante el bloque (`temporada_2022.`, `temporada_2024.`, `calendario_2025.`) o `validacion_media.`. Esta media solo promedia los bloques de tipo `validacion` o `seleccion`, que son los que cada módulo usa para elegir. **Las pruebas (2024) y la sensibilidad (2025) nunca se promedian**, para no ocultar que 2025 tiene solo tres semanas positivas. Las métricas que el reporte deja en `null`, como un F1 o un AUPRC sin positivos, no se registran.

### 4.4 Ver y comparar

Desde la raíz del repo:

```powershell
.\.venv\Scripts\mlflow ui --backend-store-uri sqlite:///mlflow.db --workers 1
```

Abrir <http://127.0.0.1:5000>. En Windows, `--workers 1` evita el error `WinError 10022` que aparece con los 4 procesos que MLflow usa por defecto; los avisos `WARNING` y `StarletteDeprecationWarning` del arranque son normales. El reporte de Great Expectations se abre con `start great_expectations\gx\uncommitted\data_docs\local_site\index.html`. Para comparar variantes de una ablación: entrar al experimento y filtrar con `tags.nivel = 'variante'`. Luego agregar columnas como `validacion_media.cls_f1` y `validacion_media.reg_f1`, ordenar y seleccionar varias filas para usar *Compare*. Otros filtros útiles: `tags.nivel = 'fold' and tags.bloque = 'temporada_2024'`, o `tags.seleccionada_en_validacion LIKE '%clasificacion%'`.

Desde Python o un notebook:

```python
import mlflow
from src.modeling.seguimiento_mlflow import uri_seguimiento

mlflow.set_tracking_uri(uri_seguimiento())
runs = mlflow.search_runs(
    experiment_names=["denguekay/validacion_temporal_compacta"],
    filter_string="tags.nivel = 'variante'",
)
runs[["tags.mlflow.runName", "metrics.validacion_media.cls_f1",
      "metrics.temporada_2024.cls_f1", "tags.seleccionada_en_validacion"]]
```

### 4.5 Desactivar en una corrida

Cada función `ejecutar_*` acepta `validar_datos=False` y `registrar_mlflow=False`. En la CLI:

```powershell
.\.venv\Scripts\python -m src.modeling.ablacion_clima --sin-mlflow
.\.venv\Scripts\python -m src.modeling.ablacion_clima --sin-validacion-datos
```

Si el registro en MLflow falla (por ejemplo, la base está bloqueada), el módulo imprime un `AVISO` y **no pierde nada**: el JSON, las predicciones y los modelos ya se guardaron en `docs/` y `models/` antes de registrar. En cambio, si falla Great Expectations, el experimento no entrena.

## 5. Agregar un experimento nuevo

Mientras el reporte siga la forma de los actuales (`reporte["horizontes"][h]["variantes"][variante]` con folds producidos por `evaluar_fold`), el registro funciona sin tocar `seguimiento_mlflow.py`. Hay que:

1. Agregar a la firma `validar_datos: bool = True, registrar_mlflow: bool = True`.
2. Tras `auditar_traspaso`, ejecutar `calidad = validar_entradas_modelado(gold_dir=gold_dir, silver_path=...) if validar_datos else None`.
3. Después de escribir el JSON, llamar a `registrar_o_avisar("<nombre>", reporte, metricas_path=..., salida_dir=..., gold_dir=gold_dir, calidad_datos=calidad)`.
4. Guardar los modelos con el patrón `xgb_h{h}_{variante}_{regresion|clasificacion}_{bloque}.json` para que se adjunten al fold correcto.

Cualquiera de los siete módulos sirve de ejemplo.

## 6. Límites y próximos pasos

- **Sin Model Registry todavía.** Cuando el equipo apruebe un modelo final, el paso natural es registrarlo con `mlflow.xgboost.log_model(...)` y `mlflow.register_model(...)`. No se implementó porque no hay modelo aprobado y porque 2024 ya se consultó varias veces: no es un test independiente.
- **Experimentos históricos.** Los resultados anteriores a esta integración siguen en `docs/modeling/metricas/*.json`. No se importaron a MLflow para no presentarlos como si se hubieran ejecutado con él. Al volver a correr los módulos, quedan registrados.
- **Reproducibilidad entre equipos.** En el mismo equipo, dos corridas dan métricas idénticas. Entre equipos no. `config/config.yaml` deja `device: auto`: XGBoost usa la GPU NVIDIA (CUDA) si existe y la CPU si no; en una Mac con Apple Silicon entrena en CPU. GPU y CPU no suman en el mismo orden al construir los histogramas, y también se observaron diferencias entre dos CPU distintas. El número de hilos no cambia resultados. Los JSON actuales de `docs/modeling/metricas/` se generaron en el equipo de Rosa con GPU (`device="cuda"`, `n_jobs=12`), y los informes de `docs/modeling/` citan esas cifras. Con la misma versión de XGBoost (3.4.1) se compararon tres corridas: la que respaldaba la versión anterior de los informes (CPU), una corrida en el entorno Linux de esta integración (CPU) y la actual (GPU). Las diferencias movieron métricas en milésimas, desplazaron algunos umbrales de probabilidad un paso de la rejilla (por ejemplo, `h=2 / historia_4_mas_2` dio 0,150 en Linux y 0,175 en las otras dos) y cambiaron estas elecciones de variante:

  | Experimento | h | Elección | Versión anterior (CPU) | Linux (CPU) | JSON actual (GPU) |
  |---|---|---|---|---|---|
  | `ablacion_espacial` | 2 | regresión | `mas_ambos` | `mas_ambos` | `mas_jerarquia` |
  | `ablacion_sociodemografica` | 2 | fija · regresión | `fija_tres` | `fija_tres` | `fija_poblacion` |
  | `ablacion_sociodemografica` | 4 | fija · regresión | `fija_tres` | `base_6` | `fija_tres` |
  | `ablacion_fracciones` | 2 | fija · regresión | `fija__fraccion_rural` | `fija__fraccion_rural` | `fija__fraccion_mujeres` |
  | `ablacion_fracciones` | 2 | anual · regresión | `anual__fraccion_rural` | `anual__fraccion_analfabeta_15_mas` | `anual__fraccion_hogares_celular` |
  | `ablacion_fracciones` | 2 | fija · clasificación | `fija__fraccion_sin_saneamiento` | `fija__fraccion_sin_seguro` | `fija__fraccion_sin_seguro` |
  | `ablacion_fracciones` | 2 | anual · clasificación | `anual__fraccion_hogares_lena` | `anual__fraccion_hogares_lena` | `anual__fraccion_alumbrado_red` |
  | `ablacion_fracciones` | 4 | fija · regresión | `fija__fraccion_agua_red` | `fija__fraccion_agua_cisterna` | `fija__fraccion_agua_cisterna` |
  | `ablacion_fracciones` | 4 | anual · regresión | `anual__fraccion_hogares_celular` | `anual__fraccion_hogares_celular` | `anual__fraccion_mujeres` |
  | `ablacion_fracciones` | 4 | anual · clasificación | `anual__fraccion_sin_saneamiento` | `anual__fraccion_alumbrado_red` | `anual__fraccion_sin_saneamiento` |
  | `validacion_temporal_compacta` | 2 | regresión | `base_4` | `base_4` | `base_6` |
  | `validacion_temporal_compacta` | 4 | regresión | `base_4` | `base_6` | `base_6` |

  La columna Linux solo registró las elecciones que diferían de la versión anterior; en las demás filas se asume que coincidía con ella. Esto es una **observación**, no una conclusión: en esos casos las variantes en competencia están separadas por menos que la variación numérica entre equipos (en el cribado de fracciones, a menudo por menos de 0,002 de F1 medio). Las elecciones de **clasificación h=4** que sostienen las decisiones principales (población fija de 2017; `sin_seguro` como mejor fracción fija; ninguna variante espacial ni climática; `base_6 + población` en la validación progresiva) fueron las mismas en las tres corridas; solo cambió, en Linux, la del carril anual retrospectivo del cribado. Antes de fijar variables para el modelo final, convendría repetir las comparaciones con varias semillas o entre equipos y tratar como empate las diferencias de ese tamaño. Por eso cada run guarda las etiquetas `plataforma`, `python` y `version.*`, y el JSON guarda `parametros.device`. Al comparar runs de Rosa y de Nicolás, revisar primero esas etiquetas. Para reproducir en CPU las condiciones de otro equipo, cambiar `device: cpu` en `config/config.yaml`.
- **Tiempo extra.** La validación de GX añade unos 8 s por corrida. El registro en MLflow tarda unos pocos segundos; el caso más grande, `ablacion_fracciones`, genera 269 runs en unos 13 s.
- **Espacio.** Cada ejecución copia predicciones y modelos a `mlartifacts/`. Una ronda completa de los siete módulos generó 553 runs, unos 21 MB de base SQLite y unos 130 MB de artefactos; la mayor parte corresponde a las predicciones de `ablacion_fracciones`. Para liberar espacio, borrar runs viejos en la interfaz y luego ejecutar `mlflow gc --backend-store-uri sqlite:///mlflow.db`.
- **Telemetría.** MLflow 3 envía estadísticas de uso anónimas. Para desactivarlo, definir la variable de entorno `MLFLOW_DISABLE_TELEMETRY=true`.

## 7. Verificación realizada

- **Tests:** `tests/test_seguimiento_mlflow.py` cubre el aplanado de métricas, la detección de folds con distintos nombres, que la media solo use validación y el registro anidado real en una base SQLite temporal. `tests/test_calidad_gx.py` comprueba que datos sintéticos válidos pasan y que las suites detectan llave duplicada, `ubigeo` sin cero inicial, `brote` inválido, fracción fuera de rango, fuga temporal, columna faltante, temperatura mínima mayor que la máxima, humedad imposible, casos negativos y coordenadas fuera de Piura. La suite completa (`python -m unittest discover -s tests`) pasa.
- **Datos reales:** las suites `silver_integrado`, `gold_h2` y `gold_h4` pasan al 100 % con los CSV actuales.
- **Antes/después:** se ejecutaron los siete módulos con el código original y con el instrumentado, en el mismo equipo. Los siete JSON de métricas resultaron idénticos. En MLflow quedaron 25 runs para `primer_xgboost`, 43 para `ablacion_espacial`, 37 para `ablacion_clima`, 99 para `ablacion_sociodemografica`, 269 para `ablacion_fracciones`, 49 para `ablacion_poblacion_sin_seguro` y 31 para `validacion_temporal_compacta`. En todas las elecciones, la variante con mayor `validacion_media` coincidió con la que eligió el propio módulo. En `ablacion_sociodemografica` y `ablacion_fracciones`, la comparación se hizo dentro de cada familia (`fija:`/`anual:`), que es como eligen esos módulos.
