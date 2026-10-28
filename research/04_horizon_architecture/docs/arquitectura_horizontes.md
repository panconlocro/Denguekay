# Arquitectura multi-horizonte (h=2, 3, 4)

**Estado:** encargo cerrado (fases 0–5). Este documento se completa por fases; el encargo está en [`plan_arquitectura_horizontes.md`](plan_arquitectura_horizontes.md). Las cifras salen de [`metricas/arquitectura_horizontes.json`](metricas/arquitectura_horizontes.json) (una sección por fase) y del [notebook 31](../notebooks/31_modelado_arquitectura_horizontes.ipynb). Equipo de referencia: GPU NVIDIA (`device="cuda"`), XGBoost 3.4.1.

## Protocolo

Fijado **antes** de comparar arquitecturas (fase 2). No se cambia después de ver resultados. Implementación: [`src/modeling/protocolo_arquitectura.py`](../../../src/modeling/protocolo_arquitectura.py), con pruebas en `tests/test_protocolo_arquitectura.py`.

### 1. Bloques y papel de cada temporada

Origen móvil por temporada epidemiológica (semana 35 a semana 34), igual que [`validacion_temporal_compacta.py`](../../../src/modeling/validacion_temporal_compacta.py). Cada modelo se entrena desde cero solo con etiquetas cerradas antes del primer origen del bloque y queda fijo dentro del bloque.

| Temporada | Papel |
|---|---|
| 2017–2020 | Solo entrenamiento. |
| 2021 | Primera temporada fuera de muestra. Sus predicciones solo ajustan el calibrador de 2022; no se evalúa ni se usa para elegir. |
| **2022 y 2023** | **Selección.** Toda decisión de arquitectura sale de aquí. |
| 2024 | Contraste reportado, **nunca decisorio**. Ya se inspeccionó en los experimentos 24–30. |
| 2025 (año calendario) | Sensibilidad de conteos (MAE/RMSE). Sus 3 positivos no permiten evaluar la alerta. |
| 2026 | Test independiente real: semanas publicadas después de congelar la arquitectura (pilotaje, HU0019). Ningún experimento de este encargo las usa. |

### 2. Cero fuga de información

- Cada predicción cumple `origen_cierre < semana_inicio`; el protocolo rechaza cualquier fila que no lo cumpla y cualquier `ubigeo` que no sea texto de seis dígitos.
- Toda matriz de un horizonte ausente en gold (h=1, 3, 5, 6) se construye en memoria y pasa la misma auditoría de causalidad. Nada se escribe en `data/`.
- Toda transformación aprendida (calibrador, umbral diagnóstico) usa solo predicciones fuera de muestra de bloques anteriores, con etiqueta cerrada (`semana_inicio + 6 días`) hasta el primer origen del bloque evaluado. Al empezar cada temporada quedan fuera 65 distrito-semanas en h=2 y 195 en h=4 cuyas etiquetas aún no cerraron.
- Cada estrategia nueva lleva un test automatizado de causalidad. El del calibrador comprueba que alterar las etiquetas del bloque evaluado o de bloques posteriores no cambia su probabilidad calibrada.

### 3. Regla de alerta y calibración (decisión aprobada)

- **Alerta:** probabilidad **calibrada** ≥ 0,50. Niveles de riesgo con los cortes de `parametro_sistema`: bajo < 0,25 ≤ medio < 0,50 ≤ alto < 0,75 ≤ muy alto. Son intervalos cerrados a la izquierda, iguales a `src/serving/riesgo.py`.
- **No se optimiza un umbral por F1.** El umbral que maximiza F1 en la calibración previa se reporta en columnas `diagnostico_*`, marcado como diagnóstico; no interviene en ninguna decisión.
- **Calibrador por defecto: Platt cronológico.** Es una regresión logística sobre el logit de la probabilidad y se ajusta con las predicciones fuera de muestra de las temporadas previas ya cerradas: 2021 para 2022; 2021–2022 para 2023; 2021–2023 para 2024; 2021–2024 para 2025. Se elige Platt porque el calibrador de 2022 solo dispone de 84 positivos (h=2) y 71 (h=4), y Platt ajusta 2 parámetros. La calibración isotónica y `scale_pos_weight` se comparan en la fase 4 (S5) con este mismo protocolo.
- Las salidas de conteo (regresión) generan alerta con la regla de gold: casos predichos > `umbral_brote_casos` y ≥ 2. Esa alerta se reporta junto a la de probabilidad.

### 4. Episodios y antelación (decisión aprobada)

- **Episodio:** semanas `brote` de un distrito, uniendo huecos de hasta 2 semanas sin brote.
- **Inicio limpio:** episodio sin semanas `brote` en las 8 semanas previas del distrito, de modo que una alerta temprana no sea arrastre del episodio anterior.
- **Antelación:** `h − (w − t0)`, donde `t0` es el inicio y `w` la primera semana objetivo con alerta entre `t0 − 2` y el fin del episodio (la alerta para `w` se emite en `w − h`). Si no hay alerta, el episodio no se detectó.
- **Métrica de selección:** fracción de inicios limpios con alerta (p ≥ 0,50 calibrada) emitida **al menos 2 semanas antes** del inicio. Intervalo de confianza del 95 % por bootstrap de episodios, estratificado por temporada (2 000 réplicas, semilla 20261020).
- Dos arquitecturas del mismo horizonte comparten exactamente los mismos episodios (dependen solo de las etiquetas), así que la comparación es **pareada**: IC bootstrap de la diferencia por episodio en 2022–2023.
- Solo se usan alertas del mismo bloque. Un episodio que empieza en las primeras semanas del bloque puede perder alertas emitidas en el bloque anterior; afecta igual a todas las arquitecturas.

### 5. Métricas reportadas

Por horizonte y por temporada (nunca solo agregadas):

- P, R y F1 con p ≥ 0,50 calibrada; VP, FP y FN; AUPRC; Brier calibrado y sin calibrar; probabilidad media frente a prevalencia; número de distrito-semanas y tasa observada de brote por nivel de riesgo.
- **Calibración:** Brier y curva de fiabilidad (bins de 0,1) **por temporada**, además de la curva agregada de 2022–2023. La fase 1 mostró que el modelo es poco confiado en 2023 y demasiado confiado en 2024, algo que el agregado oculta.
- **Conteos:** MAE y RMSE del modelo y de la persistencia (casos en `t−h`) y sus razones, **siempre juntos** y con el desglose por fase de la curva regional (valle, subida, pico, bajada). **El RMSE no decide nada por sí solo**: la fase 1 mostró que el 72–83 % del error cuadrático viene de 2023 y que el 60–74 % viene de solo 2,6 % de las filas.
- Antelación sobre inicios limpios con IC (sección 4), para la alerta del modelo, la regla de conteos y la persistencia.
- Coherencia entre horizontes (fase 3): se define y mide allí, sobre la misma semana objetivo.

### 6. Semillas y empate

- Cada arquitectura se entrena con las mismas 5 semillas: 17, 29, 41, 53 y 67. Para comparar se usa la **mediana entre semillas** de cada métrica.
- **Umbral de empate** por métrica, horizonte y temporada: el mayor rango (máximo − mínimo entre semillas) de las dos arquitecturas comparadas. Un horizonte sin semillas propias (h=3 antes de medirlo) toma el mayor rango de h=2/h=4 en la misma temporada.
- La antelación usa la diferencia pareada de la semilla 17 con su IC bootstrap. Además, la diferencia entre las medianas de las semillas debe tener el mismo signo.
- Todo se midió en un solo equipo (GPU). Una diferencia entre equipos mayor que el rango de semillas se trataría también como empate.

