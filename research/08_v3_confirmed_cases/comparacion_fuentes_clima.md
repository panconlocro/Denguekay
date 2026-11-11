# Comparación de fuentes climáticas y cobertura costera

Auditoría del 9 de noviembre de 2026, posterior al [piloto de exposición](piloto_clima.md). El criterio de selección para el panel principal combina cobertura de los 65 distritos, serie histórica y reciente, y disponibilidad de temperatura media y humedad relativa. La concordancia con estaciones se usa como comprobación local. Los resultados de dengue quedan fuera de la selección de la fuente.

## Cobertura regional

| Producto | Variable y resolución | Cobertura observada en el piloto | Rol propuesto |
|---|---|---|---|
| CHIRPS v3 sat | Lluvia a 0,05° | 65 distritos y 1 400 semanas en el silver existente | Precipitación del panel |
| ERA5-Land por Open-Meteo | Temperatura y humedad a 0,1° | 21 de 349 celdas sin las cuatro variables en la semana del 12 de marzo de 2023. Cinco distritos por debajo de 95 % de población cubierta. Mínimo de 70,9 % en Máncora | Contraste de resolución sobre soporte común |
| ERA5 global | Temperatura y humedad a 0,25° | Las 72 celdas que intersectan Piura fueron válidas en la semana común. El panel armado tiene valores válidos para los 65 distritos durante 1 400 semanas | Candidato principal para temperatura y humedad |
| CHIRTS-ERA5 | Tmax y Tmin diarias a 0,05° | Para las semanas del 12 de marzo de 2023 y del 18 de octubre de 2026, al menos 99,65 % de población cubierta en todos los distritos. 100 % en Máncora y Lobitos | Sensibilidad de temperatura extrema |
| PISCOt v1.2 | Tmax y Tmin diarias a 0,01° | Para la semana del 15 de marzo de 2020, 100 % de la población estimada cubierta al redondeo reportado. Se marcaron como faltantes seis pares celda-día con Tmax menor que Tmin. La edición publicada llega a 2020 | Contraste de temperatura en el tramo histórico |

