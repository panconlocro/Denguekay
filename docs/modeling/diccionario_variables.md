# Diccionario de variables

> Generado por `python -m denguekay.model.variable_dictionary`; no editar a mano.

La configuración vigente es la **V4**. La v2 queda como histórico al final; su diccionario completo, con rangos por temporada, está en [`diccionario_variables_v2.md`](diccionario_variables_v2.md).

## V4 vigente (b3_obs, casos confirmados)

Configuración: matriz `b3_obs` (16 columnas) · formulación S4_s3 · horizontes 2, 3, 4 semanas · etiquetas hasta el 2026-10-17. Es el modelo que sirve el predictor `v4_b3_live` (ficha en `models/registry/v4/`).

**Convención de tiempo.** El origen `o` es la semana de corte: la semana epidemiológica (domingo a sábado) cuyo cierre es la fecha de corte de los datos. La semana objetivo es `t = o + h` con h = 2, 3 o 4. El modelo calcula **un solo vector de 16 columnas en `o`** y lo usa para los tres horizontes, así que ninguna variable mira después de `o`: «rezago respecto de `t − h`» significa que la semana `o` es la última que se observa para el objetivo `t = o + h`. Las variables de clima y Niño 1+2 respetan además la fecha de publicación de su fuente.

Las columnas salen de `research/08_v3_confirmed_cases/manifiesto_b3_v4.json`, igual que en el paquete congelado y en `features/gold_v4.py`; una prueba falla si una columna no tiene entrada completa (`tests/model/test_variable_dictionary_v4.py`).

| # | Variable | Grupo | Unidad | Ventana temporal |
|---|---|---|---|---|
| 1 | `hist_lag_a` | historia y calendario | casos por semana | semana o |
| 2 | `hist_lag_b` | historia y calendario | casos por semana | semana o − 1 |
| 3 | `hist_media_4` | historia y calendario | casos por semana | 4 semanas: o − 3, o − 2, o − 1 y o |
| 4 | `hist_semanas_pos_4` | historia y calendario | semanas (0 a 4) | 4 semanas: o − 3, o − 2, o − 1 y o |
| 5 | `semana_epi_seno` | historia y calendario | adimensional (−1 a 1) | semana o + 2 (la semana objetivo de la fila del horizonte 2; el vector del origen es el mismo para h = 2, 3 y 4) |
| 6 | `semana_epi_coseno` | historia y calendario | adimensional (−1 a 1) | semana o + 2 (la semana objetivo de la fila del horizonte 2; el vector del origen es el mismo para h = 2, 3 y 4) |
| 7 | `propia_semanas_desde_ultimo_caso` | historia propia | semanas (0 a 52) | todas las semanas hasta o, incluida o |
| 8 | `propia_pendiente_4` | historia propia | log(1 + casos) por semana | 4 semanas: o − 3, o − 2, o − 1 y o |
| 9 | `propia_log_casos_temporada_anterior` | historia propia | log(1 + casos de la temporada) | temporada anterior a la del origen, cerrada antes de o (la temporada empieza en la semana 35) |
| 10 | `lat` | geografía | grados decimales | estática (no varía en el tiempo) |
| 11 | `lon` | geografía | grados decimales | estática (no varía en el tiempo) |
| 12 | `elevacion_dem90` | geografía | metros sobre el nivel del mar | estática (no varía en el tiempo) |
| 13 | `hum_rel_media_media5_h2_obs` | clima, Niño 1+2 y disponibilidad | % (0 a 100) | 5 semanas epidemiológicas: o − 6, o − 5, o − 4, o − 3 y o − 2 |
| 14 | `precip_total_mm_media5_h2_obs` | clima, Niño 1+2 y disponibilidad | mm por semana | 5 semanas epidemiológicas: o − 6, o − 5, o − 4, o − 3 y o − 2 |
| 15 | `temp_media_media5_h2_obs` | clima, Niño 1+2 y disponibilidad | °C | 5 semanas epidemiológicas: o − 6, o − 5, o − 4, o − 3 y o − 2 |
| 16 | `nino12_anom_media3_obs` | clima, Niño 1+2 y disponibilidad | °C (anomalía) | los 3 últimos meses consecutivos publicados al cierre del origen |

### `hist_lag_a`

