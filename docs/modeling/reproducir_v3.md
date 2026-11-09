# Reproducir la V3 desde un clon

Esta guía sirve para trabajar con la V3 (por ejemplo, el análisis de sensibilidad de la etiqueta, R09) sin
copiar `data/` de otra PC.

- **De dónde salen los datos:** del Release de GitHub del tag `model/v3`, verificados contra el manifiesto
  [`models/registry/v3/manifiesto_datos.json`](../../models/registry/v3/manifiesto_datos.json).
- **Protocolo:** [protocolo_v3.md](protocolo_v3.md).
- **Ficha:** [models/registry/v3/ficha.md](../../models/registry/v3/ficha.md).

## 1. Clonar y fijar la versión

```powershell
git clone https://github.com/panconlocro/Denguekay.git
cd Denguekay
git switch --detach model/v3
```

Para trabajar a partir de ahí, crea tu rama desde el tag: `git switch -c exp/<tu-rama> model/v3`.

**Windows: clona en una ruta corta** (por ejemplo `C:\dk\Denguekay`). Algunas dependencias instalan archivos
con rutas muy largas dentro de `.venv`, y sin el soporte de rutas largas de Windows `pip` falla con
`OSError: [Errno 2] No such file or directory` (pasó en la verificación desde una carpeta temporal profunda).

## 2. Entorno exacto

Python **3.12.10** de 64 bits; con otra versión las ruedas pueden diferir. `constraints.txt` fija las
versiones exactas del entorno con el que se congeló la V3. `requirements.txt` sigue siendo la lista de
dependencias.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt -c constraints.txt
.\.venv\Scripts\python -m pip install -e . -c constraints.txt
```

## 3. Descargar y verificar los datos

```powershell
.\.venv\Scripts\python -m denguekay.data.ingestion.release_bundles
```

El módulo descarga los zips del Release y comprueba el SHA-256 de cada zip y de cada archivo contra el
manifiesto. Después los descomprime en la raíz del repo:

| Zip | Contenido | Destino |
|---|---|---|
| `datos_v3.zip` (7,8 MB) | los archivos de `data/` que lee la V3: silver de casos, Sala, ERA5-Land, CHIRPS, Niño 1+2, integrado 2017–2025, catálogo de ubigeos y el bronze diario de CHIRPS `ee_final`; más el insumo preliminar de CHIRPS 2026 | `data/` y `models/experimentos/` |
| `predicciones_v3.zip` (68 MB) | predicciones de referencia de la V3 y de L + 5a sin clima (5 semillas, todos los bloques) y el registro de la corrida | `models/experimentos/mejora_modelo/v3/` |
| `comparadores_v3.zip` (467 MB) | predicciones guardadas de los comparadores (sección 10 del protocolo) | `models/experimentos/mejora_modelo/` |

- **Opciones:** `--solo datos_v3.zip predicciones_v3.zip` baja solo esos zips; `--carpeta <ruta>` guarda los
  zips para no volver a bajarlos.
- **Archivos que ya existen:** si un archivo ya existe con otro contenido, el módulo se detiene. Para
  reemplazarlo hay que pasar `--sobrescribir`.
- **Si un hash no coincide,** el módulo no escribe ese archivo y termina con error.

## 4. Reentrenar la V3 y comprobar la huella

```powershell
.\.venv\Scripts\python research/06_model_improvement/code/phase_v3_close.py verificar --semilla 17
```

Reentrena la V3 con la semilla 17 en los 20 bloques (2008–2026). En la GPU de referencia tarda unos 6 minutos.
Después:

1. Compara con las predicciones del Release de esa semilla (guarda G41: todas las filas, |diferencia| ≤ 1e-6 en
   `casos_predichos` y `probabilidad_brote`).
2. Calcula la huella de comportamiento y la compara con `frozen_configs.V3_FINGERPRINTS` para el dispositivo
   en uso.
3. Recalcula Brier y AUPRC desde las predicciones del Release y los compara con
   `research/06_model_improvement/docs/metricas/v3.json`.

Termina con `VERIFICACION: PASA` o `NO PASA`.

- **Dos referencias: GPU (oficial) y CPU (2 hilos).**
  - **GPU** (`device=cuda`, RTX 5060, driver 621.01, XGBoost 3.4.1): es la oficial y la que se sirve. Huella
    `99a0b26d…494de`; predicciones en `predicciones_v3.zip`.
  - **CPU con 2 hilos** (`$env:DENGUEKAY_XGB_DEVICE = "cpu"` y `$env:DENGUEKAY_XGB_NJOBS = "2"`): es determinista.
    La semilla 17 dio la misma huella en dos corridas, `7a46f4f2…db72b6`, unos 5,3 min por semilla. Las 5 semillas
    de V3 y de L + 5a están en `predicciones_v3_cpu.zip`, que se baja con `--solo predicciones_v3_cpu.zip` y se
    extrae en `models/experimentos/mejora_modelo/v3_cpu/`. Con ella descargada, `verificar` compara en CPU con
    esa referencia.
  - **CPU y GPU no dan los mismos árboles:** con `subsample` y `colsample` < 1 cada dispositivo muestrea distinto, y
    la CPU con otro número de hilos también. Contra la referencia GPU, la semilla 17 en CPU difiere hasta 99,8
    casos en μ y 0,072 en la probabilidad cruda por fila (con 12 hilos; medido el 2026-11-09). Es otra
    realización del mismo modelo, no ruido numérico.
  - **Las conclusiones se mantienen.** Medianas de 5 semillas, en las 6 temporadas que deciden:

    | Métrica | V3 en GPU | V3 en CPU | Diferencia máxima por celda |
    |---|---|---|---|
    | Brier | 0,0494 | 0,0494 | 0,0002 |
    | AUPRC | 0,785 | 0,785 | 0,0009 |
    | F1 a 0,50 | 0,671 | 0,672 | 0,012 |
    | Razón MAE | 0,898 | 0,897 | 0,008 |

    El veredicto de `SEASON_2026` entre V3 y L + 5a (los dos con el trial 191) es el mismo en los dos dispositivos:
    empate en Brier, alerta y conteo en h2, h3 y h4. La única diferencia es que en h4 el Brier queda con 2
    temporadas en contra en CPU y con 1 en GPU. Cifras en `comparacion_cpu_gpu.json` del mismo zip.
- **Otras semillas:** `--semilla 29`, `41`, `53` o `67` comparan con las suyas (sin huella).
- **Sin reentrenar:** `phase_v3_close.py metricas` recalcula solo el Brier y el AUPRC.
- **No uses** `phase_v3_close.py cierre` para verificar: es la corrida de 5 semillas que escribió las
  predicciones de referencia, y las sobrescribe.

## 5. Cargar las predicciones y recalcular métricas

```python
import sys
sys.path.insert(0, "research/06_model_improvement/code")
import phase_v3_close as v3

