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
| B3 | Historia propia ampliada | semanas desde el último caso (tope 52), pendiente MCO de 4 semanas, log(1 + casos) de la temporada anterior (2016 desde la historia de la regla de brote, sin registro = cero)§ | hasta `o` | semanas desde el último caso: observada; pendiente: no observada (hipótesis a priori); temporada anterior: no evaluable | B |
| B4 | Línea base estacional | log(1 + umbral) de la semana objetivo `t+h` en los 5 años previos, una columna por h (3)‡ | años previos | no aplica (se conoce al emitir) | B |
| B5 | Clima de incubación | media de la anomalía (climatología del bloque) de temperatura media y mínima, humedad y precipitación en `o−4..o` y `o−9..o−5` (8 columnas)§ | k = h..h+4 y h+5..h+9 (en h=4: 4–8 y 9–13) | anomalías de temperatura media y humedad: observadas; temperatura mínima y precipitación: hipótesis solo 2017 | B; base_6 + A3 |

‡ **Corrección del 2026-10-27, anterior a cualquier resultado de la fase 2** (aprobada por Rosa): la versión
anterior de B4 tenía 6 columnas, `log(1 + media)` y `log(1 + umbral)` para h=2, 3 y 4. Quedan solo las 3 del
umbral, porque el umbral ya contiene la media (media + 1,5 DE) y conviene tener menos columnas con solo 5 años
previos de historia. El número de comparaciones no cambia (15). Con esto, el preregistro queda congelado.

§ **Aclaraciones del 2026-10-27, anteriores a cualquier resultado de la fase 2b** (aprobadas por Rosa):
- **Extensión:** el candidato es `base_6` + familia A + familia B y la referencia es `base_6` + familia A
  (`base_6`+A1+A2+B1 frente a `base_6`+A1+A2; `base_6`+A3+B5 frente a `base_6`+A3). Así se mide qué agrega lo
  nuevo.
- **B5:** las ventanas pasan de `o−4..o` y `o−8..o−4`, que compartían la semana `o−4`, a `o−4..o` y `o−9..o−5`,
  de 5 semanas cada una y sin solaparse.
- **B3:** los casos de la temporada anterior de 2017 (temporada 2016) se toman de la historia que usa la regla
  de brote (`epi_piura_semanal.csv`, registrada en el manifest), con la misma convención: sin registro = cero.
  Así no se excluye 2017 del entrenamiento.
- **B4:** el umbral de t+h se calcula con `umbral_brote_futuro`, la misma regla de gold extendida a semanas fuera
  del panel, para que no queden nulos al final de 2025.

Descartes sin probar:
- **Aceleración de la historia propia:** no observada y es una segunda diferencia de conteos chicos.
- **Valores climáticos sin anomalía:** la temperatura media no se observa, y la humedad y la precipitación
  observadas ya están en A3.
- **B6 (socio nueva):** no se preregistra. Solo se propone a Rosa si alguna de A4–A7 gana; la fase 1 no
  analizó lo socio porque es fijo por distrito.

**Combinada (2c), preregistrada el 2026-10-27 antes de correr nada de la 2c** (aprobada por Rosa):
- **Candidatas:** **C** = `base_6`+B1+B2+B3 (las que ganan, más B2, que empata con mejor recall en brotes
  nuevos) y **C3** = `base_6`+B3.
- **Comparaciones** (regla simétrica, 5 semillas, intersección de filas de cada par):
  1. C frente a B (sobre B∩C).
  2. C3 frente a B: se reutiliza B3 frente a B de la 2b, porque las filas son las mismas.
  3. C frente a C3 (sobre C3∩C).
- **Decisión.** «Gana a X» significa adoptable frente a X: gana en algún horizonte y no pierde en ninguno.
  - Si ni C ni C3 ganan a B, se mantiene `base_6`.
  - Si solo una gana a B, se elige esa.
  - Si ambas ganan a B: C si gana a C3; si C empata o pierde frente a C3, se elige C3.
  - Ante empate entre candidatas del mismo nivel gana la de menos columnas. Es la versión por variables de la
    regla de simplicidad del protocolo.
