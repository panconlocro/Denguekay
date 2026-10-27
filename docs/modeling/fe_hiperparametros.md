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

## Fase 4 · Preregistro (verificación cruzada)

Fuente de verdad: `src/modeling/preregistro_fe.py → FASE4`, commiteado antes de correr (aprobado por Rosa,
2026-10-27). Configuración de partida: C3·S4_s2, hiperparámetros heredados, α dentro de la muestra.

- **4.1 Interacción: no se corre.** La fase 3 dejó los hiperparámetros que ya usó la fase 2. Reevaluar las
  familias con ellos daría exactamente las mismas predicciones (mismos datos, semillas y parámetros), así que no
  agrega información.
- **4.2 α dentro de la muestra frente a α OOS** (C3·S4_s2, 5 semillas, regla simétrica).
  - α OOS de un bloque: máxima verosimilitud NB2, por horizonte, con las predicciones fuera de muestra de todos
    los bloques anteriores (acumuladas) cuya semana objetivo cerró en el corte del bloque.
  - Primer bloque (2021): pseudo-bloque `temporada_2020`, entrenado con lo cerrado al 2019-08-03. Solo estima
    α: no se evalúa ni entra en Platt.
  - **Respaldo** (fijado en el código antes de ver ninguna α OOS): si la α OOS de un bloque y horizonte no
    converge, queda a menos de 1e-3 (en log α) de un límite del optimizador, o sale de [mín / 5, máx × 5] de las
    α dentro de la muestra de 2021–2024 (mismo horizonte y semilla), ese bloque usa la α dentro de la muestra y se
    reporta. El rango usa también los bloques posteriores al revisado; es solo un control de validez y no entra
    en ninguna predicción.
  - Adopción: gana → α OOS; empate o pierde → α dentro de la muestra (más simple).
  - **Limitación del pseudo-bloque:** 2020 tiene solo 2 semanas brote y cruza el inicio de la pandemia (posible
    subregistro, *hipótesis*). La dispersión de una temporada tranquila puede no representar la de una
    epidémica, y esa α entra en la cadena de Platt de 2022.
- **4.3 S4_s3 frente a S4_s2** (C3, con la α de la 4.2 en las dos ramas). Gana → S4_s3; empate o pierde → S4_s2.
- **4.4** Rangos entre semillas de la configuración final.
- Comparaciones del encargo: 17 + 2 = **19**.

## Fase 4 · Resultados

Notebook `34_modelado_verificacion_cruzada.ipynb`; cifras en `metricas/fe_hiperparametros.json →
fase4_verificacion`; figura `alfas_fase4.png`; MLflow `fe_hiperparametros_fase4_verificacion`
(`cda23d281501422986cdf4b47e121320`).

### 4.2 · α OOS: empate, se queda la α dentro de la muestra (comparación 18 de 19)

α por bloque y horizonte (mediana de las 5 semillas), h = 2 / 3 / 4:

| Bloque | Dentro de la muestra | OOS | Respaldo (semillas) |
|---|---|---|---|
| temporada_2021 (OOS desde el pseudo-bloque 2020) | 0,53 / 0,89 / 1,40 | 62,9 / 65,5 / 69,9 | 5 / 5 / 5 |
| temporada_2022 | 0,83 / 1,42 / 2,29 | 6,78 / 11,4 / 15,7 | 5 / 5 / 5 |
| temporada_2023 | 0,75 / 1,34 / 2,10 | 1,24 / 2,31 / 3,58 | 0 |
| temporada_2024 | 0,90 / 1,57 / 2,35 | 1,05 / 1,92 / 2,90 | 0 |
| calendario_2025 | 0,72 / 1,21 / 1,80 | 0,84 / 1,43 / 2,09 | 0 |

- **El respaldo actuó en 30 de 75 casos** (semilla × bloque × horizonte): en 2021 y 2022, en todas las semillas
  y horizontes, porque la α OOS salió por encima del rango (máx × 5: 4,5 / 7,9 / 11,8). En todos los casos
  convergió y no quedó en el límite del optimizador.
- **Lectura de la α de 2021:** la estimada con el pseudo-bloque 2020 es unas 50–120 veces la de dentro de la
  muestra. Es lo que la limitación anticipaba: el modelo entrenado con 2017–2019 predice en una temporada
  tranquila mucho más de lo que ocurre, y la binomial negativa absorbe esa diferencia como dispersión. En 2022
  el conjunto OOS aún incluye 2020 y sigue fuera de rango. Desde 2023, la α OOS es entre 1,2 y 1,7 veces la de
  dentro de la muestra. Esto coincide con la *hipótesis* de que la α dentro de la muestra subestima la
  dispersión.
- **Veredicto: empate en h=2, h=3 y h=4.**
  - Como 2021 y 2022 usan el respaldo, la candidata es idéntica a la referencia en 2022 (todas las deltas
    valen 0). La regla pide mejora o empeora en las dos temporadas de selección, así que **en esta corrida no
    podía dar gana ni pierde**. El empate es una consecuencia del respaldo, no evidencia de equivalencia.
  - En 2023, la única temporada donde difieren, la α OOS empeora F1 (−0,013 / −0,051 / −0,059) y Brier (+0,005 /
    +0,011 / +0,015). La antelación también baja: h3 −0,053 (IC −0,095 a −0,011) y h4 −0,084 (IC −0,137 a
    −0,032). Ese descenso no cuenta como empeora porque en 2022 la diferencia es 0.
  - Conteo: idéntico por construcción (la α solo cambia la probabilidad).
- **Adopción: α dentro de la muestra.** Lo que se observa en 2023 va en contra de la OOS, no a favor.
- **Robustez (solo lectura), sin las 8 primeras semanas de 2017:** empate en los tres horizontes, con los mismos
  signos (F1 y antelación ≤ 0 en 2023).

### 4.3 · S4_s3: gana en h=4, se adopta S4_s3 (comparación 19 de 19)

Con α dentro de la muestra en las dos ramas, C3·S4_s3 frente a C3·S4_s2:

