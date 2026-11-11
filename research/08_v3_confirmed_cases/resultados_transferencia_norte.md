# Transferencia retrospectiva de Piura a Lambayeque y Tumbes

Se ajustaron cinco semillas por brazo exclusivamente con Piura al 7 de diciembre de 2024. Se evaluaron las SE 01–38 de 2025, con 37 distritos de Lambayeque y 13 de Tumbes. Ambos brazos y las persistencias usaron las mismas 1 900 semanas distritales por horizonte. Los pronósticos se reconstruyeron con archivos históricos revisados. El paquete y el periodo se fijaron antes de puntuar.

[Diseño e insumos](protocolo_transferencia_norte.md)

## Probabilidades

Brier y AP son medianas de las cinco semillas para los brazos entrenados. El cambio relativo de Brier se calcula por semilla frente a historia y geografía y luego se toma la mediana. Brier más bajo y AP más alto son mejores.

| Departamento | h | Positivos / semanas | Brier b3 | Brier historia y geografía | Brier persistencia probabilística | Cambio relativo b3 | AP b3 | AP historia y geografía | AP persistencia probabilística |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Lambayeque | 2 | 9 / 1406 | 0,01127 | 0,01204 | 0,00757 | -6,13% | 0,133 | 0,124 | 0,069 |
| Lambayeque | 3 | 9 / 1406 | 0,00965 | 0,01092 | 0,00616 | -11,58% | 0,229 | 0,228 | 0,156 |
| Lambayeque | 4 | 9 / 1406 | 0,01277 | 0,01446 | 0,00673 | -12,07% | 0,186 | 0,179 | 0,113 |
| Tumbes | 2 | 11 / 494 | 0,02727 | 0,02232 | 0,01494 | +22,46% | 0,275 | 0,402 | 0,535 |
| Tumbes | 3 | 11 / 494 | 0,03874 | 0,02968 | 0,01617 | +30,28% | 0,183 | 0,324 | 0,383 |
| Tumbes | 4 | 11 / 494 | 0,04673 | 0,03512 | 0,02003 | +33,50% | 0,102 | 0,122 | 0,199 |

En las cinco semillas y los tres horizontes, b3 redujo el Brier en Lambayeque y lo elevó en Tumbes frente a historia y geografía. La persistencia probabilística tuvo menor Brier que ambos brazos en los seis contrastes departamento–horizonte.

## Alertas y conteos

El corte de probabilidad de los brazos entrenados y de la persistencia probabilística fue 0,50. La persistencia determinista conservó su regla de conteo. Se reporta la mediana de cada métrica por brazo.

| Departamento | h | Brazo | Semanas elevadas detectadas | Falsas alertas | MAE de casos |
|---|---:|---|---:|---:|---:|
| Lambayeque | 2 | b3_obs | 3 | 15 | 0,552 |
| Lambayeque | 2 | historia_geo | 3 | 17 | 0,548 |
| Lambayeque | 2 | persistencia_det | 1 | 9 | 0,424 |
| Lambayeque | 2 | persistencia_prob | 0 | 3 | 0,424 |
| Lambayeque | 3 | b3_obs | 5 | 13 | 0,618 |
| Lambayeque | 3 | historia_geo | 5 | 16 | 0,607 |
| Lambayeque | 3 | persistencia_det | 2 | 6 | 0,465 |
| Lambayeque | 3 | persistencia_prob | 0 | 2 | 0,465 |
| Lambayeque | 4 | b3_obs | 3 | 21 | 0,735 |
| Lambayeque | 4 | historia_geo | 3 | 23 | 0,710 |
| Lambayeque | 4 | persistencia_det | 3 | 9 | 0,513 |
| Lambayeque | 4 | persistencia_prob | 0 | 1 | 0,513 |
| Tumbes | 2 | b3_obs | 6 | 13 | 2,254 |
| Tumbes | 2 | historia_geo | 6 | 9 | 1,783 |
| Tumbes | 2 | persistencia_det | 5 | 3 | 1,617 |
| Tumbes | 2 | persistencia_prob | 3 | 2 | 1,617 |
| Tumbes | 3 | b3_obs | 4 | 21 | 3,085 |
| Tumbes | 3 | historia_geo | 4 | 15 | 2,044 |
| Tumbes | 3 | persistencia_det | 5 | 5 | 1,711 |
| Tumbes | 3 | persistencia_prob | 0 | 1 | 1,711 |
| Tumbes | 4 | b3_obs | 2 | 25 | 4,109 |
| Tumbes | 4 | historia_geo | 2 | 15 | 2,357 |
| Tumbes | 4 | persistencia_det | 2 | 3 | 1,864 |
| Tumbes | 4 | persistencia_prob | 0 | 1 | 1,864 |

A cuatro semanas, b3 y la persistencia determinista detectaron la misma cantidad de semanas elevadas por departamento. La persistencia determinista produjo 9 falsas alertas frente a 21 de b3 en Lambayeque y 3 frente a 25 en Tumbes. Es una comparación al corte fijado, con 9 y 11 semanas elevadas observadas respectivamente.

## Cobertura e interpretación

La latitud de los 50 distritos evaluados queda fuera del rango de latitudes de entrenamiento de Piura. La elevación y longitud también exceden el rango en algunos distritos de Lambayeque. Se mantuvo la especificación de ambos brazos. Seis centroides de destino provienen de COD-AB por ausencia de su distrito en GADM. Los ceros representan ausencia de confirmados registrados en la fuente. El periodo cubre un solo tramo de vigilancia y la variación entre semillas describe estabilidad del ajuste.

La validación de Piura superó 107 expectativas del integrado y 50 de gold h2. Una segunda ejecución del ajuste reprodujo el manifiesto y los SHA-256 de los diez modelos. Se comprobaron 16 779 días distritales por fuente climática y 68 400 pronósticos de soporte común contando semillas y comparadores. Las métricas y los insumos de la prueba se conservan localmente en `models/experimentos/mejora_modelo/v3_confirmados/transferencia_norte_2025/`.

Run local de MLflow `758c6ccd25324fc6a2d1615fa94b9f21`.

SHA-256 del paquete `682a9fdfeb3f9f3c7e546ae2d8ce5e990f3e91321f72524cad4ff313b951ab65`.

SHA-256 de las métricas `e4fa299d69554fa67d69bdf7d8ba5018bb8addf891763c8fb3b690d439fb8c20`.
