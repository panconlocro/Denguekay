# Protocolo de evaluación de la V3

> **Este NO es el protocolo de la V2.** La V2 se eligió con el protocolo del estudio 05: calibración con 2021,
> selección con 2022–2023 y contraste con 2024. La V3 se eligió en el estudio 06
> (`research/06_model_improvement`) con el protocolo que describe este documento: bloques por temporada desde
> 2008, seis temporadas que deciden (incluida 2026) y validación dejando una temporada fuera. Las cifras de la V2
> y de la V3 no son comparables celda a celda si se calcularon con protocolos distintos.

Configuración: `denguekay.model.frozen_configs.CONFIG_V3` (ficha en
[`models/registry/v3/ficha.md`](../../models/registry/v3/ficha.md)). Código de entrenamiento y evaluación:
`research/06_model_improvement/code/` en el tag `model/v3`; la corrida de referencia es
`phase_v3_close.py`. Cómo reproducirla desde un clon: [reproducir_v3.md](reproducir_v3.md).

## 1. Unidad, horizontes y etiqueta

- **Unidad:** distrito × semana epidemiológica (65 distritos de Piura; semanas de domingo a sábado, numeración
  MMWR de `denguekay.data.calendar`).
- **Origen:** la última semana con casos conocidos, `o`. `origen_cierre` es el sábado que cierra esa semana.
- **Horizontes:** h = 2, 3 y 4. La semana objetivo empieza `h` semanas después de la semana del origen (`t + h`).
  Un solo regresor multisalida (estrategia E3) predice las tres semanas a la vez desde el mismo origen.
- **Etiqueta `brote`:** `denguekay.features.outbreak_label.future_outbreak_threshold` calcula el umbral
  `umbral_brote_casos` = media + 1,5 · DE (muestral, `ddof=1`) de los casos de la misma semana epidemiológica en
  los 5 años anteriores (la semana 53 se suma a la 52; los años sin registro en la historia anterior al panel
  cuentan como 0). `brote = 1` si `casos_Dengue > umbral_brote_casos` **y** `casos_Dengue >= 2` (regla de gold con
  el mínimo de 2 casos del estudio 06, `OUTBREAK_RULE` de `phase0_diagnosis.py`). La serie de casos empieza en
  2000, así que hay etiquetas desde 2005.
- **Temporada epidemiológica:** de la semana 35 de un año a la semana 34 del siguiente; la temporada `Y` termina
  en el año `Y` (`denguekay.evaluation.onsets.with_season`).

## 2. Bloques y cortes

Cada bloque es un conjunto de semanas objetivo. Para cada bloque y cada semilla se entrena un modelo nuevo:

| Bloque | Semanas objetivo (h = 2) | Rol |
|---|---|---|
| `temporada_2008` … `temporada_2024` | semana 35 del año anterior a semana 34 del año | evaluación por temporada |
| `calendario_2025` | año calendario 2025 | sensibilidad (se solapa con `temporada_2026`) |
| `temporada_2026` | semana 35 de 2025 a semana 34 de 2026 | decide |
| `posterior_2026` | semana 35 de 2026 en adelante (hasta la última semana no provisional) | solo se reporta |

- **Corte de entrenamiento:** el primer origen del bloque (el `origen_cierre` más temprano entre los tres
  horizontes). Se entrena con todos los orígenes **desde 2005** cuyo objetivo de h = 4 ya cerró en ese corte
  (`semana_inicio_h4 + 6 días <= corte`). Ningún dato posterior al corte entra a los árboles del bloque.
- **Calibración (Platt, por horizonte):** para cada bloque y horizonte, una regresión logística de `brote` sobre
  `logit(p)` (p recortada a [1e-6, 1 − 1e-6]) ajustada con las predicciones fuera de muestra de los **bloques
  anteriores** (por fecha de inicio) cuya etiqueta cerró en el primer origen **de ese horizonte** en el bloque.
  Ese origen es posterior al corte de entrenamiento (común a los tres horizontes), así que el calibrador de h2 usa
  hasta 2 semanas de etiquetas más que el de h4; todas cerraron antes de la primera predicción que calibran. Probabilidad calibrada
  = 1 / (1 + exp(−(a · logit(p) + b))). El primer bloque (`temporada_2008`) queda sin calibrar.
