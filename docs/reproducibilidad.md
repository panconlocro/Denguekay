# Reproducibilidad

Esta es la entrada única. Una persona sin acceso a la PC de Rosa clona el repo y, siguiendo solo esta guía, puede:

- **(a)** regenerar `data/` desde las fuentes públicas;
- **(b)** obtener los datos exactos de cada versión;
- **(c)** reentrenar y verificar v0–v3, y regenerar y verificar la matriz de entrenamiento congelada de V4;
- **(d)** reproducir las cifras de cada estudio desde su tag;
- **(e)** levantar la API.

**Dos niveles de exactitud:**

- **Exacto:** datos del Release del tag + `constraints.txt` + huella de comportamiento, en el mismo dispositivo con
  el que se grabó la referencia. Da los mismos bits.
- **Desde las fuentes:** el pipeline vuelve a bajar todo. Las fuentes revisan y republican sus datos, así que puede
  diferir (abajo se dice cuánto, medido por muestra). La referencia de cada versión son sus Releases, no una
  descarga nueva.

## 0. Entorno (una vez)

Windows y PowerShell, Python **3.12.10** de 64 bits. Clona en una ruta corta (por ejemplo `C:\dk`): algunas
dependencias tienen rutas largas y `pip` falla sin el soporte de rutas largas de Windows.

```powershell
git clone https://github.com/panconlocro/Denguekay.git C:\dk\Denguekay
cd C:\dk\Denguekay
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt -c constraints.txt
.\.venv\Scripts\python -m pip install -e . -c constraints.txt
```

La instalación tarda unos 3 min (medido: 195 s). `constraints.txt` fija las versiones exactas con las que se
grabaron las referencias.

**Dispositivo:** `configs/config.yaml` usa la GPU NVIDIA si la hay (`device: auto`). Para elegir uno:

```powershell
$env:DENGUEKAY_XGB_DEVICE = "cpu"
$env:DENGUEKAY_XGB_NJOBS = "2"
```

XGBoost no da los mismos bits en CPU y en GPU, ni en CPU con distinto número de hilos. Por eso las huellas se
guardan por entorno.

## 1. Qué se reproduce y cómo

| Qué | Comando (desde la raíz del clon) | Resultado esperado | Tiempo | GPU | Nivel |
|---|---|---|---|---|---|
| Datos de la v0 | `python -m denguekay.data.ingestion.release_bundles --version v0` | 2 zips verificados (`gold/respaldo_pre_b3`, predicciones del protocolo compacto) | segundos | no | exacto |
| Datos de v1 / v2 / v3 | `... --version v1`, `--version v2`, `--version v3` | zips verificados contra el manifiesto de `models/registry/<v>/` | segundos (v3, con comparadores: unos 30 s) | no | exacto |
| v0 | `python -m denguekay.model.reproduce v0` | `REPRODUCE: SÍ`: misma selección y 0 métricas distintas | 20 s | sí (referencia CUDA) | exacto en GPU. En CPU con 2 hilos cambia la matriz elegida en la regresión h4 (486 métricas distintas) |
| v1 | `python -m denguekay.model.reproduce v1` | huella igual a la registrada | 10 s | no | exacto en CUDA y en CPU con 2 hilos; en CUDA, además, igual bit a bit a las predicciones guardadas |
| v2 | `python -m denguekay.model.reproduce v2` | huella igual a la registrada | 10 s | no | exacto en CUDA y en CPU con 2 hilos; en CUDA, además, igual bit a bit a las predicciones guardadas |
| v3 | `python research/06_model_improvement/code/phase_v3_close.py verificar --semilla 17` | `VERIFICACION: PASA`: G41, huella y métricas | 6 min en GPU, 5,3 min en CPU con 2 hilos | no | exacto en CUDA (referencia oficial) y en CPU con 2 hilos (referencia CPU, `--solo predicciones_v3_cpu.zip`) |
| Métricas de la v3 sin reentrenar | `python research/06_model_improvement/code/phase_v3_close.py metricas` | Brier y AUPRC de 570 celdas iguales al JSON | 15 s | no | exacto |
| Estudios 01–06 | ver el README de cada estudio (`research/<estudio>/README.md`) | sus cifras desde su tag y los Releases | según el estudio | los estudios 03–06 se grabaron en GPU | exacto con los datos del Release; las búsquedas largas no se repiten (abajo) |
| Pipeline de V0–V3 | `python -m denguekay.pipelines.run_all --version v0` (… `v3`) | recorrido 01–11 de `pipelines/notebooks/<VERSIÓN>/`, su gold y la verificación 99 | días (ERA5-Land 4–5 días por el tope diario; CHIRPS por FTP unas 10 h) | no | desde las fuentes |
| Pipeline de V4 | `python -m denguekay.pipelines.run_all --version v4 --verificar` | silver e integrado de confirmados, gold B3 y cotejo de SHA-256 | depende del caché y de los límites de descarga | no | desde las fuentes |
| Gold congelado de V4 | `python -m denguekay.features.gold_v4 --desde-release` tras extraer `datos_v4.zip` | 73 775 filas de 65 distritos al corte de la SE 41 de 2026 | segundos con los insumos extraídos | no | llaves y etiquetas exactas, flotantes con tolerancia de `1e-12` entre plataformas |
| API con la v3 | `docs/modeling/reproducir_v3.md`, «Ruta del producto» | `GET /api/v1/salud` → 200 | minutos | no (la inferencia es en CPU) | — |

