# Transferencia de 2026 con ajuste actualizado en Piura

El paquete actualizado usa el corte nominal del 13 de diciembre de 2025. Es el primer origen de h4 para la SE 01 de 2026. El paquete anterior usó el 7 de diciembre de 2024 para que el mismo ajuste cubriera la comparación entre 2025 y 2026.

Se añadieron 3 445 filas de entrenamiento de Piura por ajuste y 3 445 filas de calibración fuera de muestra por horizonte. Se conservaron los predictores con latitud, los hiperparámetros, las cinco semillas y el corte de alerta de 0,50. La evaluación usa las mismas 1 900 filas objetivo por horizonte en las SE 01–38 de 2026. Se verificó igualdad exacta de casos, etiquetas, orígenes y llaves entre los paquetes.

| Departamento | Horizonte | Brier b3 corte 2024 | Brier b3 corte 2025 | Cambio por actualización | Brier historia y geografía corte 2025 | Brier persistencia probabilística corte 2025 | Cambio relativo por clima en el paquete actualizado |
|---|---:|---:|---:|---:|---:|---:|---:|
| Lambayeque | 2 | 0,03970 | 0,03926 | -0,82% | 0,03998 | 0,03725 | -1,33% |
| Lambayeque | 3 | 0,04859 | 0,04814 | -0,78% | 0,04845 | 0,04358 | -0,32% |
| Lambayeque | 4 | 0,05397 | 0,05335 | -0,98% | 0,05329 | 0,04764 | +0,79% |
| Tumbes | 2 | 0,01937 | 0,01883 | -2,49% | 0,01815 | 0,01760 | +3,66% |
| Tumbes | 3 | 0,02533 | 0,02409 | -4,45% | 0,02284 | 0,01848 | +5,60% |
| Tumbes | 4 | 0,03014 | 0,02788 | -6,67% | 0,02394 | 0,01981 | +16,99% |

Las diferencias porcentuales se calculan por semilla y se resumen con la mediana. La persistencia probabilística conserva el menor Brier en los seis contrastes del paquete actualizado.

El corte de 2025 mejora b3 a cuatro semanas en Lambayeque y Tumbes. El efecto climático frente a historia y geografía sigue siendo desfavorable a cuatro semanas en ambos departamentos. Los resultados corresponden a una sensibilidad retrospectiva con archivos revisados y una receta elegida en el estudio de Piura.

[Protocolo](protocolo_transferencia_norte.md)

Run local de MLflow `054473bbee0d4ba3b65207e1de8dd100`.