- **Huecos y solapes entre bloques** (no son fugas):
  - Las semanas objetivo del 2024-08-25 al 2024-12-22 (18 semanas) no tienen predicción fuera de muestra.
    `temporada_2024` termina el 2024-08-18 y `calendario_2025` empieza el 2024-12-29, así que esas semanas
    tampoco entran a la calibración de los bloques siguientes.
  - `calendario_2025` y `temporada_2026` predicen las mismas semanas del 2025-08-24 al 2025-12-28. La
    calibración y la `w` de `posterior_2026` cuentan esas 1 235 semanas dos veces (2 470 filas por horizonte,
    con 1 semana brote). Solo afecta a `posterior_2026`.
- **Conteo publicado (5a):** `w · μ + (1 − w) · persistencia`, con `w` por horizonte y bloque ajustada con las
  mismas filas anteriores cerradas que usa Platt (sin filas, `w = 1`).
- **Probabilidad cruda:** P(casos ≥ k) de una binomial negativa NB2 con media μ y dispersión α estimada dentro de
  la muestra de entrenamiento del bloque (una α por horizonte), con k = max(⌊umbral⌋ + 1, 2).

## 3. Modelo

- **Variables (13):** `base_6` (`hist_lag_a`, `hist_lag_b`, `hist_media_4`, `hist_semanas_pos_4`,
  `semana_epi_seno`, `semana_epi_coseno`), B3 (`propia_semanas_desde_ultimo_caso`, `propia_pendiente_4`,
  `propia_log_casos_temporada_anterior`) y d3: temperatura media de ERA5-Land del polígono distrital en la semana
  del origen (`temp_media_s0`) y sus medias de o−1..o−4, o−5..o−8 y o−9..o−12.
- **XGBoost** `count:poisson`, `multi_output_tree`, `base_margin = log(casos del origen + 0,5)` en las tres
  salidas. Hiperparámetros del trial 191 (`frozen_configs.V3_HYPERPARAMETERS`).
- **Semillas:** 17, 29, 41, 53 y 67. Las métricas de decisión son la mediana entre semillas; la semilla 17 es la de
  despliegue y la de la huella.
- **Dispositivo:** la referencia se entrenó en GPU (`device=cuda`, XGBoost 3.4.1). En CPU las predicciones no
  coinciden bit a bit con las de GPU (ver [reproducir_v3.md](reproducir_v3.md)).

## 4. Temporadas que deciden y contraste

- **Deciden (regla `SEASON_2026`):** 2010, 2015, 2016, 2022, 2023 y 2026.
  - **Métrica principal:** Brier de la probabilidad calibrada.
  - **Ganar un horizonte:** al menos 5 de 6 temporadas a favor y 0 en contra. Una diferencia cuenta solo si
    supera el umbral de empate, que es el rango entre semillas.
  - **Guardas:** AUPRC, F1 a 0,50, razón MAE y antelación. Vetan con 4 o más de 6 temporadas en contra.
- **Adopción:** frente a la referencia, al menos 2 horizontes ganados en el Brier, y ningún «pierde» ni
  «compensa» en el Brier, en la alerta (F1) ni en el conteo (razón MAE).
- **Filtro fuera de temporada (LOSO):** al menos 16 de 24 celdas mejores (3 horizontes × 8 temporadas: las 6
  que deciden más 2017 y 2024). Cada temporada se predice con un modelo entrenado sin ella, con 4 semanas de
  margen a cada lado.
- **Ajuste de hiperparámetros:** Optuna TPE sobre otras temporadas, 2008, 2009, 2011–2014 y 2018–2021, con el
  objetivo medido en 2009, 2012, 2013, 2014, 2018 y 2021. Son disjuntas de las que deciden y de las del filtro.
- **Comparador pareado sin clima:** L + 5a con los mismos hiperparámetros (sin d3). Está en las predicciones de
  referencia para medir lo que aporta el clima con el modelo final.
- **Prueba independiente:** 2026 se usó para elegir. La única evaluación independiente de la V3 es la
  prospectiva: lo que se publique después del congelamiento (2026-11-09), en la temporada 2026–27, frente a b3
  (la retadora).

## 5. Predicciones de referencia

