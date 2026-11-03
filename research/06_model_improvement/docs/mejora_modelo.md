# Mejora del modelo sobre la V2

Informe del estudio 06. Plan y decisiones de Rosa en [plan.md](plan.md); preregistros en
`code/preregistration.py`.

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
