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
| Pipeline de V0–V3 | `python -m denguekay.pipelines.run_all` | recorrido 01–10 y gold h2 | días (ERA5-Land 4–5 días por el tope diario; CHIRPS por FTP unas 10 h) | no | desde las fuentes |
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

**Búsquedas largas:** no se repiten. El ajuste de hiperparámetros del estudio 06 (`phase_hp_tuning.py`, tope de
10 h) quedó en `optuna.db`, y el notebook 19 lee de ahí sus cifras. El estudio 05 publica sus resultados por fase.

## 3. Desde las fuentes (pipeline)

### V0–V3

```powershell
.\.venv\Scripts\python -m denguekay.pipelines.run_all --lista
.\.venv\Scripts\python -m denguekay.pipelines.run_all
```

Corre los notebooks de `pipelines/notebooks/` en orden (01 → 10, con 03b, 03c y 06b) y deja `data/` como lo usan
las versiones. Las descargas se reanudan desde sus cachés: si una se corta por un límite del API, se vuelve a
correr el comando (o `--desde <paso>`).

| Fuente | Paso | ¿Cuenta? | Tiempo | Muestra comparada con el silver del Release (2026-11-09) |
|---|---|---|---|---|
| Open-Meteo, modelo por defecto (2017–2025) | 02 → 03 | no | horas (límite por hora) | Ayabaca 2024, 51 semanas: diferencia máxima 2e-15 °C |
| ERA5-Land (2000 → hoy − 5 días) | 02 (A3, B2, C1, C2) → 03 | no | 4–5 días por el tope diario; una actualización semanal, minutos | Ayabaca 2024: 4e-15 °C |
| NOAA Niño 1+2 | 03b | no | segundos | 538 meses idénticos (último 2026-10) |
| CHIRPS v3 final por FTP (2000 → hoy) y preliminar | 03c | no (FTP anónimo) | unas 10 h (unos 9 500 archivos globales de unos 11 MB) | 2024-03-15, 65 distritos: 0,008 mm frente al snapshot de Earth Engine |
| Excel de casos (Drive) | 06 → 07 | no (`gdown`, sin sesión) | 1 min (60 MB) | la hoja principal trae **4 filas más** que el bronze del Release: la fuente cambió |
| Excel socio (Drive) | 04 → 05 | no | segundos | contenido idéntico (los bytes del xlsx difieren por sus metadatos) |
| Sala Situacional | 06b | no | minutos | Piura (200101) 2025, 53 semanas: idénticas (221 casos) |
| Integrado y gold | 08, 09 y 10 | no | minutos | — |

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

### V4 con confirmados

Ejecuta desde la raíz con el entorno de la sección 0. Las salidas regeneradas se guardan en `data/v4_fuentes/`.
Para reproducir el ajuste del paper usa la [ruta exacta del Release](modeling/reproducir_v4.md#regenerar-el-gold-congelado-desde-el-release).

```powershell
.\.venv\Scripts\python -m denguekay.pipelines.run_all --version v4 --lista
.\.venv\Scripts\python -m denguekay.pipelines.run_all --version v4 --verificar
```

Con las capturas completas ya guardadas en `data/bronze/`, añade `--sin-descargas` al segundo comando. Usa
`--desde <paso>` para reanudar y `--solo-verificar` para cotejar archivos que ya existen sin ejecutar notebooks.
El pipeline conserva el orden de los notebooks y guarda el informe en `data/v4_fuentes/gold/verificacion_v4.json`.

| Paso | Fuentes y salidas V4 |
|---|---|
| 01b | Puntos distritales versionados y respuesta GLO-90 de Open-Meteo. Archiva la consulta en `data/bronze/geografia/` y guarda `data/v4_fuentes/reference/geografia_distritos_v4.csv` para el cotejo. B3 conserva la geografía verificada del Release. |
| 02b → 03d | Open-Meteo para el panel 2017–2025 y ERA5-Land desde 2000. NOAA CPC para Niño 1+2. CHIRPS v3 por polígono desde bronze de Earth Engine y FTP, con una versión completa por semana y fecha de disponibilidad. |
| 04 → 05b y 08b | Excel socio, limpieza y unión con el silver meteorológico del panel bajo `data/v4_fuentes/silver/`. |
| 06 → 07b | `DatosDengueV2.csv` de Drive a bronze y agregado por distrito y semana con `tipo_dx=C`. V4 toma del CSV el tramo 2000–2024. |
| 06c | Sala Situacional de 2025 en adelante. Guarda las capturas crudas, reconcilia totales y escribe el silver de confirmados. La extensión del ajuste congelado incluye la SE 53 de 2025 y acaba en la SE 41 de 2026. |
| 09b → 11 | Panel y cobertura en `data/v4_fuentes/silver/integrado/`. La matriz B3 y su manifiesto quedan en `data/v4_fuentes/gold/`. El gold representa h2–h4 desde un mismo origen al corte congelado. |

Con `--verificar` y `--solo-verificar`, el código de salida `1` indica que algún insumo difiere, falta, o que
la ejecución falló. El JSON distingue el estado de los pasos, el cotejo de los insumos y la integridad del
gold respecto de su manifiesto local. `manifest_fase6.json` figura como evidencia archivada del gold h2.
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

## 4. Límites conocidos

- **Las fuentes republican:** las semanas recientes de la Sala, el Excel de casos y CHIRPS preliminar cambian.
  Regenerar desde las fuentes no reproduce bit a bit; la exactitud está en los Releases.
- **Dispositivo:** las referencias de la v0 y de los estudios 03–06 son de GPU. La v1, la v2 y la v3 tienen además
  huella en CPU con 2 hilos.
- **Estudios 01–05:** su silver de la Sala es el vigente. Las filas hasta 2025 son las que leyeron, pero el archivo
  trae además las semanas de 2026.
- **El Release de GitHub no es un archivo persistente con DOI:** para el paper conviene depositarlo además en un
  repositorio con DOI (pendiente).
