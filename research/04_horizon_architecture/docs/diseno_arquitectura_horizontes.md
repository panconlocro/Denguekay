# Diseño del estudio 04: arquitectura multi-horizonte (h=2, 3, 4)

Este documento describe el diseño del estudio: punto de partida, objetivo, alcance, método por fases,
protocolo de evaluación y decisiones fijadas de antemano. Los resultados y la recomendación están en
[arquitectura_horizontes.md](arquitectura_horizontes.md). Las rutas de este documento (`src/modeling/`,
`docs/modeling/`, notebooks 22–31) describen el repositorio en el tag `study/horizon-architecture`.

## Punto de partida

Antes del estudio, el modelado tenía siete experimentos (notebooks 24–30, informes en `docs/modeling/`,
JSON en `docs/modeling/metricas/`, runs en MLflow y predicciones fila a fila en `models/experimentos/`).
Todos usaban la misma arquitectura: **un XGBoost directo por horizonte y por tarea** (regresión de
`log1p(casos)` + regla de brote, y clasificador de `brote`), solo para **h=2 y h=4**, con hiperparámetros
fijos. h=3 no existía: `src/serving/inferencia.py` lo rechazaba con `MOTIVO_H3`, aunque la HU0007 y
`version_modelo.horizonte ∈ {2,3,4}` lo exigen.

Según los informes previos (cifras que la fase 0 recalcula), ningún modelo cumplía los umbrales de
aceptación de la HU0007-4:

| Requisito HU0007-4 | Mejor resultado previo, temporada 2024 | Brecha |
|---|---|---|
| Clasificador: Recall ≥ 0,80, Precision ≥ 0,60, F1 ≥ 0,70 **con p ≥ 0,50** | h=4: R 0,925, P 0,462, F1 0,617, pero con umbral elegido ≈ 0,175, no 0,50 | Precisión baja y probabilidades sin calibrar para la regla 0,50 |
| Regresor: MAE y RMSE ≤ 85 % de la persistencia | h=4: MAE 9,40 vs 7,85 (≈ 120 %); h=2: 5,64 vs 4,96 (≈ 114 %) | El regresor es **peor** que la persistencia |
| La regresión + regla en F1 de alerta | Supera a la persistencia por 0,004 (h=2) y 0,025 (h=4) | Ventaja pequeña |

Las ablaciones (espacio, clima, socio, fracciones) no movieron esta brecha de forma robusta. La hipótesis de
trabajo del estudio es que **el cuello de botella está en la arquitectura y en la formulación de la salida, no en
agregar más variables**, y se comprueba **antes** de cualquier feature engineering nuevo o ajuste de
hiperparámetros.

## Objetivo

1. Consolidar y diagnosticar lo que dicen los experimentos realizados (dónde y por qué falla el modelo).
2. Decidir, con evidencia, si conviene **mantener h=2/3/4 como horizontes directos separados** o cambiar la
   estrategia multi-horizonte.
3. Decidir **la formulación de la salida** (cómo se obtienen probabilidad y casos) con opción real de cumplir
   la HU0007-4.
4. Dejar una arquitectura candidata sobre la que trabajen las fases siguientes (FE y optimización de
   hiperparámetros de la HU0007-3).

**Fuera de alcance:** variables nuevas, búsqueda de hiperparámetros, cambios en serving/API/BD y escritura en
`data/`. Las variables quedan congeladas en las matrices existentes (`base_6` para regresión y
`base_6_poblacion_2017` para clasificación), de modo que cualquier diferencia se deba a la arquitectura.

## Criterios de método

- El estudio avanza por fases; cada una se cierra con un resumen revisado por el equipo antes de pasar a la
  siguiente.
- `data/` es de solo lectura. Toda matriz para un horizonte que no está en gold (h=1, h=3, h=5, h=6) se
  construye **en memoria** con las funciones de `src/modeling/` (`historia_calendario.py`, `features.py`,
  `etiqueta_brote.py`) y pasa la misma auditoría de causalidad (`semana_inicio > origen_cierre`).
