# Fase 1 — contrato temporal y objetivo

**Estado:** análisis ejecutado; decisiones y aprobación de Rosa pendientes. El [notebook](../../notebooks/17_fe_contrato_objetivo.ipynb) se ejecutó de principio a fin sobre el integrado actual. Las cifras están en [métricas](metricas/fase1_contrato_objetivo.json) y el contraste visual en [figura](figuras/fase1_contrato_objetivo/01_positivos_por_definicion.png). Los cuatro conteos de objetivos se recalcularon con un script independiente de las funciones del notebook y coincidieron.

## Hallazgos

**1. El panel permite auditar dos y cuatro semanas de anticipación.** Tiene 30 485 filas, 35 columnas, 65 distritos y 469 semanas consecutivas por distrito, sin nulos ni llaves duplicadas [`integridad`]. Para el mínimo `h=2`, hay 30 355 filas con origen y 130 sin dos semanas de historia. Para el objetivo principal `h=4`, hay 30 225 con origen y 260 sin cuatro semanas de historia. El último caso semanal potencialmente disponible para el objetivo `t` es el de `t−h`, suponiendo publicación al cierre de esa semana. Una observación de `t−1` no fue admisible para ninguno de los dos horizontes. Si la vigilancia publica con demora, el último dato utilizable sería anterior a `t−h`. Estas son cifras de disponibilidad; el rendimiento a dos semanas todavía no se ha medido.

**Ejemplo de validación con 2025:** en el distrito `200101`, la semana objetivo 2025-S52 comienza el 2025-12-21 y registra 0 casos. Para `h=4`, el pronóstico se emitiría al cierre de 2025-S48 (2025-11-29); S48 registra 1 caso y podrían usarse esa observación y las anteriores si ya estuvieran publicadas. Las semanas S49–S52 quedan fuera de sus predictores. Para `h=2`, el pronóstico se emitiría al cierre de 2025-S50 (2025-12-13); S50 registra 0 casos y podrían usarse S50 y semanas anteriores. La comparación con los 0 casos de S52 se hace después de observar S52. Si todo 2025 se reserva como prueba de un modelo fijo, el entrenamiento debe terminar antes del origen del **primer** pronóstico de ese conjunto; los casos observados de 2025 pueden alimentar los rezagos de pronósticos posteriores sin usarse para ajustar ese modelo. La disponibilidad efectiva de cada dato debe comprobarse.

**2. La cobertura técnica no resuelve qué significa un cero histórico.** Hay 23 756 filas con cero; el Excel histórico de Piura no contiene filas que notifiquen explícitamente cero, y los UBIGEO `200204`, `200205` y `200209` no figuran en él para 2017–2024 [`procedencia`]. El lateral marca 30 485 filas como verificadas, pero para esas filas indica que el actualizador aceptó el valor, no que MINSA observó un cero. Esta distinción afecta la interpretación del objetivo y la evaluación de distritos silenciosos.

**3. La semana 53 de 2025 requiere completar el panel antes de evaluarla.** Rosa confirmó que los casos de 2025 de la Sala Situacional son válidos como fuente de verdad. El panel contiene 1 114 casos de 2025; la exportación Sala tiene 1 117, incluidos tres casos en la semana 53 que no tiene fila climática en el modelo [`procedencia`]. Las 469 semanas presentes coinciden con la regla MMWR; hay 65 filas de 2020-S53. La regla actual del pipeline etiquetaría el domingo 2025-12-28 como 2026-S01, mientras MMWR lo etiqueta 2025-S53, y seguiría desplazada en 2026-01-04 [`calendario`]. El calendario oficial de la Sala requiere confirmación antes de actualizar el panel a 2026.

**4. La elección del objetivo cambia mucho el problema.** Se reprodujeron los parámetros ilustrativos de la fase 2 del EDA, sin adoptarlos como decisión final [`objetivos`, `parametros_ilustrativos`].