### 7. Regla de decisión preregistrada

Para cada horizonte, una candidata A frente a una referencia B. La regla es **simétrica**: A pierde frente a B si y solo si B gana frente a A.

1. **Criterios primarios** (deciden): F1 con p ≥ 0,50 calibrada y antelación sobre inicios limpios.
   - *Mejora en F1:* la diferencia A − B supera el umbral de empate **en 2022 y en 2023**.
   - *Empeora en F1:* la diferencia cae por debajo de −umbral **en 2022 y en 2023**.
   - *Mejora en antelación:* el IC 95 % pareado de 2022–2023 queda entero por encima de 0 y la diferencia es positiva en ambas temporadas.
   - *Empeora en antelación:* el IC queda entero por debajo de 0 y la diferencia es negativa en ambas temporadas.
2. **Guardas** (solo vetan una victoria, nunca causan una derrota): AUPRC, Brier y razón MAE frente a la persistencia. Hay veto contra A si A empeora más que el umbral **en ambas** temporadas en alguna guarda; hay veto contra B en el caso espejo.
3. **Veredicto:**

   | Veredicto | Condición |
   |---|---|
   | **gana** | A mejora en al menos un primario, no empeora en ninguno y no tiene veto. |
   | **pierde** | Espejo de «gana»: A empeora en al menos un primario, no mejora en ninguno y B no tiene veto. |
   | **compensa** (cuenta como empate) | A mejora en un primario y empeora en el otro; o mejora con veto contra A; o empeora con veto contra B. |
   | **empate** | Cualquier otro caso. |

> **Corrección aprobada por Rosa en la fase 4.** La versión escrita en la fase 2 era asimétrica: «empeora en F1» bastaba con una temporada, «empeora en antelación» no exigía el signo por temporada y un veto contaba como «pierde». Contradecía el plan («gana solo si mejora en ambas temporadas…; si no, es empate») y la simetría que pide la regla. Se detectó al revisar la fase 4, después de ver resultados. Las decisiones de las fases 3 y 4 se recalcularon con la regla corregida a partir de las predicciones guardadas, sin reentrenar, y una auditoría independiente las verificó.

4. **Entre horizontes:** una arquitectura se adopta si gana en al menos un horizonte y no pierde en ninguno. Si pierde en algún horizonte, se descarta.
5. **Desempate (decisión aprobada en la fase 3).** Ante empate **no** se conserva automáticamente la arquitectura actual. Entre las estrategias empatadas, que no ganan ni se descartan, se aplica en orden:
   - **(a) Coherencia entre horizontes.** Se mide el porcentaje de semanas objetivo (distrito-semana) donde las alertas de h=4, h=3 y h=2 cambian sin un dato nuevo que lo explique. Al pasar de h=k a h=k−1 solo se agrega la semana `w−k+1`. El cambio está explicado si esos casos subieron respecto de la semana anterior y la alerta aparece, o si bajaron y la alerta desaparece. Gana la estrategia con menos cambios sin explicar en 2022 **y** en 2023, por encima del mayor rango de semillas de las comparadas.
   - **(b) Simplicidad operativa:** menos modelos que se entrenan y despliegan. E1 usa 6 modelos (2 por horizonte); E2 y E3 usan 2.
6. **Umbral de empate de h=3:** se reemplaza el prestado por el rango de sus propias 5 semillas en cuanto existe su matriz (fase 3).
7. 2024 se reporta junto a la decisión pero no la cambia. El cumplimiento de la HU0007-4 se reporta como línea base; no es criterio de este encargo.

Control de la regla: dos semillas de la misma arquitectura (29 frente a 17) dan **empate** en h=2 y h=4.

### 8. Registro

Cada experimento se registra en MLflow con `src/modeling/seguimiento_mlflow.py` (forma `horizontes → variantes → folds`). Las predicciones van en `models/experimentos/arquitectura_horizontes/`.

## Línea base bajo el protocolo (E1, arquitectura actual)

XGBoost directo por horizonte: regresión `base_6` de `log1p(casos)` y clasificación `base_6_poblacion_2017`, semilla 17, calibración Platt cronológica. La fila de 2024 es contraste; no decide.

| h | Temporada | P | R | F1 | AUPRC | Brier (sin calibrar) | Razón MAE | Razón RMSE |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 2 | 2022 | 0,508 | 0,499 | 0,504 | 0,558 | 0,081 (0,080) | 0,992 | 1,332 |
| 2 | 2023 | 0,899 | 0,573 | 0,700 | 0,881 | 0,105 (0,102) | 0,986 | 1,140 |
| 2 | 2024 (contraste) | 0,548 | 0,879 | 0,675 | 0,720 | 0,139 (0,119) | 1,138 | 1,514 |
| 4 | 2022 | 0,534 | 0,329 | 0,407 | 0,528 | 0,082 (0,084) | 1,080 | 1,929 |
| 4 | 2023 | 0,894 | 0,412 | 0,564 | 0,834 | 0,127 (0,127) | 0,806 | 0,865 |
| 4 | 2024 (contraste) | 0,510 | 0,838 | 0,634 | 0,653 | 0,155 (0,133) | 1,198 | 1,589 |

Fracción de inicios limpios (95 episodios por horizonte en 2022–2023) con alerta emitida al menos 2 semanas antes:

| h | Modelo (p ≥ 0,50) | Regla de conteos | Persistencia |
|---|---|---|---|
| 2 | 0,105 (IC 0,053–0,168) | 0,074 | 0,116 |
| 4 | 0,084 (IC 0,032–0,147) | 0,095 | 0,211 (IC 0,137–0,295) |

Rangos de empate de E1 entre semillas:

| Métrica | h=2 (2022 / 2023) | h=4 (2022 / 2023) |
|---|---|---|
| F1 con p ≥ 0,50 | 0,021 / 0,014 | 0,013 / 0,024 |
| AUPRC | 0,022 / 0,005 | 0,012 / 0,004 |
| Brier | 0,002 / 0,002 | 0,001 / 0,002 |
| Razón MAE | 0,016 / 0,023 | 0,060 / 0,012 |
| Antelación (fracción avisada) | 0,079–0,105 / 0,105–0,123 | 0,053 / 0,105–0,123 |

**Observaciones:**
- La calibración Platt casi no cambia el Brier en 2022–2023 y lo **empeora en 2024** (0,119 → 0,139 en h=2; 0,133 → 0,155 en h=4). Es coherente con el cambio de confianza entre temporadas visto en la fase 1: el calibrador aprendido con 2021–2023 corrige en la dirección equivocada en 2024.
- En h=4 la persistencia avisa con antelación en más inicios limpios que el modelo (0,211 frente a 0,084). La diferencia formal se evaluará con la comparación pareada cuando corresponda.
- Ningún horizonte cumple la HU0007-4 en las temporadas de selección.

## Fase 3: estrategia multi-horizonte