Huellas registradas (`denguekay.model.frozen_configs`; fichas en `models/registry/`):

| Versión | CUDA | CPU con 2 hilos |
|---|---|---|
| v1 | `1534b535…3806e` | `be866649…bff5` |
| v2 | `b302d838…a936` | `0fe5d107…e2b3` |
| v3 | `99a0b26d…494de` (oficial) | `7a46f4f2…db72b6` |
| v0 | sin huella: su identidad es el SHA-256 del paquete y sus métricas de selección (`models/registry/v0/validacion_temporal_compacta.json`) | — |

Fichas: [v0](../models/registry/v0/ficha.md), [v1](../models/registry/v1/ficha.md),
[v2](../models/registry/v2/ficha.md), [v3](../models/registry/v3/ficha.md) y [v4](../models/registry/v4/ficha.md).
Guías por versión: [V3](modeling/reproducir_v3.md) y [V4](modeling/reproducir_v4.md).

## 2. Datos exactos por versión y por estudio (Releases)

Cada Release lleva zips con SHA-256 en un manifiesto versionado. El módulo de descarga verifica el zip y cada
archivo, y no sobrescribe un archivo distinto sin `--sobrescribir`.

Para cotejar los archivos ya extraídos, ejecuta el siguiente comando desde el clon de trabajo. Se puede
repetir `--version` o quitarlo para consultar V0–V4. El comando imprime el informe sin modificar archivos.
Cada versión se compara con su propio manifiesto. Si una ruta aparece en dos versiones, el mismo archivo
puede coincidir con una y diferir con la otra. Cualquier archivo ausente o distinto da código de salida `1`.

```powershell
.\.venv\Scripts\python -m denguekay.data.validation.frozen_inputs --version v4 --raiz .
```

