# Calidad y completitud de los datos de la V4 (HU0005-4 y HU0005-5 (US v1.4))

Generado: 2026-11-18T02:55:53.040576+00:00. Estado: **conforme**.

Solo lectura: el reporte no corrige datos. Entradas: `meteo_socio_epi_piura_2017_2025.csv`, `meteo_socio_epi_piura_2017_2025.coverage.csv`, `DatosDengueV2.csv`, `epi_sala_semanal.csv`.

## Completitud (HU0005-5)

Periodo 2017-01-01 a 2025-12-21: 65 distritos × 469 semanas = 30485 filas esperadas. Presentes 30485, ausentes 0, completas 30485. **Completitud 100,00 %** (mínimo 95,00 %): cumple.

| Criterio | Columna | Nulos | Completitud |
|---|---|---|---|
| ubigeo | `ubigeo` | 0 | 100,00 % |
| año | `anio` | 0 | 100,00 % |
| semana | `semana` | 0 | 100,00 % |
| inicio de semana | `semana_inicio` | 0 | 100,00 % |
| casos | `casos_Dengue` | 0 | 100,00 % |
| temperatura | `temp_media` | 0 | 100,00 % |
| precipitación | `precip_total_mm` | 0 | 100,00 % |
| humedad | `hum_rel_media` | 0 | 100,00 % |
| población | `poblacion` | 0 | 100,00 % |

El silver integrado no tiene columnas derivadas: los nulos estructurales de los rezagos no entran en la medida.

## Observaciones descartadas

Registros originales 171569, descartados 3 (0,00 %; máximo 5,00 %): cumple.

| Año | Fuente | Originales | En el panel | Descartados | Exceso en el panel |
|---|---|---|---|---|---|
| 2017 | notificaciones_csv | 42475 | 42475 | 0 | 0 |
| 2018 | notificaciones_csv | 305 | 305 | 0 | 0 |
| 2019 | notificaciones_csv | 66 | 66 | 0 | 0 |
| 2020 | notificaciones_csv | 111 | 111 | 0 | 0 |
| 2021 | notificaciones_csv | 4072 | 4072 | 0 | 0 |
| 2022 | notificaciones_csv | 11905 | 11905 | 0 | 0 |
| 2023 | notificaciones_csv | 79273 | 79273 | 0 | 0 |
| 2024 | notificaciones_csv | 32245 | 32245 | 0 | 0 |
| 2025 | sala | 1117 | 1114 | 3 | 0 |

Excluidos por la definición de la V4 (no son descartes): 2316 notificaciones no confirmadas de Piura y 892506 de otros departamentos o fuera del periodo.

## Duplicados

Llave (ubigeo, año, semana): 0; llave (ubigeo, inicio de semana): 0.

## Control de duplicados de la fuente epidemiológica (HU0001-3)

| Fuente | Filas | Claves repetidas | Filas con llave repetida | Resultado | Regla aplicada |
|---|---|---|---|---|---|
| Histórico confirmado (CSV epidemiológico, hasta 2024) | 10240 | 0 | 0 | sin duplicados | Las filas que repiten la llave (ubigeo, anio, semana) se suman en una sola fila; el resultado tiene una fila por llave |
| Sala Situacional confirmada (desde 2025) | 6240 | 0 | 0 | sin duplicados | La Sala no admite claves repetidas: normalize_sala_records y el silver se detienen con error si un distrito o una llave (ubigeo, anio, semana) se repite; nada se suma ni se descarta |
| Panel integrado de la V4 | 30485 | 0 | 0 | sin duplicados | El panel integrado exige una fila por llave (ubigeo, anio, semana): la validación del panel se detiene si una llave se repite |

## Correspondencia territorial (HU0003-2)

65 distritos en el panel y 65 en el catálogo de UBIGEO: cumple.

- En el panel sin catálogo: ninguno.
- En el catálogo sin panel: ninguno.
- UBIGEO con formato inválido: ninguno.
- Clima sin correspondencia en el censo, después de los alias de nombres («El Carmendela Frontera» → «El Carmen de la Frontera», «San Miguelde El Faique» → «San Miguel de el Faique»): ninguno.
- Censo sin correspondencia en el clima: ninguno.
- Correspondencia ambigua: ninguna.

## Fuentes climáticas: producto y fecha de extracción (HU0002-1)