| h | Veredicto | Motivo | Lectura |
|---|---|---|---|
| 2 | empate | sin mejora primaria; S4_s3 empeora AUPRC y Brier por encima del rango entre semillas (vetos) | F1 −0,017 / −0,004 |
| 3 | empate | F1 +0,047 en 2022, pero −0,001 en 2023 | recall de brotes nuevos sube en 2022 y 2023 (`mejora_recall_nuevos`) |
| 4 | **gana** | antelación: +0,095 (IC 0,032 a 0,158), positiva en 2022 (+0,053) y en 2023 (+0,123) | F1 +0,080 / +0,007 (dentro del rango en 2023) |

- **Adopción: S4_s3** (gana en h=4 y no pierde en ninguno).
- **Antelación** (inicios limpios avisados, mediana de semillas), S4_s2 → S4_s3, selección 2022–2023: h2 0,147 →
  0,137; h3 0,126 → 0,211; h4 0,137 → 0,232. En el contraste 2024: h2 0,174 → 0,435; h3 0,391 → 0,565; h4
  0,348 → 0,478.
- **Recall de brotes nuevos** (2 primeras semanas), 2022 / 2023: h3 0,02 → 0,08 / 0,14 → 0,17; h4 0 → 0,04 /
  0,13 → 0,16.
- **Costo en el conteo (HU0007-4), va junto al veredicto:**
  - La razón MAE empeora en 2022 (+0,07 / +0,10 / +0,09) y mejora en 2023 (−0,13 / −0,06 / −0,03).
  - Contraste 2024: razón MAE 1,18 → 1,35, 1,23 → 1,52, 1,30 → 1,62; razón RMSE 1,24 → 1,67, 1,25 → 1,89,
    1,27 → 2,01.
  - S4_s3 avisa antes, pero estima peor la magnitud fuera de 2023. Es el mismo patrón que la candidata de la
    fase 3, más marcado.
- **Robustez (solo lectura), sin las 8 primeras semanas de 2017:** gana en h3 y h4, empate en h2. La antelación
  en h3 y h4 sigue siendo positiva en 2022 y 2023. La ganancia en h4 no depende de esos orígenes de 2017.
- **Contexto:** con `base_6` (notebook 31), S4_s2 y S4_s3 empataban en los tres horizontes. Con C3, S4_s3 pasa a
  ganar en h4 por antelación. *Hipótesis*, sin prueba causal: B3 y el margen de persistencia se complementan.

### Decisión de Rosa sobre la configuración final (2026-10-27)

Se sigue la regla preregistrada: **C3 · E3 · S4_s3 · α dentro de la muestra · hiperparámetros heredados · Platt ·
p ≥ 0,50.** El conteo no cambia la decisión. La regla lo trata como guarda y no hubo veto, así que descartar
S4_s3 por el conteo sería cambiar el criterio después de ver los resultados.

### 4.4 · Configuración final y rangos entre semillas

**Configuración final:** C3 (`base_6` + B3, 9 columnas) · E3 multi-salida · **S4_s3** (Poisson con margen
`log(persistencia + 0,5)`, binomial negativa) · α dentro de la muestra · hiperparámetros heredados · Platt
cronológico · alerta p ≥ 0,50.

Mediana [rango entre semillas], h = 2 / 3 / 4:

| Métrica | 2022 | 2023 | 2024 (contraste) |
|---|---|---|---|
| F1 a 0,50 | 0,711 [0,007] / 0,658 [0,018] / 0,546 [0,008] | 0,852 [0,001] / 0,828 [0,003] / 0,803 [0,005] | 0,796 [0,003] / 0,778 [0,002] / 0,745 [0,002] |
| AUPRC | 0,789 [0,002] / 0,781 [0,004] / 0,753 [0,005] | 0,947 [0,001] / 0,928 [0,001] / 0,917 [0,002] | 0,891 [0,001] / 0,870 [0,001] / 0,831 [0,001] |
| Brier | 0,053 / 0,057 / 0,062 [≤ 0,001] | 0,062 / 0,075 / 0,084 [≤ 0,001] | 0,076 / 0,086 / 0,098 [≤ 0,001] |
| Razón MAE | 1,001 [0,004] / 1,021 [0,019] / 1,040 [0,028] | 0,881 [0,012] / 0,808 [0,009] / 0,764 [0,012] | 1,352 [0,037] / 1,515 [0,049] / 1,622 [0,052] |
| Razón RMSE | 1,106 [0,006] / 1,232 [0,033] / 1,380 [0,053] | 0,987 [0,023] / 0,913 [0,014] / 0,852 [0,011] | 1,673 [0,126] / 1,890 [0,149] / 2,014 [0,136] |

- **Antelación** (mediana [mín–máx]): 2022–2023 h2 0,137 [0,126–0,158], h3 0,211 [0,200–0,211], h4 0,232
  [0,221–0,232]; 2024 h2 0,435, h3 0,565, h4 0,478 [0,478–0,522].
- **Recall de brotes nuevos** (mediana [mín–máx]): 2022 h2 0,10 [0,08–0,14], h3 0,08, h4 0,04; 2023 h2 0,12, h3
  0,17 [0,16–0,17], h4 0,16 [0,15–0,20].
- **α** (S4_s3, dentro de la muestra, mediana [mín–máx]), h = 2 / 3 / 4: 2022 0,84 / 1,30 / 1,89; 2023 0,76 /
  1,22 / 1,73; 2024 0,81 / 1,30 / 1,83; los rangos entre semillas son ≤ 0,05.
- **Calendario 2025** (sensibilidad): F1 a 0,50 es 0 en h2 y h4 y 0,14 en h3, con un rango de 0,12 entre
  semillas. Hay muy pocas semanas brote, así que no es interpretable.
- Los rangos entre semillas son pequeños en la alerta (F1 ≤ 0,018 en selección) y mayores en el conteo del
  contraste 2024 (razón RMSE 0,13–0,15).

### Configuración final frente a la persistencia (antelación, semilla 17)

Diferencia pareada modelo − persistencia en los 95 inicios limpios de 2022–2023, con el IC bootstrap estratificado
del protocolo:

| h | C3·S4_s3 (final) | C3·S4_s2 | Final, 2022 / 2023 |
|---|---|---|---|
| 2 | +0,011 (IC −0,053 a 0,074) | +0,042 (IC −0,021 a 0,105) | 0,000 / +0,018 |
| 3 | +0,063 (IC −0,011 a 0,137) | +0,011 (IC −0,053 a 0,074) | 0,000 / +0,105 |
| 4 | +0,021 (IC −0,074 a 0,116) | −0,074 (IC −0,147 a 0,000) | −0,211 / +0,175 |

