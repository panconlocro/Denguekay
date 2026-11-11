# Borrador de respuesta a la revisión del short paper

Profesor, gracias por la revisión. Actualizamos el manuscrito con casos confirmados y presentamos `b3` como contraste climático principal. La V4 documenta el calendario común, los controles espaciales y temporales, los comparadores y la evaluación de alertas. El suplemento acompaña el manuscrito con las métricas por horizonte y los resultados de sensibilidad. A continuación mantenemos la numeración de sus comentarios.

0. **Evaluación general.** La revisión refuerza la comparación retrospectiva en Piura. La evidencia principal muestra que la contribución climática cambia al controlar la disponibilidad de las variables y al usar un comparador con historia y geografía. Distinguimos habilidad probabilística, ordenamiento del riesgo y utilidad de las alertas. La transferencia geográfica y la evaluación prospectiva siguen pendientes.

1. **Resumen.** Presentamos `b3` como el brazo elegido por la regla histórica y distinguimos a `d3` como variante operativa en el manuscrito. El resumen distingue el contraste con historia y geografía a parámetros fijos de la sensibilidad con ajuste simétrico e informa la comparación con persistencia probabilística. También acota el alcance de la detección temprana de episodios a los resultados observados.

2. **Elección de XGBoost.** En Métodos explicamos la capacidad de los árboles regularizados para representar interacciones y relaciones no lineales en un diseño pareado. Las tablas III y IV muestran el desempeño de LightGBM y los modelos de conteos sobre el mismo calendario. A cuatro semanas, los Brier medios del brazo sin clima fueron 0,0549 con XGBoost, 0,0552 con LightGBM y 0,0560 con Poisson.

3. **Literatura y aporte.** La Introducción ahora reconoce que Benedum y otros trabajos ya compararon predictores epidemiológicos y meteorológicos en pronósticos semanales. Añadimos estudios sobre el desafío de pronóstico de dengue, modelos estacionales y subnacionales, demoras de notificación, la epidemia peruana de 2023 y criterios de evaluación. El aporte se acota al contraste incremental distrital en Piura y a cómo se relacionan la calibración, el ordenamiento del riesgo y el costo de alertar.

4. **Referencias.** La V4 incorpora 41 referencias citadas en el manuscrito. Incluye 29 publicaciones en revistas científicas, cuatro artículos de congresos, una nota epidemiológica, seis fuentes institucionales y un capítulo sobre calibración. No se citaron tesis.

5. **Formulación de los aportes.** La Introducción presenta el diseño pareado, los controles de exposición y la distinción entre propiedades del pronóstico. La tabla II fecha las decisiones internas y los cambios de criterio. Se retiró la afirmación de un mayor beneficio durante El Niño.

6. **Validación externa. Pendiente.** La sensibilidad por incidencia ya usa proyecciones distritales oficiales del INEI para Piura. La transferencia se evaluará en Tumbes y Lambayeque después de congelar el paquete de Piura, su comparador sin clima y sus baselines. El manuscrito delimita sus conclusiones a Piura.

7. **Cambio de fuente.** Usamos casos confirmados de ambas fuentes y verificamos coincidencia en los 3 445 pares distrito–semana de 2025. En la evaluación con ajuste simétrico, al excluir 2026, el Brier a cuatro semanas aumentó 6,37% para `b3` y 6,06% para `d3` frente a historia y geografía. Declaramos la limitación de los archivos disponibles para estimar revisiones históricas de conteos y la posible influencia de cambios en vigilancia sobre la referencia de cinco años.

8. **Exposición climática.** Métodos y Resultados distinguen la medición en puntos distritales de los contrastes ponderados por población. Reportamos el cotejo en Piura y Talara con NOAA GSOD, las limitaciones de cobertura y resolución, y las pruebas con temperaturas máxima y mínima de CHIRTS. Añadir el rango diurno elevó 0,71% el Brier a cuatro semanas frente al punto medio de los extremos, en la sensibilidad correspondiente.