Las predicciones de referencia son los archivos `models/experimentos/mejora_modelo/v3/predicciones_v3.csv.gz`
(V3) y `predicciones_l5a_sin_clima.csv.gz` (L + 5a), que también están en `predicciones_v3.zip` del Release
`model/v3`. Tienen una fila por variante, semilla, bloque, horizonte, distrito y semana objetivo.

| Columna | Descripción |
|---|---|
| `variante` | `V3` (L + 5a + d3) o `L + 5a` (comparador sin clima) |
| `semilla` | semilla de XGBoost (17, 29, 41, 53, 67) |
| `bloque` | bloque de evaluación (sección 2) |
| `horizonte` | 2, 3 o 4 semanas |
| `ubigeo` | código del distrito, texto de 6 dígitos |
| `anio`, `semana` | año y semana epidemiológica de la semana objetivo |
| `semana_inicio` | domingo de la semana objetivo |
| `origen_cierre` | sábado que cierra la semana de origen (dato más reciente que usó la predicción) |
| `casos_Dengue` | casos observados en la semana objetivo |
| `brote` | etiqueta observada (0/1, sección 1) |
| `umbral_brote_casos` | umbral de la etiqueta para esa semana (casos) |
| `persistencia` | casos de la semana de origen (la predicción ingenua) |
| `estacional` | línea base estacional del protocolo: casos del mismo distrito 52 semanas antes de la semana objetivo (no entra al modelo) |
| `mu_modelo` | media μ del regresor (casos) |
| `w_mezcla` | peso `w` de la mezcla 5a del bloque y horizonte |
| `conteo_publicado` | `w_mezcla · mu_modelo + (1 − w_mezcla) · persistencia` (casos) |
| `alpha_usada` | dispersión α de la NB2 del bloque y horizonte (dentro de la muestra de entrenamiento) |
| `probabilidad_cruda` | P(casos ≥ k) de la NB2(μ, α) |
| `probabilidad_calibrada` | probabilidad con Platt; vacía en `temporada_2008` |
| `platt_a`, `platt_b` | pendiente e intercepto de Platt del bloque y horizonte |
| `filas_calibracion`, `positivos_calibracion` | filas y semanas brote con las que se ajustó Platt (y `w`) |

Brier y AUPRC por bloque: `phase_v3_close.block_metrics` (Brier = media de (p − y)²; AUPRC = precisión media de
scikit-learn); cifras en `research/06_model_improvement/docs/metricas/v3.json`.

## 6. Cortes exactos por bloque (R20)

Cada bloque tiene un solo corte de entrenamiento para los tres horizontes: el primer origen entre los tres. Se
entrena con los orígenes cuyo objetivo de h = 4 cerró en ese corte. El primer origen de entrenamiento es
siempre 2004-12-25 (cierre de la semana de origen que empieza el 2004-12-19).

- **Orígenes y semanas objetivo:** la tabla muestra los de h = 2; los de h = 3 y h = 4 están corridos una y dos
  semanas.
- **Calibración:** Platt y la `w` de 5a usan, por horizonte, las filas de los bloques anteriores cuya etiqueta
  cerró en el primer origen del bloque. Por eso las filas de calibración cambian con el horizonte.
- **Detalle completo** por bloque y horizonte (primer y último origen, última etiqueta usada por el
  calibrador): `research/06_model_improvement/docs/metricas/v3.json → cortes`. Lo calcula
  `phase_v3_close.cutoff_table`, que comprueba que las filas de calibración coinciden con las guardadas en las
  predicciones.