- **Robustez (solo lectura, no decide).** Para la elegida frente a B: quitar del entrenamiento, una a la vez,
  las primeras 8 semanas de orígenes de 2017 y la temporada 2018 (5 semillas), y reportar si se mantiene el
  signo de la diferencia de F1 y de antelación en 2022 y 2023.
- **SHAP** por horizonte de la elegida (HU0008-4).

**Comparaciones previstas: 16.** Son 7 del bloque A, 7 del bloque B y 2 de la combinada (C frente a B y C frente
a C3; C3 frente a B ya está contada en la 2b), más una condicional (B6), con aprobación. Las de robustez son de
lectura y no se cuentan. 2024 se reporta como contraste y no decide.

## Fase 2a · Re-ensayo del bloque A sobre E3·S4_s2

Cada familia se suma a `base_6` y se compara contra la referencia B con la regla simétrica del protocolo:
5 semillas, mismos bloques e hiperparámetros fijos, `estrategias_horizonte.decidir_frente_a_referencia`. A3
excluye 65 filas de entrenamiento (la primera semana de 2017 de cada distrito, sin `media5`) y se compara contra
**B∩A3**, entrenada sin esas filas. El CP1 de A7 se ajusta, con estandarización incluida, solo con los orígenes
de entrenamiento de cada bloque: explica entre el 57 % y el 61 % de la varianza. Comparaciones hechas: **7 de 15**.

### Veredictos (regla simétrica)

| Id | Familia | h=2 | h=3 | h=4 | Antecedente S1 (no comparable) |
|---|---|---|---|---|---|
| A1 | Vecinos | empate | empate | empate | no elegida; ΔF1 val +0,003 / +0,000 |
| A2 | Jerarquía | empate | **pierde** | compensa (empate) | elegida (reg. y cls.); +0,010 / +0,012 |
| A3 | Clima de gold | empate | empate | empate | no elegida; −0,024 / −0,057 |
| A4 | Población 2017 | empate | empate | empate | elegida (fija); +0,003 / +0,063 |
| A5 | Población anual† | empate | empate | empate | elegida para cls. (anual); −0,002 / +0,071 |
| A6 | Fracciones 2017 | empate | empate | empate | no elegida; +0,002 / −0,001 |
| A7 | Fracciones anuales (CP1)† | empate | empate | empate | `anual_eje` no elegida; +0,004 / −0,003 |

Ninguna familia gana en ningún horizonte. Ninguna recibe la marca de «posible señal de temporada», porque
ninguna mejora el F1 según la regla en ambas temporadas. Ninguna mejora la antelación ni el recall en brotes
nuevos en ambas temporadas. † A5 y A7 usan fracciones reconstruidas retrospectivamente con 2025: aunque hubieran
ganado, no serían pronósticos que se habrían podido emitir.

### Lectura por familia (observaciones; no cambian los veredictos)

- **A1, vecinos: la mejora es solo de 2022.**
  - F1: +0,036 / +0,055 / +0,097 en h=2/3/4, por encima del rango entre semillas (0,019 / 0,008 / 0,030).
  - Recall en brotes nuevos: +0,04 a +0,08.
  - Recall en todas las fases de la curva: sube.
  - Antelación en h=2: 0,158 frente a 0,053.

  En 2023 no cambia nada (ΔF1 entre −0,007 y +0,002; antelación igual). La regla exige mejora en ambas
  temporadas, así que el veredicto es empate. **Con una sola temporada a favor, la regla no permite separar esta
  mejora de una particularidad de 2022.**
- **A2, jerarquía: descartada por perder en h=3.** Empeora el F1 en ambas temporadas en h=3 (−0,046 / −0,015)
  y en h=4 (−0,096 / −0,022). En h=4 la mejora de AUPRC la deja en «compensa». **El veredicto cambió frente a
  S1**, donde era la elegida en validación.
