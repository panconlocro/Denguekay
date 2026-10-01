# Inclusión de variables espaciales — primer bloque de ablación

**Estado:** ejecutado para h=2 y h=4, con regresión de casos y clasificación directa. El módulo [`src/modeling/ablacion_espacial.py`](../../src/modeling/ablacion_espacial.py) reutiliza el entrenamiento y las métricas del [primer XGBoost](primer_xgboost.md). Las [métricas completas](metricas/ablacion_espacial.json) registran columnas, cortes, F1 por temporada, umbrales y hashes. Los modelos y las predicciones por fila están en `models/experimentos/ablacion_espacial/`, fuera de Git. Las cifras son las del JSON actual, generado con GPU (`device="cuda"`); en otro equipo pueden variar en decimales y, cuando dos variantes están muy cerca, también en la elegida (ver [reproducibilidad entre equipos](primer_xgboost.md#reproducibilidad-entre-equipos)).

## Qué se incluyó

Gold ya contenía estas seis columnas construidas y auditadas en la [fase 3](../feature_engineering/fase3_vecinos_jerarquia.md). Todas resumen **casos observados en `t−h`**, excluyen el distrito objetivo de sus agregados espaciales y se cruzan por UBIGEO, no por nombre:

| Bloque | Columnas agregadas a la base de seis |
|---|---|
| `mas_vecinos` | `vecinos_media_casos_knn5_h{h}`, `vecinos_frac_con_casos_knn5_h{h}` |
| `mas_jerarquia` | `provincia_otros_casos_h{h}`, `provincia_otros_frac_con_casos_h{h}`, `region_otros_casos_h{h}`, `region_otros_frac_con_casos_h{h}` |
| `mas_ambos` | Las seis anteriores |

`base_6` es exactamente la variante de seis variables del primer experimento. No se cambiaron los datos silver/gold ni los hiperparámetros de XGBoost. Todas las variantes compartieron **30 160 filas modelables para h=2** y **30 030 para h=4**; los nulos excluidos son únicamente las 325/455 filas iniciales con historia propia insuficiente. Las columnas espaciales no tienen nulos adicionales en esas filas.

## Qué asociación espacial encontró el EDA

El [EDA espacial](../eda/hallazgos.md) motivó probar estas variables, pero describió fenómenos diferentes:

- La incidencia acumulada mostró autocorrelación espacial: **I de Moran = 0,693** con cinco vecinos; al restringir el análisis a distritos de costa fue **0,333**.
- Entre 31 distritos activos, la mediana de correlación de Spearman entre series semanales fue **0,62**. Tras retirar la actividad regional común cayó a **0,06**. Buena parte de la coincidencia entre distritos refleja, por tanto, una señal regional compartida.
- En el análisis descriptivo de **arranques** de episodios, un D1 en algún vecino cuatro semanas antes se asoció con una frecuencia de arranque **2,82 veces mayor**, tras estratificar por actividad regional (razón de riesgos de Mantel-Haenszel; IC 95 %: **1,87–4,29**). Se consideraron los cinco vecinos más cercanos. La definición de candidatas del análisis principal usaba las semanas `t−1` a `t−8`; el EDA también presenta una sensibilidad con candidatas definibles desde `t−4`.

Ese resultado de arranques utilizó **D1**, una marca ilustrativa de incidencia de al menos **10 casos por 100 000 habitantes**. La etiqueta actual `brote` de gold identifica **cada semana distrital elevada**, según la media de la misma semana en los cinco años anteriores + 1,5 desviaciones estándar y un mínimo de dos casos. Tampoco se incluyó aquí un indicador de vecino con D1: las variables ensayadas resumen casos y la fracción de vecinos con **más de cero casos** en `t−h`, además de la actividad del resto de provincia y región. Por ello, la razón de riesgos del EDA no equivale al rendimiento esperado de estas variables en h=2 o h=4. La asociación no prueba transmisión causal ni mejora adicional sobre la historia del propio distrito; esta última se evalúa con la ablación siguiente.

## Cómo se compararon

La selección usa solo las temporadas de validación **2021–2023**, con los mismos cortes y filas para cada variante. Cada clasificador obtiene su umbral de probabilidad maximizando F1 en esas predicciones de validación, tal como acordamos para el primer experimento. Para escoger variables, se usa el **F1 medio de las tres temporadas**, con igual peso para cada una; los empates favorecen menos columnas. Se selecciona por separado para regresión y clasificación en cada horizonte. MAE de conteos, AUPRC, recall y falsos avisos se reportan como diagnósticos secundarios.

La temporada 2024 y el año calendario 2025 se evaluaron **después de fijar las variantes**. La base y esas pruebas ya se habían examinado en el primer experimento, por lo que estos bloques sirven para comprobar si la nueva señal se sostiene, pero **no constituyen un test completamente virgen**. No se eligió ninguna variable nueva mirando sus resultados.

El mismo conjunto de validación sirve para elegir el umbral de probabilidad y comparar variantes; por eso sus F1 son **exploratorios y pueden ser optimistas**. Harían falta más temporadas o validación interna adicional para una estimación de selección independiente.

| Horizonte | Variante | F1 validación, regresión + regla | F1 validación, clasificación |
|---|---|---:|---:|
| h=2 | Base de seis | 0,677 | 0,592 |
| h=2 | + Vecinos | 0,680 | 0,593 |
| h=2 | + Jerarquía | **0,688** | **0,604** |
| h=2 | + Ambos | 0,667 | 0,595 |
| h=4 | Base de seis | 0,567 | **0,555** |
| h=4 | + Vecinos | 0,576 | 0,554 |
| h=4 | + Jerarquía | **0,586** | 0,537 |
| h=4 | + Ambos | 0,583 | 0,543 |

La ablación reprodujo **exactamente** todas las métricas de la base de seis variables del primer experimento en ambos horizontes, incluida la selección de su umbral de probabilidad (ambas corridas en el mismo equipo). La jerarquía ganó la regresión en ambos horizontes y la clasificación h=2, con aumentos de F1 medio de **0,010 a 0,019**; vecinos solos apenas se movieron respecto de la base. Para el objetivo principal h=4, el clasificador siguió eligiendo la base: las tres variantes espaciales bajaron su F1 medio.

## Prueba principal: temporada 2024

Cada fila representa una distrito-semana. Hubo **857 positivas entre 3 380**. Solo se probaron la base y las variantes elegidas en validación; no se usaron los resultados de prueba para cambiar esa elección.

| Horizonte y enfoque | Variante | F1 | VP | FP | MAE de casos |
|---|---|---:|---:|---:|---:|
| h=2, regresión | Base de seis | **0,802** | 656 | 123 | **5,64** |
| h=2, regresión | + Jerarquía | 0,801 | 676 | 154 | 5,79 |
| h=2, clasificación | Base de seis | 0,639 | 789 | 823 | — |
| h=2, clasificación | + Jerarquía | **0,648** | 815 | 843 | — |
| h=4, regresión | Base de seis | **0,758** | 623 | 164 | **9,40** |
| h=4, regresión | + Jerarquía | 0,751 | 643 | 213 | 11,28 |
| h=4, clasificación | Base de seis, seleccionada también en validación | 0,612 | 762 | 873 | — |

Para h=2, la regresión con jerarquía detectó 20 semanas positivas más, pero produjo 31 falsos avisos adicionales; su F1 quedó prácticamente igual (**−0,001**) y su MAE empeoró de **5,64 a 5,79**. La clasificación h=2 con jerarquía detectó 26 adicionales con 20 falsos avisos más y subió su F1 en **0,009**, aunque su AUPRC bajó de **0,668 a 0,636**; es una señal pequeña, en un horizonte secundario y en un bloque ya inspeccionado. Para h=4, la regresión con jerarquía no sostuvo la mejora de validación: su F1 bajó de **0,758 a 0,751** y su MAE empeoró de **9,40 a 11,28**. Esto no respalda adoptar por defecto las variables espaciales para el objetivo principal.

En el año calendario 2025 hubo solo **3 positivas**. Las dos regresiones espaciales seleccionadas detectaron **0/3** (3 falsos avisos en h=2; 5 en h=4). El clasificador h=2 con jerarquía detectó **0/3** y emitió **139 falsos avisos**; el h=4 conservó la base del primer experimento (**1/3**, 349 falsos avisos). Con tres positivos, esas cifras no permiten una conclusión estable de generalización.

Los distritos Lagunas (`200204`), Montero (`200205`) y Sicchez (`200209`) no tenían casos registrados en 2017–2024. En cada bloque de prueba sumaron 156 filas, ninguna positiva y ninguna alerta de las variantes probadas. Esto describe la salida del modelo; **no demuestra que sus ceros sean notificaciones negativas confirmadas**.

## Interpretación y siguiente fase

La asociación espacial descrita en el EDA no se tradujo en una mejora robusta de alerta sobre la historia propia. En especial, el aumento pequeño de F1 de regresión en validación no bastó para mejorar h=4 en la prueba fija, y el clasificador h=4 no mejoró ni siquiera en validación. Estos agregados no implican transmisión causal entre distritos; la disponibilidad real de los casos al cierre de la semana sigue siendo un supuesto operativo.

El siguiente bloque de variables sería clima observado (humedad y precipitación) y, si se ensayan anomalías, su climatología deberá ajustarse **dentro de cada fold**. Después se podrá revisar la demografía fija y la reconstruida, esta última marcada como análisis retrospectivo por el uso del extremo de 2025. Esas fases quedan pendientes de revisión de Rosa.

## Reproducción

Con los dos gold de fase 6 presentes, desde la raíz del repositorio:

```bash
.venv/bin/python -m src.modeling.ablacion_espacial
.venv/bin/python -m unittest discover -s tests
```
