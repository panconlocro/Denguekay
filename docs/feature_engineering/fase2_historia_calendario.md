# Fase 2 — historia propia y calendario

**Estado:** fase 2 ejecutada; revisión de Rosa pendiente antes de fase 3. El [notebook 18](../../notebooks/18_fe_historia_calendario.ipynb) se ejecutó sobre el integrado actual. Las [métricas](metricas/fase2_historia_calendario.json) y la [figura](figuras/fase2_historia_calendario/01_reglas_por_horizonte.png) quedan junto a este informe. No se escribió en `data/gold/`.

## Método

La función `construir_historia_calendario()` en `src/modeling/historia_calendario.py` produce, para cada horizonte `h ∈ {2, 4}`, los casos de `t−h`, de `t−h−1`, la media de cuatro semanas y el número de semanas con casos en la ventana `t−h−3 … t−h`. Conserva `ubigeo`, `anio`, `semana`, `semana_inicio` y las fechas del origen. Añade seno y coseno de la semana epidemiológica objetivo, que se conoce de antemano. La semana 53 se representa en el mismo punto circular que la semana 1; la columna original `semana` permanece en el panel para probar una representación alternativa más adelante.

Los primeros valores sin historia suficiente quedan como `NaN`. Cada grupo se calcula dentro de su UBIGEO y se ordena por fecha. Se supone provisionalmente que los casos de una semana están disponibles al cierre de esa semana: el panel no contiene fecha de publicación por observación. Antes de usar una feature en operación habrá que verificar su fecha efectiva de publicación.

Para comparar reglas simples se calculó el error absoluto en `log1p(casos_Dengue)` de: persistencia `casos(t−h)`, media de las cuatro semanas que terminan en el origen y mismo distrito/semana epidemiológica del año anterior. Se usaron las mismas **27 105 filas** para cada regla y cada horizonte, desde 2018, porque la regla estacional requiere un año previo. Son reglas sin parámetros aprendidos; la comparación es retrospectiva y no estima todavía el aporte de las variables a XGBoost.

## Hallazgos

1. **La historia se alinea sin perder filas ni cruzar distritos.** El panel conserva 30 485 filas y llaves únicas. A `h=2`, 30 355 filas tienen el caso en el origen y 30 160 tienen además cuatro semanas para la media. A `h=4`, las cifras son 30 225 y 30 030. Las primeras 325 y 455 filas, respectivamente, carecen de ventana completa.
2. **La persistencia es la regla simple más precisa en ambos horizontes.** En las filas comunes, su MAE `log1p` fue **0,1650** a dos semanas y **0,2084** a cuatro. La media de cuatro semanas obtuvo **0,1867** y **0,2326**; el comparador estacional, **0,5254** en ambos. El resultado a cuatro semanas reproduce aproximadamente el 0,208 y 0,525 del EDA, con el mismo criterio de comparación. La media como predicción autónoma queda por detrás, aunque puede aportar contexto a un modelo junto con el último valor.
3. **El error cambia bastante por temporada.** Para persistencia, temporadas 2022, 2023, 2024 y 2025 dan MAE de **0,2428 / 0,3103 / 0,3710 / 0,1578** a dos semanas, y **0,3145 / 0,4385 / 0,4824 / 0,1656** a cuatro. Cada temporada va de la semana 35 del año anterior a la 34 del año indicado; por tanto, la temporada 2025 incluye semanas de fines de 2024. Si se agrupa por año calendario, 2025 da **0,1153** y **0,1218**, respectivamente. La media de cuatro semanas tampoco supera a persistencia en las temporadas 2022–2024. El promedio global mezcla temporadas de distinta intensidad; se deberán reportar resultados por temporada en el modelado. Los casos de 2025 se aceptan como válidos según la decisión de Rosa; un error bajo en un periodo tranquilo no demuestra desempeño durante un brote.
4. **El calendario se puede construir sin observar el futuro.** Seno y coseno dependen solo de la semana objetivo. Su aporte frente a la columna original `semana` todavía no está medido; hará falta un modelo ajustado dentro de cortes temporales para compararlos. La semana 53 y el calendario oficial de la Sala antes de extender a 2026 siguen requiriendo revisión.
5. **Un ejemplo de frontera temporal pasó la auditoría.** Para `ubigeo=200101`, objetivo 2025-S52 (2025-12-21), el origen a cuatro semanas es 2025-S48 (2025-11-23, cierre 2025-11-29). `casos_lag_4=1`, `casos_lag_5=1`, media de S45–S48 `=0,75` y tres semanas positivas. Cambiar casos posteriores a S48 no modifica esas variables; se comprobó en pruebas sintéticas.

## Propuesta para las fases siguientes

Conservar como candidatos pequeños los dos rezagos, la media y el conteo de semanas positivas. Se medirá su aporte mediante ablaciones temporales; el peor desempeño de la media como regla autónoma no la descarta como predictor. Probar `semana` frente al par seno/coseno en un modelo de prueba cuando corresponda, sin ajustar ninguna estadística estacional con semanas de validación. Los valores `NaN` iniciales se mantendrán explícitos hasta definir el conjunto de entrenamiento por horizonte.

Rosa decidió que la alerta identifica cada semana distrital con nivel elevado de casos; sigue pendiente su umbral concreto. También están abiertos el esquema de test final, el significado de los ceros históricos y la latencia de publicación. Las fases 3 de vecinos y jerarquía y 4 de clima se completaron después.

**Comprobación:** notebook ejecutado de principio a fin; 78 pruebas unitarias aprobadas; una implementación independiente por bucle reprodujo las 27 105 filas comunes y las MAE de persistencia y media a dos y cuatro semanas.