Matrices de h=1 a 6 construidas en memoria con `features.construir_gold`. Un test comprueba que reproduce exactamente los gold h=2/h=4 (columnas y valores), y la causalidad se verifica por perturbación del futuro para cada h. Gold persistido sigue siendo solo h=2/h=4. La E1 en memoria reproduce las predicciones del experimento 30, con diferencias de hasta 3·10⁻⁵ casos y 3·10⁻⁸ de probabilidad, atribuibles a la lectura del CSV de gold. Las métricas del protocolo coinciden con las de la fase 2. Figura: [`curva_habilidad_horizonte.png`](figuras/curva_habilidad_horizonte.png).

### 3.1 Curva de habilidad (E1, semilla 17)

| h | F1 p ≥ 0,50 (2022 / 2023) | AUPRC modelo (2022 / 2023) | AUPRC persistencia (2022 / 2023) | Razón MAE (2022 / 2023) |
|---|---|---|---|---|
| 1 | 0,572 / 0,753 | 0,605 / 0,897 | 0,754 / 0,921 | 1,025 / 1,144 |
| 2 | 0,504 / 0,700 | 0,558 / 0,881 | 0,676 / 0,899 | 0,992 / 0,986 |
| 3 | 0,454 / 0,651 | 0,542 / 0,853 | 0,640 / 0,868 | 1,009 / 0,871 |
| 4 | 0,407 / 0,564 | 0,528 / 0,834 | 0,576 / 0,844 | 1,080 / 0,806 |
| 5 | 0,381 / 0,472 | 0,506 / 0,811 | 0,506 / 0,811 | 1,167 / 0,746 |
| 6 | 0,363 / 0,440 | 0,485 / 0,794 | 0,480 / 0,774 | 1,262 / 0,707 |

**Observaciones:**
- La señal decae de forma gradual. h=3 queda en el punto medio entre h=2 y h=4; no hay quiebre.
- En ordenamiento (AUPRC), la persistencia iguala o supera al XGBoost hasta h=4 en ambas temporadas; solo empatan desde h=5.
- La razón MAE se mueve en sentidos opuestos según la temporada: mejora con h en 2023 y empeora en 2022.
- El ingenuo estacional (`t−52`) tiene F1 0,043 en 2022 y 0,452 en 2023, y tiene más error que la persistencia en MAE salvo en h=6 de 2023 (razón 0,899).

**Hipótesis:** con las variables actuales, la señal útil más allá de la persistencia es pequeña en todos los horizontes. Ningún horizonte destaca como límite natural.

### 3.3 Estrategias (mediana de 5 semillas; umbral de empate con los rangos propios, incluido h=3)

Veredictos con la regla simétrica corregida (sección 7). La versión original de esta fase descartaba E2 por un veto y por una caída de F1 en una sola temporada; con la regla corregida eso es empate.

| Estrategia | Modelos | Veredicto frente a E1 | Detalle |
|---|---|---|---|
| E2, directa agrupada | 2 | **Empate** en h=2, 3 y 4 | h=2: F1 −0,020 / −0,019 (umbrales 0,021 / 0,031); veto contra E2 por AUPRC y razón MAE, que solo impide ganar. h=3: F1 −0,012 en 2022 (umbral 0,008), pero no en 2023. h=4: F1 +0,004 / +0,069 (umbral de 2022: 0,013). |
| E3, multi-salida | 2 | **Empate** en h=2, 3 y 4 | Diferencias de F1 entre −0,008 y +0,009, dentro de los rangos de semillas. Antelación sin diferencia. |

Coherencia entre horizontes (mediana de semillas, porcentaje de semanas objetivo con cambio de alerta sin explicar):

| Temporada | E1 | E2 | E3 |
|---|---|---|---|
| 2022 | 1,57 % | 0,98 % | 1,04 % |
| 2023 | 2,34 % | 0,50 % | 1,80 % |
| 2024 (contraste) | 1,83 % | 1,30 % | 1,48 % |

**Desempate entre E1, E2 y E3:**
- **(a) Coherencia.** E2 tiene menos cambios sin explicar que E1 en 2022 y en 2023, por encima de los rangos. E3 no supera a E1 en ambas temporadas. Entre E2 y E3 solo hay diferencia en 2023: en 2022 es de 0,06 puntos, frente a un rango de 0,38. Queda E1 fuera.
- **(b) Simplicidad.** E2 y E3 usan 2 modelos cada una. **La regla no decide entre E2 y E3.**

**E4 (recursiva) descartada:** h=1 mejora el F1 respecto de h=2 en solo 0,05–0,07, su MAE es peor que la persistencia (razones 1,025 / 1,144) y su F1 queda por debajo de la persistencia (0,572 frente a 0,734 en 2022). Iterarlo propagaría ese error.

**Limitación de E3 (y de E2):** un único modelo sirve a h=2, 3 y 4, así que en cada bloque se entrena con las etiquetas cerradas antes del primer origen **más temprano**, el de h=4. Para h=2 eso significa **2 semanas menos de etiquetas de entrenamiento** que en E1, donde cada horizonte usa su propio corte. Es la condición para no filtrar información futura en h=4. En operación semanal, el reentrenamiento tendría el mismo desfase de 2 semanas para h=2.

**Resultado de la fase 3 (regla corregida):** E2 y E3 empatan y ambas quedan por delante de E1 en el desempate. Rosa adoptó E3 de forma provisional antes de la corrección de la regla. E2 no se evaluó con las formulaciones de la fase 4. `multi_strategy="multi_output_tree"` funciona en XGBoost 3.4.1 con GPU.

## Fase 4: formulación de la salida

Formulaciones definidas en [`salida_probabilistica.py`](../../../src/modeling/salida_probabilistica.py):

| Id | Media de casos | Probabilidad de brote |
|---|---|---|
| S1 | XGBoost `log1p` + error cuadrático | Clasificador XGBoost + Platt |
| S2_pois | XGBoost `count:poisson` | Clasificador + Platt (igual que S1) |
| S2_twd | XGBoost `reg:tweedie` (potencia 1,5) | Clasificador + Platt (igual que S1) |
| S3 | XGBoost `count:poisson` con `base_margin = log(persistencia + 0,5)` | Clasificador + Platt (igual que S1) |
| **S4_s2** | El modelo de S2_pois (Poisson sin margen) | **Binomial negativa** NB2 con esa media y dispersión α del entrenamiento del bloque: P(casos ≥ k), k = max(⌊umbral⌋ + 1, 2); luego Platt |
| **S4_s3** | El modelo de S3 (Poisson con margen sobre la persistencia) | **Binomial negativa**, igual que S4_s2; luego Platt |
| S5_iso | Como S1 | Clasificador + isotónica |
| S5_spw | Como S1 | Clasificador con `scale_pos_weight` + Platt |

En S4_s2 y S4_s3 la distribución es siempre binomial negativa; «Poisson» se refiere solo a la función de pérdida del modelo de la media. La distribución de Poisson aparece únicamente en el diagnóstico de calibración de más abajo. Se evaluaron sobre E3 y sobre E1, con 5 semillas cada par (mediana) y el protocolo de la fase 2.

### Compatibilidad de `multi_output_tree` (XGBoost 3.4.1, GPU y CPU)

Todo funciona, y se verificó numéricamente además de comprobar que la llamada no falle:
- `count:poisson` reproduce la media de cada salida, y `reg:tweedie` corre.
- `base_margin` funciona con forma (n, 3), una columna por salida. Con forma (n,) se rechaza.
- `feature_importances_` es **agregada** (una por variable, no por horizonte).
- SHAP (`pred_contribs`) es **por horizonte**, aditivo respecto del margen de cada salida, en regresor y clasificador. Esto cubre la HU0008-4.
- `scale_pos_weight` admite un solo valor para las 3 salidas.
- El calibrador por salida es posterior al modelo (Platt o isotónica por horizonte).

