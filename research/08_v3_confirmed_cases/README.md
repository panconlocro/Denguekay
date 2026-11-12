# V3 con casos confirmados

Se repite la comparación del cierre del estudio 06 entre V3 (L + 5a + d3) y L + 5a sin clima. Las dos variantes se ajustan con los mismos casos confirmados, el trial 191, los 20 bloques, las cinco semillas y los horizontes 2, 3 y 4 del [protocolo V3](../../docs/modeling/protocolo_v3.md). El análisis retrospectivo mide el aporte de d3 con la definición de casos actualizada. V0, V1 y V2 conservan sus protocolos de desarrollo y sus resultados históricos.

La serie combina el histórico confirmado de 2000–2016, el panel confirmado de 2017–2025 y las semanas de la Sala posteriores al panel. Se incluyen la SE 53 de 2025 y las SE 1–41 de 2026. Se omiten las SE 42 y 43 como provisionales siguiendo el protocolo original. El gold h2 se audita junto a sus insumos para verificar el linaje. La V3 construye en memoria sus matrices desde la serie larga, con la temperatura ERA5-Land congelada. Se recalculan el umbral epidémico, las variables de casos, los ajustes de XGBoost y NB2, Platt y la mezcla con persistencia por bloque y horizonte. El corte de alerta es 0,50.

Se conservan el diseño, las variables y los hiperparámetros seleccionados para V3. Esta corrida cubre el cierre pareado con la fuente nueva. Los valores archivados se usan para verificar el soporte y la equivalencia de la construcción de variables sobre los datos originales. Los cortes de entrenamiento y calibración se verifican con el protocolo. La decisión pareada se lee con SEASON_2026.

## Ejecución

Con los archivos confirmados en `data/silver/confirmados/`, su gold en `data/gold/` y los insumos congelados del Release de V3 disponibles, ejecutar desde la raíz:

```bash
DENGUEKAY_XGB_DEVICE=cpu DENGUEKAY_XGB_NJOBS=2 \
OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 OMP_NUM_THREADS=2 \
.venv/bin/python -B research/08_v3_confirmed_cases/code/run_experiment.py
```

Las predicciones, los cortes, las métricas y los checkpoints quedan en `models/experimentos/mejora_modelo/v3_confirmados/`. Los checkpoints se reutilizan solo si coinciden los insumos, la configuración y el código de la corrida. El registro de MLflow es local.

## Resultados de la corrida del 9 de noviembre de 2026

Se entrenaron 200 modelos multisalida en CPU con dos hilos por ajuste (20 bloques, 5 semillas, 2 variantes). Se guardaron 1 950 000 predicciones fuera de muestra. Las variantes y las semillas comparten filas y etiquetas, y las llaves coinciden con las de la referencia. La auditoría comprobó 60 cortes de evaluación y calibración, cobertura completa de d3 en los orígenes utilizados, reproducción de Platt y de la mezcla a partir de sus parámetros guardados. Pasaron 107 expectativas de silver y 50 de gold. La corrida de MLflow `6a47f30d535042a697943644dbb5b179` está finalizada.

| Horizonte | Brier | Temporadas a favor / en contra / empate en Brier | F1 y antelación | Error de conteo |
|---|---|---|---|---|
| 2 | Empate | 3 / 2 / 1 | Empate | Empate |
| 3 | Empate | 3 / 3 / 0 | Compensa (empate) | Empate |
| 4 | Empate | 3 / 3 / 0 | Compensa (empate) | Empate |

Las seis temporadas de decisión entraron en cada horizonte. Para h3 y h4 se activaron las guardas de F1 a 0,50 y de antelación. Sobre 209 episodios de las seis temporadas en la semilla 17, la proporción detectada con la antelación nominal mínima del protocolo fue 8,13 y 14,35 puntos porcentuales menor para V3 que para L + 5a, respectivamente. Los IC del 95 % de esas diferencias fueron [−11,96, −4,31] y [−19,62, −9,57] puntos porcentuales. La comparación queda por debajo del criterio de adopción de SEASON_2026.

En `temporada_2026` hubo 86 semanas distritales elevadas por horizonte. Las medianas entre semillas favorecen a V3 en Brier y MAE en esta temporada de desarrollo.

| Horizonte | Brier V3 | Brier L + 5a | MAE V3 (casos) | MAE L + 5a (casos) |
|---|---:|---:|---:|---:|
| 2 | 0,00956 | 0,01007 | 0,848 | 0,889 |
| 3 | 0,01074 | 0,01143 | 0,997 | 1,075 |
| 4 | 0,01333 | 0,01410 | 1,159 | 1,243 |

