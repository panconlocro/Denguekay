# Mejora del modelo sobre la V2

Informe del estudio 06. Plan y decisiones de Rosa en [plan.md](plan.md); preregistros en
`code/preregistration.py`.

## Estado actual (2026-11-08)

Rama `exp/model-improvement`. Para retomar: leer `CLAUDE.md`, [plan.md](plan.md) y este informe, y seguir desde
aquí. El estudio estuvo en pausa desde el 2026-11-04; Rosa retomó la lluvia (paso b de clima) el 2026-11-06.

**Fases cerradas (todas confirmadas por Rosa):**

| Fase | Qué se probó | Qué se adoptó |
|---|---|---|
| 0 · Diagnóstico | errores por estado, calibración, persistencia, historia 2000–2016 (sin entrenar) | nada (diagnóstico) |
| 1a · Más historia | V1 entrenada desde 2005 (L) frente a desde 2017 (R) | **L** (entrenar desde 2005); ganancia de referencia frente a la V1 tal cual: 2022 · h3 +0,046 y h4 +0,106 de F1 |
| 2 · Calibración | recorte 1e-15, Platt agrupado, beta, isotónica | nada: Platt por horizonte con recorte 1e-6 (beta, cerca en h4, no alcanza la regla) |
| 3 · Inicios | 3a1 peso a inicios, 3a2 peso por temporada, 3b dos regímenes, 3c′ L + B1 + B2 (enmienda) | nada: L sigue como base (3a1 es un intercambio: más recall de inicios a cambio de orden y brotes en curso) |
| 5 · Conteo | 5a mezcla con la persistencia, 5b `max_delta_step` por bloque, 5c peso por temporada | **5a**: conteo = w·μ + (1 − w)·persistencia, w por horizonte y bloque con las OOS anteriores |
| 4 · Niño 1+2 | 4a anomalía del último mes disponible, 4b media de 3 meses, sobre L + 5a | nada: empate en los tres horizontes (primera medición) |
| 1b′ · Humedad ERA5-Land | L + 5a + H (`hum_rel_media_media5_h2` sobre ERA5-Land 2000–2025) | nada: empate en los tres horizontes; la base sigue siendo L + 5a |
| 6 · Otra familia (lectura) | 6a GLM NB2 (no convergió), enmienda 6a′ GLM Poisson + α NB2, 6b LightGBM; C3 sin clima | nada (lectura): LightGBM empata con L + 5a; 6a′ empata o mejora (gana F1 en h4, mejor antelación, peor Brier en 2016); 6′ con clima, pendiente |
| b · Lluvia CHIRPS v3 | b1 L + 5a + lluvia CHIRPS (`precip_total_mm_media5_h2`, media del polígono); b2 L + 5a + humedad ERA5-Land + lluvia CHIRPS; b3 (agregada después) clima completo: humedad, lluvia, temperatura y Niño 1+2 | nada: b1 y b2 empatan en los tres horizontes; b3 empata en la alerta y en el conteo; la base sigue siendo L + 5a |
| 2026 · Temporada 2026 (regla del Brier sobre 6 temporadas) | L + 5a, b3, d1 y d2 = d1 + Niño 1+2, con 2026 entre las temporadas que deciden | **b3**: gana por el Brier en h2 y h3 (5 de 6 temporadas a favor, 0 en contra), empata en h4, sin «pierde» ni «compensa» en la alerta ni en el conteo; d1 y d2 empatan en todo. La regla se fijó después de ver los pasos b y d |
| d · Ventanas de clima | d1 L + 5a + lluvia CHIRPS, temperatura y humedad ERA5-Land por ventanas (o, o−1..o−4, o−5..o−8, o−9..o−12) + días >= 20 mm; frente a L + 5a y frente a b3 | nada: empate en los tres criterios (alerta, conteo y Brier) y en los tres horizontes, frente a L + 5a y frente a b3 |
| Matriz de clima (regla `SEASON_2026` + filtro LOSO >= 16 de 24) | 12 variantes sobre L + 5a: medias b1–b4, ventanas d1–d5, anomalías e1 y e2, n1 = b3 con el Niño monótono | Por la regla, **b3 sigue** (única adoptada; 19 de 24 celdas LOSO). d3 (ventanas de temperatura) gana el Brier solo en h2 y no gana la regla; el resto empata en todo. e1 pierde frente a b3 en Brier h4, F1 h3 y conteo h3. **Rosa eligió d3 como base con contexto (b3 retadora)** |

**Base de la V3: L + 5a + d3** (las 4 ventanas de temperatura de ERA5-Land), **con b3 como retadora**. Decisión de
Rosa del 2026-11-08, **con contexto y no por la regla `SEASON_2026`** (por la regla solo se adopta b3): tomada después
de ver la matriz y usando 2026 para elegir, por el objetivo de anticipar brotes en años de Niño. Justificación y tabla
de diferencias de Brier por temporada y horizonte en [plan.md](plan.md), «Decisiones de Rosa (2026-11-08, después de
la matriz de clima)». Resumen (diferencia media de Brier frente a L + 5a, negativo = mejor):

| Promedio de celdas | Celdas | d3 vs L + 5a | b3 vs L + 5a | d3 vs b3 |
|---|---|---|---|---|
| Decisivas (2010, 2015, 2016, 2022, 2023, 2026) | 18 | −1,38 % | −1,96 % | +0,58 % |
| Años de Niño (2017, 2026, `posterior_2026`) | 9 | −5,97 % | −2,00 % | −4,05 % |
| Todas | 27 | −2,34 % | −1,90 % | −0,44 % |

d3 es peor que L + 5a en 2016 (+0,4 / +0,9 / +2,3 % en h2 / h3 / h4); b3 es peor que L + 5a en 2017. **Se
congelarán las dos y se evaluarán de forma prospectiva en la temporada 2026-2027.** Antes de la fase 7 se le
consulta a Rosa. Antes: L + 5a + b3 (regla `SEASON_2026`, 2026-11-08) y L + 5a.

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

**Datos del clima ya disponibles (los corrió el equipo):**

- Humedad y temperatura de ERA5-Land 2000–2025 para los 65 distritos: `data/silver/meteo_humedad_era5_land_2000_2025.csv`
  (88 140 filas; bronze en `cache_meteo_era5_land_2000_2016/` y `cache_meteo_era5_land_2017_2025/`). Se usó en la 1b′.
- Niño 1+2 de NOAA CPC: `data/silver/enso_nino12_mensual.csv` (538 meses, 1982-01 a 2026-10). Se usó en la fase 4.
- Rosa descartó ERA5 a 0,25° (precipitación idéntica entre vecinos en 48 distritos) y «Best match» para 2000–2016;
  ERA5-Land no trae precipitación en Open-Meteo (ver «Fase 1b′»).

**Decisión de Rosa (2026-11-04): en la V3 la lluvia es solo CHIRPS v3** (entrenamiento y actualización semanal;
reemplazo, no agregado). La lluvia «Best match» de Open-Meteo queda solo para la V2: antes de 2017 Open-Meteo no
tiene lluvia útil y se entrena desde 2005. Ver [plan.md](plan.md), «Decisiones de Rosa (2026-11-04)».

**Pasos de clima (un preregistro commiteado por paso, sin adelantar ni mezclar):**

a) ~~1b′: L + 5a + humedad de ERA5-Land~~: corrida el 2026-11-04, empate en los tres horizontes; la base sigue
   siendo L + 5a.
