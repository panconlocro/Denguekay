# Fase 7 — síntesis y traspaso al modelado

**Estado:** completada como síntesis técnica. El [notebook 23](../../notebooks/23_fe_sintesis.ipynb) audita silver, los dos gold y su manifiesto, y reproduce las [métricas de esta fase](metricas/fase7_sintesis.json). Esta fase no ajustó XGBoost, no eligió el test final y no alteró las fuentes silver. El traspaso propone experimentos para la fase de modelado; requiere revisión de Rosa antes de iniciarla.

## Archivos y contrato

El origen es `data/silver/integrado/meteo_socio_epi_piura_2017_2025.csv` con su cobertura lateral. Los gold son `data/gold/meteo_socio_epi_piura_2017_2025_h2_gold.csv` y `..._h4_gold.csv`, generados en fase 6. El contrato reutilizable está en [`src/modeling/contrato_xgboost.py`](../../src/modeling/contrato_xgboost.py). Se comprueban los hashes de silver, cobertura, catálogo, historia epidemiológica y ambos gold contra `manifest_fase6.json`, las llaves únicas, fechas de origen, casos, etiqueta y coincidencia de etiquetas entre horizontes. La llave es `(ubigeo, anio, semana)` con `ubigeo` como texto; `semana_inicio` es domingo y representa el objetivo `t`.

| Comprobación de archivos actuales | h=2 | h=4 |
|---|---:|---:|
| Filas / distritos / columnas | 30 485 / 65 / 48 | 30 485 / 65 / 48 |
| Columnas candidatas / excluidas | 34 / 14 | 34 / 14 |
| Filas con las 34 candidatas pobladas | 30 095 | 29 965 |
| Semanas `brote=1` en 2017–2025 | 3 002 | 3 002 |

Los primeros nulos vienen de la historia insuficiente de cada distrito: 390 filas si se exige que estén pobladas las 34 candidatas en h=2 y 520 en h=4. No se convierten a cero. La etiqueta `brote` es idéntica en ambas salidas por llave, pues describe la semana objetivo, no el horizonte. La regla registrada es casos de la semana objetivo **estrictamente mayores** que la media de la misma semana distrital de los cinco años previos + **1,5 DE muestrales**, y al menos **2 casos**. El mínimo 2 es provisional. Los positivos por año son 520, 5, 0, 2, 213, 354, 1 402, 503 y 3 para 2017–2025, respectivamente. Esta distribución exige reportar métricas por temporada: un único promedio puede ocultar años sin positivos.

## Matriz de variables y disponibilidad

| Familia y columnas de gold (`h` = 2 o 4) | Número | Disponibilidad respecto del origen `t−h` | Propuesta de uso |
|---|---:|---|---|
| Historia propia: `casos_lag_h`, `casos_lag_{h+1}`, `casos_media_4_hh`, `casos_semanas_positivas_4_hh` | 4 | Casos hasta la semana `t−h`; la ventana de cuatro termina allí. Nulos de arranque: 325 / 455 filas en h=2 / h=4. | Base inicial; comparar con persistencia. |
| Calendario: `semana_epi_seno`, `semana_epi_coseno` | 2 | Semana objetivo conocida al emitir el pronóstico. | Base inicial junto a historia. |
| Vecinos: `vecinos_media_casos_knn5_hh`, `vecinos_frac_con_casos_knn5_hh` | 2 | Casos de cinco vecinos en `t−h`; no incluye el distrito propio. Nulos de arranque: 130 / 260. | Ablación geográfica separada. |
| Jerarquía: `provincia_otros_casos_hh`, `provincia_otros_frac_con_casos_hh`, `region_otros_casos_hh`, `region_otros_frac_con_casos_hh` | 4 | Casos de los otros distritos en `t−h`; excluye el propio. Nulos de arranque: 130 / 260. | Ablación separada de vecinos. |
| Clima: `hum_rel_media_media5_hh`, `precip_total_mm_media5_hh` | 2 | Observaciones de cinco semanas que terminan en `t−h`. Nulos de arranque: 390 / 520. Su publicación efectiva aún no se ha verificado. | Ablación secundaria; climatologías/anomalías solo ajustadas dentro de cada fold. |
| Referencia fija 2017: `fraccion_rural_2017`, `fraccion_menores_15_2017`, `fraccion_desague_red_2017`, `log_poblacion_censo_2017` | 4 | Repetidas por distrito. Gold las conserva para reconstrucción retrospectiva; 2019-01-01 es una barrera **supuesta**, no fecha verificada del Excel derivado. | Sensibilidad frente a la representación anual. |
| Anuales: las 15 `fraccion_*_anual` y `log_poblacion_anual` | 16 | Repetidas por distrito y año. Las fracciones 2018–2024 usan el extremo 2025; la publicación de las proyecciones de población no está documentada. | Solo experimentos retrospectivos identificados; ensayar bloques pequeños antes de las 15 juntas. |

Los sufijos `hh` de la tabla significan, por ejemplo, `_h2` o `_h4`; la [lista exacta de columnas](../../src/modeling/contrato_xgboost.py) se genera por horizonte y se verifica contra el CSV. **La base propuesta para empezar XGBoost tiene seis variables:** cuatro de historia y dos de calendario. Que las otras 28 estén en gold significa que están disponibles para ablaciones controladas, no que se recomiende incluirlas juntas.

**Excluir de la matriz predictora:** `casos_Dengue`, `brote`, `umbral_brote_casos`, `ubigeo`, `anio`, `semana`, `provincia`, `distrito`, `distrito_key`, `semana_inicio`, `origen_inicio`, `origen_cierre`, `socio_2017_disponible_al_origen` y `socio_fracciones_interpoladas_con_2025`. `brote` es la etiqueta; `casos_Dengue` y el umbral conocen el objetivo. `ubigeo` es identificador, no magnitud continua. `anio`, `semana` y fechas son llaves/metadatos; el calendario ya tiene seno/coseno. Las dos marcas socio son señales de auditoría que podrían identificar el origen temporal de la información, por lo que quedan fuera de la primera matriz.