- **En h=4, la configuración final ya no pierde frente a la persistencia.** Antes, con E3·S4_s2 y `base_6`, la
  diferencia era −0,105 (IC −0,189 a −0,021). Ahora es +0,021 con un IC que incluye 0. Eso no significa que la
  supere.
- En ningún horizonte el IC excluye 0, así que tampoco la supera en h=2 ni en h=3.
- El signo de h=4 no es estable entre temporadas: en 2022 la persistencia sigue avisando más inicios (−0,211) y
  en 2023 avisa más la configuración final (+0,175).

### HU0007-4: C3·S4_s3 frente a C3·S4_s2 (medianas de semillas)

Clasificación: P ≥ 0,60, R ≥ 0,80 y F1 ≥ 0,70 con p ≥ 0,50. Regresión: razón MAE y razón RMSE ≤ 0,85.

| Temporada | h | Clasificación S4_s2 → S4_s3 | P / R / F1 de S4_s3 | Regresión S4_s2 → S4_s3 | MAE / RMSE de S4_s3 |
|---|---|---|---|---|---|
| 2022 | 2 | no → no | 0,725 / 0,696 / 0,711 | no → no | 1,001 / 1,106 |
| 2022 | 3 | no → no | 0,801 / 0,559 / 0,658 | no → no | 1,021 / 1,232 |
| 2022 | 4 | no → no | 0,870 / 0,399 / 0,546 | no → no | 1,040 / 1,380 |
| 2023 | 2 | sí → sí | 0,896 / 0,812 / 0,852 | no → no | 0,881 / 0,987 |
| 2023 | 3 | no → no | 0,890 / 0,774 / 0,828 | no → no | 0,808 / 0,913 |
| 2023 | 4 | no → no | 0,900 / 0,724 / 0,803 | no → no | 0,764 / 0,852 |
| 2024 | 2 | sí → sí | 0,737 / 0,866 / 0,796 | no → no | 1,352 / 1,673 |
| 2024 | 3 | sí → sí | 0,702 / 0,873 / 0,778 | no → no | 1,515 / 1,890 |
| 2024 | 4 | sí → sí | 0,667 / 0,846 / 0,745 | no → no | 1,622 / 2,014 |

- **Clasificación:** S4_s3 cumple en las mismas celdas que S4_s2 (2023 h2 y 2024 h2/h3/h4); no gana ni pierde
  ninguna. Lo que falla en el resto es el recall, que en 2022 sube con S4_s3 (h4 0,316 → 0,399) pero sigue lejos
  de 0,80.
- **Regresión, celda h=4 · 2023:** la referencia B (`base_6`·S4_s2) era la única celda que cumplía (0,793 /
  0,846). **Se perdió en la 2c, al entrar B3:** C3·S4_s2 da una razón RMSE de 0,876. S4_s3 la acerca a 0,852, a
  0,002 del umbral. Con la mediana no cumple, pero el umbral 0,85 cae dentro del rango entre semillas (razón RMSE
  0,846–0,857). Es una celda de frontera: no se puede decir que cumpla.
- **Con la configuración final, ninguna celda cumple el criterio de regresión de la HU0007-4.**

### Compromiso explícito de la configuración final

**S4_s3 avisa antes a cambio de estimar peor la magnitud fuera de 2023.** En h=4, la antelación en 2022–2023 sube
de 0,137 a 0,232 y deja de perder frente a la persistencia. En cambio, la razón RMSE del contraste 2024 es 1,67 /
1,89 / 2,01 (h2 / h3 / h4), frente a 1,24 / 1,25 / 1,27 de S4_s2, y en 2022 la razón MAE pasa de 0,92–0,95 a
1,00–1,04.

**Limitación del conteo para la interfaz y las HU0008:**
- Los casos predichos de la configuración final no deben presentarse como una estimación precisa de la
  magnitud. Fuera de 2023, el error es mayor que el de repetir los casos de la semana de origen (razones > 1).
- La interfaz debería mostrar los casos esperados como orden de magnitud o como apoyo de la alerta, y basar la
  alerta en la probabilidad calibrada.
- Cualquier explicación por variable (HU0008) sobre el modelo de conteo describe un modelo cuya magnitud es poco
  fiable fuera de 2023.

## Fase 5 · Síntesis del encargo

### Configuración final congelada (2026-10-27)

Fuente de verdad: `src/modeling/configuracion_final.py → CONFIGURACION_2026`, commit `d6bd0be` del 2026-10-27,
que es la fecha de congelamiento.

| Pieza | Valor |
|---|---|
| Matriz | C3 = `base_6` + B3 (9 columnas; diccionario en `diccionario_variables.md`, HU0006-3) |
| Estrategia | E3: un regresor XGBoost multi-salida (`multi_output_tree`) para t+2, t+3 y t+4 desde el origen o = t − 2 |
| Conteo | `count:poisson` con `base_margin` = log(casos del origen + 0,5) en las tres salidas (S4_s3) |
| Probabilidad | P(casos ≥ k) binomial negativa NB2, k = max(⌊umbral⌋ + 1, 2); α dentro de la muestra por horizonte |
| Hiperparámetros | heredados: 160 árboles, profundidad 3, learning rate 0,05, subsample 0,8, colsample 0,9, min_child_weight 5, reg_lambda 5, reg_alpha 0, gamma 0, max_delta_step 0,7 |
| Calibración | Platt cronológico con las predicciones fuera de muestra de las temporadas previas cerradas |
| Alerta | p ≥ 0,50 |
| Semilla de despliegue | 17 |
| Huella (configuración + módulos) | `88ed2a43b0171a0878b99122b70109be61b27d5d4d29a2b93eae55066fd8f945` |

`tests/test_configuracion_final.py` comprueba que la constante reproduce las predicciones guardadas de la fase 4
con la semilla 17. **No se cambia después de ver datos de 2026**: cualquier cambio es un encargo nuevo con su
propio preregistro.

