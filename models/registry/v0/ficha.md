# V0 · XGBoost directo por horizonte (servida hoy)

| Campo | Valor |
|---|---|
| Estado | **Servida** por el backend, como `experimental: true` |
| Tag | `model/v0` (`3d59090`) |
| Modelo | E1·S1: un XGBoost por horizonte y tarea, h=2 y h=4 (h=3 responde 409) |
| Predictor | `v0_compact_xgb` (`denguekay.serving.predictors`), desde la fase 3 de la API v1: un paquete con los cuatro boosters (`modelos/<codigo_paquete>/manifest.json`); las predicciones son idénticas a las de antes del motor enchufable (`tests/serving/test_v0_parity.py`) |
| Versiones en la BD | `clf-h2-v1`, `reg-h2-v1`, `clf-h4-v1`, `reg-h4-v1` (en una BD republicada tras la 0005, los siguientes números) |
| Estudio | [`research/03_first_models_and_ablations`](../../../research/03_first_models_and_ablations/README.md), informe [validacion_temporal_compacta.md](../../../research/03_first_models_and_ablations/docs/validacion_temporal_compacta.md); tag `archive/training` (`573219d`) |
| Métricas de selección | [`validacion_temporal_compacta.json`](validacion_temporal_compacta.json) (en esta carpeta; lo lee serving) |

## Configuración

No es una configuración congelada de `denguekay.model.frozen_configs`. Las variantes se leen de
`configs/config.yaml` (`serving.paquete.opciones.variantes`) y los hiperparámetros son `denguekay.model.train.BASE_PARAMS`
(160 árboles, profundidad 3, learning rate 0,05, semilla 17):

| Tarea | Variante | Columnas (h=4; en h=2 los rezagos son 2 y 3) |
|---|---|---|
| Clasificación | `base_6_poblacion_2017` | `casos_lag_4`, `casos_lag_5`, `casos_media_4_h4`, `casos_semanas_positivas_4_h4`, `semana_epi_seno`, `semana_epi_coseno`, `log_poblacion_censo_2017` |
| Regresión + regla | `base_6` | las mismas seis, sin la población |

## Huella

V0 no tiene huella de configuración. Su identidad es el SHA-256 de cada booster
(`version_modelo.sha256_artefacto`). Cada publicación guarda además el SHA-256 de las métricas de selección
(`protocolo_metricas` en la huella de la publicación).

## Gold

| h | Archivo | SHA-256 |
|---|---|---|
| 2 | `meteo_socio_epi_piura_2017_2025_h2_gold.csv` | `0ff49650f0fa1043bf2ae562d401c0d84307550108ef71d427ba9a20cbd475e3` |
| 4 | `meteo_socio_epi_piura_2017_2025_h4_gold.csv` | `f9fbed66572e8641eee82ce1a148562f5121cf8dbd111498f73a8aa78f5f19c6` |

Manifiesto: `33bd3d2ee49d5af678a5309c9ff244b126ec10117f953ccc4508e0b4237b5d57`. Serving rechaza publicar si el
gold actual no coincide con estos hashes.

## Métricas de selección

Criterio: F1 medio no ponderado de 2022 y 2023; ante empate, menos columnas. 2024 es contraste (ya se había
mirado) y 2025, sensibilidad.

| h | Tarea | Variante | F1 medio 2022–2023 | F1 2024 | F1 2025 |
|---|---|---|---:|---:|---:|
| 2 | Regresión + regla | `base_6` | 0,757 | 0,802 | 0,000 |
| 2 | Clasificación | `base_6_poblacion_2017` | 0,695 | 0,645 | 0,017 |
| 4 | Regresión + regla | `base_6` | 0,693 | 0,758 | 0,000 |
| 4 | Clasificación | `base_6_poblacion_2017` | 0,660 | 0,617 | 0,000 |

En regresión, `base_6` y `base_4` están prácticamente empatadas. Las predicciones fuera de muestra por bloque
están en `models/experimentos/validacion_temporal_compacta/predicciones_por_bloque.csv` (11 MB, no versionado:
es un artefacto). Serving las importa como cortes pasados.

## HU0007-4

**No cumple.** Ninguna de las cuatro versiones cumple los umbrales de `parametro_sistema.umbrales_aceptacion`
en el bloque `temporada_2024`. Por eso se sirven como experimentales mediante
`parametro_sistema.seleccion_experimental` (desviación temporal en `docs/backend/desviaciones_oe2.md`).

## Publicación tras la reestructuración (D6)

La huella de una publicación incluye el SHA-256 de todo el código de `src/denguekay/`. La primera
`python -m denguekay.serving.publish` después de la reestructuración registra un reentrenamiento y un run de
MLflow nuevos. Las versiones de esta ficha se reutilizan si los boosters salen idénticos byte a byte (mismo
equipo, dispositivo y `n_jobs`); si no, se crean versiones `candidata` nuevas. Detalle en
`docs/backend/operacion.md`.
