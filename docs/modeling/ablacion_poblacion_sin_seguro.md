# Comparación condicional: población y fracción sin seguro de 2017

**Estado:** ejecutada para h=2 y h=4. El [módulo](../../src/modeling/ablacion_poblacion_sin_seguro.py), el [notebook 29](../../notebooks/29_modelado_ablacion_poblacion_sin_seguro.ipynb) y las [métricas completas](metricas/ablacion_poblacion_sin_seguro.json) documentan los cortes, umbrales, hashes, resultados por temporada y diferencias pareadas. Los modelos y predicciones por fila están en `models/experimentos/ablacion_poblacion_sin_seguro/` fuera de Git.

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
| Base de seis | 0,561 | 0,612 | 763 | 873 | 0,610 |
| + Población fija | 0,584 | **0,620** | **779** | **876** | **0,652** |
| + Sin seguro fija | 0,586 | **0,621** | 754 | 818 | 0,612 |
| + Población y sin seguro | **0,587** | 0,618 | **779** | 887 | 0,641 |

La pregunta condicional compara la última fila con **población sola**. En validación la mejora media fue aproximadamente **+0,003 F1**; las diferencias por temporada fueron **+0,0073 (2021)**, **+0,0002 (2022)** y **+0,0006 (2023)**. En 2024, al añadir `sin_seguro` a población, el F1 bajó **0,0027**, los aciertos permanecieron en **779** y aparecieron **11 falsos avisos más**. La AUPRC también bajó de **0,652 a 0,641**. Por tanto, **no hay evidencia convincente de aporte incremental de `sin_seguro` sobre población fija** en la alerta h=4 de este XGBoost.

`Sin_seguro` sola logra un F1 casi igual al de población sola en 2024, pero representa otra compensación: **25 semanas elevadas acertadas menos** y **58 falsos avisos menos**. Elegir entre esas dos alertas exigiría acordar el costo de una semana elevada no detectada frente al de un falso aviso. Ninguna asociación debe interpretarse como efecto causal del seguro sobre dengue o notificación.

## Horizonte de dos semanas y regresión de casos

| Horizonte / enfoque | Base F1 | Población F1 | Sin seguro F1 | Ambas F1 | Comparación de ambas vs población en 2024 |
|---|---:|---:|---:|---:|---|
| h=2, clasificación: validación | 0,594 | 0,650 | 0,629 | 0,650 | — |
| h=2, clasificación: 2024 | 0,641 | 0,643 | **0,651** | 0,645 | +0,002 F1; mismos 808 VP y 7 FP menos |
| h=2, regresión + regla: validación | 0,669 | 0,670 | 0,677 | **0,680** | — |
| h=2, regresión + regla: 2024 | 0,802 | 0,802 | **0,806** | 0,805 | +0,003 F1; 6 VP y 3 FP más |
| h=4, regresión + regla: validación | **0,571** | 0,561 | 0,564 | 0,561 | — |
| h=4, regresión + regla: 2024 | 0,752 | **0,759** | 0,757 | **0,759** | prácticamente igual F1; MAE 9,032 → 8,960 |

La señal de la combinación en h=2 es pequeña. En h=4, el objetivo principal, añadir la fracción no mejoró de forma útil la clasificación respecto de población sola. Para conteos, la combinación no mejoró el F1 medio de validación frente a población. El JSON conserva MAE, Brier, recall, precisión, AUPRC y conteos de cada fold; esta tabla se limita a las comparaciones principales.

En 2025 hubo solo **3 semanas positivas**. Ninguna de las cuatro regresiones las detectó en ambos horizontes. En la clasificación h=4, las tres variantes con alguna variable sociodemográfica detectaron **0/3**; sus diferentes números de falsos avisos no permiten elegir un modelo con seguridad. Los casos de 2025 de la Sala Situacional siguen siendo una fuente válida del proyecto.

## Decisión provisional y límites

Para una matriz compacta de alerta **h=4**, población fija de 2017 sigue siendo la candidata más sencilla de estas cuatro. `Sin_seguro` puede quedarse como alternativa si se prioriza reducir falsos avisos aceptando menor recall. **La combinación de ambas no queda justificada por este ensayo.** Esta decisión es provisional: el cribado previo examinó 15 fracciones con las mismas temporadas, se eligieron umbrales en esas mismas predicciones de validación y 2024 ya se había visto. La fecha exacta de publicación del Excel censal, el significado de ceros históricos sin notificación y la disponibilidad real de casos al origen siguen pendientes.

La secuencia de trabajo que seguía a las ablaciones de familias era cerrar un conjunto pequeño de variables y evaluarlo con un diseño temporal más exigente; la [comparación progresiva posterior](validacion_temporal_compacta.md) realizó ese paso sin ajustar hiperparámetros. No existía una fase numerada adicional ya aprobada después del primer experimento sociodemográfico. Antes de afirmar generalización harán falta datos futuros no utilizados en esta exploración o una evaluación interna adicional de selección.

## Reproducción

```bash
.venv/bin/python -m src.modeling.ablacion_poblacion_sin_seguro
.venv/bin/python -m unittest discover -s tests
```
