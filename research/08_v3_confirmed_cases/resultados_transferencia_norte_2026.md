# Transferencia retrospectiva de 2026 y sensibilidad a la latitud

Se evaluaron las SE 01–38 de 2026 en los mismos 37 distritos de Lambayeque y 13 de Tumbes de la transferencia de 2025. Se reutilizó el paquete ajustado en Piura al 7 de diciembre de 2024. Los modelos sin latitud se reentrenaron y recalibraron en Piura con los mismos datos, cortes y semillas. Longitud, elevación, hiperparámetros y política de alertas se conservaron.

El solape del CSV y la Sala en 2025 coincidió en los 2 703 pares distrito–semana y en los 1 739 confirmados del año completo. En 2026 las sumas de los distritos cuadraron semana a semana con los controles provinciales y departamentales. El periodo de prueba tuvo 5 739 casos y 136 semanas distritales elevadas en Lambayeque y 1 407 casos y 13 semanas distritales elevadas en Tumbes.

## Probabilidades con el paquete original en 2026

Las cifras de los dos brazos entrenados son medianas entre cinco semillas. El cambio relativo del clima se calcula por semilla antes de tomar la mediana.

| Departamento | Horizonte | Brier b3 | Brier historia y geografía | Brier persistencia probabilística | Cambio relativo del clima |
|---|---:|---:|---:|---:|---:|
| Lambayeque | 2 | 0,03970 | 0,04010 | 0,03722 | -1,05% |
| Lambayeque | 3 | 0,04859 | 0,04873 | 0,04354 | -0,21% |
| Lambayeque | 4 | 0,05397 | 0,05369 | 0,04754 | +0,43% |
| Tumbes | 2 | 0,01937 | 0,01842 | 0,01758 | +4,92% |
| Tumbes | 3 | 0,02533 | 0,02363 | 0,01847 | +6,85% |
| Tumbes | 4 | 0,03014 | 0,02517 | 0,01981 | +19,75% |

La persistencia probabilística tuvo el menor Brier en los seis contrastes con y sin latitud.

## Sensibilidad a la latitud

El cambio al retirar latitud se calcula por semilla como Brier sin latitud menos Brier con latitud. Los valores negativos favorecen la versión sin latitud. La diferencia entre medianas de Brier puede diferir de la mediana de cambios pareados.

| Año | Departamento | Horizonte | Cambio Brier b3 sin latitud | Cambio Brier historia y geografía sin latitud | Clima con latitud | Clima sin latitud |
|---|---|---:|---:|---:|---:|---:|
| 2025 | Lambayeque | 2 | +0,000004 | +0,000011 | -6,13% | -6,69% |
| 2025 | Lambayeque | 3 | +0,000017 | -0,000063 | -11,58% | -11,79% |
| 2025 | Lambayeque | 4 | -0,000005 | +0,000083 | -12,07% | -11,93% |
| 2025 | Tumbes | 2 | -0,000353 | -0,000281 | +22,46% | +22,72% |
| 2025 | Tumbes | 3 | -0,000645 | -0,000580 | +30,28% | +31,42% |
| 2025 | Tumbes | 4 | -0,001062 | -0,000984 | +33,50% | +36,73% |
| 2026 | Lambayeque | 2 | -0,000125 | +0,000039 | -1,05% | -1,29% |
| 2026 | Lambayeque | 3 | -0,000127 | -0,000113 | -0,21% | -0,45% |
| 2026 | Lambayeque | 4 | -0,000355 | -0,000261 | +0,43% | +0,46% |
| 2026 | Tumbes | 2 | -0,000039 | -0,000113 | +4,92% | +5,28% |
| 2026 | Tumbes | 3 | -0,000204 | -0,000284 | +6,85% | +7,65% |
| 2026 | Tumbes | 4 | -0,000477 | -0,000422 | +19,75% | +20,22% |

A cuatro semanas en 2026, retirar latitud redujo el Brier de b3 en 0,00035 en Lambayeque y 0,00048 en Tumbes. El contraste climático en Tumbes siguió siendo desfavorable en los tres horizontes. En Lambayeque el beneficio de 2025 se redujo en 2026 y cambió a un deterioro pequeño a cuatro semanas en ambas configuraciones.

Con latitud y corte de alerta 0,50, b3 detectó 54 de 136 semanas elevadas con 20 falsas alertas en Lambayeque a cuatro semanas. La persistencia probabilística detectó 62 con 10 falsas alertas. En Tumbes, b3 detectó 4 de 13 con 10 falsas alertas y la persistencia probabilística detectó 3 con 4.

La sensibilidad mide el cambio predictivo de retirar latitud de la receta. Las variables geográficas restantes pueden recoger información espacial. La evaluación abarca dos tramos retrospectivos y conserva la limitación de disponibilidad histórica de los archivos.

[Protocolo de la extensión](protocolo_transferencia_norte.md)

Run local de MLflow `1bf190399b064eb08ceec390dc9b0435`.
