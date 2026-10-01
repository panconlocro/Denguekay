# Entrenamiento y evaluación temporal del primer XGBoost para dengue en Piura

**Documento para reunión con el asesor · 30 de septiembre de 2026 (cifras actualizadas el 1 de octubre de 2026)**  
**Estado:** experimentos exploratorios completados para `h=2` y `h=4`; no hay un modelo operativo ni un test final independiente. Todas las cifras proceden de los JSON actuales de `docs/modeling/metricas/`, generados con GPU NVIDIA (`device="cuda"`); en otro equipo los decimales pueden variar (ver la sección 9). Para el origen de las variables y la construcción de gold, ver [la guía de feature engineering](../feature_engineering/guia_para_asesor.md).

## 1. Qué problema aprende el modelo

Cada fila describe un distrito de Piura y una **semana epidemiológica objetivo** `t`. El proyecto busca anticiparla **cuatro semanas** principalmente y **dos semanas** como mínimo. Gold contiene 30 485 filas y 48 columnas por horizonte; entre ellas hay 34 candidatas predictoras, pero los primeros modelos emplearon solo cuatro o seis. El último dato epidemiológico o climático permitido para una fila de horizonte `h` es el de `t−h` (bajo la suposición aún no verificada de publicación al cierre de esa semana).

Se entrenaron **dos XGBoost separados por horizonte y objetivo**:

1. **Regresión de casos:** `XGBRegressor` predice `log1p(casos_Dengue)`. Se invierte la transformación para obtener casos no negativos. Para convertir ese pronóstico en alerta se aplica la **regla de casos elevados** del gold: superar estrictamente el umbral histórico de la semana y alcanzar al menos dos casos.
2. **Clasificación directa:** `XGBClassifier` aprende `brote` y entrega una probabilidad. Una alerta se emite cuando supera un umbral de probabilidad elegido con datos anteriores, no por usar automáticamente 0,5.

La etiqueta `brote` marca **cada semana distrital elevada** con la regla media de la misma semana en los cinco años anteriores + **1,5 desviaciones estándar muestrales**, y mínimo provisional de **2 casos**. No representa solo el inicio de un episodio. `casos_Dengue`, `brote`, `umbral_brote_casos`, `ubigeo`, fechas y banderas de procedencia **no son predictores de la misma fila**. No se codifica UBIGEO como magnitud numérica. Los casos 2025 de Sala Situacional son válidos según la decisión del proyecto; su procedencia distinta y el escaso número de positivos se reportan.

**Referencia de comparación:** persistencia predice para `t` los casos realmente observados en `t−h`, y genera alerta con la misma regla histórica. Es una referencia difícil de superar; un F1 superior a cero por sí solo no demostraría valor agregado.

## 2. Seis variables de la base y cómo leer una fila

Las seis columnas de la base `base_6` son cuatro de historia propia y dos de calendario. Para h=4, `casos_lag_{h}` se llama `casos_lag_4`; para h=2, `casos_lag_2`.

| Predictor de `base_6` | Significado para semana objetivo `t` | Justificación del EDA |
|---|---|---|
| `casos_lag_{h}` | Casos del mismo distrito en `t−h`, el último valor potencialmente observable. | Autocorrelación y persistencia fuertes. |
| `casos_lag_{h+1}` | Casos del mismo distrito una semana antes de ese origen. | Ayuda a describir cambio reciente. |
| `casos_media_4_h{h}` | Media de casos en `t−h−3…t−h`. | Resume el nivel reciente sin mirar semanas futuras. |
| `casos_semanas_positivas_4_h{h}` | Entre esas cuatro semanas, cuántas tuvieron >0 casos. | Resume continuidad de actividad. |
| `semana_epi_seno` | Componente circular de la semana objetivo. | Ciclo anual de casos; semana objetivo conocida al emitir el pronóstico. |
| `semana_epi_coseno` | Segundo componente circular. | Evita tratar S52 y S01 como semanas muy lejanas. |