- Cada experimento se registra en MLflow con `src/modeling/seguimiento_mlflow.py` (forma
  `horizontes → variantes → folds`).
- **Honestidad estadística:** 2024 ya no es un test virgen, 2025 tiene 3 positivos y la diferencia de decimales
  entre GPU y CPU basta para cambiar elecciones ajustadas. Las diferencias menores que la variación entre
  semillas o equipos se reportan como **empate**, sin lenguaje causal.
- **Cero fuga de información.** Es la condición no negociable de cualquier arquitectura: toda entrada,
  calibrador o umbral usa solo datos cerrados hasta el origen `t−h`, y cada estrategia nueva lleva un test
  automatizado de causalidad.

## Fases

### Fase 0: inventario y verificación

- Revisión de `docs/modeling/*.md`, los JSON de `docs/modeling/metricas/`, el inventario de MLflow
  (`docs/modeling/inventario_entrenamiento_mlflow.md`) y `src/modeling/train.py`, `evaluate.py` y
  `validacion_temporal_compacta.py`.
- **Tabla única** de experimentos: horizonte, tarea, matriz, protocolo (validación original o progresivo),
  umbral, VP/FP/FN, P, R, F1, AUPRC, MAE, RMSE y razones MAE y RMSE frente a la persistencia, por temporada.
  Las cifras de 2024 se **recalculan** desde las predicciones guardadas
  (`models/experimentos/.../predicciones_*.csv`), no se copian de los informes.
- **Línea base HU0007-4:** los modelos ya entrenados se evalúan con la regla literal (p ≥ 0,50, sin umbral
  optimizado) y su RMSE frente a la persistencia.
- **Variación por semilla:** la configuración elegida de h=2 y h=4 se reentrena con 5 semillas. El rango de F1
  y MAE define qué diferencia cuenta como «empate» en el resto del estudio.

### Fase 1: diagnóstico de errores

Preguntas respondidas con cifras calculadas en memoria a partir de las predicciones existentes:

1. **¿Dónde pierde el regresor frente a la persistencia?** MAE y RMSE por temporada, por tamaño de distrito
   (terciles de casos históricos), por fase de la curva epidémica (subida, pico, bajada, valle) y por nivel de
   casos reales. Hipótesis: el objetivo `log1p` + error cuadrático subestima los picos (sesgo al invertir la
   transformación).
2. **¿Qué son los falsos positivos del clasificador?** Se separan los adyacentes a una racha real (±2 semanas:
   aviso temprano o tardío) de los aislados. Si dominan los adyacentes, el problema es de temporalidad, no de
   discriminación.
3. **Calibración:** diagrama de fiabilidad y Brier por horizonte, y la precisión y el recall con p ≥ 0,50.
4. **Detección de episodios:** para cada racha de semanas `brote`, semanas de antelación de la primera alerta,
   frente a la persistencia. Es la métrica que mejor refleja el propósito de una alerta temprana.
5. **Concentración del error:** porcentaje del error total que aportan 2023 y los cinco distritos con más casos.

Los hallazgos se presentan como observación / hipótesis, con figuras en
`docs/modeling/figuras/arquitectura_horizontes/`.

### Fase 2: protocolo de evaluación

El protocolo se fija **antes** de comparar arquitecturas y no cambia después de ver resultados:

1. **Bloques:** origen móvil por temporada (semana 35 a semana 34), el mismo de
   `validacion_temporal_compacta.py`. Cada modelo se entrena desde cero solo con etiquetas cerradas antes del
   primer origen del bloque.
