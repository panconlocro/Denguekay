# Fase 4 — clima

**Estado:** ejecutada. El [notebook 20](../../notebooks/20_fe_clima.ipynb) usa el integrado actual; las [métricas](metricas/fase4_clima.json) y la [figura](figuras/fase4_clima/01_ablacion_mae_clima.png) son reproducibles. No se escribió en `data/gold/`. La fase 5 se completó después y está documentada en [`fase5_sociodemografia.md`](fase5_sociodemografia.md).

## Variables y disponibilidad

`src/modeling/clima.py` crea, por distrito y para cada objetivo `t`, la media observada y la media de anomalías de `hum_rel_media` y `precip_total_mm` en `t−h−4,…,t−h`. Para `h=4` es la ventana 4–8 semanas del EDA; para `h=2` es 2–6. Se generan cuatro columnas por horizonte. Las primeras **8** filas por distrito en `h=4` y las primeras **6** en `h=2` quedan `NaN` por historia insuficiente. La semana 53 se agrupa con la 52 **solo para el promedio climatológico**. Se conservan llaves, fechas y las 30 485 filas. `lluvia_total_mm` no entra porque duplica la precipitación.

La climatología es la media por `(ubigeo, semana_clima)` de las semanas meteorológicas **cerradas antes del corte de ajuste**. En cada fold se ajusta otra vez, sin usar clima posterior al primer origen de prueba; los escaladores del modelo diagnóstico también se ajustan solo con entrenamiento. En una temporada de prueba se emite un pronóstico semanal móvil: las filas posteriores pueden utilizar el clima de su propio origen `t−h`, aunque ese origen caiga dentro del bloque de prueba. No se reajusta el modelo con etiquetas del bloque. El método supone que el clima semanal de Open-Meteo está disponible al cierre de la semana observada; falta verificar la demora operativa real.

## Contraste temporal exploratorio

Se usaron cuatro temporadas completas (2022–2025, semana 35 del año anterior a semana 34 del año indicado; **3 380 filas** cada una) y horizontes `h=2` y `h=4`. Para cada temporada se entrenó una única regresión ridge, con penalización fija, respuesta `log1p(casos_Dengue)` y predicción invertida a casos. La base usa el caso propio en `t−h`, su media de cuatro semanas y el calendario seno/coseno. Se comparó con la misma base más las dos anomalías climáticas. La persistencia propia en `t−h` sirve de referencia. Entrenamiento y climatología terminan antes del primer origen de la temporada de prueba; por ejemplo, para 2023 `h=4`, el corte climático es **2022-08-06**. No se eligió el mejor hiperparámetro ni se entrenó XGBoost en esta fase.

| Horizonte | Temporada | MAE persistencia | MAE base | MAE base + clima | Cambio con clima |
|---:|---:|---:|---:|---:|---:|
| 2 | 2022 | 1,959 | 1,981 | 2,080 | +0,099 |
| 2 | 2023 | 10,837 | 11,509 | 11,130 | −0,379 |
| 2 | 2024 | 4,956 | 4,896 | 4,997 | +0,101 |
| 2 | 2025 | 0,467 | 0,459 | 0,456 | −0,003 |
| 4 | 2022 | 2,846 | 2,535 | 2,649 | +0,114 |
| 4 | 2023 | 17,680 | 15,421 | 14,846 | −0,575 |
| 4 | 2024 | 7,848 | 6,776 | 6,682 | −0,095 |
| 4 | 2025 | 0,499 | 0,534 | 0,526 | −0,008 |

Un cambio negativo es mejor. El clima mejora **5 de 8** cortes en MAE de casos, con mayor ganancia en la temporada 2023, y empeora 2022 para ambos horizontes. Frente a la persistencia, el modelo con clima aún es peor en algunos cortes; por ello no se concluye que el clima aporte de forma robusta. La métrica en `log1p` también está en el JSON; su cambio promedio con clima es pequeño (−0,0012 para `h=2`, −0,0044 para `h=4`). Las temporadas tienen niveles de casos muy diferentes, por lo que no se promedian MAE de casos como si fueran equivalentes.

Se repitió la prueba agregando la anomalía de `temp_min`. Mejoró **3 de 8** cortes respecto de las dos variables climáticas, y empeoró la temporada 2023, donde la señal principal más ayuda. El EDA ya la consideraba débil. Se mantiene como candidata opcional, fuera del conjunto climático inicial. No se ensayaron `temp_media`, `temp_max` ni interacciones: el EDA observó redundancia con calendario y falta de robustez. La investigación adjunta inspira ventanas y anomalías, pero no justifica agregar todos sus rezagos o transformaciones en este panel.

## Decisión y límites

Conservar humedad y precipitación, tanto sus medias observadas como anomalías, **como candidatas** para la ablación posterior con XGBoost; no asumir que mejoran el pronóstico. La comparación diagnóstica utiliza el **conteo** de casos porque Rosa eligió alertar cada semana elevada pero el umbral cuantitativo sigue abierto. No evalúa precisión de alertas ni el arranque de brotes. 2025 se incluye como temporada válida, de acuerdo con Rosa; su cambio de fuente y bajo nivel de casos se informan, sin declararlo automáticamente test final. El corte definitivo de train/test, la latencia de Open-Meteo, el calendario oficial alrededor de 2025-S53 y la definición de alerta siguen pendientes.

**Comprobación:** el notebook ejecutó la validación del silver y cobertura de casos; una media de humedad de cinco semanas se recalculó manualmente para un distrito y dio el mismo valor. Las pruebas sintéticas comprueban `h=2/4`, corte de climatología, invariancia ante cambios de clima posteriores al origen, casilla 52/53 y errores ante duplicados, nulos o historia climática ausente. Se ejecutaron las 90 pruebas del repositorio; todas pasaron.