- **A3, clima de gold: relevante para la parte de regresión de la HU0007-4.** El F1 queda en empate (baja en
  2022, sube en 2023). En cambio, la razón MAE frente a la persistencia baja en 2022 y 2023, en los 3 horizontes,
  por encima del umbral de empate (rango entre semillas ≤ 0,057). Es una guarda: no da victoria según la regla.
  Medianas de semillas, A3 frente a B∩A3:

  | Temporada | h | MAE/pers. A3 | MAE/pers. B∩A3 | RMSE/pers. A3 | RMSE/pers. B∩A3 |
  |---|---|---|---|---|---|
  | 2022 | 2 | 0,965 | 1,055 | 1,007 | 1,178 |
  | 2022 | 3 | 0,980 | 1,157 | 1,088 | 1,394 |
  | 2022 | 4 | 1,028 | 1,297 | 1,228 | 1,678 |
  | 2023 | 2 | 0,955 | 1,008 | 1,109 | 1,171 |
  | 2023 | 3 | 0,816 | 0,864 | 0,897 | 0,963 |
  | 2023 | 4 | 0,753 | 0,793 | 0,792 | 0,845 |
  | 2024 (contraste) | 2 | 0,976 | 1,355 | 0,997 | 1,816 |
  | 2024 (contraste) | 3 | 0,937 | 1,467 | 0,955 | 1,911 |
  | 2024 (contraste) | 4 | 0,884 | 1,499 | 0,895 | 1,868 |

  - La razón RMSE se describe sin umbral de empate: el protocolo calcula rangos entre semillas para el RMSE
    absoluto, no para la razón.
  - Frente al criterio de regresión de la HU0007-4 (razones ≤ 0,85), A3 cumple solo en 2023 con h=4, igual que
    B∩A3. En 2023 con h=3 cumple la razón MAE pero no la RMSE.
  - En 2024 la caída es grande (RMSE/pers. de 1,82–1,91 a 0,90–1,00), pero no llega a 0,85 y 2024 no decide.
  - El preregistro ya incluye **B5 frente a `base_6`+A3**, que medirá si el clima de incubación aporta además
    del clima de gold. **Cambió frente a S1**, donde el clima empeoraba.
- **A4, población 2017:** empate, con veto por empeorar MAE en h=2 y h=3. En S1 ayudaba al clasificador
  (+0,063), que S4 ya no tiene.
- **A5, A6 y A7:** empate. Las diferencias de F1 son negativas y chicas en 2022 (−0,002 a −0,030) y nulas en
  2023. A5 tiene un veto por Brier en h=4.
- **2024 (contraste, no decide):** el F1 de todas las variantes queda dentro de ±0,007 del de B.

### Implicaciones para lo que sigue (hipótesis, no decisiones)

- No hay ninguna familia del bloque A que **gane**. Para la combinada (2c) solo entrarían familias que ganen o que
  empaten con mejor antelación o recall en nuevos según la regla; en el bloque A no hay ninguna.
- B1 se compara también contra `base_6`+A1+A2 y B5 contra `base_6`+A3. Esas dos referencias se ajustan en 2b.

## Fase 2b · Variables nuevas (bloque B) sobre E3·S4_s2

Las variables B1–B5 se calculan en memoria en `src/modeling/features_inicio.py`, con el estado de la semana de
origen (semanas ≤ `o`):
- B2 (núcleo) y B5 (climatología de las anomalías) se ajustan con el corte de cada bloque.
- B3 toma la temporada 2016 de la historia de la regla de brote.
- B4 usa `umbral_brote_futuro`, que coincide bit a bit con el código que genera gold; contra el CSV de gold, `k`
  y `brote` son idénticos y el valor difiere en menos de 10⁻¹² por el redondeo de la escritura.

Tests de no fuga, todos aprobados antes de correr (`tests/test_features_inicio.py`):
- perturbación sobre datos sintéticos y sobre el panel real (las variables B de orígenes ≤ D no cambian);
- B2 y B5 por bloque (los datos posteriores a 2022 no cambian las predicciones de 2021–2022);
- reproducción de los niveles y fracciones `_h2` de gold en el origen;
- B4 sin nulos al final de 2025.

Nulos de arranque, todos en 2017:
- B1 y B2: 65 filas, la primera semana de origen.
- B5: 390 filas, las primeras 6 semanas.
- B3 y B4: ninguno.

Cada variante se compara contra su B∩ en la misma intersección de filas. Comparaciones hechas: 7 (acumuladas:
**14 de 15**).

### Veredictos (regla simétrica)

