# Revisión del short paper Denguekay: diseño y estado

Este documento describe cómo se organizó la revisión metodológica del short paper tras las observaciones del asesor, qué
análisis cubre cada fase, su estado y qué comentario atiende cada uno. Las cifras y los resultados están en los
informes de [research/08_v3_confirmed_cases](../../research/08_v3_confirmed_cases/README.md) enlazados en cada sección.

La pregunta central se mantiene: **¿cuánto aporta la información climática al pronóstico semanal de dengue por distrito
en Piura cuando el modelo ya conoce la historia local de casos?** El análisis conserva h2, h3 y h4 en los términos del
plan de dirección. El comentario 10 (horizonte real) queda fuera del alcance acordado. La comparación con otros
departamentos se hace después de cerrar y congelar el método en Piura.

La revisión cubre los comentarios anclados 1–32 del Word revisado; el comentario 0 resume la evaluación general. Cada
observación se responde con una evidencia verificable, una referencia a la sección o figura corregida y un estado. El
inventario de lo ya disponible se distingue de los análisis nuevos.

## Punto de partida verificado

- El cierre con confirmados ya tenía `d3`/V3 y `L + 5a` sin clima, ambos con trial 191, cinco semillas y el calendario
  anterior. Sirve como referencia de la revisión y como insumo para probar el código de evaluación; la tabla final usa un
  calendario común para todas las variantes. [Corrida con confirmados](../../research/08_v3_confirmed_cases/README.md)
- El GeoJSON versionado contiene **65 polígonos distritales de Piura**, con 65 UBIGEO únicos, derivados de los límites
  nacionales COD-AB. La extracción filtra Piura; los polígonos de otros departamentos salen de la misma fuente en la
  última fase. [GeoJSON de Piura](../../data/reference/distritos_piura_limites.geojson) ·
  [Ingesta y validación de límites](../../src/denguekay/data/ingestion/district_boundaries.py)