Como ninguna formulación falló en E3, E1 se evaluó para comparar el mejor par de cada estrategia.

### No fuga de S4

- `tests/test_umbral_brote_sin_fuga.py`: el `umbral_brote_casos` de la fila t no cambia al alterar casos posteriores a t−h (h=1 y h=6, datos sintéticos y panel real).
- La dispersión α de la binomial negativa se estima solo con el entrenamiento de cada bloque. `test_s4_parametros_solo_con_entrenamiento_del_bloque` altera toda etiqueta que cierra después del corte de 2022 de cada horizonte, y las probabilidades S4 de 2022 no cambian (E1 y E3).
- El umbral se usa solo para convertir la distribución en probabilidad, no como entrada.

### Los 16 pares (mediana de 5 semillas; 2024 es contraste)

| Par | h | F1 p≥0,50 (22 / 23 / 24) | AUPRC (22 / 23 / 24) | Brier (22 / 23 / 24) | MAE/pers. (22 / 23 / 24) | RMSE/pers. (22 / 23 / 24) |
|---|---|---|---|---|---|---|
| E1·S1 | 2 | 0,511 / 0,693 / 0,675 | 0,563 / 0,881 / 0,720 | 0,081 / 0,105 / 0,140 | 0,987 / 0,986 / 1,151 | 1,332 / 1,140 / 1,514 |
| E1·S1 | 3 | 0,455 / 0,660 / 0,651 | 0,542 / 0,854 / 0,693 | 0,080 / 0,117 / 0,148 | 1,009 / 0,865 / 1,214 | 1,572 / 0,956 / 1,630 |
| E1·S1 | 4 | 0,401 / 0,557 / 0,635 | 0,528 / 0,834 / 0,654 | 0,082 / 0,127 / 0,156 | 1,089 / 0,805 / 1,225 | 1,919 / 0,859 / 1,631 |
| E1·S2_pois | 2 | 0,511 / 0,693 / 0,675 | 0,563 / 0,881 / 0,720 | 0,081 / 0,105 / 0,140 | 1,029 / 1,031 / 1,227 | 1,092 / 1,193 / 1,437 |
| E1·S2_pois | 3 | 0,455 / 0,660 / 0,651 | 0,542 / 0,854 / 0,693 | 0,080 / 0,117 / 0,148 | 1,156 / 0,868 / 1,473 | 1,372 / 0,963 / 1,922 |
| E1·S2_pois | 4 | 0,401 / 0,557 / 0,635 | 0,528 / 0,834 / 0,654 | 0,082 / 0,127 / 0,156 | 1,258 / 0,786 / 1,561 | 1,698 / 0,854 / 1,974 |
| E1·S2_twd | 2 | 0,511 / 0,693 / 0,675 | 0,563 / 0,881 / 0,720 | 0,081 / 0,105 / 0,140 | 1,072 / 0,952 / 1,368 | 1,377 / 1,102 / 1,894 |
| E1·S2_twd | 3 | 0,455 / 0,660 / 0,651 | 0,542 / 0,854 / 0,693 | 0,080 / 0,117 / 0,148 | 1,203 / 0,844 / 1,604 | 1,783 / 0,937 / 2,338 |
| E1·S2_twd | 4 | 0,401 / 0,557 / 0,635 | 0,528 / 0,834 / 0,654 | 0,082 / 0,127 / 0,156 | 1,342 / 0,779 / 1,715 | 2,187 / 0,844 / 2,428 |
| E1·S3 | 2 | 0,511 / 0,693 / 0,675 | 0,563 / 0,881 / 0,720 | 0,081 / 0,105 / 0,140 | 1,134 / 0,886 / 1,404 | 1,415 / 0,994 / 2,001 |
| E1·S3 | 3 | 0,455 / 0,660 / 0,651 | 0,542 / 0,854 / 0,693 | 0,080 / 0,117 / 0,148 | 1,285 / 0,811 / 1,659 | 1,859 / 0,905 / 2,563 |
| E1·S3 | 4 | 0,401 / 0,557 / 0,635 | 0,528 / 0,834 / 0,654 | 0,082 / 0,127 / 0,156 | 1,429 / 0,770 / 1,785 | 2,419 / 0,843 / 2,767 |
| E1·S4_s2 | 2 | 0,653 / 0,847 / 0,811 | 0,789 / 0,946 / 0,890 | 0,052 / 0,064 / 0,074 | 1,029 / 1,031 / 1,227 | 1,092 / 1,193 / 1,437 |
| E1·S4_s2 | 3 | 0,559 / 0,811 / 0,787 | 0,775 / 0,928 / 0,862 | 0,058 / 0,077 / 0,086 | 1,156 / 0,868 / 1,473 | 1,372 / 0,963 / 1,922 |
| E1·S4_s2 | 4 | 0,439 / 0,789 / 0,753 | 0,739 / 0,916 / 0,817 | 0,065 / 0,087 / 0,100 | 1,258 / 0,786 / 1,561 | 1,698 / 0,854 / 1,974 |
| E1·S4_s3 | 2 | 0,693 / 0,847 / 0,802 | 0,786 / 0,948 / 0,895 | 0,053 / 0,064 / 0,073 | 1,134 / 0,886 / 1,404 | 1,415 / 0,994 / 2,001 |
| E1·S4_s3 | 3 | 0,552 / 0,816 / 0,785 | 0,766 / 0,928 / 0,873 | 0,059 / 0,078 / 0,083 | 1,285 / 0,811 / 1,659 | 1,859 / 0,905 / 2,563 |
| E1·S4_s3 | 4 | 0,378 / 0,787 / 0,752 | 0,733 / 0,915 / 0,834 | 0,068 / 0,089 / 0,095 | 1,429 / 0,770 / 1,785 | 2,419 / 0,843 / 2,767 |
| E1·S5_iso | 2 | 0,537 / 0,675 / 0,673 | 0,494 / 0,863 / 0,688 | 0,089 / 0,107 / 0,141 | 0,987 / 0,986 / 1,151 | 1,332 / 1,140 / 1,514 |
| E1·S5_iso | 3 | 0,523 / 0,560 / 0,651 | 0,456 / 0,839 / 0,668 | 0,089 / 0,121 / 0,150 | 1,009 / 0,865 / 1,214 | 1,572 / 0,956 / 1,630 |
| E1·S5_iso | 4 | 0,475 / 0,311 / 0,638 | 0,442 / 0,823 / 0,618 | 0,090 / 0,131 / 0,160 | 1,089 / 0,805 / 1,225 | 1,919 / 0,859 / 1,631 |
| E1·S5_spw | 2 | 0,475 / 0,561 / 0,666 | 0,555 / 0,875 / 0,703 | 0,079 / 0,122 / 0,122 | 0,987 / 0,986 / 1,151 | 1,332 / 1,140 / 1,514 |
| E1·S5_spw | 3 | 0,369 / 0,351 / 0,642 | 0,510 / 0,848 / 0,666 | 0,082 / 0,137 / 0,129 | 1,009 / 0,865 / 1,214 | 1,572 / 0,956 / 1,630 |
| E1·S5_spw | 4 | 0,289 / 0,238 / 0,619 | 0,487 / 0,829 / 0,627 | 0,085 / 0,145 / 0,137 | 1,089 / 0,805 / 1,225 | 1,919 / 0,859 / 1,631 |
| E3·S1 | 2 | 0,505 / 0,700 / 0,676 | 0,546 / 0,878 / 0,710 | 0,082 / 0,105 / 0,139 | 1,004 / 1,001 / 1,220 | 1,413 / 1,160 / 1,657 |
| E3·S1 | 3 | 0,456 / 0,652 / 0,655 | 0,525 / 0,855 / 0,683 | 0,082 / 0,117 / 0,147 | 1,021 / 0,866 / 1,264 | 1,641 / 0,959 / 1,726 |
| E3·S1 | 4 | 0,395 / 0,566 / 0,633 | 0,504 / 0,839 / 0,641 | 0,085 / 0,127 / 0,157 | 1,104 / 0,801 / 1,229 | 1,968 / 0,854 / 1,659 |
| E3·S2_pois | 2 | 0,505 / 0,700 / 0,676 | 0,546 / 0,878 / 0,710 | 0,082 / 0,105 / 0,139 | 1,056 / 1,005 / 1,349 | 1,173 / 1,174 / 1,780 |
| E3·S2_pois | 3 | 0,456 / 0,652 / 0,655 | 0,525 / 0,855 / 0,683 | 0,082 / 0,117 / 0,147 | 1,153 / 0,865 / 1,465 | 1,377 / 0,963 / 1,883 |
| E3·S2_pois | 4 | 0,395 / 0,566 / 0,633 | 0,504 / 0,839 / 0,641 | 0,085 / 0,127 / 0,157 | 1,293 / 0,793 / 1,504 | 1,666 / 0,846 / 1,874 |
| E3·S2_twd | 2 | 0,505 / 0,700 / 0,676 | 0,546 / 0,878 / 0,710 | 0,082 / 0,105 / 0,139 | 1,061 / 0,964 / 1,448 | 1,404 / 1,115 / 2,056 |
| E3·S2_twd | 3 | 0,456 / 0,652 / 0,655 | 0,525 / 0,855 / 0,683 | 0,082 / 0,117 / 0,147 | 1,195 / 0,844 / 1,594 | 1,765 / 0,943 / 2,253 |
| E3·S2_twd | 4 | 0,395 / 0,566 / 0,633 | 0,504 / 0,839 / 0,641 | 0,085 / 0,127 / 0,157 | 1,372 / 0,780 / 1,657 | 2,213 / 0,837 / 2,257 |
| E3·S3 | 2 | 0,505 / 0,700 / 0,676 | 0,546 / 0,878 / 0,710 | 0,082 / 0,105 / 0,139 | 1,133 / 0,891 / 1,487 | 1,426 / 1,001 / 2,227 |
| E3·S3 | 3 | 0,456 / 0,652 / 0,655 | 0,525 / 0,855 / 0,683 | 0,082 / 0,117 / 0,147 | 1,269 / 0,813 / 1,655 | 1,816 / 0,909 / 2,483 |
| E3·S3 | 4 | 0,395 / 0,566 / 0,633 | 0,504 / 0,839 / 0,641 | 0,085 / 0,127 / 0,157 | 1,427 / 0,768 / 1,750 | 2,299 / 0,841 / 2,614 |
| E3·S4_s2 | 2 | 0,682 / 0,845 / 0,815 | 0,796 / 0,948 / 0,894 | 0,051 / 0,063 / 0,073 | 1,056 / 1,005 / 1,349 | 1,173 / 1,174 / 1,780 |
| E3·S4_s2 | 3 | 0,590 / 0,812 / 0,789 | 0,784 / 0,929 / 0,867 | 0,057 / 0,077 / 0,086 | 1,153 / 0,865 / 1,465 | 1,377 / 0,963 / 1,883 |
| E3·S4_s2 | 4 | 0,478 / 0,779 / 0,751 | 0,742 / 0,916 / 0,820 | 0,064 / 0,089 / 0,100 | 1,293 / 0,793 / 1,504 | 1,666 / 0,846 / 1,874 |
| E3·S4_s3 | 2 | 0,690 / 0,847 / 0,802 | 0,788 / 0,947 / 0,894 | 0,052 / 0,064 / 0,074 | 1,133 / 0,891 / 1,487 | 1,426 / 1,001 / 2,227 |
| E3·S4_s3 | 3 | 0,577 / 0,816 / 0,785 | 0,780 / 0,927 / 0,874 | 0,058 / 0,078 / 0,083 | 1,269 / 0,813 / 1,655 | 1,816 / 0,909 / 2,483 |
| E3·S4_s3 | 4 | 0,446 / 0,785 / 0,751 | 0,749 / 0,916 / 0,836 | 0,065 / 0,089 / 0,095 | 1,427 / 0,768 / 1,750 | 2,299 / 0,841 / 2,614 |
| E3·S5_iso | 2 | 0,535 / 0,655 / 0,674 | 0,461 / 0,862 / 0,681 | 0,090 / 0,108 / 0,141 | 1,004 / 1,001 / 1,220 | 1,413 / 1,160 / 1,657 |
| E3·S5_iso | 3 | 0,510 / 0,580 / 0,648 | 0,452 / 0,838 / 0,647 | 0,088 / 0,120 / 0,150 | 1,021 / 0,866 / 1,264 | 1,641 / 0,959 / 1,726 |
| E3·S5_iso | 4 | 0,491 / 0,386 / 0,627 | 0,436 / 0,826 / 0,596 | 0,093 / 0,129 / 0,163 | 1,104 / 0,801 / 1,229 | 1,968 / 0,854 / 1,659 |
| E3·S5_spw | 2 | 0,456 / 0,516 / 0,651 | 0,535 / 0,869 / 0,694 | 0,081 / 0,124 / 0,123 | 1,004 / 1,001 / 1,220 | 1,413 / 1,160 / 1,657 |
| E3·S5_spw | 3 | 0,370 / 0,374 / 0,638 | 0,506 / 0,848 / 0,668 | 0,083 / 0,135 / 0,129 | 1,021 / 0,866 / 1,264 | 1,641 / 0,959 / 1,726 |
| E3·S5_spw | 4 | 0,302 / 0,268 / 0,621 | 0,473 / 0,833 / 0,629 | 0,086 / 0,144 / 0,137 | 1,104 / 0,801 / 1,229 | 1,968 / 0,854 / 1,659 |

