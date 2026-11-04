# Mejora del modelo sobre la V2

Informe del estudio 06. Plan y decisiones de Rosa en [plan.md](plan.md); preregistros en
`code/preregistration.py`.

## Estado actual (2026-11-03)

Rama `exp/model-improvement`. Para retomar: leer `CLAUDE.md`, [plan.md](plan.md) y este informe, y seguir desde
aquí.

**Fases cerradas (todas confirmadas por Rosa):**

| Fase | Qué se probó | Qué se adoptó |
|---|---|---|
| 0 · Diagnóstico | errores por estado, calibración, persistencia, historia 2000–2016 (sin entrenar) | nada (diagnóstico) |
| 1a · Más historia | V1 entrenada desde 2005 (L) frente a desde 2017 (R) | **L** (entrenar desde 2005); ganancia de referencia frente a la V1 tal cual: 2022 · h3 +0,046 y h4 +0,106 de F1 |
| 2 · Calibración | recorte 1e-15, Platt agrupado, beta, isotónica | nada: Platt por horizonte con recorte 1e-6 (beta, cerca en h4, no alcanza la regla) |
| 3 · Inicios | 3a1 peso a inicios, 3a2 peso por temporada, 3b dos regímenes, 3c′ L + B1 + B2 (enmienda) | nada: L sigue como base (3a1 es un intercambio: más recall de inicios a cambio de orden y brotes en curso) |
| 5 · Conteo | 5a mezcla con la persistencia, 5b `max_delta_step` por bloque, 5c peso por temporada | **5a**: conteo = w·μ + (1 − w)·persistencia, w por horizonte y bloque con las OOS anteriores |
| 6 · Otra familia (lectura) | 6a GLM NB2 (no convergió), enmienda 6a′ GLM Poisson + α NB2, 6b LightGBM; C3 sin clima | nada (lectura): LightGBM empata con L + 5a; 6a′ empata o mejora (gana F1 en h4, mejor antelación, peor Brier en 2016); 6′ con clima, pendiente de la 1b |

**Configuración base actual: L + 5a.**

- Modelo: C3 (`base_6` + B3) · E3 · S4_s3 · XGBoost con los hiperparámetros de la V1, entrenado con los orígenes
  desde 2005, bloques por temporada (ventana creciente), α dentro de la muestra, Platt por horizonte con recorte 1e-6,
  alerta p ≥ 0,50.
- **Decisión de diseño (Rosa, 2026-11-03): dos μ con funciones distintas.** Los **casos** publicados salen de la μ
  mezclada (w·μ + (1 − w)·persistencia); la **probabilidad** de brote (NB2 → Platt) y la alerta salen de la μ del
  modelo. La lectura de la fase 5 mostró que calcular la probabilidad con la μ mezclada empeora la AUPRC y el Brier
  en 2–3 temporadas («compensa» en h2, h3 y h4). El intervalo del conteo queda para la fase 7.
- Código: matrices y orígenes largos y bucle de bloques en `code/phase1_history.py` (`long_matrices`,
  `long_origins`, `predict_blocks`) y `code/phase3_onsets.py` (`predict_blocks_weighted`); calibración con
  `denguekay.evaluation.protocol`; mezcla en `code/phase5_counts.py` (`mix_chronologically`, `fit_w`); reglas en
  `code/preregistration.py`. Predicciones de L en `models/experimentos/mejora_modelo/fase1a/` (no versionado).

**Pendiente del equipo (lo corre el equipo, no Claude):**

1. ~~Celda A (ERA5 fijo 2017–2025)~~: hecha; comparación en `notebooks/03_fase1b_consistencia_clima.ipynb`
   (commit `fefa3b2`). Rosa descartó ERA5 a 0,25° (precipitación idéntica entre vecinos en 48 distritos) y
   «Best match» para 2000–2016 (antes de 2017 no tiene el IFS: el empalme existiría sin medirlo).
2. ~~Celda A2 (ERA5-Land, muestra de 16 distritos)~~: hecha. ERA5-Land no trae precipitación en Open-Meteo
   (ver «Fase 1b′»). Pendiente: celdas A3 y B2 del notebook 02 (ERA5-Land 2000–2025, 65 distritos, humedad y
   temperatura; unos 4–5 días por el límite diario del API) y la sección 1b′ del notebook 03 del pipeline, que
   escribe `data/silver/meteo_humedad_era5_land_2000_2025.csv` (rama `feat/era5-land-humidity-history`).
3. ~~Ingesta del Niño 1+2 (NOAA CPC)~~: hecha por Rosa el 2026-11-03 con `pipelines/notebooks/03b_ingesta_enso.ipynb`.
   Archivo crudo `data/bronze/enso/sstoi_20261103.indices`; `data/silver/enso_nino12_mensual.csv` con 538 meses,
   de 1982-01 a 2026-10.

**Siguiente paso:** la 1b′ (L + 5a + humedad de ERA5-Land, preregistrada) cuando esté el silver de ERA5-Land;
mientras tanto, el preregistro de la fase 4 (Niño 1+2) sobre L + 5a; después, la 6′ (otra familia con clima,
lectura) y la fase 7 (síntesis, pruebas, auditoría con `revisor-modelado` y congelamiento). Si la 1b′ muestra que
el clima aporta, el siguiente paso es la precipitación de CHIRPS v3 (ver «Fase 1b′»).

