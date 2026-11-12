# Intervalos de conteos en la revisión del paper

Se evaluaron pronósticos archivados de nueve métodos en las seis temporadas decisivas y los horizontes de dos, tres y cuatro semanas, con 20 410 filas por horizonte y las mismas observaciones para todos. Se compararon WIS, ancho y cobertura de intervalos, PIT y errores de conteo puntuales. Los modelos con cinco semillas se resumen por la mediana en cada temporada. Cada temporada tiene el mismo peso en la tabla conjunta. [Protocolo](protocolo_intervalos_conteos.md)

## Cobertura y recalibración fuera de muestra

La distribución de referencia del intervalo publicado usa NB2 con la media de conteo mezclada con persistencia y la dispersión del regresor. La recalibración PIT por nivel aprende con pronósticos de temporadas anteriores y emplea el nivel del conteo pronosticado al emitir. Se verificaron los 450 cortes de calibración y se reprodujeron exactamente los límites al 80% de la fórmula del servicio. Los cuantiles se verificaron con la formulación equivalente de WIS por pérdidas de cuantiles. [WIS de Bracher et al.](https://doi.org/10.1371/journal.pcbi.1008618)

| Pronóstico a cuatro semanas | WIS base → por nivel | Cobertura nominal 80%, todas las semanas | Cobertura nominal 80%, semanas de brote | Ancho medio del 80%, todas las semanas |
|---|---:|---:|---:|---:|
| b3 | 2,930 → 2,769 | 93,5% → 93,9% | 63,7% → 66,6% | 12,08 → 13,31 |
| d3 | 2,993 → 2,831 | 93,9% → 94,0% | 66,1% → 67,4% | 13,11 → 13,06 |
| Historia y geografía | 3,293 → 2,864 | 94,2% → 93,7% | 68,7% → 67,1% | 14,37 → 12,73 |
| Persistencia NB2 | 4,386 → 3,709 | 90,3% → 92,0% | — | 11,82 → 22,37 |

Para b3, el WIS relativo pareado mejoró 5,24%, 4,11% y 3,25% en h2, h3 y h4. A h4 mejoró en cuatro de seis temporadas. Empeoró en 2015 y 2016. La recalibración global cambió poco el WIS de b3 y d3. En historia y geografía, la recalibración por nivel mejoró WIS en las seis temporadas de h4, pero bajó la cobertura en semanas con brote. Los promedios de WIS de la tabla y el cambio relativo pareado son agregaciones distintas.

La cobertura total oculta una diferencia fuerte por fase. Para b3 a h4, la cobertura sin brote se mantuvo cerca de 97,4%. En semanas de brote, todos los errores del intervalo al 80% quedaron por encima del límite superior y la recalibración redujo esa proporción de 36,3% a 33,4%. El intervalo se ensanchó en ese estrato de 47,23 a 52,78 casos. La cobertura en un subconjunto definido por los casos observados describe dónde falla el pronóstico y se interpreta junto con el PIT y el WIS. La naturaleza discreta del conteo y la abundancia de ceros también influyen en la cobertura de intervalos inclusivos.

La recalibración por nivel mejora WIS, pero la cobertura de semanas de brote a cuatro semanas permanece por debajo del 80% nominal. Los intervalos quedan como un resultado retrospectivo con incertidumbre insuficiente durante picos, y el ajuste queda como candidato de evaluación.

### WIS y aporte meteorológico

Con los mismos intervalos NB2 alrededor del conteo publicado, b3 obtuvo un WIS h4 menor que historia y geografía en seis de seis temporadas y mejoró 8,91% en la media pareada de cambios relativos. Al aplicar la recalibración por nivel a ambos brazos, la diferencia quedó en 1,24% a favor de b3 y cuatro de seis temporadas. El análisis de probabilidades de brote conserva su comparación de Brier. La magnitud de casos, el intervalo y la alerta responden a resultados de evaluación distintos.

## Sesgo y error puntual

A h4, la razón de MAE de b3 publicado frente a persistencia fue 0,88 al dar el mismo peso a cada temporada y 0,77 al agrupar las semanas. El MAE en escala log1p promedió 0,282. Para b3, el conteo bruto estimó en promedio el 54,4% de los casos observados en semanas de brote y el publicado estimó el 59,5%, como promedio de razones por temporada. Fuera de brote las razones fueron 147,7% y 146,0%. El patrón de subestimación durante brotes y sobreestimación fuera de ellos ya aparece en el conteo bruto y la mezcla lo atenúa en el promedio.

Como contraste adicional, con el calendario estacional común en 2025 las razones de MAE frente a persistencia a h4 fueron 1,96 para b3, 1,90 para d3 y 1,54 para historia y geografía. En 2024 fueron 0,88, 1,01 y 1,43, respectivamente. Las tablas conservan los resultados por estrato de incidencia, semilla y temporada.

## Probabilidad de brote, intervalo y conteo publicado

V3 calcula la probabilidad a partir de la media bruta y la dispersión NB2, luego ajusta esa probabilidad con Platt. El intervalo se obtiene alrededor del conteo mezclado y con la dispersión del regresor. También difieren las reglas que deciden un aviso. El corte de probabilidad opera sobre la posibilidad de exceder el umbral, mientras que la regla de conteo compara directamente su media con el umbral. En el b3 evaluado, a cuatro semanas se observaron 1 080 discordancias entre ambas reglas de aviso en 20 410 semanas distritales, usando medianas por temporada. En esas semanas, el conteo publicado cruzó la regla de brote y la probabilidad quedó por debajo de 0,50. Una salida probabilística unificada podría extraer la probabilidad de brote y los cuantiles de la misma distribución y requeriría evaluar de nuevo la calibración de la alerta.

Se guardaron 12 348 celdas de evaluación de distribuciones, 6 048 celdas de conteo, mapas PIT por corte y las figuras en `models/experimentos/mejora_modelo/v3_confirmados/intervalos_revision/`. MLflow registró la corrida como `d3eea7aa962547b0b2c18b3c185dd408`. La evaluación se reproduce con `code/evaluate_count_intervals.py` y las figuras y tablas con `code/summarize_count_intervals.py`.
