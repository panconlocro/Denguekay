# Revisión de la definición de brote — antes de la fase 4

**Estado:** Rosa decidió que la alerta identifica **cada semana distrital con nivel elevado de casos** y eligió **media histórica + 1,5 DE** para la etiqueta experimental añadida a gold. La implementación usa la misma semana epidemiológica de los cinco años anteriores por distrito, la definición estacional comparada aquí. Para experimentar, se adoptó provisionalmente un mínimo de **2 casos** tras revisar la sensibilidad; el mínimo de 1 queda documentado como alternativa. Los casos de 2025 de la Sala Situacional se consideran válidos para el proyecto.

## Qué dicen las fuentes

| Fuente | Regla descrita | Unidad y referencia histórica |
|---|---|---|
| [Benedum et al. (2020), estudio con Iquitos, San Juan y Singapur](https://journals.plos.org/plosntds/article?id=10.1371/journal.pntd.0008710) | Casos semanales por encima de la **media + 1,5 desviaciones estándar**. La fórmula del artículo usa los casos del conjunto de **entrenamiento** para estimar el umbral. | Una serie por lugar de estudio; el umbral no se estima separadamente para cada semana epidemiológica del año. Su uso por distrito en Piura sería una adaptación, no una copia literal. |
| [OMS/TDR, guía de dengue de 2009, capítulo 3.3.1, p. 73](https://iris.who.int/bitstream/handle/10665/44188/9789241547871_eng.pdf?sequence=1) | Comparar la semana o mes corriente con la media histórica de esa **misma semana o mes** en los **5–7 años previos**; superar la banda superior de **media + 2 desviaciones estándar** activa una **alerta de brote**. | Canal endémico estacional. La guía lo ofrece como *una aproximación* de vigilancia, no como diagnóstico universal o umbral obligatorio para todo distrito. |

El EDA local implementó D1 (tasa fija), D2 (percentil distrital), D3 (Q3 de la misma semana en cinco años previos) y D4 (aumento sostenido). **No evaluó media + 1,5 DE ni media + 2 DE**. En [`hallazgos.md`](../eda/hallazgos.md), fase 2, hallazgo 5, señaló media + 2 DE como alternativa porque el canal D3 queda en cero con frecuencia. Estas reglas externas pueden definir una semana de nivel alto; el **primer arranque** de un episodio es otra etiqueta y requiere una regla adicional.

## Comprobación exploratoria en Piura

Se usó el integrado actual, 65 distritos × semanas 1–52 de **2022–2025**: **13 520 distrito-semanas**. Para cada distrito y año se tomaron las cinco observaciones de la **misma semana** en los cinco años anteriores (2017–2021 para 2022; 2020–2024 para 2025). La desviación se calculó con `ddof=1`. Se marcó una semana si `casos_Dengue > umbral`; la desigualdad estricta evita clasificar como brote un cero cuando media y desviación son cero. Son conteos descriptivos, no una evaluación predictiva ni una elección de objetivo.

| Año | Media + 1,5 DE | Media + 2 DE (estilo canal OMS) | D3: Q3 previo (EDA) | Canales +2 DE iguales a cero |
|---|---:|---:|---:|---:|
| 2022 | 483 | 400 | 862 | 1 983 |
| 2023 | 1 597 | 1 523 | 1 791 | 2 163 |
| 2024 | 603 | 532 | 1 058 | 1 424 |
| 2025 | 12 | 7 | 54 | 1 209 |
| **Total** | **2 695** | **2 462** | **3 765** | **6 779** |

En **6 779 de 13 520 filas (50,1 %)**, los cinco años previos de esa distrito-semana tenían cero casos; por ello, **incluso media + 2 DE vale cero**. De las 2 462 semanas marcadas por esa regla, **311 tenían un solo caso**. Así que el umbral OMS por sí mismo tampoco resuelve los falsos avisos potenciales de distritos silenciosos. A ello se suma que muchos ceros históricos del Excel significan *sin registro*, no cero explícitamente notificado.

Como adaptación distinta del estudio de Iquitos, se calculó además un **único umbral por distrito** usando todas sus semanas de 2017–2021 y media + 1,5 DE. Aplicado sin reajuste a 2022–2025 marcó **325, 1 045, 606 y 31** semanas por año, respectivamente. No se debe comparar directamente ese total con el canal OMS para atribuir la diferencia solo a 1,5 frente a 2: también cambia si se agrupa toda la temporada o la misma semana y si se actualiza la historia cada año.

## Decisión tomada y parámetros pendientes

**Unidad de la alerta decidida:** una fila `(ubigeo, anio, semana)` es positiva si sus casos alcanzan el criterio acordado de nivel elevado. Si el nivel elevado dura varias semanas consecutivas, cada una se etiqueta según la misma regla. El primer inicio de un episodio puede reportarse como análisis complementario, pero no define la etiqueta principal.

Rosa eligió el multiplicador 1,5 para la etiqueta experimental. Para concretarlo en el panel, se usan cinco años anteriores de la misma semana epidemiológica, desviación muestral y comparación estricta. El mínimo provisional recomendado es **2 casos**: elimina 742 positivos de un solo caso frente al mínimo de 1 y conserva 822 positivos de 2–4 casos que se perderían con un mínimo de 5. No es un umbral clínico validado ni una regla atribuida a la OMS. Quedan abiertas su revisión con el equipo y la interpretación de los ceros sin notificación; el tratamiento de semana 53 se documenta abajo. Una exigencia de duración mínima sería una decisión adicional; si depende de semanas posteriores al objetivo, debe distinguirse de lo que puede conocerse al emitir la alerta. El umbral de cada fila se calcula solo con años anteriores; no se ajusta con su caso objetivo ni con años futuros.

La comparación anterior muestra factibilidad y desbalance. No convierte ninguna cifra en umbral clínico o decisión de salud pública. Conviene revisar el criterio cuantitativo con la compañera de tesis y el asesor antes de fijar etiquetas y métricas de clasificación.

## Preparación para incorporar la etiqueta a gold

`src/modeling/etiqueta_brote.py` implementa de forma parametrizable el canal estacional de cinco años anteriores por distrito y misma semana epidemiológica, con desviación muestral y comparación estricta `casos_Dengue > umbral`. Para etiquetar 2017–2021 utiliza 2012–2016 del Excel silver como historia, sin tomar años posteriores a cada objetivo. Las ausencias del Excel se interpretan como cero, igual que en el D3 exploratorio, **sin afirmar que fueron ceros notificados**. La semana 53 se agrupa con la 52 solo para calcular la referencia. El [notebook 22](../../notebooks/22_fe_integracion.ipynb) pasa explícitamente `multiplicador=1.5`, `anios_previos=5` y `minimo_casos=2` al generar gold; el [manifiesto local](../../data/gold/manifest_fase6.json) registra la configuración.

La sensibilidad siguiente usa todo el integrado 2017–2025 y comprueba que la variante con mínimo de 1 caso reproduce los conteos 2022–2025 de la tabla anterior:

| Multiplicador | Mínimo semanal | Positivos 2017–2025 | Positivos 2022–2025 | Positivos con exactamente 1 caso |
|---:|---:|---:|---:|---:|
| 1,5 DE | 1 | 3 744 | 2 695 | 742 |
| 1,5 DE | 2 | 3 002 | 2 262 | 0 |
| 1,5 DE | 5 | 2 180 | 1 688 | 0 |
| 2 DE | 1 | 3 365 | 2 462 | 550 |
| 2 DE | 2 | 2 815 | 2 151 | 0 |
| 2 DE | 5 | 2 078 | 1 627 | 0 |

La versión de +1,5 DE de esta tabla es **estacional** para compararla con +2 DE. El artículo de Iquitos también describe una alternativa diferente: un único umbral calculado con todas las semanas de entrenamiento de cada lugar. Ambas variantes no deben recibir el mismo nombre ni mezclarse en un experimento. La regla elegida y su mínimo están registrados en el manifiesto de gold; se puede cambiar el mínimo para un análisis de sensibilidad sin modificar las fuentes silver.