### Decisión con la regla preregistrada (simétrica)

El umbral de empate es el de la sección 6: el mayor rango de semillas de los dos pares comparados, por métrica, horizonte y temporada.

| Comparación | Resultado | Elección |
|---|---|---|
| Dentro de E3, frente a S1 | S4_s2 y S4_s3 ganan en h=2, 3 y 4. S5_spw pierde en los tres y se descarta. S2, S3 y S5_iso empatan. | Cruce directo S4_s2 / S4_s3: empate en los tres h. Coherencia: S4_s3 es mejor solo en 2023. Las dos usan 1 modelo. **Sin resolver entre S4_s2 y S4_s3.** |
| Dentro de E1, frente a S1 | S4_s2 gana en h=3 y h=4 (compensa en h=2). S4_s3 gana en h=2 y h=3 (empate en h=4). S5_spw se descarta. | Cruce directo: empate en los tres h. Coherencia: S4_s2 es mejor en 2022 y S4_s3 en 2023. Las dos usan 3 modelos. **Sin resolver.** |
| E3·S4 frente a E1·S4 (las 4 combinaciones) | E3·S4_s3 gana a E1·S4_s2 en h=3 y empata en h=2 y h=4. Las otras 3 combinaciones empatan en todos los h. | En los empates la coherencia no separa y la simplicidad favorece a E3 (1 modelo frente a 3). **Gana E3 con S4, sin resolver entre S4_s2 y S4_s3.** |

