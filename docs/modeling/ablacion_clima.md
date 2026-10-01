# Inclusión de variables climáticas — segundo bloque de ablación

**Estado:** ejecutado para h=2 y h=4, con regresión de casos y clasificación directa. El módulo [`src/modeling/ablacion_clima.py`](../../src/modeling/ablacion_clima.py) reutiliza el entrenamiento y las métricas del [primer XGBoost](primer_xgboost.md); el [notebook 26](../../notebooks/26_modelado_ablacion_clima.ipynb) lo orquesta. Las [métricas completas](metricas/ablacion_clima.json) guardan cortes, columnas, umbrales y hashes. Modelos y predicciones por fila quedan en `models/experimentos/ablacion_clima/`, fuera de Git. Las cifras son las del JSON actual, generado con GPU (`device="cuda"`); en otro equipo pueden variar en decimales (ver [reproducibilidad entre equipos](primer_xgboost.md#reproducibilidad-entre-equipos)).

## Motivo y variables

El [EDA climático](../eda/hallazgos.md) encontró asociación descriptiva en la ventana de rezagos 4–8 semanas para humedad y precipitación, pero su señal adicional después de los casos propios en `t−4` fue pequeña. La [fase 4 de FE](../feature_engineering/fase4_clima.md) las dejó como candidatas, sin concluir que mejoraran el pronóstico. La temperatura mínima fue débil; temperatura media/máxima mezclaban calendario y eran redundantes. `lluvia_total_mm` duplica `precip_total_mm`.

Para cada semana objetivo `t`, se probaron medias de humedad y precipitación de las cinco semanas **`t−h−4` a `t−h`**: h=4 usa la ventana 4–8 del EDA y h=2 usa 2–6. Las medias observadas ya están en gold. Las anomalías restan la media histórica de cada distrito y semana climática, **ajustada por separado en cada fold** con clima semanal cerrado hasta su primer origen de prueba. Después se promedian en la misma ventana. La semana 53 usa la casilla 52 solo en esa climatología. Todo el proceso supone que Open-Meteo estaba disponible al cierre de cada semana; la latencia real sigue sin verificar.

| Variante | Predictores añadidos a `base_6` |
|---|---|
| `base_6` | Ninguno: cuatro de historia propia y dos de calendario |
| `mas_clima_observado` | `hum_rel_media_media5_h{h}`, `precip_total_mm_media5_h{h}` |
| `mas_anomalias` | `hum_rel_media_anomalia_media5_h{h}`, `precip_total_mm_anomalia_media5_h{h}` |
| `mas_ambos` | Los cuatro anteriores |

Las cuatro variantes usan exactamente **30 095 filas para h=2** y **29 965 para h=4**. Se excluyen de la matriz solo las primeras 6/8 semanas por distrito, que carecen de ventana climática completa (**390/520 filas**); gold conserva sus 30 485 filas. Esto reduce en 65 filas cada horizonte frente a la ablación espacial. La base se volvió a entrenar sobre estas filas comunes: sus cifras aquí no deben confundirse con las de la base del primer experimento, que disponía de una semana más por distrito.

## Selección en validación

Se mantuvieron hiperparámetros y cortes del primer XGBoost. Los modelos se entrenan con etiquetas cerradas antes del primer origen de cada temporada; predicen semanalmente sin reajustarse con etiquetas del bloque. Las anomalías se ajustan con ese mismo corte. Como en el experimento espacial, el umbral de clasificación maximiza F1 agregado en validación 2021–2023 para cada variante y el bloque se elige por **F1 medio de las tres temporadas**, con igual peso y empate a favor de menos columnas. Se elige por separado para regresión y clasificación en cada horizonte. Este uso compartido de validación para umbral y selección puede optimizar el F1 informado.

| Horizonte | Variante | F1 medio, regresión + regla | F1 medio, clasificación |
|---|---:|---:|---:|
| h=2 | Base de seis | **0,667** | **0,592** |
| h=2 | + Clima observado | 0,643 | 0,534 |
| h=2 | + Anomalías | 0,637 | 0,494 |
| h=2 | + Ambos | 0,627 | 0,518 |
| h=4 | Base de seis | **0,567** | **0,557** |
| h=4 | + Clima observado | 0,554 | 0,493 |
| h=4 | + Anomalías | 0,547 | 0,460 |
| h=4 | + Ambos | 0,548 | 0,460 |

La base ganó las cuatro selecciones, con margen amplio (al menos **0,012** de F1 medio en regresión y **0,057** en clasificación). La caída de la clasificación se concentra en la temporada 2021: en h=4, la base obtuvo **0,339** y las variantes climáticas entre **0,091 y 0,174**. Las anomalías se calcularon correctamente por fold, pero en esta configuración no aportaron F1 incremental. No se usaron 2024 ni 2025 para escoger variables.

## Contraste de la variante elegida

Como ninguna variante climática ganó en validación, **solo la base** se ejecutó en los bloques de prueba. La temporada 2024 ya había sido inspeccionada en experimentos previos: estas cifras son un contraste de consistencia y no un test completamente virgen. En 2025 hubo tres semanas positivas, de modo que su F1 es muy inestable.

| Bloque | Horizonte | Regresión: F1 / VP / FP / MAE de casos | Clasificación: F1 / VP / FP |
|---|---:|---:|---:|
| Temporada 2024, 857 positivas | h=2 | 0,803 / 656 / 121 / 5,680 | 0,634 / 807 / 882 |
| Temporada 2024, 857 positivas | h=4 | 0,754 / 617 / 163 / 9,446 | 0,611 / 760 / 871 |
| Calendario 2025, 3 positivas | h=2 | 0,000 / 0 / 3 / 0,300 | 0,012 / 2 / 327 |
| Calendario 2025, 3 positivas | h=4 | 0,000 / 0 / 5 / 0,429 | 0,006 / 1 / 348 |

## Interpretación y límites

**No se recomienda incorporar estas variables climáticas por defecto** al XGBoost actual: todas redujeron el F1 medio de alerta en validación respecto de la base sobre las mismas filas. Esto no demuestra que el clima carezca de relación con el dengue; el EDA halló señales pequeñas y las temporadas de brote son pocas. Tampoco se probaron otras fuentes meteorológicas, otras ventanas ni ajuste de hiperparámetros, porque ampliarlas ahora con los mismos cortes favorecería la búsqueda oportunista.

La señal del clima en el EDA y el contraste ridge de la fase 4 eran sobre todo de conteos; aquí se evalúa también la etiqueta semanal elevada acordada. El supuesto de disponibilidad al cierre y la climatología de semana 53 deberán revisarse antes de un uso operativo o una ampliación del panel a 2026. La procedencia válida de los casos de 2025 se conserva, con su cambio de fuente documentado. La siguiente familia candidata es sociodemografía fija y anual reconstruida; requiere una fase y revisión separadas.

## Reproducción

Desde la raíz del repositorio, con silver y ambos gold de fase 6 presentes:

```bash
.venv/bin/python -m src.modeling.ablacion_clima
.venv/bin/python -m unittest discover -s tests
```