b) **Lluvia de CHIRPS v3 sobre L + 5a: retomada el 2026-11-06** (ver [plan.md](plan.md), «Decisiones de Rosa
   (2026-11-06, lluvia de CHIRPS v3)»). Histórico final desde Google Earth Engine, semanas recientes con el
   preliminar del CHC, y lluvia por distrito como media del polígono ponderada por área. Variantes b1 (L + 5a +
   lluvia) y b2 (L + 5a + humedad + lluvia), cada una frente a L + 5a. Pasos internos b-I a b-VII, en la rama
   `feat/chirps-precipitation`. **Corrido el 2026-11-06: b1 y b2 empatan en los tres horizontes; la base sigue
   siendo L + 5a** (ver «Paso b de clima · Lluvia de CHIRPS v3: resultados»). Cerrados b-I a b-IV y b-VII. b-V
   parcial (silver solo con la versión final); el preliminar (resto de b-V) y b-VI quedan en pausa.
   - b-I · Polígonos: COD-AB de Perú (IGN, OCHA en HDX, CC BY-IGO 3.0), 65 de 65 distritos, pcode = «PE» + ubigeo
     en todos, nombres coincidentes, los 65 centroides de la V2 dentro de su polígono, diferencia de área máxima
     0,40 % (Arenal). Referencia en `data/reference/distritos_piura_limites.geojson`.
   - b-II y b-III · `earthengine-api>=1.7,<2` en el `.venv` del worktree; registro no comercial y autenticación
     hechos por Rosa (proyecto `denguekay`).
   - b-IV · Guarda de método en memoria sobre los 24 días de `final/` (2000-01-01 a 2000-01-24), con tolerancias
     fijadas antes de correr (commit `d4332e7`): grilla idéntica (píxel 0,05000000074505806°, desfase entero);
     (a) píxel: diferencia máxima 0,0 en 48 264 píxeles, misma máscara; (b) media por polígono de Earth Engine
     frente a la local: 1560 pares, 0 nulos, 0 fuera de tolerancia, diferencia máxima 0,063 mm (Sicchez,
     2000-01-14), media 0,0007 mm. Descarga de `UCSB-CHC/CHIRPS/V3/DAILY_SAT` en
     `data/bronze/chirps/v3_sat/ee_final/`: 321 de 321 meses (2000-01 a 2026-09), 635 050 filas distrito-día,
     0 nulos, 0 a 140,9 mm/d, 6657 s. Cordura: Piura 470 mm en marzo de 2017 y 155 mm en marzo de 2023; Frías
     1030 y 511 mm. Rosa lo cotejó con el CHIRPS v3 mensual en el punto del distrito (Piura 446 y 151 mm; Frías
     1122 mm en marzo de 2017).
   - La descarga anterior desde los COG del CHC (24 días de 2000 en `data/bronze/chirps/v3_sat/final/`) se detuvo
     por el límite de tasa; esos días se usaron en la guarda de b-IV.
   - b-V · Preliminar del CHC (2026-11-06): el listado llega al 2026-10-31; se bajó solo el 2026-10-01 (grilla igual
     a la del final, desfase entero) y el CHC respondió 429 en la tercera petición, con 60 s entre peticiones.
     Por decisión de Rosa, b-V (preliminar) y b-VI se retoman otro día con pausas más largas, empezando por el 27
     al 30 de septiembre de 2026. Silver `data/silver/precip_chirps_v3_semanal_desde_2000.csv` solo con la
     versión final: 90 675 filas (65 distritos × 1395 semanas MMWR de 7 días, 2000-01-02 a 2026-09-20), sin
     vacíos; `fecha_disponible` de la última semana: 2026-10-05. El día preliminar bajado no entra al silver.
   - b-VII · Preregistro `STEP_B` en `code/preregistration.py` (commit `b82bf80`, aprobado por Rosa tal cual el
     2026-11-06: b1 y b2 frente a L + 5a, regla de la 1b′, cruce b2 frente a b1 con empate a favor de b1, guardas
     G25 a G29); variable y guardas en `code/phase_b_rain.py`.
   - b3 · **Corrida el 2026-11-06: empate en la alerta y en el conteo en h2, h3 y h4; no se adopta.** Agregada
     después de ver b1 y b2 (preregistro `STEP_B3`, aprobado por Rosa con dos cambios antes de correr: «compensa»
     también bloquea en la otra regla y ERA5-Land se publica con 7 días de retraso): L + 5a + humedad ERA5-Land + lluvia CHIRPS + `temp_media_media5_h2` (ERA5-Land) +
     `nino12_anom_media3`. Se adopta si gana la alerta (regla del paso b) o el conteo (regla de la fase 5), sin
     «pierde» ni «compensa» en la otra; guardas G25 a G34, G17, G19, G21 y G22. Código en `code/phase_b3_full_climate.py`.
   - Pendiente (sin fecha): preliminar del 2026-09-27 al 2026-10-31 con pausas más largas (propuesta: 10 min
     entre peticiones) y la medición preliminar frente a final de b-VI. No cambian el veredicto de b.
c) ~~Repetir el Niño 1+2 solo si la base cambia en (b)~~: la base no cambió; el paso c no se corre. La fase 4 del
   2026-11-04 queda como la medición del Niño 1+2.
d) **Ventanas de clima: corrido el 2026-11-06, empate en los criterios (a), (b) y (c) en h2, h3 y h4 frente a L + 5a
   y frente a b3; d1 no se adopta y la base sigue siendo L + 5a** (ver «Paso d de clima · Ventanas: resultados»).
   Preregistrado y aprobado por Rosa con tres respuestas y un agregado. Agregado
   después de ver b1, b2 y b3 (preregistro `STEP_D` en `code/preregistration.py`). d1 = L + 5a + 14 columnas en
   memoria: lluvia CHIRPS, temperatura y humedad de ERA5-Land en la semana del origen y medias de o−1..o−4,
   o−5..o−8 y o−9..o−12; días con >= 20 mm (índice R20mm del ETCCDI) en o−3..o y o−7..o−4 desde el bronze diario
   de Earth Engine. Sin Niño. Dos comparaciones (d1 frente a L + 5a y frente a b3) con la regla de b3 más el criterio (c) de Rosa: gana por el
   Brier (decide_step_d_brier) sin «pierde» ni «compensa» en la alerta ni en el conteo. Métricas
   reportadas que no deciden: Brier y AUPRC por celda, Brier skill score frente a una climatología fuera de muestra
   y AUPRC restringido a persistencia < umbral_brote_casos. Guardas G35 a G39 (más G17, G25, G29 y G30). Código en
   `code/phase_d_weather_windows.py`. Respuestas de Rosa: >= 20 mm; la climatología propuesta; la base pasa a d1
   solo si gana frente a L + 5a (si además pierde frente a b3, se le consulta antes de la fase 7).

e) **Temporada 2026 (decisiones de Rosa del 2026-11-08, ver [plan.md](plan.md)).** Regla de decisión preregistrada
   (`SEASON_2026`, commit `e02ebe1`); `EVALUATION_2026` deja de ser independiente para la V3. **Punto 1 (datos)
   hecho el 2026-11-08** con una excepción de escritura acotada, ya cerrada (cifras en `metricas/datos_2026.json`):
   - Sala: 2025 sin cambios frente al silver (3445 filas, 0 distintas, 1117 casos); 2026 agregado al silver
     `epi_sala_semanal.csv` por upsert (2795 filas: 65 distritos × semanas 1 a 43, 15 716 casos; las filas previas
     quedan idénticas). Semanas provisionales: la 42 y la 43 de 2026.
   - ERA5-Land 2026 (65 distritos, 2026-01-01 a 2026-10-31, sin nulos) en `cache_meteo_era5_land_2026/` y silver nuevo
     `meteo_humedad_era5_land_2000_2026.csv` (91 000 filas hasta la semana del 2026-10-25); reproduce exactamente el
     de 2000-2025 en sus 88 140 filas.
   - CHIRPS por FTP (código en `feat/chirps-precipitation`, commit `5b6f6cd`): preliminar del 2026-09-27 al 2026-10-31
     (35 días, el 2026-10-01 sin cambios); final y preliminar de enero a abril de 2025 y 2026 (471 archivos, sin
     errores; faltan en el servidor 9 días del preliminar de 2025). Silver nuevo
     `precip_chirps_v3_semanal_desde_2000_20261108.csv` (91 000 filas: las 90 675 del vigente idénticas + 5 semanas
     `prelim` del 2026-09-27 al 2026-10-25). Con el OK de Rosa (2026-11-08) reemplazó al vigente
     `precip_chirps_v3_semanal_desde_2000.csv` (una sola escritura; el archivo con fecha ya no existe).
   - Final por FTP frente a Earth Engine (240 días de enero a abril de 2025 y 2026, 15 600 pares distrito-día):
     diferencia media 0,003 mm, máxima 0,145 mm; 2 pares fuera de la tolerancia de b-IV (distrito 200503, 2026-01-10
     y 2026-03-12: 1,58 frente a 1,65 mm y 3,31 frente a 3,20 mm). Rosa los acepta como diferencia menor.
   - Semanas brote (sin las provisionales): temporada 2026, 89 por horizonte (19 distritos, 20 inicios limpios);
     posterior_2026 (2026-08-30 a 2026-10-11), 167 (36 distritos, 17 inicios limpios). Las dos superan el mínimo de 30.
   - b-VI (preliminar frente a final, enero a abril): ver «Paso b-VI» en `metricas/datos_2026.json`. En 2025 el
     preliminar llueve 5 % más que el final por semana (correlación semanal 0,95); en 2026, 7 % menos (0,94). La media
     de 5 semanas de b3 cambia en promedio 2,3 mm (2025) y 3,1 mm (2026) con correlación 0,98 y 0,97; los días
     >= 20 mm de o−3..o cambian en 106 de 845 orígenes (2025) y 219 de 1040 (2026), correlación 0,93 y 0,85.
     Aprobado por Rosa como descriptivo. **Riesgo anotado para d1 y d2 en producción:** los días >= 20 mm son la
     variable más sensible al preliminar (en enero a abril de 2026 el preliminar cuenta 170 días distrito con >= 20 mm
     frente a 213 del final; en 2025, 142 frente a 109).
   - **Evaluación corrida el 2026-11-08: b3 se adopta** (ver «Temporada 2026: resultados»).
