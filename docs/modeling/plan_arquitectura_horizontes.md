# Encargo: revisar los experimentos y decidir la arquitectura multi-horizonte (h=2, 3, 4)

## Contexto

El modelado lleva siete experimentos (notebooks 24–30, informes en `docs/modeling/`,
JSON en `docs/modeling/metricas/`, runs en MLflow y predicciones fila a fila en
`models/experimentos/`). Todos usan la misma arquitectura: **un XGBoost directo por
horizonte y por tarea** (regresión de `log1p(casos)` + regla de brote, y clasificador
de `brote`), solo para **h=2 y h=4**, con hiperparámetros fijos. h=3 no existe:
`src/serving/inferencia.py` lo rechaza con `MOTIVO_H3`, aunque la HU0007 y
`version_modelo.horizonte ∈ {2,3,4}` lo exigen.

Según los informes (verifícalo, no lo des por cierto), ningún modelo cumple todavía
los umbrales de aceptación de la HU0007-4:

| Requisito HU0007-4 | Mejor resultado actual, temporada 2024 | Brecha |
|---|---|---|
| Clasificador: Recall ≥ 0,80, Precision ≥ 0,60, F1 ≥ 0,70 **con p ≥ 0,50** | h=4: R 0,925, P 0,462, F1 0,617, pero con umbral elegido ≈ 0,175, no 0,50 | Precisión baja y probabilidades sin calibrar para la regla 0,50 |
| Regresor: MAE y RMSE ≤ 85 % de la persistencia | h=4: MAE 9,40 vs 7,85 (≈ 120 %); h=2: 5,64 vs 4,96 (≈ 114 %) | El regresor es **peor** que la persistencia |
| La regresión + regla en F1 de alerta | Supera a la persistencia por 0,004 (h=2) y 0,025 (h=4) | Ventaja pequeña |

Las ablaciones (espacio, clima, socio, fracciones) no movieron esta brecha de forma
robusta. La hipótesis de trabajo es que **el cuello de botella está en la arquitectura
y en la formulación de la salida, no en agregar más variables**. Este encargo comprueba
esa hipótesis **antes** de cualquier feature engineering nuevo o ajuste de
hiperparámetros.

## Objetivo

1. Consolidar y diagnosticar lo que dicen los experimentos realizados (dónde y por qué falla el modelo).
2. Decidir, con evidencia, si conviene **mantener h=2/3/4 como horizontes directos separados**
   o cambiar la estrategia multi-horizonte.
3. Decidir **la formulación de la salida** (cómo se obtienen probabilidad y casos) que
   tenga opción real de cumplir la HU0007-4.
4. Dejar una arquitectura candidata para que las fases siguientes (FE, optimización de
   hiperparámetros de la HU0007-3) trabajen sobre ella.

**Fuera de alcance:** variables nuevas, búsqueda de hiperparámetros, cambios en
serving/API/BD, escribir en `data/`. Las variables se congelan en las matrices actuales
(`base_6` para regresión y `base_6_poblacion_2017` para clasificación) para que cualquier
diferencia se deba a la arquitectura.

## Cómo trabajar

- Fase por fase. Antes de cada fase muéstrame el plan concreto (archivos a crear o
  modificar). Al cerrarla, presenta el resumen como texto en el chat y **detente**
  hasta que lo confirme.
- Respeta `CLAUDE.md`: `data/` es de solo lectura, `ubigeo` es string, las rutas salen
  de `src/utils/paths.py`, CRLF y UTF-8, todo en español, Windows + PowerShell, lógica
  reutilizable en `src/modeling/` con test y notebooks solo para orquestar.
- Antes de crear archivos, lee `docs/estructuraRepo.md` y actualízalo en el mismo cambio.
- Toda matriz para un horizonte que no exista en gold (h=1, h=3, h=5, h=6) se construye
  **en memoria** con las funciones de `src/modeling/` (`historia_calendario.py`,
  `features.py`, `etiqueta_brote.py`) y se valida con la misma auditoría de causalidad
  (`semana_inicio > origen_cierre`). Nunca se persiste en `data/`. Si para eso hay que
  generalizar una función que hoy acepta solo `HORIZONTES = (2, 4)`, propónmelo primero.
- Cada experimento se registra en MLflow con `src/modeling/seguimiento_mlflow.py`
  (forma `horizontes → variantes → folds`); no crees otro tracker.
