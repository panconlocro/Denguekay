# Encargo: estudio 06 · mejorar el modelo sobre la V2

## Paso previo

- Crea la rama `exp/model-improvement` desde `develop` actualizado (`git switch develop`, `git pull`,
  `git switch -c exp/model-improvement`). Este plan es el primer commit del estudio
  (`docs(research): add model improvement study plan`).
- Lee `CLAUDE.md`, `docs/architecture.md`, `models/registry/v2/ficha.md` y
  `research/05_fe_hyperparameters/docs/fe_hiperparametros.md` (Fase 5 y Encargo complementario).

## Contexto

La V2 (`CONFIG_2026`: C3+A3 · E3 · S4_s3, Platt, p ≥ 0,50) es la configuración vigente y la que se sirve, y no
cumple la HU0007-4. Según los informes (verifícalo, no lo des por cierto):

- Clasificación: cumple en 4 de 9 celdas. Falla el recall: 2022 · h4 en 0,202 (el 0,40 era de la V1), y
  0,00–0,15 en las 2 primeras semanas de brotes nuevos (verificado en la fase 0).
- Regresión: cumple en 2 de 9 celdas, 2023 · h3 (0,747 / 0,818) y 2023 · h4 (0,708 / 0,779); «ninguna» era la
  V1. En el resto pierde o empata con la persistencia, sobre todo en el pico.
- La caída de F1 en 2022 · h4 con A3 es de calibración: la AUPRC casi no cambia, el Platt se ajusta solo con
  2021 y su Brier calibrado es peor que el sin calibrar.
- Las ganancias de B3 dependen de los inicios de 2017. 2022–2023 ya se usaron en 19 comparaciones.

**Hipótesis de trabajo:** el cuello de botella es la poca historia (pocos brotes para entrenar, calibrar y
evaluar), no la arquitectura. `data/silver/epi_piura_semanal.csv` tiene casos por distrito de Piura desde 2000,
pero el modelo entrena desde 2017. El clima (`denguekay.data.ingestion.openmeteo`, `START = "2017-01-01"`) y el
socio empiezan en 2017.

## Objetivo

Encontrar una V3 que supere a la V2 con una regla preregistrada y una evaluación menos optimista. Si nada la
supera, se queda la V2 y se documenta por qué. Ese resultado también es válido.

**Fuera de alcance:** serving, API, BD y frontend. No se escribe en `data/`. No se cambian el umbral
p ≥ 0,50 ni la etiqueta de brote (canal endémico).

## Cómo trabajar

- Fase por fase. Antes de cada fase muestra los archivos que vas a crear o modificar. Al cerrarla, da el
  resumen como texto en el chat y **detente** hasta que Rosa confirme.
- Respeta `CLAUDE.md`:
  - `data/` es de solo lectura;
  - `ubigeo` es string de 6 dígitos;
  - las rutas salen de `denguekay.config.paths`;
  - el código va en inglés y la documentación en español;
  - CRLF y UTF-8.
- El estudio vive en `research/06_model_improvement/` (`README.md`, `notebooks/`, `code/`, `tests/`, `docs/`).
  Importa `denguekay`; el producto nunca importa `research/`.
- Todo cambio de datos (por ejemplo, clima anterior a 2017) se **propone** como cambio al pipeline
  (`openmeteo.py` y notebooks 02–09) y lo corre el equipo. Mientras tanto, todo se trabaja en memoria.
- Variables nuevas: en memoria, con funciones de `denguekay.features`, y con un test de no fuga por
  perturbación.
- Cada fase se registra en MLflow con `denguekay.model.tracking`. Usa 5 semillas (17/29/41/53/67), mediana y
  rango.
- **Preregistro antes de correr cada fase:** candidatas, comparaciones, regla de decisión y qué temporadas
  deciden, en código y en commit, antes de ver resultados. No se amplía sin aprobación de Rosa.
- Honestidad: no uses lenguaje causal. Reporta cada métrica con su número de positivos. Las diferencias de una
  celda o de 2 inicios no deciden nada.

## Decisiones de Rosa (2026-11-02)