f) **Matriz de clima: corrida el 2026-11-08; solo b3 se adopta y la base sigue siendo L + 5a + b3** (ver «Matriz
   de clima: resultados»). Preregistrada después de ver 2026 (`CLIMATE_MATRIX` en `code/preregistration.py`) y
   aprobada por Rosa con el filtro LOSO (>= 16 de 24 celdas con mejor Brier que L + 5a, también para b3), agregado
   por las comparaciones múltiples antes de ver b4, d3, d4, d5, e1, e2 y n1. 12 variantes sobre L + 5a (medias b1,
   b2, b3, b4; ventanas d1 a d5; anomalías e1 y e2 con la climatología del bloque; n1 = b3 con el Niño monótono);
   15 comparaciones (12 + los 3 cruces fijos). Código de e1, e2 y n1 en `code/phase_climate_matrix.py` (guardas G45
   a G50), notebook `16_matriz_clima.ipynb`, cifras en `metricas/matriz_clima.json`. **Después, Rosa eligió L + 5a +
   d3 como base con contexto** (b3 retadora; ver arriba y [plan.md](plan.md)).
g) **Diagnóstico frente a la persistencia (solo lectura, d3, b3 y L + 5a): hecho el 2026-11-08, pendiente del OK de
   Rosa** (ver «Diagnóstico frente a la persistencia»). El conteo se queda corto en los picos, no en la subida de 2026;
   la w retrospectiva es cercana a 0 en 2026; la persistencia avisa más inicios limpios que p >= 0,50 (18 de 20 son de
   junio a agosto, con el umbral estacional bajando); la calibración en promedio de 2026 es buena y `posterior_2026`
   subpronostica. Propuesta: probar solo la alerta combinada (p >= 0,50 o la persistencia) y documentar el resto como
   limitación. Después del OK: el preregistro del ajuste de hiperparámetros sobre L + 5a + d3 (sin correr).

**Por hacer:** la 6′ (otra familia con clima, lectura), si Rosa la retoma ahora que hay lluvia 2000–2026; y la
**fase 7** (síntesis frente a la
V2 con la HU0007-4 por celda, pruebas obligatorias, auditoría con `revisor-modelado`, intervalo del conteo con la μ
mezclada y congelamiento). No se ha empezado.

**Ramas abiertas sin PR:** `feat/chirps-precipitation` (ingesta de CHIRPS v3) y `fix/notebook-02-era5-land-imports`
(imports de las celdas de ERA5-Land del notebook 02). Los PR y los merges los decide Rosa.

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
- **Posible desfase entre el entrenamiento y la app (CHIRPS):** el modelo se entrenaría con el final `sat` y la app
  usaría el preliminar `sat`, que según la CHC se calcula con menos estaciones y sin el mismo control de calidad;
  sus valores pueden diferir del final. Cuando sale el final de un mes, las semanas se recalculan con él (el bronze
  conserva ambos). Es un riesgo a medir en la fase 7.
- **Retraso real del preliminar (medido el 2026-11-04):** con las fechas de modificación del listado
  `daily/prelim/sat/` de 2025 y 2026 (130 péntadas, 660 días; sin bajar archivos), el retraso entre el fin de la
  péntada y la publicación tiene mediana 2 días, percentil 90 de 4 y máximo de 18 (en 2025; en 2026 el máximo es
  5). 96 de 130 péntadas salieron en la fecha del calendario oficial (fin + 2). La ingesta fija la disponibilidad en
  fin de péntada + 5 días (`PUBLICATION_LAG_DAYS = 5`, rama `feat/chirps-precipitation`, commit `d3b7d9b`), que
  cubre el 94 % de 2025–2026. Los atrasos mayores se tratan en el diseño del serving.

## Fase 4 · Señal regional de El Niño (Niño 1+2)

### Verificación del dato y preregistro (2026-11-04, antes de correr)

- **Fuente:** NOAA CPC, `sstoi.indices` (OISST v2.1, base 1991-2020). Crudo `data/bronze/enso/sstoi_20261103.indices`;
  silver `data/silver/enso_nino12_mensual.csv`, 538 meses de 1982-01 a 2026-10, con `fecha_disponible` = día 10 del
  mes siguiente.
- **Verificación pedida por Rosa:** el valor de 2026-10 (5,25) es la columna `ANOM` que sigue a `NINO1+2` en el
  crudo (cuarta columna: `2026 10 26.12 5.25 29.24 4.16 29.88 1.20 30.01 3.25`), no la temperatura (26,12) ni la
  anomalía de Niño 3 (4,16), Niño 4 (1,20) o Niño 3.4 (3,25). Las 6 últimas filas procesadas coinciden con las
  crudas: 2026-05 1,81; 06 2,83; 07 3,56; 08 4,08; 09 4,69; 10 5,25.
- **Riesgo de extrapolación (observación):** en 2000–2025 la anomalía va de −1,90 (2007-11) a 3,30 (2023-08); en
  todo el registro 1982–2025 el máximo es 4,03 (1983-06). El valor de 2026-10 (5,25) queda fuera del rango de
  entrenamiento, y por encima del máximo del registro. Un modelo de árboles no extrapola: trataría 5,25 como el
  valor más alto que vio. Se revisa en la fase 7 para la app.
- **Contexto de la temporada 2026–2027 (observación, sin inferencia):** la anomalía de Niño 1+2 sube todos los
  meses desde 2026-05 (1,81) hasta 2026-10 (5,25). Qué implica para el dengue en Piura no se afirma aquí.
- **Preregistro `PHASE4`** (aprobado por Rosa el 2026-11-04 con la verificación anterior, commiteado antes de
  correr): 4a = C3 + anomalía del último mes disponible; 4b = C3 + media de los 3 últimos meses disponibles; cada
  una frente a L + 5a con la regla de 5 temporadas de las fases 2 y 3; guardas G21–G24. Si la 1b′ adopta H, 4a y
  4b se vuelven a medir sobre L + 5a + H.

### Resultados de la fase 4 (2026-11-04)

Notebook `10_fase4_nino.ipynb`; cifras en `metricas/fase4.json`; predicciones en
`models/experimentos/mejora_modelo/fase4/` (no versionado); MLflow `denguekay/mejora_modelo_fase4_nino`
(`01c630b438a6469da4e5909bb6b6262d`). Dispositivo: cuda, `n_jobs` = 12.

- **Guardas:** pasan todas. G21: 0 de 71 175 orígenes usan un mes publicado después de su cierre. G22: el test de
  no fuga pasa. G23: 0 de 71 110 orígenes desde 2005 sin valor. G24: L + 5a reproduce `fase5.json` (diferencia
  máxima 4,9e-11).
- **Rango en los orígenes desde 2005:** último mes de −1,90 a 3,30; media de 3 meses de −1,74 a 3,11.
- **Veredictos (regla de 5 temporadas):** 4a y 4b **empatan en h2, h3 y h4**; ninguna se adopta y la base sigue
  siendo L + 5a. F1 a favor en 0–1 de 5 temporadas y en contra en 1–2; ninguna guarda veta. La lectura sin 2010 y
  la regla de razón MAE de la fase 5 también dan empate en los tres horizontes.
- **Antelación (semilla 17, 193 episodios):** algo peor, sin significancia: diferencias de −0,005 a −0,026 con
  IC95 que incluye 0 en todos los horizontes; la caída más repetida está en 2022 (−0,03 a −0,08).