- **Descripción:** Casos confirmados del distrito en la semana de origen.
- **Fuente:** epidemiológica: casos confirmados de dengue de Piura (CSV epidemiológico confirmado hasta 2024 y Sala Situacional del MINSA desde 2025), con la historia desde 2000 para completar las ventanas
- **Unidad:** casos por semana
- **Ventana temporal:** semana o
- **Regla de cálculo:** valor de casos_Dengue de la semana o, sin transformación
- **Rezago respecto del origen:** 0 semanas respecto del origen; para el objetivo t = o + h equivale a t − h

### `hist_lag_b`

- **Descripción:** Casos confirmados del distrito en la semana anterior al origen.
- **Fuente:** epidemiológica: casos confirmados de dengue de Piura (CSV epidemiológico confirmado hasta 2024 y Sala Situacional del MINSA desde 2025), con la historia desde 2000 para completar las ventanas
- **Unidad:** casos por semana
- **Ventana temporal:** semana o − 1
- **Regla de cálculo:** valor de casos_Dengue de la semana o − 1, sin transformación
- **Rezago respecto del origen:** 1 semana respecto del origen; para el objetivo t = o + h equivale a t − h − 1

### `hist_media_4`

- **Descripción:** Nivel reciente de casos: media de las últimas 4 semanas hasta el origen.
- **Fuente:** epidemiológica: casos confirmados de dengue de Piura (CSV epidemiológico confirmado hasta 2024 y Sala Situacional del MINSA desde 2025), con la historia desde 2000 para completar las ventanas
- **Unidad:** casos por semana
- **Ventana temporal:** 4 semanas: o − 3, o − 2, o − 1 y o
- **Regla de cálculo:** media aritmética de casos_Dengue en la ventana; se exigen las 4 semanas (sin completar con ceros)
- **Rezago respecto del origen:** la ventana termina en el origen (rezago 0); equivale a las 4 semanas que terminan en t − h

### `hist_semanas_pos_4`

- **Descripción:** Persistencia de la transmisión: semanas con casos entre las últimas 4 hasta el origen.
- **Fuente:** epidemiológica: casos confirmados de dengue de Piura (CSV epidemiológico confirmado hasta 2024 y Sala Situacional del MINSA desde 2025), con la historia desde 2000 para completar las ventanas
- **Unidad:** semanas (0 a 4)
- **Ventana temporal:** 4 semanas: o − 3, o − 2, o − 1 y o
- **Regla de cálculo:** número de semanas de la ventana con casos_Dengue mayor que 0; se exigen las 4 semanas
- **Rezago respecto del origen:** la ventana termina en el origen (rezago 0); equivale a las 4 semanas que terminan en t − h

### `semana_epi_seno`

- **Descripción:** Posición estacional de la semana objetivo del horizonte 2, parte seno.
- **Fuente:** calendario epidemiológico MMWR (no usa observaciones)
- **Unidad:** adimensional (−1 a 1)
- **Ventana temporal:** semana o + 2 (la semana objetivo de la fila del horizonte 2; el vector del origen es el mismo para h = 2, 3 y 4)
- **Regla de cálculo:** sen(2π · ((semana epidemiológica de o + 2) − 1) mód 52 / 52); la semana 53 ocupa la misma posición que la semana 1
- **Rezago respecto del origen:** ninguno: el calendario de la semana objetivo se conoce de antemano

### `semana_epi_coseno`

- **Descripción:** Posición estacional de la semana objetivo del horizonte 2, parte coseno.
- **Fuente:** calendario epidemiológico MMWR (no usa observaciones)
- **Unidad:** adimensional (−1 a 1)
- **Ventana temporal:** semana o + 2 (la semana objetivo de la fila del horizonte 2; el vector del origen es el mismo para h = 2, 3 y 4)
- **Regla de cálculo:** cos(2π · ((semana epidemiológica de o + 2) − 1) mód 52 / 52); la semana 53 ocupa la misma posición que la semana 1
- **Rezago respecto del origen:** ninguno: el calendario de la semana objetivo se conoce de antemano

### `propia_semanas_desde_ultimo_caso`

- **Descripción:** Cuánto lleva el distrito sin transmisión: semanas desde la última semana con casos.
- **Fuente:** epidemiológica: casos confirmados de dengue de Piura (CSV epidemiológico confirmado hasta 2024 y Sala Situacional del MINSA desde 2025), con la historia desde 2000 para completar las ventanas; calculada en memoria
- **Unidad:** semanas (0 a 52)
- **Ventana temporal:** todas las semanas hasta o, incluida o
- **Regla de cálculo:** o menos la posición de la última semana con casos_Dengue mayor que 0 (0 si o tiene casos); tope de 52 semanas, que también se usa si el distrito no tiene caso previo
- **Rezago respecto del origen:** usa solo semanas hasta el origen (rezago 0); no ve nada posterior a o