La variante `base_4` usa solo `casos_lag_{h}`, `casos_media_4_h{h}` y el par seno/coseno. Las seis fueron una **propuesta inicial** de la fase 7, no una selección demostrada. Los primeros **325 registros de h=2** y **455 de h=4** no tienen cuatro semanas completas de historia: permanecen en gold, pero no forman parte de las matrices que comparan estas variantes. Así se usan **30 160** o **30 030** filas, respectivamente. Los nulos estructurales no se sustituyeron por cero.

## 3. Hiperparámetros fijos del experimento

La configuración en `src/modeling/train.py` es una **base fijada manualmente para comparar variantes**, no los valores por defecto de la librería y tampoco el resultado de una búsqueda de hiperparámetros. Se mantuvo constante en las ablaciones para que la diferencia observada se atribuya principalmente a las variables comparadas.

| Parámetro | Valor | Papel |
|---|---:|---|
| `n_estimators` | 160 | Número de árboles. |
| `max_depth` | 3 | Profundidad máxima de cada árbol. |
| `learning_rate` | 0,05 | Tamaño de cada paso de aprendizaje. |
| `subsample` | 0,8 | Fracción de filas por árbol. |
| `colsample_bytree` | 0,9 | Fracción de columnas por árbol. |
| `min_child_weight` | 5 | Exige evidencia mínima para dividir un nodo. |
| `reg_lambda` | 5,0 | Penalización L2 sobre hojas. |
| `tree_method` | `hist` | Método de construcción de árboles. |
| `random_state` | 17 | Semilla reproducible dentro de un mismo equipo. |
| `device` | `auto` (`cuda` en los JSON actuales) | GPU NVIDIA si existe; si no, CPU. No es un hiperparámetro del modelo. |
| `n_jobs` | `auto` (12 en los JSON actuales) | Hilos de CPU; no cambia los resultados. |

Regresión: `objective=reg:squarederror` sobre `log1p(casos)`. Clasificación: `objective=binary:logistic`, `eval_metric=logloss`. La versión registrada es **XGBoost 3.4.1**. No se aplicó un offset poblacional automático, ponderación de clases ni calibración probabilística adicional. La fracción de población que se prueba más adelante es **una variable predictora**, no un denominador de tasa.

## 4. Cómo se separaron entrenamiento y evaluación

**No se hizo un `train_test_split` aleatorio por filas ni un único 80/20.** Se usó un esquema temporal de origen móvil, con el mismo corte para los 65 distritos. Una **temporada etiquetada Y** va de la **semana 35 de Y−1** a la **semana 34 de Y**. El [EDA temporal](../eda/hallazgos.md) encontró un valle estacional aproximadamente en la semana 35 y un pico cerca de la 20; así el año calendario no corta habitualmente la subida y bajada en enero. La semana 35 es una convención analítica, no un límite epidemiológico oficial. El brote de 2023–2024 cruza esa frontera, por lo que dos temporadas no equivalen a episodios independientes.

Para cada bloque se ajustó **un XGBoost nuevo desde cero** con todas las filas históricas cuyas etiquetas ya habían cerrado al **primer origen** de pronóstico del bloque. Durante ese bloque los árboles quedan fijos. Los pronósticos posteriores sí reciben lags más recientes de casos o clima que ya se hayan observado; esos valores actualizan las **entradas**, no los pesos del modelo. Con h=4, el primer objetivo de la temporada 2022 es 2021-S35; su origen es el cierre de 2021-S31 (**2021-08-07**). Por eso el entrenamiento de ese modelo incluye historia desde 2017 hasta etiquetas cerradas en esa fecha, no las respuestas futuras de 2021-S32 en adelante.

| Bloque evaluado | Primer corte h=2 | Filas train h=2 | Primer corte h=4 | Filas train h=4 | Filas evaluadas |
|---|---|---:|---|---:|---:|
| Temporada 2021 | 2020-08-15 | 11 960 | 2020-08-01 | 11 700 | 3 445 |
| Temporada 2022 | 2021-08-21 | 15 405 | 2021-08-07 | 15 145 | 3 380 |
| Temporada 2023 | 2022-08-20 | 18 785 | 2022-08-06 | 18 525 | 3 380 |
| Temporada 2024 | 2023-08-19 | 22 165 | 2023-08-05 | 21 905 | 3 380 |
| **Año calendario** 2025 | 2024-12-21 | 26 715 | 2024-12-07 | 26 455 | 3 380 |

