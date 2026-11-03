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

- Clasificación: cumple en 4 de 9 celdas. Falla el recall: 2022 · h4 en 0,40, y 0,00–0,09 en las 2 primeras
  semanas de brotes nuevos.
- Regresión: no cumple en ninguna celda. Pierde contra la persistencia en el pico.
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
- Recorte del logit fijado en el preregistro (la auditoría del estudio 05 mostró que cambia 2022 · h4).
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
