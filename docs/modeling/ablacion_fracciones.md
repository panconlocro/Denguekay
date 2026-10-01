# Cribado individual de las 15 fracciones sociodemográficas

**Estado:** ejecutado para h=2 y h=4. El [módulo](../../src/modeling/ablacion_fracciones.py) y el [notebook 28](../../notebooks/28_modelado_ablacion_fracciones.ipynb) comparan cada fracción por separado. Las [métricas completas](metricas/ablacion_fracciones.json) incluyen las 31 variantes por horizonte, F1 y MAE por temporada, umbrales, cortes, hashes y ganadores por temporada. Las predicciones y los modelos seleccionados se guardan en `models/experimentos/ablacion_fracciones/`, fuera de Git.

## Pregunta y diseño

El [EDA sociodemográfico](../eda/hallazgos.md) ya relacionó cada fracción **de 2017** con la **incidencia acumulada por distrito en 2017–2024**. Esa correlación transversal no responde si una fracción mejora el pronóstico de casos o de la etiqueta **semanal** `brote` después de conocer la historia reciente. La [ablación anterior](ablacion_sociodemografica.md) ensayó las tres fracciones interpretables juntas y las 15 anuales juntas; aquí se agrega **una fracción a la vez** a `base_6` (cuatro rasgos de historia propia y dos de calendario). Se entrenan por separado regresión de `log1p(casos_Dengue)` y clasificación directa de `brote`; la regresión también se convierte en alerta con la regla de casos de gold.

Las 15 fracciones fijas de 2017 proceden de la referencia distrital del silver. Gold ya contiene tres; el módulo verifica su igualdad con la referencia y añade las otras 12 por **UBIGEO**. Las 15 fracciones anuales se leen de gold. Todas las variantes usan exactamente **30 160 filas modelables en h=2** y **30 030 en h=4**; las primeras 325/455 filas carecen de historia propia completa y permanecen en gold. No se modifican silver ni gold. Los orígenes de validación/prueba de las referencias fijas son posteriores a la barrera de disponibilidad **2019-01-01**, que es conservadora y no una fecha verificada para el Excel local. Las etiquetas de 2017–2018 sí pueden entrenar un modelo ajustado después de esa barrera.

El brazo **anual** es retrospectivo: sus fracciones de 2018–2024 se interpolaron entre los extremos de 2017 y **2025**. Si una variante anual gana, eso no demuestra que sus valores se hubieran conocido al emitir pronósticos históricos. Se mantienen separados los dos brazos. La población no entra en estas variantes; el experimento aísla la contribución marginal de cada fracción respecto de `base_6`, **no** su contribución adicional sobre un modelo que ya incluya población.

## Selección temporal

Se mantuvieron los hiperparámetros fijos del primer XGBoost. Cada variante escoge su umbral de probabilidad por F1 agregado de validación 2021–2023; la comparación entre variantes usa el **F1 medio de las tres temporadas** con igual peso. Se elige por separado entre base + 15 fracciones fijas y base + 15 anuales, para cada horizonte y enfoque. En empate gana el modelo con menos columnas. **2024 y 2025 no intervienen en la selección.** Las 30 búsquedas individuales con solo tres temporadas hacen que los máximos de validación sean exploratorios y probablemente optimistas.

| Horizonte / objetivo de alerta | Base F1 | Mejor fracción fija F1 | Mejor fracción anual F1, retrospectiva |
|---|---:|---:|---:|
| h=2, regresión + regla | 0,669 | `rural` **0,683** | `rural` **0,682** |
| h=2, clasificación | 0,594 | `sin_saneamiento` **0,636** | `hogares_lena` **0,638** |
| h=4, regresión + regla | 0,571 | `agua_red` **0,576** | `hogares_celular` **0,575** |
| h=4, clasificación | 0,561 | `sin_seguro` **0,586** | `sin_saneamiento` **0,574** |

**La elección cambia según horizonte, objetivo y temporada.** Por ejemplo, para clasificación h=4, `sin_seguro` fijo elevó el F1 en la temporada 2021 de **0,341 a 0,430**, pero quedó por debajo de la base en 2022 (**0,527 frente a 0,540**) y casi igual en 2023 (**0,802 frente a 0,801**). Ninguna fracción fija ganó por sí sola las tres temporadas de validación en ese enfoque. La columna `ganadora_por_temporada` del JSON muestra esos cambios para los cuatro análisis. Estos resultados tampoco indican causalidad: la fracción es constante o anual por distrito, y muchas semanas del mismo distrito no constituyen observaciones sociodemográficas independientes.

