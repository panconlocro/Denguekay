# Piloto de exposición climática en Piura

Piloto de la fase 1 realizado el 9 de noviembre de 2026. Atiende la parte de medición del comentario 8 y prepara los controles del comentario 11. Las diferencias de exposición se midieron sin evaluar el Brier ni elegir variantes por el resultado del modelo.

## Qué se comparó

- Se usaron los 65 polígonos COD-AB, la grilla de 0,1° distribuida para ERA5-Land y el raster WorldPop Perú 2020 de conteos por píxel de aproximadamente 1 km. Hay **349 celdas meteorológicas únicas** y **696 intersecciones distrito-celda**. Se verificó que la suma de los pesos de población reproduce el conteo del raster dentro de cada distrito. WorldPop 2020 se eligió para el piloto posterior a 2020. El año y la versión aplicables al histórico anterior siguen por fijar. Los pesos describen distribución de población y se mantienen separados del denominador distrital para tasas. [WorldPop Perú 2020](https://hub.worldpop.org/geodata/summary?id=38239)
- Se compararon Piura, Catacaos y Paita en la costa y Ayabaca, Huancabamba y Canchaque en la sierra. Se descargaron 91 celdas para ocho semanas del 12 de marzo al 8 de abril y del 9 de julio al 5 de agosto de 2023. Se usaron semanas domingo–sábado con días de Perú. Se guardaron temperatura y humedad medias, medias semanales de mínimas y máximas diarias y rango diurno medio.
- Los métodos fueron el punto del archivo original con las opciones por defecto, la celda más cercana al mismo punto sin corrección de elevación, el promedio por superficie de intersección y el promedio ponderado por población. Las tres últimas opciones consultaron centros de celdas con ERA5-Land fijo, `cell_selection=nearest` y `elevation=nan`. Se verificaron las coordenadas devueltas, las unidades y todos los días solicitados. La comparación por área usa superficie en EPSG:6933. La comparación por población distribuye los conteos de WorldPop por la fracción de cada píxel que intersecta el polígono y la celda meteorológica. [Documentación de Open-Meteo](https://open-meteo.com/en/docs/historical-weather-api)
- El punto original reprodujo la temperatura y humedad semanales archivadas de las 48 combinaciones distrito-semana, dentro de la precisión numérica. La comparación entre la celda más cercana y los promedios ponderados separa el efecto de agregar espacialmente del ajuste aplicado al punto original.

## Diferencias observadas

Mediana de las diferencias absolutas en las 24 observaciones distrito-semana de cada zona.

| Contraste | Temperatura costa °C | Temperatura sierra °C | Humedad costa pp | Humedad sierra pp |
|---|---:|---:|---:|---:|
| Área frente a la celda más cercana | 0,17 | 0,46 | 0,34 | 1,04 |
| Población frente a la celda más cercana | 0,25 | 0,68 | 0,55 | 1,22 |
| Población frente al punto original | 0,21 | 1,44 | 0,55 | 1,57 |

En Canchaque, la temperatura ponderada por población fue hasta **3,30 °C menor** que la serie original. Parte de la diferencia ya aparece al cambiar del punto original a la celda más cercana sin corrección de elevación. A grilla y configuración comparables, la mayor diferencia entre población y celda más cercana fue **1,24 °C** para temperatura y **5,53 puntos porcentuales** para humedad. Las magnitudes muestran el impacto de la medición espacial. La comparación con estaciones y el aporte predictivo se evalúan por separado.

## Cobertura y disponibilidad

- Se consultaron las 349 celdas regionales para la semana del 12 de marzo de 2023. Los 65 distritos tuvieron al menos una celda válida y la máscara de celdas válidas fue estable durante esos siete días. Diez distritos tuvieron cobertura parcial. Cinco quedaron por debajo de 95 % de la población representada, con **70,9 %** en Máncora, **73,7 %** en Lobitos y **90,3 %** en Paita. El promedio del piloto se renormaliza sobre el soporte válido y la cobertura se guarda por separado. Para la serie final hay que fijar el tratamiento de esas zonas antes de evaluar el desempeño.
- El silver de CHIRPS tiene 91 000 filas y 65 distritos por semana. Todas las fechas del campo `fecha_disponible` coinciden con el proxy de fin de péntada más cinco días, tanto para 90 675 filas finales como para 325 preliminares. El proxy queda entre 5 y 10 días después del sábado de la semana observada. Al aplicar el corte estricto de sábado del calendario común, la lluvia de esa semana cae después del corte en **1 001 de 1 001** orígenes distintos, la semana anterior en **410 de 1 001** y dos semanas atrás en **0 de 1 001**. El resultado vale para ese proxy. Las fechas reales de publicación y la versión disponible en el momento requieren evidencia del proveedor o snapshots. [Metodología de CHIRPS v3](https://chc.ucsb.edu/data/chirps3)
- En el inventario público de SENAMHI, los historiales visibles para Miraflores y Ayabaca terminan en 2013 y 2014, respectivamente. Los histogramas consultados quedan fuera de las semanas del piloto. La validación requiere series fechadas con solape y la comparación de la estación con la celda de su ubicación, además de la lectura distrital. [Inventario de SENAMHI](https://www.senamhi.gob.pe/site/descarga-datos/map_hist_data.php)

## Temperatura CHIRTS-ERA5

Se recuperaron los 28 GeoTIFF diarios de mínima y máxima para las semanas del 12 al 18 de marzo de 2023 y del 18 al 24 de octubre de 2026. El proveedor permite peticiones HTTP por rangos. Algunas lecturas parciales requirieron reintentos y, en un caso, se recuperó el TIFF original para recortarlo localmente. Los 28 recortes se conservaron con sus hashes. El mínimo de cobertura válida en CHIRTS-ERA5 fue **99,7 %** del área en Paita. En los otros cinco distritos fue 100 % en el piloto. [Producto y método de CHIRTS-ERA5](https://www.chc.ucsb.edu/data/chirts-era5)

La comparación usa la media semanal de las máximas o mínimas diarias y aplica ponderación por superficie a cada grilla. ERA5-Land se consultó en UTC para esta comparación por fecha del producto. La comparación local del punto original usa la zona horaria de Perú y se reporta aparte. En 12 pares distrito-semana, las medianas de las diferencias absolutas fueron **2,68 °C** para la máxima diaria y **2,90 °C** para la mínima. Los máximos de esas diferencias fueron **5,45 °C** y **5,69 °C** en Huancabamba. Las fuentes comparten los límites distritales y pueden tener distinta cobertura válida dentro de ellos. Para comparar exclusivamente las fuentes en distritos costeros se debe delimitar un soporte espacial común.

La extracción CHIRTS-ERA5 es viable para una sensibilidad de temperatura. La diferencia entre productos requiere validación local con observaciones comparables antes de decidir qué exposición usar en el análisis principal. La disponibilidad se comprobó al momento de la descarga. Los metadatos de modificación de los archivos pueden corresponder a revisiones y no indican necesariamente la primera publicación.

## Salidas y trabajo restante

El piloto queda en `models/experimentos/mejora_modelo/v3_confirmados/piloto_clima/`. El manifiesto archiva el SHA-256 de los polígonos, coordenadas y raster de población. Las salidas incluyen los pesos, el clima semanal de los seis distritos, el control con el silver, la cobertura regional de una semana, los recortes de CHIRTS y la comparación por fuente. Para reproducir la comparación de disponibilidad de lluvia se usa la auditoría previa de cortes.

```bash
.venv/bin/python -B research/08_v3_confirmed_cases/code/audit_revision_inputs.py
.venv/bin/python -B research/08_v3_confirmed_cases/code/pilot_climate_exposure.py --worldpop /ruta/worldpop2020.tif
.venv/bin/python -B research/08_v3_confirmed_cases/code/pilot_climate_exposure.py --solo-cobertura-regional
.venv/bin/python -B research/08_v3_confirmed_cases/code/fetch_pilot_chirts.py /ruta/chirts
.venv/bin/python -B research/08_v3_confirmed_cases/code/pilot_climate_exposure.py --solo-chirts --chirts /ruta/chirts
```

Se conserva ERA5-Land como referencia de humedad. Completar las 349 celdas para todo el histórico equivale aproximadamente a 244 300 unidades de una ubicación por 14 días según la regla publicada de Open-Meteo, antes de considerar la máscara y las variantes del punto original. La extracción regional de ERA5-Land horario de Copernicus permite recortar a Piura y requiere una sesión autorizada. Con los datos horarios se calcularía humedad relativa por hora usando temperatura y punto de rocío y luego se agregaría al día peruano y la semana. Para cerrar la fase queda construir el histórico, fijar el peso de población y el criterio de cobertura para la costa, y buscar observaciones de estación con solape. [Cuotas de Open-Meteo](https://open-meteo.com/en/pricing) · [ERA5-Land horario en Copernicus](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land?tab=download)