**Pendientes del pipeline anotados (no tocar en este estudio):** semana 53 de 2009 en `epi_piura_semanal.csv`;
`propia_semanas_desde_ultimo_caso` en `gold.py` sin la historia anterior a 2017 (limitación conocida de la V1/V2).

## Fase 0 · Diagnóstico y techo (cerrada el 2026-11-03)

Notebook `01_diagnostico_techo.ipynb`, cifras en `metricas/fase0.json`, MLflow
`denguekay/mejora_modelo_fase0_diagnostico`. Resumen presentado a Rosa en el chat el 2026-11-03.

## Fase 1 · Más historia

### Preregistro

`code/preregistration.py → PHASE1`, commit `6a29a8e`, aprobado por Rosa antes de entrenar.

### Enmienda G1 (2026-11-03, antes de entrenar)

- **Qué falló:** G1 exigía que las 9 columnas de la V1 (`base_6` + B3) fueran iguales en la tabla de orígenes
  larga y en la de la V1. Ocho coinciden exactamente en los 30 160 orígenes comunes. `propia_semanas_desde_ultimo_caso`
  difiere en **134 orígenes** de **20 distritos**, con cierres entre el 2017-01-28 y el 2017-05-06.
- **Causa:** la V1 calcula esa variable con el panel desde 2017, sin las semanas anteriores. Un distrito que aún
  no tenía casos en 2017 recibe el tope (52, «sin caso conocido»); con la historia larga se ve su último caso de
  2016, entre 1 y 43 semanas antes (mediana 16).
- **Enmienda aprobada por Rosa:** esas filas se exceptúan de G1. En ellas, la tabla larga debe dar < 52 e igual
  al recálculo directo desde la serie de casos; se cumple en las 134.
- **Consecuencia para la comparación 1a:** L usa los valores largos y R conserva la tabla exacta de la V1. Esas
  134 filas de entrenamiento (todas de 2017) forman parte de la diferencia L − R, junto con las temporadas
  2005–2016.

### Resultados de la 1a (2026-11-03)

Notebook `02_fase1a_historia.ipynb`; cifras en `metricas/fase1a.json`; predicciones y α en
`models/experimentos/mejora_modelo/fase1a/` (no versionado); MLflow `denguekay/mejora_modelo_fase1a_historia`
(`8372af480d9646529005126b404573e2`). Dispositivo: cuda, `n_jobs` = 12.

- **Guardas:** G1 (con la enmienda) pasa: 0 filas distintas en las 9 columnas; las 134 exceptuadas coinciden con
  el recálculo. G2 pasa bit a bit (diferencia 0 en μ y en la probabilidad NB2). G3 pasa: 0 etiquetas distintas
  en 30 485. G4 es un test y pasa.
  - G2 se lee con `float_precision="round_trip"`: con el lector por defecto de pandas, las mismas predicciones
    escritas y releídas en CSV difieren en 1,1e-13, sin que cambie el modelo.
- **Corridas fallidas:** las dos primeras ejecuciones del notebook se cayeron al guardar (los `attrs` de pandas y
  un booleano de numpy en el JSON) y no mostraron ninguna cifra. Se corrigió el código (`e69da56`, `377f519`) y
  se volvió a correr igual.
- **Veredicto preregistrado (2022 y 2023): L gana en h=2, 3 y 4.** F1 mejora más que el umbral de empate en las
  dos temporadas y la antelación también (IC95 de la diferencia: h2 0,084 a 0,221; h3 0,168 a 0,337; h4 0,189 a
  0,358; 95 inicios limpios). No hay vetos contra L. **Se adopta el entrenamiento desde 2005.**

| Temporada | h | Semanas brote | F1 L / R / V1 tal cual | AUPRC L / R | Brier L / R | Razón MAE L / R |
|---|---|---|---|---|---|---|
| 2022 | 2 | 431 | 0,712 / 0,154 / 0,711 | 0,781 / 0,789 | 0,054 / 0,084 | 0,962 / 1,001 |
| 2022 | 3 | 431 | 0,704 / 0,000 / 0,658 | 0,771 / 0,781 | 0,056 / 0,102 | 0,959 / 1,021 |
| 2022 | 4 | 431 | 0,652 / 0,000 / 0,546 | 0,743 / 0,753 | 0,060 / 0,110 | 0,952 / 1,040 |
| 2023 | 2 | 1039 | 0,857 / 0,778 / 0,852 | 0,947 / 0,947 | 0,062 / 0,082 | 0,847 / 0,881 |
| 2023 | 3 | 1039 | 0,835 / 0,578 / 0,828 | 0,930 / 0,928 | 0,073 / 0,120 | 0,791 / 0,808 |
| 2023 | 4 | 1039 | 0,811 / 0,216 / 0,803 | 0,922 / 0,917 | 0,081 / 0,159 | 0,748 / 0,764 |

- **Ganancia de referencia (decisión de Rosa al confirmar la 1a, 2026-11-03):** la comparación preregistrada L
  frente a R está **inflada por el calibrador de R**, que se aplasta al calibrar con 2018–2021 (ver abajo). La
  ganancia que se toma como referencia es la de L frente a la **V1 tal cual**: F1 +0,046 en 2022 · h3 y +0,106 en
  2022 · h4; en 2023 es marginal (+0,005 a +0,008). Entrenar desde 2005 pasa a ser la base de las fases siguientes.