| Bloque | Corte de entrenamiento | Filas de entrenamiento | Último objetivo h4 entrenado | Orígenes evaluados (h2) | Semanas objetivo (h2) | Filas / positivos evaluados (h2 · h3 · h4) | Bloques de Platt | Filas / positivos de calibración (h2 · h3 · h4) |
|---|---|---|---|---|---|---|---|---|
| `temporada_2008` | 2007-08-04 | 8 645 | 2007-07-29 | 2007-08-18 a 2008-08-09 | 2007-08-26 a 2008-08-17 | 3 380 / 85 · 3 380 / 85 · 3 380 / 85 | ninguno (sin calibrar) | 0 / 0 · 0 / 0 · 0 / 0 |
| `temporada_2009` | 2008-08-02 | 12 025 | 2008-07-27 | 2008-08-16 a 2009-08-15 | 2008-08-24 a 2009-08-23 | 3 445 / 174 · 3 445 / 174 · 3 445 / 174 | `temporada_2008` | 3 315 / 83 · 3 250 / 81 · 3 185 / 81 |
| `temporada_2010` | 2009-08-08 | 15 470 | 2009-08-02 | 2009-08-22 a 2010-08-14 | 2009-08-30 a 2010-08-22 | 3 380 / 234 · 3 380 / 234 · 3 380 / 234 | `temporada_2008` … `temporada_2009` (2) | 6 760 / 258 · 6 695 / 257 · 6 630 / 255 |
| `temporada_2011` | 2010-08-07 | 18 850 | 2010-08-01 | 2010-08-21 a 2011-08-13 | 2010-08-29 a 2011-08-21 | 3 380 / 13 · 3 380 / 13 · 3 380 / 13 | `temporada_2008` … `temporada_2010` (3) | 10 140 / 491 · 10 075 / 490 · 10 010 / 488 |
| `temporada_2012` | 2011-08-06 | 22 230 | 2011-07-31 | 2011-08-20 a 2012-08-11 | 2011-08-28 a 2012-08-19 | 3 380 / 64 · 3 380 / 64 · 3 380 / 64 | `temporada_2008` … `temporada_2011` (4) | 13 520 / 506 · 13 455 / 505 · 13 390 / 505 |
| `temporada_2013` | 2012-08-04 | 25 610 | 2012-07-29 | 2012-08-18 a 2013-08-10 | 2012-08-26 a 2013-08-18 | 3 380 / 85 · 3 380 / 85 · 3 380 / 85 | `temporada_2008` … `temporada_2012` (5) | 16 900 / 566 · 16 835 / 562 · 16 770 / 558 |
| `temporada_2014` | 2013-08-03 | 28 990 | 2013-07-28 | 2013-08-17 a 2014-08-09 | 2013-08-25 a 2014-08-17 | 3 380 / 58 · 3 380 / 58 · 3 380 / 58 | `temporada_2008` … `temporada_2013` (6) | 20 280 / 655 · 20 215 / 655 · 20 150 / 655 |
| `temporada_2015` | 2014-08-02 | 32 370 | 2014-07-27 | 2014-08-16 a 2015-08-15 | 2014-08-24 a 2015-08-23 | 3 445 / 557 · 3 445 / 557 · 3 445 / 557 | `temporada_2008` … `temporada_2014` (7) | 23 660 / 709 · 23 595 / 704 · 23 530 / 701 |
| `temporada_2016` | 2015-08-08 | 35 815 | 2015-08-02 | 2015-08-22 a 2016-08-13 | 2015-08-30 a 2016-08-21 | 3 380 / 395 · 3 380 / 395 · 3 380 / 395 | `temporada_2008` … `temporada_2015` (8) | 27 105 / 1 258 · 27 040 / 1 247 · 26 975 / 1 239 |
| `temporada_2017` | 2016-08-06 | 39 195 | 2016-07-31 | 2016-08-20 a 2017-08-12 | 2016-08-28 a 2017-08-20 | 3 380 / 539 · 3 380 / 539 · 3 380 / 539 | `temporada_2008` … `temporada_2016` (9) | 30 485 / 1 661 · 30 420 / 1 655 · 30 355 / 1 648 |
| `temporada_2018` | 2017-08-05 | 42 575 | 2017-07-30 | 2017-08-19 a 2018-08-11 | 2017-08-27 a 2018-08-19 | 3 380 / 62 · 3 380 / 62 · 3 380 / 62 | `temporada_2008` … `temporada_2017` (10) | 33 865 / 2 199 · 33 800 / 2 196 · 33 735 / 2 188 |
| `temporada_2019` | 2018-08-04 | 45 955 | 2018-07-29 | 2018-08-18 a 2019-08-10 | 2018-08-26 a 2019-08-18 | 3 380 / 1 · 3 380 / 1 · 3 380 / 1 | `temporada_2008` … `temporada_2018` (11) | 37 245 / 2 266 · 37 180 / 2 266 · 37 115 / 2 266 |
| `temporada_2020` | 2019-08-03 | 49 335 | 2019-07-28 | 2019-08-17 a 2020-08-08 | 2019-08-25 a 2020-08-16 | 3 380 / 2 · 3 380 / 2 · 3 380 / 2 | `temporada_2008` … `temporada_2019` (12) | 40 625 / 2 267 · 40 560 / 2 267 · 40 495 / 2 267 |
| `temporada_2021` | 2020-08-01 | 52 715 | 2020-07-26 | 2020-08-15 a 2021-08-14 | 2020-08-23 a 2021-08-22 | 3 445 / 90 · 3 445 / 90 · 3 445 / 90 | `temporada_2008` … `temporada_2020` (13) | 44 005 / 2 269 · 43 940 / 2 269 · 43 875 / 2 269 |
| `temporada_2022` | 2021-08-07 | 56 160 | 2021-08-01 | 2021-08-21 a 2022-08-13 | 2021-08-29 a 2022-08-21 | 3 380 / 431 · 3 380 / 431 · 3 380 / 431 | `temporada_2008` … `temporada_2021` (14) | 47 450 / 2 353 · 47 385 / 2 346 · 47 320 / 2 340 |
| `temporada_2023` | 2022-08-06 | 59 540 | 2022-07-31 | 2022-08-20 a 2023-08-12 | 2022-08-28 a 2023-08-20 | 3 380 / 1 039 · 3 380 / 1 039 · 3 380 / 1 039 | `temporada_2008` … `temporada_2022` (15) | 50 830 / 2 788 · 50 765 / 2 786 · 50 700 / 2 784 |
| `temporada_2024` | 2023-08-05 | 62 920 | 2023-07-30 | 2023-08-19 a 2024-08-10 | 2023-08-27 a 2024-08-18 | 3 380 / 857 · 3 380 / 857 · 3 380 / 857 | `temporada_2008` … `temporada_2023` (16) | 54 210 / 3 793 · 54 145 / 3 761 · 54 080 / 3 723 |
| `calendario_2025` | 2024-12-07 | 67 470 | 2024-12-01 | 2024-12-21 a 2025-12-20 | 2024-12-29 a 2025-12-28 | 3 445 / 3 · 3 445 / 3 · 3 445 / 3 | `temporada_2008` … `temporada_2024` (17) | 57 655 / 4 686 · 57 655 / 4 686 · 57 655 / 4 686 |
| `temporada_2026` | 2025-08-02 | 69 680 | 2025-07-27 | 2025-08-16 a 2026-08-15 | 2025-08-24 a 2026-08-23 | 3 445 / 89 · 3 445 / 89 · 3 445 / 89 | `temporada_2008` … `calendario_2025` (18) | 59 800 / 4 688 · 59 735 / 4 688 · 59 670 / 4 688 |
| `posterior_2026` | 2026-08-08 | 73 125 | 2026-08-02 | 2026-08-22 a 2026-10-03 | 2026-08-30 a 2026-10-11 | 455 / 167 · 455 / 167 · 455 / 167 | `temporada_2008` … `temporada_2026` (19) | 64 480 / 4 763 · 64 415 / 4 749 · 64 350 / 4 736 |