| Candidato | Semanas positivas | % del panel | Episodios | Limitación principal |
|---|---:|---:|---:|---|
| D1, tasa ≥ 10/100 000 | 4 076 | 13,37 % | 805 | Depende del denominador de población, cuya fuente cambia entre 2017 y 2018. |
| D2, > p90 distrital | 2 122 | 6,96 % | 516 | El percentil calculado con todo 2017–2025 usa información futura; habría que definirlo con el entrenamiento de cada corte. |
| D3, canal endémico | 5 218 | 17,12 % | 1 176 | El canal vale cero en 73,9 % de las distrito-semanas [`d3_pct_canal_en_cero`]; a menudo equivale a ≥ 1 caso. |
| D4, aumento sostenido | 755 | 2,48 % | 153 | Marca todas las semanas de una racha de al menos tres, no solo su inicio; confirmar la primera semana requiere observar las siguientes. |

El **arranque** es una etiqueta distinta de D4: exige definir cuál es la primera semana de un episodio y qué periodo previo debe estar libre de brote. El EDA contó 249 arranques bajo su definición ilustrativa D1 (`docs/eda/metricas/fase3_temporal.json`: `arranques_n`); no debe interpretarse ese número como positivos D4. La etiqueta retrospectiva puede requerir semanas posteriores al evento para confirmarse, pero ningún predictor puede verlas al emitir el pronóstico.

**5. El origen móvil por temporada es viable, con pocos eventos independientes.** Para temporadas que comienzan en la semana 35, las pruebas candidatas 2022, 2023 y 2024 tienen respectivamente 628, 1 148 y 1 269 positivos D1; con D4, 123, 300 y 149. La temporada 2025 tiene 98 D1 y 3 D4 [`folds_propuestos`]. Cada fold comparte fechas de corte entre los 65 distritos. El último objetivo de entrenamiento sin demora de notificación se sitúa dos o cuatro semanas antes de la primera semana objetivo de prueba, según el horizonte evaluado. El brote de 2023–2024 cruza la frontera de temporada, por lo que esos folds no son episodios independientes. Cualquier ajuste aprendido (climatología, PCA, percentiles, selección) se recalculará dentro de cada fold. La inclusión de 2025 como fold de prueba depende del esquema temporal que se acuerde, no de la validez de sus casos.

## Recomendaciones para decidir

| Decisión | Recomendación provisional | Estado |
|---|---|---|
| Qué predecir | Rosa decidió identificar **cada semana distrital con nivel elevado de casos**; una racha puede contener varias semanas positivas. El arranque no es la etiqueta principal. D1 se usó solo como referencia experimental y su umbral no quedó aprobado. El conteo puede ser un desenlace secundario. | Tipo de alerta decidido; umbral pendiente de Rosa, compañera y asesor. |
| 2025 | Aceptar los casos de la Sala como válidos y conservar su procedencia. La propuesta previa del EDA P2/D1 de excluir 2025 por una sospecha de subregistro no se adopta. Elegir el periodo de prueba por diseño temporal y cantidad de episodios evaluables; 2025 puede aportar al entrenamiento de folds posteriores o ser prueba, según el corte. | Validez de casos decidida por Rosa; partición temporal pendiente. |
| Ceros sin notificación | Mantener los tres distritos en el panel y reportar resultados con y sin ellos; no llamar “cero observado” a sus ausencias históricas. | Pendiente de Rosa. |
| Población | Confirmar la procedencia de 2017 antes de fijar un objetivo basado en tasa o interpretar un efecto de exposición. | Pendiente de fuente/asesor. |
| Calendario | Usar el panel 2017–2025 tal como está para esta fase. Confirmar la regla oficial de la Sala y corregir el pipeline antes de generar observaciones de 2026. | Pendiente de fuente/asesor. |
| Inicio del panel | Para `h=2`, hay 130 filas sin dos semanas de historia; para `h=4`, 260 sin cuatro. Definir si se excluyen del entrenamiento de cada horizonte o si se incorpora y valida historia anterior. | Pendiente de Rosa. |

Las fases 2 y 3 construyeron variables causales sin fijar un umbral de nivel elevado; `casos_Dengue` sigue siendo la observación y ninguna definición ilustrativa de brote fue aprobada como etiqueta. La salida gold se producirá solo en la fase de integración.
