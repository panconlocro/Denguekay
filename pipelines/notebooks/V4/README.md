# Pipeline de V4 (confirmados)

Notebooks del Medallion de la V4, numerados por paso. Se ejecutan en orden con

```powershell
.\.venv\Scripts\python -m denguekay.pipelines.run_all --lista
.\.venv\Scripts\python -m denguekay.pipelines.run_all --version v4 --verificar
```

`run_all` no modifica estos notebooks: el notebook ejecutado y su registro de cada paso quedan en
`pipelines/ejecuciones/v4/<fecha>/` (ignorada por Git).

| Paso | Notebook | Qué hace |
|---|---|---|
| 01 | `01_bronze_geografia` | Puntos distritales y respuesta de elevación GLO-90 de Open-Meteo |
| 02 | `02_bronze_clima` | Open-Meteo (panel 2017–2025) y ERA5-Land desde 2000 |
| 03 | `03_bronze_socio` | Excel sociodemográfico (Drive) |
| 04 | `04_bronze_casos` | `DatosDengueV2.csv` de Drive |
| 05 | `05_bronze_sala` | Sala Situacional MINSA, confirmados |
| 06 | `06_silver_clima` | Silver semanal de meteorología, CHIRPS y Niño 1+2 |
| 07 | `07_silver_socio` | Silver socioeconómico |
| 08 | `08_silver_casos` | Confirmados por distrito y semana desde el CSV |
| 09 | `09_silver_meteo_socio` | Clima y socio unidos |
| 10 | `10_silver_integrado` | Panel integrado y cobertura epidemiológica |
| 11 | `11_gold` | Matriz B3 de los horizontes 2, 3 y 4 al corte congelado |
| 99 | `99_verificacion` | Compara lo generado con los manifiestos del estudio y del Release |

Los datos exactos de V4 están en su Release (`docs/reproducibilidad.md`); una corrida desde las fuentes puede
diferir en lo que las fuentes republican.

Las salidas se escriben en `data/` con los nombres del Release (`data/silver/confirmados/…`, `data/gold/…`). Una
corrida desde las fuentes reemplaza una copia exacta extraída antes: se recupera con
`release_bundles --version v4 --solo datos_v4.zip --sobrescribir`. El corte de cada fuente (Sala hasta la SE 43 de
2026, etiquetas hasta 2026-10-17, ERA5-Land y CHIRPS hasta la semana del 2026-10-25, Niño 1+2 hasta 2026-10) está en
`src/denguekay/pipelines/versions.py`.

## Sala Situacional

El paso 05 captura la serie CONFIRMADO de 2025 (completo, SE 53) y de 2026, y `versions.py` la recorta a la SE 43 de 2026
(6 240 filas, 2 semanas provisionales). El Release no registra la fecha de su captura. Una corrida nueva captura el
día en que se ejecuta: la del 16/11/2026 difirió en 102 filas con conteo distinto, que MINSA revisó. Las respuestas
crudas quedan en `data/bronze/epi/sala/<año>_<fecha UTC>/`.

## Geografía

Los centroides del catálogo (`data/reference/distritos_piura_coords.csv`, versionado) salen de GADM 4.1 nivel 3
(`geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_PER_3.json.zip`). La elevación fija de B3 es el DEM Copernicus GLO-90 en esos
puntos, según el [resultado del estudio 08](../../../research/08_v3_confirmed_cases/resultado_resolucion_chirts.md). El
paso 01 vuelve a consultar la elevación en la API de Open-Meteo y la guarda en `data/bronze/geografia/` solo para
cotejarla: **la geografía que usa el modelo es la archivada en el Release** (`geografia_distritos.csv`).