- Honestidad estadística: 2024 ya no es un test virgen, 2025 tiene 3 positivos, y la
  diferencia de decimales entre GPU y CPU basta para cambiar elecciones ajustadas.
  Diferencias menores que la variación entre semillas o equipos se reportan como
  **empate**. No uses lenguaje causal.
- Si una ambigüedad cambia el análisis, **pregunta**. Las decisiones que ya están tomadas
  aparecen en la sección «Decisiones ya tomadas»; no vuelvas a plantearlas.
- **Cero fuga de información (data leakage).** Es la condición no negociable de cualquier
  arquitectura: toda entrada, calibrador o umbral usa solo datos cerrados hasta el origen
  `t−h`. Cada estrategia nueva lleva un test automatizado de causalidad.

## Fase 0: inventario y verificación (sin código nuevo de modelado)

1. Lee `docs/modeling/*.md`, los JSON de `docs/modeling/metricas/`, el inventario de
   MLflow (`docs/modeling/inventario_entrenamiento_mlflow.md`) y `src/modeling/train.py`,
   `evaluate.py`, `validacion_temporal_compacta.py`.
2. Arma una **tabla única** con todos los experimentos: horizonte, tarea, matriz,
   protocolo (validación original o progresivo), umbral, VP/FP/FN, P, R, F1, AUPRC,
   MAE, RMSE, razón MAE/persistencia y razón RMSE/persistencia, por temporada.
   **Recalcula** las cifras de 2024 desde las predicciones guardadas
   (`models/experimentos/.../predicciones_*.csv`), no las copies de los informes.
3. Evalúa los modelos ya entrenados **contra la regla literal de la HU0007-4**
   (p ≥ 0,50, sin umbral optimizado) y su RMSE frente a la persistencia. Esa es la
   línea base real de este encargo.
4. Mide la variación por semilla: reentrena la configuración elegida de h=2 y h=4 con
   5 semillas y reporta el rango de F1 y MAE. Ese rango define qué diferencia se
   considera «empate» en el resto del encargo.

**Entregable:** tabla consolidada y línea base HU0007-4 en el chat. Detente.

## Fase 1: diagnóstico de errores

Responde con cifras calculadas (todo en memoria, a partir de las predicciones existentes):

1. **¿Dónde pierde el regresor frente a la persistencia?** Desglose de MAE y RMSE por
   temporada, por tamaño de distrito (terciles de casos históricos), por fase de la
   curva epidémica (subida, pico, bajada, valle) y por nivel de casos reales. Hipótesis
   a comprobar: el objetivo `log1p` + error cuadrático subestima sistemáticamente los
   picos (sesgo al invertir la transformación).
2. **¿Qué son los falsos positivos del clasificador?** Sepáralos entre los adyacentes a
   una racha real (±2 semanas: «aviso temprano o tardío») y los aislados. Si la mayoría
   son adyacentes, el problema es de temporalidad, no de discriminación.
3. **Calibración:** diagrama de fiabilidad y Brier por horizonte. ¿Qué precisión y
   recall daría p ≥ 0,50?
4. **Detección de episodios:** para cada racha de semanas `brote`, ¿con cuántas semanas
   de antelación emitió el modelo su primera alerta? Compara con la persistencia. Es la
   métrica que mejor refleja el propósito de una alerta temprana a cuatro semanas.
5. **Concentración del error:** ¿qué porcentaje del error total aportan 2023 y los
   cinco distritos con más casos?

**Entregable:** 4 o 5 hallazgos con «observación / hipótesis» y figuras en
`docs/modeling/figuras/arquitectura_horizontes/`. Detente.

## Fase 2: protocolo de evaluación (se fija ANTES de comparar arquitecturas)

El protocolo ya está acordado. Impleméntalo, documéntalo y no lo cambies después de ver
resultados:

1. **Bloques:** origen móvil por temporada (semana 35 a semana 34), el mismo de
   `validacion_temporal_compacta.py`. Cada modelo se entrena desde cero solo con
   etiquetas cerradas antes del primer origen del bloque.
2. **Papel de cada temporada:**
   - **2017–2020:** solo entrenamiento.
   - **2021:** primera temporada fuera de muestra; sus predicciones solo sirven para
     ajustar el **calibrador** de 2022 (no se usa para elegir).
   - **2022 y 2023:** **selección**. Toda decisión de arquitectura sale de aquí.
   - **2024:** contraste reportado, **nunca** usado para decidir, con la advertencia
     explícita de que ya se inspeccionó en experimentos anteriores.
   - **2025:** sensibilidad de conteos (MAE/RMSE); sus 3 positivos no permiten evaluar
     la alerta.
   - **Test independiente real:** las semanas de 2026 que se publiquen después de
     congelar la arquitectura (pilotaje, HU0019). Ningún experimento de este encargo las toca.
