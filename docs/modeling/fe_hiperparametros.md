# Feature engineering e hiperparámetros sobre E3·S4_s2

Encargo posterior a `arquitectura_horizontes.md`. La arquitectura (E3·S4_s2: XGBoost `count:poisson`
`multi_output_tree` para t+2, t+3 y t+4; P(casos ≥ k) con binomial negativa NB2 y Platt cronológico) y el
protocolo (`src/modeling/protocolo_arquitectura.py`) quedan fijos. Cifras en
`docs/modeling/metricas/fe_hiperparametros.json` (una sección por fase); figuras en
`docs/modeling/figuras/fe_hiperparametros/`; predicciones fila a fila en `models/experimentos/fe_hiperparametros/`;
notebook `notebooks/32_modelado_fe_inicios.ipynb`.

## Fase 0 · Línea base (referencia B)

- E3·S4_s2 con `base_6`, hiperparámetros fijos y semillas 17/29/41/53/67, **reentrenado sin caché**, reproduce
  `arquitectura_horizontes.json → fase5_decision.metricas_mediana_semillas`: 615/615 métricas iguales al
  redondeo de 3 decimales (diferencia absoluta máxima 5·10⁻¹¹). Registrado en MLflow
  (`denguekay/fe_hiperparametros_fase0_referencia_B`).
- Referencia B (mediana de semillas), temporadas de selección: F1 a 0,50 de 0,682 / 0,845 (h=2, 2022 / 2023),
  0,590 / 0,812 (h=3) y 0,478 / 0,779 (h=4). Rangos entre semillas de F1: 0,004–0,021.
- Antelación en inicios limpios 2022–2023 (95 episodios, semilla 17), modelo − persistencia: −0,032
  (IC95 −0,084 a 0,021) en h=2, −0,042 (−0,105 a 0,011) en h=3 y −0,105 (−0,189 a −0,021) en h=4.
- Recall en las 2 primeras semanas de brotes nuevos: **0,00–0,09** en 2022–2023 (frente a 0,37–0,84 en
  semanas de brotes en curso). El 0,15 citado antes correspondía a 2024.
- HU0007-4: falla el recall en 2022 (0,33–0,60) y 2023 (0,66–0,78).
- Gold h=2 tiene 34 candidatas predictoras, de las cuales 6 son `base_6`: quedan 28 adicionales. Solo el clima
  `media5` tiene nulos de arranque tras las exclusiones (65 filas, una semana por distrito).
- Un ajuste completo (5 bloques × 1 semilla) más la evaluación tarda 6,8–7,2 s en GPU.

Los veredictos de las ablaciones 25–29 salieron con S1 y otro protocolo (umbral elegido en validación, F1 medio,
una semilla). Están en el JSON como **antecedente, no comparable**.

## Fase 1 · Diagnóstico de inicios

### Partición (opción A, decidida por Rosa)

Las variables se diseñan solo con las temporadas 2017–2021. 2022–2023 (selección) y 2024 (contraste) no se usan
para diseñar. Inicios limpios verificables (8 semanas previas observadas y sin brote):

| Temporada | Limpios | Verificables |
|---|---|---|
| 2017 (solo enero–agosto) | 53 | 40 |
| 2018 | 12 | 12 |
| 2019 | 1 | 1 |
| 2020 | 2 | 2 |
| 2021 | 16 | 16 |
| **2017–2021** | 84 | **71** |
| 2022–2023 (no usados) | 95 | 95 |

El 56 % de los inicios de diseño es de 2017, por eso todo se reporta por separado para 2017 (40) y para
2018–2021 (31).

### Método

- Estado de cada distrito en la semana `w`, calculado solo con semanas ≤ `w`; el perfil de un inicio en `s` mira
  `w = s − k`, con `k = 1..12` (`src/modeling/diagnostico_inicios.py`).
- Dos controles, ambos con la misma semana epidemiológica, del periodo de diseño, sin brote en la semana ni en las
  8 previas: `semana` (cualquier distrito; mediana de 283 controles por inicio) y `distrito` (el mismo distrito en
  otras temporadas; 2–4 por inicio). Ningún inicio necesitó el respaldo por tercil.
- Diferencia media inicio − control con IC95 bootstrap por episodio (estratificado por periodo), sin p-valores.
- Climatología (anomalías), ranking de los 5 distritos núcleo y terciles: ajustados con 2017–2021 **solo para
  este diagnóstico**. En la fase 2 se recalculan con el entrenamiento de cada bloque.