## 7. Especificación completa del entrenamiento (R16, R30)

| Hiperparámetro (trial 191) | Valor |
|---|---|
| `n_estimators` | 1055 |
| `max_depth` | 8 |
| `learning_rate` | 0.012202198485831055 |
| `min_child_weight` | 1.3472042263917448 |
| `subsample` | 0.6374222616667551 |
| `colsample_bytree` | 0.5231175260584356 |
| `reg_lambda` | 27.462610520474446 |
| `reg_alpha` | 0.8263569818396628 |
| `gamma` | 0.010338285504760625 |
| `max_delta_step` | 1.5830208659380955 |

- **Objetivo y árboles:**
  - XGBoost 3.4.1 con `XGBRegressor(objective="count:poisson", tree_method="hist",
    multi_strategy="multi_output_tree")`.
  - `base_margin = log(casos de la semana de origen + 0,5)` en las tres salidas (h = 2, 3 y 4).
  - Un solo modelo por bloque y semilla, sin `sample_weight`.
- **Pérdida de los tres horizontes:**
  - Es la deviance de Poisson de cada salida, sin pesos por horizonte.
  - Con `multi_output_tree`, cada hoja es un vector de 3 valores y la ganancia de un corte agrega la de las 3
    salidas.
  - Las hojas compartidas no definen una distribución conjunta de las semanas futuras: cada salida se usa como
    una media marginal.