### Cadena de decisiones (19 comparaciones preregistradas)

| Fase | Comparaciones | Resultado |
|---|---|---|
| 0 | — | Referencia B = E3·S4_s2 con `base_6`, reproducida 615/615 |
| 1 | — | Diagnóstico de inicios (2017–2021) y preregistro de A1–A7 y B1–B5 |
| 2a | 7 (A1–A7 frente a B) | Ninguna familia de gold gana; A2 pierde en h3 |
| 2b | 7 (B1–B5 frente a B; extensiones de B1 y B5) | B3 gana en h2 y h3; B1 gana en h2 solo por antelación; B2, B4 y B5 empatan; la extensión de B5 pierde en h4 |
| 2c | 2 (C frente a B; C frente a C3) | C y C3 ganan a B; C empata con C3 → **C3** (menos columnas) |
| 3 | 1 (candidata TPE frente a la base) | Empate → **hiperparámetros heredados** |
| 4.2 | 1 (α OOS frente a α dentro de la muestra) | Empate forzado por el respaldo → **α dentro de la muestra** |
| 4.3 | 1 (S4_s3 frente a S4_s2) | S4_s3 gana en h4 por antelación → **S4_s3** |

Las lecturas de robustez, SHAP, antelación y recall de brotes nuevos no decidieron. 2024 fue siempre contraste.

### Qué cambió frente a la referencia B (lectura)

- **Antelación sobre inicios limpios 2022–2023** (mediana de semillas): h4 0,105 (B) → 0,232 (final). Frente a
  la persistencia, h4 pasa de −0,105 (IC −0,189 a −0,021) a +0,021 (IC −0,074 a 0,116): **ya no pierde, no la
  supera**.
- **Clasificación (HU0007-4):** gana la celda 2023 · h2 (recall 0,782 → 0,812) y conserva las tres de 2024.
- **Regresión (HU0007-4):** pierde la única celda que cumplía (2023 · h4), que se perdió al entrar B3 (2c). Con
  S4_s3 queda en frontera (razón RMSE 0,852, rango entre semillas 0,846–0,857). En el contraste 2024 la
  magnitud empeora (razón RMSE 1,27 → 2,01 en h4).
- **Dependencia de 2017:** las ganancias de B3 sobre B se vuelven empates al quitar las 8 primeras semanas de
  orígenes de 2017 (2c). La de S4_s3 en h4 se mantiene sin ellas (4.3).

### Estado de la HU0007-4

Umbrales: clasificación P ≥ 0,60, R ≥ 0,80 y F1 ≥ 0,70 con p ≥ 0,50; regresión, razón MAE y razón RMSE ≤ 0,85
frente a la persistencia. Mediana de las 5 semillas.

| Temporada | h | Clasificación B → C3·S4_s2 → final | Regresión B → C3·S4_s2 → final |
|---|---|---|---|
| 2022 | 2 / 3 / 4 | no / no / no en las tres | no / no / no en las tres |
| 2023 | 2 | no → **sí** → **sí** | no → no → no |
| 2023 | 3 | no → no → no | no → no → no |
| 2023 | 4 | no → no → no | **sí** (0,793 / 0,846) → no (0,796 / 0,876) → no, frontera (0,764 / 0,852) |
| 2024 (contraste) | 2 / 3 / 4 | sí → sí → sí en las tres | no → no → no en las tres |

- **Clasificación:** cumple en 4 de 9 celdas (2023 h2 y 2024 h2/h3/h4). Lo que falla en el resto es el recall
  (2022 h4: 0,399).
- **Regresión:** no cumple en ninguna celda con la configuración final.
- **Precisión a la HU:** la HU habla de «temporada 2025-2026». El test independiente es solo la parte publicada
  después del congelamiento (ver más abajo). 2022–2023 son temporadas de selección (optimistas) y 2024 no es un
  test virgen.

### Evaluación prospectiva de 2026 (fijada ahora; todavía no se aplica a nada)

- **Test independiente:** las semanas objetivo publicadas por MINSA después del congelamiento vigente.
  - **Actualización (complemento de clima):** la configuración vigente es la V2 (C3 + A3). El test independiente
    empieza en el commit que la congela (2026-10-27, mismo día que la V1, pero posterior a ella). La V1
    (`d6bd0be`) queda como histórica.
- **No son independientes** las semanas 35–53 de 2025: ya están en el panel y se miraron como sensibilidad de
  conteos (`calendario_2025`). Aunque la HU0007-4 hable de «temporada 2025-2026», no cuentan.
- **Reporte:** cada métrica con su número de positivos (semanas brote o inicios limpios) y un IC bootstrap.
- **Mínimos** (`EVALUACION_2026["minimos"]`):
  - clasificación y regresión: **30 semanas brote** por horizonte;
  - antelación: **20 inicios limpios** por horizonte;
  - por debajo del mínimo, la celda es «no evaluable» en vez de «cumple / no cumple».
- **Justificación de los mínimos:**
  - `calendario_2025` tuvo 3 semanas brote por horizonte (2 de inicio). F1 dio 0 en h2 y h4 y 0,14 en h3, con
    0,12 de rango entre semillas: una sola semana cambiaba el veredicto.
  - Con 30 semanas brote, una semana mueve el recall 0,033; con 20 inicios, una alerta mueve la antelación 0,05.
  - Ambos mínimos quedan por debajo de los bloques que sí se evaluaron: temporada_2024 tuvo 23 inicios y 857
    semanas brote; temporada_2021, de calibración, 90 semanas brote.
  - Aun en el mínimo, el IC del recall es ancho (± 0,14 alrededor de 0,80 con 30 positivos). Por eso el IC va
    siempre junto a la cifra.

### Cambios propuestos, sin implementar

Los ejecuta el equipo. Complementan «Cambios que implicaría la arquitectura elegida» de
`arquitectura_horizontes.md`, que sigue vigente.

**Gold y feature engineering (`features.py`, notebook 22):**
- E3 se entrena solo con **gold h=2**. Los objetivos t+3 y t+4 salen de `tabla_origenes` y el umbral de
  cualquier semana objetivo, de `umbral_brote_futuro`. **No hace falta un gold h=3.**