1. **Los ceros son reales.** `epi_piura_semanal.csv` viene directamente del MINSA: un 0 (o una semana sin
   registro de un distrito) significa que esa semana hubo 0 casos. No es subregistro ni falta de cobertura. No
   se vuelve a cuestionar ni se trata como dato faltante, tampoco en 2000–2016.
2. **El clima se extiende hacia atrás.** Según su documentación, el Historical Weather API de Open-Meteo
   (`/v1/archive`, el que ya usa `openmeteo.py`) tiene ERA5 desde 1940 y ERA5-Land desde 1950
   (https://open-meteo.com/en/docs/historical-weather-api). Alcanza para 2000–2016. Lo descarga el equipo con el
   pipeline; tú propones el cambio (ver la fase 1b).
3. **La V3 pasa por todas las pruebas y experimentos necesarios** antes de congelarse (ver la fase 7). Si se
   congela, el test independiente de 2026 (`EVALUATION_2026`) se aplica a la V3 desde su commit de
   congelamiento.

## Decisiones de Rosa (2026-11-03, al cerrar la fase 0)

1. **Protocolo nuevo aprobado:** bloques por temporada con ventana creciente desde 2005; Platt de cada bloque con
   todas las temporadas cerradas anteriores; deciden 2010, 2015, 2016, 2022 y 2023 (mejora en al menos 4 de 5 y
   ninguna en contra); 2024 queda como contraste. El bloque 2010 se reporta aparte porque entrena con pocos
   brotes. El umbral de «en contra» se define en el preregistro de la fase 1.
2. **Recorte del logit** como variante de la fase 2 (ver la fase 2).
3. **Corrección pendiente del pipeline:** `epi_piura_semanal.csv` tiene una semana 53 en 2009, que en MMWR no
   existe (2009 tiene 52 semanas). En Piura son 3 filas con 4 casos (distritos 200601, 200701 y 200705), que la
   historia larga deja fuera. Queda anotada; no se toca en este estudio.

## Decisiones de Rosa (2026-11-04, clima y precipitación)

1. **En la V3, la lluvia es solo CHIRPS v3**, para entrenar y para la actualización semanal (reemplazo, no
   agregado). Antes de 2017 Open-Meteo no tiene lluvia útil (ERA5 a 0,25° deja iguales a los distritos vecinos y
   ERA5-Land no trae precipitación), y como se entrena desde 2005, la lluvia de Open-Meteo solo cubriría 2017–2025.
   La lluvia «Best match» de Open-Meteo queda solo para la V2.
2. **Orden de los pasos de clima, cada uno con su propio preregistro commiteado antes de correr** (no se adelantan
   ni se mezclan):
   a) 1b′: L + 5a + humedad de ERA5-Land;
   b) la variante que agrega la lluvia de CHIRPS v3 sobre la base que gane en (a);
   c) repetir el Niño 1+2 solo si la base cambió en (a) o en (b).
3. **La fase 4 cerrada el 2026-11-04 es la primera medición del Niño 1+2** (sobre L + 5a; empate, no se adopta).
4. **Disponibilidad de CHIRPS:** cada semana lleva una `fecha_disponible` según el calendario del preliminar
   (péntadas publicadas los días 2, 7, 12, 17, 22 y 27) y una guarda tipo G21: ningún origen usa una semana publicada
   después de su cierre. Sin esa guarda, la variante (b) no se preregistra.
5. **Posible desfase entrenamiento–app:** el entrenamiento usa el final `sat` y la app el preliminar `sat`, que usa
   menos estaciones; pueden diferir.

## Decisiones de Rosa (2026-11-06, lluvia de CHIRPS v3)

1. **Fuente única de lluvia de la V3: CHIRPS v3 diario `sat`.** Histórico con la versión final desde Google Earth
   Engine (`UCSB-CHC/CHIRPS/V3/DAILY_SAT`, proyecto de Google Cloud `denguekay`, uso no comercial); las semanas que aún
   no tienen final usan el preliminar `sat` del CHC (`prelim/sat/AAAA/chirps-v3.0.prelim.AAAA.MM.DD.tif`), que se
   reemplaza por el final cuando se publica. Ninguna semana mezcla versiones.