- **Dispositivo e hilos:** `device="cuda"` (NVIDIA GeForce RTX 5060, driver 621.01, XGBoost compilado con CUDA
  13.3) y `n_jobs=12` (`device: auto` y `n_jobs: auto` en `configs/config.yaml`). `random_state` = semilla.
- **Semillas:** 17, 29, 41, 53 y 67. La 17 es la de despliegue y la de la huella.
- **Dispersión NB2:** α por horizonte y bloque, por máxima verosimilitud sobre las predicciones dentro de la
  muestra de entrenamiento (`negative_binomial_dispersion`, log α acotado en [−12, 6]). Las α usadas están en
  la columna `alpha_usada`.
- **Platt:** `LogisticRegression(C=1e6, max_iter=1000)` de scikit-learn sobre logit(clip(p, 1e-6, 1 − 1e-6)).
- **Ajuste de hiperparámetros** (`HP_TUNING`, notebook 19 del estudio 06):
  - Optuna 4.9.0, `TPESampler(seed=20261108, n_startup_trials=20)`, sin pruning.
  - XGBoost con la semilla 17. Presupuesto de 300 trials con tope de 10 h de pared: se alcanzó el tope con
    255 trials completos y 0 fallidos.
  - El trial 0 fueron los heredados con `reg_alpha = 1e-3`.
  - Objetivo: media del Brier calibrado relativo a los heredados en 18 celdas (h2–h4 × 2009, 2012, 2013, 2014,
    2018 y 2021).
  - Las 5 mejores se recalcularon con 5 semillas; la candidata fue la de menor mediana. Después se aplicaron
    la regla `SEASON_2026` y el filtro LOSO (sección 4).
  - Los trials fallidos se registran sin detener la búsqueda (`catch=(Exception,)`); no hubo ninguno.
  - El estudio de Optuna quedó guardado en `models/experimentos/mejora_modelo/ajuste_hp/optuna.db` (no está en
    el Release).

| Espacio de búsqueda | Tipo | Mínimo | Máximo | Escala |
|---|---|---|---|---|
| `max_depth` | entero | 2 | 8 | lineal |
| `min_child_weight` | real | 1.0 | 100.0 | logarítmica |
| `learning_rate` | real | 0.01 | 0.3 | logarítmica |
| `n_estimators` | entero | 100 | 1500 | lineal |
| `subsample` | real | 0.5 | 1.0 | lineal |
| `colsample_bytree` | real | 0.5 | 1.0 | lineal |
| `reg_lambda` | real | 0.001 | 50.0 | logarítmica |
| `reg_alpha` | real | 0.001 | 10.0 | logarítmica |
| `gamma` | real | 0.0 | 5.0 | lineal |
| `max_delta_step` | real | 0.3 | 2.0 | lineal |

## 8. Producto climático de d3 (R14)

- **Fuente:**
  - Open-Meteo, Historical Weather API (archive), con `models=era5_land` fijado en la petición
    (`denguekay.data.ingestion.openmeteo.fetch_district`).
  - ERA5-Land tiene 0,1° de resolución (unos 11 km).
  - Variable diaria `temperature_2m_mean`, con `timezone=America/Lima`.
- **Punto por distrito:**
  - Un punto por distrito: el centroide de `data/reference/distritos_piura_coords.csv`. No es un promedio
    ponderado por área.
  - Open-Meteo devuelve la celda de la grilla más cercana; sus coordenadas y su elevación quedan en el caché
    bronze (`lat_celda`, `lon_celda`, `elevacion_celda`).
- **Agregación semanal:** media de los 7 días de la semana MMWR (domingo a sábado). Las semanas incompletas de
  los bordes se descartan (`weekly_aggregation.aggregate_to_weekly`).
- **Descargas (cachés bronze):**
  - `cache_meteo_era5_land_2000_2016/` y `cache_meteo_era5_land_2017_2025/`, del 2026-11-04;
  - `cache_meteo_era5_land_2026/`, del 2026-11-08, con días del 2026-01-01 al 2026-10-31.
- **Silver usado:** `data/silver/meteo_humedad_era5_land_2000_2026.csv`, con 91 000 filas hasta la semana del
  2026-10-25.
  - SHA-256 `3e91e57f31fa47af3f01515caa42ec1cf758ecfbe0320cbea50d23fb73d03879`.
  - Está en `datos_v3.zip`. Las cachés bronze no están en el Release.