- **Lectura, no cambia la decisión: la victoria frente a R es sobre todo de calibración.**
  - R calibra con 2018–2021 (155 semanas brote en unas 13 500 filas) y su probabilidad calibrada se aplasta: F1 0
    en 2022 · h3 y h4. La misma R con el Platt de la V1 (solo 2021) da 0,658 y 0,546. Extender el calibrador
    hacia atrás sin más historia de entrenamiento empeora.
  - La AUPRC de L no mejora: en 2022 queda 0,008–0,010 por debajo de R (fuera del umbral de empate en 1 de 2
    temporadas por horizonte). El orden de las semanas no mejora; mejora la escala.
  - Frente a la V1 tal cual, la ganancia de F1 se concentra en 2022 · h3 (+0,046) y h4 (+0,106); en 2023 es
    +0,005 a +0,008.
  - El calibrador de L para 2022 usa 47 000 filas y 2 340–2 353 semanas brote; el de la V1, 3 380 filas y 90.
    Con L, el Brier calibrado queda por debajo del sin calibrar en 2022 y 2023 (en la V2 era al revés en 2022).
  - El conteo sí cambia por el entrenamiento (μ no depende de Platt): la razón MAE baja 0,02–0,09 en 2022 y 2023.
- **Inicios limpios:** el recall de las 2 primeras semanas de brotes nuevos sigue bajo: 0,12–0,19 en 2022–2023,
  0,02–0,13 en 2010, 2015 y 2016. Antelación (≥ 2 semanas, semilla 17) en 2022–2023 frente a la persistencia: h2
  0,168 / 0,116; h3 0,263 / 0,137; h4 0,284 / 0,211 (IC separados, no pareados). En 2010 y 2015 L no se
  distingue de la persistencia (0,03–0,07 las dos).
- **2010 (aparte; entrena con 2005–2009):** F1 0,722 / 0,631 / 0,476 en h2 / h3 / h4, 234 semanas brote y 30
  inicios limpios. El h=4 de 2010 y 2015 (F1 0,476 y 0,480) es la celda más débil de las temporadas que deciden.
- **HU0007-4 de L** (mediana de semillas; todas las celdas son evaluables):
  - Clasificación: cumple en 2023 · h2 y 2024 · h2 / h3 / h4. No cumple en 2010, 2015, 2016, 2017 ni 2022.
    Falla el recall.
  - Regresión: cumple en 2023 · h4 (0,748 / 0,839) y 2017 · h3 / h4; 2017 entra como lectura (se usó para elegir
    B3). En el resto la razón RMSE es > 0,85.
  - L no tiene A3, así que no es comparable con la V2 en regresión: la V2 cumple 2023 · h3 y h4. Eso es la 1b.

### 1b · Propuesta para el equipo (2026-11-03; no se descargó nada)

- **`openmeteo.py`:** `fetch_district` y `download_pending_batch` aceptan `start_date`, `end_date` y `models`.
  Por defecto no cambia nada: 2017-2025, sin parámetro `models` (el «Best match» del API) y caché
  `cache_meteo/`. Otro rango o un modelo fijo exige su propio `cache_dir` (si no, `ValueError`), porque la
  reanudación solo mira si existe el archivo del distrito. Con un modelo fijo, si el API devuelve columnas
  renombradas, la descarga se detiene. Tests en `tests/data/test_openmeteo.py`.
- **Cachés nuevos** (`denguekay.config.paths`): `cache_meteo_era5_2017_2025/` (comparación) y
  `cache_meteo_2000_2016/` (historia); salida semanal de la historia en
  `silver/meteo_semanal_distrital_2000_2016.csv`. Anotados en `docs/architecture.md`.
- **Notebook 02 del pipeline:** celda A (ERA5 fijo 2017-2025, se corre ya) y celda B (2000-2016, bloqueada
  hasta la decisión de Rosa sobre el modelo). **Notebook 03 del pipeline:** agrega la historia a semanas con la
  misma función que 2017-2025.
- **Comparación:** `notebooks/03_fase1b_consistencia_clima.ipynb` (código en `code/phase1b_climate.py`) compara
  por variable y por año la diferencia ERA5 − actual (media, MAE, máximo, correlación, semanas iguales). Probado
  solo leyendo, con el caché actual contra sí mismo: 30 485 semanas, diferencia 0 en las 9 variables.
- **Modelo fijado:** ERA5 (0,25°, desde 1940). Según la documentación de Open-Meteo, ERA5-Land no trae
  radiación solar y el «Best match» combina IFS HRES, ERA5 y ERA5-Land. La página no muestra el identificador
  exacto del parámetro `models`; el notebook usa `"era5"` y pide confirmarlo antes de descargar.

### Limitación conocida de la V1 y la V2

La V1 y la V2 tienen el mismo defecto de inicio de panel en `propia_semanas_desde_ultimo_caso`: en las primeras
semanas de 2017 la variable no ve la historia anterior y queda en el tope 52 para los distritos sin casos en
2017. Afecta a 134 orígenes de entrenamiento, todos entre el 2017-01-28 y el 2017-05-06; no afecta a ninguna
semana evaluada (2021 en adelante), porque desde mayo de 2017 cada distrito ya tiene su último caso dentro del
panel o lleva 52 semanas sin casos. **Las versiones congeladas no se modifican:** la V1 y la V2 se reproducen tal
como se congelaron, con ese defecto.

### Cambios propuestos para `gold.py` (sin implementar; los ejecuta el equipo)

- `propia_semanas_desde_ultimo_caso` debe leer también la historia anterior a 2017 (`SILVER_EPI_HISTORICAL`), no
  solo para la temporada anterior (`propia_log_casos_temporada_anterior`, que ya la lee). Así las primeras
  semanas de 2017 dejan de quedar en el tope por falta de historia.
