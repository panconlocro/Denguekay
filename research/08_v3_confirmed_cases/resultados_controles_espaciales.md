# Controles espaciales y ajuste simétrico de b3 y d3

Evaluación retrospectiva con casos confirmados en 65 distritos de Piura. La pregunta sigue siendo cuánto aporta el clima al pronóstico distrital de brotes. b3 ocupa la fila principal porque fue la variante que adoptó la regla histórica. d3 se presenta como la variante operativa. Los resultados de esta revisión se reportan como retrospectivos porque las temporadas decisivas ya informaron decisiones anteriores del estudio.

Las tablas siguientes muestran el cambio porcentual de Brier calibrado. Un valor negativo favorece a la primera variante de cada fila. Se calcula el cambio pareado por semilla, se toma la mediana de las cinco semillas en cada temporada y se promedia con igual peso entre las seis temporadas decisivas. Esto puede dar un resultado ligeramente distinto del cociente entre los Brier medios de la tabla principal. Los tres horizontes se cuentan desde el origen nominal de los datos. Las temporadas decisivas son 2010, 2015, 2016, 2022, 2023 y 2026.

## Réplica histórica y cruce de geografía con disponibilidad

| Especificación de b3 y comparador sin clima de la misma geografía | h2 | h3 | h4 |
|---|---:|---:|---:|
| Reloj histórico, sin geografía | −1,24% | −1,06% | −1,14% |
| Reloj histórico, con geografía | −1,19% | −1,15% | −1,14% |
| Clima disponible al cierre, sin geografía | −0,03% | +0,86% | +1,21% |
| Clima disponible al cierre, con geografía | −0,14% | +0,41% | +0,91% |

Con los casos confirmados, b3 reproduce una mejora histórica pequeña con o sin las tres covariables geográficas. La mejora cambia al exigir que los predictores meteorológicos estén disponibles al cierre. Con el reloj histórico y geografía, h4 mejora 0,62% sin 2026. Con clima al cierre y geografía, h4 empeora 1,49% sin 2026. El cruce fue un seguimiento diagnóstico motivado por los controles originales. Distingue los dos cambios de especificación y queda condicionado a las covariables y al supuesto de publicación usados. Los archivos de ERA5-Land aportan temperatura y humedad de la coordenada distrital histórica. Se modeló una disponibilidad de siete días desde el cierre de la semana meteorológica y se aplicó un rezago de dos semanas a las ventanas semanales. Los datos del archivo histórico se usan como aproximación a los datos que habrían estado disponibles en cada fecha.

En la réplica con reloj histórico sin geografía, d3 cambia el Brier frente a historia en −0,03%, +0,27% y +0,12% en h2, h3 y h4. b3 mejora frente a d3 en 1,18%, 1,35% y 1,26%. Este resultado usa parámetros heredados compartidos y preserva la alineación histórica.

## Placebos, anomalía y respuesta térmica

| Comparación con clima al cierre | h2 | h3 | h4 | h4 sin 2026 |
|---|---:|---:|---:|---:|
| b3 observado vs mediana de tres placebos de temperatura | −0,32% | −0,28% | −0,13% | +0,34% |
| b3 observado vs placebo de todas las covariables climáticas | −1,57% | −1,22% | −1,02% | −0,12% |
| d3 observado vs placebo de las cuatro ventanas de temperatura | −0,49% | −0,66% | −0,43% | +0,16% |
| b3 con anomalía térmica vs historia y geografía | +0,72% | +1,23% | +1,28% | +1,39% |

El placebo térmico de b3 conserva el distrito y la semana epidemiológica y cambia el año de la temperatura. De los tres calendarios donantes, el cambio a h4 va de −0,60% a +0,68%. Excluyendo 2026, el efecto de b3 frente a la mediana placebo cambia de signo en los tres horizontes. El placebo conjunto deja una diferencia de apenas 0,12% a h4 al excluir 2026. Son contrastes descriptivos sobre un conjunto finito de calendarios placebo y temporadas.