- **Disponibilidad:** el código del estudio asume que ERA5-Land se publica unos días después de cada sábado
  (`ERA5_LAND_DELAY_DAYS` en `phase1b_prime.py` y `phase_b3_full_climate.py`). La retrospectiva usa los valores
  del archivo descargado, no los publicados en cada origen.
- **Otros insumos que lee el código (d3 no los usa):** el código arma también las columnas de b3, d1 y d2.
  - CHIRPS v3: el silver semanal, el bronze diario `ee_final` y las ventanas preliminares de 2026.
  - El Niño 1+2 de `enso_nino12_mensual.csv`.
  - Por eso esos archivos están en `datos_v3.zip`.

## 9. Diccionario de las variables de la V3 (R13)

Generado con `denguekay.model.variable_dictionary.compact_markdown(CONFIG_V3["columnas"])`.

- **Faltantes:** en la V3 la serie de casos empieza en 2000. Los nulos de arranque de las variables de historia
  quedan antes de 2005, así que ningún origen de entrenamiento o evaluación se excluye.
- **No son predictores:** el `ubigeo`, la población y las fracciones sociodemográficas.
- **Insumo aparte:** el margen de persistencia, `log(casos del origen + 0,5)`, entra como `base_margin`, no
  como columna.

| Columna | Definición | Unidades | Ventana | Transformación | Faltantes |
|---|---|---|---|---|---|
| `hist_lag_a` | casos de dengue de la semana de origen o | casos | semana o | ninguna (conteo) | en gold, las 2 primeras semanas de cada distrito; esas filas no entran a la tabla de orígenes |
| `hist_lag_b` | casos de dengue de la semana o − 1 | casos | semana o − 1 | ninguna (conteo) | en gold, las 3 primeras semanas de cada distrito; no entran a la tabla de orígenes |
| `hist_media_4` | media de casos de las semanas o − 3 a o | casos por semana | semanas o − 3..o | media móvil de 4 semanas | en gold, las 5 primeras semanas de cada distrito; no entran a la tabla de orígenes |
| `hist_semanas_pos_4` | número de semanas con al menos 1 caso entre o − 3 y o | semanas (0–4) | semanas o − 3..o | conteo de semanas positivas (0–4) | en gold, las 5 primeras semanas de cada distrito; no entran a la tabla de orígenes |
| `semana_epi_seno` | sen(2π · ((semana epi de t) − 1) mód 52 / 52) | adimensional (−1 a 1) | semana objetivo t (conocida de antemano) | codificación cíclica | ninguno |
| `semana_epi_coseno` | cos(2π · ((semana epi de t) − 1) mód 52 / 52) | adimensional (−1 a 1) | semana objetivo t (conocida de antemano) | codificación cíclica | ninguno |
| `propia_semanas_desde_ultimo_caso` | semanas transcurridas desde la última semana con casos del distrito, hasta o | semanas (0–52) | semanas ≤ o | tope 52 semanas | ninguno (sin caso previo = tope) |
| `propia_pendiente_4` | pendiente MCO de log(1 + casos) en las semanas o − 3..o | log(1 + casos) por semana | semanas o − 3..o | log1p y pendiente lineal de 4 puntos | nulo si faltan semanas de historia; ver el conteo de nulos en la tabla de orígenes |
| `propia_log_casos_temporada_anterior` | log(1 + casos de la temporada anterior completa del distrito) | log(1 + casos) | temporada anterior, cerrada antes de o | suma de la temporada y log1p | nulo solo si falta en la historia un año necesario; la fila no se excluye |
| `temp_media_s0` | temperatura media de la semana de origen o | °C | semana o | media de las temperaturas medias semanales de la ventana, sin climatología ni anomalía | nulo si falta alguna semana de la ventana; ningún origen de 2005 en adelante queda nulo (guarda G42 del estudio 06), así que no se excluye ninguna fila |
| `temp_media_media_s1_4` | media de la temperatura media semanal de o − 4 a o − 1 | °C | semanas o − 4..o − 1 | media de las temperaturas medias semanales de la ventana, sin climatología ni anomalía | nulo si falta alguna semana de la ventana; ningún origen de 2005 en adelante queda nulo (guarda G42 del estudio 06), así que no se excluye ninguna fila |
| `temp_media_media_s5_8` | media de la temperatura media semanal de o − 8 a o − 5 | °C | semanas o − 8..o − 5 | media de las temperaturas medias semanales de la ventana, sin climatología ni anomalía | nulo si falta alguna semana de la ventana; ningún origen de 2005 en adelante queda nulo (guarda G42 del estudio 06), así que no se excluye ninguna fila |
| `temp_media_media_s9_12` | media de la temperatura media semanal de o − 12 a o − 9 | °C | semanas o − 12..o − 9 | media de las temperaturas medias semanales de la ventana, sin climatología ni anomalía | nulo si falta alguna semana de la ventana; ningún origen de 2005 en adelante queda nulo (guarda G42 del estudio 06), así que no se excluye ninguna fila |

