# Ingeniería de características para el pronóstico semanal de dengue en Piura

**Documento para reunión con el asesor · 30 de septiembre de 2026**  
**Alcance:** lo implementado en las fases 1–7. El primer modelo es XGBoost; el entrenamiento y sus cifras están explicados por separado en [la guía de modelado](../modeling/guia_para_asesor.md).

## 1. El proyecto en dos minutos

Se pronostican los casos y la condición de **semana con nivel elevado de dengue** de cada distrito de Piura. La unidad de análisis es `(ubigeo, anio, semana)`: una fila por distrito y semana epidemiológica. La fecha `semana_inicio` es el domingo de la **semana objetivo**. Hay **65 distritos, 469 semanas por distrito y 30 485 filas** entre 2017 y 2025. El archivo integrado de `data/silver/integrado/` tiene **35 columnas** y junta casos, clima y demografía, sin variables predictoras derivadas.

Se construyeron dos archivos `data/gold/`, uno para `h=2` y otro para `h=4`; `h` significa semanas de anticipación. El objetivo principal del proyecto es **cuatro semanas** y el mínimo deseado es **dos**. Ambos gold conservan **30 485 filas y 48 columnas**, incluidas **34 candidatas predictoras** y **14 campos de identidad, objetivo o auditoría**. Gold no obliga a entrenar con las 34 candidatas. El primer XGBoost empezó con seis y después comparó familias por separado.

```text
Fuentes bronze → fuentes limpias silver → panel integrado silver (35 columnas)
                                           ↓ fases 1–7
                    gold h=2 y gold h=4 (48 columnas cada uno)
                                           ↓ experimentos temporales
                  matrices pequeñas → XGBoost de casos / alerta
```

Los 1 114 casos de 2025 presentes en el panel proceden de la Sala Situacional y se aceptan como fuente válida. Su exportación registra además **tres casos de 2025-S53** que no se incorporaron al modelo porque falta esa semana en el panel climático. El cambio de fuente se documenta; no implica declarar falsos sus casos.

## 2. Contrato temporal: qué se sabe al pronosticar

Para una fila cuyo objetivo es la semana `t`, `h=4` significa emitir el pronóstico al **cierre de `t−4`**; `h=2`, al cierre de `t−2`. Los casos, el clima observado y el estado de otros distritos solo pueden usar semanas **hasta `t−h`**. Por ejemplo, para predecir la semana 20 con cuatro semanas de anticipación, la información observada termina en la semana 16: no se leen las semanas 17–20. La semana objetivo sí se conoce de antemano y permite usar calendario. `origen_inicio` y `origen_cierre` registran y permiten auditar este límite.

La suposición actual es que casos y clima semanal están disponibles al cerrar la semana de origen. **No se han verificado las demoras reales de publicación**; con una demora, habría que retroceder el último dato permitido. Los lags se calcularon por `ubigeo`, ordenados por fecha, y se comprobaron con ejemplos y pruebas que alteran semanas posteriores al origen: la variable de la semana objetivo no cambia.

`ubigeo` se mantiene como texto de seis dígitos y sirve para unir datos, nunca como número continuo. Los nulos del comienzo del panel significan **historia previa insuficiente**, no cero casos. No se rellenaron con cero.

## 3. Etiqueta experimental de semana elevada

La alerta elegida por Rosa marca **cada semana distrital con nivel elevado de casos**, también si es la segunda o tercera semana elevada de una racha. No se limita al primer arranque de un episodio. La etiqueta `brote` se calculó una vez por `(ubigeo, anio, semana)` y es idéntica en gold h=2 y h=4:

```text
umbral_brote_casos(distrito, año, semana)
  = media de esa misma semana en los 5 años anteriores
    + 1,5 × desviación estándar muestral de esos 5 valores

brote = 1 si casos_Dengue > umbral_brote_casos y casos_Dengue ≥ 2;
         0 en otro caso.
```