- **Recall de brotes nuevos** (2 primeras semanas, 5 temporadas × 3 horizontes): 4a mejora en 2 celdas y empeora
  en 6; 4b mejora en 2 y empeora en 9. Son diferencias de 1 a 3 semanas por celda (por ejemplo, 2022 · h4: 6 de 49
  con L + 5a frente a 4 de 49 con 4a). La hipótesis de que el índice regional adelanta los inicios no se observa
  con esta matriz.
- **Conteo (lectura):** la razón MAE baja en 2022 (h3: 0,875 con 4a y 0,841 con 4b frente a 0,927) y en el
  contraste 2024 (h4: 1,130 y 1,213 frente a 1,362), pero sube en 2015; la regla de razón MAE da empate.
- **Lectura (observación, no conclusión):** con la información de L, la anomalía Niño 1+2 publicada al origen no
  mejora la alerta en las temporadas que deciden. El valor es único por mes para toda la región, y en 2000–2025 hay
  pocos episodios de El Niño costero (el máximo es 2023); con tan pocos años, no se generaliza. Si la 1b′ adopta H,
  4a y 4b se repiten sobre L + 5a + H, como quedó preregistrado.

## Disponibilidad de los datos en la app (2026-11-04)

- **Referencia (decisión de Rosa; *hipótesis*):** la app corre cuando hay casos nuevos, y la Sala Situacional del
  MINSA va unas 3 semanas atrasada (una sola observación: en la semana epi 44 de 2026 seguía en la 41; no se sabe qué
  día exacto actualiza). Como referencia conservadora, un dato cuenta como disponible para un origen si se publica a
  más tardar en `origen_cierre` + 14 días. Con una sola observación, la cifra es una hipótesis a revisar.
- **Conteo de orígenes afectados desde 2005 (71 110), contra `origen_cierre` + 14 días:**
  - humedad de ERA5-Land con la alineación h=2 (la última semana usada termina en `origen_cierre`; ERA5-Land se
    publica unos 5 días después según Open-Meteo): **0** (margen mínimo de 9 días). Contra `origen_cierre` solo, los
    71 110 quedarían afectados: sin la referencia de los casos, H no estaría disponible al cierre;
  - CHIRPS con la misma alineación y disponibilidad en fin de péntada + 5 días: **0** (el retraso máximo desde el
    sábado es de 10 días);
  - Niño 1+2: la fase 4 usó el último mes con `fecha_disponible` <= `origen_cierre`, más estricto que la nueva
    referencia; **0** orígenes la violan. Con `origen_cierre` + 14 días, el 46,1 % de los orígenes (32 760) tendría un
    mes más reciente disponible: la fase 4 fue conservadora. No se vuelve a correr (paso c).
- **Para el serving:** antes de predecir, la app debe verificar que el clima de la última semana usada (humedad y
  lluvia) ya esté publicado. Eso cubre los atrasos raros del preliminar de CHIRPS (hasta unos 18 días después de la
  péntada en 2025).

## Diagnóstico frente a la persistencia (solo lectura, 2026-11-08)

Notebook `17_diagnostico_persistencia.ipynb`, código en `code/diagnosis_persistence.py` (tests en
`tests/test_diagnosis_persistence.py`), cifras en `metricas/diagnostico_persistencia.json`. Sin entrenar ni
preregistrar nada: predicciones guardadas de L + 5a y b3 (`temporada_2026`) y d3 (`matriz_clima`) reevaluadas con el
protocolo; medianas de 5 semillas. Fases de la curva regional con `episodes.curve_phase`. En `temporada_2026` no hay
fase de bajada (la curva sigue por encima del 60 % del máximo hasta el final) y en `posterior_2026` (7 semanas) solo
hay subida y pico.

**1 · Conteo por fase** (suma predicha / suma observada del conteo publicado, h2 / h3 / h4):

| Bloque · fase (semanas, casos) | L + 5a | b3 | d3 |
|---|---|---|---|
| 2026 · valle (27, 234) | 1,38 / 1,46 / 1,54 | 1,55 / 1,64 / 1,71 | 1,51 / 1,59 / 1,65 |
| 2026 · subida (9, 1354) | 1,06 / 1,07 / 0,96 | 1,12 / 1,17 / 1,15 | 1,06 / 1,11 / 1,02 |
| 2026 · pico (17, 5979) | 0,77 / 0,69 / 0,66 | 0,75 / 0,66 / 0,62 | 0,82 / 0,74 / 0,71 |
| posterior · subida (4, 2294) | 0,73 / 0,65 / 0,56 | 0,69 / 0,60 / 0,49 | 0,79 / 0,71 / 0,60 |
| posterior · pico (3, 3337) | 0,56 / 0,44 / 0,39 | 0,57 / 0,43 / 0,35 | 0,65 / 0,54 / 0,48 |

En la temporada 2026 el conteo **no se queda corto en la subida** (entre −4 % y +17 %): **se queda corto en el pico**
(18–38 % menos) y sobrepronostica el valle. En `posterior_2026`, el arranque de la temporada 2026-2027, se queda
corto **en la subida y en el pico** (21–65 % menos), más cuanto mayor el horizonte. La persistencia también se queda
corta, pero su error medio es igual o menor: la razón MAE del conteo publicado es 1,03–1,10 en el pico de 2026 para
L + 5a y b3, y 0,94–0,99 para d3; en el pico de `posterior_2026`, 1,12–1,22 para L + 5a y b3 y 0,98–1,01 para d3.
d3 es la que menos se queda corta en los picos de los dos bloques y en la subida de `posterior_2026`.

**2 · Peso w de 5a.** w usado en `temporada_2026` (h2 / h3 / h4): L + 5a 0,62 / 0,65 / 0,68; b3 0,86 / 0,88 / 0,91;
d3 0,72 / 0,73 / 0,75. Es parecido al de 2011–2017 (L + 5a 0,58–0,75) y menor que el de 2018–2024 (0,73–0,87).
Razón MAE en 2026 (h2 / h3 / h4) con w = 1 (solo el modelo): L + 5a 1,21 / 1,23 / 1,23; b3 1,17 / 1,16 / 1,13; d3
1,09 / 1,11 / 1,09. Con la w usada: 1,06 / 1,10 / 1,07; 1,11 / 1,12 / 1,10; 1,03 / 1,05 / 1,01. Con w = 0 es 1 por
definición. **La w retrospectiva** (la de menor MAE en el propio bloque; usa el futuro) es 0,02–0,32 en 2026 y **0 en
`posterior_2026`** para las tres. Es decir, en 2026 la μ del modelo no agrega nada al conteo frente a la persistencia.

**3 · Los 20 inicios limpios de 2026.** Probabilidad calibrada mediana para la semana del inicio (h2 / h3 / h4):
L + 5a 0,18 / 0,25 / 0,07; b3 0,20 / 0,27 / 0,09; d3 0,21 / 0,29 / 0,085. Inicios avisados con >= 2 semanas por
p >= 0,50: L + 5a 2 / 2 / 2; b3 2 / 3 / 2; d3 3 / 4 / 5. **Por la persistencia: 4 / 9 / 8.** Hallazgo de la lectura:
18 de los 20 inicios caen entre junio y agosto de 2026. En los 20, el umbral de brote de la semana del inicio es más
bajo que el de la semana del origen de h3 (por ejemplo, 200601: 461 casos en el origen frente a 51 en el inicio), y en
varios distritos los casos siguen en un nivel que no era brote en el origen pero supera el umbral más bajo del
inicio (200114: 79 casos frente a 143 y 43; 200401: 82 frente a 168 y 71). *Hipótesis:* estos «inicios» son en buena
parte transmisión que no bajó fuera de temporada (invierno de Niño) mientras el umbral estacional sí bajó. La
persistencia los avisa casi por construcción; el modelo espera la bajada estacional. d3 los sigue un poco mejor.

**4 · Calibración** (probabilidad media / tasa observada de semanas brote, h2 / h3 / h4):

| Bloque (tasa observada) | L + 5a | b3 | d3 |
|---|---|---|---|
| temporada_2026 (2,6 %) | 0,93 / 0,92 / 0,92 | 0,96 / 0,95 / 0,95 | 0,99 / 0,98 / 0,99 |
| posterior_2026 (36,7 %) | 0,74 / 0,66 / 0,58 | 0,78 / 0,68 / 0,59 | 0,81 / 0,73 / 0,64 |

