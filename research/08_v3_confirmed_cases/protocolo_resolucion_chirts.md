# Contraste predictivo de resolución de CHIRTS en Piura

Protocolo fechado el 10 de noviembre de 2026 antes de calcular métricas de pronóstico de este contraste. Usa confirmados, el calendario semanal disjunto y los cinco valores de semilla del protocolo de revisión. La pregunta principal de esta prueba es si la temperatura de mayor resolución añade información al pronóstico de semanas elevadas, dadas la historia local, la geografía y las demás variables climáticas.

## Entrada y soporte

- Se usa una misma edición de CHIRTS-ERA5, a 0,05° y reagrupada a 0,25° en bloques de 5 × 5. El grueso promedia por superficie y se pondera después con el mismo peso de población y máscara de las celdas finas. Se mantienen los años de referencia de WorldPop del candidato ERA5. Se evalúan medias semanales de Tmax y Tmin diarias en la fecha de CHIRTS. La variante experimental tiene dos extremos térmicos en lugar de la temperatura media diaria del b3 histórico.
- Se enmascaran las parejas celda-día sin ambos valores, las parejas invertidas y los valores fuera de −90 a 57 °C. Una exposición diaria requiere al menos 95 % de la población raster cubierta. Una semana requiere al menos cinco de sus siete días válidos en ambos brazos. Se conserva el número de días y la cobertura. Las semanas faltantes se mantienen explícitas. Para cada origen se usan las cinco semanas consecutivas cuyo último dato se sitúa al menos dos semanas antes del cierre de origen. Si no hay una ventana completa, se conserva un valor faltante en ambas resoluciones y se registra el soporte.
- La lluvia es CHIRPS v3 sat por área y la humedad es ERA5 global ponderada por población. Las dos usan la misma ventana nominal de cinco semanas con dos semanas de rezago. Niño 1+2 se selecciona por su fecha disponible. Este calendario prueba disponibilidad con proxies conservadores de publicación. El origen histórico de los archivos revisados limita la interpretación como una reconstrucción de lo publicado en tiempo real.

## Comparadores

1. Historia local y calendario más latitud, longitud y elevación fija DEM GLO-90 del punto distrital.
2. La misma base más lluvia, humedad y Niño 1+2.
3. El comparador 2 más Tmax y Tmin a 0,25°.
4. El comparador 2 más Tmax y Tmin nativas a 0,05°.
5. El comparador 3 más la diferencia entre la señal fina y la gruesa para Tmax y Tmin.

Se usan los hiperparámetros heredados de la familia b3, con las mismas semillas, orígenes, filas y etiquetas. La calibración Platt de cada horizonte solo usa predicciones previas cuyas etiquetas ya habían cerrado. 2008 entra al historial de calibración y queda fuera de las métricas calibradas. El bloque posterior de 2026 se presenta aparte. Se verifica que las covariables comunes y los faltantes coincidan por UBIGEO y origen.

## Lectura

Se reporta la diferencia pareada de Brier de la variante fina frente a la gruesa y de la gruesa con diferencia fina frente a la gruesa sola. Se toman medianas entre semillas para cada temporada y se agregan las seis temporadas de decisión con igual peso. Se reportan h2, h3 y h4 por separado, el desglose por temporada y la sensibilidad sin 2026 y al omitir cada temporada. El primer contraste mantiene el mismo número de variables térmicas. El segundo mide el valor de la diferencia local después de que el modelo ya conoce la señal gruesa. Se guardan las predicciones y el AP como diagnóstico complementario. La evaluación es retrospectiva sobre temporadas ya inspeccionadas durante V3. Se distingue del cotejo meteorológico con estaciones y de la comparación principal con placebo y tuning simétrico.
