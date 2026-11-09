# Reproducibilidad

Esta es la entrada única. Una persona sin acceso a la PC de Rosa clona el repo y, siguiendo solo esta guía, puede:

- **(a)** regenerar `data/` desde las fuentes públicas;
- **(b)** obtener los datos exactos de cada versión;
- **(c)** reentrenar y verificar v0, v1, v2 y v3;
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
| Pipeline completo | `python -m denguekay.pipelines.run_all` | `data/` regenerado | días (ERA5-Land 4–5 días por el tope diario; CHIRPS por FTP unas 10 h) | no | desde las fuentes |
| API con la v3 | `docs/modeling/reproducir_v3.md`, «Ruta del producto» | `GET /api/v1/salud` → 200 | minutos | no (la inferencia es en CPU) | — |

Huellas registradas (`denguekay.model.frozen_configs`; fichas en `models/registry/`):

| Versión | CUDA | CPU con 2 hilos |
|---|---|---|
| v1 | `1534b535…3806e` | `be866649…bff5` |
| v2 | `b302d838…a936` | `0fe5d107…e2b3` |
| v3 | `99a0b26d…494de` (oficial) | `7a46f4f2…db72b6` |
| v0 | sin huella: su identidad es el SHA-256 del paquete y sus métricas de selección (`models/registry/v0/validacion_temporal_compacta.json`) | — |

Fichas: [v0](../models/registry/v0/ficha.md), [v1](../models/registry/v1/ficha.md),
[v2](../models/registry/v2/ficha.md) y [v3](../models/registry/v3/ficha.md). La v3 tiene además su guía:
[reproducir_v3.md](modeling/reproducir_v3.md).

## 2. Datos exactos por versión y por estudio (Releases)

Cada Release lleva zips con SHA-256 en un manifiesto versionado. El módulo de descarga verifica el zip y cada
archivo, y no sobrescribe un archivo distinto sin `--sobrescribir`.

| Tag | Assets | Manifiesto |
|---|---|---|
| `model/v0` | `respaldo_pre_b3_v0.zip` (gold anterior h2, h4, manifiesto y SHA256SUMS; antes era la única copia), `predicciones_v0.zip` | `models/registry/v0/manifiesto_datos.json` |
| `model/v1` | `datos_v1.zip` (integrado, cobertura, epi histórico y gold anterior), `predicciones_v1.zip` | `models/registry/v1/` |
| `model/v2` | `datos_v2.zip` (integrado, base, cobertura, epi histórico, Sala, gold h2 vigente y su manifiesto), `predicciones_v2.zip` | `models/registry/v2/` |
| `model/v3` | `datos_v3.zip`, `predicciones_v3.zip`, `comparadores_v3.zip`, `predicciones_v3_cpu.zip` | `models/registry/v3/` |
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

## 4. Límites conocidos

- **Las fuentes republican:** las semanas recientes de la Sala, el Excel de casos y CHIRPS preliminar cambian.
  Regenerar desde las fuentes no reproduce bit a bit; la exactitud está en los Releases.
- **Dispositivo:** las referencias de la v0 y de los estudios 03–06 son de GPU. La v1, la v2 y la v3 tienen además
  huella en CPU con 2 hilos.
- **Estudios 01–05:** su silver de la Sala es el vigente. Las filas hasta 2025 son las que leyeron, pero el archivo
  trae además las semanas de 2026.
- **El Release de GitHub no es un archivo persistente con DOI:** para el paper conviene depositarlo además en un
  repositorio con DOI (pendiente).