En la temporada 2026 la calibración en promedio es buena (d3, 0,98–0,99). En `posterior_2026` las tres
subpronostican, más a mayor horizonte, con una tasa de brote del 37 %.

**5 · Propuesta (sin correr), para que Rosa decida:**

- **Lo único que propongo probar antes de congelar:** una alerta combinada, «p >= 0,50 **o** alerta de la
  persistencia», sobre las predicciones guardadas de d3 y b3. No hay que entrenar nada ni cambiar la probabilidad, y
  el Brier no cambia. Es una regla fija, así que se puede preregistrar. Se juzgaría con la F1, la precisión y la
  antelación en los inicios limpios de las 6 temporadas decisivas, frente a la alerta p >= 0,50 sola, con la regla de
  la alerta de `SEASON_2026`. Riesgo: más falsos positivos en años normales (la precisión puede caer). La operación
  semanal ya tiene la persistencia, así que no agrega fuentes.
- **Documentar como limitación (sin ajuste):**
  - el conteo se queda corto en los picos (18–38 % en 2026 y 35–65 % en `posterior_2026`), y la μ no le gana a la
    persistencia en 2026 (w retrospectiva cerca de 0). El intervalo del conteo de la fase 7 debería reflejarlo;
  - la probabilidad subpronostica cuando la tasa de brote sale del rango histórico (`posterior_2026`).
- **No propongo:**
  - una w «reciente»: la w de los bloques 2018–2024 (0,73–0,96 según variante y horizonte) queda lejos de la retrospectiva;
  - recalibrar con pesos por recencia: en la temporada 2026 la calibración en promedio ya es buena, y
    `posterior_2026` solo se reporta.

## Matriz de clima: resultados (2026-11-08)

Notebook `16_matriz_clima.ipynb`, cifras en `metricas/matriz_clima.json`, MLflow
`denguekay/mejora_modelo_matriz_clima` (run `3e33511d09124833a0d7fa63e875daa3`). GPU, 5 semillas.

**Guardas: todas pasan.** G40, G17, G25, G30, G35a/b, G42, G43 (lluvia, ventanas, temperatura, Niño), G44; G45
(e1 + ventana de la climatología = d1, bloques 2008 y 2026 y sintética), G46, G47 (bloques 2016 y 2026), G48 (todos
los cortes), G49 (n1 monótona en cada bloque, peor diferencia 0,0) y G50 (restricción 0 = b3, diferencia 0,0).
Reutilización: L + 5a, b3, d1 y d2 reproducen con la semilla 17 las predicciones de `temporada_2026` (G41,
diferencia 0,0); b1 y b2 las de `paso_b` (G41, 0,0; 975 filas nuevas de los bloques 2026). El resto se entrenó.

**Veredictos frente a L + 5a (regla `SEASON_2026` + filtro LOSO):**

| Variante | Columnas | Brier h2/h3/h4 | F1 h2/h3/h4 | Conteo h2/h3/h4 | Celdas LOSO mejores (de 24) | Adoptada |
|---|---|---|---|---|---|---|
| b1 | 1 | empate/empate/empate | empate ×3 | empate ×3 | 16 | no |
| b2 | 2 | empate ×3 | empate ×3 | empate ×3 | 15 | no |
| b4 | 3 | empate ×3 | empate ×3 | empate ×3 | 20 | no |
| d3 | 4 | **gana**/empate/empate | empate ×3 | empate ×3 | 21 | no (gana un solo horizonte) |
| d5 | 4 | empate ×3 | empate ×3 | empate ×3 | 17 | no |
| b3 | 4 | **gana/gana**/empate | empate ×3 | empate ×3 | 19 | **sí** |
| n1 | 4 | empate ×3 | empate ×3 | empate ×3 | 19 | no |
| d4 | 6 | empate ×3 | empate ×3 | empate ×3 | 12 | no |
| d1 | 14 | empate ×3 | empate ×3 | empate ×3 | 22 | no |
| e1 | 14 | empate ×3 | empate ×3 | empate ×3 | 17 | no |
| d2 | 15 | empate ×3 | empate ×3 | empate ×3 | 23 | no |
| e2 | 15 | empate ×3 | empate ×3 | empate ×3 | 17 | no |

Una sola adoptada, así que no hay cruces entre adoptadas; **base: b3** (`select_matrix_base`). Cruces fijos frente a
b3: d1 y d2 empatan en todo; e1 **pierde** en Brier h4, F1 h3 y conteo h3. Comparaciones hechas: 15.

**Métricas reportadas (no deciden).** Brier de `temporada_2026` en h2: 0,010 en b3, b4, d1, d2, d3 y n1; 0,011 en
L + 5a y el resto. F1 a 0,50 de `temporada_2026` h2/h3/h4: L + 5a 0,658/0,557/0,424; b3 0,671/0,611/0,455; d3
0,703/0,648/0,539 (la más alta). En `posterior_2026` (solo se reporta), d3 tiene el Brier más bajo en los tres
horizontes (0,087/0,104/0,120 frente a 0,095/0,115/0,134 de L + 5a y 0,091/0,112/0,132 de b3) y la razón MAE más
cerca de 1 (1,01/1,01/1,07). HU0007-4: ninguna celda de ninguna variante cumple la parte de clasificación ni la de
regresión en `temporada_2026` ni en `posterior_2026` (78 celdas). Brier mediano frente a L + 5a (sobre las 6
temporadas y 3 horizontes): b3 −0,00065, n1 −0,00063, d2 −0,00062; e1 +0,00022, e2 +0,00014, d4 +0,00005.

**n1 (Niño monótono):** la pendiente de Platt es positiva en todos los bloques (mínima 0,842; mediana 1,22 a 1,26 por
horizonte), así que la restricción no invierte la probabilidad. n1 empata con L + 5a en todo; frente a b3 no se
compara (la regla no la adopta).

**SHAP (semilla 17; b3, n1 y d2, las tres con mejor Brier mediano; bloques 2022, 2023 y 2026, h2):** domina
`propia_semanas_desde_ultimo_caso` (1,26 a 1,53), luego `hist_media_4` y la temperatura (`temp_media_media5_h2`
0,30 a 0,34 en b3 y n1; `temp_media_s0` 0,17 a 0,20 en d2) y la estacionalidad. El Niño pesa poco y menos en 2026
(b3: 0,043 en 2022, 0,020 en 2023, 0,007 en 2026). Detalle por horizonte en el JSON.

**Lectura (observación, no conclusión):** con 15 comparaciones y empates casi en todo, la matriz no muestra una
variante de clima mejor que b3 por la regla preregistrada. d3 (solo ventanas de temperatura) es la única señal
distinta: gana el Brier en h2, tiene 21 de 24 celdas LOSO mejores y es la mejor en las métricas reportadas de 2026
y `posterior_2026`, pero no alcanza la regla y es una de 15 comparaciones; queda como hipótesis, no como hallazgo.

## Temporada 2026: resultados (2026-11-08)

Preregistro `SEASON_2026`: regla aprobada por Rosa antes de bajar los datos (commit `e02ebe1`); guardas, métricas,
lecturas y validación dejando una temporada fuera escritas antes de entrenar (`5a6b27e`); enmienda antes de entrenar
(`f2ddca2`): la semana 53 de 2025 (65 filas, 3 casos) se toma del silver de la Sala porque el panel integrado termina
en la semana 52 y había un hueco antes de 2026. Notebook `15_temporada_2026.ipynb`; cifras en
`metricas/temporada_2026.json`; predicciones en `models/experimentos/mejora_modelo/temporada_2026/` (no versionado);
MLflow `denguekay/mejora_modelo_temporada_2026` (`2d22b09851374954a8cd46ed249ea155`). Dos correcciones de código
después del primer intento y antes de mirar ningún veredicto: el umbral de empate de la regla del conteo
(`df6fb03`) y la climatología de la lectura dejando una temporada fuera (`37c6415`); la segunda corrida
reutilizó las predicciones ya entrenadas por la primera (mismo código y datos).

