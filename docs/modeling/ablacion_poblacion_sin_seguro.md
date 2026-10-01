# Comparación condicional: población y fracción sin seguro de 2017

**Estado:** ejecutada para h=2 y h=4. El [módulo](../../src/modeling/ablacion_poblacion_sin_seguro.py), el [notebook 29](../../notebooks/29_modelado_ablacion_poblacion_sin_seguro.ipynb) y las [métricas completas](metricas/ablacion_poblacion_sin_seguro.json) documentan los cortes, umbrales, hashes, resultados por temporada y diferencias pareadas. Los modelos y predicciones por fila están en `models/experimentos/ablacion_poblacion_sin_seguro/` fuera de Git. Las cifras son las del JSON actual, generado con GPU (`device="cuda"`); las diferencias que se discuten aquí son del mismo orden que la variación entre equipos (ver [reproducibilidad entre equipos](primer_xgboost.md#reproducibilidad-entre-equipos)).

## Por qué se hizo

Después de [comparar bloques demográficos](ablacion_sociodemografica.md), la población censal fija de 2017 quedó como candidata para clasificar semanas elevadas. En el [cribado individual](ablacion_fracciones.md), `fraccion_sin_seguro_2017` tuvo el mayor F1 medio entre las fracciones fijas para la alerta principal h=4. **No se sabía si aportaba información adicional a población.** Antes de entrenar se fijaron cuatro variantes, sin buscar otra fracción en 2024:

| Variante | Predictores añadidos a la base de seis |
|---|---|
| `base_6` | Ninguno |
| `poblacion_2017` | `log_poblacion_censo_2017` |
| `sin_seguro_2017` | `fraccion_sin_seguro_2017` |
| `poblacion_y_sin_seguro_2017` | Ambos |

Cada variante usa las mismas **30 160 filas modelables para h=2** y **30 030 para h=4**. Las 325/455 filas iniciales sin historia propia completa permanecen en gold y no entran en ninguna matriz. La fracción de 2017 se cruza por UBIGEO desde la referencia validada de silver; no se usa la fracción interpolada del año de la fila. La población es el logaritmo del censo distrital de 2017, también repetido en todos los años. Los orígenes evaluados son posteriores a la barrera conservadora supuesta de disponibilidad censal de **2019-01-01**. Las etiquetas históricas de 2017–2018 pueden entrar en entrenamientos ajustados después de esa fecha. El módulo reutiliza las validaciones de gold, la referencia censal y los cortes del primer XGBoost.

Se conservaron los hiperparámetros fijos, los folds de validación **2021–2023**, la temporada 2024 como contraste y el calendario 2025 como sensibilidad. Cada clasificador escogió su umbral de probabilidad maximizando F1 en la validación agregada; ese mismo umbral se aplicó a 2024 y 2025. Se entrenaron los cuatro modelos para ambos enfoques, regresión de casos y clasificación directa, **sin seleccionar uno mirando 2024**. Como 2024 ya se había inspeccionado en experimentos previos, estas diferencias son exploratorias y no una confirmación independiente.

## Resultado principal: alerta directa a cuatro semanas

| Variante | F1 medio validación | F1 2024 | VP 2024 | FP 2024 | AUPRC 2024 |
|---|---:|---:|---:|---:|---:|
| Base de seis | 0,555 | 0,612 | 762 | 873 | 0,609 |
| + Población fija | 0,584 | 0,622 | 764 | 835 | **0,653** |
| + Sin seguro fija | **0,589** | 0,621 | 738 | **780** | 0,617 |
| + Población y sin seguro | 0,584 | **0,626** | **765** | 824 | 0,644 |

La pregunta condicional compara la última fila con **población sola**. En validación quedaron prácticamente empatadas (**0,5844 frente a 0,5842**); las diferencias por temporada fueron **+0,0086 (2021)**, **−0,0062 (2022)** y **−0,0016 (2023)**, es decir, la combinación fue peor en dos de las tres. En 2024, al añadir `sin_seguro` a población, el F1 subió **0,0034**: un acierto más (**765** frente a **764**) y **11 falsos avisos menos** (824 frente a 835). Sin embargo, la AUPRC bajó de **0,653 a 0,644**, y una diferencia de ese tamaño en un bloque ya inspeccionado no compensa el empate de validación. Por tanto, **no hay evidencia convincente de aporte incremental de `sin_seguro` sobre población fija** en la alerta h=4 de este XGBoost.

`Sin_seguro` sola logra un F1 casi igual al de población sola en 2024 (**0,621** frente a **0,622**), pero representa otra compensación: **26 semanas elevadas acertadas menos** y **55 falsos avisos menos**. Elegir entre esas dos alertas exigiría acordar el costo de una semana elevada no detectada frente al de un falso aviso. Ninguna asociación debe interpretarse como efecto causal del seguro sobre dengue o notificación.

## Horizonte de dos semanas y regresión de casos

| Horizonte / enfoque | Base F1 | Población F1 | Sin seguro F1 | Ambas F1 | Comparación de ambas vs población en 2024 |
|---|---:|---:|---:|---:|---|
| h=2, clasificación: validación | 0,592 | **0,655** | 0,634 | 0,652 | — |
| h=2, clasificación: 2024 | 0,639 | 0,645 | **0,654** | 0,647 | +0,002 F1; 1 VP menos y 10 FP menos |
| h=2, regresión + regla: validación | 0,677 | **0,680** | 0,671 | 0,676 | — |
| h=2, regresión + regla: 2024 | 0,802 | 0,807 | **0,808** | **0,808** | +0,001 F1; 5 VP y 6 FP más |
| h=4, regresión + regla: validación | **0,567** | 0,559 | 0,562 | 0,566 | — |
| h=4, regresión + regla: 2024 | 0,758 | **0,760** | 0,753 | 0,754 | −0,006 F1; 10 VP y 3 FP menos; MAE 8,742 → 8,726 |

La señal de la combinación en h=2 es pequeña y en validación quedó por debajo de población sola en ambos enfoques. En h=4, el objetivo principal, añadir la fracción no mejoró de forma útil la clasificación respecto de población sola. Para conteos h=4, la combinación subió el F1 medio de validación frente a población (**0,559 → 0,566**) pero bajó en 2024 (**0,760 → 0,754**); ninguna variante superó a la base en validación. El JSON conserva MAE, Brier, recall, precisión, AUPRC y conteos de cada fold; esta tabla se limita a las comparaciones principales.

En 2025 hubo solo **3 semanas positivas**. Ninguna de las cuatro regresiones las detectó en ambos horizontes. En la clasificación h=4, las tres variantes con alguna variable sociodemográfica detectaron **0/3**; sus diferentes números de falsos avisos no permiten elegir un modelo con seguridad. Los casos de 2025 de la Sala Situacional siguen siendo una fuente válida del proyecto.

## Decisión provisional y límites

Para una matriz compacta de alerta **h=4**, población fija de 2017 sigue siendo la candidata más sencilla de estas cuatro. `Sin_seguro` puede quedarse como alternativa si se prioriza reducir falsos avisos aceptando menor recall. **La combinación de ambas no queda justificada por este ensayo.** Esta decisión es provisional: el cribado previo examinó 15 fracciones con las mismas temporadas, se eligieron umbrales en esas mismas predicciones de validación y 2024 ya se había visto. La fecha exacta de publicación del Excel censal, el significado de ceros históricos sin notificación y la disponibilidad real de casos al origen siguen pendientes.

La secuencia de trabajo que seguía a las ablaciones de familias era cerrar un conjunto pequeño de variables y evaluarlo con un diseño temporal más exigente; la [comparación progresiva posterior](validacion_temporal_compacta.md) realizó ese paso sin ajustar hiperparámetros. No existía una fase numerada adicional ya aprobada después del primer experimento sociodemográfico. Antes de afirmar generalización harán falta datos futuros no utilizados en esta exploración o una evaluación interna adicional de selección.

## Reproducción

```bash
.venv/bin/python -m src.modeling.ablacion_poblacion_sin_seguro
.venv/bin/python -m unittest discover -s tests
```
