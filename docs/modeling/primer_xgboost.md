# Primer experimento XGBoost: casos y alerta semanal

**Estado:** ejecutado sobre los gold validados de h=2 y h=4. La tabla completa, los cortes, los hiperparámetros y los hashes están en [`metricas/primer_xgboost.json`](metricas/primer_xgboost.json). Los modelos y predicciones por fila están en `models/experimentos/` (artefactos locales no versionados). El [notebook 24](../../notebooks/24_modelado_xgboost_dos_objetivos.ipynb) orquesta el mismo módulo reutilizable [`src/modeling/train.py`](../../src/modeling/train.py).

## Dos objetivos diferentes

1. **Regresión:** XGBoost predice `log1p(casos_Dengue)` y se invierte a un conteo no negativo. Para emitir alerta, ese conteo pronosticado debe superar el `umbral_brote_casos` histórico de la fila y alcanzar al menos 2 casos.
2. **Clasificación:** otro XGBoost estima `P(brote=1)` directamente. El umbral de probabilidad se fija con las predicciones fuera de muestra de las temporadas de validación, maximizando F1; no se elige mirando ninguna prueba. Queda como criterio provisional hasta que Rosa y el equipo definan el costo de falsos avisos frente a alertas perdidas.

La regla de brote describe **la semana objetivo observada**; la regresión no es requisito lógico para construir la etiqueta ni para entrenar el clasificador. `casos_Dengue`, `brote`, `umbral_brote_casos`, fechas e identificadores nunca entran en `X`. El umbral histórico sirve para convertir el pronóstico de conteos en alerta: procede de los cinco años anteriores a la semana objetivo y ya existe al origen de h=2/4. Como referencia se evalúa persistencia: los casos observados en `t−h`.

## Diseño temporal

- Filas por `(ubigeo, anio, semana)`, objetivo en `semana_inicio`; solo se usan predictores que cierran hasta `origen_cierre` (h semanas antes). Se validó el manifiesto de fase 6. Las primeras 325 filas de h=2 y 455 de h=4 carecen de la ventana completa de historia; se excluyen **solo de la matriz de entrenamiento**, no del gold. Un nulo posterior a ese arranque hace fallar el experimento.
- Dos bases predefinidas, sobre exactamente las mismas filas: cuatro variables (casos `t−h`, media de cuatro semanas hasta `t−h`, seno y coseno de la semana objetivo) y seis (las cuatro anteriores más casos `t−h−1` y número de semanas positivas de la ventana). No se ha demostrado que seis sea óptimo. Los vecinos, clima y demografía siguen siendo candidatos de ablación posterior; este primer experimento no atribuye ni descarta su aporte.
- Validación temporal: temporadas 2021, 2022 y 2023, cada una con un modelo reentrenado antes de su primer origen. **Prueba principal:** temporada 2024, del 2023-08-27 al 2024-08-18, con 857 semanas distritales positivas de 3 380. **Sensibilidad:** año calendario 2025, con solo 3 positivas de 3 380. Para cada bloque, la última etiqueta de entrenamiento se observó antes del primer origen del bloque. Dentro del bloque, el modelo permanece fijo; los rezagos de semanas de prueba ya observadas pueden alimentar pronósticos posteriores, como ocurriría al operar semanalmente.
- Se eligió la temporada 2024 como prueba principal **antes de mirar los resultados de XGBoost**, porque 2025 calendario casi no contiene positivos. 2025 se mantiene como fuente válida y como sensibilidad a un periodo de baja incidencia y al cambio de procedencia; no se excluye por defecto de futuros entrenamientos. La temporada llamada «2025» contiene 57 positivos, pero 55 corresponden aún a 2024; por eso no reemplaza la evaluación del año calendario 2025.

## Hiperparámetros y umbrales de este experimento

Ambos XGBoost se entrenaron con estos **hiperparámetros fijos**, iguales para h=2 y h=4 y para las bases de cuatro y seis variables. Se fijaron antes de las pruebas; no hubo búsqueda de hiperparámetros ni *early stopping*. Los parámetros no listados conservaron los valores predeterminados de la versión de XGBoost registrada en el JSON de métricas.

| Parámetro | Valor |
|---|---:|
| `n_estimators` | 160 árboles |
| `max_depth` | 3 |
| `learning_rate` | 0,05 |
| `subsample` | 0,8 |
| `colsample_bytree` | 0,9 |
| `min_child_weight` | 5 |
| `reg_lambda` | 5,0 |
| `tree_method` | `hist` |
| `n_jobs` | 2 |
| `random_state` | 17 |

La regresión usó `objective="reg:squarederror"` sobre `log1p(casos_Dengue)`; la clasificación usó `objective="binary:logistic"` y `eval_metric="logloss"` sobre `brote`. No se aplicó calibración de probabilidades.

Hay **dos umbrales distintos**:

