# Matrices compactas y validación temporal progresiva

**Estado:** experimento ejecutado para h=2 y h=4. El [módulo](../../src/modeling/validacion_temporal_compacta.py), el [notebook 30](../../notebooks/30_modelado_validacion_temporal_compacta.ipynb) y las [métricas completas](metricas/validacion_temporal_compacta.json) permiten reproducir las cifras. Las predicciones por distrito-semana quedan en `models/experimentos/validacion_temporal_compacta/`, fuera de Git. Silver y gold permanecieron como entradas.

## Pregunta y matrices predefinidas

El [EDA](../eda/informe_eda.md) recomendó comparar con persistencia y validar con origen móvil por temporada en 2022–2024; describió una señal climática parcial pequeña y una asociación sociodemográfica débil dentro de la zona cálida. Las ablaciones posteriores no respaldaron añadir clima ni contexto espacial por defecto para la alerta h=4. La comparación condicional tampoco mostró un aporte convincente de `fraccion_sin_seguro_2017` encima de población fija. Por ello se cerró una comparación pequeña, sin nuevas variables ni ajuste de hiperparámetros:

| Variante | Predictores |
|---|---|
| `base_4` | Casos en `t−h`, media de las cuatro semanas terminadas en `t−h`, seno y coseno de semana objetivo |
| `base_6` | Los cuatro anteriores + casos de una semana previa al origen + número de semanas con casos en la ventana |
| `base_6_poblacion_2017` | Los seis anteriores + `log_poblacion_censo_2017` fija por distrito |

Se entrenaron **regresión de log1p(casos)**, con conversión a alerta mediante la regla de gold, y **clasificación directa de `brote`**. La persistencia de casos `t−h` es referencia. Se conservaron los hiperparámetros del primer XGBoost. Para cada horizonte y variante se usaron las mismas filas: **30 160 en h=2** y **30 030 en h=4**; las 325/455 filas iniciales sin historia completa continúan en gold. No se imputa un faltante como cero. `ubigeo`, `casos_Dengue`, `brote` y `umbral_brote_casos` quedan fuera de los predictores. Se verificó que la población censal fuera positiva y constante por UBIGEO.

## Evaluación progresiva

Los modelos se ajustan antes del primer origen de cada temporada y permanecen fijos durante ella. La temporada epidemiológica etiquetada **2024** va aproximadamente de la semana 35 de 2023 a la 34 de 2024. El primer origen de esa temporada fue **2023-08-19** para h=2 y **2023-08-05** para h=4. Solo entraron al ajuste etiquetas cerradas hasta esa fecha.

La temporada 2021 sirvió como **calibración inicial** del umbral de clasificación. Para evaluar 2022, se eligió el umbral de F1 con predicciones fuera de muestra de 2021 cuyas etiquetas ya habían cerrado al primer origen de 2022. Para 2023 se agregaron las predicciones de 2022 disponibles; para 2024, las de 2023. Al comienzo de cada temporada evaluada entre 2022 y 2024 se excluyeron de la calibración **65 distrito-semanas para h=2** o **195 para h=4**, porque sus etiquetas aún no habían cerrado. El umbral quedó fijo durante el bloque. Esta regla evita calcular el F1 de una temporada con un umbral elegido usando sus propias etiquetas.

La elección de matriz por objetivo y horizonte utilizó únicamente el **F1 medio, con igual peso de 2022 y 2023**; en empate ganaría la matriz más corta. Después se consultó 2024 como contraste. Las tres matrices se evaluaron allí para ver estabilidad, sin cambiar la elección. El calendario 2025 es una sensibilidad aparte con solo tres semanas positivas. Las predicciones y métricas de cada corte, umbral, tamaño de calibración y hashes de gold están en el JSON.

## Resultados

| Horizonte / objetivo | Variante | F1 medio 2022–2023 | F1 temporada 2024 | F1 calendario 2025 |
|---|---|---:|---:|---:|
| h=2, regresión + regla | **`base_4`** | **0,754** | 0,798 | 0,000 |
| h=2, regresión + regla | `base_6` | 0,750 | 0,802 | 0,000 |
| h=2, regresión + regla | `base_6_poblacion_2017` | 0,741 | 0,802 | 0,000 |
| h=2, clasificación | `base_4` | 0,668 | 0,643 | 0,008 |
| h=2, clasificación | `base_6` | 0,662 | 0,641 | 0,015 |
| h=2, clasificación | **`base_6_poblacion_2017`** | **0,692** | 0,643 | 0,018 |
| h=4, regresión + regla | **`base_4`** | **0,693** | 0,753 | 0,000 |
| h=4, regresión + regla | `base_6` | 0,691 | 0,752 | 0,000 |
| h=4, regresión + regla | `base_6_poblacion_2017` | 0,686 | 0,759 | 0,000 |
| h=4, clasificación | `base_4` | 0,611 | 0,613 | 0,005 |
| h=4, clasificación | `base_6` | 0,601 | 0,612 | 0,006 |
| h=4, clasificación | **`base_6_poblacion_2017`** | **0,661** | **0,620** | 0,000 |

La matriz seleccionada para **clasificación h=4** acertó **779 de 857** semanas positivas de la temporada 2024 y produjo **876 falsos avisos**. La regresión h=4 con `base_4` obtuvo F1 **0,753**, frente a **0,733** de persistencia, pero su MAE de casos fue **9,668** frente a **7,85** de persistencia. La mejora de alerta no equivale a una mejora del conteo. En h=2, la regresión seleccionada obtuvo F1 **0,798**, prácticamente igual a persistencia (**0,798**), y también mayor MAE de casos (**5,978** frente a **4,96**).

El F1 de la clasificación h=4 con población fue **0,526 en 2022** y **0,797 en 2023**. El promedio favorece a esa matriz, pero la diferencia entre temporadas impide tratarla como una mejora estable. En 2025, la regresión de las tres matrices no acertó ninguna de las tres semanas positivas para ambos horizontes; la clasificación h=4 seleccionada tampoco acertó una y emitió **158 falsos avisos**. Los casos de Sala Situacional de 2025 siguen siendo una fuente válida; el bajo número de positivos limita la comparación de alertas.

## Decisión provisional y límites

Para continuar con un conjunto compacto, la **regresión de cuatro variables** y la **clasificación de seis más población fija de 2017** son las candidatas elegidas por el criterio cronológico predefinido, en ambos horizontes. No hay una ganancia suficientemente estable para declarar un modelo operativo: las diferencias de F1 entre matrices son pequeñas, 2024 ya se había examinado en ensayos anteriores, y la selección original de familias usó parte de las mismas temporadas. Esta evaluación corrige la reutilización de etiquetas para calibrar el umbral de cada bloque, pero **no convierte 2024 en un test virgen ni elimina el sesgo de selección previo**.

El mínimo de dos casos para `brote`, el costo de falsos avisos, los ceros sin registro, la fecha real de disponibilidad de población/casos y el calendario 2025-S53 siguen abiertos. La siguiente etapa, si Rosa la aprueba, sería acordar un criterio operativo de alerta y diseñar una evaluación realmente independiente antes de ajustar hiperparámetros o desplegarla.

## Reproducción

```bash
.venv/bin/python -m src.modeling.validacion_temporal_compacta
.venv/bin/python -m unittest discover -s tests
```