- Ese cambio movería la columna de gold en esas 134 filas: rompería la paridad bit a bit de gold con
  `frozen_configs.origins` de la V1/V2. Por eso solo entra si la configuración que lo usa reemplaza a la V2
  (decisión de Rosa en la fase 7), con su propia ficha y su propia huella.

## Fase 2 · Calibración (2026-11-03)

Preregistro `PHASE2` (commit `3bbfa10`, aprobado por Rosa sin cambios antes de calibrar). Notebook
`04_fase2_calibracion.ipynb`; cifras en `metricas/fase2.json`; MLflow `denguekay/mejora_modelo_fase2_calibracion`
(`d320f5c3d1e54e529b36901f3e3a0541`). Se recalibran las predicciones sin calibrar de L (5 semillas); μ no cambia.

- **Guardas:** G5 pasa (Platt por horizonte con 1e-6 reproduce el protocolo, diferencia 0 en las 5 semillas). G6
  pasa (0 bloques no monótonos en Platt, Platt agrupado y beta). G7 es un test y pasa.
- **Guarda de calibración:** la referencia tiene 1 temporada de 5 en contra por horizonte (calibrado peor que sin
  calibrar en las 5 semillas); ninguna variante llega a 3.
- **Veredictos (5 temporadas): ninguna variante se adopta. Se queda Platt por horizonte con recorte 1e-6.**

| Candidata | h2 | h3 | h4 |
|---|---|---|---|
| Recorte 1e-15 (paso A) | empate | empate | empate |
| Platt agrupado | empate | empate | empate |
| Beta | empate | empate | empate |
| Isotónica | empate (veto AUPRC) | empate (veto AUPRC) | compensa (veto AUPRC) |

- **Recorte 1e-15:** no mejora en ninguna temporada; empeora F1 en 2010 y 2015 en h3 y h4 (h4: −0,091 en 2010 y
  −0,053 en 2015, con 234 y 557 semanas brote). Con 2 temporadas en contra no llega a «pierde». El recorte de 1e-6
  se queda.
- **Platt agrupado:** cambios de F1 de ±0,02 o menos salvo 2010 · h4 (+0,023). Antelación: h2 +0,047 (IC95 0,021 a
  0,078) y h4 −0,021 (IC95 −0,041 a −0,005), con solo 2 temporadas fuera de la banda; no decide.
- **Beta (lectura, no cambia la decisión):** es la que más se mueve.
  - h4: F1 +0,066 en 2010, +0,130 en 2015 y +0,015 en 2022, fuera del umbral de empate; neutra en 2016 y 2023 →
    3 de 5, no 4.
  - Brier y log-loss calibrados mejoran frente a la referencia en 4–5 de las 5 temporadas en cada horizonte (en
    2024, contraste, empeoran un poco).
  - Antelación h4 +0,036 (IC95 0,010 a 0,062) con 2 temporadas a favor; h2 −0,021 (IC95 −0,041 a −0,005).
  - Recall de brotes nuevos en 2022–2023 casi igual que la referencia (0,10–0,19).
- **Isotónica:** la AUPRC cae en las 4 temporadas donde se aplica (2010 queda en Platt por tener < 500
  positivos), de −0,004 a −0,024: es el efecto de los escalones, el que la guarda de AUPRC estricta debía
  detectar. Veto en los tres horizontes.
- La AUPRC de Platt, Platt agrupado y beta es idéntica a la de la referencia en todas las celdas, como se espera de
  un calibrador monótono.
- **Cierre (confirmado por Rosa, 2026-11-03):** L queda con Platt por horizonte y recorte 1e-6. Beta estuvo cerca en
  h4 (F1 a favor en 3 de 5 temporadas: 2010, 2015 y 2022), pero **no se adopta**: no alcanza la regla
  preregistrada (4 de 5 y ganar en 2 de 3 horizontes).
- **Consecuencia:** la base sigue siendo L tal como salió de la 1a; la ganancia frente a la V1 tal cual no cambia
  (2022 · h3 +0,046, h4 +0,106). El cuello de botella del recall en inicios limpios (0,12–0,19 en 2022–2023) no es
  de calibración: queda para la fase 3.

## Fase 3 · Inicios de brote (3a1, 3a2 y 3b; 2026-11-03)

Preregistro `PHASE3` (commit `6574669`, aprobado por Rosa con dos ajustes: recorte de 3a2 a [0,25, 1] y fiabilidad y
Brier por régimen como lectura). Notebook `05_fase3_inicios.ipynb`; cifras en `metricas/fase3.json`; predicciones
en `models/experimentos/mejora_modelo/fase3/` (no versionado); MLflow `denguekay/mejora_modelo_fase3_inicios`
(`f563d64ea4ae4d3da49a385b0ce3cce6`). Dispositivo: cuda, `n_jobs` = 12.

- **G8 pasa:** el ciclo nuevo sin pesos ni regímenes reproduce L bit a bit (diferencia 0 en μ y en la probabilidad
  sin calibrar, 183 105 filas, semilla 17); con pesos iguales a 1 la diferencia también es 0. G9 es un test y pasa.
- **Veredictos frente a L: ninguna se adopta; L sigue siendo la base.**

