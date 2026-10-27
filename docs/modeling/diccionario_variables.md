# Diccionario de variables de la configuración final (HU0006-3)

> Generado por `python -m src.modeling.diccionario_variables`; no editar a mano.

Configuración: C3 + A3 = base_6 + B3 + clima de gold (humedad y precipitación, media de 5 semanas hasta o) · E3 (un regresor multi-salida, multi_output_tree, t+2/t+3/t+4 desde el origen o = t − 2) · S4_s3 · α dentro_muestra. El origen es `o = t − 2` (fila h=2); las tres salidas (t+2, t+3, t+4) usan las mismas variables.

## `hist_lag_a`

- **Etiqueta:** casos de dengue de la semana de origen o
- **Columna en gold h=2:** `casos_lag_2`
- **Fuente:** epidemiológica (casos de dengue, silver integrado)
- **Definición:** casos de dengue de la semana de origen o
- **Ventana:** semana o
- **Transformación:** ninguna (conteo)
- **Tipo:** entero ≥ 0
- **Nulos:** en gold, las 2 primeras semanas de cada distrito; esas filas no entran a la tabla de orígenes
- **Por qué está:** persistencia: el mejor predictor simple del encargo de arquitectura (base_6)
- **Evidencia:** base_6, referencia B (fase 0)
- **Test de no fuga:** tests/test_historia_calendario.py · test_cambios_despues_del_origen_no_alteran_ningun_horizonte
- **Rango observado (orígenes 2017-02-04 a 2025-12-13, 30095 filas):** 0 a 2084, mediana 0; 0 nulos

## `hist_lag_b`

- **Etiqueta:** casos de dengue de la semana o − 1
- **Columna en gold h=2:** `casos_lag_3`
- **Fuente:** epidemiológica
- **Definición:** casos de dengue de la semana o − 1
- **Ventana:** semana o − 1
- **Transformación:** ninguna (conteo)
- **Tipo:** entero ≥ 0
- **Nulos:** en gold, las 3 primeras semanas de cada distrito; no entran a la tabla de orígenes
- **Por qué está:** tendencia inmediata junto con hist_lag_a
- **Evidencia:** base_6, referencia B (fase 0)
- **Test de no fuga:** tests/test_historia_calendario.py · test_cambios_despues_del_origen_no_alteran_ningun_horizonte
- **Rango observado (orígenes 2017-02-04 a 2025-12-13, 30095 filas):** 0 a 2084, mediana 0; 0 nulos

## `hist_media_4`

- **Etiqueta:** media de casos de las semanas o − 3 a o
- **Columna en gold h=2:** `casos_media_4_h2`
- **Fuente:** epidemiológica
- **Definición:** media de casos de las semanas o − 3 a o
- **Ventana:** semanas o − 3..o
- **Transformación:** media móvil de 4 semanas
- **Tipo:** real ≥ 0
- **Nulos:** en gold, las 5 primeras semanas de cada distrito; no entran a la tabla de orígenes
- **Por qué está:** nivel reciente menos ruidoso que un rezago
- **Evidencia:** base_6, referencia B (fase 0)
- **Test de no fuga:** tests/test_historia_calendario.py · test_cuatro_semanas_solo_utiliza_observaciones_hasta_origen
- **Rango observado (orígenes 2017-02-04 a 2025-12-13, 30095 filas):** 0 a 1772, mediana 0; 0 nulos

## `hist_semanas_pos_4`

- **Etiqueta:** número de semanas con al menos 1 caso entre o − 3 y o
- **Columna en gold h=2:** `casos_semanas_positivas_4_h2`
- **Fuente:** epidemiológica
- **Definición:** número de semanas con al menos 1 caso entre o − 3 y o
- **Ventana:** semanas o − 3..o
- **Transformación:** conteo de semanas positivas (0–4)
- **Tipo:** entero 0–4
- **Nulos:** en gold, las 5 primeras semanas de cada distrito; no entran a la tabla de orígenes
- **Por qué está:** persistencia de la transmisión
- **Evidencia:** base_6, referencia B (fase 0)
- **Test de no fuga:** tests/test_historia_calendario.py · test_cuatro_semanas_solo_utiliza_observaciones_hasta_origen
- **Rango observado (orígenes 2017-02-04 a 2025-12-13, 30095 filas):** 0 a 4, mediana 0; 0 nulos

## `semana_epi_seno`