La primera versión de este informe descartaba E3 por una caída de F1 de 0,010 en h=4 en 2023 (umbral 0,008). Con la regla simétrica, esa caída en una sola temporada es empate: en 2022 E3 tiene +0,039.

**Auditoría independiente.** Un subagente revisor recalculó todo desde las predicciones guardadas y el texto del protocolo, sin leer el código de selección ni de evaluación. Llegó a las mismas decisiones y comprobó que las 48 comparaciones dentro de cada estrategia y las cruzadas salen en espejo. Las interpretaciones que tuvo que hacer (desigualdades estrictas, signo por temporada con la semilla 17) no cambian ninguna decisión.

### Calibración de S4: Poisson frente a binomial negativa (diagnóstico, E3·S4_s2)

- **Poisson sale sobreconfiado.** Sin calibrar (h=4, semilla 17), sus probabilidades de 0,9 a 1,0 se cumplen entre el 77 % y el 96 % de las veces; el intervalo incluye las probabilidades exactamente iguales a 1, que son 60–201 filas por temporada. Las de 0,6–0,9 se cumplen entre el 38 % y el 74 %; con la mediana de semillas, entre el 36 % y el 73 %. Su probabilidad media supera la prevalencia en 2022 y 2024 (h=4: 0,150 frente a 0,128 y 0,350 frente a 0,254).
- En la binomial negativa, la probabilidad media queda cerca de la prevalencia en 2022 y 2024. Aun así, es **poco confiada**: en los tramos de 0,5 a 0,8 de h=4 la frecuencia observada supera a la predicha en 0,1–0,2, también en 2022 y 2024. En 2023 la diferencia es mayor (probabilidad media 0,203 frente a una prevalencia de 0,307 en h=4).
- Después de Platt, la binomial negativa tiene F1 y AUPRC iguales o mayores que Poisson en todas las celdas, salvo F1 de h=4 en 2022.
- Figuras: `fiabilidad_s4_poisson_sin_calibrar_E3.png` y `fiabilidad_s4_binomial_negativa_sin_calibrar_E3.png`.

### ¿Anticipa brotes nuevos? No

- **Antelación sobre inicios limpios (2022–2023, 95 episodios):** ningún par mejora a S1 con un intervalo que excluya 0. Frente a la persistencia en h=4 (0,211), con la semilla 17, que es la que usa la diferencia pareada: E3·S4_s2 avisa 0,105 (diferencia −0,105, IC −0,189 a −0,021) y E1·S4_s2 avisa 0,105 (−0,105, IC −0,200 a −0,011). E1·S4_s3 y E3·S4_s3 avisan 0,137 y 0,147, con IC que incluyen 0. Las medianas de las 5 semillas son 0,105, 0,126, 0,137 y 0,158.
- **Recall por tipo de semana brote (mediana de semillas):** en las 2 primeras semanas de brotes nuevos el recall se queda entre 0,00 y 0,15 con S1 y con S4 (49 semanas en 2022 y 86 en 2023). En semanas de brotes en curso, S4 lo sube mucho: en 2023, de 0,61 a 0,85 en h=2 y de 0,43 a 0,74 en h=4 (E1).

**Conclusión:** la mejora de S4 viene de **acertar más semanas de brotes que ya están en curso**. No viene de anticipar brotes nuevos.

### Conteo de S4 frente a la persistencia, por fase (mediana de semillas, por temporada)

El conteo de S4_s2 es su modelo Poisson. La razón se calcula por temporada y semilla, y se reporta la mediana de las 5 semillas **en cada temporada**: mezclar 2022 y 2023 en una sola mediana daría un valor que no representa a ninguna.

| Par | h | Temporada | Subida | Pico | Bajada | Valle |
|---|---|---|---|---|---|---|
| E1·S1 (log1p) | 4 | 2022 | 1,13 | 1,72 | 0,39 | 0,68 |
| E1·S1 (log1p) | 4 | 2023 | 0,90 | 1,11 | 0,43 | 0,85 |
| E1·S4_s2 | 2 | 2022 | 1,10 | 1,21 | 0,69 | 0,95 |
| E1·S4_s2 | 2 | 2023 | 0,91 | 1,22 | 0,79 | 1,06 |
| E1·S4_s2 | 4 | 2022 | 1,02 | 2,02 | 0,68 | 0,77 |
| E1·S4_s2 | 4 | 2023 | 0,81 | 1,10 | 0,42 | 0,88 |
| E3·S4_s2 | 2 | 2022 | 1,12 | 1,21 | 0,74 | 0,97 |
| E3·S4_s2 | 2 | 2023 | 0,93 | 1,22 | 0,69 | 1,02 |
| E3·S4_s2 | 4 | 2022 | 1,02 | 2,04 | 0,71 | 0,88 |
| E3·S4_s2 | 4 | 2023 | 0,81 | 1,09 | 0,45 | 0,91 |

Los valores son la razón MAE. La razón RMSE sigue el mismo patrón (pico > 1 y bajada < 1 en todos los casos) y está en el JSON. El conteo sigue perdiendo en el **pico** en todas las formulaciones. Ningún modelo de conteo (log1p, Poisson, Tweedie, S3) cumple MAE y RMSE ≤ 0,85 de la persistencia en 2022 y 2023 a la vez. Ninguna alternativa a log1p mejora el MAE en ambas temporadas: en 2022 todas empeoran en los tres horizontes, y en 2023 algunas mejoran (S3 en h=2: 0,886 frente a 0,986, en E1).

## Fase 5: síntesis y decisión

### Arquitectura elegida

**E3 + S4_s2**, decidida por Rosa al cerrar la fase 4 con la regla simétrica:

| Pieza | Qué es |
|---|---|
| Estrategia | E3: un XGBoost `multi_strategy="multi_output_tree"` predice el vector (t+2, t+3, t+4) desde el mismo origen, con los predictores de h=2 (`base_6` en nombres genéricos). |
| Casos | La salida del modelo con `objective="count:poisson"`: media de casos por horizonte. |
| Probabilidad de brote | P(casos ≥ k) con binomial negativa NB2, media del modelo y α estimada por máxima verosimilitud en el entrenamiento de cada bloque (una por horizonte); k = max(⌊umbral_brote_casos⌋ + 1, 2). Después, Platt cronológico por horizonte. |
| Regla de alerta | Probabilidad calibrada ≥ 0,50; niveles con los cortes 0,25 / 0,50 / 0,75. |
| Modelos a desplegar | **1** (hoy son 6: regresor y clasificador para h=2 y h=4, sin h=3). |

**Criterio:**
- E3·S4 gana a E1·S4. Frente a E1·S4_s2 gana E3·S4_s3 por la regla (h=3); las otras combinaciones empatan y la simplicidad favorece a E3.
- S4_s2 y S4_s3 empatan con la regla. Se elige S4_s2 por ser la más simple: no depende del margen de persistencia.