| Variante | h2 | h3 | h4 |
|---|---|---|---|
| 3a1 · peso 5 a inicios | compensa (vetos AUPRC, Brier, razón MAE) | empate | empate |
| 3a2 · peso por temporada | empate | empate | empate |
| 3b · dos regímenes | compensa (veto razón MAE) | compensa (vetos AUPRC, razón MAE) | empate |

- **3a1 es un intercambio, no un fracaso:** gana recall de inicios a cambio del orden de las semanas y del recall en
  brotes en curso. La regla preregistrada no lo adopta porque las guardas pesan ese costo.
  - Lo que gana: antelación h2 +0,078 (IC95 0,041 a 0,114, 4 temporadas a favor), h3 y h4 +0,047 (IC95 0,010 a
    0,083, 3 a favor). Recall de brote nuevo: 2023 0,30 / 0,29 / 0,26 frente a 0,17 / 0,19 / 0,17 de L; 2016 · h2
    0,21 frente a 0,13; 2022 · h2 0,22 frente a 0,12.
  - Lo que cuesta: la AUPRC baja en las 5 temporadas en los tres horizontes, el Brier empeora en 3–4 y la razón
    MAE en 3 (hasta +0,24 en 2016 · h4). En 2010 y 2015 · h4 el recall de brotes en curso baja a 0,09 y 0,24 (L:
    0,45 y 0,36) y el F1 a 0,135 y 0,349 (L: 0,476 y 0,480), con 234 y 557 semanas brote.
  - Queda como evidencia de que el peso de muestra mueve el balance entre inicios y brotes en curso; el factor 5
    se fijó a priori y no se ajustó.
- **3a2:** sin efecto en F1 ni AUPRC fuera del umbral de empate; la razón MAE mejora en 3–4 temporadas (y −0,11 a
  −0,17 en 2024, contraste), la antelación baja un poco (−0,026 a −0,036). Empate.
- **3b:** empeora los inicios. La antelación baja en los tres horizontes (h3 −0,181, IC95 −0,233 a −0,130) y el
  recall de brote nuevo cae a 0–0,06. El modelo de inicios no supera p ≥ 0,50 con un solo Platt sobre la
  probabilidad combinada. En h3 y h4 la lectura sin 2010 da «pierde».
  - Lectura por régimen (Rosa): el Brier del régimen de inicios (n = 43 207, 2 316 positivos en las 5 temporadas)
    queda un poco mejor que L en 2016 y 2022, peor en 2015 y en 2023 · h3 y h4; el del régimen en curso (n = 7 688,
    5 652 positivos) mejora en 2010 y 2015. El régimen en curso usó el modelo único en 1 bloque por semilla (menos
    de 100 orígenes de entrenamiento).
- **Lectura:** el peso a los inicios es la única variante que mueve el recall de brotes nuevos; lo hace a cambio del
  orden, del conteo y de los brotes en curso. No se adopta.

### Enmienda de 3c (2026-11-03, después de ver 3a1, 3a2 y 3b; antes de entrenar 3c)

- **Qué cambia:** 3c deja de ser «3b con B1 + B2 en el modelo de inicios» y pasa a ser una sola variante,
  **3c′ = L + B1 + B2 en el modelo único** (C3 + B1 + B2, mismas α, hiperparámetros y calibración), comparada
  contra L con la misma regla y la misma adopción (`adopt_phase3`).
- **Por qué:** 3b dejó el recall de brote nuevo en 0–0,06 y bajó la antelación en los tres horizontes. Construir 3c
  sobre 3b la haría partir de una base que empeora lo que intenta arreglar. Decisión de Rosa.
- **Cuándo:** la enmienda se hizo **después de ver los resultados de 3a y 3b**, así que no es ciega a ellos; sí es
  anterior a cualquier corrida de 3c′. Se declara aquí por eso.
- **Cierre:** si 3c′ empata o pierde, la fase 3 se cierra con L como base.
- B1 y B2 sobre la serie larga y G10: `code/phase3_onsets.py` (`long_spatial_table`, `spatial_prepare_block`) y
  `tests/test_phase3_onsets.py`; B2 usa el ranking del núcleo de cada corte de bloque.

### Resultado de 3c′ y cierre de la fase 3 (2026-11-03)

Notebook `06_fase3c_contexto_espacial.ipynb`; cifras en `metricas/fase3c.json`; MLflow
`denguekay/mejora_modelo_fase3_inicios` (`588ac341bfed43dfaa4ba2190898426b`). Dispositivo: cuda, `n_jobs` = 12.

- **Veredicto: empate en h2, h3 y h4; no se adopta.** Lectura sin 2010: empate en los tres.
- F1: en contra en 2 de 5 temporadas por horizonte (2010 y 2015: h3 −0,046 y −0,081; h4 −0,051 y −0,094, con 234 y
  557 semanas brote); en 2016, 2022 y 2023 dentro del umbral de empate.
- Antelación: h2 y h4 +0,031 (IC95 0,000 a 0,062), h3 +0,016 (IC95 −0,016 a 0,047), con 1–2 temporadas a favor.
- Recall de brote nuevo: 2023 0,22 / 0,24 / 0,19 frente a 0,17 / 0,19 / 0,17 de L; 2022 · h2 0,16 frente a 0,12;
  en 2010 y 2016 igual o menor salvo 2016 · h4 (0,09 frente a 0,06). El recall de brotes en curso baja en 2010 y 2015 (h4: 0,37 y 0,27 frente a 0,45 y
  0,36).