### `propia_pendiente_4`

- **Descripción:** Dirección del cambio reciente de los casos: pendiente de log(1 + casos) en 4 semanas.
- **Fuente:** epidemiológica: casos confirmados de dengue de Piura (CSV epidemiológico confirmado hasta 2024 y Sala Situacional del MINSA desde 2025), con la historia desde 2000 para completar las ventanas; calculada en memoria
- **Unidad:** log(1 + casos) por semana
- **Ventana temporal:** 4 semanas: o − 3, o − 2, o − 1 y o
- **Regla de cálculo:** pendiente de mínimos cuadrados de log(1 + casos_Dengue) contra el tiempo (4 puntos equiespaciados); nula si falta alguna de las 4 semanas
- **Rezago respecto del origen:** la ventana termina en el origen (rezago 0)

### `propia_log_casos_temporada_anterior`

- **Descripción:** Nivel previo del distrito: casos de la temporada anterior completa.
- **Fuente:** epidemiológica: casos confirmados de dengue de Piura (CSV epidemiológico confirmado hasta 2024 y Sala Situacional del MINSA desde 2025), con la historia desde 2000 para completar las ventanas; calculada en memoria
- **Unidad:** log(1 + casos de la temporada)
- **Ventana temporal:** temporada anterior a la del origen, cerrada antes de o (la temporada empieza en la semana 35)
- **Regla de cálculo:** log(1 + suma de casos_Dengue de la temporada anterior del distrito); nula solo si falta de la historia un año necesario
- **Rezago respecto del origen:** temporada completa y cerrada antes del origen; no usa semanas posteriores a o

### `lat`

- **Descripción:** Latitud del punto del distrito.
- **Fuente:** geográfica: coordenadas del punto del distrito de las consultas climáticas (data/reference/distritos_piura_coords.csv), en el archivo geografia_distritos.csv del paquete
- **Unidad:** grados decimales
- **Ventana temporal:** estática (no varía en el tiempo)
- **Regla de cálculo:** se toma tal cual del archivo de geografía congelado (65 distritos); su SHA-256 está en la ficha de la V4
- **Rezago respecto del origen:** no aplica: constante del distrito

### `lon`

- **Descripción:** Longitud del punto del distrito.
- **Fuente:** geográfica: coordenadas del punto del distrito de las consultas climáticas (data/reference/distritos_piura_coords.csv), en el archivo geografia_distritos.csv del paquete
- **Unidad:** grados decimales
- **Ventana temporal:** estática (no varía en el tiempo)
- **Regla de cálculo:** se toma tal cual del archivo de geografía congelado (65 distritos); su SHA-256 está en la ficha de la V4
- **Rezago respecto del origen:** no aplica: constante del distrito

### `elevacion_dem90`

- **Descripción:** Elevación del punto del distrito.
- **Fuente:** geográfica: modelo digital de elevación GLO-90 (90 m) consultado con la API de elevación de Open-Meteo en el punto del distrito
- **Unidad:** metros sobre el nivel del mar
- **Ventana temporal:** estática (no varía en el tiempo)
- **Regla de cálculo:** se toma tal cual del archivo de geografía congelado (65 distritos); su SHA-256 está en la ficha de la V4
- **Rezago respecto del origen:** no aplica: constante del distrito

### `hum_rel_media_media5_h2_obs`

- **Descripción:** Humedad relativa reciente: media de 5 semanas que terminan 2 semanas antes del origen.
- **Fuente:** meteorológica: ERA5-Land (0,1°) vía la API de archivo de Open-Meteo, valor diario en el punto del distrito, agregado a semana epidemiológica (domingo a sábado); variable relative_humidity_2m_mean
- **Unidad:** % (0 a 100)
- **Ventana temporal:** 5 semanas epidemiológicas: o − 6, o − 5, o − 4, o − 3 y o − 2
- **Regla de cálculo:** media aritmética de hum_rel_media semanal de las 5 semanas; solo cuenta una semana si su fecha de disponibilidad es anterior o igual al cierre del origen (ERA5-Land: fecha_era5_land_disponible de la BD, o el domingo de la semana más 13 días en el silver sin esa fecha); si falta alguna de las 5, el valor es nulo y el distrito no se pronostica, con el motivo registrado
- **Rezago respecto del origen:** la ventana termina 2 semanas antes del origen (o − 2): la última semana climática que ya está publicada al cierre del origen; no es el rezago de un horizonte