**Alternativas documentadas, sin adoptar:**
- **E3·S4_s3:** empata con S4_s2 y tiene mejor antelación en h=4 (15,8 % frente a 10,5 % de inicios limpios avisados, mediana de semillas; diferencia no significativa). Revisarla si en la etapa de variables la anticipación pasa a ser el problema central.
- **E2 (directa agrupada):** empató con E3 en la fase 3 y no se evaluó con S4. En h=2 empeoró AUPRC y MAE en ambas temporadas (veto), así que por la regla no podía ganar frente a E3, y otra comparación solo agregaría riesgo de selección.

### Resultados de E3·S4_s2 (mediana de 5 semillas; 2024 es contraste)

| h | Temporada | P | R | F1 | AUPRC | Brier | MAE / pers. | RMSE / pers. |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 2 | 2022 | 0,794 | 0,601 | 0,682 | 0,796 | 0,051 | 1,056 | 1,173 |
| 2 | 2023 | 0,919 | 0,782 | 0,845 | 0,948 | 0,063 | 1,005 | 1,174 |
| 2 | 2024 | 0,750 | 0,894 | 0,815 | 0,894 | 0,073 | 1,349 | 1,780 |
| 3 | 2022 | 0,869 | 0,445 | 0,590 | 0,784 | 0,057 | 1,153 | 1,377 |
| 3 | 2023 | 0,936 | 0,716 | 0,812 | 0,929 | 0,077 | 0,865 | 0,963 |
| 3 | 2024 | 0,716 | 0,880 | 0,789 | 0,867 | 0,086 | 1,465 | 1,883 |
| 4 | 2022 | 0,890 | 0,327 | 0,478 | 0,742 | 0,064 | 1,293 | 1,666 |
| 4 | 2023 | 0,941 | 0,664 | 0,779 | 0,916 | 0,089 | 0,793 | 0,846 |
| 4 | 2024 | 0,664 | 0,867 | 0,751 | 0,820 | 0,100 | 1,504 | 1,874 |

En el año calendario 2025 (sensibilidad de conteos, 3 positivos), el conteo de S4_s2 tiene razón MAE 2,016 / 2,451 / 2,769 (h=2 / 3 / 4) frente a la persistencia: en un periodo de casi cero casos, el modelo Poisson sobreestima más que la persistencia.

Frente a la arquitectura actual (E1·S1), el F1 con p ≥ 0,50 sube en 2022 / 2023 de 0,51 / 0,69 a 0,68 / 0,85 en h=2 y de 0,40 / 0,56 a 0,48 / 0,78 en h=4. El Brier baja de 0,08–0,13 a 0,05–0,09.

### Cumplimiento de la HU0007-4 (línea base; no fue criterio de decisión)

- **Clasificación** (P ≥ 0,60, R ≥ 0,80 y F1 ≥ 0,70 con p ≥ 0,50):
  - No se cumple en ninguna temporada de selección. Falla siempre el recall: 0,327–0,601 en 2022 y 0,664–0,782 en 2023. En h=2 de 2023 falta 0,018 para llegar a 0,80.
  - Se cumple en h=2, h=3, h=4 de 2024. Ese año es contraste ya inspeccionado y no sirve para aceptar.
- **Regresión** (MAE y RMSE ≤ 85 % de la persistencia): se cumple solo en h=4 de 2023 (0,793 y 0,846). En el resto de las celdas el conteo no alcanza el 85 %.
- **Consecuencia operativa:** `cumple_umbrales` sigue siendo falso. El modelo se serviría como experimental, según la desviación temporal (a) de `docs/backend/desviaciones_oe2.md`.

### Importancia de variables por horizonte (HU0008-4)

E3·S4_s2 tiene un único modelo, el de casos. La importancia por horizonte es la media de |SHAP| de cada salida (`pred_contribs`, aditivo respecto del margen en escala log). Así es como `multi_output_tree` da importancias por horizonte: `feature_importances_` solo da la agregada. Las tablas por bloque (2022–2024, semilla 17) están en `fase5_decision` del JSON y en el notebook 31.

Bloque 2023:

| Horizonte | `hist_lag_a` | `hist_lag_b` | `hist_media_4` | `hist_semanas_pos_4` | `semana_epi_seno` | `semana_epi_coseno` |
|---|---:|---:|---:|---:|---:|---:|
| h=2 | 1,406 | 0,297 | 1,000 | 0,107 | 0,189 | 0,076 |
| h=3 | 1,351 | 0,285 | 0,954 | 0,100 | 0,257 | 0,127 |
| h=4 | 1,300 | 0,272 | 0,910 | 0,093 | 0,308 | 0,182 |

**Observación:**
- Dominan los casos del origen (`hist_lag_a`) y la media de 4 semanas, y su peso baja un poco con el horizonte.
- El peso del calendario (seno y coseno de la semana) crece con el horizonte. El mismo patrón aparece en 2022 y 2024.
- La dispersión α de la binomial negativa también crece con el horizonte: 0,767 / 1,387 / 2,222 en h=2 / 3 / 4 (bloque 2023). A mayor horizonte, más incertidumbre en el conteo.

### Hallazgo central: detecta mejor brotes en curso, no anticipa brotes nuevos

- **Lo que mejora S4:** el recall en semanas de brotes **en curso**, de 0,43–0,62 a 0,72–0,85 en 2023.
- **Lo que no cambia:** el recall en las 2 primeras semanas de brotes **nuevos** se queda entre 0,00 y 0,15, igual que con S1.
- **Antelación sobre inicios limpios:** ningún par mejora a S1. En h=4 E3·S4_s2 avisa el 10,5 % frente al 21,1 % de la persistencia (diferencia pareada −0,105; IC −0,189 a −0,021).
- **Por fase de la curva:** el conteo de E3·S4_s2 sigue perdiendo frente a la persistencia en el pico: razón MAE 1,21–2,04 en 2022 y 1,09–1,22 en 2023, según el horizonte.

**Esto define la siguiente etapa de variables:** buscar señal que preceda al inicio de un brote. No basta con describir mejor un brote que ya empezó.

### Cambios que implicaría la arquitectura elegida (no implementados)

**Gold y feature engineering (los ejecuta el equipo)**
- Para **entrenar**, E3 necesita **solo gold h=2**. La tabla de entrenamiento se arma en memoria desde gold h=2: una fila por origen con sus predictores, y los objetivos t+3 y t+4 (casos y `brote`) son las filas siguientes del mismo distrito (`estrategias_horizonte.tabla_origenes`). No hace falta un gold h=3 ni un gold apilado.
- La **evaluación** de este encargo usó, para h=3 y h=4, las etiquetas (`brote`) y los umbrales (`umbral_brote_casos`) de las semanas objetivo de las matrices h=3 y h=4 construidas en memoria con `features.construir_gold`. El test de regresión garantiza que reproducen gold en h=2 y h=4.
- En **producción**, el umbral de las semanas objetivo o+2, o+3 y o+4 todavía no existe en el panel. Debe venir de la función nueva descrita en «Serving».
- `features.py` y el notebook 22 no cambian. Gold h=4 deja de ser entrada del modelo; puede conservarse para comparar.
- Si el equipo prefiere persistir la tabla de orígenes, sería un archivo gold nuevo derivado de h=2. Requiere validación GX y los tests de no fuga ya existentes (`test_horizontes_generalizados`, `test_estrategias_horizonte`).

