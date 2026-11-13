# Historia, calibración y utilidad del pronóstico en el calendario común

Se evaluó XGBoost con historia epidemiológica y geografía sobre casos confirmados. El contraste separa la cantidad de historia con que se entrenan los árboles de la cantidad de predicciones y observaciones pasadas con que se calibra Platt. Las dos ventanas usan las mismas semanas de evaluación, predictores, etiqueta e hiperparámetros. Se reentrenó la ventana móvil de tres años en 19 temporadas y cinco semillas. Se reusó el entrenamiento expansivo desde 2005. [Protocolo](protocolo_historia_calibracion_comun.md)

## Qué gana cada componente

Cada celda es la media con igual peso de las diferencias pareadas de cinco temporadas, después de tomar la mediana entre las cinco semillas en cada temporada. Se usaron 2015, 2016, 2022, 2023 y 2026. Los calibradores de dos temporadas y expansivo coinciden para 2010, que queda disponible para comparar entrenamiento. Los cambios de Brier son relativos. Un valor negativo es un Brier menor. AP se informa en puntos porcentuales.

| Contraste | Brier h2 | Brier h3 | Brier h4 | AP h4 |
|---|---:|---:|---:|---:|
| Calibrar con toda la historia vs dos temporadas, con entrenamiento móvil fijo | −2,88% | −5,43% | −7,06% | 0,00 pp |
| Calibrar con toda la historia vs dos temporadas, con entrenamiento expansivo fijo | −2,39% | −5,09% | −5,54% | 0,00 pp |
| Entrenamiento expansivo vs móvil, ambos con calibración expansiva | −1,00% | −3,08% | −4,42% | +2,35 pp |
| Entrenamiento expansivo vs móvil, con probabilidades crudas | +3,99% | +6,03% | +7,18% | +2,35 pp |

**Más historia para calibrar** redujo el Brier a h4 en cuatro de cinco temporadas para cada ventana de entrenamiento. La reducción se atribuye al componente de descalibración dentro de cada bloque. AP y la discriminación CORP se mantuvieron a la precisión reportada. La calibración Platt fue monotónica y conserva el orden dentro de la temporada salvo posibles empates numéricos. El beneficio de ampliarla varió entre temporadas. Para el entrenamiento expansivo, mejoró el Brier h4 en 2016, 2022, 2023 y 2026 y lo empeoró en 2015.

**Más historia para entrenar** elevó AP a h4 en las cinco temporadas del contraste principal, con el mayor aumento en 2022 (+4,73 pp) y luego 2026 (+4,03 pp). El Brier crudo empeoró en promedio aunque mejoró la discriminación. Con calibración expansiva, el Brier bajó en cuatro de cinco temporadas. Los resultados apoyan una distinción entre ordenar el riesgo y asignar probabilidades fiables. La afirmación de que toda la ganancia de la historia larga viene de calibración sería demasiado amplia. La discriminación también cambió al ampliar el entrenamiento. Al retirar 2026, la ganancia media de AP h4 con entrenamiento expansivo quedó en +1,93 puntos porcentuales y los dos efectos de ampliar la calibración conservaron el signo.

