# Falsos avisos por distrito y semana

Diagnóstico retrospectivo de los cortes ajustados de b3 y persistencia probabilística en h4. El conjunto contiene 10 205 semanas distritales en 2022, 2023 y 2026. Se usa el corte asociado al objetivo de un falso aviso por distrito cada 52 semanas de desarrollo. Para que las distribuciones sumen exactamente, se promedian los recuentos entre las cinco semillas en cada grupo. Por eso el total de b3 aquí es 371. En la comparación operativa previa fue 367 al sumar medianas por temporada. La persistencia da 411 con ambas agregaciones. Se verificó la reproducción exacta de falsos avisos y verdaderos positivos por método, semilla y temporada.

## Dónde se concentran

| Situación del distrito en la temporada objetivo | Distritos × temporadas | Falsos avisos de b3 | Falsos avisos de persistencia |
|---|---:|---:|---:|
| Sin casos registrados durante la temporada | 46 | 0 | 0 |
| Casos registrados, sin semanas sobre el umbral de brote | 46 | 24,2 | 20 |
| Al menos una semana sobre el umbral de brote | 103 | 346,8 | 391 |

El 93,5% de los falsos avisos de b3 cayó en distritos con alguna semana de brote en esa misma temporada. Al clasificar los distritos usando solo la historia disponible al primer origen de cada temporada, el 96,8% cayó en distritos con al menos una semana de brote previa. Los tres distritos sin casos registrados en toda la serie de 2000–2026 fueron Lagunas, Montero y Sicchez. Ninguno recibió falsos avisos en las tres temporadas. La serie histórica conserva la convención de imputar cero donde el archivo temprano no tiene filas explícitas, dentro de su periodo cubierto. La categoría describe el registro de confirmados.

b3 tuvo algún falso aviso en 52 de 65 distritos en alguna de las cinco semillas. Los cinco distritos con más acumulan el 23% de sus falsos avisos. Los tres primeros fueron La Matanza, Buenos Aires y Máncora, con 22, 18 y 16,2 respectivamente en promedio entre semillas.

## Cuándo ocurren

| Posición de la semana objetivo dentro del mismo distrito | b3 | Persistencia |
|---|---:|---:|
| Una o dos semanas antes de un episodio | 68,8 | 56 |
| Pausa sin etiqueta positiva dentro de un episodio | 90,0 | 92 |
| Una o dos semanas después de un episodio | 59,6 | 74 |
| A dos semanas o menos tanto de un final como de un inicio | 13,0 | 11 |
| A más de dos semanas de cualquier episodio | 139,6 | 178 |

El 62,4% de los falsos avisos de b3 cayó dentro de una pausa o a dos semanas o menos de un episodio. En las 713 semanas negativas de ese entorno hubo 231,4 falsos avisos de b3 en promedio, aproximadamente 32 por cada 100 semanas. A más de dos semanas, hubo 139,6 entre 7 929 semanas negativas, aproximadamente dos por cada 100. Los episodios se construyen uniendo semanas positivas separadas por hasta dos semanas negativas.

Con el conteo de casos como referencia, el 48,6% de los falsos avisos de b3 cayó en semanas con casos que quedaron por debajo del criterio de brote. El 29,2% cayó en semanas sin casos cuyo siguiente registro positivo llegó en una o dos semanas, el 8,1% en tres o cuatro semanas y el 14,1% cayó en semanas con cero casos tanto en la semana objetivo como en las cuatro siguientes. La secuencia se establece con los casos observados después de emitir el pronóstico y se usa para explicar los errores.

En 2023, b3 generó 45,8 falsos avisos en las dos semanas objetivo anteriores al inicio de episodios, frente a 18 de persistencia. En 2026 fueron 3 y 10, respectivamente. En el conjunto, 24 falsos avisos semanales de b3 en promedio cayeron dentro de la ventana previa de un inicio limpio elegible, frente a 15 de persistencia. El mismo aviso puede contar como falso para la semana objetivo y contribuir a detectar el inicio posterior en la métrica de anticipación. Ambos recuentos conservan sus definiciones.

## Implicación para modelos por distrito

Al primer origen de 2022, 16 distritos tenían cero episodios anteriores según la etiqueta y 31 tenían menos de cinco, incluyendo esos 16. El distrito mediano tenía cinco episodios. Entrenar un modelo independiente por distrito exigiría estimar relaciones con pocos episodios en casi la mitad de los distritos. Una prueba de ajuste distrital podría compartir el modelo regional y estimar una corrección local de riesgo con regularización, usando solo historia disponible y comparando la anticipación y las falsas alarmas sobre las mismas filas. El patrón temporal también justifica medir avisos repetidos alrededor de un episodio y distinguir un aviso nuevo de una actualización operativa. [Modelos multinivel de Gelman y Hill](https://www.cambridge.org/highereducation/books/data-analysis-using-regression-and-multilevel-hierarchical-models/32A29531C7FD730C3A68951A17C9D983/multilevel-linear-models-varying-slopes-non-nested-models-and-other-complexities/40A537714D32360CC612FCCF3148E41F)

Las tablas por distrito, semana, posición de brote, proximidad de casos y fila de alerta se guardaron en `models/experimentos/mejora_modelo/v3_confirmados/cortes_alerta/diagnostico_falsos_avisos/`. Se reproducen con `code/diagnose_alert_false_positives.py`.