2. **Lluvia por distrito como media del polígono distrital ponderada por área** (límites del IGN publicados en HDX,
   COD-AB, licencia CC BY-IGO), no el píxel del centroide.
3. **No se une CHIRPS con la lluvia «Best match» de Open-Meteo.** En enero a abril de 2017, 2019 y 2023 (715 pares
   distrito-mes, comparación fuera del estudio), Open-Meteo da en promedio un 65 % más (de 1,08 a 3,43 veces según el
   mes), con correlación 0,82; unirlas metería un salto en 2017.
4. **Hechos al 2026-11-06:** el preliminar llega al 2026-10-31 (publicado el 2 de noviembre; TIF globales de unos
   11 MB, no COG) y existe desde 2025; la final en el CHC y en Earth Engine llega al 2026-09-30 (publicada el 15 de
   octubre); el CHC respondió 429 tras unos 11 archivos pedidos con 1,5 a 3 s de pausa.
5. **Variantes del paso b) de clima** (cada una frente a L + 5a; después, el paso c, Niño 1+2, solo si la base
   cambia):
   - **b1** = L + 5a + lluvia CHIRPS como media de 5 semanas hasta el origen, con la misma definición que la A3 de la
     V2 (`precip_total_mm_media5_h2`);
   - **b2** = L + 5a + H (humedad ERA5-Land, `hum_rel_media_media5_h2`) + lluvia CHIRPS: la A3 de la V2 con fuentes
     largas.
6. **Pasos internos del paso b) de clima** (no son fases nuevas del estudio; Claude se detiene al final de cada uno):
   - b-I: polígonos distritales y verificación de los 65 distritos;
   - b-II: `--dry-run` de `earthengine-api`;
   - b-III: registro no comercial y autenticación (los hace Rosa);
   - b-IV: ingesta de Earth Engine y guarda de método (media local por polígono frente a la de Earth Engine en los
     24 días del final ya bajados);
   - b-V: preliminar del CHC (un archivo por petición, pausado, se detiene ante el primer 429);
   - b-VI: medición preliminar frente a final (descriptiva), en enero a abril de 2025 y de 2026, sobre la media de
     5 semanas de b1;
   - b-VII: preregistro de b1 y b2.
7. **`data/` sigue siendo de solo lectura:** cada paso que escriba en `data/` necesita el OK explícito y acotado de
   Rosa.

## Fase 0 · Diagnóstico y techo (solo lectura, sin entrenar variantes)

- Con las predicciones OOS guardadas de la V2, separa el error por estado:
  - inicio limpio;
  - brote en curso;
  - bajada;
  - valle.

  Hazlo por temporada y por horizonte. ¿Dónde se concentran los falsos negativos?
- Calibración:
  - curva de confiabilidad por temporada;
  - cuántas semanas brote caen en [0,40, 0,50);
  - techo diagnóstico de F1 con calibración perfecta por temporada (no decide nada).
- Persistencia: ¿en qué fracción de las semanas brote ya acierta? Con eso se ve cuánto margen real queda para
  el modelo.
- Historia previa a 2017 (los ceros son reales; un distrito sin registro en una semana tiene 0 casos):
  - casos por año;
  - semanas brote según la regla de gold, extendida con `umbral_brote_futuro` y sus 5 años previos (la etiqueta
    existe desde ~2005);
  - inicios limpios por temporada.

**Entregable:** tablas en el chat y una propuesta del protocolo de evaluación nuevo de la fase 1. Detente.

## Fase 1 · Más historia (palanca principal)

- **1a, solo epidemiología:** entrena E3·S4_s3 con `base_6` + B3 (sin A3) desde la primera temporada con
  etiqueta válida: la que tiene 5 años previos para la regla de brote (2005, si la historia empieza en 2000). Compárala con la misma matriz entrenada
  desde 2017.
- **Protocolo nuevo, que se preregistra en esta fase:**
  - bloques temporales por temporada;
  - las **temporadas que deciden** pasan a ser más (por ejemplo 2010, 2015, 2016, 2021, 2022 y 2023, según la
    fase 0), en vez de solo 2022–2023;
  - 2024 queda como contraste.

  Así se reduce la dependencia de 2017 y el optimismo acumulado.