La descomposición CORP reproduce `Brier = descalibración − discriminación + incertidumbre` por bloque y semilla. Los componentes se calcularon con regresión isotónica en los bloques observados para diagnosticar el error. Los pronósticos puntuados usan las probabilidades originales o la calibración Platt ajustada únicamente con bloques anteriores. El gráfico agrupado de confiabilidad usa la mediana de las curvas isotónicas por semilla y se lee junto a las cifras por bloque. [Dimitriadis, Gneiting y Jordan](https://doi.org/10.1073/pnas.2016191118)

## Por qué esto importa para las alertas

En las seis temporadas decisivas, b3 a h4 ordena las semanas mejor que la persistencia probabilística según AP medio por temporada (0,7144 frente a 0,6733). El log score también favorece a b3 (0,1915 frente a 0,2189), mientras que su BSS medio frente a persistencia es −1,86%. En 2026 y con los cortes ajustados con temporadas previas, b3 avisó 10 de 20 inicios con 37 falsas alarmas y la persistencia 13 de 20 con 65. El orden, la exactitud de las probabilidades y la capacidad de avisar inicios describen propiedades distintas. [Resultados de alertas](resultados_alertas_revision.md)

En el diagnóstico de fase se conservaron 17 778 semanas negativas comunes a los dos contrastes. Se agregaron por separado 486 semanas positivas de las dos primeras semanas de episodios y 2 146 de continuación. Los BSS y AP de cada fase se calculan en esas muestras condicionadas. Las probabilidades originales se refieren a cualquier semana de brote. Con ese soporte, a h4 el AP de b3 frente a persistencia fue 0,143 frente a 0,104 para las primeras dos semanas y 0,766 frente a 0,746 para continuaciones. Los BSS medios fueron −2,74% y −13,04%, respectivamente. Se conservó el desglose de pérdida cuadrática por fase que suma exactamente el Brier de todas las filas.

La endemicidad se definió con la frecuencia de brotes previa al primer origen de cada bloque, separando distritos sin brotes previos y dividiendo los demás por la mediana de esa frecuencia. El estrato sin brote previo en 2026 carecía de positivos y quedó fuera del resumen de métricas que requieren ambas clases. Se archivaron también pendiente e intercepto por horizonte y temporada. En h4, para b3 y los pronósticos de probabilidad de al menos 0,30, las medianas por temporada sumaron 1 967 semanas de brote observadas frente a 1 447,4 esperadas en 2 938 pronósticos. Esto cuantifica el déficit de probabilidad en la zona de riesgo alto.

## Incertidumbre del contraste climático

Se enumeraron los remuestreos de las seis temporadas completas con reemplazo. Se mantuvo el pareo de ambos modelos, los 65 distritos por temporada y los tres horizontes por separado. El análisis principal remuestrea las diferencias medianas entre semillas por temporada. La sensibilidad incorpora la variación entre semillas usando la misma semilla para todos los bloques seleccionados dentro de cada repetición. También se guardaron intervalos t pareados sobre los diferenciales de pérdida por temporada, un contraste de cambios de signo y las exclusiones de una temporada a la vez. Las seis temporadas proporcionan una base limitada para la inferencia y ya informaron etapas retrospectivas del estudio.

A h4, b3 empeora el Brier en 5,28% frente a historia y geografía. El intervalo percentil de remuestreo que incorpora semillas es de +1,02% a +9,81%. Sin 2023, la estimación es +4,18% y el intervalo va de −0,07% a +9,02%. Sin 2026, la estimación es +6,37% y el intervalo va de +1,76% a +10,87%. El contraste exacto de cambios de signo de seis temporadas da p = 0,125 a h4. La lectura se apoya en las diferencias por temporada, sus sensibilidades y el pequeño número de unidades independientes.

Los pronósticos, 95 cortes de entrenamiento y 1 080 registros de calibración se guardaron en `models/experimentos/mejora_modelo/v3_confirmados/historia_calibracion_comun/`. La corrida quedó registrada en MLflow como `9c7a62f4067045d6a55cf0d0f732e01a`. Las métricas por estrato y los intervalos están en `diagnostico_probabilidades_revision/` e `incertidumbre_por_temporada/` del mismo directorio de experimentos.

### Sensibilidad con efectos cruzados de temporada y distrito

Se calculó la diferencia pareada de pérdida cuadrática en cada combinación distrito–temporada y se resumió la variación mediante un modelo balanceado con interceptos aleatorios cruzados de distrito y temporada. La estimación central usa la media entre semillas. Se preservan las estimaciones individuales por semilla. Los componentes de varianza se obtienen de los cuadrados medios de la ANOVA cruzada y se truncan a cero si el estimador cae por debajo de cero. El intervalo aproximado usa cinco grados de libertad para la comparación con seis temporadas. Este modelo supone independencia entre los efectos de distrito y entre temporadas y tiene alcance de sensibilidad. [ANOVA cruzada de NIST](https://www.itl.nist.gov/div898/handbook/ppc/section2/ppc232.htm)

A h4, la diferencia absoluta de Brier de b3 frente a historia y geografía fue **+0,00380**, con intervalo aproximado de **−0,00047 a +0,00808**. Para d3 fue **+0,00346**, con intervalo de **−0,00055 a +0,00748**. El cambio positivo se conserva en la estimación central al retirar 2023 o 2026. Los intervalos de esta sensibilidad incluyen cero. Las conclusiones del paper deben reflejar la variación por temporada y la limitada precisión de seis temporadas. Se verificó que las diferencias por semilla recuperan exactamente las diferencias absolutas calculadas directamente sobre el Brier de cada temporada.

El archivo `incertidumbre_por_temporada/sensibilidad_efectos_cruzados.csv` contiene las estimaciones y se reproduce con `code/evaluate_crossed_brier.py`.
