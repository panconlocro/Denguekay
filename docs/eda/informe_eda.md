# Informe del análisis exploratorio (Data Understanding) — Denguekay

**Proyecto:** predicción de brotes de dengue en Piura, Perú, con al menos 4 semanas de anticipación (CRISP-DM, Hito 2).
**Dataset:** panel distrito × semana epidemiológica, `data/silver/integrado/meteo_socio_epi_piura_2017_2025.csv`.
**Notebooks:** `notebooks/10_eda_*` a `16_eda_*`. Detalle por hallazgo: `docs/eda/hallazgos.md`. Problemas y decisiones pendientes: `docs/eda/problemas_y_decisiones.md`.

Toda cifra de este informe se calculó en los notebooks y está en `docs/eda/metricas/<fase>.json`; entre corchetes, `fase: clave`. Las explicaciones de dominio se presentan como **hipótesis**: no se verificaron con fuentes externas ni se citan referencias.

---

## Resumen ejecutivo

1. **Datos íntegros, con problemas de origen.**
   - El panel está completo: 30 485 filas = 65 distritos × 469 semanas, sin nulos ni duplicados [fase1: `n_filas`]. Reproduce sus fuentes sin pérdidas.
   - Los problemas están en el origen: una regla de calendario que diverge de la semana epidemiológica desde fines de 2025 [fase1: `primera_semana_regla_pipeline_difiere_mmwr`], un cambio de fuente en 2025, un salto de población entre 2017 y 2018 y la sociodemografía interpolada hacia 2025.
2. **Objetivo difícil de modelar.** Tiene 77.93 % de ceros y varianza/media de 360.1 [fase2: `pct_ceros`, `varianza_sobre_media`]. Tres años calendario (2017, 2023 y 2024) concentran el 89.6 % de los casos [fase2: `pct_casos_2017_2023_2024`], y 5 distritos suman la mitad [fase2: `distritos_para_50pct_casos`].
3. **La propia historia es una línea base exigente.** Repetir lo observado 4 semanas antes ya logra F1 = 0.735 para la marca de brote ilustrativa D1 [fase3: `binaria_D1`]. El valor agregado de un modelo está en los **arranques** de brote, que la persistencia no anticipa por construcción.
4. **Los vecinos se asocian con los arranques.** A igual actividad regional, tener un vecino con brote 4 semanas antes se asocia con una probabilidad de arranque 2.82 veces mayor (IC95 % 1.87-4.29) [fase4: `rr_mh_vecino_con_D1_t_menos_4`, `rr_mh_ic95_bootstrap_temporadas`]. Es una asociación; su capacidad predictiva debe medirse en el modelado.
5. **El clima aporta poco más allá de la persistencia.** La correlación cruda con la temperatura es sobre todo calendario. Solo la humedad y la precipitación muestran una asociación robusta (Spearman 0.285 y 0.273 en la ventana de rezagos 4-8) [fase5: `robustez_ventana_4_8`], y su señal más allá de los casos de t − 4 es pequeña [fase5: `corr_parcial_v48_controlando_casos_t4`].
6. **La sociodemografía es casi un solo eje urbano.** Ese eje explica el 61.3 % de la varianza de las 15 fracciones [fase6: `varianza_explicada_cp`]. Su relación con la incidencia es sobre todo la separación frío/cálido; dentro de la zona cálida es débil y no robusta [fase6: `cp1_rho_por_definicion_de_zona`].

---

## Hallazgos por fase

### Fase 1 — Integridad y calidad
- No hay valores imposibles ni violaciones de las 13 reglas físicas y de consistencia evaluadas [fase1: `violaciones_reglas_consistencia`].
- `lluvia_total_mm` duplica a `precip_total_mm` [fase1: `pares_columnas_identicas`].
- Las fracciones sociodemográficas son la recta entre 2017 y 2025 [fase1: `max_desvio_recta_fracciones`]. La población salta +6.8 % (mediana) entre 2017 y 2018 [fase1: `crec_pob_2018_mediana_pct`].
- 8 distritos comparten series climáticas idénticas, total o parcialmente, con un vecino [fase1: `n_distritos_en_pares_clima_identico`].
- Los extremos climáticos no son valores aislados: el 88.6 % de las semanas de humedad extrema cae en 2017 o 2023 [fase1: `hum_extremas_pct_en_2017_2023`].
- Los ceros del Excel significan "sin notificación", y tres distritos nunca aparecen en él [fase1: `distritos_nunca_en_excel`].

### Fase 2 — Variable objetivo
- La tasa y el conteo ordenan distinto a los distritos: solo 3 del top 10 coinciden [fase2: `top10_coinciden_casos_y_tasa`].
- Las cuatro definiciones candidatas de brote dan entre 2.48 % (D4, aumento sostenido) y 17.12 % (D3, canal endémico) de semanas positivas [fase2: `definiciones`].
- El canal endémico está en 0 en el 73.9 % de las distrito-semanas y, en la práctica, se reduce a "≥ 1 caso" [fase2: `D3_pct_distrito_semanas_con_canal_en_cero`].
- El Excel contiene temporadas grandes antes de 2017, no usadas en el panel [fase2: `excel_historia_anios_mas_de_5000_casos`].

