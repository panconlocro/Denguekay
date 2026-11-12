# Alertas e inicios en la revisión del paper

Se reutilizaron las probabilidades archivadas de b3, d3 y XGBoost de historia y geografía, y las reglas de persistencia del calendario de confirmados. Los resultados son retrospectivos. Se verificó la alineación por distrito, fecha, horizonte, origen y etiqueta. La reevaluación de b3 y persistencia probabilística reprodujo el tiempo de aviso de cada episodio de la corrida de cortes ajustados.

## Precisión y sensibilidad para semanas de brote

En las seis temporadas decisivas, la persistencia determinista aplica el umbral epidemiológico de la semana objetivo al último conteo conocido. Para cada modelo y semilla se toma la máxima sensibilidad alcanzable con una precisión al menos igual a la de la persistencia determinista. Se conservan juntos los empates de puntaje y se toman medianas entre semillas. El punto de precisión comparable se identifica con las etiquetas de evaluación y se interpreta como capacidad retrospectiva de ordenar semanas por riesgo. La figura muestra la mediana de la mejor precisión alcanzable para al menos cada valor de sensibilidad. El panel conjunto agrupa filas de los tres horizontes. Esas filas incluyen semanas objetivo repetidas y el panel describe un resumen de los tres horizontes.

| Horizonte | Precisión de referencia | Sensibilidad de la persistencia determinista | b3 | d3 | Historia y geografía |
|---|---:|---:|---:|---:|---:|
| h2 | 79,04% | 76,22% | 76,67% | 76,86% | 76,60% |
| h3 | 75,33% | 72,15% | 72,49% | 72,53% | 73,40% |
| h4 | 71,51% | 67,82% | 69,19% | 69,07% | 71,31% |
| h2–h4 | 75,31% | 72,06% | 72,34% | 72,80% | 73,56% |

A h4, b3 gana 1,37 puntos porcentuales y el modelo de historia y geografía 3,50 puntos con la precisión de referencia en el conjunto. Por temporada, la diferencia de sensibilidad de b3 a h4 es positiva en cinco de seis y cae 27,91 puntos en 2026. La precisión fijada para cada comparación por temporada es la alcanzada por la regla determinista en esa temporada. Los rangos de sensibilidad se reportan junto con el resultado conjunto. [Método de curvas precisión–recall](https://doi.org/10.1145/1143844.1143874)

## Inicios que se ganaron o perdieron

Se aplicaron los cortes escogidos en desarrollo bajo el objetivo de un falso aviso por distrito y 52 semanas, con la misma regla para b3, d3, historia y geografía y persistencia probabilística. Se incluyó la persistencia determinista en su punto original. En h4 se evaluaron 102 inicios con al menos ocho semanas previas sin brote. La anticipación mínima fue de dos semanas nominales. Se sumaron las medianas de las cinco semillas por temporada.

| Método | 2022, inicios / FP | 2023, inicios / FP | 2026, inicios / FP | Total, inicios / FP |
|---|---:|---:|---:|---:|
| b3 | 8 / 139 | 31 / 191 | 10 / 37 | 49 / 367 |
| d3 | 12 / 229 | 32 / 189 | 9 / 32 | 53 / 450 |
| Historia y geografía | 15 / 249 | 33 / 191 | 8 / 34 | 56 / 474 |
| Persistencia probabilística | 7 / 227 | 9 / 119 | 13 / 65 | 29 / 411 |
| Persistencia determinista | 7 / 176 | 7 / 104 | 8 / 21 | 22 / 301 |

Comparando b3 frente a historia y geografía, con detección en al menos tres de cinco semillas, hubo **11 inicios exclusivos del modelo sin clima y 3 exclusivos de b3** con los cortes ajustados. De los 11 exclusivos de historia y geografía, en 10 el último conteo al origen de la predicción para la semana de inicio estaba por debajo del mínimo de casos de la semana objetivo. En seis era cero. A corte fijo de 0,50 hubo 23 inicios exclusivos de historia y geografía y ninguno exclusivo de b3. Estos contrastes caracterizan episodios concretos con los cortes respectivos. Los costos observados difieren entre métodos. La lista de distritos, semanas y tiempos de alerta por semilla se conserva en `inicios_comparados.csv`.

### Estrategias probadas en el estudio original

| Estrategia | Resultado histórico |
|---|---|
| Ponderar por cinco las filas cercanas a inicios | Aumentó 7,8 puntos la proporción anticipada en h2 y 4,7 puntos en h3 y h4. Bajó AP en las cinco temporadas analizadas en cada horizonte. |
| Ponderar por temporada | F1 y AP dentro del empate. La anticipación bajó entre 2,6 y 3,6 puntos. |
| Entrenar dos modelos por régimen | La anticipación cayó 18,1 puntos en h3 y la sensibilidad en semanas de brote nuevo quedó entre 0 y 6%. |
| Agregar contexto espacial al modelo único | La anticipación aumentó 3,1 puntos en h2 y h4 y 1,6 en h3. Bajó la sensibilidad de las continuaciones en 2010 y 2015 a h4. |

Las cifras corresponden al estudio original. Ninguna estrategia superó su regla de adopción. [Experimentos de inicios](../06_model_improvement/docs/mejora_modelo.md#fase-3--inicios-de-brote-3a1-3a2-y-3b-2026-11-03)

## Beneficio neto para alertas semanales

Para cada horizonte y temporada de evaluación de cortes, se calculó `(VP − FP × costo_FP/costo_FN) / número de semanas distritales`. Para los métodos probabilísticos se evaluaron 46 cortes entre 0,05 y 0,50, que corresponden a razones de costo de 1/19 a 1. La persistencia determinista mantiene su regla de casos. Son escenarios de costo relativo para alertas de semanas, con 0 como beneficio de nunca emitir un aviso. [Análisis de decisión de Vickers y Elkin](https://pmc.ncbi.nlm.nih.gov/articles/PMC2577036/)

A h4, b3 supera a la persistencia probabilística en 36 de los 46 valores en 2022, en los 46 en 2023 y en ninguno en 2026. Frente a persistencia determinista, la supera en 31, 38 y 9, respectivamente. La utilidad simulada depende tanto de la temporada como del costo relativo.

## Hipótesis de corrección distrital

Como diagnóstico descriptivo de b3 a h4, se calculó por distrito y temporada el promedio de la etiqueta menos la probabilidad y se tomó la mediana entre semillas. La correlación de rangos de Spearman entre pares de temporadas fue 0,20 para 2022–2023, 0,11 para 2022–2026 y 0,16 para 2023–2026. Hay poca estabilidad del orden distrital del sesgo observado en esos tres bloques. Una corrección distrital se podría evaluar como sensibilidad mediante un desplazamiento regularizado del logit aprendido de predicciones anteriores fuera de muestra. El diagnóstico por sí solo cuantifica la estabilidad observada.

Las figuras y tablas se guardaron en `models/experimentos/mejora_modelo/v3_confirmados/cortes_alerta/precision_sensibilidad/`. Se reproducen con `code/evaluate_revision_alerts.py`.