- **Etiqueta:** sen(2π · ((semana epi de t) − 1) mód 52 / 52)
- **Columna en gold h=2:** `semana_epi_seno`
- **Fuente:** calendario
- **Definición:** sen(2π · ((semana epi de t) − 1) mód 52 / 52)
- **Ventana:** semana objetivo t (conocida de antemano)
- **Transformación:** codificación cíclica
- **Tipo:** real −1..1
- **Nulos:** ninguno
- **Por qué está:** estacionalidad sin inventar un corte de temporada
- **Evidencia:** base_6, referencia B (fase 0)
- **Test de no fuga:** tests/test_historia_calendario.py · test_calendario_conocido_y_semana_53
- **Rango observado (orígenes 2017-02-04 a 2025-12-13, 30095 filas):** -1 a 1, mediana 0; 0 nulos

## `semana_epi_coseno`

- **Etiqueta:** cos(2π · ((semana epi de t) − 1) mód 52 / 52)
- **Columna en gold h=2:** `semana_epi_coseno`
- **Fuente:** calendario
- **Definición:** cos(2π · ((semana epi de t) − 1) mód 52 / 52)
- **Ventana:** semana objetivo t (conocida de antemano)
- **Transformación:** codificación cíclica
- **Tipo:** real −1..1
- **Nulos:** ninguno
- **Por qué está:** pareja del seno: ubica la semana en el círculo
- **Evidencia:** base_6, referencia B (fase 0)
- **Test de no fuga:** tests/test_historia_calendario.py · test_calendario_conocido_y_semana_53
- **Rango observado (orígenes 2017-02-04 a 2025-12-13, 30095 filas):** -1 a 1, mediana 0; 0 nulos

## `propia_semanas_desde_ultimo_caso`

- **Etiqueta:** Propio: semanas desde el último caso (tope 52)
- **Columna en gold h=2:** `no está en gold (propuesta)`
- **Fuente:** epidemiológica (en memoria, features_inicio)
- **Definición:** semanas transcurridas desde la última semana con casos del distrito, hasta o
- **Ventana:** semanas ≤ o
- **Transformación:** tope 52 semanas
- **Tipo:** entero 0–52
- **Nulos:** ninguno (sin caso previo = tope)
- **Por qué está:** cuánto lleva el distrito sin transmisión antes de un inicio
- **Evidencia:** B3: gana a B en h2 y h3 (fase 2b); C3 elegida (fase 2c); 3.ª por SHAP
- **Test de no fuga:** tests/test_features_inicio.py · test_no_fuga_por_perturbacion y test_no_fuga_por_perturbacion_en_origenes
- **Rango observado (orígenes 2017-02-04 a 2025-12-13, 30095 filas):** 0 a 52, mediana 21; 0 nulos

## `propia_pendiente_4`

- **Etiqueta:** Propio: pendiente 4 semanas (log)
- **Columna en gold h=2:** `no está en gold (propuesta)`
- **Fuente:** epidemiológica (en memoria, features_inicio)
- **Definición:** pendiente MCO de log(1 + casos) en las semanas o − 3..o
- **Ventana:** semanas o − 3..o
- **Transformación:** log1p y pendiente lineal de 4 puntos
- **Tipo:** real
- **Nulos:** nulo si faltan semanas de historia; ver el conteo de nulos en la tabla de orígenes
- **Por qué está:** dirección del cambio reciente (a priori; no observada en la fase 1)
- **Evidencia:** B3 (fase 2b), C3 (fase 2c)
- **Test de no fuga:** tests/test_features_inicio.py · test_no_fuga_por_perturbacion
- **Rango observado (orígenes 2017-02-04 a 2025-12-13, 30095 filas):** -1,171 a 1,346, mediana 0; 0 nulos

## `propia_log_casos_temporada_anterior`

- **Etiqueta:** Propio: log(1 + casos de la temporada anterior)
- **Columna en gold h=2:** `no está en gold (propuesta)`
- **Fuente:** epidemiológica (en memoria; para 2017, histórico epi previo al panel)
- **Definición:** log(1 + casos de la temporada anterior completa del distrito)
- **Ventana:** temporada anterior, cerrada antes de o
- **Transformación:** suma de la temporada y log1p
- **Tipo:** real ≥ 0
- **Nulos:** nulo solo si falta en la historia un año necesario; la fila no se excluye
- **Por qué está:** nivel previo del distrito (memoria de una temporada)
- **Evidencia:** B3 (fase 2b), C3 (fase 2c)
- **Test de no fuga:** tests/test_features_inicio.py · test_temporada_2017_usa_la_historia y test_no_fuga_por_perturbacion
- **Rango observado (orígenes 2017-02-04 a 2025-12-13, 30095 filas):** 0 a 9,47, mediana 1,386; 0 nulos

## `hum_rel_media_media5_h2`