- **Guardas (todas pasan):** G40 (la serie extendida reproduce las 71 175 filas 2005-2025 del estudio sin
  diferencias en casos, umbral ni brote; agrega la semana 53 de 2025 y 2665 filas de 2026, 65 distritos × semanas 1 a
  41, iguales a la Sala); G17, G25 y G30 (diferencia 0); G35a (las sumas semanales del diario son iguales al silver en
  las 91 000 semanas, también las preliminares); G35b (≤ 5,7e-14); G42 (0 de 73 840 orígenes sin clima hasta el último
  usado, 2026-10-03); G43 (0 orígenes afectados contra `origen_cierre` + 14 días en lluvia, días fuertes, temperatura,
  humedad y Niño; margen mínimo 4 días); G44 (4 tests de no fuga); G41 (L, b3 y d1 reentrenadas reproducen sus
  915 525 predicciones guardadas con diferencia 0; 975 filas nuevas por la semana 53 de 2025); G29 (4,9e-11).
- **Semanas brote de 2026:** 89 por horizonte (supera el mínimo de 30), 20 inicios limpios.
- **Veredicto: b3 se adopta.** Frente a L + 5a, el Brier de b3 está a favor en 5, 5 y 4 de las 6 temporadas y en
  contra en ninguna: gana en h2 y h3 y empata en h4, sin vetos. Alerta (F1): empate en los tres horizontes (a favor
  en 1, 2 y 3; en contra en 1). Conteo (razón MAE): empate en los tres (a favor en 3, en contra en 2). Antelación:
  0,000 [−0,028; 0,033] en h2, −0,014 [−0,047; 0,014] en h3 y −0,014 [−0,042; 0,014] en h4. d1 y d2: empate en el
  Brier, la alerta y el conteo en los tres horizontes. Con una sola adoptada no hay cruce. **Declaración:** la regla
  del Brier se fijó después de ver que el criterio (c) habría adoptado b3 con las 5 temporadas (lectura del paso d);
  la adopción de b3 no es independiente de haber mirado esos resultados.
- **Temporada 2026 por variante (L + 5a / b3 / d1 / d2, mediana de 5 semillas):**
  - Brier: 0,011 / 0,010 / 0,010 / 0,010 (h2), 0,012 / 0,011 / 0,011 / 0,011 (h3), 0,016 / 0,015 / 0,015 / 0,015 (h4).
  - Brier skill score frente a la climatología: 0,630 / 0,642 / 0,645 / 0,644 (h2), 0,587 / 0,607 / 0,612 / 0,612
    (h3), 0,463 / 0,484 / 0,496 / 0,495 (h4).
  - AUPRC: 0,791 / 0,801 / 0,801 / 0,801 (h2), 0,743 / 0,762 / 0,771 / 0,771 (h3), 0,586 / 0,614 / 0,630 / 0,631 (h4).
  - AUPRC en inicios (persistencia < max(umbral, 2); 29, 26 y 36 positivos): 0,246 / 0,275 / 0,265 / 0,263 (h2),
    0,159 / 0,171 / 0,171 / 0,169 (h3), 0,115 / 0,137 / 0,135 / 0,137 (h4).
  - F1 a 0,50: 0,658 / 0,671 / 0,671 / 0,676 (h2), 0,557 / 0,611 / 0,610 / 0,610 (h3), 0,424 / 0,455 / 0,511 / 0,522 (h4).
  - Razón MAE: 1,064 / 1,113 / 1,082 / 1,088 (h2), 1,099 / 1,118 / 1,096 / 1,098 (h3), 1,072 / 1,097 / 1,083 / 1,087
    (h4): ninguna variante supera a la persistencia en 2026. Razón RMSE entre 0,96 y 1,00.
  - HU0007-4: ninguna celda de 2026 se cumple, ni en clasificación ni en regresión, con ninguna variante.
  - Antelación (semilla 17, 20 inicios): avisados con >= 1 semana 10 % (h2), 5–15 % (h3) y 10–20 % (h4) según la
    variante; la persistencia, 20 %, 45 % y 40 %.
- **posterior_2026 (semanas 35 a 41 de 2026, entrenado hasta la temporada 2026; solo se reporta; 167 semanas brote,
  17 inicios, debajo del mínimo para la antelación):** Brier 0,095 / 0,091 / 0,090 / 0,090 (h2) a 0,134 / 0,132 /
  0,130 / 0,129 (h4); AUPRC 0,90 a 0,93 en todas; razón MAE 1,07 a 1,28 (peor que la persistencia; b3 es la más alta
  en h4, 1,284).
- **Niño por origen:** en temporada_2026 los 55 orígenes están dentro del rango de entrenamiento (−1,74 a 3,11; el
  máximo en 2026 es 2,73); en posterior_2026, 4 de 9 orígenes están fuera (del 2026-09-12 al 2026-10-03, hasta 3,49).
- **Lluvia preliminar:** solo el origen del 2026-10-03 (posterior_2026) usa una semana preliminar (la del 2026-09-27),
  en b3 y en d1/d2.
- **Semanas provisionales (fuera de las métricas):** 2026-10-18 y 2026-10-25, 2629 casos, 60 semanas brote en 37
  distritos.
- **Dejando una temporada fuera (lectura optimista, no decide; solo compara variantes):** en las 24 celdas (8
  temporadas × 3 horizontes), el Brier mejora frente a L + 5a en 19 (b3), 22 (d1) y 23 (d2); la AUPRC en 19, 20 y 20;
  la F1 en 14, 14 y 13; la razón MAE en 16, 17 y 17. Las mejoras se concentran en 2010, 2017, 2022, 2023, 2024 y 2026; en
  2015 y 2016 las diferencias son de milésimas. Ejemplos: 2023 · h4 Brier 0,088 frente a 0,080 / 0,079 / 0,079; 2017 ·
  h4 AUPRC 0,710 frente a 0,734 / 0,730 / 0,731. *Hipótesis:* con más temporadas de Niño en el entrenamiento, el clima
  aporta algo más; no se puede afirmar porque esta lectura usa el futuro.
- **Lectura (observación, no conclusión):** el clima mejora un poco la calidad de la probabilidad (Brier, BSS, AUPRC)
  en las temporadas grandes y en 2026, pero no la alerta al corte de 0,50 ni el conteo; en 2026 ningún modelo supera a
  la persistencia en el conteo ni cumple la HU0007-4.

## Paso d de clima · Ventanas de clima: resultados (2026-11-06)

Preregistro `STEP_D` (commit `b7ad38c`; respuestas de Rosa y criterio (c) antes de correr en `658d0bd`), agregado
después de ver b1, b2 y b3. Notebook `14_paso_d_ventanas_clima.ipynb`; cifras en `metricas/paso_d.json`; predicciones
en `models/experimentos/mejora_modelo/paso_d/` (no versionado); MLflow `denguekay/mejora_modelo_paso_b_lluvia_chirps`
(`851bf57f64214ed48d38c84914304f71`). d1 = C3 + 14 columnas de ventanas (sin Niño).

- **Guardas (todas pasan):** G17, G25 y G30 (diferencia 0 en 30 095 filas); G29 (L + 5a reproduce `fase5.json`,
  4,9e-11); G35a (las sumas semanales del bronze diario de Earth Engine son iguales al silver en las 90 675 semanas,
  diferencia 0, ninguna semana sin par); G35b ((o + 4 × media o−1..o−4) / 5 igual a la media de 5 semanas validada:
  diferencia máxima 5,7e-14 en lluvia, 7,1e-15 en temperatura y 4,3e-14 en humedad); G35c (tests sintéticos de las
  ventanas y de los días >= 20 mm); G36 (no fuga: test sintético y, en los datos reales, cambiar todo el clima posterior
  al 2016-12-31 no cambia ninguna columna en 40 820 orígenes hasta esa fecha y sí en 30 355 posteriores); G37 (0 de
  71 110 orígenes desde 2005 sin valor); G38 (0 de 71 175 orígenes afectados contra `origen_cierre` + 14 días en lluvia,
  días fuertes, temperatura y humedad; margen mínimo 4 días en CHIRPS); G39 (las predicciones guardadas de b3
  reproducen `paso_b3.json`, 4,9e-11).
- **Veredicto: empate en los tres criterios y en los tres horizontes, frente a L + 5a y frente a b3; d1 no se adopta
  y la base sigue siendo L + 5a.** Frente a L + 5a: F1 a favor en 1, 0 y 2 de 5 temporadas; razón MAE a favor en 3 y
  en contra en 1 en los tres horizontes; Brier a favor en 2, 2 y 3 (en contra en 0, 0 y 1). Antelación frente a
  L + 5a: 0,021 [−0,016; 0,057] en h2, −0,016 [−0,052; 0,016] en h3 y −0,010 [−0,047; 0,021] en h4. Frente a b3,
  ningún «pierde» (d1 no pierde frente a b3 en ningún criterio).