La máscara oficial de ERA5-Land coincide con los centros de la grilla de 0,1°. De las 21 celdas vacías vía Open-Meteo, cuatro tienen más de 99 % de tierra en esa máscara. Dos celdas con datos tienen menos de 50 % de tierra. Por ello una regla de fracción de tierra sola es insuficiente para explicar o reconstruir el patrón observado. La consulta horaria directa a Copernicus respondió HTTP 401. La comparación con el archivo horario oficial para esas celdas queda pendiente de una sesión autorizada. [ERA5-Land y máscara oficial](https://confluence.ecmwf.int/spaces/CKB/pages/140385202/ERA5-Land%2Bdata%2Bdocumentation) · [CHIRTS-ERA5](https://www.chc.ucsb.edu/data/chirts-era5) · [PISCOt v1.2](https://www.nature.com/articles/s41597-023-02777-w)

## Cotejo puntual con observaciones

Se cotejó la celda más cercana a cada aeropuerto con las observaciones diarias NOAA GSOD de Piura y Talara. Se usaron siete días por estación y periodo. Se compararon ERA5, ERA5-Land y CHIRTS en marzo de 2023, y ERA5, ERA5-Land y PISCOt en marzo de 2020. Las temperaturas de ERA5 se consultaron en UTC para este cotejo. La hora de referencia de los extremos publicados por PISCOt y CHIRTS se debe confirmar al ampliar la evaluación. El resultado no establece independencia de observaciones respecto al desarrollo o la asimilación de los productos. [NOAA GSOD](https://www.ncei.noaa.gov/access/metadata/landing-page/bin/iso?id=gov.noaa.ncdc%3AC00516)

- En 2023, CHIRTS tuvo el menor error absoluto medio de Tmax en Piura y Talara (0,85 y 0,91 °C). En Talara tuvo el mayor error de Tmin (7,87 °C). Para temperatura media, ERA5 tuvo menos error que ERA5-Land en ambas estaciones.
- En 2020, ERA5-Land tuvo menos error de temperatura media que ERA5 en ambas estaciones. PISCOt tuvo el menor error de Tmin en Piura por un margen pequeño (1,81 °C frente a 1,83 °C de ERA5) y el mayor error de Tmin en Talara (3,28 °C).
- Las estaciones cubren la costa. La comparación no permite ordenar la precisión en sierra ni validar la humedad relativa de los productos. Los valores se reportan como piloto de exposición, con resultados diarios por fuente y estación.

## Sensibilidad de relleno

En la semana común de 2023 se completó únicamente la temperatura media faltante de ERA5-Land con el valor de la celda ERA5 más cercana. Esta variante queda separada y sin corrección de sesgo. Cambió la media semanal de Máncora en **+0,39 °C**, Lobitos en **+0,24 °C** y Los Órganos en **+0,17 °C**. El relleno acredita que una alternativa cambia la exposición estimada y recupera el soporte poblacional. Para adoptar un relleno haría falta verificar su sesgo en celdas costeras observadas y con estaciones, registrar la fracción completada y mostrar el resultado con la serie de una sola fuente.

## Candidato semanal listo para evaluar

Se recuperaron **9 676 días locales completos** de ERA5 horario de Earthmover hasta el 29 de junio de 2026 y se completó el resto de la serie con ERA5 horario vía Open-Meteo. El empalme usa los mismos 72 centros y el mismo cálculo de humedad relativa por hora a partir de temperatura y punto de rocío. Antes de unir, se fijaron tolerancias para el percentil 95 y el máximo de las diferencias. En ocho días y 72 celdas de solape, la diferencia máxima fue **0,043 °C** en temperatura media y **0,126 puntos porcentuales** en humedad, dentro de los límites fijados. Se conserva el identificador de entrega por semana y los insumos tienen SHA-256. [Archivo público ERA5 de Earthmover](https://registry.opendata.aws/earthmover-era5/) · [ERA5 en Copernicus](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels?tab=overview) · [Open-Meteo histórico](https://open-meteo.com/en/docs/historical-weather-api)

El candidato tiene **91 000 filas** únicas, 65 distritos y 1 400 semanas entre el 2 de enero de 2000 y el 25 de octubre de 2026. Incluye temperatura media, media de máximas y mínimas diarias y humedad relativa media, cada una por área y por población. Los días se agregaron en hora de Perú. Para ponderar por población se usa el raster WorldPop del año de referencia más reciente entre 2000, 2005, 2010, 2015 y 2020, según el año de inicio de cada semana. Se mantiene 2020 después de ese año. Son estimaciones retrospectivas y se puede probar una ponderación de época fija para verificar que los resultados no dependan de los saltos entre rasters. La fecha de disponibilidad de ERA5 queda explícitamente marcada como proxy de sábado más cinco días. [WorldPop histórico](https://hub.worldpop.org/Global1_2000-2020)

**Decisión para llevar a la comparación del paper.** Usar CHIRPS para lluvia y ERA5 global ponderado por población para temperatura y humedad en el panel principal de Piura. ERA5-Land y CHIRTS sirven para sensibilidades sobre filas y periodos comunes. PISCOt sirve para un contraste histórico de extremos. La resolución de 0,25° puede suavizar gradientes entre costa y sierra. El paper debe reportar este límite, el cotejo de estaciones disponible y los controles espaciales de la siguiente fase.

### Detalle distrital que conserva la grilla

Con los pesos WorldPop 2020, las celdas de mayor peso en ERA5 global son 31 para los 65 distritos. En 51 distritos, la celda de mayor peso también es la principal de otro distrito. En 13 distritos una celda aporta al menos 90 % del peso y en siete aporta todo el peso. Bellavista de la Unión, Bernal y Rinconada Llicuar comparten series semanales idénticas de temperatura media y humedad ponderadas durante todo el panel. Catacaos y La Arena tienen una diferencia absoluta mediana de 0,012 °C en la temperatura semanal desde 2020, aunque sus pesos difieren.

Con la máscara observada de ERA5-Land de la semana del 12 de marzo de 2023 y los mismos pesos poblacionales de referencia, la celda dominante se comparte en 22 distritos y tres concentran al menos 90 % de peso en una celda válida. La mayor separación espacial viene con la cobertura parcial documentada. Las celdas de la grilla ERA5 global de 0,25° miden aproximadamente 28 km de lado en Piura.

La cobertura uniforme justifica conservar ERA5 global como referencia completa. Para evaluar la pérdida de detalle térmico, se comparará con CHIRTS-ERA5 y ERA5-Land sobre las mismas filas y con la misma definición de máximas y mínimas diarias, manteniendo fijas la humedad, la lluvia y las covariables estáticas. El cotejo con estaciones y la cobertura se fijarán antes de usar las métricas del modelo para interpretar las diferencias.

### Prueba que aísla la resolución

Para separar el efecto de la resolución del efecto de cambiar de producto, se compararon los mismos datos CHIRTS-ERA5 a 0,05° y tras agregarlos a 0,25° en bloques completos de 5 × 5. Se aplicó una media por superficie en cada bloque y se conservaron la máscara original y los pesos WorldPop. La grilla gruesa se anida en CHIRTS y su origen es distinto del de ERA5. Se usaron los 65 distritos y las mismas dos semanas de marzo de 2023 y octubre de 2026.

| Media semanal | Pares distrito-semana | Mediana absoluta del cambio | Máximo absoluto | Pares con cambio mayor a 1 °C |
|---|---:|---:|---:|---:|
| Tmax diaria | 130 | 0,26 °C | 1,72 °C | 6 |
| Tmin diaria | 130 | 0,36 °C | 1,87 °C | 7 |

La comparación mantiene idéntica la cobertura por superficie y población y reproduce los valores archivados a 0,05°. Esto demuestra que el tamaño de celda cambia la exposición estimada en algunos distritos. La prueba predictiva comparará primero ambas grillas con el mismo diseño y, después, la señal gruesa con y sin la diferencia fina. En ambos contrastes se mantienen fijas las covariables distritales, la lluvia y la humedad. El análisis requiere completar el histórico común antes del ajuste. El piloto se reproduce con `research/08_v3_confirmed_cases/code/chirts_resolution.py`.

### Reproducción con los insumos guardados

Las tablas y los insumos quedan bajo `models/experimentos/mejora_modelo/v3_confirmados/piloto_clima/`. Los archivos de PISCOt se obtienen con `fetch_pisco_pilot.py` en un entorno con h5py. El histórico de ERA5 se obtiene con `era5_historical.py` usando icechunk, xarray, zarr y pcodec. El tramo reciente se obtiene con `era5_recent.py`. La auditoría y la agregación semanal se pueden repetir desde los recortes guardados con el entorno del proyecto.

```bash
pilot_dir=models/experimentos/mejora_modelo/v3_confirmados/piloto_clima
.venv/bin/python -B research/08_v3_confirmed_cases/code/compare_coastal_sources.py "$pilot_dir/fuentes_costa/insumos" --pisco
.venv/bin/python -B research/08_v3_confirmed_cases/code/assemble_era5_candidate.py "$pilot_dir/candidato_era5/insumos"
```