| Candidata | Referencia | h=2 | h=3 | h=4 | Mejora antelación | Mejora recall nuevos | Señal de temporada |
|---|---|---|---|---|---|---|---|
| B1 dinámica espacial | B∩B1 | **gana** | empate | empate | h=2 | — | no |
| B2 distritos núcleo | B∩B2 | empate | empate | empate | — | h=2 | no |
| B3 historia propia ampliada | B | **gana** | **gana** | empate | h=2, h=3 | h=2 | no |
| B4 línea base estacional | B | empate | empate | empate | — | — | no |
| B5 clima de incubación | B∩B5 | empate | empate | empate | — | — | no |
| `base_6`+A1+A2+B1 | `base_6`+A1+A2 (∩) | empate | empate | empate | — | — | no |
| `base_6`+A3+B5 | `base_6`+A3 (∩) | empate | empate | **pierde** | — | — | no |

### Lectura por familia (observaciones; no cambian los veredictos)

- **B3 gana en h=2 y h=3** por F1 (en ambas temporadas, por encima del rango entre semillas) y por antelación.
  - F1 en h=2: +0,046 (2022) y +0,011 (2023); en h=3: +0,022 y +0,017.
  - Antelación sobre inicios limpios: 0,147 frente a 0,084 en h=2 (diferencia pareada +0,074, IC95 0,031 a
    0,126) y 0,126 frente a 0,095 en h=3 (+0,053, IC95 0,011 a 0,105).
  - Recall en brotes nuevos en h=2: +0,061 (2022) y +0,035 (2023).
  - En 2022 baja mucho el error de casos (MAE/pers. 1,056 → 0,929 en h=2; 1,293 → 0,947 en h=4).
  - En h=4 empata.
  - En 2024 (contraste) el F1 queda entre −0,008 y −0,002 frente a B.
  - Como sube la antelación y el recall en nuevos, **no** recibe la marca de señal de temporada.
  - Límite: «semanas desde el último caso» empieza truncada en las primeras semanas de 2017 (no usa la
    historia previa); afecta solo filas de entrenamiento.
- **B1 gana en h=2 solo por antelación, no por F1** (0,137 frente a 0,084; +0,042, IC95 0,011 a 0,084), con
  más inicios avisados en 2022 y en 2023. Su F1 de 2022 cae mucho (en h=4, de 0,463 a 0,275); la regla no lo
  cuenta como pérdida porque es una sola temporada.
  - El F1 no mejora: sube en 2023 (+0,011 a +0,016) y **baja en 2022** (−0,047 / −0,093 / −0,188 en h=2/3/4).
    Como empeora en una sola temporada, la regla no lo cuenta.
  - La caída de 2022 en h=4 es grande (0,463 → 0,275) y debe pesar en la lectura, aunque no cambie el
    veredicto.
  - La extensión `base_6`+A1+A2+B1 frente a `base_6`+A1+A2 empata en los 3 horizontes: sobre A1+A2, lo nuevo
    no agrega según la regla.
- **B2 empata.** Mejora el recall en brotes nuevos en h=2 (+0,041 / +0,035, justo en el umbral de 2023). En
  2022, h=4, el F1 baja (−0,063).
- **B4 empata** en los 3 horizontes. Baja el MAE en 2022 pero lo sube en 2023.
- **B5 empata frente a B∩B5**, pero en 2022 el F1 de h=3 y h=4 se desploma (0,360 y 0,036, frente a 0,497 y
  0,290). La extensión `base_6`+A3+B5 **pierde** en h=4 frente a `base_6`+A3 (F1 −0,225 en 2022 y −0,008 en
  2023). El clima de incubación no agrega sobre el clima de gold.

### Observación transversal: la fragilidad de 2022 en h=4

Quitar solo 390 filas de entrenamiento de comienzos de 2017 (B∩B5) baja el F1 de 2022 en h=4 de 0,478 a 0,290,
y quitar 65 (B∩B1) lo deja en 0,463. El F1 a 0,50 de 2022 en h=4 es muy sensible a cambios chicos en el
entrenamiento. Eso pide prudencia con cualquier diferencia grande que aparezca solo en esa celda. Es una
observación: no cambia la regla.

### Implicaciones para la 2c (según la regla preregistrada)

Entran a la combinada las familias que **ganan** (B1 y B3) o que empatan con mejor antelación o recall en
brotes nuevos (B2, por el recall en nuevos en h=2). Ninguna familia del bloque A cumple esa condición. La
variante conjunta candidata sería `base_6`+B1+B2+B3, comparada contra la referencia B en la intersección de filas.