La regla usa solo **años anteriores al objetivo**. Para etiquetar 2017–2021 se incorporó la historia epidemiológica 2012–2016 de silver; las ausencias del Excel histórico se tratan como cero para calcular el canal, lo cual **no prueba que se haya notificado un cero**. La semana 53 se suma a la 52 solo para la referencia histórica; la fila objetivo conserva su semana original. El multiplicador **1,5 DE** fue elegido para experimentar; el mínimo de **2 casos** es provisional. La sensibilidad dio **3 744** positivos con mínimo 1, **3 002** con mínimo 2 y **2 180** con mínimo 5. `brote` es la etiqueta, `umbral_brote_casos` es metadato de la regla y ninguno entra como predictor. El conteo `casos_Dengue` también queda fuera de la matriz `X` de esa misma semana.

El [EDA del objetivo](../eda/hallazgos.md) comparó además una tasa D1, un percentil distrital D2, un canal D3 y aumento sostenido D4; esas marcas exploratorias **no son la etiqueta actual**. La [revisión de definición](revision_definicion_brote.md) explica por qué 1,5 DE y un canal tipo media + 2 DE son opciones diferentes.

## 4. Proceso por fases: justificación, ensayo e insight

### Fase 1 — contrato y objetivo (`17_fe_contrato_objetivo`)

Se auditó el panel integrado antes de crear features: 30 485 llaves únicas, 65 distritos, 469 semanas, cobertura técnica sin nulos. Se verificó la disponibilidad de origen para h=2/h=4 y se compararon cuatro definiciones ilustrativas del objetivo. El EDA había encontrado un problema de calendario alrededor de 2025-S53, ceros históricos ambiguos y pocas temporadas independientes. **Insight:** el problema debe evaluarse en orden temporal, y una etiqueta semanal elevada requiere una regla explícita distinta de «al menos un caso» o «arranque». Esta fase estableció el contrato temporal; la etiqueta definitiva se materializó en la fase 6.

### Fase 2 — historia propia y calendario (`18_fe_historia_calendario`)

El [EDA temporal](../eda/hallazgos.md) mostró fuerte autocorrelación a cuatro semanas, aun quitando el nivel de temporada, y una línea base de persistencia exigente. Se crearon dos casos rezagados, una media de cuatro semanas, un conteo de semanas con casos, y seno/coseno de la semana objetivo. Todos los agregados de casos terminan en `t−h`; el calendario es conocido de antemano. Se compararon **reglas simples**, no XGBoost: en 27 105 filas comunes, el MAE en `log1p(casos)` de persistencia fue **0,1650 para h=2** y **0,2084 para h=4**, mejor que usar la media de cuatro semanas como pronóstico aislado (**0,1867 / 0,2326**) y que repetir la misma semana del año anterior (**0,5254 / 0,5254**). **Insight:** la media no reemplaza la persistencia como regla autónoma, aunque puede complementar al último caso dentro de un modelo.

### Fase 3 — vecinos y jerarquía (`19_fe_vecinos_jerarquia`)

El [EDA espacial](../eda/hallazgos.md) encontró autocorrelación espacial de incidencia (I de Moran **0,693** con cinco vecinos; **0,333** dentro de la costa) y actividad regional compartida. Se definieron cinco vecinos por centroides con pesos iguales; cada distrito queda excluido de su propio contexto. Se generaron media y fracción de vecinos con casos, más casos y fracción activa del resto de provincia y de la región, siempre en `t−h`. Se probaron `k=3`, `k=8` y pesos por distancia como sensibilidad. La correlación descriptiva de la media de cinco vecinos con casos objetivo fue **0,6207 / 0,6130** para h=2/h=4, menor que la historia propia (**0,7785 / 0,7426**). **Insight:** hay contexto espacial medible, pero la correlación no demuestra contagio entre distritos ni mejora predictiva incremental; por eso se dejó para una ablación XGBoost separada.

### Fase 4 — clima (`20_fe_clima`)