- El silver local de **CHIRPS v3 sat** tenía **91 000 filas**, 65 distritos y semanas del 2 de enero de 2000 al 25 de
  octubre de 2026: 90 675 filas finales y 325 preliminares, sin nulos ni llaves repetidas en el archivo inspeccionado.
  La lluvia se agrega por polígono y el notebook 03c conserva versión y fecha de disponibilidad. La fecha del silver se
  audita contra los metadatos del producto antes de usarla como evidencia de disponibilidad histórica.
  [Notebook 03c](../../pipelines/notebooks/03c_ingesta_chirps.ipynb) ·
  [Agregación y versionado](../../src/denguekay/data/processing/chirps_precipitation.py) ·
  [CHIRPS v3](https://chc.ucsb.edu/data/chirps3)
- La temperatura y la humedad de ERA5-Land del estudio se extrajeron **en un punto por distrito**, mientras el protocolo
  también hablaba de temperatura promedio del polígono. La versión final describe la extracción usada en cada
  experimento. [Producto climático de V3](protocolo_v3.md#8-producto-climático-de-d3-r14)
- El diagnóstico con confirmados separó las ventanas de entrenamiento y calibración y añadió persistencia
  probabilística. El beneficio de la historia larga dependió de la ventana de calibración, y los resultados de alertas,
  de la temporada y del presupuesto alcanzado. Orientan el manuscrito y se vuelven a evaluar con el calendario común y
  `b3`. [Resultados del diagnóstico](../../research/08_v3_confirmed_cases/README.md#calibración-y-alertas-para-la-revisión-del-paper)

## Fase 0. Protocolo de la revisión

1. **Insumos:** insumos confirmados, rango de observación, definición de semana y política de faltantes fijados, con los
   hashes del CSV, la Sala, el panel, la cobertura, la geometría y cada insumo climático. Los datos y resultados
   originales de V3 se conservan por separado.
2. **Temporadas:** uniformes y disjuntas desde la SE 35, incluida `temporada_2025`, con agosto–diciembre de 2024
   recuperado y cada semana objetivo contada una sola vez. 2024 es contraste retrospectivo, con la fecha en que se
   inspeccionó; `posterior_2026` queda separada de las temporadas decisivas, y el primer bloque, sin historia suficiente,
   fuera de las comparaciones calibradas. Una tabla registra cortes y filas por bloque y horizonte.
3. **Evaluación principal del aporte climático: Brier pareado por temporada.** Se reportan las seis temporadas originales
   con su justificación y fechas de selección, sus resultados individuales y la lectura sin 2026. La regla histórica
   `SEASON_2026` se aplica con su rol documentado. El promedio agrupado y los guardarraíles de alertas y conteos se
   presentan por separado, y el tratamiento de comparaciones múltiples y las sensibilidades se fijan de antemano.
4. **Cronología de decisiones:** qué se decidió antes de cada etapa y qué cambió después, incluidos el paso de F1 a
   Brier, la incorporación de 2026 y la elección operativa de `d3`, y cuántas configuraciones se evaluaron realmente
   contra las temporadas de decisión. Métricas, versiones, cortes, semillas, definiciones alternativas y presupuesto de
   tuning se fijan antes de las comparaciones nuevas. El manuscrito usa «prespecified» para la planificación interna y
   reserva «preregistered» para un protocolo registrado externamente antes de su evaluación.

**Estado.** Protocolo fechado y calendario común auditado, con 60 cortes, inventario de insumos y solape de fuentes
reproducible. La fase climática completa el inventario con las exposiciones nuevas.
[Protocolo y auditoría](../../research/08_v3_confirmed_cases/protocolo_revision.md)

## Fase 1. Exposición climática

**CHIRPS aporta lluvia en una grilla de 0,05°; ERA5-Land, temperatura y humedad en su propia grilla, distribuida a
0,1°.** Reutilizar los polígonos de CHIRPS mejora la forma de resumir ERA5-Land dentro de un distrito, pero un distrito
contenido en una sola celda puede conservar la misma temperatura tras ponderar: el resultado sigue teniendo la resolución
de ERA5-Land. [CHIRPS v3](https://chc.ucsb.edu/data/chirps3) ·
[ERA5-Land en Copernicus](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land?tab=overview)

1. **Lluvia.** CHIRPS v3 sat con el cálculo por intersección de celda y polígono, y auditoría de completitud semanal,
   versión, fuente y disponibilidad. En los orígenes de la retrospectiva se usa el producto o versión que podía estar
   disponible cuando hay evidencia; cuando el histórico solo tiene datos revisados, el supuesto se documenta y los
   diagnósticos retrospectivos y prospectivos se mantienen separados. Preliminar y final se guardan como versiones
   auditables.
2. **Temperatura y humedad.** Celdas ERA5-Land que intersectan los 65 polígonos, con un piloto en costa y sierra con el
   mismo intervalo, zona horaria, unidades y definición de semana. Se comparan tres exposiciones sobre las mismas filas:
   **celda de centroide**, **media por área de intersección** y **media ponderada por población o asentamientos**. Para
   la humedad se verifica que la variable de origen, o la fórmula con temperatura y punto de rocío, sea comparable con el
   silver. Las ventanas de `d3` y las medias de `b3` se calculan después de agregar espacialmente.
3. **Pesos y denominadores.** La capa poblacional histórica, su año de referencia y el tratamiento de distritos con
   datos insuficientes se fijan antes de evaluar, documentando cómo se reconstruyen los pesos y qué información estaba
   disponible en cada periodo. Las tasas por 100 000 usan denominadores distritales anuales con fuente y cobertura
   explícitas; los pesos dentro de las celdas y el denominador del distrito cumplen funciones distintas.
   [WorldPop, grillas históricas](https://hub.worldpop.org/Global1_2000-2020)
4. **Verificación.** Diferencias centroide–área–población por distrito y semana, estratificadas por costa y sierra;
   revisión de geometrías, pesos, celdas válidas y UBIGEO; validación con estaciones SENAMHI donde hay series comparables,
   con su cobertura. La mínima y el rango diurno entran como sensibilidades fijadas de antemano. La disponibilidad de
   todas las variables se verifica en los orígenes usados, por separado de la observación excluida sobre horizonte
   efectivo.
5. **Piloto de temperatura CHIRTS-ERA5.** Comparación de las medias semanales de Tmax y Tmin diarias de CHIRTS-ERA5
   (0,05°) y ERA5-Land sobre las mismas semanas, polígonos y regla de ponderación, primero en distritos costeros y
   serranos y, cuando hay series comparables, en estaciones. La media de Tmax y Tmin es un estimador distinto de la media
   de 24 horas. El catálogo contiene archivos históricos desde 1980 y archivos de 2026; antes de descargar la serie se
   verifican los días y celdas válidos en Piura, la fecha de publicación de ambas variables y la extracción por ventanas
   espaciales. El proveedor indica un desfase nominal de cinco días para Tmax y Tmin. Si el piloto pasa, se corre una sola
   sensibilidad de fuente con el diseño de `b3` y las mismas filas evaluables, con la lluvia, la humedad y las demás
   entradas fijas. El uso prospectivo exige comprobar la disponibilidad en cada fecha de emisión.
   [Ficha de CHIRTS-ERA5](https://www.chc.ucsb.edu/data/chirts-era5) ·
   [Catálogo diario de Tmax](https://data.chc.ucsb.edu/experimental/CHIRTS-ERA5/tmax/tifs/daily/) ·
   [Catálogo diario de Tmin](https://data.chc.ucsb.edu/experimental/CHIRTS-ERA5/tmin/tifs/daily/)
6. **Humedad.** La humedad relativa de ERA5-Land es la referencia. El proveedor documenta humedad calculada a partir de
   la temperatura CHIRTS-ERA5 y el punto de rocío de ERA5 para otros productos, pero el catálogo revisado no la lista como
   serie descargable. Una reconstrucción sería una serie híbrida y exigiría verificar que su estadístico diario sea
   comparable con la humedad del panel.
   [Documentación de las variables derivadas](https://data.chc.ucsb.edu/experimental/CHIRTS-ERA5/aaa.readme.txt)

**Estado.** Candidato principal construido y validado para los 65 distritos y 1 400 semanas: CHIRPS para lluvia y ERA5
global por población para temperatura y humedad. Los resultados de ERA5-Land, CHIRTS, PISCOt y el relleno exploratorio
se conservan como contrastes separados. [Comparación de fuentes y candidato](../../research/08_v3_confirmed_cases/comparacion_fuentes_clima.md)

**Salidas de la fase.** Silver semanal con fuentes y versiones, pesos reproducibles, informe de cobertura y comparación
de las tres exposiciones. El modelo principal usa la definición fijada por el protocolo y el centroide queda como
contraste con el estudio original.

## Fase 2. Reexperimentación en Piura y pregunta climática

| Comparación | Qué responde |
|---|---|
| `b3` original frente a `L + 5a`, con los hiperparámetros heredados compartidos | Si se sostiene la elección histórica de `b3` con confirmados; `d3`/V3 se muestra como variante operativa en la misma evaluación. |
| Historia y covariables estáticas frente a la misma base con `d3` o con `b3` | Si el clima agrega información después de controlar por diferencias entre distritos. Coordenadas, elevación y cualquier otra covariable portable se fijan antes de la corrida. |
| Temperatura observada frente a placebo y anomalías, sobre la misma base distrital | Si la mejora supera la señal que se obtiene conservando la geografía y la época del año. El placebo usa otra fecha del mismo distrito y semana, elegida con una regla reproducible entre años previos disponibles; las ventanas de una misma serie se mantienen juntas y la SE 53 se documenta. Para `b3` hay además un placebo del bloque climático. |
| Exposición por centroide, área y población dentro de la misma variante | Cuánto cambia el resultado por la representación espacial, con un gráfico ALE o SHAP como diagnóstico del modelo. |
| CHIRTS nativo a 0,05° frente al mismo CHIRTS agregado a 0,25° | Cuánto aporta el detalle espacial por sí mismo, con las mismas máximas y mínimas, fechas, soporte válido, pesos y demás variables, y el aporte de la diferencia entre ambas escalas sobre el modelo que ya conoce la señal gruesa. |
| Calendario y geografía, con y sin clima y con y sin historia | Si el clima aporta cuando faltan los casos recientes y cuánto sigue aportando al agregarlos. Las variantes sin historia prescinden también del anclaje y de la mezcla con persistencia. |
| Historia corta frente a larga sobre las mismas filas evaluables | Cuánto aporta la historia adicional al entrenamiento y cuánto al calibrador, con confirmados y una especificación fija, primero en el comparador sin clima. El contraste original cambió a la vez entrenamiento y calibración. |

- **Ablación principal.** Dentro de cada contraste de variables, mismo diseño e hiperparámetros compartidos, mismos
  orígenes, etiquetas y cinco semillas. Se guardan el conteo bruto y publicado, la dispersión, la probabilidad cruda y
  calibrada, las filas de calibración y las predicciones por episodio.
- **Tuning simétrico.** `b3`, `d3` y el modelo sin clima se ajustan por separado con el mismo espacio, presupuesto de
  trials y temporadas de ajuste, con las temporadas de decisión fuera de la búsqueda. El presupuesto común se fija tras
  medir el costo de un bloque (el estudio original consumió hasta diez horas para la búsqueda de una sola variante). El
  contraste con parámetros compartidos sirve para atribución y el de tuning simétrico, para rendimiento.
- **Baselines en la tabla principal.** Persistencia determinista, ingenuo estacional y climatología, más persistencia
  probabilística ajustada cronológicamente sobre el último conteo relativo al umbral. Un GLM autorregresivo NB (o, si el
  ajuste falla bajo un criterio fijado de convergencia, el modelo estadístico alternativo predefinido), y Poisson y
  LightGBM sobre el mismo soporte. El contraste con y sin clima se replica en la familia estadística para responder la
  observación sobre XGBoost.
- **Entrenamiento separado de calibración.** Dos ventanas de entrenamiento con los mismos predictores e hiperparámetros,
  e idénticas etiqueta, regla de predictores y filas de evaluación. Las predicciones crudas fuera de muestra se comparan
  primero con una ventana de calibración común y, para cada modelo, calibración corta frente a larga cuando hay
  predicciones previas suficientes para las dos; los cortes documentan qué temporadas permiten cada contraste. Se
  reportan Brier y su descomposición, curvas de confiabilidad y precisión promedio (AP) por bloque, y un AP similar se
  interpreta según la variación entre temporadas y el margen fijado antes del análisis. Se reutilizan predicciones
  compatibles y solo se reentrenan los ajustes que faltan.
  [Contraste histórico](../../research/06_model_improvement/docs/mejora_modelo.md)

**Contraste de resolución.** Histórico CHIRTS y evaluación pareada con confirmados, covariables geográficas y cortes
comunes completos. La grilla fina mejoró modestamente el Brier frente a su versión gruesa; frente al comparador de
historia y geografía, h4 quedó muy cerca. [Resultados de resolución](../../research/08_v3_confirmed_cases/resultado_resolucion_chirts.md)

**Controles espaciales y ajuste.** Réplica de b3 y d3 con confirmados, geografía, placebos, anomalía y ALE completos. El
contraste cruzado atribuye el cambio en la comparación principalmente al criterio de disponibilidad meteorológica. Con
ajuste simétrico, b3 empata a h2 y empeora a h3 y h4 frente al comparador sin clima con geografía.
[Resultados y sensibilidades](../../research/08_v3_confirmed_cases/resultados_controles_espaciales.md)

**Salidas de la fase.** Predicciones auditadas, tablas con las mismas llaves y cortes, trazabilidad del tuning, evidencia
del placebo y resultados por temporada. Si la mejora no sobrevive al control espacial o si `b3` empata, la interpretación
del paper se actualiza con ese resultado.

## Fase 3. Evidencia del paper

| Bloque | Contenido |
|---|---|
| **Probabilidades** | Brier y habilidad relativa a climatología y persistencia probabilística, AP, log score, descomposición de Brier y diagnóstico de calibración. Rango operativo de probabilidades, endemicidad definida en entrenamiento, e inicios y continuaciones con denominadores explícitos. |
| **Alertas** | Curvas precisión–recall por horizonte y agrupadas con el punto de persistencia, comparación a la misma precisión y análisis de falsos avisos frente a inicios detectados. Beneficio neto o valor esperado para un rango explícito de costos. Un corte nuevo se seleccionaría en desarrollo y se evaluaría aparte. |
| **Conteos** | MAE y RMSE agrupados y por temporada, error en escala logarítmica, sesgo del conteo bruto y mezclado y resultados por estrato de incidencia. WIS con cuantiles comunes, cobertura y ancho de intervalos y diagnóstico de calibración de la distribución; cualquier recalibración se ajusta solo con bloques anteriores y se verifica fuera de muestra. Se explica qué media y dispersión usan la probabilidad y el intervalo. [Evaluación de pronósticos por intervalos](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1008618) |
| **Etiqueta** | La definición primaria se mantiene. A/B con confirmados, mínimos 1 y 5, una referencia robusta como Farrington y un umbral fijo de incidencia con denominador documentado, y cuántos positivos quedan determinados por el mínimo de casos. Los pronósticos de conteo se reutilizan cuando su entrenamiento es independiente de la etiqueta; el corte de conteos, las probabilidades y Platt se recalculan para cada alternativa. [Farrington mejorado](https://onlinelibrary.wiley.com/doi/abs/10.1002/sim.5595) |
| **Fuente e incertidumbre** | Las 3 445 coincidencias CSV–Sala de 2025, la comparación sin 2026 y retirando una temporada a la vez (incluida 2023), la variación por semilla y la incertidumbre con temporadas como bloques. Como sensibilidad, una estimación pareada con efectos de temporada y distrito, con cautela por el número de temporadas. Distritos y semillas son observaciones dependientes dentro de las temporadas. Las revisiones se miden con snapshots comparables si existen, y se declara qué queda sin medir. |
| **Inicios** | Brier frente a persistencia probabilística vinculado con la proporción de episodios detectados con al menos dos semanas de anticipación nominal, comparado a igual presupuesto de falsas alertas por distrito y temporada (cortes fijados en desarrollo, costo verificado en evaluación). También el punto operativo de la persistencia determinista, la variación entre temporadas y las estrategias de inicios ya probadas, identificando qué cifras son del estudio original. |

## Fase 4. Manuscrito de Piura y congelamiento

1. **Métodos y Resultados** con confirmados, exposiciones nuevas, cronología de selección, comparadores y veredictos; la
   tabla de criterios internos de aceptación y el rol experimental de la aplicación; referencias originales y vacío de
   literatura revisados, ampliados a unas 30 referencias pertinentes según el comentario 4; ecuaciones revisadas en el
   formato de entrega.
2. **Alcance de las conclusiones.** La afirmación de mayor beneficio durante El Niño sale del abstract, los aportes y la
   conclusión y queda como hipótesis: sostenerla como resultado exigiría clasificar periodos sin solape con un índice
   oficial y evaluar formalmente la interacción. El abstract y la conclusión se alinean con las tablas definitivas y con la
   pregunta climática original. Si los análisis pareados lo respaldan, la contribución metodológica es la distinción entre
   calibrar probabilidades, ordenar el riesgo y anticipar el inicio de episodios. Cada hallazgo se presenta con su
   comparador y su alcance temporal.
3. **Congelamiento** de la versión que va a validación externa **junto con su par sin clima y sus baselines**:
   predictores, pesos de exposición, parámetros de los modelos, calibradores, dispersión, mezcla, corte, periodo de
   entrenamiento, semillas, archivos y hashes. Las fichas y salidas congeladas originales se mantienen como referencia
   histórica. Una evaluación prospectiva requiere registrar externamente su protocolo antes de ver los desenlaces; el
   registro y los resultados prospectivos son entregables distintos.

**Salidas de la fase.** Paquete reproducible, tablas definitivas de Piura, revisión del equipo y especificación congelada
antes de evaluar otros departamentos. El paquete congelado es la [V4](../../models/registry/v4/ficha.md).

## Fase 5. Comparación externa

- **Prueba principal de transferencia.** La versión ajustada y congelada en Piura, con su par sin clima y sus baselines
  congelados, se aplica en Tumbes y Lambayeque en un periodo común verificable, sobre semanas objetivo posteriores al corte
  de entrenamiento del paquete. La historia local de casos construye los predictores y define el evento de cada distrito;
  la exposición se calcula con los polígonos y la población de destino aplicando la fórmula congelada. Árboles,
  calibradores, parámetros de distribución, pesos de la mezcla y decisiones aprendidas en Piura quedan fijos. Se audita la
  cobertura de covariables y el rango de los predictores en los destinos, y periodo, departamentos y métricas se eligen
  antes de ver el desempeño. Loreto puede ampliar el contraste si hay insumos equivalentes. Una lectura externa de años
  anteriores al congelamiento ajusta solo con Piura en cada corte retrospectivo y se reporta por separado.
- **Réplica metodológica secundaria.** Reentrenar en cada departamento con la receta, el presupuesto y los cortes fijados
  muestra cómo funciona el método al adaptarse a otra región; se reporta aparte de la transferencia del modelo congelado.
- **Datos.** CSV nacional de confirmados, límites y catálogos de cada departamento desde COD-AB, clima y denominadores
  equivalentes, y la Sala solo si hace falta extender el periodo común. El pipeline del producto está configurado para
  Piura. Piura sigue siendo el estudio principal y la validación externa se muestra por departamento y temporada,
  considerando que una epidemia regional puede afectar a varios departamentos a la vez.

**Salidas de la fase.** Tablas externas pareadas, cobertura documentada y una conclusión que distingue los resultados de
Piura, la transferencia y la réplica. [Transferencia al norte](../../research/08_v3_confirmed_cases/resultados_transferencia_norte.md)

## Trazabilidad de los comentarios

| Fase | Comentarios que atiende |
|---|---|
| Protocolo y diseño | 5, 16, 17, 18, 20, 23 |
| Geometría y clima | 6 en insumos, 8, 11 |
| Experimentos en Piura | 2, 11, 12, 16, 19, 21, 23, 29 |
| Métricas y sensibilidades | 7, 9, 14, 15, 17, 20, 21, 24, 25, 26, 27, 28 |
| Manuscrito y congelamiento | 0 como evaluación general, 1, 3, 4, 5, 13, 18, 22, 23, 30, 31, 32 |
| Validación externa | 6 |
| Fuera del alcance acordado | 10 |

### Comentarios atendidos en la V4 del manuscrito

Los números son los identificadores de los comentarios anclados en el Word. La V4 del manuscrito de Piura consolida el
análisis retrospectivo y conserva los 33 comentarios originales; tiene seis tablas, siete figuras, ecuaciones nativas de
Word y 41 referencias citadas. Las figuras y el cálculo por celda de los criterios internos se guardan en
`models/experimentos/mejora_modelo/v3_confirmados/manuscrito_piura/`. El suplemento acompaña la V4 con tablas S1–S11 y
dos figuras; sus datos, figuras, código y manifiesto se guardan en
`models/experimentos/mejora_modelo/v3_confirmados/manuscrito_piura/suplemento/`. Las tablas S10–S11 (cambios de
calibración por temporada y descomposición de Brier por modelo y horizonte) se reconstruyeron de los resultados
archivados de historia y calibración y del diagnóstico de probabilidades.

Los comentarios 6 y 31 dependen del paquete congelado para la transferencia externa y la validación prospectiva. El
comentario 10 mantiene el alcance acordado.

| Comentario de redacción | Integración en la V4 |
|---|---|
| 1, 5, 22 y 32 | Resumen, aportes y conclusión alineados con la comparación pareada. El Niño queda como hipótesis. |
| 13 | Ecuaciones del umbral, el conteo y la probabilidad en formato matemático editable. |
| 30 | Tabla VI con criterios internos y resultados por celda, y el rol experimental del dashboard. |

| Comentario | Evidencia disponible | Estado en la V4 |
|---|---|---|
| 2–4 · XGBoost, literatura y aporte [3 es MAJOR] | Estudios semanales comparables en Iquitos, Río de Janeiro y Vietnam, antecedentes regionales y fuentes metodológicas. El aporte se acota al contraste distrital pareado de Piura y a la evaluación de probabilidades y alertas; la justificación de XGBoost se apoya en su especificación y en los comparadores locales. | Integrado en Introducción, Métodos y Discusión. La V4 contiene 41 referencias, incluidas las fuentes de la revisión. |
| 7 · Cambio de fuente [MAJOR] | Solape de 2025 comprobado en 3 445 pares y sensibilidad sin 2026 para `d3`. | Integrado en Métodos y Resultados. Los archivos disponibles no permiten estimar el backfill histórico. |
| 8 · Exposición climática | Comparación de área y población, auditoría costera, cotejo con dos estaciones y candidato completo de ERA5 para los 65 distritos; resolución de CHIRTS, extremos térmicos y rango diurno. A h4, añadir el rango elevó el Brier medio en 0,71 % frente al punto medio de los extremos. [Resolución](../../research/08_v3_confirmed_cases/resultado_resolucion_chirts.md) · [Rango diurno](../../research/08_v3_confirmed_cases/resultados_rango_diurno_chirts.md) | Integrado en Métodos y Resultados, distinguiendo el brazo principal por punto de las exposiciones alternativas ponderadas. |
| 9 y 28 · Etiqueta [9 es MAJOR] | A/B con confirmados, mínimos de 1 y 5, percentil estacional robusto y ventanas recientes de 4, 8 y 12 semanas; probabilidades recalculadas para las alternativas estacionales y comparación de inicios; cortes de 5, 10 y 20 casos semanales por 100 000 habitantes con la serie INEI 2018–2026. [Sensibilidad de la etiqueta](../../research/08_v3_confirmed_cases/resultados_sensibilidad_etiqueta_confirmados.md), [incidencia fija](../../research/08_v3_confirmed_cases/resultados_sensibilidad_incidencia.md) | Integrado en Métodos, Resultados y la tabla V, con la sensibilidad de incidencia distinguida por su cobertura temporal. |
| 11 · Confusión espacial [MAJOR] | Geografía en el comparador, tres placebos térmicos, placebo conjunto, anomalías, ALE y cruce de geografía con disponibilidad. | Integrado en Resultados, con la figura ALE y el contraste de disponibilidad y geografía. |
| 12 · Equidad | Ajuste separado con presupuesto idéntico y temporadas comunes; contraste dentro de NB2 con y sin clima. | Integrado en Métodos y Resultados, con el presupuesto común y la frecuencia de ajustes de respaldo del NB2. |
| 16 · Calendario | Calendario uniforme y 60 cortes validados. 2024 se inspeccionó durante el desarrollo y 2008 carece de historial para calibrar. | Integrado en Métodos y en la serie temporal de la figura 6. |
| 17, 18 y 20 · Inferencia y decisiones | Cronología con commits, inventario de configuraciones, incertidumbre pareada por temporada, variación entre semillas y exclusiones. [Resultados](../../research/08_v3_confirmed_cases/resultados_historia_calibracion_comun.md) | Integrado en Métodos, la tabla II y Resultados, con la selección histórica de años y sus límites. |
| 19 · Baselines [MAJOR] | BSS contra persistencia probabilística y climatología en el calendario común; NB2, Poisson y LightGBM sobre el mismo soporte. | Integrado en las tablas III y IV y en la evaluación de alertas. |
| 21 · Historia y modelos estadísticos | Contraste factorial en el calendario común con Brier, AP, descomposición CORP y curvas de confiabilidad; GLM sobre las mismas semanas. [Resultados](../../research/08_v3_confirmed_cases/resultados_historia_calibracion_comun.md) | Integrado en las tablas de comparadores, la discusión y la tabla S10. |
| 23 · Elección del modelo [MAJOR] | `b3` principal, `d3` operativo y el par sin clima con cortes comunes y ajuste simétrico. | Integrado en la tabla III y la figura 4, con la selección original diferenciada del contraste retrospectivo. |
| 24 · Habilidad y estratos | BSS frente a persistencia y climatología, log score, descomposición de Brier, endemicidad, inicios y continuaciones, y calibración a riesgo alto. [Resultados](../../research/08_v3_confirmed_cases/resultados_historia_calibracion_comun.md) | Integrado en Resultados y en las tablas S3–S4 y S11 (calibración por horizonte, componentes CORP, log score y Brier, AP y BSS por fase del episodio y frecuencia previa de brote). |
| 14 y 26 · Intervalos y conteos | WIS, PIT, cobertura, ancho, recalibración cronológica y errores por estrato y temporada; uso de las dos medias y discordancia de sus reglas de aviso. [Resultados](../../research/08_v3_confirmed_cases/resultados_intervalos_conteos.md) | Integrado en Resultados, la tabla IV, las tablas S1–S2 y la figura S1 (histogramas PIT y coberturas nominales de 50 %, 80 % y 95 % por horizonte). |
| 29 · Clima con y sin historia de casos | Contraste factorial con cuatro brazos, cortes comunes y cinco semillas. [Resultados](../../research/08_v3_confirmed_cases/resultados_clima_sin_historia.md) | Integrado en Discusión como contribución predictiva. |
| 15, 25 y 27 · Beneficio neto, alertas e inicios | Curvas precisión–recall, sensibilidad a la precisión de persistencia, beneficio neto y episodios discordantes auditados. [Resultados de alertas](../../research/08_v3_confirmed_cases/resultados_alertas_revision.md) | Integrado en Resultados, las figuras 5 y 7, las tablas S5–S9 y la figura S2, con las políticas de corte, los costos observados y las estrategias de inicio. La validación prospectiva de la política de alertas sigue pendiente. |

El mayor trabajo de datos de la revisión es reconstruir la exposición ERA5-Land y preparar los departamentos externos, y
el mayor costo de cómputo, la búsqueda simétrica. Cada fase conserva evidencia suficiente para aceptar un resultado
favorable, un empate o uno desfavorable sin cambiar la regla después de mirar las cifras.
