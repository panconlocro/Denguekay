# Pipeline de V2 (casos notificados)

[Ficha](../../../models/registry/v2/ficha.md) · [estudio 05](../../../research/05_fe_hyperparameters/README.md) · [datos exactos](../../../docs/reproducibilidad.md)

La v2 añade la Sala de 2025 y 2026 como silver aparte (`epi_sala_semanal.csv`) y su gold limpio de 20 columnas. Cuenta casos **notificados** (Excel de Drive y Sala), no confirmados: es la definición de V4 la que cambia, y las dos nunca se mezclan en un archivo.

| Paso | Notebook | Qué hace |
|---|---|---|
| 01 | `01_bronze_geografia` | Reconstruye el catálogo de distritos desde GADM y lo compara con `data/reference/` (no lo reescribe) |
| 02 | `02_bronze_clima` | Open-Meteo, panel 2017–2025 |
| 03 | `03_bronze_socio` | Excel sociodemográfico (Drive) |
| 04 | `04_bronze_casos` | Excel de casos **notificados** `PiuraDengue.xlsx` (Drive) |
| 05 | `05_bronze_sala` | Sala Situacional de 2025 y 2026 con la definición de notificados, recortada al corte; capturas en `data/bronze/epi/sala_notificados/` |
| 06 | `06_silver_clima` | Silver semanal de meteorología 2017–2025 |
| 07 | `07_silver_socio` | Silver socioeconómico |
| 08 | `08_silver_casos` | Casos notificados por distrito y semana desde el Excel |
| 09 | `09_silver_meteo_socio` | Clima y socio unidos |
| 10 | `10_silver_integrado` | Panel integrado de 2017–2025: Excel hasta 2024 y Sala (notificados) para 2025; cobertura epidemiológica |
| 11 | `11_gold` | Gold h=2 limpio de 20 columnas (`base_6`, A3 y B3) |
| 99 | `99_verificacion` | Compara silver y gold con el manifiesto del Release de la versión |

Los notebooks solo llaman funciones del paquete; los pasos de clima, socio y meteo-socio son los mismos que
usa V4 (`pipelines/v4_inputs.py`) y los de casos y gold están en `pipelines/older_inputs.py`.

## Dónde escribe

`run_all` ejecuta esta carpeta con `DENGUEKAY_DATA_DIR=data_anteriores/v2`: el silver y el gold quedan en
`data_anteriores/v2/silver` y `data_anteriores/v2/gold` (ignorada por Git) y **nunca** en `data/`, que es de V4.
El bronze es el caché común: se lee de `data/bronze/`.

```powershell
.\.venv\Scripts\python -m denguekay.pipelines.run_all --version v2 --lista
.\.venv\Scripts\python -m denguekay.pipelines.run_all --version v2 --bronze-publicado
```

La copia exacta de la versión es su Release (`models/registry/v2/manifiesto_datos.json`). Para tenerla sin regenerar:
`release_bundles --version v2 --data-dir data_anteriores/v2`. Regenerar desde las fuentes puede dar diferencias donde las
fuentes republican; el paso 99 las lista archivo por archivo.