Las filas de entrenamiento anteriores proceden del primer experimento `base_6` y excluyen solo los arranques sin la historia requerida. **2017–2020 sí se usan para entrenar** (salvo esas primeras semanas estructurales). Las etiquetas de 2021 entran en modelos de temporadas posteriores una vez conocidas; igual ocurre con 2022, 2023 y 2024. La temporada 2021 tiene 3 445 filas por la semana 53 de 2020; los bloques de 52 semanas tienen 65 × 52 = 3 380. El año calendario 2025 es una sensibilidad separada, no la «temporada 2025» que empieza en 2024-S35.

### Qué se usó para elegir variables y el umbral

En los **primeros experimentos**, las temporadas **2021–2023** sirvieron para elegir variables y el umbral de probabilidad: para cada variante se maximizó F1 con sus predicciones de validación agregadas. La temporada **2024** se consultó como contraste principal y calendario **2025** como sensibilidad. Ese F1 de validación puede ser optimista porque las mismas temporadas servían para elegir umbral y variables. Además, 2024 ha sido inspeccionado repetidas veces; **no es ya un test virgen**.

El ensayo progresivo más reciente corrigió específicamente la reutilización de etiquetas para el **umbral de cada bloque**. Las predicciones fuera de muestra de **2021** calibran el umbral de 2022; para 2023 se agregan solo etiquetas anteriores ya cerradas, y así sucesivamente. Las últimas **65 distrito-semanas en h=2** o **195 en h=4** de la temporada previa se excluyen de esa calibración si todavía no cerraban al primer origen. La matriz se seleccionó por F1 medio de **2022–2023**, y se revisó en 2024. Esto es cronológicamente más estricto, pero **no elimina la familiaridad previa con 2024 ni el cribado anterior de muchas variantes**.

## 5. Cómo interpretar las métricas

- **VP (verdaderos positivos):** semanas elevadas para las que el modelo emitió alerta. **FP (falsos positivos):** semanas normales con alerta. **FN:** semanas elevadas sin alerta.
- **Precisión = VP / (VP + FP):** de las alertas emitidas, cuántas acertaron. **Recall = VP / (VP + FN):** de las semanas elevadas reales, cuántas detectó.
- **F1:** media armónica de precisión y recall. Se mantuvo como criterio provisional mientras el equipo define cuánto cuesta un falso aviso frente a una semana elevada no detectada.
- **AUPRC:** calidad del ordenamiento de semanas por puntaje de alerta ante clases desbalanceadas, sin fijar un solo umbral.
- **MAE de casos:** diferencia absoluta promedio entre casos reales y pronosticados; menor es mejor. Un modelo puede mejorar F1 de alerta y empeorar MAE de conteos, porque son objetivos distintos.

## 6. Primer XGBoost con las seis variables

Estos resultados usan el diseño inicial: umbral de clasificación elegido con validación 2021–2023. En la temporada 2024 hubo **857** semanas positivas de **3 380**. «Regresión + regla» significa que primero se predice el número de casos y luego se aplica la regla histórica para dar la alerta.

| Horizonte y método, temporada 2024 | MAE casos | VP | FP | Precisión | Recall | F1 | AUPRC |
|---|---:|---:|---:|---:|---:|---:|---:|
| h=2, regresión + regla | 5,64 | 656 | 123 | 0,842 | 0,765 | **0,802** | 0,871 |
| h=2, clasificación directa | — | 789 | 823 | 0,489 | **0,921** | 0,639 | 0,668 |
| h=2, persistencia + regla | **4,96** | 690 | 183 | 0,790 | 0,805 | 0,798 | 0,843 |
| h=4, regresión + regla | 9,40 | 623 | 164 | 0,792 | 0,727 | **0,758** | 0,770 |
| h=4, clasificación directa | — | **762** | 873 | 0,466 | **0,889** | 0,612 | 0,609 |
| h=4, persistencia + regla | **7,85** | 634 | 240 | 0,725 | 0,740 | 0,733 | 0,746 |