- **Platt con más temporadas:** el calibrador de cada bloque se ajusta con todas las temporadas cerradas
  anteriores, no solo desde 2021.
- **1b, clima 2000–2016:**
  - Propón el cambio a `openmeteo.py` (rango de fechas parametrizable) y a los notebooks 02–03. Lo corre el
    equipo.
  - **Consistencia:** `openmeteo.py` no fija el parámetro `models`, así que el API elige el modelo
    automáticamente y puede no ser el mismo en todos los años. Antes de usar el clima largo, compara en
    2017–2025 lo ya descargado con ERA5 (o ERA5-Land) fijado explícitamente. Reporta las diferencias por
    variable y propón si conviene descargar 2000–2025 con un solo modelo. Ese cambio movería gold y la paridad
    de la V2, así que lo decide Rosa.
  - Con el clima disponible, repite 1a con A3. Mientras no esté, avanza con las fases 2 y 3 sobre la variante
    epidemiológica y retoma 1b cuando el equipo lo entregue.
  - Socio anterior a 2017: se usa el valor de 2017 del distrito (es casi fijo). Decláralo como supuesto.

**Entregable:** veredictos con la regla preregistrada, recall en inicios limpios y la HU0007-4 por celda.
Detente.

## Fase 2 · Calibración

Sobre la mejor matriz de la fase 1, con p ≥ 0,50 fijo:

- Platt por horizonte frente a Platt agrupado entre horizontes. El agrupado tiene más positivos.
- Calibración beta (3 parámetros).
- Isotónica, solo si hay suficientes positivos. La S5 del estudio 04 ya la probó en E1 con pocos datos: cita
  ese antecedente.
- Recorte del logit como **variante**: 1e-6 (el actual) frente a uno menor, fijado en el preregistro. La
  auditoría del estudio 05 mostró que cambia 2022 · h4 y la fase 0, que 1e-6 aplasta entre el 1 % y el 8 % de
  las probabilidades sin calibrar (decisión de Rosa, 2026-11-03).
- Guardas: Brier y log-loss calibrados no deben empeorar frente a los sin calibrar.

Detente.

## Fase 3 · Inicios de brote

El recall en inicios es casi nulo. Prueba, una a la vez:

- **Pesos de muestra:** más peso a las semanas objetivo que son inicio, o peso por temporada para que 2017 y
  2023 no dominen, con el factor fijado a priori.
- **Dos regímenes:** un modelo para distritos sin brote al origen (que solo predice inicios) y otro para brote
  en curso. Se combinan por el estado al origen, que es conocido al emitir y no tiene fuga.
- **Re-ensayo de B1/B2** (contexto espacial y distritos núcleo) **solo en el modelo de inicios**: en el modelo
  único no agregaron sobre B3, pero la fase 1 del estudio 05 los marcó como observados en los inicios.

Detente.

## Fase 4 · Señal regional de El Niño (solo si la fase 1 deja margen)

- *Hipótesis*, no verificada: un índice costero de El Niño (por ejemplo, el ICEN de ENFEN o la anomalía
  Niño 1+2) podría aportar antelación regional en Piura.
- Antes de proponer nada, **verifica la fuente, la frecuencia y el retraso de publicación**, y pásale el enlace
  a Rosa. Si no se puede verificar, no se usa.
- Solo valores publicados al origen. Entraría como una ingesta nueva al pipeline, que propones tú y corre el
  equipo.

Detente.

## Fase 5 · Conteo

- **Mezcla con la persistencia:** μ = w·modelo + (1 − w)·persistencia por horizonte, con w ajustado solo en el
  entrenamiento de cada bloque. Es el objetivo directo de la razón ≤ 0,85.
- Rango ampliado de `max_delta_step`: en el estudio 05 quedó en el tope (2,0). Va con preregistro aparte.
- Reporta el conteo por fase de la curva (valle, subida, pico, bajada), siempre MAE y RMSE juntos.

Detente.

## Fase 6 · Línea base de otra familia (lectura, no decide)

