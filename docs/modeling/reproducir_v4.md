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
