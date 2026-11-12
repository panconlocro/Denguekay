# Transferencia del pronóstico de Piura a Lambayeque y Tumbes

La prueba mide si el paquete ajustado en Piura conserva su habilidad en otros departamentos. La pregunta climática se evalúa con el par emparejado de historia y geografía y el brazo `b3`. La política de alertas se compara con persistencia en las mismas filas. Los resultados se informarán por departamento, temporada y horizonte de 2, 3 y 4 semanas.

## Congelamiento en Piura

El contraste principal del manuscrito usa `b3` y su par sin clima con hiperparámetros fijos. El ajuste simétrico es una sensibilidad. Para materializar el paquete se debe acordar cuál configuración se traslada, el último origen de entrenamiento, el uso de las cinco semillas o su regla de agregación y el corte de alerta por horizonte. La decisión se registra antes de puntuar los destinos.

Se ajusta el paquete en Piura con los datos que corresponden al corte y se guardan los modelos, el orden de variables, las ventanas y reglas de disponibilidad, los parámetros de dispersión y calibración, la mezcla de conteos y los cortes de alerta. Se guardan también los parámetros que necesiten los comparadores probabilísticos, las reglas de persistencia, los hashes de código e insumos y el entorno. Una comprobación de inferencia local debe reproducir las predicciones generadas al guardar el paquete. Los pronósticos retrospectivos archivados se ajustaron por corte y no contienen por sí solos un paquete único de inferencia.

## Auditoría de insumos previa a la evaluación

Se revisó el CSV nacional `DatosDengueV2.csv` filtrando `tipo_dx=C` y el ZIP nacional COD-AB del IGN publicado por OCHA. Se verificaron los UBIGEO y el calendario MMWR sin calcular pronósticos ni métricas de desempeño.

| Departamento | Distritos COD-AB | Distritos con algún confirmado y polígono | Primer registro confirmado con semana válida | Último registro confirmado con semana válida |
|---|---:|---:|---|---|
| Lambayeque | 38 | 37 | 2001-SE05 | 2025-SE53 |
| Tumbes | 13 | 13 | 2000-SE19 | 2025-SE53 |

Los 51 polígonos tienen geometrías válidas. Todos los UBIGEO con confirmados coinciden con polígonos. El UBIGEO 140203 carece de confirmados en esta copia. La ausencia de notificaciones requiere verificar cobertura antes de completar el panel. Lambayeque tiene cinco notificaciones confirmadas con semana fuera de la grilla MMWR. Se deben reconciliar con la fuente o excluirlas con un registro explícito de la decisión. Las fechas de la tabla indican extremos observados de notificación.

- CSV nacional, SHA-256 `7865e8b2f5a7aef1e8dce159444891f2c2e59b311d574f28c55aaca5a9abb8ba`.
- ZIP COD-AB, SHA-256 `2f0ec51b7a0899b407546aa644621e1c3255cba59fdda76fcde6975ca6baafb3`.

Desde la raíz, con el entorno del proyecto y rutas a las copias locales:

```bash
python -m pip install -e .
python -B research/08_v3_confirmed_cases/code/audit_northern_transfer_inputs.py \
  --cases /ruta/DatosDengueV2.csv \
  --boundaries /ruta/per_admin_boundaries.geojson.zip
```

## Preparación de la prueba

1. Confirmar un periodo común posterior al corte del paquete. Si el ajuste incorpora Piura de 2026, el CSV auditado sirve para reconstruir historia local y se necesitan observaciones externas más recientes para puntuar. Si se quiere probar años ya cerrados, se requiere un corte de entrenamiento anterior en Piura y se reporta como transferencia retrospectiva.
2. Verificar cobertura del origen epidemiológico y continuidad de UBIGEO. Cuando se extienda la serie con la Sala, extraer solo confirmados y comprobar el tramo de solape por departamento.
3. Calcular la exposición con las fuentes, la resolución y las reglas del brazo que se congele. Preparar lluvia CHIRPS por intersección de celdas y polígonos, temperatura ERA5-Land con la regla del brazo y las covariables estáticas. Auditar fechas de disponibilidad, cobertura espacial y valores fuera del rango de entrenamiento de Piura.
4. Construir la historia local y el umbral de evento con la misma receta en cada distrito. Aplicar los modelos y calibradores de Piura sin reentrenar con datos de los destinos. Verificar llaves idénticas entre los brazos y reportar Brier pareado, AP, recall y costo de alertas con cortes fijados en Piura.

## Transferencia retrospectiva de 2025

Especificación fijada antes de puntuar los destinos.