### Fase 3 — Dinámica temporal
- Hay un ciclo anual con valle en la semana 35 [fase3: `semana_valle`]. Los brotes de 2023 y 2024 están conectados: entre sus picos nunca hay menos de 141 casos por semana [fase3: `min_casos_regionales_semanales_entre_picos_2023_2024`].
- Hay tres regímenes: brote 2017, silencio 2018-2020 y un nivel basal alto en 2021-2024 [fase3: `mediana_casos_regionales_sem35_52_por_anio`].
- Autocorrelación dentro de cada distrito, quitando el nivel de cada temporada: 0.643 en el rezago 4 y 0.29 en el 8 [fase3: `acf_distrital_sin_nivel_temporada_mediana_rezagos_1_4_8`].
- 3 de 10 temporadas tienen menos de 50 semanas positivas (D1) [fase3: `temporadas_con_menos_de_umbral_D1`].

### Fase 4 — Estructura espacial
- I de Moran de la incidencia acumulada: 0.693 en toda la región y 0.333 solo en la costa [fase4: `moran`].
- Domina una señal regional común. La sincronía local es débil con todos los distritos activos (Mantel p = 0.072), pero se ve con claridad al excluir los 7 distritos de actividad casi continua (rho −0.395) [fase4: `mantel_residual_vs_distancia`, `mantel_residual_vs_distancia_sin_continuos`].
- No hay una dirección de propagación estable entre temporadas [fase4: `propagacion`].
- Asociación de los vecinos con los arranques: ver el resumen ejecutivo.

### Fase 5 — Clima y casos
- El ciclo del clima costero está adelantado unas 9 semanas respecto del de casos [fase5: `centro_estacional_semana_costa`, `centro_estacional_semana_casos`].
- La temperatura media pierde su asociación al quitar el calendario (0.332 → 0.02) [fase5: `mejor_rezago_ge_4`].
- Humedad y precipitación son las únicas con un IC que excluye el 0 [fase5: `variables_ic95_excluye_0`].
- La "forma" de la relación clima-casos es sobre todo la diferencia entre años de brote y años tranquilos. Dentro de una temporada, solo la humedad muestra un gradiente claro [fase5: `forma_rezago6`].
- El clima de las semanas previas no distingue de forma robusta a los arranques [fase5: `arranques_variables_ic95_excluye_0`].

### Fase 6 — Sociodemografía
- 20 pares de fracciones tienen |rho| ≥ 0.85 [fase6: `pares_abs_rho_ge_0_85`].
- Correlación del eje urbano con la incidencia: 0.727 con todos los distritos y 0.277 en la costa cálida, con un IC que incluye el 0 [fase6: `spearman_con_log_incidencia`, `cp1_rho_por_definicion_de_zona`].
- Es inestable entre temporadas [fase6: `cp1_vs_incidencia_por_temporada_costa`].
- La variabilidad entre distritos es muy superior a la de Poisson, pero compatible con un modelo sobredisperso [fase6: `pct_distritos_costa_fuera_998_ajustado_sobredispersion`].

---

## Decisiones recomendadas para el feature engineering y el modelado

La tabla completa (17 decisiones priorizadas A/B/C) está en `notebooks/16_eda_sintesis.ipynb` [fase7: `tabla_decisiones`]. Las de prioridad A:

1. **Línea base y métricas:** comparar todo modelo contra la persistencia a 4 semanas, con métricas por temporada y aparte en arranques.
2. **Validación:** origen móvil por temporada (corte en la semana 35), nunca partición aleatoria, con un margen de al menos horizonte + rezago máximo entre entrenamiento y prueba.
3. **Objetivo:** conteo con la población como exposición (con un modelo apto para ceros y sobredispersión), o una marca binaria de brote. La definición (nivel o arranque) se elige con el asesor.
4. **Predictores de casos:** rezagos de 4-5 semanas más resúmenes del nivel reciente; nunca rezagos menores que el horizonte.
5. **Vecinos:** estado rezagado (≥ 4 semanas) de los distritos vecinos.
6. **Datos:** corregir el calendario antes de actualizar a 2026 y decidir el tratamiento de 2025.

De prioridad B (selección; la lista completa está en la tabla):
- Anomalías rezagadas de humedad y precipitación (climatología calculada solo con entrenamiento).
- Descartar la temperatura cruda como señal climática.
- Sociodemografía como a lo sumo un eje fijado en 2017.
- Confirmar la fuente de la población antes de usar tasas.

## Riesgos

- **Fuga de información:** rezagos menores que el horizonte; climatologías, perfiles, percentiles o escaladores calculados con todo el periodo; sociodemografía interpolada; población proyectada; partición aleatoria.
- **Dependencia de 2-3 temporadas de brote.**
- **Subregistro posible en 2025.**
- **Sobredispersión y desbalance de clases** (D1: 13.37 % de positivos; D4: 2.48 %) [fase7: `cifras_clave`].

## Limitaciones del EDA

- Relaciones ecológicas, entre distritos; nada se concluye sobre personas.
- Asociaciones, no causas: El Niño costero y los mecanismos del vector son hipótesis de conocimiento general, no verificadas aquí.
- Las anomalías climáticas y varias medidas descriptivas usan todo el periodo, así que no deben reutilizarse tal cual en el modelo.
- Los intervalos por bootstrap remuestrean pocas temporadas o distritos no independientes, así que son aproximados.
- El dataset no trae serotipo, control vectorial, movilidad, altitud ni polígonos distritales.