La clasificación directa detecta más semanas elevadas, pero genera muchos más falsos avisos. La regresión seguida de la regla ofrece una alerta más precisa; en **MAE de casos** todavía queda por detrás de persistencia para ambos horizontes. La mejora de F1 de regresión frente a persistencia es **0,004** en h=2 y **0,025** en h=4, pequeña. El umbral de probabilidad fue **0,175** para h=2 y h=4, no 0,5.

En **calendario 2025** hubo solo **3 semanas positivas**. Con h=4, regresión detectó **0** y produjo **5 FP**; clasificación detectó **1** y produjo **349 FP**. Con h=2, regresión detectó **0** con **3 FP**; clasificación **2** con **282 FP**. Es un año válido, pero cada acierto altera el recall en un tercio; no permite una estimación estable del sistema de alertas. La base de cuatro variables dio cifras próximas a las seis y no se declaró una ganadora en este primer ensayo.

## 7. Ablaciones: qué se añadió, qué mejoró y qué empeoró

Cada ablación conserva hiperparámetros y compara variantes **en las mismas filas dentro del experimento**. Las cifras de clima usan una fila menos por distrito que las otras, porque la ventana meteorológica de cinco semanas tarda más en estar completa; por eso su F1 base no es directamente comparable con el F1 base de otros informes. Los números de validación de esta sección pertenecen al esquema original 2021–2023, salvo donde se indique «progresivo».

### 7.1 Espacio: vecinos y contexto provincia/región

Se agregó a `base_6` por separado: dos variables de cinco vecinos, cuatro del resto de provincia/región, o las seis juntas. El EDA mostraba asociación espacial, pero para el clasificador **h=4** el F1 medio de validación pasó de **0,555** (base) a **0,554** (+vecinos), **0,537** (+jerarquía) o **0,543** (+ambos): empeoró en las tres opciones. En regresión h=4, +jerarquía subió de **0,567 a 0,586** en validación, pero en 2024 bajó de **0,758 a 0,751** de F1 y su MAE pasó de **9,40 a 11,28**. Para h=2, +jerarquía en clasificación elevó F1 de validación **0,592→0,604** y en 2024 **0,639→0,648**, con 26 VP y 20 FP adicionales, aunque su AUPRC bajó **0,668→0,636**. **Lectura:** el contexto espacial no mostró una ganancia robusta para la alerta principal h=4; su correlación descriptiva no equivale a valor incremental. La señal h=2 es pequeña y procede de un bloque ya inspeccionado.

### 7.2 Clima: humedad y precipitación

Se agregaron a `base_6` las medias observadas de cinco semanas, anomalías de esas mismas variables ajustadas por fold, o ambas. Sobre filas con clima completo, la clasificación **h=4** tuvo F1 medio de **0,557** en la base, **0,493** con clima observado, **0,460** con anomalías y **0,460** con ambos. La regresión h=4 pasó de **0,567** a **0,554 / 0,547 / 0,548**. Para h=2, clasificación pasó de **0,592** a **0,534 / 0,494 / 0,518**. **Lectura:** en el ridge exploratorio de FE el clima había ayudado algunos conteos, pero en esta configuración XGBoost ninguna variante climática ganó en F1 de alerta; no se incorporó por defecto. El retraso real de publicación de Open-Meteo sigue pendiente.

### 7.3 Sociodemografía: referencia fija frente a reconstrucción anual

Se añadieron a `base_6` población fija de 2017, tres fracciones fijas (rural, menores de 15, desagüe), un eje PCA fijo y combinaciones; también versiones anuales reconstruidas. En clasificación **h=4**, población fija elevó el F1 medio de **0,555 a 0,584** y en 2024 de **0,612 a 0,622**: **764 VP y 835 FP** frente a **762 VP y 873 FP** de la base. En h=2, clasificación pasó de **0,592 a 0,655** en validación, pero en 2024 solo de **0,639 a 0,645**. La regresión con tres fracciones fijas, elegida en h=4, apenas redujo el MAE de 2024 (**9,401 a 9,349**) y su F1 bajó de **0,758 a 0,751**. En h=2, la regresión fija elegida fue población, por solo 0,001 sobre las tres fracciones.