El [EDA climático](../eda/hallazgos.md) halló una señal parcial pequeña de **humedad relativa** y **precipitación** en la ventana de 4–8 semanas para h=4; temperatura media/máxima reflejaban sobre todo calendario y `lluvia_total_mm` duplicaba precipitación. Se crearon medias observadas de cinco semanas: `t−8…t−4` en h=4 y `t−6…t−2` en h=2. También se ensayaron anomalías contra la climatología distrito-semana, **ajustada solo con el entrenamiento de cada corte**, y una anomalía de temperatura mínima como prueba secundaria. Las anomalías no se guardaron como una columna única de gold porque sus valores dependen del corte.

En un ridge exploratorio de conteos `log1p`, añadir las dos anomalías climáticas mejoró el MAE en **5 de 8** combinaciones horizonte-temporada. Para h=4, en la temporada 2023 redujo el MAE en **0,575 casos**, pero en 2022 lo aumentó en **0,114**. Temperatura mínima mejoró **3 de 8** cortes frente a las dos variables principales. **Insight:** el clima merecía una prueba XGBoost, pero la evidencia no justificaba incluirlo por defecto.

### Fase 5 — sociodemografía (`21_fe_sociodemografia`)

El [EDA sociodemográfico](../eda/hallazgos.md) mostró que un eje urbano resume **61,3 %** de la variación de las 15 fracciones, pero su relación con la incidencia dentro de distritos cálidos es débil y no robusta. Se comparó una referencia **fija de 2017** contra valores anuales reconstruidos: `log(población)`, tres fracciones interpretables (rural, menores de 15, desagüe de red), las 15 fracciones y un eje PCA `CP1`. El PCA se ajustó **dentro de cada fold** con la referencia 2017 y se aplicó a cada año; sus puntajes no se publicaron como un valor global en gold.

El ridge exploratorio de conteos comparó ocho cortes. Población fija de 2017 redujo MAE en **6/8**; las tres fracciones fijas, **4/8**; CP1 fijo, **5/8**; las **15 fracciones anuales juntas, 2/8**. Los cambios fueron pequeños y variables entre temporadas. Las fracciones anuales de 2018–2024 se interpolaron entre los extremos de **2017 y 2025**. Rosa decidió ensayarlas como reconstrucción retrospectiva, **sin llamar a ese ensayo una simulación de pronósticos que se podían emitir entonces**. La población anual mezcla censo 2017 y proyecciones 2018–2025, cuya publicación exacta no está documentada. **Insight:** conservar representación fija y anual para comparar, pero no convertir la asociación transversal o el ridge en una selección final del XGBoost.

### Fase 6 — integración y calidad (`22_fe_integracion`)

Tras validar silver y cobertura, `src/modeling/features.py` unió por llave las familias, añadió `brote` y produjo ambos gold. Se comprobó que ningún join aumentara filas, que `semana_inicio` y los orígenes respetaran el horizonte, que los casos y umbrales fueran coherentes y que h=2/h=4 compartieran exactamente la misma etiqueta. El manifiesto local guarda hashes de fuentes, cobertura, catálogo geográfico, historia de la etiqueta y salidas. Gold h=2/h=4 tiene **48 columnas**. Si se exigen **las 34 candidatas** completas, quedan **30 095 / 29 965** filas; las primeras **390 / 520** filas tienen al menos una ventana sin historia. Para entrenar solo la base de seis bastan **30 160 / 30 030** filas. **Insight:** conservar en gold las filas iniciales con nulos estructurales permite auditar la cobertura; cada experimento selecciona filas según sus variables, sin fingir observaciones.

### Fase 7 — síntesis y traspaso (`23_fe_sintesis`)

Se auditó el gold persistido y se clasificaron **34 columnas candidatas** frente a **14 no predictoras**. El contrato prohibió introducir en `X` la etiqueta, casos de la semana objetivo, umbral, fechas, identificadores o banderas de procedencia. Se resumieron los experimentos ridge: clima y población mostraban aportes pequeños o variables; las 15 fracciones anuales juntas no mejoraban de modo estable. Se propuso comenzar XGBoost con historia propia y calendario y añadir familias por bloques sobre las mismas filas y cortes. **Insight:** publicar candidatos en gold no equivale a usarlos todos ni a declarar una relación causal. Las ablaciones XGBoost posteriores se detallan en la [guía de entrenamiento](../modeling/guia_para_asesor.md).