- **Etiqueta:** media de la humedad relativa media semanal (%) de las semanas o − 4 a o
- **Columna en gold h=2:** `no está en gold (propuesta)`
- **Fuente:** meteorológica (Open-Meteo, archive API; diario agregado a semana MMWR; silver integrado)
- **Definición:** media de la humedad relativa media semanal (%) de las semanas o − 4 a o
- **Ventana:** semanas o − 4..o (5 semanas observadas hasta el origen)
- **Transformación:** media móvil de 5 semanas, sin climatología ni anomalía
- **Tipo:** real 0–100 (%)
- **Nulos:** en gold, las 6 primeras semanas de cada distrito; en la tabla de orígenes, la primera semana de 2017 (65 filas), que la configuración excluye
- **Por qué está:** clima reciente; bajó las razones MAE y RMSE del conteo
- **Evidencia:** A3 (fase 2a, lectura de conteo); complemento de clima: F+A3 mejora el conteo en h2, h3 y h4
- **Test de no fuga:** tests/test_clima_features.py · test_ventana_h4_y_h2_acaba_en_origen y test_cambio_posterior_al_origen_no_altera_feature
- **Rango observado (orígenes 2017-02-04 a 2025-12-13, 30095 filas):** 47,14 a 95,17, mediana 71; 0 nulos

## `precip_total_mm_media5_h2`

- **Etiqueta:** media de la precipitación total semanal (mm) de las semanas o − 4 a o
- **Columna en gold h=2:** `no está en gold (propuesta)`
- **Fuente:** meteorológica (Open-Meteo, archive API; diario agregado a semana MMWR; silver integrado)
- **Definición:** media de la precipitación total semanal (mm) de las semanas o − 4 a o
- **Ventana:** semanas o − 4..o (5 semanas observadas hasta el origen)
- **Transformación:** media móvil de 5 semanas, sin climatología ni anomalía
- **Tipo:** real ≥ 0 (mm por semana)
- **Nulos:** en gold, las 6 primeras semanas de cada distrito; en la tabla de orígenes, la primera semana de 2017 (65 filas), que la configuración excluye
- **Por qué está:** clima reciente; bajó las razones MAE y RMSE del conteo
- **Evidencia:** A3 (fase 2a, lectura de conteo); complemento de clima: F+A3 mejora el conteo en h2, h3 y h4
- **Test de no fuga:** tests/test_clima_features.py · test_ventana_h4_y_h2_acaba_en_origen y test_cambio_posterior_al_origen_no_altera_feature
- **Rango observado (orígenes 2017-02-04 a 2025-12-13, 30095 filas):** 0 a 480,8, mediana 3,08; 0 nulos

## Insumo de inferencia: margen de persistencia

- **Nombre:** margen_persistencia (no es columna del modelo)
- **Definición:** log(casos de la semana de origen + 0,5); base_margin de las tres salidas en S4_s3
- **Uso:** obligatorio en entrenamiento e inferencia: sin los casos del origen no se puede predecir
- **Test de no fuga:** tests/test_salida_probabilistica.py · test_s4_y_s3_sin_fuga_por_perturbacion_del_futuro

## Rango por temporada del origen