La población anual elevó el F1 medio retrospectivo de clasificación h=4 a **0,599**, pero en 2024 dio **0,611**, por debajo de la población fija (**0,622**), con **969 FP**. Las 15 fracciones anuales juntas dieron **0,547** en validación h=4, por debajo de la base. **Lectura:** población fija quedó como candidata pequeña para clasificación; las series 2018–2024 usan el extremo 2025 y no son una simulación histórica en tiempo real.

### 7.4 Cribado de las 15 fracciones y prueba condicional

Cada fracción de 2017 y cada fracción anual se añadió **una por vez** a `base_6`, sin población. Para clasificación h=4, la mejor fija por F1 de validación fue `fraccion_sin_seguro_2017`: **0,589** frente a **0,555** de base; en 2024 tuvo **0,621**, **738 VP** y **780 FP**. Es una alerta con **menos avisos falsos, pero también menos aciertos** que la de población fija: esta última tuvo **0,622**, **764 VP** y **835 FP**. Las 30 búsquedas individuales sobre pocas temporadas pueden inflar el mejor resultado. Además, en seis de las ocho elecciones del cribado la ganadora supera a la segunda por menos de 0,002 de F1, y esas ganadoras cambiaron respecto de una corrida anterior en otro equipo; la elección de clasificación h=4 (`sin_seguro`) sí se mantuvo.

Para saber si `sin_seguro` aportaba *además* de la población fija se predefinieron cuatro variantes: base, +población, +sin seguro y +ambas. En clasificación h=4, sumar ambas dio **0,584** de F1 medio, empatada con población sola (**0,584**), y fue peor en dos de las tres temporadas de validación. En 2024 **subió de 0,622 a 0,626**, con **765 VP** (uno más) y **824 FP** (11 menos), pero su AUPRC bajó de **0,653 a 0,644**. **Lectura:** no hay evidencia convincente de aporte incremental de `sin_seguro` sobre población en este modelo; tampoco es una afirmación causal sobre cobertura de seguro.

### 7.5 Cierre de matrices pequeñas con evaluación progresiva

Se predefinieron `base_4`, `base_6` y `base_6 + log_poblacion_censo_2017`. A diferencia de las ablaciones anteriores, el umbral de cada temporada se fijó con **predicciones y etiquetas anteriores disponibles al primer origen**. Se eligió matriz por F1 medio de 2022–2023, con igual peso; luego se miró 2024. Ningún hiperparámetro de XGBoost se optimizó.

| Horizonte / objetivo | Matriz elegida en 2022–2023 | F1 medio 2022–2023 | F1 en 2024 | Referencia útil |
|---|---|---:|---:|---|
| h=2, regresión + regla | `base_6` | 0,757 | 0,802 | Persistencia F1 0,798 |
| h=2, clasificación | `base_6 + población 2017` | 0,695 | 0,645 | 811 VP, 847 FP en 2024 |
| h=4, regresión + regla | `base_6` | 0,693 | 0,758 | Persistencia F1 0,733 |
| h=4, clasificación | `base_6 + población 2017` | 0,660 | 0,617 | 793 VP, 922 FP en 2024 |

En regresión, `base_6` y `base_4` quedaron prácticamente empatadas (diferencia de **0,004** en h=2 y **0,001** en h=4); en una corrida anterior en otro equipo ganaba `base_4`. La clasificación h=4 con población obtuvo F1 **0,523 en 2022** y **0,798 en 2023**: el promedio favorable es inestable entre temporadas. En 2024 su **precisión fue 0,462** (menos de la mitad de sus 1 715 alertas acertaron) y su **recall 0,925** (793 de 857 semanas elevadas detectadas). La regresión h=4 de seis variables produjo **623 VP y 164 FP** y F1 **0,758**, pero MAE de **9,401** frente a **7,848** de persistencia. Ninguna de las regresiones compactas detectó las tres positivas de 2025; el clasificador h=4 elegido tampoco, y emitió **203 FP**. Estos ensayos no establecen todavía un modelo final.