- El Brier mejora en 3 de 5 temporadas en cada horizonte (no decide; es guarda).
- **Cierre de la fase 3:** ninguna variante (3a1, 3a2, 3b, 3c′) se adopta; **L sigue siendo la base**. Lo único que
  movió el recall de inicios fue el peso de muestra de 3a1, como intercambio con el orden y los brotes en curso.

## Fase 5 · Conteo (2026-11-03)

Preregistro `PHASE5` (commit `6d2164c`, aprobado por Rosa con una lectura agregada). Notebook `07_fase5_conteo.ipynb`;
cifras en `metricas/fase5.json`; predicciones de 5b, w de 5a y `max_delta_step` elegidos en
`models/experimentos/mejora_modelo/fase5/` (no versionado); MLflow `denguekay/mejora_modelo_fase5_conteo`
(`3259773a81f14abeb94cbcbc2366647f`). Dispositivo: cuda, `n_jobs` = 12. Decide la razón MAE; vetan la razón RMSE, F1,
AUPRC, Brier y la antelación.

- **Guardas:** G11 pasa (0 bloques con w = 1 distintos de L). G12 pasa (5b con la grilla {0,7} reproduce L bit a bit,
  183 105 filas, semilla 17). G13 pasa (3a2 con las 5 semillas y las mismas filas que L).
- **Veredictos frente a L:**

| Variante | h2 | h3 | h4 | Se adopta |
|---|---|---|---|---|
| 5a · mezcla con la persistencia | gana (5 de 5) | gana (4 de 5) | gana (4 de 5) | **sí** |
| 5b · `max_delta_step` por bloque | empate | empate | empate | no |
| 5c · 3a2 (no ciega) | empate | compensa (veto Brier) | empate (veto Brier) | no |

- **5a se adopta: la base pasa a ser L + mezcla con la persistencia (solo el conteo).** Una sola variante adoptada:
  no hay cruce.
  - Razón MAE: baja en las 5 temporadas en h2 (−0,016 a −0,070) y en 4 de 5 en h3 y h4; en 2010 · h3/h4 queda igual
    (w = 1,00, mediana entre semillas). La razón RMSE baja en todas las celdas salvo 2010 · h4 (−0,001 a −0,142);
    está marcada como mejora en ≥ 3 temporadas («veto contra la referencia» en la tabla). 2024 (contraste): razón MAE
    −0,11 a −0,14 y RMSE −0,20 a −0,29.
  - F1, AUPRC, Brier y antelación son idénticos a L por construcción (la probabilidad no cambia).
  - w mediano por bloque: 0,59–0,88 en h2, 0,65–1,00 en h3 y 0,69–1,00 en h4; para 2022–2024, 0,73–0,85. El modelo
    pesa más que la persistencia en todos los bloques, y más en h4.
  - Por fase de la curva (2022–2023): mejora en pico y subida (2022 · h4 pico 1,347 → 1,236; 2023 · h2 subida 1,063
    → 0,976) y empeora en bajada (2022 · h2 0,666 → 0,727), donde la persistencia arrastra el pico ya pasado. MAE y
    RMSE se mueven en el mismo sentido.
  - HU0007-4 de regresión: 5a cumple en 2023 · h4 (igual que L). En 2015 · h3 la razón MAE pasa a ≤ 0,85 (en
    2015 · h4 ya lo era), pero la RMSE no. En 2017 (solo lectura) 5a queda peor: L cumplía la regresión en h3 y h4
    y 5a no, y en h2 la razón MAE de 5a pasa por encima de 0,85. El conteo sigue sin cumplir la HU0007-4 en la
    mayoría de las celdas.
- **5b:** `max_delta_step` elegido: 0,7 en 65 de 90 bloques·semilla, 1,0 en 20 y 2,0 en 5; nunca 3, 5 ni 10. La
  razón MAE baja solo donde se eligió otro valor (2015, 2016, 2024) y no alcanza 4 de 5. Empate. Con la
  validación interna, el rango ampliado casi no se usa en L con 160 árboles.
- **5c (3a2):** razón MAE a favor en 3–4 de 5 temporadas, como en la fase 3, pero el Brier veta en h3 y h4 y la
  antelación baja (−0,026 a −0,036). No se adopta.
- **Lectura de Rosa: probabilidad desde la μ mezclada.** NB2 con la μ y la α de L reproduce la probabilidad guardada
  (diferencia 0). Con la μ mezclada y Platt: «compensa (empate)» en los tres horizontes. El F1 casi no cambia (−0,009
  a +0,031), pero la AUPRC queda en contra en 2–3 temporadas y el Brier en 2–3. **Casos y probabilidad no deberían
  salir de la misma μ mezclada:** la probabilidad (y el intervalo de la alerta) siguen con la μ del modelo y el conteo
  publicado con la μ mezclada. Cómo se calcula el intervalo del conteo con la μ mezclada queda para la fase 7.
- **Cierre (confirmado por Rosa, 2026-11-03):** se adopta 5a. La base pasa a ser L + mezcla del conteo con la
  persistencia. Decisión de diseño: los casos salen de la μ mezclada y la probabilidad de la μ del modelo (ver
  «Estado actual»). El intervalo del conteo queda para la fase 7.

## Fase 6 · Líneas base de otra familia (lectura, 2026-11-03)