La comparación válida de esta corrida es la de ambas variantes sobre los mismos confirmados y en el mismo entorno. La referencia congelada original se ajustó en GPU y tiene otra definición de casos. La temporada 2026 ya formaba parte del desarrollo de V3.

## Calibración y alertas para la revisión del paper

El [protocolo complementario](protocolo_contribucion.md) usa los mismos casos confirmados y el trial 191. Reutiliza las predicciones crudas de V3 y del par sin clima y agrega 40 ajustes del modelo sin clima desde 2017. Las salidas y el manifiesto quedan en `models/experimentos/mejora_modelo/v3_confirmados/contribucion/`. La corrida validada quedó en MLflow con ID `a3d079e9ae414898b17789b6188db93b`.

```bash
DENGUEKAY_XGB_DEVICE=cpu DENGUEKAY_XGB_NJOBS=2 \
OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 OMP_NUM_THREADS=2 \
.venv/bin/python -B research/08_v3_confirmed_cases/code/run_contribution.py
```

### Historia para entrenar e historia para calibrar

Promedios de las medianas por semilla en las 12 celdas de 2021–2024 y h2–h4. Menor Brier indica menor error de probabilidad. Mayor AP indica mejor ordenamiento del riesgo.

| Calibración | Brier con entrenamiento corto | Brier con entrenamiento largo | AP con entrenamiento corto | AP con entrenamiento largo |
|---|---:|---:|---:|---:|
| Sin Platt | 0,05528 | 0,06059 | 0,77274 | 0,76798 |
| Últimas dos temporadas | 0,05916 | 0,06024 | 0,77273 | 0,76798 |
| Todas las temporadas previas desde 2018 | 0,06834 | 0,06007 | 0,77273 | 0,76798 |

El entrenamiento largo obtiene menor Brier en 9 de 12 celdas con calibración larga y en 5 de 12 con calibración corta. En 8 de 12 celdas la diferencia absoluta de AP es de hasta 0,01. Con el entrenamiento largo fijo, ampliar la calibración mejora el Brier en 6 de 12 celdas y lo empeora en los tres horizontes de 2026. En estos bloques, la conclusión sobre el valor de la historia larga depende de cómo se ajustan las probabilidades. La comparación cruda también ayuda a localizar de dónde viene la diferencia.

### Habilidad probabilística y alertas

Antes de 2026, V3 obtuvo menor Brier que la persistencia probabilística en 12 de 15 celdas y el modelo sin clima en 10 de 15. En h4, el Brier medio por temporada fue 0,06206 para V3, 0,06412 para el par sin clima y 0,06881 para persistencia probabilística. En 2026, V3 obtuvo menor Brier que la persistencia probabilística en h2. La persistencia probabilística obtuvo menor Brier en h3 y h4.

| Bloques | Política h4 | V3, episodios avisados con ≥2 semanas | Persistencia probabilística, episodios avisados con ≥2 semanas | Falsos avisos por distrito por 52 semanas, V3 / persistencia |
|---|---|---:|---:|---:|
| Cinco temporadas previas a 2026 | Corte fijado con temporadas anteriores | 61/177 | 25/177 | 2,47 / 2,21 |
| Cinco temporadas previas a 2026 | Presupuesto aplicado retrospectivamente | 25/177 | 8/177 | 1,00 / 0,90 |
| 2026 | Corte fijado con temporadas anteriores | 5/20 | 9/20 | 0,15 / 0,33 |
| 2026 | Presupuesto aplicado retrospectivamente | 13/20 | 13/20 | 1,00 / 1,00 |

Se usó como objetivo un falso aviso por distrito por 52 semanas. La política retrospectiva aplica el presupuesto en cada temporada evaluada y preserva empates completos. Las medianas entre semillas se calculan por temporada y luego se suman los recuentos. La persistencia determinista original avisó 22 de 177 inicios en h4 en los cinco bloques anteriores a 2026 y 8 de 20 en 2026, con costos de 2,11 y 0,32 falsos avisos por distrito y 52 semanas, respectivamente.

V3 obtuvo más avisos tempranos en varios contrastes. El hallazgo metodológico para la revisión es que la evaluación de probabilidades debe acompañarse del desempeño de la política de alertas y su costo observado. Un mismo presupuesto fijado con temporadas anteriores produjo costos distintos y el orden entre métodos varió por temporada. Esta lectura retrospectiva conserva el calendario archivado y su hueco de 2024–2025. Para la versión final se repetirá con el calendario común, `b3` y los controles espaciales del plan.

Se verificaron 420 cortes de calibración de historia y 765 de los comparadores de alertas. Se reprodujeron los recuentos de falsos avisos a partir de las predicciones guardadas y se comprobó la conversión del presupuesto. La primera corrida local quedó marcada como reemplazada en MLflow porque aplicó un denominador de semanas regionales al presupuesto distrital.