| Tag | Assets | Manifiesto |
|---|---|---|
| `model/v0` | `respaldo_pre_b3_v0.zip` (gold anterior h2, h4, manifiesto y SHA256SUMS; antes era la única copia), `predicciones_v0.zip` | `models/registry/v0/manifiesto_datos.json` |
| `model/v1` | `datos_v1.zip` (integrado, cobertura, epi histórico y gold anterior), `predicciones_v1.zip` | `models/registry/v1/` |
| `model/v2` | `datos_v2.zip` (integrado, base, cobertura, epi histórico, Sala, gold h2 vigente y su manifiesto), `predicciones_v2.zip` | `models/registry/v2/` |
| `model/v3` | `datos_v3.zip`, `predicciones_v3.zip`, `comparadores_v3.zip`, `predicciones_v3_cpu.zip` | `models/registry/v3/` |
| `model/v4` | `datos_v4.zip` (entradas exactas del gold), `modelo_v4.zip` (boosters y parámetros), `demo_v4.zip` y los demás paquetes de la [guía de V4](modeling/reproducir_v4.md#archivos-del-release) | `models/registry/v4/manifiesto_datos.json` |
| `archive/EDA` | `datos_estudio01.zip` (silver por fuente e integrados) | `research/01_eda/` |
| `archive/training` | `gold_anterior.zip` (el gold anterior en `data/gold/`, como lo leen los tags 02–05), `artefactos_estudio03.zip` | `research/03_first_models_and_ablations/` |
| `study/horizon-architecture` | `artefactos_estudio04.zip` | `research/04_horizon_architecture/` |
| `study/fe-hyperparameters` | `artefactos_estudio05.zip` | `research/05_fe_hyperparameters/` |
| `study/model-improvement` | `artefactos_estudio06.zip` (con `optuna.db` del ajuste), `bronze_estudio06.zip` (cachés de clima, CHIRPS por FTP, NOAA y HDX) | `research/06_model_improvement/` |

Las carpetas `cache/` de los estudios 04 y 05 (cachés de cómputo, 5,6 GB) no se publican: se regeneran solas.

Para un estudio, la copia del tag es un worktree. Los datos se extraen en él con `--raiz`, desde el clon de
`develop`:

```powershell
git worktree add ..\denguekay-horizontes study/horizon-architecture
.\.venv\Scripts\python -m denguekay.data.ingestion.release_bundles --estudio 04_horizon_architecture --raiz ..\denguekay-horizontes
```

Cada README de `research/` dice qué bajar y en qué orden.

**Una versión anterior sin pisar V4.** `data/silver/` y `data/gold/` son los de V4. Para trabajar con v0 a v3 se
extraen aparte, en una carpeta dentro del repositorio (la convención es `data_anteriores/<versión>/`, ignorada por Git),
y se le dice al código que lea de ahí con `DENGUEKAY_DATA_DIR`. `BRONZE` y `REFERENCE` no se mueven.

```powershell
.\.venv\Scripts\python -m denguekay.data.ingestion.release_bundles --version v2 --data-dir data_anteriores/v2 --solo datos_v2.zip
$env:DENGUEKAY_DATA_DIR = "data_anteriores/v2"
.\.venv\Scripts\python -m denguekay.model.reproduce v2
```

`--data-dir` (relativa a la raíz del repo) extrae solo los archivos `data/silver/…` y `data/gold/…` del zip en
`<carpeta>/silver` y `<carpeta>/gold`; el resto de sus miembros se omite y se cuenta como `omitidos`. No se combina
con `--raiz`. Los archivos de `models/experimentos/` (por ejemplo `predicciones_v2.zip`) se extraen como siempre, sin
`--data-dir`. Verificado el 16/11/2026 en un clon con los datos de V4 en `data/`: `data/` quedó idéntico (hash por
archivo), `reproduce v2` dio la huella registrada (`0fe5d107…`, CPU con 2 hilos) y `tests/test_equivalence.py` pasó.

Los tests que necesitan el integrado, la historia y el gold de v1 a v3 se omiten con el `data/` de V4 (y en el CI, que no
tiene `data/`): con la suite completa son 40 omitidos. Para correrlos se apunta a la carpeta de la versión, por ejemplo
`DENGUEKAY_DATA_DIR=data_anteriores/v2` y `python -m unittest discover -s tests`: 640 tests OK y 6 omitidos (17/11/2026).
Con el gold de la v2 (20 columnas) y con el de la v3 (24) los tests de esquema aceptan el que corresponde a la carpeta.

**Búsquedas largas:** no se repiten. El ajuste de hiperparámetros del estudio 06 (`phase_hp_tuning.py`, tope de
10 h) quedó en `optuna.db`, y el notebook 19 lee de ahí sus cifras. El estudio 05 publica sus resultados por fase.

## 3. Desde las fuentes (pipeline)

### V0–V3

```powershell
.\.venv\Scripts\python -m denguekay.pipelines.run_all --version v2 --lista
.\.venv\Scripts\python -m denguekay.pipelines.run_all --version v2 --bronze-publicado
```

Corre los notebooks de `pipelines/notebooks/V2/` (o `V0`, `V1`, `V3`) en orden, del 01 al 11 y el 99. Cada versión
escribe su silver y su gold en `data_anteriores/<versión>/` (`run_all` fija `DENGUEKAY_DATA_DIR`), nunca en `data/`, que
es de V4; el bronze es el caché común. Las descargas se reanudan desde sus cachés: si una se corta por un límite del
API, se vuelve a correr el comando (o `--desde <paso>`). Cada carpeta tiene su README. v0 y v1 comparten silver y gold
anterior; v2 añade la Sala y su gold limpio; v3 añade ERA5-Land desde 2000, CHIRPS y Niño 1+2 (los mismos archivos que V4).

| Fuente | Paso | ¿Cuenta? | Tiempo | Muestra comparada con el silver del Release (2026-11-09) |
|---|---|---|---|---|
| Open-Meteo, modelo por defecto (2017–2025) | 02 → 06 | no | horas (límite por hora) | Ayabaca 2024, 51 semanas: diferencia máxima 2e-15 °C |
| ERA5-Land (2000 → hoy − 5 días; solo v3) | 02 → 06 | no | 4–5 días por el tope diario; una actualización semanal, minutos | Ayabaca 2024: 4e-15 °C |
| NOAA Niño 1+2 (solo v3) | 06 | no | segundos | 538 meses idénticos (último 2026-10) |
| CHIRPS v3 final por FTP (2000 → hoy) y preliminar (solo v3) | 06 | no (FTP anónimo) | unas 10 h (unos 9 500 archivos globales de unos 11 MB) | 2024-03-15, 65 distritos: 0,008 mm frente al snapshot de Earth Engine |
| Excel de casos (Drive) | 04 → 08 | no (`gdown`, sin sesión) | 1 min (60 MB) | la hoja principal trae **4 filas más** que el bronze del Release: son filas en blanco (sin `ubigeo`, año ni semana; comprobado el 16/11/2026) y el silver da lo mismo |
| Excel socio (Drive) | 03 → 07 | no | segundos | contenido idéntico (los bytes del xlsx difieren por sus metadatos) |
| Sala Situacional | 05 | no | minutos | Piura (200101) 2025, 53 semanas: idénticas (221 casos) |
| Integrado y gold | 09, 10 y 11 | no | minutos | — |

SHA-256 de lo que devolvió Drive el 2026-11-09:

- `PiuraDengue.xlsx`: `bf5c2965684f3940593ca75b8a44d4c21f5728e7f0dd9cd6f770086646450b4f` (el bronze del Release
  es `9b1b4a1c…`);
- `data_socio_2017_2025.xlsx`: `bff86075e82117e07c386ca317be4410fc1f9e30d295533297e77e4eaf3c0673` (el bronze es
  `07fa942a…`, con el mismo contenido).

**CHIRPS: FTP y Earth Engine.**

- El silver con el que se entrenaron b3 y d1 tomó el final del snapshot de Earth Engine (`ee_final`, en los
  Releases).
- El pipeline usa el FTP anónimo. En los 240 días que se solapan (enero a abril de 2025 y 2026), las medias
  diarias por polígono difieren como máximo 0,15 mm (media 0,003 mm) y las sumas semanales, como máximo 0,34 mm.
- `silver-ftp --con-earth-engine` reconstruye el silver congelado. La v3 no usa lluvia.

**Cotejo del 16 de noviembre de 2026 (Windows, v0 a v3).** En un clon aparte se ejecutaron los 12 pasos de cada
carpeta con descargas reales (código de salida `0` en las cuatro). Cada versión escribió solo en
`data_anteriores/<versión>/`: tras correr las cuatro, el hash de los 18 archivos de `data/silver` y `data/gold` del
clon no cambió. El paso 99 compara con el manifiesto del Release:

| Archivo | v0 | v1 | v2 | v3 |
|---|---|---|---|---|
| `epi_piura_semanal.csv` (81 196 filas, `c4b67ce0…`) | — | idéntico | idéntico | idéntico |
| Integrado de notificados | — | dentro de tolerancia (3,6 × 10⁻¹⁵) | dentro de tolerancia (3,6 × 10⁻¹⁵) | dentro de tolerancia (3,6 × 10⁻¹⁵) |
| Cobertura del integrado | — | idéntica | idéntica | — |
| Gold h2 y h4 anterior (`respaldo_pre_b3`) | idénticos (`0ff49650…`, `f9fbed66…`) | idénticos | — | — |
| Gold h2 limpio de 20 columnas (`a5d16663…`) | — | — | idéntico | — |
| Manifiesto del gold y `SHA256SUMS.txt` | difieren solo en `sha256_fuente` | ídem | difiere solo en `sha256_fuente` | — |
| Sala Situacional | — | — | 174 filas con conteo distinto | 174 filas con conteo distinto |
| ERA5-Land y Niño 1+2 | — | — | — | idénticos |
| CHIRPS | — | — | — | 325 filas distintas: 5 semanas (2026-09-27 a 2026-10-25) pasaron de `prelim` a `final` |

`sha256_fuente` es el hash del integrado, que difiere en bytes por ese ruido de punto flotante; el gold que se
calcula desde él es idéntico. El gold de v0 a v2 se reproduce con `features.gold.generate_gold` (`columns="candidatas"` con
`horizons=(2, 4)`, o `columns="v2"`); el de la v3 no tiene referencia en un Release (es de 24 columnas, solo para
trazabilidad).

Con esos datos regenerados: `model.reproduce v2` y `v1` dan la huella registrada (CPU con 2 hilos); `reproduce v0`
da lo mismo que con los datos del Release (486 métricas numéricas distintas, la diferencia CPU frente a GPU de la tabla
de arriba) más una diferencia de linaje, `sha256_manifest_gold`, por lo anterior. `reproduce v1` leía la regla de brote de
`gold/manifest_fase6.json`, que el Release de v1 no trae; ahora usa el de `gold/respaldo_pre_b3/` si el otro no existe.

`research/06_model_improvement/code/phase_v3_close.py verificar --semilla 17` (CPU con 2 hilos) sobre `DENGUEKAY_DATA_DIR`:

| Carpeta de datos | Resultado |
|---|---|
| Datos exactos del Release (`release_bundles --version v3 --data-dir data_anteriores/v3_release`) | `VERIFICACION: PASA`: G41 con diferencia 0 y huella `7a46f4f2…` |
| Pipeline de V3 regenerado desde las fuentes | `NO PASA`: G41 con diferencia máxima 0,52 en la probabilidad de brote y otra huella |
| La anterior, con solo la Sala del Release puesta en su lugar | `VERIFICACION: PASA`, misma huella |

Así que la única diferencia que cambia el modelo es la de la **Sala**: MINSA revisó 174 conteos de 2026 desde que se congeló
la v3. ERA5-Land, Niño 1+2, el histórico, el integrado (ruido de punto flotante) y las 5 semanas de CHIRPS republicadas no
alteran el resultado. La v3 no se reproduce desde las fuentes mientras la Sala no se pueda recortar a sus conteos de
entonces; por eso su copia exacta es el Release.

### Casos de v0 a v3 (notificados)

V4 cuenta casos **confirmados** (CSV `DatosDengueV2.csv` y gráfico `ten-fig02a-echart` de la Sala). v0 a v3 usan
**notificados**, y las dos definiciones nunca se mezclan en un mismo archivo. Para regenerar los de v0–v3 están
restaurados desde `model/v3`: `data/processing/epi_cases_legacy.py` (Excel `PiuraDengue.xlsx`, ID en
`drive.epi_excel_file_id` de `config.yaml`, descarga con `drive_download.download_epi_excel`) y la Sala con
`scrape_sala(..., case_definition="notificados")` (gráfico `ten-fig02b-echart`) o
`weekly_update --casos notificados`. El paso de la Sala se puede esperar con `await refresh_sala_silver_async(...)`
desde un notebook; la versión síncrona `refresh_sala_silver(...)` también funciona dentro de un kernel.

Comprobado el 16/11/2026 sobre el `PiuraDengue.xlsx` local (1 029 421 filas): el histórico semanal da 81 196 filas
y, escrito con fin de línea CRLF como lo hacía el notebook 07, `c4b67ce03d6915d4…`, el de `datos_v1` a `datos_v3`. El
Excel no está en ningún Release; si Drive entrega otro (hoy trae 4 filas más), el informe lo mostrará como cambio de
la fuente. El sitio de la Sala sigue sirviendo ambos gráficos (comprobado el 16/11/2026 para Piura 2025 con
`case_definition` en cada valor). Observación: para 2025 las dos definiciones dan los mismos números (221 casos en
el distrito de Piura y 1 117 en el departamento), y los silver congelados de v2 y V4 coinciden en las 3 445 filas
de 2025. En 2026 difieren 421 filas entre esos dos silver; con lo calculado no se puede decir si es por la
definición o por la fecha de captura. Si el sitio dejara de servir el gráfico anterior, v0–v3 toman la Sala de su Release.

### V4 con confirmados

Ejecuta desde la raíz con el entorno de la sección 0. Las salidas se escriben en `data/` con los mismos nombres que tienen en `datos_v4.zip`, que es como los lee el modelo. Una corrida desde las fuentes reemplaza una copia exacta extraída antes; se recupera con `release_bundles --version v4 --solo datos_v4.zip --sobrescribir`.
Para reproducir el ajuste del paper usa la [ruta exacta del Release](modeling/reproducir_v4.md#regenerar-el-gold-congelado-desde-el-release).

```powershell
.\.venv\Scripts\python -m denguekay.pipelines.run_all --version v4 --lista
.\.venv\Scripts\python -m denguekay.pipelines.run_all --version v4 --verificar
```

Con las capturas completas ya guardadas en `data/bronze/`, añade `--sin-descargas` al segundo comando. Usa
`--desde <prefijo>` (por ejemplo `06`) para reanudar y `--solo-verificar` para cotejar archivos que ya existen sin ejecutar notebooks.
El pipeline conserva el orden de los notebooks y guarda el informe en `data/gold/verificacion_v4.json`. Para cada archivo regenerado que difiere, el informe lo coteja con `datos_v4.zip` (descargado a una carpeta temporal): para la Sala lista las filas con conteo distinto; para ERA5-Land y el panel da la diferencia máxima por columna y los marca `dentro_tolerancia` si es menor que 1e-12.
En un clon limpio, `--bronze-publicado` restaura las capturas climáticas históricas verificadas para reducir
la descarga inicial. El [detalle de la opción](modeling/reproducir_v4.md#regenerar-desde-las-fuentes)
describe los paquetes y las fuentes que se consultan en vivo.

Los pasos son los notebooks de `pipelines/notebooks/V4/`. `run_all` no ejecuta en el lugar: guarda el notebook
ejecutado y su registro en `pipelines/ejecuciones/v4/<fecha>/` (ignorada por Git) e imprime la celda y el error si un
paso falla. `--version` acepta `v0` a `v4` (por defecto `v4`); las carpetas de `v0` a `v3` todavía no existen.

| Paso | Fuentes y salidas V4 |
|---|---|
| 01 | Puntos distritales versionados y respuesta GLO-90 de Open-Meteo. Archiva la consulta en `data/bronze/geografia/` y guarda `data/bronze/geografia/geografia_distritos_v4.csv` para el cotejo. B3 conserva la geografía verificada del Release. |
| 02 → 06 | Open-Meteo para el panel 2017–2025 y ERA5-Land desde 2000. NOAA CPC para Niño 1+2. CHIRPS v3 por polígono desde bronze de Earth Engine y FTP, con una versión completa por semana y fecha de disponibilidad. |
| 03 → 07 y 09 | Excel socio, limpieza y unión con el silver meteorológico del panel en `data/silver/`. |
| 04 → 08 | `DatosDengueV2.csv` de Drive a bronze y agregado por distrito y semana con `tipo_dx=C`. V4 toma del CSV el tramo 2000–2024. |
| 05 | Sala Situacional de 2025 en adelante. Guarda las capturas crudas, reconcilia totales y escribe el silver de confirmados. La extensión del ajuste congelado incluye la SE 53 de 2025 y acaba en la SE 41 de 2026. |
| 10 → 11 | Panel y cobertura en `data/silver/confirmados/`. La matriz B3 y su manifiesto quedan en `data/gold/`, junto con el gold h2 de confirmados y su `manifest_fase6.json`. El gold representa h2–h4 desde un mismo origen al corte congelado. |

En el recorrido desde las fuentes, el código de salida `0` indica que la corrida produjo un gold válido con
los insumos disponibles. El JSON registra los hashes y lista las diferencias de los insumos regenerados respecto
del Release. Un archivo requerido ausente, un paso fallido o una inconsistencia de integridad devuelve `1`.
La comprobación `--solo-verificar --desde-release` exige los hashes publicados y la referencia del gold.
`manifest_fase6.json` figura como evidencia archivada del gold h2.
La consulta nueva de elevación se reporta por separado de la geografía fija usada en B3.

**Cotejo realizado el 15 de noviembre de 2026.** Se ejecutaron los ocho pasos de la ruta sin descargas con los
cachés disponibles y una captura de Sala archivada ese día. Los resultados corresponden a esos insumos.

| Insumo | Comparación con el Release |
|---|---|
| Histórico confirmado, cobertura del integrado, UBIGEO, CHIRPS, Niño 1+2 y geografía usada por B3 | SHA-256 idénticos. CHIRPS y Niño usaron cachés locales. La geografía usada por B3 provino del Release. |
| Sala Situacional | Las 3 445 filas de 2025 conservaron sus conteos. En 2026 se añadió la SE 44 (65 filas) y se revisaron 102 conteos en semanas que ya estaban en el Release. De esos, 61 corresponden a la SE 41 o anteriores. |
| ERA5-Land | Coincidieron las 91 000 llaves. El SHA-256 difirió, con diferencias numéricas máximas de 3,6 × 10⁻¹⁵ °C en temperatura y 1,5 × 10⁻¹⁴ puntos porcentuales en humedad. |
| Integrado de confirmados | Coincidieron las 30 485 llaves y todos sus conteos. El SHA-256 difirió, con una diferencia numérica máxima de 1,2 × 10⁻¹³ mm en precipitación. |
| Consulta nueva de elevación | Los 65 distritos conservaron la misma elevación. Dos latitudes difirieron en el último decimal representado. El SHA-256 difirió. |

El gold de la corrida desde bronze tuvo las mismas 73 775 llaves del gold congelado. Las revisiones de casos
cambiaron dos etiquetas de brote por horizonte. Con los archivos del Release se verificaron los diez hashes
de los insumos y el CSV congelado se regeneró byte por byte. La guía de V4 explica ambas rutas y sus salidas.

**Cotejo del 16 de noviembre de 2026 (Windows, ruta completa).** En un clon aparte se ejecutaron los 12 pasos
de `pipelines/notebooks/V4/` con `--bronze-publicado` y descargas reales (Open-Meteo, Drive, Sala, NOAA, CHC), sin
extraer antes `datos_v4.zip`. Código de salida `0`. Lo que escribió el pipeline en `data/` se comparó con el Release:

| Archivo | Comparación con el Release |
|---|---|
| Histórico confirmado, cobertura, Niño 1+2, ERA5-Land, UBIGEO y geografía de B3 | SHA-256 idénticos. Para ERA5-Land hace falta leer `distritos_piura_coords.csv` con el lector de pandas por defecto y pandas 3.0.x, el de `constraints.txt` (con `round_trip` Arenal y Miguel Checa cambian 1 ulp; con pandas 3.1, que siempre lee exacto, también). |
| Integrado de confirmados | Mismas llaves y textos. Diferencia numérica máxima 5,7 × 10⁻¹⁴ (dentro de 1 × 10⁻¹²). |
| Sala Situacional | 102 filas con conteo distinto del Release (MINSA revisó conteos de semanas ya publicadas). |
| CHIRPS | 325 filas distintas, que son 5 semanas (2026-09-27 a 2026-10-25) × 65 distritos: pasaron de `prelim` a `final` porque el CHC publicó el dato final después de congelar V4. Las demás filas, versiones y fechas son idénticas. |
| Consulta nueva de elevación | Difiere de la geografía del Release; B3 usa la del Release. |
| Gold h2 de confirmados (`11_gold`) | Mismas 30 485 filas y 24 columnas que el del Release. Idéntico salvo 1 × 10⁻¹⁶ en `semana_epi_seno` y `semana_epi_coseno` (diferencia entre plataformas ya conocida). En `manifest_fase6.json` solo cambia `sha256_fuente`, por el integrado. |
| Gold B3 (`11_gold`) | Mismas 73 775 filas y llaves. Contra el gold generado con los insumos del Release cambian 500 celdas, todas en columnas derivadas de casos (rezagos históricos, pendiente, casos y etiquetas de brote por horizonte; 2 etiquetas por horizonte). Clima, geografía y estacionalidad son idénticos: las 5 semanas de CHIRPS republicadas no entran al entrenamiento. |

Con los archivos del Release en `data/`, el gold B3 en Windows queda dentro de tolerancia frente a la referencia
independiente y `research/08_v3_confirmed_cases/code/freeze_v4.py` corre de principio a fin (10 boosters, 73 775
filas). Sobre los archivos regenerados el script se detiene en su propia guarda («Changed epidemiological input»),
porque exige los hashes exactos de los insumos del estudio; esos hashes cambian cuando las fuentes republican.

## 4. Límites conocidos

- **Las fuentes republican:** las semanas recientes de la Sala, el Excel de casos y CHIRPS preliminar cambian.
  Regenerar desde las fuentes no reproduce bit a bit; la exactitud está en los Releases.
- **Dispositivo:** las referencias de la v0 y de los estudios 03–06 son de GPU. La v1, la v2 y la v3 tienen además
  huella en CPU con 2 hilos.
- **Estudios 01–05:** su silver de la Sala es el vigente. Las filas hasta 2025 son las que leyeron, pero el archivo
  trae además las semanas de 2026.
- **El Release de GitHub no es un archivo persistente con DOI:** para el paper conviene depositarlo además en un
  repositorio con DOI (pendiente).