3. **Criterio de selección preregistrado:** F1 con la regla de alerta p ≥ 0,50 sobre
   probabilidades calibradas, AUPRC, Brier, razón MAE/RMSE frente a la persistencia y
   antelación de detección de episodios. Una arquitectura gana solo si mejora **en
   ambas** temporadas de selección y por encima del rango de semillas de la fase 0; si
   no, es empate y se prefiere la más simple.
4. **Calibración:** el calibrador de cada bloque se ajusta con predicciones fuera de
   muestra de las temporadas anteriores ya cerradas (2021 para 2022; 2021–2022 para
   2023; etc.). Nunca con la temporada evaluada.

**Entregable:** protocolo escrito en `docs/modeling/arquitectura_horizontes.md`
(sección «Protocolo») y su implementación con test. Detente.

## Fase 3: estrategia multi-horizonte

### 3.1 Curva de habilidad según el horizonte

Antes de comparar estrategias, mide cómo decae la señal. Para h = 1, 2, 3, 4, 5 y 6
(matrices en memoria, matriz `base_6`) calcula persistencia, ingenuo estacional y el
XGBoost directo actual. Grafica F1, AUPRC y MAE relativo a la persistencia frente a h.

Esto responde: ¿hay señal útil más allá de la persistencia en h=3–4?, ¿h=3 está en el
punto medio o hay un quiebre?, ¿qué horizonte máximo es defendible?

### 3.2 Definición de horizonte (decidida)

`h` se mantiene como está: distancia entre el último dato disponible (`t−h`) y la semana
objetivo `t`. La demora de publicación de MINSA es una **limitación aceptada** del
proyecto; no se modela ni se simulan escenarios de demora. Solo se deja escrita como
limitación en el informe.

### 3.3 Estrategias a comparar (mismas variables, mismos bloques y semillas)

| Id | Estrategia | Descripción | Qué hay que verificar |
|---|---|---|---|
| E1 | Directa por horizonte (actual) | Un modelo por h ∈ {2,3,4} y por tarea (6 modelos) | Línea base; incluye construir h=3 |
| E2 | Directa agrupada | Un solo modelo por tarea, entrenado con filas apiladas (origen `o`, objetivo `o+h`, h ∈ {2,3,4}) y `h` como variable | Triplica las filas; vigila la correlación entre filas apiladas en la validación |
| E3 | Multi-salida (MIMO) | Un modelo que predice el vector (t+2, t+3, t+4) desde el mismo origen (`multi_strategy="multi_output_tree"` de XGBoost) | Verifica soporte en XGBoost 3.4.1 y en GPU; si no hay, usa CPU y repórtalo |
| E4 | Recursiva (opcional) | Modelo h=1 iterado | Solo si la curva 3.1 muestra que h=1 es mucho mejor; si no, justifica por qué se descarta |

Para cada estrategia reporta también la **coherencia entre horizontes**: para una misma
semana objetivo, ¿las predicciones h=2/3/4 son consistentes o se contradicen (p. ej., una
alerta a h=4 que desaparece a h=3 sin un dato nuevo que lo explique)? Para el usuario de
DIRESA, la incoherencia entre horizontes es un defecto, aunque cada horizonte por
separado tenga buenas métricas.

**Entregable:** tabla comparativa por estrategia, horizonte y temporada, más la
recomendación con su justificación. Detente.

## Fase 4: formulación de la salida

Con la estrategia ganadora de la fase 3, compara cómo se obtienen probabilidad y casos:

| Id | Formulación | Motivo |
|---|---|---|
| S1 | Actual: regresor `log1p` + MSE y clasificador independiente | Línea base |
| S2 | Regresor con objetivo de conteo (`count:poisson`, `reg:tweedie`) | Evita el sesgo de invertir `log1p` y puede mejorar los picos (hipótesis de la fase 1) |
| S3 | Regresor sobre la persistencia: `base_margin = log(casos_lag_h + ε)` o el cambio respecto de la persistencia como objetivo | El modelo aprende la desviación respecto de una referencia ya difícil de superar |
| S4 | Modelo probabilístico único: distribución de conteo (Poisson o binomial negativa con la media de S2/S3, o regresión cuantílica) → `P(casos > umbral)` como probabilidad de brote | Probabilidad y magnitud coherentes por construcción; usa el umbral conocido de la semana objetivo |
| S5 | Clasificador actual + calibración cronológica (isotónica o Platt ajustada con temporadas previas) y, como variante, `scale_pos_weight` | Hace que la regla fija p ≥ 0,50 tenga sentido |