## 10. Comparadores guardados (`comparadores_v3.zip`)

Las predicciones se guardaron con el mismo protocolo de bloques y las mismas semillas (17, 29, 41, 53 y 67).
Son las predicciones crudas del modelo: `casos_predichos` es μ sin mezclar y `probabilidad_brote` es la NB2
sin Platt. La mezcla 5a y Platt se recalculan con `phase5_counts.evaluate_mixture`. La columna `estacional` es
el rezago de `SEASONAL_LAG` = 52 semanas (`horizon_strategies.SEASONAL_LAG`, confirmado en el código).

| Archivo (en `models/experimentos/mejora_modelo/`) | Qué es | Bloques |
|---|---|---|
| `fase6/predicciones_6a_prima_poisson_glm.csv.gz` y `ajustes_6a_prima_poisson_glm.csv` | GLM Poisson + α NB2 (enmienda 6a′), matriz C3 sin clima | 2008–2024 y `calendario_2025`; **sin 2026** |
| `fase6/predicciones_6a_nb_glm.csv.gz` y `ajustes_6a_nb_glm.csv` | GLM binomial negativa NB2 (6a; no convergió en al menos un horizonte de cada bloque, ver `ajustes`; no interpretable) | 2008–2024 y `calendario_2025`; **sin 2026** |
| `fase6/predicciones_6b_lightgbm.csv.gz` y `ajustes_6b_lightgbm.csv` | LightGBM 4.7.0 con la matriz C3 (base_6 + B3) y orígenes desde 2005, sin clima | 2008–2024 y `calendario_2025`; **sin 2026** |
| `temporada_2026/predicciones_L_5a.csv.gz` | L + 5a con hiperparámetros heredados (referencia sin clima) | 2008–2026 (20 bloques) |
| `matriz_clima/predicciones_d3.csv.gz` | L + 5a + d3 con hiperparámetros heredados (contra la que ganó el trial 191) | 2008–2026 (20 bloques) |
| `temporada_2026/predicciones_b3.csv.gz` | b3, la retadora (clima completo), heredados | 2008–2026 (20 bloques) |
| `temporada_2026/predicciones_d1.csv.gz` y `predicciones_d2.csv.gz` | d1 (ventanas de lluvia, temperatura y humedad + días ≥ 20 mm) y d2 (d1 + Niño 1+2) | 2008–2026 (20 bloques) |
| `matriz_clima/predicciones_{b1,b2,b4,d4,d5,e1,e2,n1}.csv.gz` | resto de la matriz de clima (medias, ventanas, anomalías, Niño monótono) | 2008–2026 (20 bloques) |
| `matriz_clima/fuera_de_temporada_*.csv.gz` y `temporada_2026/fuera_de_temporada_*.csv.gz` | validación dejando una temporada fuera (2010, 2015, 2016, 2017, 2022, 2023, 2024 y 2026) | bloques `fuera_<año>` |

«2008–2026 (20 bloques)» significa `temporada_2008` … `temporada_2024`, `calendario_2025`, `temporada_2026` y
`posterior_2026`.

En `matriz_clima/` no están `predicciones_L_5a`, `predicciones_b3`, `predicciones_d1` ni `predicciones_d2`: la
matriz reutilizó las de `temporada_2026/`, que reproducen con la semilla 17 (G41, diferencia 0,0). El detalle
de cada variante está en `research/06_model_improvement/docs/mejora_modelo.md`, «Matriz de clima: resultados».