El gráfico ALE de b3 a h4 resume la respuesta de su probabilidad cruda en las 3 380 filas distritales de la temporada 2023, semilla 17. Los deciles se calcularon en las 59 540 filas de entrenamiento y todas las filas evaluadas quedaron dentro de su rango térmico. La curva es aproximadamente plana por debajo de 19,6 °C y crece hacia el extremo cálido. El recorrido total es de 3,97 puntos porcentuales entre el mínimo y máximo de la curva centrada. Esta visualización describe cómo usa la temperatura un ajuste de b3, dentro del soporte de entrenamiento. Su lectura complementa el placebo. [Método ALE de Apley y Zhu](https://academic.oup.com/jrsssb/article/82/4/1059/7056085)

## Comparación con ajuste independiente e idéntico presupuesto

Se evaluaron 17 configuraciones por brazo, con los mismos cortes y la misma semilla de desarrollo. Los cuatro mejores candidatos Sobol y los parámetros heredados avanzaron al segundo tramo. Se eligió el menor Brier relativo al de la configuración heredada dentro de cada brazo. Historia y geografía conservó los parámetros heredados. b3 y d3 eligieron `sobol_09`, con mejoras de 0,40% y 0,87% respectivamente en su objetivo de desarrollo. Luego se hicieron 300 ajustes en evaluación, con 20 cortes y cinco semillas por brazo.

| Brazo vs historia y geografía | h2 | h3 | h4 | h4 sin 2026 |
|---|---:|---:|---:|---:|
| b3 ajustado | +0,01% | +3,68% | +5,28% | +6,37% |
| d3 ajustado | +0,46% | +3,12% | +4,43% | +6,06% |

A h4, los Brier medios de las medianas por temporada fueron 0,05488 para historia y geografía, 0,05859 para b3 y 0,05835 para d3. Las precisiones promedio fueron 0,71434, 0,71436 y 0,70867, respectivamente. El deterioro a h4 ocurrió en cuatro de seis temporadas para ambos brazos climáticos. En 2023, b3 y d3 empeoraron 10,79% y 11,60% frente a historia y geografía. En 2026, mejoraron 0,13% y 3,76%, respectivamente. Estas cifras no sostienen atribuir una mejora general al clima bajo la especificación evaluada.

El contraste de variables con parámetros fijos y el contraste de rendimiento con ajuste independiente se reportan por separado. El barrido en CPU fue más pequeño que la búsqueda histórica. Las seis temporadas decisivas quedaron fuera del objetivo nuevo de ajuste, pero el procedimiento sigue siendo una reevaluación retrospectiva. La selección de hiperparámetros reúne temporadas de desarrollo que son posteriores a algunas temporadas decisivas tempranas. La comparación prospectiva se reserva para un paquete congelado.

## Trazabilidad

- Réplica y controles. 12 brazos, cinco semillas y 194 805 filas por brazo y semilla sobre las mismas llaves, etiquetas y cortes. Se ejecutaron 1 100 ajustes nuevos y se reutilizó el comparador geográfico con huellas idénticas. Hubo cuatro sustituciones de SE 53 por SE 52 en cada calendario donante, 12 en total. Todos los años donantes preceden a los años originales. El bloque inicial 2008 se archiva y alimenta la calibración de bloques posteriores.
- Ajuste. 204 ajustes en el cribado, 150 para los finalistas y 300 en la evaluación. Se archivaron configuraciones, rankings, probabilidades crudas y calibradas, mezclas de conteos, métricas y contrastes por temporada.
- MLflow. Controles `db5cb4eaa5c34652b55c8ea25a13ab8a`, cruce de geografía y disponibilidad `8fea1929241f4fbca9315366f0b3aa9c` y ajuste `a5a1d000e66d4fadbcf94854f5f2d3be`. No hay una nueva versión congelada.

[Protocolo de controles](protocolo_controles_espaciales.md) · [Protocolo del cruce](protocolo_puente_geografia_disponibilidad.md) · [Protocolo de ajuste](protocolo_ajuste_simetrico.md)

## Persistencia y comparadores estadísticos en el mismo calendario

La persistencia probabilística usa el último conteo relativo al mínimo que activa la etiqueta objetivo y una calibración logística cronológica. La climatología usa frecuencias de brote históricas por distrito y época del año. Se compararon ambas sobre las 184 665 filas calibrables del calendario común. La tabla resume las seis temporadas decisivas. Cada BSS es una media de habilidades por temporada y no se obtiene tomando el cociente de los Brier medios publicados en la misma tabla.

| Variante | Brier h4 | AP h4 | BSS vs persistencia h2 | h3 | h4 | BSS vs climatología h4 |
|---|---:|---:|---:|---:|---:|---:|
| b3 principal | 0,05859 | 0,71436 | +0,46% | −2,78% | −1,86% | +43,67% |
| d3 operativo | 0,05835 | 0,70867 | +0,09% | −2,23% | −0,95% | +44,13% |
| XGBoost de historia y geografía | 0,05488 | 0,71434 | +0,35% | +0,65% | +2,86% | +46,17% |
| LightGBM de historia y geografía | 0,05518 | 0,71232 | +0,63% | +0,18% | +2,08% | +45,76% |
| Poisson GLM de historia y geografía | 0,05604 | 0,70765 | −1,24% | −1,69% | +0,44% | +44,56% |
| NB2 de historia y geografía | 0,05870 | 0,67900 | −3,58% | −5,46% | −3,41% | +42,32% |
| NB2 con clima y rezagos | 0,06469 | 0,67864 | −8,97% | −13,32% | −12,40% | +36,70% |
| Persistencia probabilística | 0,05950 | 0,67326 | 0,00% | 0,00% | 0,00% | +44,76% |
| Climatología | 0,11410 | 0,26597 | — | — | — | 0,00% |

La ganancia de XGBoost sin clima frente a persistencia es pequeña y heterogénea. El BSS es positivo en nueve de 18 celdas temporada × horizonte. b3 también supera a la persistencia en nueve celdas, pero el tamaño de las pérdidas deja un BSS medio negativo en h3 y h4. Brier y AP evalúan probabilidades y ordenamiento. La anticipación de inicios y el costo en falsas alertas se evalúan por separado.

El NB2 autorregresivo con clima empeoró el Brier frente al NB2 de historia y geografía en 4,78%, 6,87% y 7,74% en h2, h3 y h4. Sin 2026, el deterioro fue 7,42%, 9,57% y 10,38%. La regla de respaldo L2 se activó en 3 de 60 ajustes sin clima y 10 de 60 con clima. La especificación climática usa lluvia, humedad y Niño 1+2 junto con términos lineales y cuadráticos en cuatro ventanas térmicas. Este contraste comprueba la dirección del resultado en otra arquitectura con sus propios predictores climáticos y supuestos.

Para conteos, el MAE mezclado a h4 fue 3,86 casos por distrito-semana para b3, 3,97 para d3 y 4,00 para XGBoost de historia y geografía, frente a 4,98 de persistencia de conteos y 6,53 del ingenuo estacional. Se calculó MAE por semilla y temporada y se promedió la mediana de semillas sobre seis temporadas. Las métricas de conteo puntual y las probabilidades de brote tienen objetivos distintos. La calibración de intervalos y WIS se evaluarán sobre el archivo de pronósticos.

Los ajustes y predicciones del comparador se registraron en MLflow con el ID `da946fd93fc94e4595959795b67fdb92`. Las tablas `tabla_probabilidades.csv` y `tabla_conteos.csv` se reproducen con `code/summarize_revision_comparators.py`. [Protocolo de los comparadores](protocolo_benchmarks_confirmados.md)

## Comprobaciones del workspace

La suite general ejecutó 556 pruebas, con 32 omitidas y cinco fallos. El manifiesto de gold coincide por SHA-256 con el integrado de confirmados y difiere del integrado histórico que usan las pruebas de equivalencia. Los fallos son de comparación de umbral y predictores con gold, y de los hashes congelados de V1/V2. No se regeneraron los fixtures. En estas corridas se validaron gold y silver de confirmados con Great Expectations, las huellas de entradas y el soporte común de las predicciones. Las comprobaciones de soporte y calibración de los experimentos pasaron.