Nota sobre S4: `umbral_brote_casos` de la semana objetivo se calcula con la misma semana
de los cinco años anteriores, así que se conoce en el origen y no filtra el futuro.
**Verifícalo con un test** en `etiqueta_brote.py` antes de usarlo: el umbral de la fila
`t` no puede depender de ningún caso posterior a `t−h`. S4 usa el umbral solo para
convertir la distribución de casos predicha en probabilidad; no es una variable de
entrada. Si el test falla, descarta S4 y repórtalo.

**Calibración (decidida):** las probabilidades se calibran para que la regla de alerta y
los cortes de riesgo de `parametro_sistema` (0,25 / 0,50 / 0,75) se apliquen tal como
están en las HU. No se optimiza un umbral por F1. El calibrador sigue la regla de la fase 2.

Evalúa S1–S5 con la regla p ≥ 0,50 sobre probabilidades calibradas y con el protocolo
de la fase 2. Reporta además el diagrama de fiabilidad de cada formulación.

**Entregable:** tabla S1–S5 por horizonte y temporada con P/R/F1 a 0,50, Brier, AUPRC,
razones MAE y RMSE frente a la persistencia y antelación de detección. Detente.

## Fase 5: síntesis y decisión

1. Escribe `docs/modeling/arquitectura_horizontes.md` (protocolo, resultados,
   recomendación y límites), `docs/modeling/metricas/arquitectura_horizontes.json` y
   el notebook `31_modelado_arquitectura_horizontes.ipynb` (orquesta y muestra; la
   lógica va en `src/modeling/`, p. ej. `estrategias_horizonte.py` y
   `salida_probabilistica.py`, con tests). Las predicciones van en
   `models/experimentos/arquitectura_horizontes/`.
2. Lista **sin implementarlos** los cambios que implicaría la arquitectura elegida:
   - generación de gold h=3 (o el formato apilado por horizonte) en `features.py` y el
     notebook 22 (lo ejecuta el equipo, no tú);
   - `config.yaml` → `serving.horizontes`, retirar `MOTIVO_H3`, el registro de
     `version_modelo` si un modelo agrupado sirve a 3 horizontes (¿3 filas que apuntan a
     un mismo artefacto?) y cualquier desviación respecto de OE2 para
     `docs/backend/desviaciones_oe2.md`;
   - qué quedaría pendiente para la fase de FE y para la optimización de hiperparámetros
     (HU0007-3).
3. Una auditoría independiente recalcula, desde las predicciones guardadas, cada cifra
   citada en el informe (subagente revisor; si no existe uno para modelado, propón crear
   `.claude/agents/revisor-modelado.md` siguiendo `revisor-backend.md`). Pega su tabla
   en el resumen.
4. Ejecuta `python -m unittest discover -s tests` y el notebook de punta a punta.

**Entregable:** resumen final en el chat con la arquitectura recomendada, el estado de
cumplimiento de la HU0007-4 por horizonte y lo que quedaría bloqueado. Detente.

## Decisiones ya tomadas (no las vuelvas a preguntar)

1. **Regla de alerta:** se mantiene p ≥ 0,50 y los cortes 0,25 / 0,50 / 0,75 de las HU,
   aplicados sobre **probabilidades calibradas**. No se optimiza el umbral por F1.
2. **Demora de MINSA:** limitación aceptada. `h` se mide desde el último dato disponible
   y no se simulan demoras.
3. **Temporadas:** 2021 calibración inicial, 2022–2023 selección, 2024 contraste no
   decisorio, 2025 sensibilidad de conteos, 2026 (pilotaje) test independiente.
4. **Umbral de brote en S4:** se puede usar para convertir casos predichos en probabilidad,
   siempre que pase el test de no fuga.
5. **Gold:** puede cambiar de formato si la arquitectura ganadora lo requiere (por
   ejemplo, apilado por horizonte). Condición: tests de no fuga y validación GX antes de
   escribirlo. Tú propones y modificas `src/modeling/features.py`; la regeneración de
   `data/gold/` la hace el equipo, como dice `CLAUDE.md`.
6. **Cumplimiento de umbrales de aceptación:** no es objetivo de este encargo. Se reporta
   para tener la línea base, pero la decisión de arquitectura se toma con el criterio de
   la fase 2. Las expectativas sobre el modelo se revisan en la etapa de experimentos con
   variables.