- **Métricas reportadas (mediana de 5 semillas; no deciden):** el Brier de las tres variantes difiere en milésimas en
  cada celda; d1 y b3 lo bajan algo en 2023 y 2024 (2024 · h4: 0,089 L + 5a, 0,085 b3, 0,084 d1). Brier skill score
  frente a la climatología fuera de muestra: entre 0,34 y 0,76 en todas las celdas y variantes (todas mejoran a la
  climatología); las diferencias entre variantes son de 0,00 a 0,02. AUPRC general: diferencias de hasta 0,03
  (2010 · h4: 0,600, 0,632 y 0,612). AUPRC con persistencia < umbral_brote_casos: d1 es la más alta en 12 de 18
  celdas, pero con pocas filas positivas (24 a 141 por celda) y sin un patrón estable (en 2015 · h3–h4 y 2022 · h3–h4 baja
  frente a L + 5a). Ese subconjunto deja fuera, por la definición literal, las filas con umbral 0 (2024 de 3380 en
  2022 · h2), que son la mayoría.
- **Lectura del criterio (c) para b3 frente a L + 5a (declarada posterior a ver b3):** b3 gana por el Brier en h2 y h3
  (4 de 5 temporadas a favor y 0 en contra, sin vetos) y empata en h4; la alerta y el conteo de b3 eran empate, así
  que con el criterio (c) b3 se habría adoptado. Es una lectura: el criterio se fijó después de ver b3 y no cambia
  su decisión.
- **HU0007-4 (2022 y 2023):** la clasificación se cumple solo en 2023 · h2 con las tres variantes; la regresión, en 3
  de 6 celdas con d1 (2023 · h2, h3 y h4), 5 de 6 con b3 y 1 de 6 con L + 5a.
- **SHAP de d1 (semilla 17):** sigue mandando `propia_semanas_desde_ultimo_caso` (1,15 a 1,53); entre el clima, la
  temperatura de la semana del origen es la mayor (0,19 a 0,24) y la de o−1..o−4 la siguiente (0,09 a 0,19); las
  ventanas de o−5 a o−12 de temperatura pesan menos (0,004 a 0,06). La lluvia (0,002 a 0,09), la humedad (0,007 a
  0,09) y los días >= 20 mm (0,0002 a 0,08) pesan poco; en 2024 los días >= 20 mm de o−3..o y la humedad de o−9..o−12
  suben a 0,06–0,09. *Hipótesis:* la temperatura reciente sigue representando el ciclo estacional.
- **Lectura (observación, no conclusión):** separar las ventanas no cambia la alerta, el conteo ni el Brier frente a
  L + 5a; con b1, b2, b3 y d1 son cuatro empates del clima sobre L + 5a.

## Paso b de clima · Variante b3 (clima completo): resultados (2026-11-06)

Preregistro `STEP_B3` (commit `31553db`; cambios de Rosa antes de correr en `96af5cd`), agregado después de ver b1 y
b2: es la tercera comparación del paso b. Notebook `13_paso_b3_clima_completo.ipynb`; cifras en
`metricas/paso_b3.json`; predicciones en `models/experimentos/mejora_modelo/paso_b3/` (no versionado); MLflow
`denguekay/mejora_modelo_paso_b_lluvia_chirps` (`fa2a7b5bff2f45cd84d30e6d707e59b6`). b3 = C3 +
`hum_rel_media_media5_h2` + `precip_total_mm_media5_h2` + `temp_media_media5_h2` + `nino12_anom_media3`.

- **Guardas (todas pasan):** G17 y G25 (diferencia 0 en 30 095 filas con valor, mismos vacíos); G19, G28 y G32 (0 de
  71 110 orígenes desde 2005 sin valor); G21 (0 de 71 175 orígenes con un mes del Niño publicado después de
  `origen_cierre`); G22, G26 y G31 (tests de no fuga del Niño, la lluvia y la temperatura); G27 (lluvia: 0
  afectados contra `origen_cierre` + 14 días, margen mínimo 4 días); G29 (L + 5a reproduce `fase5.json`, 4,9e-11);
  G30 (temperatura igual a `build_observed_climate` h=2 en 30 095 filas, diferencia 0); G33 (temperatura con 7 días
  de retraso: 0 de 71 175 afectados contra `origen_cierre` + 14 días); G34 (2026-10 = 5,25 en el crudo
  `sstoi_20261103.indices` y en el silver).
- **Veredicto: empate en h2, h3 y h4 en la alerta y en el conteo; b3 no se adopta y la base sigue siendo L + 5a.**
  Alerta: F1 a favor en 1, 1 y 2 de 5 temporadas y en contra en 1; ninguna guarda veta. Conteo (regla de la fase
  5): razón MAE a favor en 3 de 5 temporadas y en contra en 1 en los tres horizontes (hacen falta 4 y 0).
- **Antelación (semilla 17, 193 episodios):** 0,000 [−0,036; 0,036] en h2, −0,026 [−0,062; 0,005] en h3 y −0,016
  [−0,047; 0,010] en h4 (IC95 que incluyen 0).
- **Lecturas que no deciden:**
  - Sin 2010: empate en los tres horizontes.
  - 2024 (contraste): F1 0,805, 0,797 y 0,770 frente a 0,799, 0,788 y 0,761; razón MAE 0,907, 0,857 y 0,819 frente a
    1,136, 1,238 y 1,362.
  - Recall de brotes nuevos (2 primeras semanas, 15 celdas): mejora en 2 y empeora en 9 (en 2022, de 0,122–0,163 a
    0,082–0,102).
  - Frente a la V2 en 2022 y 2023: en 2022 · h4, F1 0,635 (b3), 0,652 (L + 5a) y 0,333 (V2); razón MAE en 2022
    0,888, 0,821 y 0,787 (b3) frente a 0,946, 0,927 y 0,929 (L + 5a) y 0,919, 0,883 y 0,838 (V2).
  - HU0007-4 (6 celdas de 2022 y 2023): la clasificación se cumple solo en 2023 · h2 con las tres; la regresión se
    cumple en 5 de 6 celdas con b3 (todas menos 2022 · h2), en 1 con L + 5a y en 2 con la V2.
  - 2017 y 2023 frente a L + 5a: F1 casi igual (2017: 0,699, 0,657 y 0,624 frente a 0,703, 0,658 y 0,632; 2023:
    0,861, 0,837 y 0,819 frente a 0,857, 0,835 y 0,811) y razón MAE algo más baja.
  - SHAP del regresor (media de |SHAP|, semilla 17): la temperatura es la segunda variable en 2022, 2023 y 2024
    (0,33 a 0,46), detrás de `propia_semanas_desde_ultimo_caso` (1,14 a 1,49) y por delante de `hist_media_4`; la
    lluvia va de 0,06 a 0,18, la humedad de 0,03 a 0,06 y el Niño de 0,02 a 0,06. *Hipótesis:* la temperatura de 5
    semanas sigue el ciclo estacional y podría estar repartiéndose el papel de `semana_epi_seno`/`coseno`, que bajan
    frente al estudio 05; no se probó.
  - Rango del Niño: `nino12_anom_media3` va de −1,74 a 3,11 en los orígenes desde 2005; el valor actual (agosto a
    octubre de 2026, publicado el 2026-11-10) es 4,67, fuera de ese rango.
  - Contrafactual del Niño (modelo del bloque, semilla 17; con el valor real reproduce el μ guardado, diferencia
    0): con 3,3 y con 5,25 las predicciones son idénticas en los 4 orígenes (los árboles no distinguen valores por
    encima del rango de entrenamiento). En 2017 (bloque entrenado hasta 2016), fijar el Niño en 2,0, 3,3 o 5,25
    *baja* los casos predichos frente al valor real (0,39 y 0,58): en 2017-03-04, de 431, 482 y 532 a 402, 434 y 464
    casos (h2, h3 y h4), con 1 distrito menos en alerta; los observados fueron 799, 1105 y 1671. En 2023 el efecto es
    de hasta 4 % (2023-03-04 · h4: 960 con el real, 929 con 2,0 y 955 con 3,3 o 5,25; observados 1431). La probabilidad
    media cambia menos de 0,03.