**Serving**
- `config.yaml` → `serving.horizontes: [2, 3, 4]`.
- `configuracion.py`: deja de exigir gold por horizonte. Los tres horizontes salen del vector de h=2.
- `inferencia.py`: se retiran `MOTIVO_H3` y el 409 de h=3.
- `inferencia_futura.py`: se quita la guarda que limita a h=2/4 y se construye un solo vector por distrito y corte.
- **Artefacto:** un paquete con el booster multi-salida, las tres α de la binomial negativa y los tres calibradores Platt (pendiente y ordenada por horizonte), con un solo SHA-256.
- `publicar.py`: ajuste final con etiquetas cerradas hasta el último corte (el corte lo fija h=4, ver la limitación de E3). Los calibradores salen de las predicciones OOS del protocolo.
- `importancia_variable`: SHAP por horizonte.
- **Umbral de brote de semanas futuras (requisito de S4).** S4 convierte la media de casos en P(casos ≥ k) con `k = max(⌊umbral_brote_casos⌋ + 1, 2)` de cada semana objetivo. Hoy ni `src/serving/` ni `inferencia_futura.py` calculan ese umbral para semanas que aún no están en el panel. Se necesita:
  - Una función (por ejemplo, `umbral_brote_futuro` en `src/modeling/etiqueta_brote.py`) que calcule el umbral de cualquier semana objetivo con la **misma regla** de `etiquetar_brote_estacional`: misma semana epidemiológica de los 5 años previos, con la semana 53 sumada a la 52 para la referencia; media + multiplicador · DE muestral (`ddof=1`); ausencias históricas como cero; parámetros leídos de `parametro_sistema` / `manifest_fase6.json`.
  - La función debe funcionar también para semanas de un año que todavía no está en el panel (por ejemplo, las primeras de 2026 emitidas desde un origen de diciembre de 2025).
  - Un test que verifique que, para todas las semanas ya observadas, la función da **exactamente** el mismo `umbral_brote_casos` que gold.
  - Solo usa casos de años anteriores al de la semana objetivo, así que no depende de datos posteriores al origen. Ya lo cubre `tests/test_umbral_brote_sin_fuga.py`.

**BD: cómo encaja «1 modelo, 2 tareas, 3 horizontes» en OE2**

| Opción | Qué cambia | Desviación |
|---|---|---|
| **A (propuesta).** Seis filas de `version_modelo`, una por (tarea, horizonte), que apuntan al **mismo artefacto** (`ruta_artefacto` y `sha256_artefacto` iguales) | Ningún cambio de DDL. `prediccion.id_version_clasificador` e `id_version_regresor` apuntan a las filas (clasificación, h) y (regresión, h). El índice de una activa por (tarea, horizonte) se cumple tal cual | Solo de uso: varias filas comparten artefacto, y la activación debe hacerse **por horizonte, en pareja** (clasificación y regresión de ese h salen de la misma salida del modelo) |
| B. Una sola fila con `horizonte` nulo o tarea `multitarea` | Cambia el ENUM `tarea_t` y el CHECK de `horizonte`; `prediccion` debería apuntar a una sola versión | Cambio de DDL: corrección del documento OE2 |
| C. Tres filas por horizonte con una tarea combinada | Cambia `tarea_t`, y `prediccion` usaría la misma FK en las dos columnas | Cambio de DDL y semántica forzada |

Se recomienda **A**, la de menor desviación. El texto propuesto está en `docs/backend/desviaciones_oe2.md`, sección 8, como propuesta no implementada.

### Pendiente para las siguientes etapas

**Feature engineering:**
- Variables que anticipen inicios: vecinos y jerarquía con rezagos que precedan al inicio, clima con ventanas de incubación y señales de importación.
- Evaluarlas sobre E3·S4_s2 con este protocolo, usando como criterio principal la antelación sobre inicios limpios y el recall en brotes nuevos.
- Las ablaciones anteriores se hicieron con S1. No se pueden trasladar a S4 sin repetirlas.

**Hiperparámetros (HU0007-3):**
- Buscar sobre el modelo `count:poisson` multi-salida: profundidad, número de árboles, tasa y regularización.
- Opcional: la forma de estimar α (por ejemplo, con OOS de bloques previos en lugar del ajuste dentro de la muestra).
- Selección con 2022–2023 y la regla simétrica; 2024 solo como contraste.

**Otros:**
- Medir de nuevo la variación entre semillas tras cualquier cambio. Con E3·S4_s2 los rangos de F1 son muy chicos (0,005–0,021 en 2022–2023), así que diferencias pequeñas ya cuentan.

### Límites

- **2024 no es un test virgen** y 2025 solo tiene 3 positivos. El test independiente real son las semanas de 2026 publicadas tras congelar la arquitectura (HU0019).
- **La regla de decisión se corrigió durante la fase 4**, después de ver resultados, porque era asimétrica. Una auditoría independiente recalculó las decisiones con el texto corregido y coincidió en todas.
- **E3 entrena h=2 con el corte de h=4** (2 semanas menos de etiquetas).
- **La α de la binomial negativa se estima dentro de la muestra de entrenamiento** y puede quedar subestimada; Platt corrige la escala, pero la calibración cambia entre temporadas: en 2023 el modelo es poco confiado.
- **Todo se midió en un solo equipo (GPU).** La demora de publicación de MINSA no se modela (limitación aceptada).
- **Sin lenguaje causal:** las mejoras son asociaciones en 2022–2023, con pocas temporadas epidémicas.

## Resumen para el asesor

1. **Qué se hizo.** Se revisaron los siete experimentos y se fijó por adelantado un protocolo de evaluación:
   - origen móvil por temporada;
   - selección con 2022–2023;
   - alerta con probabilidad calibrada ≥ 0,50;
   - regla de decisión simétrica con 5 semillas.

   Con ese protocolo se compararon tres estrategias multi-horizonte y ocho formas de producir la salida, para h=2, 3 y 4, sin cambiar las variables.
2. **Qué se eligió.** Un único modelo XGBoost multi-salida de conteo (Poisson) que predice h=2, 3 y 4 desde el mismo origen. La probabilidad de brote se obtiene con una binomial negativa sobre la media predicha y el umbral de brote de la semana, ya conocido al emitir. Reemplaza 6 modelos por 1 e incorpora h=3.
3. **Cuánto mejora.** En las temporadas de selección, el F1 de alerta sube de 0,51 / 0,69 a 0,68 / 0,85 en h=2 y de 0,40 / 0,56 a 0,48 / 0,78 en h=4. El AUPRC y el Brier también mejoran. Todavía no cumple los umbrales de la HU0007-4 en 2022–2023 (falta recall), y el conteo sigue sin superar de forma estable a la persistencia.
4. **De dónde viene la mejora.** De **detectar mejor brotes que ya están en curso**, no de **anticipar brotes nuevos**:
   - el recall en las primeras semanas de un brote nuevo no cambia (0,00–0,15);
   - a 4 semanas, el modelo avisa con antelación menos inicios que la simple persistencia (10,5 % frente a 21,1 %).
5. **Qué sigue.** La próxima etapa de variables debe orientarse a señales que precedan el inicio de un brote, medidas sobre esta arquitectura. Después corresponde ajustar hiperparámetros (HU0007-3).