- El **umbral epidemiológico de casos** (`umbral_brote_casos`, con mínimo de 2 casos) define la etiqueta observada y convierte el conteo pronosticado por regresión en alerta. Proviene de la regla histórica elegida para gold; no se ajustó con las pruebas de este experimento.
- El **umbral de probabilidad de la clasificación** decide cuándo `P(brote=1)` se convierte en alerta. **Sí se seleccionó ya en este primer experimento**, pero solo con predicciones fuera de muestra de las temporadas de validación 2021–2023: se probaron valores de 0,05 a 0,95 cada 0,025, se eligió el de mayor F1 agregado y, ante empate, el más alto. En la base de seis variables resultó **0,175 para ambos horizontes**; por ejemplo, una probabilidad de 0,18 genera alerta. Para la base de cuatro fue 0,175 en h=2 y 0,20 en h=4. Ni la temporada 2024 ni el calendario 2025 intervinieron en esa selección.

Ese 0,175 es una **decisión de alerta**, no un hiperparámetro de los árboles ni una prueba de que sus probabilidades estén calibradas. Si el equipo prioriza menos falsos avisos o más semanas elevadas detectadas, se puede elegir otro criterio y volver a seleccionar el umbral **dentro de la validación temporal**, sin escogerlo por el resultado de las pruebas.

## Resultados de prueba

La tabla usa la base de seis variables, que era la propuesta inicial de fase 7. **VP/FP** son semanas distritales con alerta acertada/falsa. AUPRC evalúa ordenamiento de alertas; para regresión usa el margen del conteo pronosticado respecto al umbral histórico, no una probabilidad.

| Horizonte y bloque | Enfoque | MAE casos | VP | FP | Precisión | Recall | F1 | AUPRC |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| h=2, temporada 2024 | Regresión + regla | 5,68 | 651 | 116 | 0,849 | 0,760 | 0,802 | 0,868 |
| h=2, temporada 2024 | Clasificación directa | — | 790 | 819 | 0,491 | 0,922 | 0,641 | 0,665 |
| h=2, temporada 2024 | Persistencia + regla | 4,96 | 690 | 183 | 0,790 | 0,805 | 0,798 | 0,843 |
| h=4, temporada 2024 | Regresión + regla | 9,44 | 614 | 161 | 0,792 | 0,716 | 0,752 | 0,770 |
| h=4, temporada 2024 | Clasificación directa | — | 763 | 873 | 0,466 | 0,890 | 0,612 | 0,610 |
| h=4, temporada 2024 | Persistencia + regla | 7,85 | 634 | 240 | 0,725 | 0,740 | 0,733 | 0,746 |
| h=2, calendario 2025 | Regresión + regla | 0,30 | 0 | 3 | 0 | 0 | 0 | 0,044 |
| h=2, calendario 2025 | Clasificación directa | — | 2 | 287 | 0,007 | 0,667 | 0,014 | 0,009 |
| h=2, calendario 2025 | Persistencia + regla | 0,29 | 0 | 8 | 0 | 0 | 0 | 0,010 |
| h=4, calendario 2025 | Regresión + regla | 0,43 | 0 | 5 | 0 | 0 | 0 | 0,034 |
| h=4, calendario 2025 | Clasificación directa | — | 1 | 346 | 0,003 | 0,333 | 0,006 | 0,005 |
| h=4, calendario 2025 | Persistencia + regla | 0,32 | 0 | 10 | 0 | 0 | 0 | 0,001 |

Los MAE de regresión son peores que la persistencia en la prueba principal para ambos horizontes. Su alerta logra menos falsos avisos que la clasificación directa, pero pierde más semanas elevadas. La clasificación usa el umbral F1 fijado en validación (0,175 para la base de seis en ambos horizontes) y alcanza mayor recall con muchos falsos avisos. En 2025, tres positivos son insuficientes para estimar con precisión la capacidad de alerta: una diferencia de un solo acierto cambia el recall en 0,333. No se declara un enfoque ganador ni se optimiza con los resultados de prueba.

La base de cuatro variables produce resultados cercanos; las seis no muestran una ganancia estable suficiente para declararlas preferidas. Los resultados por variante y cada temporada de validación están en el JSON. Hay solo unas pocas temporadas con transmisión intensa; los cortes no son independientes entre sí porque comparten historia y una ola puede cruzar el límite de temporada.

## Límites y próxima decisión

La primera versión usa hiperparámetros fijos y un único umbral de probabilidad elegido por F1. No busca hiperparámetros, no calibra probabilidades ni prueba todavía los bloques de vecinos, clima o demografía. La baja prevalencia de 2025 cambia la precisión aunque el modelo mantuviera recall; además cambió la fuente de casos. Los ceros históricos de distritos sin registro no prueban notificación cero. La disponibilidad real publicada de casos y clima aún debe verificarse; este ensayo supone disponibilidad al cierre de la semana. Las fracciones socio reconstruidas con 2025 no entraron en los predictores de este experimento.

Antes de decidir una alerta operativa, Rosa y el equipo deben acordar cuántos falsos avisos son aceptables por cada semana elevada detectada y revisar el rendimiento por distrito/temporada. Después corresponde una ablación controlada de vecinos, clima y demografía sobre los mismos cortes, sin reutilizar las pruebas para seleccionar variables o umbrales.

## Reproducción

Desde la raíz del repositorio, con el gold de fase 6 ya generado:

```bash
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m src.modeling.train
.venv/bin/python -m unittest discover -s tests
```
