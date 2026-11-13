# Contraste de resolución de CHIRTS con casos confirmados

## Histórico auditado

Se recortó la redistribución pública Zarr de CHIRTS-ERA5 con revisión fija `35669afbbd1c6ab84dcc496f2f95b7cbbf75867f`. El periodo requerido va del **7 de noviembre de 2004 al 3 de octubre de 2026**, 8 001 días. Se descargaron 252 objetos comprimidos (625 MB) correspondientes a la ventana de Piura y se conservaron los recortes de 52 × 48 celdas con sus hashes. El archivo redistribuido conserva temperatura a décimas de grado. En los 14 recortes de marzo de 2023 la máscara coincidió con los GeoTIFF de CHC y la diferencia máxima fue 0,05 °C. El cotejo detectó una discrepancia el 21 de octubre de 2026, posterior al fin de la serie usada. El resultado identifica una edición histórica y conserva esa restricción. [Producto CHIRTS-ERA5](https://www.chc.ucsb.edu/data/chirts-era5) · [Edición del archivo público](https://huggingface.co/datasets/aaguilar90/chirts-era5-daily/tree/35669afbbd1c6ab84dcc496f2f95b7cbbf75867f)

La agregación conserva **74 295 filas** de 65 distritos en 1 143 semanas MMWR, con siete días válidos por fila en ambas resoluciones. La cobertura poblacional diaria mínima fue **97,1 %** y se enmascararon dos pares de extremos invertidos. Engrosar la grilla cambió la media semanal de las máximas y las mínimas en **0,28 °C** y **0,30 °C** de mediana absoluta, respectivamente. Los cambios máximos fueron **2,07 °C** para máximas y **1,89 °C** para mínimas.

La elevación fija del control geográfico se tomó del DEM Copernicus GLO-90 en las coordenadas distritales ya usadas por el proyecto, con latitud y longitud como covariables adicionales. El [protocolo del contraste](protocolo_resolucion_chirts.md) fija las variables, las ventanas, los cortes y la agregación de resultados. [Servicio de elevación Open-Meteo](https://open-meteo.com/en/docs/elevation-api)

El cotejo adicional abarcó máxima y mínima en cuatro fechas repartidas entre 2005, 2015, 2022 y 2026. Los ocho recortes coincidieron en la máscara y dentro de 0,05 °C. La discrepancia detectada fuera del periodo se conserva junto con las muestras que sí se usaron para la validación.

## Resultados fuera de muestra

La corrida incluyó cinco variantes, cinco semillas y 20 bloques. Se verificaron 73 905 orígenes con temperatura, 60 cortes y 194 805 predicciones por combinación de variante y semilla, para un total de 4 870 125 predicciones. Los 65 distritos comparten el calendario disjunto. El primer bloque aporta datos a Platt y queda fuera del Brier calibrado. El resumen usa la tabla de cortes común. Los ajustes se recuperaron después de corregir la referencia al calendario archivado en el primer intento de resumen. Great Expectations validó silver y gold. MLflow registró la corrida `130464e0100043be9ff85568930eb0bd`.

Cada celda muestra el cambio porcentual medio de Brier en seis temporadas, calculado a partir de los cambios pareados y medianos por semilla de cada temporada. Un signo negativo favorece a la candidata. El recuento entre paréntesis indica cuántas de las seis temporadas favorecen a la candidata.

| Contraste | h2 | h3 | h4 |
|---|---:|---:|---:|
| CHIRTS 0,05° frente al mismo CHIRTS 0,25° | −0,35 % (6) | −0,51 % (6) | −0,33 % (5) |
| CHIRTS 0,25° con diferencia fina frente a CHIRTS 0,25° | −0,22 % (5) | −0,25 % (5) | −0,16 % (5) |
| CHIRTS 0,05° frente al mismo bloque climático sin temperatura | −0,70 % (5) | −0,99 % (5) | −0,87 % (5) |
| Clima con CHIRTS 0,05° frente a historia y geografía | −0,44 % (4) | −0,35 % (5) | +0,03 % (3) |

Sin 2026, la comparación 0,05° frente a 0,25° fue −0,37 %, −0,47 % y −0,31 % en h2, h3 y h4. En las temporadas de contraste 2024 y 2025, fuera del conjunto de seis, la comparación fina frente a gruesa produjo mayor Brier en los tres horizontes. El bloque parcial posterior de 2026 se reporta por separado. El resumen de cada omisión, la precisión promedio y las diferencias absolutas están archivados.

## Lectura para el manuscrito

El contraste con la misma fuente aporta evidencia de una **ganancia pequeña por usar detalle térmico en las temporadas de decisión**. La resolución fina también mejora el bloque climático frente al mismo conjunto sin temperatura. Frente a historia y geografía, el bloque climático con temperatura fina ofrece ganancias medias más pequeñas en h2 y h3 y un resultado muy cercano en h4. La selección histórica de temporadas y el contraste desfavorable en 2024 y 2025 limitan la generalización.

La versión fina se conserva como brazo del paper. La variante usa Tmax y Tmin y comparte hiperparámetros heredados. Falta completar el placebo temporal, el ajuste simétrico y la comparación del b3 histórico con el par sin clima. La prueba de resolución complementa esas comparaciones.

## Archivos y reproducción

Las salidas se guardaron en `models/experimentos/mejora_modelo/v3_confirmados/piloto_clima/resolucion_chirts/historico/`. El subdirectorio `pronosticos/` conserva las predicciones, los cortes, las métricas y el manifiesto de MLflow. Para reconstruir el histórico remoto se usa `code/fetch_chirts_history.py` con numcodecs. Los recortes ya guardados permiten repetir la agregación sin llamadas de red.

```bash
history_dir=models/experimentos/mejora_modelo/v3_confirmados/piloto_clima/resolucion_chirts/historico
.venv/bin/python -B research/08_v3_confirmed_cases/code/assemble_chirts_history.py "$history_dir/insumos/chirts_piura_diario.npz"
DENGUEKAY_XGB_DEVICE=cpu DENGUEKAY_XGB_NJOBS=2 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 OMP_NUM_THREADS=2 \
.venv/bin/python -B research/08_v3_confirmed_cases/code/run_chirts_resolution.py \
  "$history_dir/insumos/geografia_distritos.csv" --codigo-ajustes "$history_dir/insumos/codigo_ajustes_original.py"
```
