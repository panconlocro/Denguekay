# Sensibilidad de la etiqueta de brote con casos confirmados

Comparación retrospectiva definida antes de calcular los nuevos resultados, el 10 de noviembre de 2026. El objetivo principal sigue siendo la semana con casos por encima del nivel esperado para la época. Todas las etiquetas se calculan por distrito con la misma serie confirmada y se comparan sobre las mismas semanas objetivo del calendario común.

| Variante | Referencia | Mínimo |
|---|---|---:|
| Principal | Media + 1,5 DE muestrales de la misma SE en cinco años anteriores | 2 |
| A | Media + 2 DE muestrales de la misma SE en cinco años anteriores | 2 |
| B | Media + 1,5 DE muestrales de la misma SE en tres años anteriores | 2 |
| Mínimo 1 y mínimo 5 | Umbral estacional principal | 1 o 5 |
| Estacional robusta | Percentil 75 de las cinco observaciones de la misma SE en los años anteriores. Con cinco datos es el segundo valor más alto y resiste un único extremo superior. | 2 |
| Aumento reciente | Media + 1,5 DE muestrales de las ocho semanas completas anteriores a la semana objetivo. Cuatro y doce semanas son sensibilidades. | 2 |

Se exige superar el umbral de forma estricta y alcanzar el mínimo entero de casos. En las variantes estacionales se conserva la convención de sumar la SE 53 a la SE 52 en el histórico. En las ventanas recientes se conservan las semanas reales en su orden, también al cruzar de año. Los cortes elegidos para una alternativa de etiqueta sirven como prueba de sensibilidad. Se reporta la prevalencia de cada etiqueta y la fracción de umbrales en cero.

## Comparación de etiquetas e inicios

- Comparar cada alternativa con la principal en semanas positivas y discordantes, por temporada y en las seis temporadas decisivas. Informar cuántas semanas positivas quedan con el mínimo de casos como umbral entero efectivo y cuántas semanas con un caso quedan fuera por el mínimo.
- Usar la definición de episodios del estudio. Unir semanas positivas con pausas de hasta dos semanas y considerar limpios los inicios precedidos por al menos ocho semanas sin un episodio. Emparejar inicios limpios por distrito y hasta cuatro semanas de distancia. Informar cuáles son exclusivos, cuántos coinciden, cuál etiqueta aparece antes y cuántos inicios pertenecen a episodios con una sola semana positiva. La tolerancia de emparejamiento describe concordancia temporal entre etiquetas observadas.
- Guardar el conjunto completo por semana y tablas por temporada. La decisión principal se resume sobre 2010, 2015, 2016, 2022, 2023 y 2026. El conjunto temporal entero se utiliza para dar continuidad a los episodios y la calibración.

## Sensibilidad de los pronósticos

Reutilizar el conteo bruto, la dispersión NB2 y el conteo publicado de las tres variantes ajustadas de la revisión. La salida de conteo se ajustó con conteos y predictores que se conservan, de modo que el cambio de etiqueta modifica la probabilidad de exceder el umbral. Usar solo las variantes de umbral conocido al origen, con sus mínimos respectivos. Recalibrar Platt en cada variante y bloque con predicciones previas fuera de muestra cuyas etiquetas ya hayan cerrado al primer origen de ese horizonte. Reconstruir la persistencia probabilística con el mismo mínimo entero y su propia calibración. Reproducir las probabilidades del principal antes de interpretar las alternativas.

Comparar Brier y AP dentro de cada etiqueta, con diferencias de Brier por semilla, horizonte y temporada. Tomar primero la mediana de las semillas y promediar las seis temporadas con peso igual. Informar sensibilidad sin 2026. Las variantes recientes se evalúan como etiquetas observadas. En h2–h4 una parte de la ventana reciente de la semana objetivo aún es futura al emitir. Evaluar un pronóstico de ese aumento requiere una especificación que modele la trayectoria de casos o el evento directamente.

El umbral fijo de incidencia del plan requiere una serie de población distrital compatible con el calendario. Su elección y validación se tratan en un análisis posterior.