Una binomial negativa GLM con rezagos (casos y clima) y un LightGBM con la misma matriz y el mismo protocolo.
Sirven para saber si XGBoost es el límite o si lo son los datos.

## Decisiones de Rosa (2026-11-08, temporada 2026)

1. **Lluvia de la V3: solo CHIRPS v3 `sat`; el preliminar y el final se bajan por FTP** (`ftp.chc.ucsb.edu`,
   `/products/CHIRPS/v3.0/daily/{prelim,final}/sat/AAAA/`). La prueba del 2026-11-08 bajó los 31 días del preliminar de
   octubre de 2026 en 108 s, sin errores, con la grilla igual al final y el sha256 del 2026-10-01 idéntico al de b-V.
   Se descarta la familia Open-Meteo (OM, OM + Niño, R + 5a y d1-2017).
2. **La temporada 2026 se usa para comparar modelos.** La temporada 2026 (semana 35 de 2025 a semana 34 de 2026) y las
   semanas posteriores disponibles son temporadas de evaluación. Con eso, **`EVALUATION_2026` deja de ser
   independiente para la V3**: la prueba independiente de la V3 pasa a ser lo publicado después de su congelamiento (el
   resto de la temporada 2026-2027). Esto reemplaza, para la V3, lo dicho en el punto 3 de «Decisiones de Rosa
   (2026-11-02)» y en la fase 7.
3. **Regla de decisión** (`SEASON_2026` en `code/preregistration.py`): el Brier como métrica principal sobre 2010,
   2015, 2016, 2022, 2023 y 2026; gana con >= 5 de 6 a favor y 0 en contra; vetos con >= 4 de 6; adopción sin «pierde»
   ni «compensa» en el Brier, la F1 ni la razón MAE; cruce entre adoptadas con empate a favor de la más simple. Se fijó
   después de ver los pasos b y d.
4. **Bloques:** `temporada_2026` se entrena hasta la temporada 2025; `posterior_2026` (semana 35 de 2026 en adelante)
   hasta la temporada 2026 y solo se reporta. Las 2 últimas semanas publicadas de la Sala son provisionales: no entran
   en las métricas y se reportan aparte.
5. **Validación dejando una temporada fuera** (2010, 2015, 2016, 2017, 2022, 2023, 2024 y 2026): lectura optimista
   (usa el futuro) que solo compara variantes entre sí y nunca se reporta como rendimiento esperado.
6. **Orden:** primero los datos (Sala 2026, ERA5-Land 2026, CHIRPS por FTP y b-VI) con una excepción de escritura
   acotada; después del OK de Rosa, el preregistro completo y la evaluación.

## Decisiones de Rosa (2026-11-08, después de la matriz de clima)

1. **La base de la V3 es L + 5a + d3** (las 4 ventanas de temperatura de ERA5-Land: semana del origen y medias de
   o−1..o−4, o−5..o−8 y o−9..o−12) **y b3 queda como retadora.** **No sale de la regla `SEASON_2026`**: d3 gana el
   Brier en un solo horizonte (h2) y es peor que L + 5a en 2016 en los tres (+0,4 %, +0,9 % y +2,3 %). Es una
   decisión con contexto, **tomada después de ver los resultados de la matriz y usando 2026 para elegir**.
   Justificación de Rosa:
   - el objetivo operativo actual es anticipar brotes en años de Niño (el ENFEN prevé un Niño Costero extraordinario
     de setiembre de 2026 a mayo de 2027; fuente citada por Rosa);
   - en los periodos de Niño (2017, 2026 y `posterior_2026`), d3 baja el Brier frente a L + 5a un 5,97 % de media,
     frente al 2,00 % de b3; b3 es peor que L + 5a en 2017 en los tres horizontes;
   - en años normales d3 cuesta hasta 2–3 % de Brier frente a b3; en las 27 celdas, d3 −2,34 % y b3 −1,90 % frente a
     L + 5a;
   - mejora 21 de 24 celdas LOSO; es la mejor en F1 y en conteo en 2026 y en `posterior_2026`;
   - es más simple: 4 columnas de clima y una sola fuente (ERA5-Land), sin CHIRPS ni NOAA en la operación semanal.