9. **Definición de brote.** Probamos el percentil 75 estacional como referencia robusta. El mínimo de dos casos determinó el corte entero efectivo en 1 714 de las 2 632 semanas elevadas. La tabla S4 separa las dos primeras semanas de los episodios de las semanas de continuación y reporta Brier, AP y BSS, con las mismas semanas negativas para ambos estratos.

10. **Horizonte efectivo. Fuera del alcance de esta revisión.** Definimos los horizontes de dos, tres y cuatro semanas respecto de la última semana publicada. La medición del desfase real y la extensión a otros horizontes quedan como preguntas separadas del análisis retrospectivo.

11. **Confusión espacial.** Incorporamos latitud, longitud y elevación al comparador, tres placebos de temperatura, un placebo del bloque climático, anomalías térmicas y una figura ALE. El cruce de especificaciones muestra cómo cambian los resultados al controlar la geografía y aplicar el criterio de disponibilidad de predictores. Los resultados con placebo debilitan la interpretación de una ganancia climática estable.

12. **Ajuste comparable.** Ajustamos por separado `b3`, `d3` e historia más geografía con el mismo espacio de 17 candidatos y las mismas temporadas de desarrollo. Presentamos ese ejercicio junto con el contraste de hiperparámetros compartidos. Incluimos una comparación adicional de NB2 con y sin clima, con términos rezagados de temperatura.

13. **Ecuaciones.** Las ecuaciones del umbral, el conteo y la probabilidad están compuestas en formato matemático editable de Word.

14. **Distribución de conteos.** La tabla IV muestra WIS y cobertura. Las tablas S1–S2 y la figura S1 muestran cobertura al 50%, 80% y 95% e histogramas PIT. Métodos distingue la media bruta usada para la probabilidad de excedencia de la media mezclada que centra el intervalo de conteos.

15. **Costos de alerta.** La figura 7 compara el beneficio neto de las reglas en distintos costos relativos de una falsa alerta y una semana elevada omitida. Los resultados cambian por temporada. Las tablas S7–S8 y la figura S2 complementan ese análisis con los costos observados para anticipar episodios.

16. **Calendario.** Rehicimos la evaluación con temporadas disjuntas de la semana epidemiológica 35 a la 34, recuperamos las semanas de 2024 y eliminamos la doble evaluación de 2025. Se aclara que 2024 se examinó durante el desarrollo. El bloque de 2008 aporta predicciones a la calibración posterior y queda fuera de las métricas calibradas. La figura 6 usa el calendario corregido.

17. **Inferencia.** La tabla II documenta cuándo se incorporaron las temporadas. La evidencia histórica permite reconstruir la secuencia de decisiones. El criterio exacto para reproducir la selección de las seis temporadas quedó sin documentar. Usamos Brier pareado con igual peso por temporada, mostramos la sensibilidad con efectos cruzados de temporada y distrito y declaramos la multiplicidad de la matriz histórica. Métodos enumera las ocho temporadas de la evaluación dejando una fuera.

18. **Prerregistro.** Retiramos el término del título y las afirmaciones de registro externo. La tabla II presenta las decisiones internas fechadas, sus commits, el cambio de F1 a Brier, la incorporación de 2026 y la elección operativa. Identificamos al menos 15 configuraciones distintas que se evaluaron en las seis temporadas históricas.

19. **Comparadores.** Las tablas III y IV incorporan persistencia probabilística, climatología, NB2, Poisson, LightGBM y las referencias de conteo. La tabla III reporta habilidad probabilística frente a persistencia y climatología.

20. **Remuestreo.** Usamos temporadas completas como unidad de remuestreo, preservamos el pareo y evaluamos la variación entre semillas. Los resultados muestran la sensibilidad al retirar 2026 o 2023, además del análisis con efectos cruzados. Seis temporadas limitan la precisión de las estimaciones.

21. **Modelos simples e historia larga.** Poisson figura en las tablas III y IV. Separamos la ventana de entrenamiento de la de calibración. La tabla S10 muestra el cambio de Brier y sus componentes CORP por temporada decisiva. A cuatro semanas, ampliar la historia de calibración con el entrenamiento fijo redujo 5,54% el Brier en promedio entre las cinco temporadas con ventanas distintas y mantuvo el orden de riesgo. Ampliar el entrenamiento con calibración expansiva aumentó el AP en 2,35 puntos porcentuales.

