# Pipeline de V3 (casos notificados)

[Ficha](../../../models/registry/v3/ficha.md) · [guía](../../../docs/modeling/reproducir_v3.md) · [estudio 06](../../../research/06_model_improvement/README.md) · [datos exactos](../../../docs/reproducibilidad.md)

La v3 añade ERA5-Land desde 2000, CHIRPS v3 y el índice Niño 1+2 (los mismos archivos de clima que V4) y su gold de 24 columnas, que guarda para trazabilidad: el modelo entrena con la historia desde 2000. Cuenta casos **notificados** (Excel de Drive y Sala), no confirmados: es la definición de V4 la que cambia, y las dos nunca se mezclan en un archivo.

| Paso | Notebook | Qué hace |
|---|---|---|
| 01 | `01_bronze_geografia` | Reconstruye el catálogo de distritos desde GADM y lo compara con `data/reference/` (no lo reescribe) |
| 02 | `02_bronze_clima` | Open-Meteo 2017–2025 y ERA5-Land desde 2000 (temperatura y humedad) |
| 03 | `03_bronze_socio` | Excel sociodemográfico (Drive) |
| 04 | `04_bronze_casos` | Excel de casos **notificados** `PiuraDengue.xlsx` (Drive) |
| 05 | `05_bronze_sala` | Sala Situacional de 2025 y 2026 con la definición de notificados, recortada al corte; capturas en `data/bronze/epi/sala_notificados/` |
| 06 | `06_silver_clima` | Silver semanal: panel Open-Meteo, ERA5-Land desde 2000, CHIRPS v3 por polígono y Niño 1+2, recortados al corte |
| 07 | `07_silver_socio` | Silver socioeconómico |
| 08 | `08_silver_casos` | Casos notificados por distrito y semana desde el Excel |
| 09 | `09_silver_meteo_socio` | Clima y socio unidos |
| 10 | `10_silver_integrado` | Panel integrado de 2017–2025: Excel hasta 2024 y Sala (notificados) para 2025; cobertura epidemiológica |
| 11 | `11_gold` | Gold h=2 de 24 columnas (`base_6`, A3, B3 y d3) |
| 99 | `99_verificacion` | Compara silver y gold con el manifiesto del Release de la versión |

Los notebooks solo llaman funciones del paquete; los pasos de clima, socio y meteo-socio son los mismos que
usa V4 (`pipelines/v4_inputs.py`) y los de casos y gold están en `pipelines/older_inputs.py`.

## Dónde escribe

`run_all` ejecuta esta carpeta con `DENGUEKAY_DATA_DIR=data_anteriores/v3`: el silver y el gold quedan en
`data_anteriores/v3/silver` y `data_anteriores/v3/gold` (ignorada por Git) y **nunca** en `data/`, que es de V4.
El bronze es el caché común: se lee de `data/bronze/`.

```powershell
.\.venv\Scripts\python -m denguekay.pipelines.run_all --version v3 --lista
.\.venv\Scripts\python -m denguekay.pipelines.run_all --version v3 --bronze-publicado
```

La copia exacta de la versión es su Release (`models/registry/v3/manifiesto_datos.json`). Para tenerla sin regenerar:
`release_bundles --version v3 --data-dir data_anteriores/v3`. Regenerar desde las fuentes puede dar diferencias donde las
fuentes republican; el paso 99 las lista archivo por archivo.