- Regla de consistencia, fijada en el código antes de ver resultados, sobre las ventanas a priori (`origen_2_4`
  y `previa_5_8` para lo epidemiológico; `clima_4_8` y `clima_8_12` para el clima):
  - **observada:** el mismo signo en 2017 y en 2018–2021 con ambos controles, y el IC95 de 2017–2021 excluye el 0
    con ambos;
  - **hipótesis (solo 2017):** el patrón se sostiene en 2017 con ambos controles, pero no en 2018–2021;
  - **no observada** o **no evaluable** (falta una celda).
- Comparaciones descriptivas: 33 variables × 2 ventanas = 66 veredictos, sin corrección por multiplicidad.

### Observaciones (2017–2021)

Las cifras son diferencias inicio − control en la ventana `origen_2_4`, salvo que se indique otra.

- **Contexto espacial:** son «observadas» las 12 combinaciones de nivel y fracciones (con casos y en brote) de
  provincia y región (6 variables × 2 ventanas), y para los vecinos el nivel, la fracción con casos, la fracción
  en brote y el nº con casos nuevos en ambas ventanas. Ejemplos:
  - fracción de vecinos knn5 en brote: 0,126 en los inicios frente a 0,011–0,014 en los controles;
  - fracción regional en brote: 0,151 frente a 0,013–0,029.

  El efecto es mucho mayor en 2017 que en 2018–2021. Por ejemplo, en la fracción regional en brote la
  diferencia es de 0,20 frente a 0,02.
- **Cambios:** el cambio en 1 semana es «observado» en `origen_2_4` para vecinos, provincia y región. El cambio
  en 4 semanas solo es «observado» a nivel regional. Para provincia en 4 semanas es «hipótesis solo 2017». Para
  vecinos en 4 semanas, «no observado».
- **Distritos núcleo** (Piura, Castilla, Veintiséis de Octubre, Sullana y Chulucanas; Pariñas reemplaza al propio
  distrito cuando corresponde): la fracción del núcleo en brote vale 0,527 en los inicios frente a 0,044–0,102 en
  los controles. Se mantiene en 2018–2021 (diferencia 0,11–0,13), aunque mucho menor que en 2017 (0,67–0,76).
  Es co-ocurrencia; la importación desde el núcleo queda como **hipótesis**, sin lectura causal.
- **Clima:**
  - la anomalía de temperatura media es menor antes de los inicios (−0,26 a −0,29 °C en 4–8 semanas;
    −0,16 a −0,19 °C en 8–12);
  - la anomalía de humedad relativa es mayor (+5,3 a +5,9 puntos en 4–8; +3,4 a +3,8 en 8–12).

  Ambas son «observadas». La precipitación (+26 a +29 mm semanales de anomalía en 4–8 semanas) y la temperatura
  mínima solo se sostienen en 2017: son **hipótesis (solo 2017)**. La temperatura media sin anomalía no se
  observa.
- **Historia propia:**
  - las semanas desde el último caso son menos antes de un inicio (12 frente a 32–36);
  - tener casos y el nivel de casos son «observados» (los dos últimos ya están representados en `base_6`);
  - la pendiente y la aceleración de 4 semanas no se observan;
  - los casos de la temporada anterior no son evaluables en 2017.
- **Inicios de 2021 con la referencia B** (único bloque del periodo de diseño): para los 16 inicios, la
  probabilidad sin calibrar del modelo para la semana de inicio fue a lo sumo 0,41 y ninguna llegó a 0,50 en
  h=2, 3 o 4. La persistencia también era 0 en la mayoría.

### Hipótesis y límites

- El contexto espacial «observado» compara sobre todo con semanas de otras temporadas. Una parte de la
  diferencia puede reflejar que los inicios ocurren en temporadas con mucha actividad regional, más que
  discriminar **qué** distrito inicia dentro de una temporada activa. Ninguno de los dos controles separa ambas
  cosas; la fase 2 dirá si aporta sobre `base_6`.
- 2017 domina los inicios y los tamaños de efecto. En 2018–2021 hay 31 inicios, 16 de ellos en 2021.
- Con 71 inicios y 66 veredictos descriptivos, algunos «observados» pueden ser casuales. El diagnóstico solo
  justifica qué probar; no decide nada.

### Verificación: ¿el conteo pierde en el pico? (2022–2023, solo verificación)

Sí. En la fase «pico» de la curva regional, la razón MAE modelo / persistencia es mayor que 1 en las 6 celdas:
1,21 / 1,58 / 2,04 en 2022 y 1,22 / 1,12 / 1,09 en 2023 (h=2/3/4; rango entre semillas ≤ 0,09). En 2023 el
modelo subestima el pico (suma predicha / real 0,36–0,48); en 2022 lo sobreestima (1,24–1,93). En la bajada,
el modelo gana a la persistencia (0,45–0,74).

## Preregistro