## Fase 2c · Combinación

Preregistrada y commiteada antes de correr: candidatas **C** = `base_6`+B1+B2+B3 y **C3** = `base_6`+B3.
Comparaciones nuevas: 2 (acumuladas: **16**, todas las previstas).

### Veredictos (regla simétrica, 5 semillas)

| Candidata | Referencia | h=2 | h=3 | h=4 | Resultado |
|---|---|---|---|---|---|
| C (`base_6`+B1+B2+B3) | B∩C | **gana** | empate | empate | adoptable |
| C3 (`base_6`+B3) | B (reutiliza la 2b) | **gana** | **gana** | empate | adoptable |
| C | C3∩C | empate | empate | empate | empate |

**Decisión según la regla preregistrada:** ambas ganan a B y C empata con C3, así que **se elige C3**, que tiene
menos columnas (9 frente a 21).

**Matriz elegida:** `base_6` + B3 = `hist_lag_a`, `hist_lag_b`, `hist_media_4`, `hist_semanas_pos_4`,
`semana_epi_seno`, `semana_epi_coseno`, `propia_semanas_desde_ultimo_caso`, `propia_pendiente_4` y
`propia_log_casos_temporada_anterior`.

Observaciones sobre C, que no cambian la decisión:
- Mejora el F1 de 2023 en los 3 horizontes (+0,018 a +0,033), pero en 2022 lo derrumba en h=4 (0,463 → 0,063)
  y lo baja en h=3. Es la misma caída que mostraron B1 y B5 en la celda frágil 2022·h=4.
- Frente a C3 empata en todo: B1 y B2 no agregan nada sobre B3 según la regla.

### Robustez de C3 frente a B (solo lectura; no cambia la decisión)

Se quitaron del entrenamiento de ambas, una a la vez, las primeras 8 semanas de orígenes de 2017 (520 filas) y
la temporada 2018 (3380 filas). Diferencias C3 − B (medianas de 5 semillas):

| Recorte | h | ΔF1 2022 | ΔF1 2023 | ΔAntelación 2022 | ΔAntelación 2023 | Veredicto |
|---|---|---|---|---|---|---|
| ninguno | 2 | +0,046 | +0,011 | +0,079 | +0,053 | gana |
| ninguno | 3 | +0,022 | +0,017 | −0,026 | +0,053 | gana |
| ninguno | 4 | −0,012 | +0,018 | 0,000 | +0,053 | empate |
| sin 8 primeras semanas de 2017 | 2 | +0,030 | +0,003 | +0,026 | 0,000 | empate |
| sin 8 primeras semanas de 2017 | 3 | **−0,006** | +0,004 | 0,000 | 0,000 | empate |
| sin 8 primeras semanas de 2017 | 4 | −0,042 | +0,006 | 0,000 | +0,018 | empate |
| sin temporada 2018 | 2 | +0,031 | +0,019 | +0,053 | +0,053 | gana |
| sin temporada 2018 | 3 | +0,004 | +0,026 | 0,000 | +0,070 | gana |
| sin temporada 2018 | 4 | −0,098 | +0,026 | 0,000 | +0,088 | empate |

**Límite.** Sin las primeras 8 semanas de 2017, el signo de la diferencia de F1 se **invierte** en h=3 de 2022
(+0,022 → −0,006). La ventaja de antelación desaparece (pasa a 0) en h=2 de 2023 y en h=3 de ambas temporadas, y
las dos victorias de C3 pasan a empate. Sin la temporada 2018, en cambio, se mantienen las victorias en h=2 y
h=3 y todos los signos de F1.

La ventaja de B3 depende en buena parte de que el entrenamiento incluya el arranque de la epidemia de 2017. Con
las dos epidemias grandes concentrando los inicios, esto se reporta como límite de la elección: el resultado no
es estable ante quitar 8 semanas de entrenamiento.

### SHAP por horizonte de C3 (semilla 17; media de |SHAP| en el log de casos esperados)