## Evidencia de aporte incremental disponible

Las siguientes comparaciones usan **ridge fijo con respuesta `log1p(casos_Dengue)`**, cuatro temporadas de prueba 2022–2025 y el mismo corte temporal por horizonte. Delta MAE = variante menos referencia; un valor negativo favorece a la variante. **No son resultados de XGBoost ni de la clasificación `brote`**. Los detalles y todas las temporadas están en [métricas](metricas/fase7_sintesis.json), derivadas de las fases [4](metricas/fase4_clima.json) y [5](metricas/fase5_sociodemografia.json).

| Añadido a historia + calendario | Cortes con menor MAE, h=2 | Cortes con menor MAE, h=4 | Lectura |
|---|---:|---:|---|
| Humedad y precipitación | 2/4 | 3/4 | En h=4 mejora 2023 en −0,575 casos MAE, pero empeora 2022 en +0,114. Mantener como prueba, sin prometer mejora general. |
| Población fija 2017 | 3/4 | 3/4 | Cambios pequeños y signo variable; comparar con anual. |
| Población anual | 3/4 | 3/4 | También cambios pequeños; fecha de publicación pendiente. |
| Las 15 fracciones anuales juntas | 1/4 | 1/4 | Bajo ridge no mejora de modo estable y en 2025 h=4 empeora +0,057; probar solo con justificación y comparación. |

La fase 3 encontró asociación descriptiva de vecinos con casos objetivo (Spearman 0,621 / 0,613 para h=2 / h=4), menor que la historia propia (0,779 / 0,743). **No hay una ablación predictiva de vecinos ni de jerarquía** en las fases anteriores. Deben ensayarse contra la misma base y los mismos cortes antes de atribuirles aporte. La referencia del EDA sobre vecindad tampoco demuestra transmisión causal.

## Contrato de experimentación posterior

1. Crear **un experimento por horizonte**, con objetivo binario `brote` para la alerta semanal. Conservar `casos_Dengue` para referencias y análisis de error, fuera de `X`. El conteo puede ser un objetivo alternativo en otra comparación, claramente identificado.
2. Usar cortes temporales comunes a todos los distritos. En cada fold, la **última etiqueta de entrenamiento** debe haberse observado antes del primer origen de pronóstico de la prueba. Si se fija un modelo para toda una temporada, los casos/clima que se vayan observando durante ella pueden alimentar pronósticos posteriores como lags; no reajustan el modelo salvo que se defina un protocolo de actualización.
3. Comparar base de seis variables, luego `+vecinos`, `+jerarquía`, `+clima` y alternativas socio **por bloques sobre las mismas filas de cada fold**. Mantener un benchmark de persistencia a cada horizonte. Ajustar imputación, climatología, PCA, pesos, codificación y selección de variables solo en entrenamiento. No usar `ubigeo` como número continuo.
4. Reportar precisión, exhaustividad, AUPRC y calibración de la alerta por temporada, además de las cuentas de positivos y falsos avisos. Fijar el umbral de probabilidad con validación temporal interna, nunca con el test final. Comparar en paralelo errores del conteo cuando ese objetivo se experimente. Evaluar distritos sin registros aparte; no asumir que todos sus ceros son ceros notificados.
5. Registrar hashes de datos, versión de regla de brote, horizonte, columnas de cada variante, fechas de corte y cualquier supuesto de disponibilidad. Los resultados ridge de fases 4–5 son diagnósticos de conteo; el aporte a la clasificación y a XGBoost queda por medir.

## Límites y decisiones para Rosa

- **Test final:** pendiente. 2025 se considera fuente válida; tampoco se asigna automáticamente a prueba. Con esta etiqueta solo tiene **3 positivos en el año calendario**, por lo que un test centrado allí daría una estimación muy inestable de precisión/exhaustividad. Conviene acordar con el equipo cómo reservar temporadas y cómo usar 2023–2024 sin seleccionar el mejor esquema mirando el test.
- **Etiqueta:** el mínimo de 2 y la regla estacional son provisionales. La referencia 2012–2016 del Excel es dispersa y trata ausencia como cero; eso afecta los umbrales iniciales y los distritos silenciosos. El [análisis de sensibilidad](revision_definicion_brote.md) conserva la alternativa de mínimo 1 y 5.
- **Tiempo y procedencia:** aún falta resolver semana 53 de 2025 antes de ampliar el calendario, documentar latencias reales de casos y clima, y verificar versiones/fechas de población. Las fracciones anuales de 2018–2024 son reconstrucción retrospectiva con 2025, por decisión expresa de Rosa para la experimentación; sus resultados no deben llamarse pronósticos que se habrían podido emitir en esos años.
- **Alternativas de modelo:** las variables de calendario, lags y agregados numéricos pueden usarse también con modelos lineales o de conteo. Ridge ya sirvió de diagnóstico. No hay evidencia local suficiente para recomendar entrenar otra arquitectura en esta fase; primero medir la base XGBoost y sus ablaciones.

## Reproducción

Desde la raíz, con silver y gold ya generados:

```bash
.venv/bin/jupyter nbconvert --to notebook --execute --inplace notebooks/23_fe_sintesis.ipynb
.venv/bin/python -m unittest discover -s tests
```

Si cambia silver o una feature, regenerar antes gold con el [notebook 22](../../notebooks/22_fe_integracion.ipynb). El notebook 23 falla cuando los hashes o el esquema no coinciden; escribe solo el JSON de métricas versionado de esta síntesis.