Fuente de verdad: `src/modeling/preregistro_fe.py` (copiado en `fe_hiperparametros.json → fase1_preregistro`).
**No se amplía después de ver resultados sin la aprobación de Rosa.**

Reglas comunes:
- `o` = origen de la fila h=2. Toda variable usa solo semanas ≤ `o`.
- Las ventanas son a priori.
- Toda transformación aprendida se ajusta con el entrenamiento de cada bloque.
- Con nulos de arranque distintos, la variante y la referencia se comparan sobre la intersección de filas.
- Cada variable nueva necesita un test de no fuga por perturbación (h=2, 3 y 4) antes de entrar a un experimento.

### Bloque A · gold h=2, re-ensayo tal cual sobre E3·S4_s2

| Id | Familia | Columnas | Contra |
|---|---|---|---|
| A1 | Vecinos | `vecinos_media_casos_knn5_h2`, `vecinos_frac_con_casos_knn5_h2` | B |
| A2 | Jerarquía | `provincia_otros_casos_h2`, `provincia_otros_frac_con_casos_h2`, `region_otros_casos_h2`, `region_otros_frac_con_casos_h2` | B |
| A3 | Clima de gold | `hum_rel_media_media5_h2`, `precip_total_mm_media5_h2` (65 nulos: intersección) | B |
| A4 | Población 2017 | `log_poblacion_censo_2017` | B |
| A5 | Población anual | `log_poblacion_anual` (reconstruida†) | B |
| A6 | Fracciones 2017 | `fraccion_rural_2017`, `fraccion_menores_15_2017`, `fraccion_desague_red_2017` | B |
| A7 | Fracciones anuales | `socio_anual_cp1`: CP1 de las 15 `fraccion_*_anual`, ajustado por bloque (reconstruidas†) | B |

† Las fracciones 2018–2024 son reconstrucción retrospectiva con 2025 y la fecha de publicación de la población
anual no está verificada: su resultado no puede presentarse como un pronóstico que se habría podido emitir.

### Bloque B · variables nuevas (en memoria)

| Id | Familia | Columnas y regla | Ventana | Evidencia de la fase 1 | Contra |
|---|---|---|---|---|---|
| B1 | Dinámica espacial | fracción en brote de vecinos/provincia/región; nº de vecinos knn5 con casos nuevos; cambio de log(1 + casos) en 1 y 4 semanas de vecinos/provincia/región (10 columnas) | `o`; `o−1→o` y `o−4→o` | fracciones en brote, casos nuevos y cambio de 1 semana: observadas; cambios de 4 semanas: mixtos (se incluyen por simetría a priori) | B; base_6 + A1 + A2 |
| B2 | Distritos núcleo | log(1 + casos), fracción en brote y cambio en 4 semanas de los 5 distritos con más casos del entrenamiento del bloque, excluido el propio | `o`; `o−4→o` | observada (importación: hipótesis) | B |
| B3 | Historia propia ampliada | semanas desde el último caso (tope 52), pendiente MCO de 4 semanas, log(1 + casos) de la temporada anterior | hasta `o` | semanas desde el último caso: observada; pendiente: no observada (hipótesis a priori); temporada anterior: no evaluable | B |
| B4 | Línea base estacional | log(1 + media) y log(1 + umbral) de la semana objetivo `t+h` en los 5 años previos, una columna por h (6) | años previos | no aplica (se conoce al emitir) | B |
| B5 | Clima de incubación | media de la anomalía (climatología del bloque) de temperatura media y mínima, humedad y precipitación en `o−4..o` y `o−8..o−4` (8 columnas) | k = h..h+4 y h+4..h+8 (en h=4: 4–8 y 8–12) | anomalías de temperatura media y humedad: observadas; temperatura mínima y precipitación: hipótesis solo 2017 | B; base_6 + A3 |

Descartes sin probar:
- **Aceleración de la historia propia:** no observada y es una segunda diferencia de conteos chicos.
- **Valores climáticos sin anomalía:** la temperatura media no se observa, y la humedad y la precipitación
  observadas ya están en A3.
- **B6 (socio nueva):** no se preregistra. Solo se propone a Rosa si alguna de A4–A7 gana; la fase 1 no
  analizó lo socio porque es fijo por distrito.

**Combinada (2c):** una sola variante con las familias que ganan (o empatan con mejor antelación o recall en
brotes nuevos), contra la referencia B, sin búsqueda hacia adelante.

**Comparaciones previstas: 15.** Son 7 del bloque A, 7 del bloque B (5 contra la referencia B y 2 contra la
familia A que extienden) y 1 de la combinada; cada una se evalúa en h=2, 3 y 4. Más una condicional (B6),
con aprobación. 2024 se reporta como contraste y no decide.