- Agregar a gold h=2 las 3 columnas de B3 (`propia_semanas_desde_ultimo_caso`, `propia_pendiente_4`,
  `propia_log_casos_temporada_anterior`), con la misma definición que `features_inicio` (ver el diccionario).
- `construir_gold` tiene que leer el histórico epi previo a 2017 (`SILVER_EPI_HISTORICO`, el mismo del manifest
  de la regla de brote) para la temporada anterior de 2017.
- Test de regresión: gold h=2 regenerado igual, bit a bit, a lo que da `features_inicio` en memoria; mantener
  `test_no_fuga_por_perturbacion`.
- Regenerar `manifest_fase6.json` con las columnas nuevas y su procedencia.
- Gold h=4 se puede conservar solo para comparar; deja de ser entrada del modelo.

**Validación GX (`src/validation/expectations_gold.py`):**
- `propia_semanas_desde_ultimo_caso` entero entre 0 y 52, sin nulos.
- `propia_pendiente_4` finita.
- `propia_log_casos_temporada_anterior` ≥ 0, con nulos solo donde falte la historia.
- `ubigeo` de 6 dígitos como texto, como ya se exige.

**`config/config.yaml`:**
- `serving.horizontes: [2, 3, 4]`.
- `serving.variantes`: reemplazar `base_6_poblacion_2017` / `base_6` por una sola entrada para la configuración
  congelada (C3·E3·S4_s3). Ya no hay clasificador.

**Artefacto:**
- Un paquete con el booster multi-salida, las 3 α NB2 (una por horizonte), los 3 calibradores Platt, la regla de
  k, la lista de columnas y la huella de `CONFIGURACION_2026`, con un solo SHA-256.
- **Nuevo con S4_s3:** el artefacto declara que necesita los **casos de la semana de origen** para el
  `base_margin`. Sin ellos no hay predicción. Hoy `hist_lag_a` es ese mismo dato, pero el `base_margin` se pasa
  aparte del vector de variables.

**Serving (`src/serving/`):**
- `inferencia.vectores_desde_bd`: entregar las 9 columnas (incluidas las de B3, que necesitan la historia
  completa del distrito y la temporada anterior) y los casos del origen.
- `publicar.py`: ajuste final con etiquetas cerradas al último corte; calibradores desde las predicciones OOS
  del protocolo.
- BD: la «propuesta A» de `arquitectura_horizontes.md` (6 filas de `version_modelo` con el mismo artefacto).
- Interfaz y HU0008: mostrar los casos esperados como orden de magnitud o como apoyo de la alerta, no como
  estimación precisa. La razón RMSE de 2024 es 1,67 / 1,89 / 2,01. Las explicaciones por variable del modelo de
  conteo deben llevar esa advertencia.

### Limitaciones del encargo

- **Dependencia de 2017:** la selección de C3 descansa en buena parte en los inicios de 2017. Al quitar las 8
  primeras semanas de orígenes de 2017, las victorias de B3 pasan a empate.
- **Optimismo:** la selección de variables, hiperparámetros, α y formulación usó 2022–2023. Las cifras de esas
  temporadas son optimistas.
- **Conteo:** S4_s3 avisa antes a cambio de estimar peor la magnitud fuera de 2023.
- **`max_delta_step`** quedó en el tope del rango de búsqueda (fase 3); queda como trabajo futuro.
- **Pseudo-bloque 2020:** temporada tranquila al inicio de la pandemia. Su α OOS activó el respaldo, así que la
  4.2 no pudo distinguir entre las dos α.
- **Pocos brotes:** 2017 y 2023 concentran la mayor parte de los casos. 2026 dirá la magnitud real de la mejora.
- **Sin lenguaje causal:** las mejoras son asociaciones en las temporadas evaluadas.
- **Preregistro de la 2c escrito con la 2b a la vista.** La regla de la combinada (C y C3, con desempate por
  menos columnas) se commiteó (`d30c726`) antes de correr la 2c, pero después de ver los resultados de la 2b, con
  aprobación de Rosa. Con la regla original del preregistro de la fase 1 («una sola variante con las familias que
  ganan», sin C3), según el revisor, se habría adoptado C, que también gana a B. La elección de C3 depende de esa enmienda.
- **Márgenes chicos en decisiones:**
  - Fase 3, h3 · 2022: ΔF1 0,01450 frente a un umbral de 0,01481. Si lo hubiera superado, h3 habría dado «gana»
    y se habría adoptado la candidata.
  - Fase 4.3: la victoria de S4_s3 en h4 descansa en +0,053 de antelación en 2022, que son 2 inicios de 38.

### Auditoría independiente (`revisor-modelado`, 2026-10-27)

El revisor recalculó desde las predicciones guardadas y el texto del protocolo, sin leer el código de modelado
ni los JSON de métricas.

- **Coinciden:**
  - los 19 veredictos y las 4 adopciones (C3, base, α dentro de la muestra, S4_s3), con regla simétrica en las 19;
  - las medianas y rangos de la configuración final (45 cifras);
  - la tabla de la HU0007-4 (54 cifras), incluida la frontera 2023 · h4 (0,852; 0,846–0,857);
  - los 100 trials sin fallos y el trial 86 (0,209188);
  - que la candidata con α OOS es idéntica a la referencia en 2021 y 2022;
  - la ausencia de fuga en los 29 archivos de predicciones.
- **Orden de los commits:** cada preregistro es anterior a los resultados de su fase (`0fb31d2` → `092b7ba`,
  `68c3902` → `c4b331c`, `d30c726` → `b856c06`, `af507ae` → `cd5904a`, `f6325b0` → `260f026`).
  - `f6325b0` contiene el preregistro en código (`preregistro_fe.FASE4`). La sección del informe se escribió
    con los resultados, en `260f026`.
  - El orden de los commits no prueba cuándo se corrieron los experimentos.