- **Lectura (observación, no conclusión):** el clima completo no cambia la alerta en las temporadas que deciden y
  empeora el recall de los brotes nuevos; mejora el conteo en 2022, 2024 y la HU0007-4 de regresión, pero no
  alcanza la regla de la fase 5 (3 de 5 temporadas). El modelo no traduce una anomalía del Niño mayor en más casos:
  con lo visto en 2000–2025 (máximo de 3,11 en los orígenes), no se puede
  usar b3 para anticipar el efecto del Niño previsto para 2026–2027; es un riesgo a tratar en la fase 7 y en la app.

## Paso b de clima · Lluvia de CHIRPS v3: resultados (2026-11-06)

Preregistro `STEP_B` (commit `b82bf80`), sin enmiendas. Notebook `12_paso_b_lluvia_chirps.ipynb`; cifras en
`metricas/paso_b.json`; predicciones en `models/experimentos/mejora_modelo/paso_b/` (no versionado); MLflow
`denguekay/mejora_modelo_paso_b_lluvia_chirps` (`c2c52c15a2bf4e71a5d7b339e51c04e6`). Silver de entrada
`data/silver/precip_chirps_v3_semanal_desde_2000.csv` (90 675 filas, 2000-01-02 a 2026-09-20, todo `final`).

- **Guardas (todas pasan):** G25: la lluvia calculada con el silver vigente («Best match») es igual a
  `precip_total_mm_media5_h2` del gold en las 30 095 filas con valor (diferencia 0, mismos vacíos). G26: el test de
  no fuga por perturbación pasa. G27: 0 de 71 175 orígenes con lluvia usan una semana publicada después de
  `origen_cierre` + 14 días (margen mínimo 4 días; contra `origen_cierre` solo, los 71 175 quedarían afectados).
  G28: 0 de 71 110 orígenes desde 2005 sin valor en b1 y en b2. G29: L + 5a reproduce `fase5.json` (diferencia
  máxima 4,9e-11 en 18 filas). b2: G17 (diferencia 0 en 30 095 filas) y G19 (0 de 71 110 sin H) pasan. Todas las
  semanas de lluvia que llegan a los orígenes desde 2005 son `final`.
- **Veredicto (regla de 5 temporadas): empate en h2, h3 y h4 en b1 y en b2**; ninguna se adopta, no hay cruce y la
  base sigue siendo L + 5a. F1 a favor en 0, 0 y 1 de 5 temporadas (h2, h3, h4) en las dos variantes y en contra en
  0; ninguna guarda veta. En las guardas, la razón MAE va a favor en 2 a 4 de 5 temporadas (y en contra en 1) y la
  AUPRC en 1 a 3; no deciden.
- **Antelación (semilla 17, 193 episodios):** b1 +0,005 [−0,021; 0,031] en h2, −0,010 [−0,036; 0,016] en h3 y
  −0,010 [−0,026; 0,000] en h4; b2 −0,005 en los tres (IC95 que incluyen 0).
- **Lecturas que no deciden:** sin 2010, empate en los tres horizontes en las dos; la regla de razón MAE de la
  fase 5, empate en los tres. Contraste 2024: F1 casi igual (b1 0,805, 0,792 y 0,769 frente a 0,799, 0,788 y 0,761)
  y razón MAE más baja (b1 0,903, 0,860 y 0,844 frente a 1,136, 1,238 y 1,362). Recall de brotes nuevos (2 primeras
  semanas, 15 celdas): b1 mejora en 1 y empeora en 3; b2 mejora en 1 y empeora en 5. Frente a la V2 en 2022 y 2023,
  b1 y b2 quedan como L + 5a (en 2022 · h4, F1 0,649 y 0,646 frente a 0,652 de L + 5a y 0,333 de la V2). HU0007-4:
  la clasificación se cumple solo en 2023 · h2, igual que en L + 5a; la regresión se cumple en 2023 · h2, h3 y h4
  con b1 y b2 (L + 5a solo en h4).
- **CHIRPS − «Best match»** (`precip_total_mm_media5_h2`, 2017–2025, 65 distritos): CHIRPS es más baja todos los
  años (diferencia media de −6,8 a −13,1 mm; media de CHIRPS de 3,9 a 22,6 mm frente a 11,5 a 35,6 mm de «Best
  match») con correlación 0,77–0,90 por año. Va en el mismo sentido que la comparación mensual del plan (Open-Meteo
  da en promedio un 65 % más).
- **Lectura (observación, no conclusión):** con la información de L + 5a, la lluvia de CHIRPS (sola o con la
  humedad) no mejora la alerta en las temporadas que deciden. La baja de la razón MAE en 2024 y en las guardas es
  una observación del conteo que la regla no usa para decidir; con pocos brotes, no se generaliza.

## Fase 1b′ · Humedad de ERA5-Land: resultados (2026-11-04)

Preregistro `PHASE1B_PRIME` (commit `ebad7be`), sin enmiendas: H con la alineación h=2 tal como quedó preregistrada
(el código acepta un rezago extra, `extra_lag`, que no se usa). Notebook `11_fase1b_prima_humedad.ipynb`; cifras en
`metricas/fase1b_prima.json`; predicciones en `models/experimentos/mejora_modelo/fase1b_prima/` (no versionado);
MLflow `denguekay/mejora_modelo_fase1b_prima_humedad` (`baa635b12e0642adbf82574ccf71e1a7`). Silver de entrada
`data/silver/meteo_humedad_era5_land_2000_2025.csv` (88 140 filas, 2000-01-02 a 2025-12-21, sin vacíos), escrito
con la excepción autorizada por Rosa (el hash de `meteo_semanal_distrital.csv` no cambió).

- **Guardas:** G17 pasa (H calculada con el silver vigente es igual a `hum_rel_media_media5_h2` del gold en las
  30 095 filas con valor; diferencia 0, mismos vacíos; distritos mapeados por centroide, gold leído con
  `float_precision="round_trip"`). G18: el test de no fuga pasa. G19: 0 de 71 110 orígenes desde 2005 sin H. G20:
  L + 5a reproduce `fase5.json`. Disponibilidad contra `origen_cierre` + 14 días: 0 afectados.
- **Veredicto (regla de 5 temporadas):** **empate en h2, h3 y h4**; H no se adopta y la base sigue siendo L + 5a.
  F1 a favor en 0 de 5 temporadas y en contra en 0–1; ninguna guarda veta. La lectura sin 2010 y la regla de razón
  MAE de la fase 5 también dan empate en los tres horizontes.
- **Antelación (semilla 17, 193 episodios):** +0,010 [−0,016; 0,036] en h2, −0,010 [−0,031; 0,010] en h3 y −0,005
  [−0,016; 0,000] en h4; el IC95 incluye 0.
- **Recall de brotes nuevos** (2 primeras semanas, 5 temporadas × 3 horizontes): mejora en 2 celdas y empeora en 7;
  son diferencias de 1 a 2 semanas por celda (por ejemplo, 2022 · h3: 8 de 49 con L + 5a frente a 6 de 49).
- **Conteo (lectura):** la razón MAE baja en 2022 y 2023 (2023 · h3: 0,734 frente a 0,763) y mucho en el contraste
  2024 (h3: 0,938 frente a 1,238), pero sube en 2010 · h2 y en 2015–2016; la regla de razón MAE da empate. En la
  HU0007-4 de regresión, 2023 · h3 pasa a cumplir con H (razón MAE 0,734 y RMSE 0,817, ambas <= 0,85; con L + 5a
  la RMSE era 0,852).
- **Frente a la V2 (lectura, 2022 y 2023):** en 2022 · h4 la V2 tiene F1 0,333 (recall 0,202) frente a 0,652 de
  L + 5a y 0,648 de L + 5a + H; en 2023 las tres quedan en F1 de 0,81 a 0,86. La V2 usa la humedad y la lluvia de
  «Best match» y su propio Platt.
- **Humedad ERA5-Land − «Best match», 2017–2025:** diferencia media entre −0,22 (2023) y +1,55 (2021) puntos de
  humedad, MAE de 3,0 a 3,9 y correlación semanal de 0,84 a 0,88 según el año.
- **Lectura (observación, no conclusión):** con la información de L, la humedad de ERA5-Land no mejora la alerta en
  las temporadas que deciden; mejora el conteo en algunas temporadas, sin alcanzar la regla. Con pocos brotes, no se
  generaliza. Siguiente paso: la lluvia de CHIRPS v3 sobre L + 5a (paso b), con su propio preregistro.