2. **Se congelan las dos, d3 y b3,** y se evalúan de forma prospectiva en la temporada 2026-2027.
3. **Siguiente:** diagnóstico de solo lectura frente a la persistencia (d3, b3 y L + 5a); después del OK de Rosa, el
   preregistro del ajuste de hiperparámetros sobre L + 5a + d3.

Diferencia de Brier en % (variante / referencia − 1; negativo = mejor), de `metricas/matriz_clima.json`
(mediana de 5 semillas):

| Bloque | h | d3 vs L + 5a | b3 vs L + 5a | d3 vs b3 |
|---|---|---|---|---|
| 2010 | 2 / 3 / 4 | −0,84 / −0,66 / −0,74 | −1,09 / −1,97 / −2,76 | +0,25 / +1,34 / +2,08 |
| 2015 | 2 / 3 / 4 | −0,55 / −0,66 / −1,74 | −0,53 / −0,64 / −2,68 | −0,02 / −0,03 / +0,97 |
| 2016 | 2 / 3 / 4 | +0,42 / +0,94 / +2,32 | −0,98 / −1,59 / −0,51 | +1,42 / +2,57 / +2,85 |
| 2017 (Niño) | 2 / 3 / 4 | −2,49 / −2,30 / −2,34 | +1,16 / +0,76 / +1,03 | −3,60 / −3,04 / −3,34 |
| 2022 | 2 / 3 / 4 | −0,52 / −0,72 / −0,11 | −1,31 / −1,24 / −0,12 | +0,80 / +0,52 / +0,01 |
| 2023 | 2 / 3 / 4 | −0,56 / −1,10 / −1,80 | −1,92 / −2,62 / −3,24 | +1,39 / +1,56 / +1,48 |
| 2024 | 2 / 3 / 4 | −0,65 / −0,93 / −1,47 | −1,91 / −3,52 / −4,62 | +1,29 / +2,68 / +3,31 |
| 2026 (Niño) | 2 / 3 / 4 | −4,44 / −7,22 / −6,90 | −3,34 / −4,90 / −3,83 | −1,13 / −2,44 / −3,19 |
| posterior_2026 (Niño) | 2 / 3 / 4 | −8,41 / −9,37 / −10,28 | −4,43 / −2,69 / −1,74 | −4,16 / −6,87 / −8,70 |

| Promedio de celdas | Celdas | d3 vs L + 5a | b3 vs L + 5a | d3 vs b3 |
|---|---|---|---|---|
| Decisivas (2010, 2015, 2016, 2022, 2023, 2026) | 18 | −1,38 | −1,96 | +0,58 |
| Años de Niño (2017, 2026, `posterior_2026`) | 9 | −5,97 | −2,00 | −4,05 |
| Años normales (el resto) | 18 | −0,52 | −1,85 | +1,36 |
| Todas | 27 | −2,34 | −1,90 | −0,44 |

## Fase 7 · Síntesis, pruebas y congelamiento

- Configuración elegida frente a la V2, con el protocolo nuevo, y la HU0007-4 por celda.
- **Pruebas obligatorias de la V3 antes de congelarla:**
  - 5 semillas con mediana y rango, y robustez (sin las 8 primeras semanas de 2017, y sin la temporada de mayor
    peso en el entrenamiento nuevo);
  - test de no fuga por perturbación de cada variable nueva;
  - la configuración en `denguekay.model.frozen_configs` y en el registro, con su test de configuración y su
    huella de comportamiento;
  - suite completa (`python -m unittest discover -s tests`) y guardas de equivalencia en verde, sin regenerar la
    línea base;
  - comparación contra la persistencia (antelación con IC sobre los inicios limpios).
- Auditoría con el subagente `revisor-modelado` (pega su tabla).
- Si la nueva gana:
  - se propone la ficha `models/registry/v3/`, la entrada del CHANGELOG, el tag `model/v3` y
    `EVALUATION_2026` aplicada a la V3 desde su commit de congelamiento;
  - se proponen los cambios a `denguekay/features/gold.py`, que regenera el equipo.
- Se cierra con el tag `study/model-improvement` y la fila del estudio en `research/README.md`.
