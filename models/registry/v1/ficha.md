# V1 · C3·E3·S4_s3 (reemplazada)

| Campo | Valor |
|---|---|
| Estado | **Reemplazada** por la [V2](../v2/ficha.md) (complemento de clima, comparación 20). Nunca se sirvió |
| Tag | `model/v1` (`d6bd0be`), congelada el 2026-10-27 |
| Configuración | `denguekay.model.frozen_configs.CONFIG_2026_V1` (antes `CONFIGURACION_2026_V1`); se carga con `denguekay.model.registry.configuration("v1")` |
| Estudio | [`research/05_fe_hyperparameters`](../../../research/05_fe_hyperparameters/README.md), informe [fe_hiperparametros.md](../../../research/05_fe_hyperparameters/docs/fe_hiperparametros.md), «Fase 5 · Síntesis del encargo»; tag `study/fe-hyperparameters` (`e4bc7b7`) |
| Métricas de selección | `research/05_fe_hyperparameters/docs/metricas/fe_hiperparametros.json` |

## Configuración

| Pieza | Valor |
|---|---|
| Matriz | C3 = `base_6` + B3 (9 columnas) |
| Estrategia | E3: un regresor XGBoost multi-salida (`multi_output_tree`) para t+2, t+3 y t+4 desde el origen o = t − 2 |
| Conteo | `count:poisson` con `base_margin` = log(casos del origen + 0,5) (S4_s3) |
| Probabilidad | P(casos ≥ k) binomial negativa NB2, k = max(⌊umbral⌋ + 1, 2); α dentro de la muestra |
| Hiperparámetros | heredados (el tuning de la fase 3 empató) |
| Calibración y alerta | Platt cronológico; p ≥ 0,50 |
| Semilla de despliegue | 17 |

## Huellas

- **Histórica** (definición original: JSON de la configuración + texto de cinco módulos):
  `88ed2a43b0171a0878b99122b70109be61b27d5d4d29a2b93eae55066fd8f945` (`d6bd0be`).
- **De comportamiento** (decisión D1 del [ADR 0001](../../../docs/decisions/0001-repo-restructure.md)):
  SHA-256 del JSON de la configuración y de las predicciones de referencia (semilla 17) en orden canónico.
  XGBoost da los mismos bits solo con el mismo dispositivo y número de hilos, así que hay un valor por entorno:

  | Entorno | Huella |
  |---|---|
  | `device=cpu,n_jobs=2` (CI) | `be86664973cf5e7ac3af4a29ae0f8887a5191ed1007a0c097aacba3c7190bff5` |
  | `device=cuda` | `1534b535bd19d6945c852c10f64294c1d2b16cd9e4359d074fcac11a9ed3806e` |

La definición de la huella cambió en la reestructuración (28/10/2026, commit `3d54055`). La equivalencia con
la configuración congelada se demuestra con predicciones idénticas bit a bit
(`tests/model/test_frozen_configs.py` y `tests/test_equivalence.py`). El modelo no cambió.

## Gold

Matrices en memoria desde gold h=2 (`meteo_socio_epi_piura_2017_2025_h2_gold.csv`,
`0ff49650f0fa1043bf2ae562d401c0d84307550108ef71d427ba9a20cbd475e3`) y B3 desde el silver epidemiológico
histórico.

## Métricas de selección

19 comparaciones preregistradas con regla simétrica sobre 2022 y 2023 (5 semillas); 2024 solo como contraste.
Frente a la referencia B: la antelación sobre inicios limpios 2022–2023 en h=4 pasa de 0,105 a 0,232 (mediana
de semillas), y frente a la persistencia ya no pierde, pero no la supera (+0,021, IC −0,074 a 0,116).

## HU0007-4

**No cumple.** Clasificación: 4 de 9 celdas (2023 h2 y 2024 h2/h3/h4). Regresión: ninguna; 2023 · h4 queda en
frontera (razón MAE 0,764, razón RMSE 0,852).