## 8. Qué se puede afirmar ante el asesor y qué falta

**Hallazgo sólido dentro del experimento:** los predictores usan semanas que terminan como máximo en el origen; el mismo panel y los mismos cortes permiten comparaciones pareadas; la persistencia es un comparador exigente; añadir todas las familias de gold no mejoró automáticamente XGBoost. Para la alerta h=4, la población fija de 2017 es la única adición pequeña con señal favorable en clasificación, pero su ventaja es modesta y varía por temporada. La regresión y la clasificación producen compromisos distintos entre semanas detectadas y falsos avisos.

**Límites del rendimiento:** 2024 se ha inspeccionado en varias decisiones y ya no es un test independiente; las métricas varían en decimales entre equipos (GPU frente a CPU) y eso basta para cambiar las elecciones de variante más ajustadas; el brote 2023–2024 atraviesa la frontera entre temporadas; 2025 contiene solo tres etiquetas positivas; los hiperparámetros son fijos y la regla de brote y umbral de F1 son provisionales. La disponibilidad real de publicación, el significado de ceros sin notificación, el calendario S53/2026 y la procedencia temporal de proyecciones siguen abiertos. Las métricas no prueban que el modelo sirva ya como alerta operativa ni que alguna fracción social o climática cause dengue.

**Decisiones útiles en la reunión:** (1) cuál es el costo aceptable de falsos avisos por semana elevada detectada; (2) si la etiqueta media + 1,5 DE y mínimo 2 responde al uso previsto; (3) cómo obtener una evaluación futura genuinamente independiente antes de afinar hiperparámetros; (4) si se quiere priorizar calidad del conteo, sensibilidad de alerta o ambas con métricas separadas. El siguiente paso técnico solo debería fijarse después de ese acuerdo.

## 9. Reproducibilidad y fuentes internas

- Dataset: `data/gold/meteo_socio_epi_piura_2017_2025_h2_gold.csv`, `..._h4_gold.csv` y `manifest_fase6.json`; proceden del integrado silver, no se alteran en los ensayos de modelo.
- Entrenamiento y cortes: `src/modeling/train.py`; métricas compartidas: `src/modeling/evaluate.py`; protocolo progresivo: `src/modeling/validacion_temporal_compacta.py`.
- Notebooks de orquestación: `24` (base), `25` (espacio), `26` (clima), `27` (socio), `28` (fracciones), `29` (población + sin seguro), `30` (validación progresiva).
- Informes con cifras completas: [primer XGBoost](primer_xgboost.md), [espacio](ablacion_espacial.md), [clima](ablacion_clima.md), [sociodemografía](ablacion_sociodemografica.md), [fracciones](ablacion_fracciones.md), [comparación condicional](ablacion_poblacion_sin_seguro.md) y [evaluación progresiva](validacion_temporal_compacta.md). Los JSON están en `docs/modeling/metricas/`.
- Comprobación: `.venv/bin/python -m unittest discover -s tests` y auditoría de linaje con `src.modeling.contrato_xgboost.auditar_traspaso()`.
- **Reproducibilidad entre equipos:** con `device: auto` en `config/config.yaml`, el entrenamiento usa la GPU NVIDIA si existe y la CPU si no (por ejemplo, en una Mac). En un mismo equipo dos corridas dan métricas idénticas; entre equipos cambian decimales, a veces un umbral de probabilidad y, cuando dos variantes se separan por milésimas, la variante elegida. Las conclusiones principales para h=4 (población fija como candidata de clasificación, sin aporte convincente de `sin_seguro` encima de ella, ninguna ganancia robusta de clima ni espacio) se mantuvieron. Al comparar resultados de Rosa y Nicolás, revisar primero `parametros.device` en el JSON o las etiquetas `plataforma` y `version.*` en MLflow. Detalle en [primer XGBoost](primer_xgboost.md#reproducibilidad-entre-equipos) y [MLflow](mlflow_great_expectations.md).