2. **Papel de cada temporada:**
   - **2017–2020:** solo entrenamiento.
   - **2021:** primera temporada fuera de muestra; sus predicciones solo ajustan el **calibrador** de 2022.
   - **2022 y 2023:** **selección**. Toda decisión de arquitectura sale de aquí.
   - **2024:** contraste reportado, **nunca** usado para decidir, porque ya se inspeccionó en experimentos
     anteriores.
   - **2025:** sensibilidad de conteos (MAE/RMSE); sus 3 positivos no permiten evaluar la alerta.
   - **Test independiente real:** las semanas de 2026 publicadas después de congelar la arquitectura
     (pilotaje, HU0019). Ningún experimento del estudio las toca.
3. **Criterio de selección preregistrado:** F1 con la regla p ≥ 0,50 sobre probabilidades calibradas, AUPRC,
   Brier, razones MAE/RMSE frente a la persistencia y antelación de detección. Una arquitectura gana solo si
   mejora **en ambas** temporadas de selección y por encima del rango de semillas de la fase 0; si no, es empate
   y se prefiere la más simple.
4. **Calibración:** el calibrador de cada bloque se ajusta con predicciones fuera de muestra de las temporadas
   anteriores ya cerradas (2021 para 2022; 2021–2022 para 2023; etc.), nunca con la temporada evaluada.

El protocolo está escrito en la sección «Protocolo» de [arquitectura_horizontes.md](arquitectura_horizontes.md)
e implementado con su test.

### Fase 3: estrategia multi-horizonte

**3.1 Curva de habilidad según el horizonte.** Para h = 1 a 6 (matrices en memoria, matriz `base_6`) se
calculan la persistencia, el ingenuo estacional y el XGBoost directo, y se grafican F1, AUPRC y MAE relativo a
la persistencia frente a h. Responde si hay señal útil más allá de la persistencia en h=3–4, si h=3 está en el
punto medio o hay un quiebre, y qué horizonte máximo es defendible.

**3.2 Definición de horizonte.** `h` es la distancia entre el último dato disponible (`t−h`) y la semana objetivo
`t`. La demora de publicación de MINSA es una **limitación aceptada**: no se modela ni se simulan escenarios de
demora.

**3.3 Estrategias comparadas** (mismas variables, bloques y semillas):

| Id | Estrategia | Descripción | Punto a verificar |
|---|---|---|---|
| E1 | Directa por horizonte | Un modelo por h ∈ {2,3,4} y por tarea (6 modelos) | Línea base; incluye construir h=3 |
| E2 | Directa agrupada | Un solo modelo por tarea con filas apiladas (origen `o`, objetivo `o+h`, h ∈ {2,3,4}) y `h` como variable | Triplica las filas; correlación entre filas apiladas en la validación |
| E3 | Multi-salida (MIMO) | Un modelo que predice el vector (t+2, t+3, t+4) desde el mismo origen (`multi_strategy="multi_output_tree"` de XGBoost) | Soporte en XGBoost 3.4.1 y en GPU; si no hay, CPU |
| E4 | Recursiva (opcional) | Modelo h=1 iterado | Solo si la curva 3.1 muestra que h=1 es mucho mejor |

Para cada estrategia se mide también la **coherencia entre horizontes**: si, para una misma semana objetivo, las
predicciones h=2/3/4 se contradicen (por ejemplo, una alerta a h=4 que desaparece a h=3 sin un dato nuevo que lo
explique). Para el usuario de DIRESA esa incoherencia es un defecto, aunque cada horizonte tenga buenas métricas.

### Fase 4: formulación de la salida

Con la estrategia ganadora de la fase 3 se comparan cinco formas de obtener probabilidad y casos:

| Id | Formulación | Motivo |
|---|---|---|
| S1 | Regresor `log1p` + MSE y clasificador independiente | Línea base |
| S2 | Regresor con objetivo de conteo (`count:poisson`, `reg:tweedie`) | Evita el sesgo de invertir `log1p` y puede mejorar los picos (hipótesis de la fase 1) |
| S3 | Regresor sobre la persistencia: `base_margin = log(casos_lag_h + ε)` o el cambio respecto de la persistencia como objetivo | El modelo aprende la desviación respecto de una referencia ya difícil de superar |
| S4 | Modelo probabilístico único: distribución de conteo (Poisson o binomial negativa con la media de S2/S3, o regresión cuantílica) → `P(casos > umbral)` | Probabilidad y magnitud coherentes por construcción; usa el umbral conocido de la semana objetivo |
| S5 | Clasificador + calibración cronológica (isotónica o Platt con temporadas previas) y, como variante, `scale_pos_weight` | Da sentido a la regla fija p ≥ 0,50 |

**Umbral en S4:** `umbral_brote_casos` de la semana objetivo se calcula con la misma semana de los cinco años
anteriores, así que se conoce en el origen. Un test en `etiqueta_brote.py` comprueba que el umbral de la fila `t`
no depende de ningún caso posterior a `t−h`. S4 usa el umbral solo para convertir la distribución predicha en
probabilidad; no es una variable de entrada. Si el test fallara, S4 quedaría descartada.

**Calibración:** las probabilidades se calibran para aplicar la regla de alerta y los cortes de riesgo de
`parametro_sistema` (0,25 / 0,50 / 0,75) tal como están en las HU, con el calibrador de la fase 2. No se optimiza
un umbral por F1.

S1–S5 se evalúan con p ≥ 0,50 sobre probabilidades calibradas y el protocolo de la fase 2: P/R/F1, Brier, AUPRC,
razones MAE y RMSE frente a la persistencia, antelación de detección y diagrama de fiabilidad.

### Fase 5: síntesis y decisión

1. **Salidas:** [arquitectura_horizontes.md](arquitectura_horizontes.md) (protocolo, resultados, recomendación y
   límites), `metricas/arquitectura_horizontes.json` y el notebook `31_modelado_arquitectura_horizontes.ipynb`,
   que orquesta y muestra; la lógica está en `src/modeling/` (`estrategias_horizonte.py`,
   `salida_probabilistica.py`) con tests. Las predicciones quedan en `models/experimentos/arquitectura_horizontes/`.
2. **Cambios que implica la arquitectura elegida** (listados, no implementados en el estudio): gold h=3 o formato
   apilado por horizonte en `features.py` y el notebook 22; `serving.horizontes` en `config.yaml`, retiro de
   `MOTIVO_H3`, registro de `version_modelo` cuando un modelo sirve a tres horizontes y las desviaciones respecto
   de OE2; y lo que queda para la fase de FE y para la HU0007-3.
3. **Auditoría independiente:** un revisor recalcula, desde las predicciones guardadas, cada cifra citada en el
   informe.
4. **Verificación:** la suite de tests y el notebook ejecutado de punta a punta.

## Decisiones fijadas antes del estudio

1. **Regla de alerta:** p ≥ 0,50 y los cortes 0,25 / 0,50 / 0,75 de las HU, sobre **probabilidades calibradas**.
   No se optimiza el umbral por F1.
2. **Demora de MINSA:** limitación aceptada. `h` se mide desde el último dato disponible y no se simulan demoras.
3. **Temporadas:** 2021 calibración inicial, 2022–2023 selección, 2024 contraste no decisorio, 2025 sensibilidad
   de conteos y 2026 (pilotaje) test independiente.
4. **Umbral de brote en S4:** puede convertir casos predichos en probabilidad si pasa el test de no fuga.
5. **Gold:** puede cambiar de formato si la arquitectura ganadora lo requiere (por ejemplo, apilado por
   horizonte), con tests de no fuga y validación GX antes de escribirlo. El cambio se propone en
   `src/modeling/features.py` y el equipo regenera `data/gold/`.
6. **Umbrales de aceptación:** cumplirlos no es objetivo del estudio. Se reportan como línea base, pero la
   decisión de arquitectura se toma con el criterio de la fase 2.