### `precip_total_mm_media5_h2_obs`

- **Descripción:** Lluvia reciente: media de 5 semanas que terminan 2 semanas antes del origen.
- **Fuente:** precipitación: CHIRPS v3 (final y preliminar) agregada por distrito, diaria, a semana epidemiológica (domingo a sábado)
- **Unidad:** mm por semana
- **Ventana temporal:** 5 semanas epidemiológicas: o − 6, o − 5, o − 4, o − 3 y o − 2
- **Regla de cálculo:** media aritmética de precip_total_mm semanal de las 5 semanas; solo cuenta una semana si su fecha de disponibilidad es anterior o igual al cierre del origen (CHIRPS: fecha_chirps_disponible, el cierre del pentad que contiene el sábado más 5 días); si falta alguna de las 5, el valor es nulo y el distrito no se pronostica, con el motivo registrado
- **Rezago respecto del origen:** la ventana termina 2 semanas antes del origen (o − 2): la última semana climática que ya está publicada al cierre del origen; no es el rezago de un horizonte

### `temp_media_media5_h2_obs`

- **Descripción:** Temperatura reciente: media de 5 semanas que terminan 2 semanas antes del origen.
- **Fuente:** meteorológica: ERA5-Land (0,1°) vía la API de archivo de Open-Meteo, valor diario en el punto del distrito, agregado a semana epidemiológica (domingo a sábado); variable temperature_2m_mean
- **Unidad:** °C
- **Ventana temporal:** 5 semanas epidemiológicas: o − 6, o − 5, o − 4, o − 3 y o − 2
- **Regla de cálculo:** media aritmética de temp_media semanal de las 5 semanas; solo cuenta una semana si su fecha de disponibilidad es anterior o igual al cierre del origen (ERA5-Land: fecha_era5_land_disponible de la BD, o el domingo de la semana más 13 días en el silver sin esa fecha); si falta alguna de las 5, el valor es nulo y el distrito no se pronostica, con el motivo registrado
- **Rezago respecto del origen:** la ventana termina 2 semanas antes del origen (o − 2): la última semana climática que ya está publicada al cierre del origen; no es el rezago de un horizonte

### `nino12_anom_media3_obs`

- **Descripción:** Anomalía reciente del océano frente a Piura: media de los 3 últimos meses publicados del Niño 1+2.
- **Fuente:** oceánica: anomalía mensual Niño 1+2 del índice OISST v2.1 de NOAA CPC (sstoi.indices); un solo valor para todos los distritos
- **Unidad:** °C (anomalía)
- **Ventana temporal:** los 3 últimos meses consecutivos publicados al cierre del origen
- **Regla de cálculo:** media aritmética de la anomalía mensual de esos 3 meses; un mes está publicado desde el día 10 del mes siguiente; si no hay 3 meses consecutivos, el valor es nulo
- **Rezago respecto del origen:** entre 1 y 3 meses de retraso por la publicación del índice; usa solo meses ya publicados al cierre del origen

### Pruebas de no fuga

- historia y calendario: `tests/features/test_history_calendar.py`
- historia propia: `tests/features/test_onset_features.py`
- clima, Niño 1+2 y disponibilidad: `tests/features/test_gold_v4.py · test_uses_only_the_five_eligible_weeks_and_three_published_months`

## Histórico: v2 (HU0006-3, congelada antes de la V3)

Tabla resumida de las 11 columnas de la configuración v2 (`CONFIG_2026`), que ya no se sirve.

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
| `hum_rel_media_media5_h2` | media de la humedad relativa media semanal (%) de las semanas o − 4 a o | % | semanas o − 4..o (5 semanas observadas hasta el origen) | media móvil de 5 semanas, sin climatología ni anomalía | en gold, las 6 primeras semanas de cada distrito; en la tabla de orígenes, la primera semana de 2017 (65 filas), que la configuración excluye |
| `precip_total_mm_media5_h2` | media de la precipitación total semanal (mm) de las semanas o − 4 a o | mm por semana | semanas o − 4..o (5 semanas observadas hasta el origen) | media móvil de 5 semanas, sin climatología ni anomalía | en gold, las 6 primeras semanas de cada distrito; en la tabla de orígenes, la primera semana de 2017 (65 filas), que la configuración excluye |