Preregistro `PHASE6` (commit `71f446a`, aprobado por Rosa tal cual antes de correr). Notebook
`08_fase6_otras_familias.ipynb`; cifras en `metricas/fase6.json`; predicciones en
`models/experimentos/mejora_modelo/fase6/` (no versionado); MLflow `denguekay/mejora_modelo_fase6_otras_familias`
(`637310f706b84c19b6856cbd37552e6a`). LightGBM 4.7.0 y statsmodels 0.15.0. Base: L + 5a, con la misma matriz C3
sin clima. Es una lectura: nada se adopta.

- **Guardas:** pasan todas. G14: filas de entrenamiento y corte iguales a los de L en los 18 bloques de las dos
  familias. G15: los tests de no fuga por perturbación pasan. G16: LightGBM con la semilla 17 da dos veces lo mismo
  (diferencia 0), y L + 5a reproduce las métricas de `fase5.json` (diferencia máxima 4,9e-11 en 18 filas).
- **6a · GLM NB2: no es interpretable.** El ajuste por máxima verosimilitud no convergió en 200 iteraciones en al
  menos un horizonte de cada uno de los 18 bloques; en h3 converge solo en 2 de 18. Según el preregistro se
  reporta y no se ajusta nada. Los síntomas están en los resultados: en h3 la mezcla 5a le da w = 0 en la mediana
  (el conteo publicado queda igual a la persistencia, razón MAE = 1,000 en todas las temporadas) y su F1 en
  2010 · h3 cae a 0,009. Por eso no se leen sus veredictos (F1: empate en h2, pierde en h3 y «gana» en h4; razón
  MAE: empate en los tres) como evidencia sobre la familia. Se enmendó con 6a′ (abajo).
- **6b · LightGBM: empate con L + 5a en los tres horizontes**, con las dos reglas (F1 de la fase 3 y razón MAE de
  la fase 5) y sin vetos. Las diferencias por temporada son de centésimas (F1 de las 5 temporadas que deciden
  entre −0,06 y +0,01; razón MAE entre −0,02 y +0,02). La antelación tampoco cambia (IC95 que incluye 0 en h2 y
  h4; en h3, −0,010 con IC95 [−0,026; 0,000]). Con la μ sin mezclar, LightGBM pierde por razón MAE en h2 y h3
  frente a L + 5a (veta la razón RMSE): la mezcla 5a también le sirve a esta familia.
- **6′ (con clima):** el código acepta otra lista de columnas (`run_family(..., columns=...)`); queda para cuando
  la 1b entregue el clima 2000–2016, con su propio preregistro.

### Enmienda 6a′ (2026-11-03, después de ver que 6a no convergió; antes de correr 6a′)

- **Por qué y cuándo:** Rosa la pidió **después de ver** la no convergencia del GLM NB2 de 6a. Es la única
  enmienda de la fase 6 (`PHASE6_AMENDMENT`, commit `e37e55c`, antes de correr).
- **Qué es:** GLM Poisson por horizonte (IRLS, maxiter 200) con offset log(hist_lag_a + 0,5), las mismas 9
  columnas de C3 con la misma transformación y estandarizadas por bloque; la α de la NB2 con el estimador de L sobre
  el ajuste dentro de la muestra, igual que L con XGBoost. Un ajuste que no converge se reajusta con L2 = 1e-4 (sin
  penalizar el intercepto) y se reporta. Regla de cierre: si no converge sin penalización en más de 27 de los 54
  ajustes (bloque × horizonte), el GLM queda como no interpretable.

### Resultado de 6a′ (2026-11-03)

Notebook `09_fase6a_prima_glm_poisson.ipynb`; cifras en `metricas/fase6.json` (sección `enmienda_6a_prima`);
MLflow `b4aaa1cfb6c94074a3dcbb552409afe2`.

- **Guardas:** G14 pasa (filas y corte de L en los 18 bloques); los tests de no fuga pasan con 6a′; L + 5a
  reproduce `fase5.json`.
- **Convergencia:** 54 de 54 ajustes convergen sin penalización; no se usó la L2. Es interpretable.
- **Veredictos (lectura, no deciden), frente a L + 5a.** El GLM es determinista, así que el umbral de empate es
  solo el rango entre semillas de L.

  | Regla | h2 | h3 | h4 |
  |---|---|---|---|
  | F1 (fase 3) | empate (Brier en contra) | empate (Brier en contra) | **gana** |
  | razón MAE (fase 5) | empate | empate | empate |
  | sin 2010, F1 (3 de 4) | empate | gana | gana |

- **F1 en h4** (5 temporadas que deciden, positivos entre paréntesis): 2010 0,522 frente a 0,476 (234); 2015
  0,648 frente a 0,480 (557); 2016 0,577 frente a 0,590 (395); 2022 0,657 frente a 0,652 (431); 2023 0,822
  frente a 0,811 (1 039). En 2024 (contraste) pierde: 0,746 frente a 0,761 (857). Buena parte de la ganancia
  está en 2015; 2022 y 2023 son diferencias de centésimas.
- **Antelación:** mejor en los tres horizontes, con IC95 que excluye 0: h2 +0,057 [0,021; 0,098], h3 +0,078
  [0,041; 0,119], h4 +0,119 [0,073; 0,166] (193 episodios). La mayor diferencia está en 2016 (+0,15 a +0,38).
- **Peor en:** Brier en 2016 en los tres horizontes (h4 0,083 frente a 0,070) y razón MAE en 2016 y 2022 (h4
  2016: 1,157 frente a 1,062). Por eso la razón MAE queda en empate: mejora en 2010, 2015 y 2023 y empeora en 2016
  y 2022.