22. **El Niño.** Se retiró del resumen, los aportes y la conclusión la afirmación de que el clima aporta más durante El Niño. La Discusión lo plantea como hipótesis prospectiva. Métodos y Resultados distinguen las 12 variantes climáticas de las tres comparaciones adicionales entre configuraciones ya evaluadas.

23. **Elección del modelo.** `b3` es el análisis principal. `d3` conserva su rol de variante operativa histórica. La tabla III y la figura 4 muestran los dos brazos junto con el comparador sin clima, con el mismo presupuesto de ajuste y sobre el mismo calendario.

24. **Habilidad, calibración y estratos.** Reportamos habilidad frente a persistencia probabilística. Las tablas S3–S4 incluyen pendiente e intercepto por horizonte, eventos observados y esperados en pronósticos de al menos 0,30, y métricas por fase del episodio y frecuencia histórica de brotes. La tabla S11 muestra el log score y los componentes CORP de los brazos principales y las referencias probabilísticas a dos, tres y cuatro semanas.

25. **Alertas frente a persistencia.** La figura 5 y las tablas S5–S6 comparan la sensibilidad a igual o mayor precisión que la persistencia determinista. A cuatro semanas, en el conjunto de temporadas, `b3` alcanzó 69,19% de sensibilidad frente a 67,82%. En 2026 quedó 27,91 puntos porcentuales por debajo de persistencia a la precisión de esa temporada. La evaluación de políticas con cortes elegidos en desarrollo se reporta por separado.

26. **Conteos e intervalos.** Separamos los errores agrupados y por temporada y el sesgo antes y después de mezclar con persistencia. Para `b3` a cuatro semanas, la razón MAE frente a persistencia fue 0,88 al dar igual peso a cada temporada y 0,77 al agrupar semanas. En semanas de brote, la cobertura del intervalo nominal de 80% pasó de 63,7% a 66,6% después de recalibrar. Reportamos la cobertura que sigue por debajo del valor nominal en ese subconjunto.

27. **Anticipación de inicios.** Auditamos episodios detectados por un brazo y omitidos por otro. Las tablas S7–S8 y la figura S2 muestran cuántos inicios se anticiparon y el costo en falsas alertas bajo distintos cortes. La tabla S9 documenta las estrategias históricas de ponderación, regímenes y contexto espacial. La Discusión identifica posibles fuentes adicionales para pronosticar inicios.

28. **Sensibilidad de la etiqueta.** La tabla V incluye mínimos de uno y cinco casos y la referencia estacional robusta. También evaluamos cortes de 5, 10 y 20 casos semanales por 100 000 habitantes en las temporadas con denominadores distritales comparables del INEI.

29. **Clima con y sin historia de casos.** Cruzamos la presencia de historia epidemiológica y clima en cuatro brazos. Con historia de casos, añadir clima redujo 0,91% el Brier a cuatro semanas en promedio y lo elevó 0,08% al retirar 2026 en ese contraste. Sin historia, el clima mejoró el AP y empeoró el Brier. La Discusión relaciona estos resultados predictivos con el antecedente de Iquitos.

30. **Limitaciones y criterios internos.** La tabla VI explicita los criterios de alertas y conteos y cuántas celdas los cumplen. La Discusión explica el uso experimental del tablero y documenta el alcance geográfico, las limitaciones de vigilancia, la falta de datos de serotipo y vectores, y el uso de archivos retrospectivos.

31. **Evaluación prospectiva. Pendiente.** El equipo debe congelar y fechar el paquete de pronóstico y registrar externamente el protocolo antes de evaluar los desenlaces prospectivos. El diseño contemplará los comparadores, las métricas, los cortes de alerta y la hipótesis climática. Esta evaluación requiere pronósticos emitidos con fechas verificables.

32. **Conclusión.** La conclusión distingue el resultado del contraste climático de la mejora por historia de calibración y del desempeño operativo de las alertas. Acota la interpretación a las temporadas y horizontes retrospectivos evaluados en Piura.