## 5. Inventario completo de candidatas de gold

En los nombres siguientes, `h` se sustituye por **2** o **4** en cada archivo. Por ejemplo, `casos_lag_h` aparece realmente como `casos_lag_2` o `casos_lag_4`. La columna `semana` original **no** es predictor; el calendario circular sí.

| Familia | Columna exacta o patrón | Definición y razón tomada del EDA |
|---|---|---|
| Historia | `casos_lag_{h}` | Casos propios de `t−h`; autocorrelación y persistencia fuertes. |
| Historia | `casos_lag_{h+1}` | Casos propios una semana antes del origen; compara nivel y cambio reciente. |
| Historia | `casos_media_4_h{h}` | Media propia de `t−h−3…t−h`; resume nivel reciente sin usar futuro. |
| Historia | `casos_semanas_positivas_4_h{h}` | Número de las cuatro semanas anteriores con casos >0; resume continuidad. |
| Calendario | `semana_epi_seno` | Seno de la semana objetivo; representa el ciclo anual y su valle alrededor de S35. |
| Calendario | `semana_epi_coseno` | Coseno complementario; evita el salto numérico entre S52 y S01. |
| Vecinos | `vecinos_media_casos_knn5_h{h}` | Media de casos en `t−h` de los cinco centroides más cercanos, sin el propio distrito. |
| Vecinos | `vecinos_frac_con_casos_knn5_h{h}` | Fracción de esos cinco vecinos con >0 casos en `t−h`. |
| Jerarquía | `provincia_otros_casos_h{h}` | Suma de casos en otros distritos de la misma provincia en `t−h`. |
| Jerarquía | `provincia_otros_frac_con_casos_h{h}` | Fracción de esos otros distritos con >0 casos. |
| Jerarquía | `region_otros_casos_h{h}` | Suma de casos en los otros 64 distritos del panel de Piura en `t−h`. |
| Jerarquía | `region_otros_frac_con_casos_h{h}` | Fracción de esos otros 64 distritos con >0 casos. |
| Clima | `hum_rel_media_media5_h{h}` | Media de humedad en `t−h−4…t−h`; señal parcial del EDA. |
| Clima | `precip_total_mm_media5_h{h}` | Media de precipitación en la misma ventana; señal parcial del EDA. |
| Censo fijo | `fraccion_rural_2017` | Proporción rural censal, repetida por distrito; eje de asentamiento. |
| Censo fijo | `fraccion_menores_15_2017` | Proporción menor de 15 años; composición etaria. |
| Censo fijo | `fraccion_desague_red_2017` | Proporción con desagüe de red; infraestructura/urbanidad. |
| Censo fijo | `log_poblacion_censo_2017` | Logaritmo natural de habitantes censados en 2017; tamaño distrital, no tasa ni offset. |
| Anual | `fraccion_rural_anual` | Proporción rural anual reconstruida por distrito. |
| Anual | `fraccion_mujeres_anual` | Proporción de mujeres anual reconstruida. |
| Anual | `fraccion_menores_15_anual` | Proporción menor de 15 años anual reconstruida. |
| Anual | `fraccion_sin_seguro_anual` | Proporción sin seguro anual reconstruida. |
| Anual | `fraccion_analfabeta_15_mas_anual` | Proporción analfabeta de 15+ anual reconstruida. |
| Anual | `fraccion_pared_precaria_anual` | Proporción con pared precaria anual reconstruida. |
| Anual | `fraccion_piso_tierra_anual` | Proporción con piso de tierra anual reconstruida. |
| Anual | `fraccion_agua_red_anual` | Proporción con agua de red anual reconstruida. |
| Anual | `fraccion_agua_cisterna_anual` | Proporción con agua de cisterna anual reconstruida. |
| Anual | `fraccion_desague_red_anual` | Proporción con desagüe de red anual reconstruida. |
| Anual | `fraccion_sin_saneamiento_anual` | Proporción sin saneamiento anual reconstruida. |
| Anual | `fraccion_alumbrado_red_anual` | Proporción con alumbrado de red anual reconstruida. |
| Anual | `fraccion_hogares_refrigeradora_anual` | Proporción de hogares con refrigeradora anual reconstruida. |
| Anual | `fraccion_hogares_celular_anual` | Proporción de hogares con celular anual reconstruida. |
| Anual | `fraccion_hogares_lena_anual` | Proporción de hogares que usan leña anual reconstruida. |
| Anual | `log_poblacion_anual` | Logaritmo de habitantes asignados al año; censo 2017 y proyecciones posteriores. |

