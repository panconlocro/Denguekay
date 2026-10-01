# Inclusión de variables sociodemográficas — tercer bloque de ablación

**Estado:** ejecutado para h=2 y h=4, con regresión de casos y clasificación directa. El [módulo](../../src/modeling/ablacion_sociodemografica.py), el [notebook 27](../../notebooks/27_modelado_ablacion_sociodemografica.ipynb) y las [métricas completas](metricas/ablacion_sociodemografica.json) permiten reproducirlo. Los modelos y predicciones por fila se guardan en `models/experimentos/ablacion_sociodemografica/`, fuera de Git. Las cifras son las del JSON actual, generado con GPU (`device="cuda"`); en otro equipo pueden variar en decimales y, cuando dos variantes están muy cerca, también en la elegida (ver [reproducibilidad entre equipos](primer_xgboost.md#reproducibilidad-entre-equipos)).

## Evidencia y linaje

El [EDA sociodemográfico](../eda/hallazgos.md) halló una asociación transversal fuerte entre el primer eje urbano y la incidencia en todos los distritos, pero mucho más débil dentro de la costa cálida. Las 15 fracciones están correlacionadas y pueden reflejar acceso al diagnóstico y notificación, no una causa del dengue. La [fase 5 de FE](../feature_engineering/fase5_sociodemografia.md) dejó población, tres fracciones interpretables y un eje urbano como candidatos; el ensayo ridge previo no estableció su aporte a XGBoost.

Gold contiene `log_poblacion_censo_2017`, tres fracciones de 2017, `log_poblacion_anual` y 15 fracciones anuales. Las fracciones de **2018–2024 se interpolaron entre 2017 y 2025**; el resultado de esas variantes es una **comparación retrospectiva con datos reconstruidos hoy**, no una simulación de pronósticos que se podían emitir entonces. La fecha de publicación de cada proyección anual del archivo local tampoco está documentada. Las variables fijas usan una barrera conservadora supuesta de **2019-01-01** para los orígenes de prueba; las etiquetas de 2017–2018 permanecen en entrenamiento porque sus casos ya eran conocidos en cada corte de 2021 en adelante. Esa barrera no es la fecha verificada del Excel local.

El eje urbano (`CP1`) no está precalculado en gold. Para cada fold se ajustó con las 15 fracciones **de 2017** y solo los distritos presentes en entrenamiento. Su signo coloca refrigeradora en el lado positivo; la misma escala y cargas transforman luego el valor anual de cada distrito. Como los 65 distritos aparecen en todos los cortes, los cinco ajustes por horizonte explicaron **61,34 %** de la variación transversal de las fracciones censales. Esa cifra no mide valor predictivo. Ajustar CP1 por fold evita que las fracciones de prueba definan el eje, pero **no elimina** la anticipación de 2025 ya contenida en las series anuales interpoladas.

## Variantes y selección

Todas las variantes añadieron sus columnas a `base_6` (historia propia y calendario) y utilizaron exactamente **30 160 filas en h=2** o **30 030 en h=4**. Solo se apartaron de la matriz las 325/455 filas iniciales sin historia propia completa; gold conservó 30 485. La base reproduce las cifras del primer experimento y de la ablación espacial. Se mantuvieron sus hiperparámetros, cortes y regla de alerta. Cada variante eligió su umbral de probabilidad con F1 agregado de validación 2021–2023. La selección se hizo por **F1 medio de las tres temporadas**, por separado para regresión y clasificación. Para no convertir una reconstrucción anual en una recomendación operativa, se eligió una variante entre **base y fijas** y otra entre **base y anuales retrospectivas**.

| Variante | Columnas añadidas | F1 h=2 reg. / clas. | F1 h=4 reg. / clas. |
|---|---|---:|---:|
| Base de seis | Ninguna | 0,677 / 0,592 | 0,567 / 0,555 |
| Población fija | `log_poblacion_censo_2017` | **0,680** / **0,655** | 0,559 / **0,584** |
| Tres fracciones fijas | rural, menores de 15, desagüe de red | 0,679 / 0,591 | **0,575** / 0,550 |
| Eje fijo | `eje_urbano_2017` | 0,677 / 0,616 | 0,566 / 0,558 |
| Población + eje fijos | Dos columnas | 0,674 / 0,630 | 0,561 / 0,578 |
| Población anual | `log_poblacion_anual` | 0,675 / **0,664** | 0,553 / **0,599** |
| Tres fracciones anuales | Las mismas tres, reconstruidas | **0,685** / 0,592 | **0,574** / 0,544 |
| Eje anual | `eje_urbano_anual` | 0,681 / 0,589 | 0,564 / 0,541 |
| 15 fracciones anuales | Todas las fracciones reconstruidas | 0,658 / 0,599 | 0,532 / 0,547 |
| Población + eje anuales | Dos columnas | 0,679 / 0,640 | 0,553 / 0,583 |

Entre las variantes fijas, **población censal ganó la clasificación en ambos horizontes**. En regresión ganó población en h=2, por apenas **0,001** sobre tres fracciones (0,6797 frente a 0,6788), y **tres fracciones en h=4**. Una diferencia de ese tamaño queda dentro de la variación entre equipos. En el carril anual retrospectivo fueron tres fracciones para regresión y población anual para clasificación, en ambos horizontes. La clasificación fija con población subió en promedio **0,063 de F1 para h=2** y **0,029 para h=4** sobre la base, pero la mejora de h=4 se concentró en la temporada de validación 2021 (**0,327 → 0,424**); en 2022 y 2023 el F1 fue ligeramente menor que la base. La población anual elevó aún más el promedio retrospectivo, sin resolver el problema de disponibilidad histórica.

## Contraste de 2024 y sensibilidad de 2025

Solo la base y las variantes elegidas en validación se evaluaron en estos bloques. La temporada 2024 ya se había inspeccionado en experimentos anteriores; no es un test completamente virgen. Las cifras anuales incorporan el linaje retrospectivo descrito arriba.

| Horizonte y enfoque | Variante | F1 2024 | VP | FP | MAE de casos |
|---|---|---:|---:|---:|---:|
| h=2, regresión | Base | 0,802 | 656 | 123 | 5,639 |
| h=2, regresión | Población fija | 0,807 | 657 | 114 | **5,428** |
| h=2, regresión | Tres anuales | **0,808** | 663 | 122 | 5,786 |
| h=2, clasificación | Base | 0,639 | 789 | 823 | — |
| h=2, clasificación | Población fija | **0,645** | 811 | 847 | — |
| h=2, clasificación | Población anual | 0,644 | 808 | 844 | — |
| h=4, regresión | Base | **0,758** | 623 | 164 | 9,401 |
| h=4, regresión | Tres fijas | 0,751 | 614 | 164 | **9,349** |
| h=4, regresión | Tres anuales | 0,755 | 625 | 173 | 10,218 |
| h=4, clasificación | Base | 0,612 | 762 | 873 | — |
| h=4, clasificación | Población fija | **0,622** | 764 | 835 | — |
| h=4, clasificación | Población anual | 0,611 | 804 | 969 | — |

Para el objetivo principal **h=4**, población fija en clasificación acertó 2 semanas elevadas más que la base y emitió **38 falsos avisos menos** en 2024. Su F1 mejoró **0,011**; es una señal favorable pero pequeña y procede de un bloque ya inspeccionado. La regresión con tres fracciones fijas redujo apenas el MAE (**9,401 → 9,349**), y su F1 de alerta bajó **0,007**. Las ventajas anuales de validación no se sostuvieron de forma clara en 2024 y no son evidencia de rendimiento operativo histórico.

En el año calendario 2025 hubo solo **3 semanas positivas**. Ninguna regresión seleccionada detectó una; la clasificación con población fija detectó 2/3 en h=2 y 0/3 en h=4, con 166 y 203 falsos avisos respectivamente. Esas cifras no permiten una comparación estable y tampoco justifican descartar los casos de la Sala como fuente válida. El JSON guarda los resultados completos y los umbrales de cada variante.

## Decisión y límites

**Mantener población censal fija como candidata para clasificación**, especialmente h=4. Las tres fracciones fijas, elegidas solo para la regresión h=4 y sin mejora de F1 en 2024, quedan como experimento secundario. Su mejora debe confirmarse con más temporadas o una evaluación prospectiva antes de adoptar un modelo final. No incluir por defecto las 15 fracciones anuales ni tratar la población anual como una señal históricamente disponible. La asociación sociodemográfica es ecológica y podría reflejar diferencias en notificación.

La selección de variantes y umbrales usa el mismo conjunto de validación, de modo que su F1 puede ser optimista. La disponibilidad exacta del Excel censal, las proyecciones anuales y el cambio de año en un origen de diciembre siguen sin comprobarse. No se alteraron silver ni gold; el tratamiento de los ceros sin notificación y el calendario 2025-S53/2026 permanecen como límites del proyecto.

## Reproducción

Desde la raíz, con silver y gold presentes:

```bash
.venv/bin/python -m src.modeling.ablacion_sociodemografica
.venv/bin/python -m unittest discover -s tests
```