tabla = v3.read_table(v3.OUT / "predicciones_v3.csv.gz")      # ubigeo como texto de 6 dígitos
metricas = v3.block_metrics(tabla)                             # Brier y AUPRC por semilla, bloque y horizonte
mediana = metricas.groupby(["horizonte", "bloque"])[["brier", "auprc"]].median()
```

Las columnas están en la sección 5 de [protocolo_v3.md](protocolo_v3.md).

## 6. Para el análisis de sensibilidad de la etiqueta (R09)

- **Dónde se construye la etiqueta:** en memoria, en `research/06_model_improvement/code/phase0_diagnosis.py`.
  - `OUTBREAK_RULE` = 1,5 DE, 5 años previos y mínimo de 2 casos.
  - `long_labels` aplica `denguekay.features.outbreak_label.future_outbreak_threshold` sobre la serie desde 2000.
- **Dónde trabajar:** un estudio nuevo va en `research/07_<nombre>/` e importa ese código. No modifica
  `research/06_model_improvement/`, que está congelado en `study/model-improvement`.
- **Cómo usar la etiqueta primaria:** como definición congelada. Las alternativas se reportan como sensibilidades
  predeclaradas.

## 7. Límite

Regenerar los datos desde las fuentes puede no dar los mismos bytes: Open-Meteo, CHIRPS, la Sala Situacional del
MINSA y NOAA revisan y republican sus datos, y los cachés bronze no están en el Release. **La referencia de la V3
son los archivos del Release**, con los SHA-256 del manifiesto, no una descarga nueva.

## 8. Ruta del producto: de un clon de `develop` a la API con la v3

Lo que necesita **PostgreSQL** está marcado. Lo demás corre con SQLite o sin BD.

1. **Instalar** (sección 2) y **descargar los datos** de la v3:
   `python -m denguekay.data.ingestion.release_bundles --version v3`.
2. **Migrar** (crea `temp_media_era5_land_c`, migración `0007_v3`). Con SQLite local alcanza para probar; en
   PostgreSQL usa `MIGRATION_DATABASE_URL` (ver `docs/backend/despliegue.md`):

   ```powershell
   .\.venv\Scripts\python -m alembic upgrade head
   ```

3. **Regenerar gold** con d3. Escribe en `data/gold/`. Necesita el integrado y su cobertura, que bajan con
   `--version v2`:

   ```powershell
   .\.venv\Scripts\python -m jupyter nbconvert --to notebook --execute --inplace pipelines/notebooks/10_silver_to_gold.ipynb
   ```

4. **Construir el paquete servido sin BD**: booster, α, Platt y la `w` de 5a. Imprime la paridad con la v3
   congelada (en GPU debe ser 0,0) y la huella:

   ```powershell
   .\.venv\Scripts\python -m denguekay.serving.predictors.v3_l5a_d3 --salida models\paquete_v3
   ```

5. **Cargar la BD y publicar** (en producción, **PostgreSQL**):

   ```powershell
   .\.venv\Scripts\python -m denguekay.serving.load_data
   .\.venv\Scripts\python -m denguekay.serving.publish --seleccionar-experimental --inferir
   ```

6. **Levantar la API y probarla:**

   ```powershell
   .\.venv\Scripts\python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
   curl http://127.0.0.1:8000/api/v1/salud
   ```

   Respuesta esperada: `200`. `GET /api/v1/modelos/activo` lista las versiones `v3-…` y `GET /api/v1/mapa-riesgo?horizonte=4`
   devuelve los 65 distritos (verificado en una SQLite temporal: publicación de 109 s, 65 de 65 disponibles por horizonte).

Variables de entorno: `.env.example` (`DATABASE_URL`, `API_KEY`, `STORAGE_BACKEND=local`). Los tests usan BD
temporales, nunca la de producción.
