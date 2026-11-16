# Denguekay V4 · B3 con casos confirmados

Modelo congelado para Piura con casos confirmados hasta la semana epidemiológica 41 de 2026 (17 de octubre). La demo usa la semilla 17 y muestra los 65 distritos a 2, 3 y 4 semanas desde ese corte. Los pronósticos que se muestran son retrospectivos.

El tag `model/v4` apunta al [congelamiento del modelo](https://github.com/panconlocro/Denguekay/commit/305005ce096a55bc16757ce3f6efcd69b145596d). El [commit del código de la demo](https://github.com/panconlocro/Denguekay/commit/38de6f4b260aa0aa72d76c4f9824d1f24c8664f4) incluye el frontend y la API necesarios para abrirla.

## Abrir el tablero en otro equipo

Necesitas Git, Python 3.12 de 64 bits y Node.js 20.19 o posterior. En macOS, XGBoost requiere el entorno de ejecución OpenMP (`brew install libomp` si aún no está instalado).

Descarga `demo_v4.zip` y `manifiesto_datos.json` del release y guárdalos juntos en una carpeta llamada `release-v4` al lado del repositorio. Desde una terminal:

```sh
git clone https://github.com/panconlocro/Denguekay.git
cd Denguekay
git switch --detach 38de6f4b260aa0aa72d76c4f9824d1f24c8664f4
```

En Windows (PowerShell):

```powershell
py -3.12 -m venv .venv
$python = ".\.venv\Scripts\python.exe"
& $python -m pip install -r requirements-api.txt -c constraints.txt
& $python -m pip install --no-deps -e .
& $python -m denguekay.data.ingestion.release_bundles --manifiesto ../release-v4/manifiesto_datos.json --carpeta ../release-v4 --solo demo_v4.zip
& $python apps/web/tools/serve_demo.py --v4
```

En macOS o Linux:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-api.txt -c constraints.txt
.venv/bin/python -m pip install --no-deps -e .
.venv/bin/python -m denguekay.data.ingestion.release_bundles --manifiesto ../release-v4/manifiesto_datos.json --carpeta ../release-v4 --solo demo_v4.zip
.venv/bin/python apps/web/tools/serve_demo.py --v4
```

Deja la API abierta. En otra terminal, desde la raíz del repositorio:

```sh
cd apps/web
npm ci
npm run dev:demo
```

Abre [el tablero local](http://127.0.0.1:5173). La demo usa SQLite en modo lectura y archivos de almacenamiento locales.

## Archivos del release

Desde un clon que ya incluya `models/registry/v4/manifiesto_datos.json`,
`python -m denguekay.data.ingestion.release_bundles --version v4` usa el manifiesto del repositorio.

| Archivo | Contenido |
| --- | --- |
| `demo_v4.zip` | SQLite lista para la API local y artefactos de inferencia de la semilla 17. |
| `modelo_v4.zip` | Los diez boosters congelados de `b3_obs` e `historia_geo`, sus parámetros, observaciones agregadas y el vector de origen. |
| `datos_v4.zip` | Casos confirmados agregados, ERA5-Land, CHIRPS v3, Niño 1+2, geografía distrital e insumos silver/gold validados. |
| `predicciones_v4.zip` | Predicciones retrospectivas y ajustes de B3 e historia y geografía, con cinco semillas por brazo. |
| `comparadores_v4.zip` | Predicciones y resultados archivados de los controles espaciales y los comparadores estadísticos, incluida persistencia. |
| `clima_sensibilidad_v4.zip` | Series distritales semanales de CHIRTS-ERA5 y ERA5 global y cotejos de cobertura costera. |
| `tablas_paper_v4.zip` | Predicciones agregadas y script para recalcular las tablas II y S16 del paper. |

El extractor comprueba SHA-256 de cada ZIP y cada archivo. Conserva las rutas relativas del repo y se detiene ante un archivo existente con contenido distinto. Para recalcular las tablas, extrae `tablas_paper_v4.zip` y ejecuta `python reproducibility/reproduce.py --out reproduced` con Python 3.9 o posterior.

Para repetir el ajuste congelado con los scripts del paper, instala `requirements.txt` con `constraints.txt` y selecciona `datos_v4.zip predicciones_v4.zip` con `--solo`. Sigue el [protocolo de congelamiento](https://github.com/panconlocro/Denguekay/blob/model/v4/research/08_v3_confirmed_cases/congelamiento_b3_v4.md) con CPU y dos hilos. Usa otra ruta de salida si también extrajiste el modelo archivado. Los boosters adjuntos son la referencia para usar el modelo congelado en otros equipos.

## Regenerar el gold congelado desde el Release

Instala el [entorno completo de Python 3.12](../reproducibilidad.md#0-entorno-una-vez) en un clon limpio
que incluya `denguekay.features.gold_v4`. Usa ese clon para los archivos del Release. Desde su raíz, en
PowerShell, ejecuta los tres comandos en orden.

```powershell
.\.venv\Scripts\python -m denguekay.data.ingestion.release_bundles --version v4 --solo datos_v4.zip
.\.venv\Scripts\python -m denguekay.features.gold_v4 --desde-release
.\.venv\Scripts\python -m denguekay.pipelines.run_all --version v4 --solo-verificar --desde-release
```

Los resultados quedan en `data/gold/`.

- `piura_confirmados_v4_gold.csv` contiene **73 775 filas** de los **65 distritos** de Piura. Las filas
  se identifican por `(ubigeo, anio, semana)` de h2 y comparten un origen para los objetivos h2, h3 y h4.
  Cada horizonte lleva la semana objetivo, los casos confirmados, el umbral y la etiqueta `brote`.
- `manifest_v4.json` enumera los 16 predictores de B3, los hashes de los insumos y del CSV, y el cierre de
  las etiquetas. El corte del ajuste congelado es el **17 de octubre de 2026 (SE 41)**.
- `verificacion_v4.json` muestra el SHA-256 esperado y el observado para cada insumo. Se apoya en el
  [manifiesto del estudio](../../research/08_v3_confirmed_cases/manifiesto_b3_v4.json) y el
  [registro del Release](../../models/registry/v4/manifiesto_datos.json). Para el gold, comprueba la
  integridad del archivo contra `manifest_v4.json` y la equivalencia de sus 34 columnas contra la
  [referencia independiente](../../tests/fixtures/v4_gold/referencia.json).

Los diez hashes de entrada coincidieron en macOS ARM64, Linux x86-64 y Windows x86-64. Difieren cuatro
columnas de punto flotante del CSV, con una desviación absoluta máxima de `8,88e-16`. La referencia
registra los hashes de los tres entornos observados y usa igualdad exacta para llaves, fechas, conteos,
etiquetas y variables de aritmética exacta. Los valores de punto flotante calculados se verifican celda a
celda con `rtol=0, atol=1e-12`. El CI de las tres plataformas regenera el gold y comprueba también la
equivalencia entre el clima del gold, el vector de la BD y el `origen.csv` congelado en la SE 41.

El `manifest_fase6.json` y el gold h2 presentes en `datos_v4.zip` son evidencia del linaje que se validó
al congelar V4. El ajuste de los boosters se reproduce por separado con el protocolo del paper.

## Regenerar desde las fuentes

Usa el mismo entorno. Los resultados de este recorrido quedan en `data/v4_fuentes/`, con su propio `silver/`,
`gold/` y `reference/`. Los archivos descargados del Release mantienen sus rutas originales. Los dos perfiles
pueden coexistir en el mismo clon.

```powershell
.\.venv\Scripts\python -m denguekay.pipelines.run_all --version v4 --verificar
```

En un clon limpio, el histórico de clima tarda por la cuota de Open-Meteo y el volumen de CHIRPS. Para
empezar con las capturas climáticas históricas publicadas y descargar el tramo reciente, usa:

```powershell
.\.venv\Scripts\python -m denguekay.pipelines.run_all --version v4 --bronze-publicado --verificar
```

La opción comprueba `bronze_estudio06.zip` y `datos_v3.zip` y extrae solo los cachés climáticos a
`data/bronze/`. Si un archivo de destino ya existe con otro hash, la extracción se detiene. Los pasos
siguientes descargan el clima reciente y las demás fuentes, y generan silver e integrado antes del gold.

Si ya tienes en `data/bronze/` las capturas de la Sala confirmada, la consulta de elevación y los cachés de las
demás fuentes, añade `--sin-descargas`. Este modo también requiere que la geografía fija de `datos_v4.zip` esté
disponible en la ruta del Release. Para una corrida nueva con acceso a red, 01b descarga y verifica ese archivo
del Release si falta. B3 usa esa geografía para conservar los valores que recibió el booster congelado.
El paso 01b guarda la consulta nueva por separado para cotejarla. `--desde <paso>` permite reanudar la
generación. El paso `11` construye el gold al corte
congelado con los insumos disponibles en ese clon. La actualización de observaciones para servir pronósticos
usa sus propios cortes de publicación.

El informe en `data/v4_fuentes/gold/verificacion_v4.json` registra los archivos que coinciden, difieren o faltan, y el
estado de los pasos. En este recorrido `gold.estado_manifiesto_local` comprueba la integridad del CSV y
la referencia independiente del gold se aplica con `--solo-verificar --desde-release`. Una corrida válida
desde las fuentes devuelve `0` aunque hayan cambiado los insumos regenerados. Sus nombres y hashes quedan
en `diferencias_en_fuentes` e `insumos`. Un paso fallido, un archivo requerido ausente, un hash distinto en
una entrada congelada o un manifiesto local que no corresponda al gold devuelven `1`.
La [tabla de cotejo](../reproducibilidad.md#v4-con-confirmados) documenta qué diferencias se
observaron al repetir el pipeline. Para replicar el ajuste del estudio se usa el Release de `model/v4`.