| Fuente | Producto | Fecha de extracción | Tipo de fecha | Capturas | Referencia |
|---|---|---|---|---|---|
| NOAA CPC | Niño 1+2: anomalía mensual de la TSM (OISST v2.1, sstoi.indices) | 2026-11-17 | captura registrada | 2 | fecha del nombre del archivo sstoi_AAAAMMDD.indices (bronze/enso) |
| CHIRPS v3 (Earth Engine) | CHIRPS v3.0 diario final, desagregación sat (Earth Engine, UCSB-CHC/CHIRPS/V3/DAILY_SAT, banda precipitation) | 2026-11-06 | captura registrada | 1 | manifiesto_ee_*.json (bronze/chirps/v3_sat/ee_final) |
| CHIRPS v3 (FTP del CHC) | CHIRPS v3.0 diario final, desagregación sat (GeoTIFF por FTP del CHC) | 2026-11-17 | captura registrada | 2 | manifiesto_ftp_final_*.json (bronze/chirps/v3_sat/final_ftp) |
| CHIRPS v3 preliminar (FTP del CHC) | CHIRPS v3.0 diario preliminar, desagregación sat (GeoTIFF por FTP del CHC) | 2026-11-17 | captura registrada | 2 | manifiesto_ftp_prelim_*.json (bronze/chirps/v3_sat/prelim) |
| ERA5-Land (semanas recientes) | ERA5-Land 0,1° vía Open-Meteo (archive API, models=era5_land), variables diarias | 2026-11-12 | captura registrada | 2 | carpeta con fecha AAAA-MM-DD (bronze/meteo/cache_meteo_era5_land_reciente) |
| Open-Meteo (clima del panel 2017-2025) | Open-Meteo archive API (sin models), variables diarias | 2026-11-12 | congelamiento del Release model/v4 (la fecha real de extracción no se registró) | 1 | caché histórica (cache_meteo); fecha de congelamiento de la ficha de la V4 |
| ERA5-Land 2000-2016 | ERA5-Land 0,1° vía Open-Meteo (archive API, models=era5_land), variables diarias | 2026-11-12 | congelamiento del Release model/v4 (la fecha real de extracción no se registró) | 1 | caché histórica (cache_meteo_era5_land_2000_2016); fecha de congelamiento de la ficha de la V4 |
| ERA5-Land 2017-2025 | ERA5-Land 0,1° vía Open-Meteo (archive API, models=era5_land), variables diarias | 2026-11-12 | congelamiento del Release model/v4 (la fecha real de extracción no se registró) | 1 | caché histórica (cache_meteo_era5_land_2017_2025); fecha de congelamiento de la ficha de la V4 |
| ERA5-Land 2026 (hasta el 31 de octubre) | ERA5-Land 0,1° vía Open-Meteo (archive API, models=era5_land), variables diarias | 2026-11-12 | congelamiento del Release model/v4 (la fecha real de extracción no se registró) | 1 | caché histórica (cache_meteo_era5_land_2026); fecha de congelamiento de la ficha de la V4 |

## Cobertura por distrito

Completitud de cada distrito y proporción de semanas con casos verificados.

| UBIGEO | Semanas | Completas | Completitud | Casos verificados |
|---|---|---|---|---|
| 200101 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200104 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200105 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200107 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200108 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200109 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200110 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200111 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200114 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200115 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200201 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200202 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200203 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200204 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200205 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200206 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200207 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200208 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200209 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200210 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200301 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200302 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200303 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200304 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200305 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200306 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200307 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200308 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200401 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200402 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200403 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200404 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200405 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200406 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200407 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200408 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200409 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200410 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200501 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200502 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200503 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200504 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200505 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200506 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200507 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200601 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200602 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200603 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200604 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200605 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200606 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200607 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200608 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200701 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200702 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200703 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200704 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200705 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200706 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200801 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200802 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200803 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200804 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200805 | 469 / 469 | 469 | 100,00 % | 100,00 % |
| 200806 | 469 / 469 | 469 | 100,00 % | 100,00 % |

## Casos antes de asignar ceros

De 30485 semanas distritales, 9564 (31,37 %) tienen un conteo en la fuente y 20921 recibieron cero en la unión. Las semanas de un distrito sin notificaciones reciben cero en la unión (relleno selectivo; el archivo de cobertura las marca verificadas). La completitud de `casos` del panel es 100 % por construcción; esta es la proporción con un conteo en la fuente antes de esa asignación. Es un criterio de lectura a confirmar: un cero verificado de vigilancia no se trata como dato faltante.

Semanas con cero casos en el panel: 23872 (el archivo de cobertura distingue los ceros verificados).

## Transformaciones

- **Casos confirmados del CSV (hasta 2024)** (`data/processing/epi_cases.py`): Se filtran las notificaciones de Piura con tipo_dx = C, se valida UBIGEO, año y semana (un valor inválido detiene el proceso, no se descarta) y se cuentan por UBIGEO, año y semana; las filas repetidas se suman.
- **Casos confirmados de la Sala (desde 2025)** (`data/processing/epi_sala.py`): Series distrito-año de la Sala Situacional normalizadas por semana epidemiológica; las semanas fuera del calendario del modelo se conservan en el silver de la Sala y no se asignan a otra semana.
- **Unión con el panel** (`data/processing/merge.py`): Los casos se unen al panel de clima y sociodemografía por UBIGEO, año y semana; el relleno selectivo marca en el archivo de cobertura qué ceros están verificados.
- **Clima semanal** (`data/processing/weekly_aggregation.py`): Los valores diarios se agregan por semana epidemiológica y distrito.
- **Sociodemografía anual** (`data/processing/socio_interpolation.py`): Las fracciones con valores en 2017 y 2025 se interpolan entre ambos extremos.
