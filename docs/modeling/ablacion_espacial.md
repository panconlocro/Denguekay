# Inclusión de variables espaciales — primer bloque de ablación

**Estado:** ejecutado para h=2 y h=4, con regresión de casos y clasificación directa. El módulo [`src/modeling/ablacion_espacial.py`](../../src/modeling/ablacion_espacial.py) reutiliza el entrenamiento y las métricas del [primer XGBoost](primer_xgboost.md). Las [métricas completas](metricas/ablacion_espacial.json) registran columnas, cortes, F1 por temporada, umbrales y hashes. Los modelos y las predicciones por fila están en `models/experimentos/ablacion_espacial/`, fuera de Git.

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
| h=2 | Base de seis | 0,669 | 0,594 |
| h=2 | + Vecinos | 0,669 | 0,587 |
| h=2 | + Jerarquía | 0,680 | **0,598** |
| h=2 | + Ambos | **0,682** | 0,579 |
| h=4 | Base de seis | 0,571 | **0,561** |
| h=4 | + Vecinos | 0,569 | 0,557 |
| h=4 | + Jerarquía | **0,585** | 0,534 |
| h=4 | + Ambos | 0,578 | 0,529 |

La ablación reprodujo **exactamente** todas las métricas de la base de seis variables del primer experimento en ambos horizontes, incluida la selección de su umbral de probabilidad. La jerarquía muestra un pequeño aumento del F1 de regresión en validación; vecinos solos no mejoran de forma estable. Para el objetivo principal h=4, el clasificador siguió eligiendo la base.

## Prueba principal: temporada 2024

Cada fila representa una distrito-semana. Hubo **857 positivas entre 3 380**. Solo se probaron la base y las variantes elegidas en validación; no se usaron los resultados de prueba para cambiar esa elección.

| Horizonte y enfoque | Variante | F1 | VP | FP | MAE de casos |
|---|---|---:|---:|---:|---:|
| h=2, regresión | Base de seis | 0,802 | 651 | 116 | 5,68 |
| h=2, regresión | + Vecinos y jerarquía | **0,805** | 681 | 153 | 5,61 |
| h=2, clasificación | Base de seis | **0,641** | 790 | 819 | — |
| h=2, clasificación | + Jerarquía | 0,637 | 819 | 894 | — |
| h=4, regresión | Base de seis | **0,752** | 614 | 161 | **9,44** |
| h=4, regresión | + Jerarquía | 0,750 | 650 | 226 | 12,20 |
| h=4, clasificación | Base de seis, seleccionada también en validación | 0,612 | 763 | 873 | — |

Para h=2, agregar ambos bloques a la regresión detectó 30 semanas positivas más, pero produjo 37 falsos avisos adicionales; su F1 subió solo **0,003**. La clasificación con jerarquía detectó 29 adicionales y produjo 75 falsos avisos adicionales, de modo que su F1 bajó. Para h=4, la regresión con jerarquía no sostuvo la mejora de F1 y empeoró el MAE de **9,44 a 12,20**. Esto no respalda adoptar por defecto las variables espaciales para el objetivo principal.

En el año calendario 2025 hubo solo **3 positivas**. Las dos regresiones espaciales seleccionadas detectaron **0/3** (3 falsos avisos en h=2; 5 en h=4). El clasificador h=2 con jerarquía detectó **0/3** y emitió **146 falsos avisos**; el h=4 conservó la base del primer experimento (**1/3**, 346 falsos avisos). Con tres positivos, esas cifras no permiten una conclusión estable de generalización.

Los distritos Lagunas (`200204`), Montero (`200205`) y Sicchez (`200209`) no tenían casos registrados en 2017–2024. En cada bloque de prueba sumaron 156 filas, ninguna positiva y ninguna alerta de las variantes probadas. Esto describe la salida del modelo; **no demuestra que sus ceros sean notificaciones negativas confirmadas**.

## Interpretación y siguiente fase

La asociación espacial descrita en el EDA no se tradujo en una mejora robusta de alerta sobre la historia propia. En especial, el aumento pequeño de F1 en validación no bastó para mejorar h=4 en la prueba fija. Estos agregados no implican transmisión causal entre distritos; la disponibilidad real de los casos al cierre de la semana sigue siendo un supuesto operativo.

El siguiente bloque de variables sería clima observado (humedad y precipitación) y, si se ensayan anomalías, su climatología deberá ajustarse **dentro de cada fold**. Después se podrá revisar la demografía fija y la reconstruida, esta última marcada como análisis retrospectivo por el uso del extremo de 2025. Esas fases quedan pendientes de revisión de Rosa.

## Reproducción

Con los dos gold de fase 6 presentes, desde la raíz del repositorio:

```bash
.venv/bin/python -m src.modeling.ablacion_espacial
.venv/bin/python -m unittest discover -s tests
```