| Variable | 2022 (h=2 / 3 / 4) | 2023 (h=2 / 3 / 4) | 2024 (h=2 / 3 / 4) |
|---|---|---|---|
| `hist_lag_a` | 1,42 / 1,35 / 1,26 | 1,25 / 1,19 / 1,13 | 1,54 / 1,48 / 1,41 |
| `hist_media_4` | 0,55 / 0,54 / 0,53 | 0,68 / 0,66 / 0,64 | 0,63 / 0,61 / 0,59 |
| `propia_semanas_desde_ultimo_caso` | 0,43 / 0,40 / 0,37 | 0,54 / 0,50 / 0,48 | 0,39 / 0,37 / 0,35 |
| `semana_epi_seno` | 0,19 / 0,25 / 0,31 | 0,17 / 0,22 / 0,26 | 0,15 / 0,21 / 0,27 |
| `hist_lag_b` | 0,24 / 0,23 / 0,22 | 0,18 / 0,17 / 0,16 | 0,22 / 0,21 / 0,20 |
| `propia_log_casos_temporada_anterior` | 0,16 / 0,18 / 0,20 | 0,11 / 0,12 / 0,14 | 0,16 / 0,19 / 0,21 |
| `semana_epi_coseno` | 0,05 / 0,08 / 0,11 | 0,05 / 0,08 / 0,11 | 0,03 / 0,04 / 0,06 |
| `hist_semanas_pos_4` | 0,09 / 0,09 / 0,09 | 0,05 / 0,05 / 0,05 | 0,00 / 0,00 / 0,00 |
| `propia_pendiente_4` | 0,06 / 0,07 / 0,08 | 0,04 / 0,05 / 0,06 | 0,04 / 0,05 / 0,06 |

«Semanas desde el último caso» es la tercera variable en importancia en todos los bloques. Con el horizonte,
crecen el calendario y la temporada anterior, y bajan los rezagos.

**Limitación de B3, sin cambiar su definición después de los resultados:** «semanas desde el último caso» empieza
truncada al inicio de 2017, porque no usa la historia previa al panel; afecta solo filas de entrenamiento.

## Conclusión de la fase 2 (variables)

- **Matriz elegida: C3 = `base_6` + B3 (9 columnas).** Bajo el protocolo congelado, frente a la referencia B
  (`base_6`), gana en h=2 y h=3 por F1 a 0,50 en 2022 y 2023 y por antelación sobre inicios limpios, y empata en
  h=4. Ninguna familia del bloque A ganó. De las nuevas, solo B3 sostiene la mejora; B1 y B2 no agregan nada
  sobre B3.
- **La mejora es bajo el protocolo y frágil.** Depende de los pocos inicios de 2017 que hay en el entrenamiento:
  sin las 8 primeras semanas de orígenes de 2017, las dos victorias de C3 pasan a empate, y en h=3 de 2022 se
  invierte el signo del F1. Las diferencias son de una a pocas centésimas de F1 y de pocos episodios de
  antelación sobre 95.
- **No se puede concluir que el modelo anticipe brotes en general.** La mejora se mide sobre dos temporadas de
  selección (2022 y 2023) que además se usaron para elegir. La magnitud real la dirá la evaluación independiente
  de 2026.
- **Sobre «semanas desde el último caso»:** es la tercera variable por importancia SHAP en el modelo de conteo y
  su inclusión se asocia a la mejora observada. Eso describe cómo usa el modelo la variable; no muestra que el
  tiempo sin casos tenga relación causal con el inicio de un brote.

## Fase 3 · Preregistro de la optimización de hiperparámetros (HU0007-3)

Fuente de verdad: `src/modeling/hiperparametros.py → PREREGISTRO_FASE3`. Se commiteó antes del estudio
(aprobado por Rosa, 2026-10-27).

- **Matriz:** C3 = `base_6` + B3.
- **Base de comparación:** C3 con los hiperparámetros heredados: 160 árboles, profundidad 3, learning rate 0,05,
  subsample 0,8, colsample 0,9, min_child_weight 5, reg_lambda 5. Además, `reg_alpha` = `gamma` = 0 y
  `max_delta_step` = 0,7, que es el valor por defecto de XGBoost con `count:poisson`; los tres se fijan
  explícitamente.