- **Diferencias de lectura del protocolo, sin cambio de decisiones:**
  - El revisor no reproduce algunas cifras de antelación: la persistencia en h3/h4, S4_s3 en h3 (0,221 frente a
    0,211) y S4_s2 en 2024 · h4. Tampoco la log-loss de la candidata de la fase 3 en h3 · 2023.
  - Con los mismos archivos guardados, el protocolo congelado (`protocolo_arquitectura.evaluar`) da las cifras
    del informe. La candidata con semilla 17 da 0,2091878 desde su CSV. S4_s3 en h3 da 0,200 / 0,211 / 0,200 /
    0,211 / 0,211, con mediana 0,211.
  - La diferencia está en la implementación del revisor: calibración y conteo de inicios en casos de borde, a
    partir de un texto que no fija esos detalles. Los archivos son los mismos.
  - Con su lectura, la conclusión «en h=4 la final ya no pierde frente a la persistencia y no la supera» se
    mantiene (+0,000, IC −0,095 a 0,095). Pero C3·S4_s2 sí perdería en h4 (IC −0,179 a −0,011).
- **Correcciones aplicadas al informe a raíz de la auditoría:** la razón MAE de S4_s2 en 2022 (0,92–0,95, no
  0,93–0,95); la nota sobre el preregistro de la 2c escrito con la 2b a la vista; y los márgenes chicos de la
  fase 3 (h3 · 2022) y de la 4.3 (2 inicios de 38).
- **No verificable sin reentrenar:** SHAP, robustez, importancia fANOVA, medianas con 5 semillas de los trials
  91/75/82/62, reproducción 615/615 de la fase 0, α (no se guardan en los archivos de predicciones) y recall de
  brotes nuevos.

### Cierre técnico

- **Corrida de cierre:** notebooks 32, 33 y 34 de punta a punta, sin caché (`DENGUEKAY_FORZAR_REENTRENO=1`). El
  33 reutiliza el estudio de 100 trials guardado en SQLite (decisión de Rosa).
  - Tiempos: 22, 16 y 4 minutos.
  - Sin errores.
  - Todas las huellas de predicciones registradas en MLflow coinciden con las anteriores, así que no se
    registraron runs nuevos.
  - Ninguna métrica del JSON cambió; solo los tiempos de la fase 0.
- **Suite completa:** 389 tests, OK, sin omitidos (PostgreSQL arriba).

## Encargo complementario · clima para el conteo

### Preregistro (2026-10-27, antes de correr)

Fuente de verdad: `src/modeling/complemento_clima.py → PREREGISTRO_COMPLEMENTO`. Es una sola comparación, la
**20 del encargo**. El protocolo (`protocolo_arquitectura.py`) no cambia.

- **Motivo:** el punto débil de la configuración final es el conteo. Con ella ninguna celda cumple la regresión
  de la HU0007-4, y fuera de 2023 las razones son > 1. En la 2a, A3 (clima de gold) bajó las razones MAE y RMSE
  sobre la referencia B en 2022 y 2023, pero nunca se probó sobre la configuración final.
- **Referencia F∩A3:** la configuración final (C3, 9 columnas) reentrenada sin las 65 filas con nulos de
  arranque de A3 (primera semana de 2017). F completa se reporta solo como lectura.
- **Candidata F+A3:** C3 + `hum_rel_media_media5_h2` y `precip_total_mm_media5_h2` (11 columnas). Todo lo demás
  queda idéntico: E3 · S4_s3 · α dentro de la muestra · hiperparámetros heredados · Platt · p ≥ 0,50 · 5
  semillas.
- **Umbral de empate:** por métrica, horizonte y temporada, el mayor rango entre semillas de las dos variantes.
  Para las razones MAE y RMSE se calcula sobre la razón por semilla. El delta es la mediana de semillas de F+A3
  menos la de F∩A3. Las desigualdades son estrictas.
- **Condición 1, conteo:**
  - mejora en un horizonte si la razón MAE **y** la razón RMSE bajan más que su umbral en 2022 **y** en 2023;
  - empeora si la razón MAE **o** la razón RMSE suben más que su umbral en 2022 y en 2023;
  - se cumple si mejora en al menos un horizonte y no empeora en ninguno.
- **Condición 2, la alerta no pierde:** se aplica la regla simétrica del protocolo a F+A3 frente a F∩A3. Se
  cumple si ningún horizonte da «pierde»; gana, empate y compensa son aceptables.
- **Decisión:**
  - si se cumplen las dos condiciones, se adopta F+A3 y hay una configuración congelada nueva, con fecha igual
    a la del commit de la constante nueva;
  - si no, se queda F y el congelamiento sigue en 2026-10-27.
- **No decide:** 2024 (contraste), 2025 (sensibilidad de conteos), la robustez sin las 8 primeras semanas de
  2017, SHAP, la antelación, el recall de brotes nuevos y el conteo por fase de la curva.

### Resultados

Notebook `35_modelado_clima_conteo.ipynb`; cifras en `metricas/fe_hiperparametros.json → complemento_clima`;
predicciones en `models/experimentos/fe_hiperparametros/complemento_clima/`; figura
`shap_por_horizonte_F_A3.png`; MLflow `fe_hiperparametros_complemento_clima` (`6afc4549fd214a1497636319b3e6844c`).
Filas excluidas por A3: 65 orígenes, todos de la semana del 2017-02-05.

**Condición 1, conteo: se cumple en h=2, h=3 y h=4.** Delta de la mediana de la razón (F+A3 − F∩A3) [umbral de
empate]:

| h | Razón MAE 2022 | Razón MAE 2023 | Razón RMSE 2022 | Razón RMSE 2023 |
|---|---|---|---|---|
| 2 | −0,082 [0,016] | −0,066 [0,011] | −0,162 [0,032] | −0,123 [0,020] |
| 3 | −0,134 [0,029] | −0,064 [0,006] | −0,300 [0,051] | −0,094 [0,011] |
| 4 | −0,198 [0,026] | −0,057 [0,011] | −0,464 [0,041] | −0,072 [0,013] |

Ninguna razón sube en ningún horizonte.

**Condición 2, la alerta no pierde: se cumple** (empate en h=2, h=3 y h=4). La razón MAE marca un veto a favor
de F+A3: la guarda mejora más que el rango entre semillas.

**Decisión: se adopta F+A3.** La configuración congelada nueva es la V2 de `configuracion_final.py`
(`CONFIGURACION_2026`).

#### El costo en la alerta, que la regla no mide

La regla pide que la alerta empeore en las dos temporadas para declarar «pierde». En 2022 empeora; en 2023 sube
un poco (F1 supera su rango hacia arriba en h2 y h4, por menos de 0,01):