| Variable | Temporada | Mínimo | Mediana | Máximo | Nulos |
|---|---|---|---|---|---|
| `hist_lag_a` | 2017 | 0 | 0 | 2084 | 0 |
| `hist_lag_a` | 2018 | 0 | 0 | 26 | 0 |
| `hist_lag_a` | 2019 | 0 | 0 | 4 | 0 |
| `hist_lag_a` | 2020 | 0 | 0 | 6 | 0 |
| `hist_lag_a` | 2021 | 0 | 0 | 154 | 0 |
| `hist_lag_a` | 2022 | 0 | 0 | 161 | 0 |
| `hist_lag_a` | 2023 | 0 | 0 | 1527 | 0 |
| `hist_lag_a` | 2024 | 0 | 1 | 482 | 0 |
| `hist_lag_a` | 2025 | 0 | 0 | 41 | 0 |
| `hist_lag_a` | 2026 | 0 | 0 | 8 | 0 |
| `hist_lag_b` | 2017 | 0 | 0 | 2084 | 0 |
| `hist_lag_b` | 2018 | 0 | 0 | 26 | 0 |
| `hist_lag_b` | 2019 | 0 | 0 | 4 | 0 |
| `hist_lag_b` | 2020 | 0 | 0 | 6 | 0 |
| `hist_lag_b` | 2021 | 0 | 0 | 154 | 0 |
| `hist_lag_b` | 2022 | 0 | 0 | 161 | 0 |
| `hist_lag_b` | 2023 | 0 | 0 | 1527 | 0 |
| `hist_lag_b` | 2024 | 0 | 1 | 482 | 0 |
| `hist_lag_b` | 2025 | 0 | 0 | 41 | 0 |
| `hist_lag_b` | 2026 | 0 | 0 | 8 | 0 |
| `hist_media_4` | 2017 | 0 | 0,5 | 1772 | 0 |
| `hist_media_4` | 2018 | 0 | 0 | 21,75 | 0 |
| `hist_media_4` | 2019 | 0 | 0 | 2,25 | 0 |
| `hist_media_4` | 2020 | 0 | 0 | 2,5 | 0 |
| `hist_media_4` | 2021 | 0 | 0 | 125 | 0 |
| `hist_media_4` | 2022 | 0 | 0 | 125,8 | 0 |
| `hist_media_4` | 2023 | 0 | 0,25 | 1319 | 0 |
| `hist_media_4` | 2024 | 0 | 1 | 411,2 | 0 |
| `hist_media_4` | 2025 | 0 | 0 | 28,5 | 0 |
| `hist_media_4` | 2026 | 0 | 0 | 5 | 0 |
| `hist_semanas_pos_4` | 2017 | 0 | 2 | 4 | 0 |
| `hist_semanas_pos_4` | 2018 | 0 | 0 | 4 | 0 |
| `hist_semanas_pos_4` | 2019 | 0 | 0 | 4 | 0 |
| `hist_semanas_pos_4` | 2020 | 0 | 0 | 4 | 0 |
| `hist_semanas_pos_4` | 2021 | 0 | 0 | 4 | 0 |
| `hist_semanas_pos_4` | 2022 | 0 | 0 | 4 | 0 |
| `hist_semanas_pos_4` | 2023 | 0 | 1 | 4 | 0 |
| `hist_semanas_pos_4` | 2024 | 0 | 2 | 4 | 0 |
| `hist_semanas_pos_4` | 2025 | 0 | 0 | 4 | 0 |
| `hist_semanas_pos_4` | 2026 | 0 | 0 | 4 | 0 |
| `hum_rel_media_media5_h2` | 2017 | 52,97 | 79,84 | 94,2 | 0 |
| `hum_rel_media_media5_h2` | 2018 | 54 | 71,86 | 93,6 | 0 |
| `hum_rel_media_media5_h2` | 2019 | 53,37 | 71,93 | 94,89 | 0 |
| `hum_rel_media_media5_h2` | 2020 | 53,31 | 69,09 | 93,49 | 0 |
| `hum_rel_media_media5_h2` | 2021 | 53,14 | 69,09 | 93,23 | 0 |
| `hum_rel_media_media5_h2` | 2022 | 54 | 69,94 | 94,17 | 0 |
| `hum_rel_media_media5_h2` | 2023 | 50,23 | 72,23 | 93,57 | 0 |
| `hum_rel_media_media5_h2` | 2024 | 50,4 | 70,6 | 93,77 | 0 |
| `hum_rel_media_media5_h2` | 2025 | 47,14 | 70,26 | 95,17 | 0 |
| `hum_rel_media_media5_h2` | 2026 | 53,66 | 70,67 | 90,8 | 0 |
| `precip_total_mm_media5_h2` | 2017 | 0 | 31,15 | 480,8 | 0 |
| `precip_total_mm_media5_h2` | 2018 | 0 | 2,98 | 136,2 | 0 |
| `precip_total_mm_media5_h2` | 2019 | 0 | 3,62 | 291,1 | 0 |
| `precip_total_mm_media5_h2` | 2020 | 0 | 2,54 | 140,3 | 0 |
| `precip_total_mm_media5_h2` | 2021 | 0 | 2,34 | 151,8 | 0 |
| `precip_total_mm_media5_h2` | 2022 | 0 | 2,5 | 160,7 | 0 |
| `precip_total_mm_media5_h2` | 2023 | 0 | 2,9 | 327 | 0 |
| `precip_total_mm_media5_h2` | 2024 | 0 | 3,78 | 198 | 0 |
| `precip_total_mm_media5_h2` | 2025 | 0 | 3,3 | 207,8 | 0 |
| `precip_total_mm_media5_h2` | 2026 | 0 | 1,75 | 64,62 | 0 |
| `propia_log_casos_temporada_anterior` | 2017 | 0 | 3,135 | 7,084 | 0 |
| `propia_log_casos_temporada_anterior` | 2018 | 0 | 3,332 | 9,47 | 0 |
| `propia_log_casos_temporada_anterior` | 2019 | 0 | 0,6931 | 9,47 | 0 |
| `propia_log_casos_temporada_anterior` | 2020 | 0 | 0 | 5,283 | 0 |
| `propia_log_casos_temporada_anterior` | 2021 | 0 | 0 | 3,738 | 0 |
| `propia_log_casos_temporada_anterior` | 2022 | 0 | 0,6931 | 7,319 | 0 |
| `propia_log_casos_temporada_anterior` | 2023 | 0 | 2,639 | 7,446 | 0 |
| `propia_log_casos_temporada_anterior` | 2024 | 0 | 5,159 | 9,38 | 0 |
| `propia_log_casos_temporada_anterior` | 2025 | 0 | 4,673 | 9,38 | 0 |
| `propia_log_casos_temporada_anterior` | 2026 | 0 | 1,609 | 8,526 | 0 |
| `propia_pendiente_4` | 2017 | -1,074 | 0 | 0,9531 | 0 |
| `propia_pendiente_4` | 2018 | -0,7749 | 0 | 0,6628 | 0 |
| `propia_pendiente_4` | 2019 | -0,5545 | 0 | 0,4852 | 0 |
| `propia_pendiente_4` | 2020 | -0,5521 | 0 | 0,6531 | 0 |
| `propia_pendiente_4` | 2021 | -0,9757 | 0 | 1,346 | 0 |
| `propia_pendiente_4` | 2022 | -1,022 | 0 | 1,212 | 0 |
| `propia_pendiente_4` | 2023 | -1,165 | 0 | 1,308 | 0 |
| `propia_pendiente_4` | 2024 | -1,171 | 0 | 1,037 | 0 |
| `propia_pendiente_4` | 2025 | -0,861 | 0 | 0,9016 | 0 |
| `propia_pendiente_4` | 2026 | -0,7026 | 0 | 0,4852 | 0 |
| `propia_semanas_desde_ultimo_caso` | 2017 | 0 | 1 | 52 | 0 |
| `propia_semanas_desde_ultimo_caso` | 2018 | 0 | 17 | 52 | 0 |
| `propia_semanas_desde_ultimo_caso` | 2019 | 0 | 52 | 52 | 0 |
| `propia_semanas_desde_ultimo_caso` | 2020 | 0 | 52 | 52 | 0 |
| `propia_semanas_desde_ultimo_caso` | 2021 | 0 | 52 | 52 | 0 |
| `propia_semanas_desde_ultimo_caso` | 2022 | 0 | 8 | 52 | 0 |
| `propia_semanas_desde_ultimo_caso` | 2023 | 0 | 3 | 52 | 0 |
| `propia_semanas_desde_ultimo_caso` | 2024 | 0 | 0 | 52 | 0 |
| `propia_semanas_desde_ultimo_caso` | 2025 | 0 | 10 | 52 | 0 |
| `propia_semanas_desde_ultimo_caso` | 2026 | 0 | 26 | 52 | 0 |
| `semana_epi_coseno` | 2017 | -1 | -0,6631 | 0,7485 | 0 |
| `semana_epi_coseno` | 2018 | -1 | 0 | 1 | 0 |
| `semana_epi_coseno` | 2019 | -1 | 0 | 1 | 0 |
| `semana_epi_coseno` | 2020 | -1 | 0 | 1 | 0 |
| `semana_epi_coseno` | 2021 | -1 | 0 | 1 | 0 |
| `semana_epi_coseno` | 2022 | -1 | 0 | 1 | 0 |
| `semana_epi_coseno` | 2023 | -1 | 0 | 1 | 0 |
| `semana_epi_coseno` | 2024 | -1 | 0 | 1 | 0 |
| `semana_epi_coseno` | 2025 | -1 | 0 | 1 | 0 |
| `semana_epi_coseno` | 2026 | -0,5681 | 0,4097 | 0,9927 | 0 |
| `semana_epi_seno` | 2017 | -0,7485 | 0,6631 | 1 | 0 |
| `semana_epi_seno` | 2018 | -1 | 0 | 1 | 0 |
| `semana_epi_seno` | 2019 | -1 | 0 | 1 | 0 |
| `semana_epi_seno` | 2020 | -1 | 0 | 1 | 0 |
| `semana_epi_seno` | 2021 | -1 | 0 | 1 | 0 |
| `semana_epi_seno` | 2022 | -1 | 0 | 1 | 0 |
| `semana_epi_seno` | 2023 | -1 | 0 | 1 | 0 |
| `semana_epi_seno` | 2024 | -1 | 0 | 1 | 0 |
| `semana_epi_seno` | 2025 | -1 | 0 | 1 | 0 |
| `semana_epi_seno` | 2026 | -1 | -0,8542 | -0,1205 | 0 |