La relación descriptiva del EDA y el resultado predictivo no ordenan igual las variables. Por ejemplo, `sin_seguro` de 2017 tuvo correlación de Spearman **0,051** con incidencia acumulada entre los distritos de costa (IC 95 %: −0,273 a 0,366), pese a quedar primero para la alerta h=4 en esta selección. Una correlación transversal pequeña no impide que un árbol use una fracción en combinación con la historia de casos, pero con estos datos tampoco demuestra una señal estable.

## Contraste de las variantes elegidas en 2024

Solo la base y las variantes elegidas en validación se probaron en la temporada 2024 y, como sensibilidad, en el año calendario 2025. **2024 ya había sido inspeccionado en experimentos anteriores**, por lo que es un contraste exploratorio. La tabla muestra la métrica del enfoque que seleccionó cada variante; todas las filas de 2024 tienen **857** semanas positivas.

| Horizonte / enfoque | Variante | F1 | VP | FP | MAE de casos |
|---|---|---:|---:|---:|---:|
| h=2, regresión | Base | 0,802 | 651 | 116 | **5,681** |
| h=2, regresión | Rural fija | 0,805 | 654 | 114 | 5,916 |
| h=2, regresión | Rural anual | **0,808** | 660 | 117 | 5,846 |
| h=2, clasificación | Base | 0,641 | 790 | 819 | — |
| h=2, clasificación | Sin saneamiento fija | **0,643** | 798 | 828 | — |
| h=2, clasificación | Hogares con leña anual | 0,636 | 801 | 860 | — |
| h=4, regresión | Base | 0,752 | 614 | 161 | **9,443** |
| h=4, regresión | Agua de red fija | **0,755** | 615 | 157 | 9,570 |
| h=4, regresión | Hogares con celular anual | 0,754 | 629 | 182 | 12,405 |
| h=4, clasificación | Base | 0,612 | **763** | 873 | — |
| h=4, clasificación | Sin seguro fija | **0,621** | 754 | **818** | — |
| h=4, clasificación | Sin saneamiento anual | 0,611 | 767 | 886 | — |

Para el objetivo principal h=4, `sin_seguro` fija emitió **55 falsos avisos menos**, pero dejó de acertar **9 semanas elevadas** respecto de la base. Su F1 subió **0,009**. Es una compensación entre precisión y recall, no una ganancia inequívoca. En la [ablación por bloques](ablacion_sociodemografica.md), población censal fija ya había dado **0,584** de F1 medio en validación y **0,620** en 2024; `sin_seguro` fija dio **0,586** y **0,621**. La diferencia es demasiado pequeña para preferir una sobre la otra con estos mismos cortes. La [comparación condicional posterior](ablacion_poblacion_sin_seguro.md) ensayó si `sin_seguro` añade valor **encima de** población fija; no halló una ganancia convincente.

En el calendario 2025 hubo solo **3** semanas positivas. Los resultados completos están en el JSON; con tan pocas positivas no hay una comparación fiable entre fracciones. Los casos de la Sala Situacional siguen siendo una fuente válida según la decisión del proyecto.

## Interpretación y siguiente decisión

El experimento identifica candidatas para una evaluación posterior, **no una fracción ganadora definitiva**. La prioridad provisional para investigar la alerta h=4 sería `sin_seguro` fija, contrastándola contra población fija y midiendo si aporta algo al incluir ambas. Para conteos h=4, `agua_red` fija solo mejoró **0,003** de F1 de alerta y empeoró ligeramente el MAE de casos; no hay evidencia suficiente para adoptarla. Las variantes anuales son sensibilidad retrospectiva. No se seleccionan variables por su correlación bruta con la incidencia acumulada ni se interpretan como causas del dengue.

Si se continúa con selección formal, hará falta una validación interna adicional o más temporadas independientes: el mismo conjunto de 2021–2023 eligió umbrales y cribó 15 fracciones por brazo. La fecha real de disponibilidad del Excel censal y de las proyecciones, el significado de ceros sin notificación y el calendario alrededor de 2025-S53 siguen abiertos.

## Reproducción

Desde la raíz del repositorio, con silver y gold presentes:

```bash
.venv/bin/python -m src.modeling.ablacion_fracciones
.venv/bin/python -m unittest discover -s tests
```