- **F1 a 0,50, Δ 2022 / 2023:** h2 +0,007 / +0,006; h3 −0,048 / +0,002; h4 **−0,192** / +0,009. En 2022 · h4 la
  caída supera el umbral de empate (0,060).
- **Recall 2022:** h4 0,376 → **0,202**; h3 0,531 → 0,462.
- **AUPRC 2022:** −0,006 / −0,008 / −0,009. **Brier 2022:** +0,001 / +0,002 / +0,005. Ninguna supera su rango en
  las dos temporadas.
- **Antelación frente a F∩A3** (semilla 17, IC pareado):
  - h2: +0,021 (IC −0,021 a 0,063);
  - h3: −0,053 (IC −0,116 a 0,000), con el extremo superior en 0;
  - h4: −0,032 (IC −0,074 a 0,011).
  - En 2022 · h4, la mediana de la antelación pasa de 0,053 a 0.
- **Antelación sobre inicios limpios 2022–2023** (mediana de semillas):

  | h | F∩A3 | F+A3 | F completa |
  |---|---|---|---|
  | 2 | 0,116 | 0,147 | 0,137 |
  | 3 | 0,200 | 0,147 | 0,211 |
  | 4 | 0,221 | 0,189 | 0,232 |

- **Frente a la persistencia** (semilla 17), F+A3 da h2 +0,021 (IC −0,042 a 0,074), h3 +0,011 (IC −0,053 a
  0,074) y h4 −0,021 (IC −0,105 a 0,063).
  - En h4 sigue sin perder (el IC incluye 0), pero la diferencia pasa de positiva a negativa: 2022 −0,263, 2023
    +0,140.
  - Parte de lo que la 4.3 ganó en antelación con S4_s3 se devuelve aquí.
- **Recall de brotes nuevos** (2 primeras semanas), 2022 / 2023: h2 0,061 → 0,102 / 0,116 → 0,151; h3 0,061 →
  0,041 / 0,163 → 0,128; h4 0,041 → 0 / 0,163 → 0,151.

En resumen: F+A3 estima mucho mejor la magnitud, pero alerta menos en 2022 · h4. La regla preregistrada da más
peso al conteo y acepta ese costo porque no se repite en 2023.

#### Auditoría del complemento (`revisor-modelado`, 2026-10-27)

- **Coinciden:**
  - la decisión: las dos condiciones se cumplen en h2, h3 y h4;
  - los 12 deltas del conteo, que superan su umbral por un factor de 4 a 12;
  - la condición 2 (empate en los tres horizontes);
  - la tabla de métricas (F1, razones, MAE y RMSE en casos);
  - el recall y el recall de brotes nuevos;
  - la HU0007-4: en 2023 · h3 y h4, F+A3 cumple en las 5 semillas, no en la frontera;
  - la ausencia de fuga;
  - el orden de los commits (preregistro `e5d90be` antes que los resultados `424a148`).
- **Diferencias de lectura, las mismas del encargo principal:** antelación en h3 (1 inicio de 95) y frente a la
  persistencia en h4 (con la lectura del revisor, −0,042, IC −0,137 a 0,053). No cambian ninguna conclusión.
- **Márgenes y fragilidades:**
  - Antelación de F+A3 frente a F∩A3 en h3: el extremo superior del IC es exactamente 0,000. Con «≤ 0» habría
    «empeora en antelación» y el veredicto sería «compensa» (por el veto de la razón MAE), no «pierde». La
    condición 2 se cumple igual.
  - El costo en 2022 · h4 depende del recorte del logit en Platt, un detalle que el texto del protocolo no fija
    (el código usa 1e-6). El 12 % de las probabilidades sin calibrar de F+A3 son < 1e-6. Con un recorte de 1e-12,
    F1 2022 · h4 baja a 0,254 en lugar de 0,333. El veredicto no cambia, pero **el costo en la alerta podría ser
    mayor que el reportado**.
- **No verificable sin reentrenar:** robustez, SHAP y conteo por fase.

#### Métricas (mediana de semillas, F∩A3 → F+A3)

| Temporada | h | F1 | Razón MAE | Razón RMSE | MAE (casos) | RMSE (casos) |
|---|---|---|---|---|---|---|
| 2022 | 2 | 0,702 → 0,709 | 1,000 → 0,919 | 1,099 → 0,938 | 1,96 → 1,80 | 6,64 → 5,66 |
| 2022 | 3 | 0,642 → 0,594 | 1,017 → 0,883 | 1,221 → 0,922 | 2,43 → 2,11 | 8,95 → 6,75 |
| 2022 | 4 | 0,525 → 0,333 | 1,036 → 0,838 | 1,369 → 0,905 | 2,95 → 2,39 | 11,68 → 7,73 |
| 2023 | 2 | 0,852 → 0,858 | 0,884 → 0,818 | 0,991 → 0,869 | 9,58 → 8,87 | 49,05 → 42,97 |
| 2023 | 3 | 0,826 → 0,828 | 0,811 → 0,747 | 0,912 → 0,818 | 11,88 → 10,94 | 61,17 → 54,85 |
| 2023 | 4 | 0,802 → 0,811 | 0,765 → 0,708 | 0,851 → 0,779 | 13,53 → 12,52 | 68,26 → 62,47 |
| 2024 (contraste) | 2 | 0,796 → 0,803 | 1,343 → 0,937 | 1,691 → 0,945 | 6,66 → 4,64 | 26,65 → 14,90 |
| 2024 (contraste) | 3 | 0,778 → 0,781 | 1,508 → 0,938 | 1,874 → 0,981 | 9,62 → 5,98 | 38,68 → 20,26 |
| 2024 (contraste) | 4 | 0,744 → 0,749 | 1,617 → 0,951 | 2,007 → 1,011 | 12,69 → 7,46 | 51,08 → 25,74 |

P, R, AUPRC, Brier y los rangos entre semillas de las tres variantes (F, F∩A3 y F+A3) están en el JSON. F
completa y F∩A3 difieren muy poco: solo cambian las 65 filas.

#### Conteo por fase de la curva regional (razón MAE, F∩A3 → F+A3)