- **Periodo.** SE 01–38 de 2025, con semanas objetivo que empiezan del 29 de diciembre de 2024 al 14 de septiembre de 2025. Es el primer tramo continuo del año con alguna notificación en ambos departamentos. Desde la SE 39 aparecen semanas sin ninguna notificación en Lambayeque. La prueba usa los casos históricos revisados como aproximación a los que se habrían observado en cada origen.
- **Corte común.** 7 de diciembre de 2024, primer cierre de origen de h4. Los tres objetivos de cada fila multisalida de entrenamiento deben haber cerrado a esa fecha. Los calibradores Platt y los pesos de la mezcla se ajustan con pronósticos fuera de muestra de Piura cuyas etiquetas ya cerraron para ese mismo corte.
- **Brazos.** `b3_obs` y `historia_geo` con los parámetros fijos del análisis principal, cinco semillas, persistencia determinista y persistencia probabilística calibrada en Piura. El corte de alerta es 0,50. Se reportan Brier, AP, MAE, detecciones y falsas alertas por departamento, horizonte y semilla. La variación entre semillas es descriptiva.
- **Soporte.** 37 distritos en Lambayeque y 13 en Tumbes. El distrito 140203 se excluye del soporte principal porque el CSV no contiene notificaciones de ningún diagnóstico en 2020–2024. Se excluyen cinco confirmados de Lambayeque con fechas fuera del calendario MMWR. En los distritos incluidos, una ausencia de filas se codifica como cero *confirmados registrados*. La continuidad departamental no certifica cobertura distrital semanal.
- **Exposición.** CHIRPS v3.0 diario final, desagregación sat, ponderado por intersección con los polígonos COD-AB. ERA5-Land de Open-Meteo en centroides de GADM 4.1, con la misma proyección que Piura. Se usan centroides COD-AB en los seis distritos ausentes de GADM. La elevación se consulta en DEM90 y Niño 1+2 usa la serie común del paper. Se reproducen las reglas de disponibilidad de la retrospectiva de Piura, con sus aproximaciones para los archivos finales.
- **Alcance.** El modelo seleccionado y las fuentes revisadas se reconstruyen retrospectivamente. El resultado mide transferencia a los distritos y semanas evaluados. El paquete de 2025 se guarda como artefacto del experimento.

### Reproducción

En la rama de transferencia, usar el entorno y el código versionado de la revisión de Piura en `paper_pendings`. Los datos, los modelos y los pronósticos se guardan en un directorio local del experimento.

```bash
export PYTHONPATH="/ruta/checkout-piura/src"
export DENGUEKAY_XGB_DEVICE=cpu DENGUEKAY_XGB_NJOBS=2

python -B research/08_v3_confirmed_cases/code/prepare_northern_weather.py \
  --cod-ab /ruta/per_admin_boundaries.geojson.zip --gadm /ruta/gadm41_PER_3.json.zip \
  --output /ruta/insumos --source era5

python -B research/08_v3_confirmed_cases/code/prepare_northern_weather.py \
  --cod-ab /ruta/per_admin_boundaries.geojson.zip --gadm /ruta/gadm41_PER_3.json.zip \
  --output /ruta/insumos --source chirps

python -B research/08_v3_confirmed_cases/code/run_northern_transfer.py fit \
  --piura /ruta/checkout-piura --geography /ruta/geografia_distritos_piura.csv \
  --output /ruta/paquete

python -B research/08_v3_confirmed_cases/code/run_northern_transfer.py score \
  --piura /ruta/checkout-piura --cases /ruta/DatosDengueV2.csv \
  --weather /ruta/insumos --output /ruta/paquete
```

## Extensión retrospectiva de 2026 y sensibilidad a la latitud

Se conserva la comparación de 2025 y se añade 2026 en las SE 01–38, con los mismos 50 distritos y horizontes. La versión con latitud reutiliza los diez archivos XGBoost y parámetros calibrados del paquete de 2025, ajustado en Piura al 7 de diciembre de 2024. Para el tramo de 2026 se usan confirmados semanales de la Sala, con reconciliación de los distritos contra los totales provinciales y departamentales. Se cuantifica el acuerdo con el CSV en el solape de 2025. Las series de clima y casos se alinean por fecha de origen con las reglas de la primera transferencia.

Para medir la contribución predictiva de la latitud se ejecutan dos configuraciones de cada brazo. La sensibilidad retira `lat` y conserva `lon`, elevación, las demás variables, semillas, hiperparámetros y el corte de Piura. Cada configuración sin latitud se reentrena y recalibra en los mismos cortes de Piura. Los desenlaces externos se reservan para puntuar. En cada departamento, año, brazo y horizonte se calcula por semilla el Brier sin latitud menos el Brier con latitud y se resume con la mediana. Un cambio negativo indica menor error al retirarla. Se calcula también el contraste climático pareado en ambas configuraciones. La comparación estima la contribución predictiva de esa variable con el resto de la receta fijo.

La descarga de clima se ejecuta con `--year 2026`. Para el solape epidemiológico se corre `prepare_northern_surveillance.py` con `--year 2025` y `--year 2026`, el mismo archivo COD-AB y un directorio de salida para la Sala. La etapa `fit --without-latitude` crea el segundo paquete. La etapa `score --year 2026 --sala /ruta/sala_2026.csv --overlap /ruta/sala_2025.csv` se ejecuta sobre copias de los dos paquetes y el clima de 2026.

## Sensibilidad con entrenamiento actualizado para 2026

El contraste anterior mantiene fijo el entrenamiento de diciembre de 2024 para comparar dos años. Esta sensibilidad posterior a esa primera evaluación mide el efecto de acercar el ajuste al comienzo de la prueba de 2026. Usa las mismas SE 01–38, los mismos 50 distritos, la misma latitud, cinco semillas, hiperparámetros fijos y umbral de alerta 0,50.

La primera semana objetivo empieza el 4 de enero de 2026. A h4, su origen es la semana que cierra el 13 de diciembre de 2025. Ese es el corte común para ajustar árboles, dispersión, calibradores, mezcla y persistencia probabilística. Se incorporan al ajuste y a la calibración las etiquetas de Piura con semana cerrada para ese corte según el reloj retrospectivo. Los insumos archivados pueden incorporar revisiones posteriores a esas fechas. La receta del paper también se seleccionó retrospectivamente.

El ajuste se ejecuta con `fit --year 2026` y un directorio nuevo. Para cada departamento y horizonte se comparan el Brier y la utilidad operativa del paquete actualizado frente al de 2024, emparejando por semilla y soporte. En ambos paquetes se compara además b3 frente a historia y geografía y a las persistencias. Los cambios describen esta evaluación retrospectiva posterior a la primera corrida.
