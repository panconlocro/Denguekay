# Réplica histórica y controles espaciales del clima

Protocolo fechado el 10 de noviembre de 2026 antes de calcular los nuevos resultados. Se usan confirmados, 65 distritos, el calendario disjunto y las cinco semillas del protocolo. La inferencia corresponde a temporadas retrospectivas que ya intervinieron en el desarrollo.

## Dos lecturas distintas

- **Réplica histórica.** Reajustar L + 5a, b3 y d3 con los hiperparámetros heredados compartidos. Reproducir sus variables originales y su alineación respecto del origen, incluidas las temperaturas y la humedad del punto de ERA5-Land y la lluvia CHIRPS por área. Preservar el supuesto retrospectivo original para los predictores que llegan después del sábado y cuyo retraso se modeló con una tolerancia de 14 días. El modelo operativo d3 se muestra junto a b3, elegido por la regla histórica.
- **Control espacial.** Agregar a todos los brazos latitud, longitud y elevación del DEM fijo. Usar las variables originales de b3 y d3 pero aplicar dos semanas de rezago a las observaciones semanales, con verificaciones de disponibilidad al cierre. Niño 1+2 se selecciona por fecha disponible. Esta comparación fija producto y estadístico y cambia disponibilidad y controles de forma explícita. El estudio independiente de CHIRTS aporta la sensibilidad de resolución.

## Placebos y anomalías

- Se toma un año donante previo, separado por uno a cuatro años, con el mismo número de semana MMWR del origen. Una realización elige el mismo desfase para toda una temporada de orígenes y todos los distritos. Así se mantienen juntas las ventanas de temperatura y el patrón espacial de cada fecha. Si la SE 53 falta en el año donante, se usa su SE 52. Se archivan las fechas donantes y se comprueba que todas sean anteriores.
- La temperatura placebo de b3 sustituye solo la temperatura. Se corren tres calendarios con semillas 20261110, 20261111 y 20261112. El placebo conjunto de b3 traslada en bloque temperatura, lluvia, humedad y Niño 1+2, con la primera semilla. El placebo de d3 traslada juntas sus cuatro ventanas con la primera semilla.
- La variante de anomalías de b3 sustituye temperatura absoluta por su desviación respecto de la media de la misma semana del distrito, estimada exclusivamente con los orígenes del entrenamiento de cada bloque. Para una SE 53 ausente del entrenamiento se toma como referencia la SE 52. Lluvia, humedad, Niño 1+2 y geografía permanecen iguales.
- La comparación primaria del control es b3 observado frente a historia y geografía y frente a su placebo de temperatura. Se reportan cada una de las tres realizaciones y la mediana de los contrastes por temporada, además de la lectura sin 2026. El placebo conjunto, d3 y las anomalías tienen lectura separada. La plausibilidad de la forma térmica se examinará con efectos locales acumulados de la probabilidad cruda, con bins fijados en el entrenamiento de temporada 2023, h4 y semilla 17.

Las métricas se comparan por temporada y horizonte sobre las mismas filas, con Brier calibrado como métrica primaria y precisión promedio como apoyo. Se conservan la predicción cruda, la calibrada y la mezcla de conteos. La estabilidad entre realizaciones del placebo se interpreta descriptivamente. La búsqueda simétrica se fija en un protocolo separado, con presupuesto establecido tras cronometrar solo el desarrollo.
