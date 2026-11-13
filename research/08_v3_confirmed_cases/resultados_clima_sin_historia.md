# Aporte del clima con y sin predictores de casos

Se ajustaron cuatro brazos de XGBoost Poisson con el mismo calendario, covariables geográficas, arquitectura, hiperparámetros, orígenes y etiqueta. El diseño cruza el bloque climático b3 con las variables de historia de casos. Todos los brazos producen conteo bruto sin margen ni mezcla con persistencia. Para la probabilidad, convierten el conteo a una excedencia NB2 del umbral histórico común y aplican Platt cronológico. Los brazos sin historia omiten los predictores de conteos. La definición del evento todavía usa los años anteriores, por lo que las métricas de conteo complementan la comparación binaria. [Protocolo](protocolo_clima_sin_historia.md)

## Qué agrega el clima

El cambio relativo de Brier se calcula por temporada y semilla, se toma la mediana de las cinco semillas y se promedian con igual peso las seis temporadas decisivas. Un cambio negativo de Brier o MAE indica una mejora. AP se muestra en puntos porcentuales.

| Contraste | Brier h2 | Brier h3 | Brier h4 | AP h4 | MAE h4 |
|---|---:|---:|---:|---:|---:|
| Añadir clima a calendario y geografía, sin predictores de casos | +4,23% | +3,42% | +2,89% | +3,51 pp | +0,10 |
| Añadir clima a calendario, geografía e historia de casos | −0,92% | −0,96% | −0,91% | +0,61 pp | −0,03 |
| Añadir historia de casos a calendario y geografía, sin clima | −57,22% | −49,52% | −42,91% | +40,30 pp | −1,92 |
| Añadir historia de casos a calendario, geografía y clima | −58,61% | −51,14% | −44,88% | +37,47 pp | −2,07 |

Sin predictores de casos, el clima elevó la AP h4 de 0,294 a 0,329, pero el Brier fue peor en cinco de seis temporadas. El modelo climático sin predictores de casos tampoco superó la climatología distrital como referencia probabilística en el resumen de las seis temporadas. A h4 su BSS fue −4,65%. Su MAE de conteo pasó de 6,15 a 6,26. Los resultados indican una mejora en el ordenamiento del riesgo con la meteorología, junto con errores mayores de probabilidad y conteo bajo esta especificación.

Con predictores de casos, el Brier h4 mejoró en tres de seis temporadas al incorporar clima. Al retirar 2026, la mejora promedio pasó de −0,91% a un empeoramiento de +0,08%, y el AP dejó de favorecer al modelo con clima. El aporte en Brier quedó prácticamente plano entre h2, h3 y h4. Sin predictores de casos y sin 2026, el cambio relativo h4 permaneció desfavorable (+1,52%). La diferencia absoluta media cambió ligeramente de signo al retirar 2026, dada la escala de los Brier por temporada.

Este contraste aporta evidencia sobre el valor predictivo incremental con y sin los conteos recientes. La mejora de AP por clima se atenúa al incorporar la historia. Para Brier y conteos, el clima sin predictores de casos ya mostraba resultados mixtos. La relación entre esos resultados y el uso de la historia es predictiva. El contraste no estima una mediación causal.

## Relación con estudios anteriores

Benedum et al. ya contrastaron el valor de la vigilancia y el clima para pronosticar dengue semanal en Iquitos, San Juan y Singapur, con plazos de cuatro a doce semanas. La comparación de Piura aporta un diseño distrital pareado a dos, tres y cuatro semanas, una lectura de Brier y AP por separado y una evaluación de anticipación de inicios frente a persistencia. Dostal et al. estimaron asociaciones meteorológicas y de El Niño con el riesgo de brote en distritos peruanos a escala mensual. El análisis de Piura estima el rendimiento incremental de pronósticos semanales fuera de muestra. [Benedum et al.](https://pubmed.ncbi.nlm.nih.gov/33064770/) · [Dostal et al.](https://pmc.ncbi.nlm.nih.gov/articles/PMC9278784/)

Se completaron 380 ajustes y se verificaron 1 140 registros de horizonte y corte. Los cuatro brazos comparten las 193 440 filas regulares por semilla y se verificó el cierre de etiquetas de entrenamiento y calibración. Los pronósticos y resúmenes están en `models/experimentos/mejora_modelo/v3_confirmados/clima_sin_historia/`. La corrida se registró en MLflow como `c7d5e39db3d34732aab810909e66cefc`. Se conserva la huella original de los ajustes reutilizados tras corregir el orden de columnas de la validación del resumen.