- **Con la μ sin mezclar** también empata por razón MAE (veta la razón RMSE). La mezcla 5a le da w con mediana
  0,64 (h2), 0,76 (h3) y 0,81 (h4).

### Lectura de la fase 6 y cierre (2026-11-03)

- **Observación:** con la misma información (C3, sin clima), LightGBM rinde igual que L, y un GLM Poisson lineal
  con la α de la NB2 empata o mejora en la lectura: gana por F1 en h4 y adelanta las alertas en los tres
  horizontes, a cambio de peor Brier en 2016 y sin mejora en el conteo.
- **Hipótesis (no conclusión):** el límite parece estar en la información de la matriz más que en la familia del
  modelo; la flexibilidad de los árboles no aporta sobre un modelo lineal con las mismas 9 columnas. Con pocos
  brotes por temporada y la ganancia concentrada en 2015 y 2016, no se generaliza ni se usa lenguaje causal.
- **Nada se adopta** (la fase 6 no decide, por preregistro). Que el GLM gane en h4 queda anotado como hipótesis para
  la síntesis de la fase 7 o un estudio posterior; usarlo como candidata requeriría un preregistro nuevo aprobado
  por Rosa.
- **La fase 6 queda cerrada**, salvo la 6′ con clima, preparada para cuando llegue la 1b.

## Fase 1b′ · Fuente del clima y preregistro (2026-11-03 y 2026-11-04)

- **ERA5 fijo (0,25°) frente a lo descargado («Best match»), 2017–2025:** notebook
  `03_fase1b_consistencia_clima.ipynb` (commit `fefa3b2`, cifras en `metricas/fase1b_consistencia.json`). Las
  diferencias son sistemáticas (viento −4,19 km/h, temperatura media +0,52 °C, precipitación +2,49 mm por semana en
  promedio; correlación semanal de la precipitación 0,824 y de la humedad 0,837), con 2025 como el año más
  distinto. 48 de los 65 distritos comparten celda real de ERA5 (34 celdas) y, dentro de cada celda, la
  precipitación, el viento y la radiación son idénticos en todas las semanas (mediana por grupo 1,000).
- **Decisión de Rosa:** no usar ERA5 a 0,25° (precipitación idéntica entre vecinos en 48 distritos) ni «Best match»
  para 2000–2016 (antes de 2017 no tiene el IFS: el empalme existiría igual, sin medirlo).
- **ERA5-Land (0,1°):** la celda A2 bajó una muestra de 16 distritos (5 grupos que comparten celda en ERA5 y 4
  distritos de costa y sierra). Las 15 celdas de ERA5-Land separan esos grupos (solo La Arena y La Unión comparten
  una), pero la precipitación, la lluvia, el viento, la radiación y la ET0 llegaron vacías en el 100 % de los días.
  La documentación de Open-Meteo confirma que ERA5-Land no trae precipitación, lluvia, radiación ni viento
  (https://open-meteo.com/en/docs/historical-weather-api), y Rosa lo comprobó en el navegador (diaria y horaria en
  `null`). Sí trae temperatura y humedad.
- **Plan aprobado:** humedad de ERA5-Land 2000–2025 para los 65 distritos (rama `feat/era5-land-humidity-history`:
  `daily_vars` configurable en `openmeteo.py`, agregación semanal que deja vacía la semana sin datos en vez de 0,
  silver aparte). No cambia el silver vigente, el gold ni la V2.
- **Preregistro `PHASE1B_PRIME`** (aprobado por Rosa el 2026-11-04 tal cual, commiteado antes de que termine la
  descarga): L + 5a + H, con H = `hum_rel_media_media5_h2` (definición de gold.py) sobre la humedad de ERA5-Land,
  frente a L + 5a con la regla de 5 temporadas de las fases 2 y 3; adopción con «gana» en >= 2 de 3 horizontes y
  sin «pierde» ni «compensa». Guardas G17–G20 (definición de H igual a la del gold, no fuga, sin nulos desde 2005,
  reproducción de L + 5a).

### Precipitación: fuentes verificadas (2026-11-04; siguiente paso si la 1b′ muestra que el clima aporta)

- **CHIRPS v3** (Climate Hazards Center, UCSB; https://www.chc.ucsb.edu/data/chirps3): 0,05°, diaria, desde 1981,
  licencia CC BY 4.0. Archivos GeoTIFF y NetCDF sin registro en https://data.chc.ucsb.edu/products/CHIRPS/v3.0/.
  Al 2026-11-04, el producto final llega al 2026-09-30 y el preliminar al 2026-10-31 (publicado el 2026-11-02).
  Preliminar: 2 días después de cada péntada; final: una vez al mes, normalmente en la tercera semana del mes
  siguiente. **Sirve para entrenar (2000–2025) y, con el preliminar, para la actualización semanal de la app.**
  La v2 se produce hasta diciembre de 2026. La documentación aclara que la fecha de cada valor diario es una
  etiqueta del proceso de desagregación: habría que medir su efecto en las sumas semanales.
- **PISCOp v2.1** (SENAMHI; https://piscoprec.github.io/webPISCO/en/about): 0,1°, diaria y mensual, desde 1981.
  SENAMHI suspendió su generación en casi tiempo real y no hay valores después del 2018-06-30. El catálogo de IRIDL
  exige iniciar sesión y no se pudo verificar la licencia de los datos. Una publicación no oficial menciona una
  v3.0 (1981–2025) que no se pudo confirmar en fuentes de SENAMHI. **No sirve para la app con lo verificado.**
