# Sensibilidad de la etiqueta con casos confirmados

Se compararon nueve definiciones sobre las mismas 64 935 semanas distritales del calendario común. Los resultados principales de esta página usan las seis temporadas decisivas y sus 20 410 semanas distritales. Los conteos describen las etiquetas bajo cada regla. Los inicios se cuentan sobre la serie continua y se asignan a la temporada por su fecha. La comparación no utiliza un catálogo independiente de brotes confirmados. [Protocolo](protocolo_sensibilidad_etiqueta_confirmados.md)

## Semanas e inicios que marca cada regla

| Definición | Semanas elevadas | Prevalencia | Añadidas / retiradas vs principal | Inicios limpios | Inicios de episodios con una semana elevada |
|---|---:|---:|---:|---:|---:|
| Principal | 2 632 | 12,90% | 0 / 0 | 209 | 58 |
| A, +2 DE y cinco años | 2 504 | 12,27% | 0 / 128 | 205 | 62 |
| B, +1,5 DE y tres años | 2 878 | 14,10% | 342 / 96 | 207 | 58 |
| Mínimo de un caso | 3 269 | 16,02% | 637 / 0 | 268 | 116 |
| Mínimo de cinco casos | 1 907 | 9,34% | 0 / 725 | 166 | 35 |
| Estacional Q75 | 3 457 | 16,94% | 825 / 0 | 222 | 61 |
| Reciente de cuatro semanas | 1 242 | 6,09% | 347 / 1 737 | 307 | 155 |
| Reciente de ocho semanas | 1 388 | 6,80% | 401 / 1 645 | 286 | 107 |
| Reciente de doce semanas | 1 513 | 7,41% | 451 / 1 570 | 265 | 85 |

Con la regla principal, en **1 714 de las 2 632 semanas elevadas (65,1%)** bastan dos casos para satisfacer el umbral entero efectivo. El mínimo deja fuera otras 637 semanas con un solo caso que habrían superado su umbral estacional. En 13 729 de las 20 410 semanas (67,3%) la referencia estacional dio un umbral de cero. Los ceros provienen de la serie confirmada y de la convención de cobertura histórica del estudio.

La ventana de ocho semanas marca **47,3% menos semanas elevadas** y **36,8% más inicios limpios**. Con una tolerancia de cuatro semanas y dentro del conjunto de temporadas decisivas, coinciden 167 inicios por distrito entre las dos etiquetas. De ellos, 143 coinciden en la misma semana, 22 aparecen primero con la ventana reciente y dos aparecen después. Quedan 42 inicios exclusivos de la etiqueta principal y 119 de la reciente bajo esa tolerancia. En 2026, el total cambia de 20 a 40 inicios limpios y solo siete se emparejan. El patrón concuerda con una señal que responde a subidas recientes y puede perder semanas elevadas cuando las incorpora a su ventana de referencia.

El percentil 75 estacional limita el efecto de la observación más alta de los cinco años y conserva la comparación por semana epidemiológica. Marcó 825 semanas adicionales. En esta muestra, el mínimo de dos casos es el umbral entero efectivo en 78,8% de sus semanas positivas. Se interpreta como sensibilidad robusta simple, con fuerte influencia del mínimo en series escasas.

## ¿Se mantiene la comparación climática?

Se recalcularon las probabilidades de superar el umbral de las seis definiciones estacionales. Se conservaron los conteos y la dispersión de los pronósticos fuera de muestra y se reajustó Platt de forma cronológica. Se reprodujo el Brier de las 855 celdas calibradas de los tres XGBoost bajo la definición principal. El cambio porcentual de Brier se calcula por semilla y temporada, toma la mediana de semillas y da igual peso a las seis temporadas. Los valores positivos indican un Brier mayor para el modelo climático frente a historia y geografía.

| Etiqueta | b3, h2 | b3, h3 | b3, h4 | d3, h4 |
|---|---:|---:|---:|---:|
| Principal | +0,01% | +3,68% | +5,28% | +4,43% |
| A | +0,48% | +3,70% | +5,14% | +4,22% |
| B | −0,02% | +3,75% | +5,82% | +4,17% |
| Mínimo de un caso | −0,47% | +2,81% | +4,39% | +3,38% |
| Mínimo de cinco casos | +0,33% | +2,38% | +3,02% | +2,78% |
| Estacional Q75 | −0,20% | +3,30% | +5,72% | +4,98% |

A h2 la diferencia de b3 es pequeña y cambia de signo según la definición. A h3 y h4, ambos modelos climáticos tienen mayor Brier en las seis definiciones estacionales y al retirar 2026. El resultado es condicional a los pronósticos de conteo archivados y a su selección retrospectiva. Los Brier absolutos se interpretan dentro de cada etiqueta, dada la distinta prevalencia.

La ventana reciente se evaluó como etiqueta observada. Para anticipar a h2–h4 el exceso respecto de esas semanas se necesita pronosticar la trayectoria futura o el evento binario. La sensibilidad a incidencia fija se evaluó en las temporadas cubiertas por las proyecciones anuales del INEI. [Resultados de incidencia](resultados_sensibilidad_incidencia.md)

Las etiquetas, las tablas por temporada, los pares de inicios y el manifiesto de huellas se guardaron en `models/experimentos/mejora_modelo/v3_confirmados/sensibilidad_etiqueta_revision/`. Se reproducen con `code/evaluate_label_sensitivity.py`.