- **Objetivo:** log-loss de la probabilidad calibrada (Poisson → binomial negativa con α dentro de la muestra →
  Platt cronológico), promediado sobre h=2/3/4 × 2022 y 2023. F1 a 0,50 y AUPRC se registran por trial, pero no
  se optimizan.
- **Espacio:**
  - `max_depth` 2–8; `min_child_weight` 1–50 (log); `learning_rate` 0,01–0,3 (log); `n_estimators` 100–1500;
  - `subsample` y `colsample_bytree` 0,5–1; `reg_lambda` y `reg_alpha` 1e-3–10 (log); `gamma` 0–5;
  - `max_delta_step` **0,3–2** (lineal). No es 0–2 porque con `count:poisson` el 0 significa «sin límite» y puede
    volver inestable la optimización; el rango incluye el 0,7 de la base.
- **Estudio:** TPE con semilla 20261027, XGBoost con semilla 17, 100 trials, sin pruning ni early stopping. Un
  trial que falle o dé un objetivo no finito queda como FAIL en Optuna y en MLflow, y se reporta.
- **Trial 0:** la base con `reg_alpha = 1e-3`, porque Optuna no admite 0 en escala log. Medido antes del estudio,
  con semilla 17: objetivo 0,220007, igual al sexto decimal que con `reg_alpha = 0`; F1 y AUPRC idénticos en las 6
  celdas; diferencia máxima de casos predichos 0,0024. La regla compara contra la **base exacta** (C3 de la 2c,
  `reg_alpha = 0`). El trial 0 solo sitúa el arranque de la curva, donde se muestran los dos.
- **Selección:** las 5 mejores por el objetivo se reentrenan con las 5 semillas y se elige la de mejor mediana
  del objetivo. Solo esa pasa por la regla simétrica contra la base: +1 comparación, **17 en total**.
- **Adopción:**
  - si la candidata gana, se adopta;
  - si empata, se queda la base, salvo que la candidata sea igual o más simple (árboles × profundidad);
  - si pierde, se queda la base.
- **Robustez (solo lectura):** la candidata final frente a la base sin las 8 primeras semanas de orígenes de 2017;
  se reportan los signos de la diferencia.
- **Tiempos medidos antes del estudio** (5 bloques × 1 semilla con el protocolo): base 6,5 s; 800 × 5, unos 30 s;
  1500 × 8, unos 104 s. Con unos 30 s esperados por trial, alcanza para 100.
- **Límite:** la búsqueda usa las mismas temporadas de selección (2022–2023), así que las métricas de la
  candidata son optimistas. 2024 es solo de contraste.

## Fase 3 · Resultados

Notebook `33_modelado_hiperparametros.ipynb`; cifras en `metricas/fe_hiperparametros.json → fase3_hiperparametros`;
figuras `curva_optimizacion_fase3.png` e `importancia_hiperparametros_fase3.png`.

- **Trials:** 100 completos y 0 fallidos, como en el preregistro.
  - *Defecto y corrección (2026-10-27):* la primera corrida terminó con 99 trials. `estudio` contaba el trial 0
    encolado (en estado WAITING) como ya hecho y pedía 99. Se corrigió: un trial encolado cuenta solo cuando se
    ejecuta. El test `TestConteoDelEstudio` comprueba que el estudio termina con exactamente `n_trials` trials
    completos o fallidos y que reanudar no agrega de más.
  - El estudio se reanudó desde el almacén SQLite y se corrió el trial 99. Dio 0,210366, el 11.º mejor, así que
    no entra al top 5: la selección, la candidata y la regla no cambian.
  - En MLflow, el estudio de 99 trials (`adf16508…`) y sus hijos quedan marcados con `obsoleta = true`. El
    vigente es `d1a4f93b6d274ffc830a61a37f122cba` (padre + 100 hijos).
- **Base exacta (C3, `reg_alpha` = 0):** objetivo por semilla 0,220007 / 0,220112 / 0,219951 / 0,220917 /
  0,221031; mediana 0,220112. El trial 0 (`reg_alpha` = 1e-3) da 0,220007, igual a la base exacta con semilla 17.
- **Mejor trial:** n.º 86, objetivo 0,209188 con semilla 17.
- **Importancia (fANOVA, 100 trials):** `n_estimators` 0,67; `min_child_weight` 0,15; `max_delta_step` 0,09; el
  resto < 0,04.