Las 15 fracciones anuales anteriores comparten la motivación exploratoria de la fase 6 del EDA: describen un eje urbano y diferencias distritales, **sin demostrar efectos causales**. Su valor es igual en todas las semanas de un distrito-año. Las fracciones 2018–2024 contienen el extremo 2025 y por eso requieren la advertencia de reconstrucción retrospectiva.

**Columnas creadas para auditoría, no para entrenar:** `origen_inicio`, `origen_cierre`, `socio_2017_disponible_al_origen`, `socio_fracciones_interpoladas_con_2025`, `umbral_brote_casos` y `brote`. La última es la etiqueta; `casos_Dengue` permanece como observación de la semana objetivo. Otros ocho campos no predictores identifican distrito, semana y procedencia (`ubigeo`, `anio`, `semana`, `provincia`, `distrito`, `distrito_key`, `semana_inicio`, además del conteo ya indicado). Las anomalías climáticas, el indicador de temperatura mínima, los puntajes `eje_urbano_2017`/`eje_urbano_anual` y `fraccion_sin_seguro_2017` se calcularon **solo en experimentos específicos**; no forman parte de las 34 candidatas persistidas.

## 6. Qué está resuelto y qué conviene discutir

**Resuelto en código:** la unidad y las llaves del panel; horizontes separados; cálculos de lags sin usar semanas posteriores al origen; joins por UBIGEO; conservación de nulos de arranque; dos gold reproducibles; etiqueta actual auditable; linaje y hashes. Las reglas de variables describen asociaciones predictivas, no causalidad.

**Decisiones aún abiertas para la tesis:** confirmar la fecha real de publicación de casos, Open-Meteo y proyecciones; revisar el significado de ceros en distritos sin registros históricos; acordar con el asesor si el mínimo de 2 casos y el canal media + 1,5 DE sirven para una alerta operativa; resolver la semana 53 antes de extender a 2026; distinguir la validez de los casos 2025 del poder estadístico de una evaluación con apenas tres positivas. Para la población anual, documentar el quiebre entre censo 2017 y proyecciones 2018+ antes de interpretarla como exposición.

## 7. Dónde verificar y reproducir

- Entrada: `data/silver/integrado/meteo_socio_epi_piura_2017_2025.csv` y cobertura lateral.
- Código: `src/modeling/` (features, etiqueta y familias), `src/validation/contrato_pronostico.py`.
- Orquestación: notebooks `17`–`23`; el `22_fe_integracion.ipynb` regenera gold y el `23_fe_sintesis.ipynb` audita el traspaso.
- Evidencia: [plan por fases](plan.md), [informes de fase](fase1_contrato_objetivo.md), [métricas del EDA](../eda/hallazgos.md), [síntesis gold](fase7_sintesis_traspaso.md) y los JSON en `docs/feature_engineering/metricas/`.
- Comprobación actual: `.venv/bin/python -m unittest discover -s tests` y auditoría de silver/gold/manifest con `src.modeling.contrato_xgboost.auditar_traspaso()`.

**Nota de lectura:** los números de ridge de fases 4–5 son experimentos exploratorios de **conteos**; las métricas de F1 de alerta y las decisiones sobre subconjuntos proceden de los ensayos XGBoost descritos en el segundo documento.