- **Pico:**
  - 2022: h2 1,20 → 1,02; h3 1,41 → 1,08; h4 1,60 → 1,08;
  - 2023: 1,01 → 0,89; 1,02 → 0,91; 1,05 → 0,95;
  - 2024: 1,80 → 1,05; 1,95 → 1,09; 2,00 → 1,14.
- **Bajada 2024:** 1,41 → 0,84; 1,81 → 0,86; 2,22 → 0,94.
- **Subida 2022:** 1,14 → 1,07; 1,14 → 1,06; 1,07 → 1,04.
- **Valle:** sin cambios relevantes (2023 · h2 sube de 1,03 a 1,05).
- **Lectura:** el clima ayuda sobre todo en el pico y la bajada, que es donde la configuración final
  sobreestimaba o subestimaba la magnitud. Es una asociación, no una prueba de efecto del clima.

#### HU0007-4 (F → F+A3)

- **Clasificación:** las mismas 4 celdas (2023 · h2 y 2024 h2/h3/h4).
- **Regresión:** F+A3 cumple en **2023 · h3** (0,747 / 0,818) y **2023 · h4** (0,708 / 0,779). La frontera
  2023 · h4 (F: 0,764 / 0,852) queda resuelta a favor.
  - 2023 · h2 sigue sin cumplir: la razón RMSE es 0,869.
  - 2022 y 2024 no cumplen.
- **Contraste 2024:** las razones quedan cerca de 1 (MAE 0,94–0,95; RMSE 0,95–1,01), frente a 1,35–1,62 y
  1,67–2,01 con F. Ya no son mucho peores que la persistencia, pero tampoco mejores.

#### Robustez (solo lectura), sin las 8 primeras semanas de orígenes de 2017

- Los 12 deltas de las razones siguen siendo negativos, aunque más chicos. Por ejemplo, h4 2022 razón RMSE
  −0,154 frente a −0,464.
- La condición 1 se sigue cumpliendo en h2, h3 y h4.

#### SHAP por horizonte de F+A3 (semilla 17)

- En S4_s3 el margen de persistencia es `base_margin`, así que SHAP describe la desviación respecto de la
  persistencia.
- La precipitación media de 5 semanas está entre las 3–4 variables con más peso en los tres bloques (0,18–0,35).
- La humedad pesa menos (0,04–0,16) y crece con h.
- `propia_semanas_desde_ultimo_caso` sigue primera.

#### Disponibilidad del clima (supuesto y limitación)

- `src/ingestion/fetch_openmeteo.py` descarga clima **diario histórico** de la *archive API* de Open-Meteo, con un
  rango fijo (`START`/`END` = 2017-01-01 a 2025-12-31).
- `src/processing/agregacion_semanal.py` lo agrega a semana MMWR (domingo a sábado).
- El manifest de gold declara el supuesto: «Casos y clima semanal suponen disponibilidad al cierre de su semana;
  latencia no verificada».
- A3 usa la semana o, la que cierra en el origen. En producción hace falta el clima diario de esa semana el día
  en que se emite el pronóstico.
- **No se verificó** (sin llamadas de red) si la *archive API* ya tiene esos días al cierre de la semana o con
  cuánto rezago llegan. Es una *hipótesis* que pueda haber unos días de rezago.
- Si lo hubiera, habría dos opciones, y cualquiera de las dos sería un encargo nuevo con preregistro:
  - correr la ventana una semana (o − 5..o − 1), lo que cambia la variable;
  - usar otra fuente para los últimos días, lo que cambia la distribución de los datos.
- Hoy no existe una ingesta periódica: el rango de descarga es fijo.

### Configuración congelada nueva (V2)

| Pieza | Valor |
|---|---|
| Matriz | C3 + A3 = `base_6` + B3 + `hum_rel_media_media5_h2` + `precip_total_mm_media5_h2` (11 columnas; diccionario actualizado) |
| Filas | Sin los 65 orígenes con nulos de arranque de A3 (primera semana de 2017) |
| Resto | Igual que la V1: E3 · S4_s3 · α dentro de la muestra · hiperparámetros heredados · Platt · p ≥ 0,50 · semilla 17 |
| Fecha de congelamiento | 2026-10-27, commit que introduce la V2 en `configuracion_final.py` |
| Huella (configuración + módulos) | `c36d7a80d1896a203874bf271bd78f1078850e1faa381e2b17e9ba04b07d5569` |
| Histórica | V1 (`CONFIGURACION_2026_V1`, `d6bd0be`, huella `88ed2a43…`, sin cambios) |

- `tests/test_configuracion_final.py` reproduce con la semilla 17 las predicciones guardadas de las dos versiones.
- En MLflow, el run del complemento (`6afc4549…`) lleva `configuracion_congelada_2026 = vigente`. El de la fase 4
  (`cda23d28…`) lleva `reemplazada`.

### Cambios pendientes por la V2 (sin implementar)

- **Gold h=2 y GX:** A3 ya existe en gold h=2 (`hum_rel_media_media5_h2`, `precip_total_mm_media5_h2`) y en sus
  expectativas GX (humedad entre 0 y 100, entre otras). No cambian. Siguen pendientes las 3 columnas de B3.
- **`features.py` y notebook 22:** nada nuevo por A3. Lo pendiente es lo de B3.
- **`config/config.yaml`:** la variante única pasa a ser la V2 (11 columnas). Los horizontes no cambian
  ([2, 3, 4]).
- **Artefacto:** la lista de columnas pasa a 11 y la huella a la de la V2. El resto queda igual (booster
  multi-salida, 3 α, 3 Platt, regla de k, casos del origen para el `base_margin`).
- **`inferencia.vectores_desde_bd`:** ahora también necesita el **clima de las semanas o − 4..o** de cada
  distrito. Sin él no hay predicción; no se imputa.
- **Ingesta meteo:** hace falta una ingesta periódica (hoy el rango es fijo hasta 2025-12-31) y verificar el
  rezago de la *archive API* (ver la limitación de arriba).
- **Interfaz y HU0008:** la advertencia sobre el conteo se suaviza. En 2024 las razones quedan cerca de 1, no
  por debajo; los casos esperados siguen siendo orientativos. Además, hay que advertir que en 2022 la alerta en
  h4 fue más tardía.