- **Zona de las mejores:** las 10 mejores tienen profundidad 3–4, `learning_rate` 0,014–0,021, 918–1104 árboles,
  `min_child_weight` 25–44, `gamma` 1,9–3,0 y `max_delta_step` 1,68–1,97.
- **Top 5 con 5 semillas:** medianas 0,2095 (trials 86 y 91), 0,2097 (75 y 82) y 0,2100 (62). La candidata es
  el trial 86 (mejor mediana, 0,209471; complejidad 1103 × 3 = 3309, frente a 160 × 3 = 480 de la base).

### Veredicto y su costo en el conteo

- **Regla simétrica contra la base exacta (comparación 17 de 17): empate en h=2, h=3 y h=4.**
  - F1 a 0,50, delta 2022 / 2023: h2 −0,004 / +0,008; h3 +0,015 / +0,018; h4 +0,022 / +0,029. En h3 y h4 ambos
    deltas son positivos, pero el de 2022 no supera el rango entre semillas (umbrales 0,015 y 0,036).
  - Brier: mejora en las 6 celdas y supera el rango entre semillas en h2 y h3 (marcado como veto contra la base),
    pero Brier es una guarda y no decide.
  - Antelación h4: diferencia +0,074 (IC95 0,021 a 0,137), pero en 2022 la diferencia es 0, así que no cuenta
    como mejora (la regla pide ambas temporadas).
- **Adopción: se queda la base** (empata y la candidata es más compleja).
- **Costo en el conteo (HU0007-4):** la candidata empata en la alerta, pero empeora el conteo fuera de 2023.
  - Razón MAE: empeora en 2022 (+0,05 a +0,07) y mejora en 2023 (−0,03 a −0,06).
  - En el contraste 2024, MAE y RMSE son peores en los tres horizontes. Razón MAE h2/h3/h4: 1,18 → 1,35;
    1,23 → 1,46; 1,30 → 1,55. Razón RMSE: 1,24 → 1,58; 1,25 → 1,67; 1,27 → 1,72.
  - La búsqueda optimiza la probabilidad calibrada, no el conteo, y la candidata lo paga en conteo. Aunque la
    regla hubiera dado gana, este costo habría que ponerlo junto al veredicto.
- **Recall de brotes nuevos (lectura, no decide).** 2 primeras semanas, 2022 / 2023: h3 0,02 → 0,04 /
  0,14 → 0,17; h4 0 → 0 / 0,13 → 0,20. No pasa el criterio de `mejora_recall_nuevos`.
- **Robustez (solo lectura), sin las 8 primeras semanas de orígenes de 2017:** la regla daría gana en h2 y h3
  y empate en h4. Los signos de F1 y antelación son ≥ 0 en las 6 celdas, mientras que sin recorte F1 h2 2022 es
  negativo. Con esos orígenes la candidata se parece más a la base; sin ellos se separa algo más. No cambia la
  decisión.

### Cobertura de la HU0007-3

La HU0007-3 queda cubierta aunque la candidata no se adopte. Hubo búsqueda sistemática preregistrada (TPE, 100
trials), con los mejores parámetros, la curva de optimización, la importancia de cada hiperparámetro y la
comparación con la base bajo la regla. Todo está registrado en MLflow (`fe_hiperparametros_fase3_estudio`:
padre con los mejores parámetros, la candidata, la adopción y las tablas; un hijo por trial con su estado). Que
la configuración final conserve los hiperparámetros heredados es el resultado de esa búsqueda, no la falta de
búsqueda.

### Limitaciones y trabajo futuro

- **`max_delta_step` en el tope del rango:** en las 10 mejores va de 1,68 a 1,97, contra un máximo de 2,0. El
  óptimo de ese hiperparámetro podría estar fuera del rango preregistrado. El rango no se amplía en esta
  tesis: queda como limitación. Como trabajo futuro, una búsqueda con un tope mayor, preregistrada aparte.
- **Optimismo:** la búsqueda y la regla usan las mismas temporadas (2022–2023), así que las métricas de la
  candidata son optimistas. Aun así, empata.
- **Una sola semilla de XGBoost en la búsqueda** (17). Las 5 semillas se usan solo en el top 5.
