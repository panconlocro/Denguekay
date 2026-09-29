# Hallazgos del EDA — Denguekay (Hito 2, Data Understanding)

Cada cifra de este documento está en `docs/eda/metricas/<fase>.json` (entre corchetes, la clave) y sale de una celda ejecutada del notebook de la fase. Etiquetas: **observación** (calculado), **hipótesis** (explicación no verificada), **conclusión** (se sigue de lo calculado).

---

## Fase 1 — Integridad y calidad

Notebook: `notebooks/10_eda_integridad_calidad.ipynb` · Métricas: `docs/eda/metricas/fase1_integridad_calidad.json` · Figuras: `docs/eda/figuras/fase1_integridad_calidad/` · Revisión independiente (`revisor-eda`): aprobado con observaciones; todas las observaciones quedaron incorporadas.

**Hallazgo 1 — El panel está completo, es consistente y reproduce sus fuentes**
- **Evidencia:**
  - Tamaño: 30 485 filas × 35 columnas [`n_filas`, `n_columnas`] = 65 distritos × 469 semanas [`n_distritos`, `semanas_por_distrito`], del 2017-01-01 al 2025-12-21.
  - Estructura: 0 nulos, 0 filas duplicadas, 0 llaves repetidas y 0 filas que no empiecen en domingo [`nulos_totales`, `filas_duplicadas`, `llaves_duplicadas`, `filas_no_domingo`]. Ninguna de las 13 reglas físicas y de consistencia se viola [`violaciones_reglas_consistencia`].
  - Casos: 2017-2024 coincide con el Excel silver fila por fila (0 diferencias en 6 300 filas con casos) [`excel_filas_con_casos_distintos`, `excel_filas_piura_2017_2024`] y 2025 coincide con la Sala (0 diferencias) [`sala_filas_con_casos_distintos_al_panel`].
  - Clima y sociodemografía: coinciden con meteo silver y socio silver (0 filas sin par y 0 celdas distintas) [`meteo_silver_*`, `socio_silver_*`].
  - `validate_complete()` acepta el panel [`validate_complete`].
- **Interpretación:** observación. La integración reproduce sus fuentes sin pérdidas dentro del calendario del panel.
- **Implicación para el modelado:** no hay que imputar ni reparar valores. El panel está balanceado, así que los rezagos se pueden calcular por distrito sin huecos.
- **Confianza:** alta (chequeo exhaustivo, sin muestreo).
- **Pendiente / pregunta:** ninguno.

**Hallazgo 2 — La regla de calendario del pipeline diverge de la semana epidemiológica MMWR desde el 2025-12-28**
- **Evidencia:**
  - El calendario del panel coincide con la regla MMWR en todas las filas (0 desacuerdos) [`filas_calendario_distinto_mmwr`].
  - La regla del pipeline (`isocalendar()` de domingo + 3 días) difiere de MMWR desde la semana del 2025-12-28 [`primera_semana_regla_pipeline_difiere_mmwr`], en 53 semanas entre 2017 y 2026 [`semanas_2017_2026_regla_pipeline_difiere_mmwr`]: etiqueta esa semana como 2026-S01 en vez de 2025-S53 y desplaza todo 2026 una semana. La divergencia se repite en tramos que empiezan el 2031-12-28 y el 2036-12-28 [`inicios_tramos_divergencia_pipeline_mmwr_hasta_2040`].
  - La Sala trae una semana 53 en 2025 que quedó fuera del panel: 65 filas con 3 casos [`sala_filas_fuera_del_panel`, `sala_casos_fuera_del_panel`]. En 62 de esos distritos la semana no figura como observada en el gráfico de la Sala [`sala_semana53_distritos_no_observados`].
- **Interpretación:** el desfase es una observación. Que la Sala use MMWR es una **hipótesis**:
  - A favor: trae la semana 53 de 2025.
  - En contra: el Excel histórico de MINSA tiene semana 53 en 2009, año que según MMWR tiene 52 semanas [`anios_con_s53_en_excel_2000_2024`, `anios_con_s53_segun_mmwr_2000_2024`]. Para 2017-2025, en cambio, ambos coinciden.
- **Implicación para el modelado:** hoy el impacto es mínimo (3 casos). Pero una actualización a 2026 con la regla actual desalinearía casos y clima una semana, lo que metería ruido sistemático en los rezagos.
- **Confianza:** alta en el desfase; media en el calendario que usa MINSA.
- **Pendiente / pregunta:** confirmar el calendario oficial de la Sala antes de actualizar a 2026.

**Hallazgo 3 — `lluvia_total_mm` duplica a `precip_total_mm`**
- **Evidencia:** son el único par de columnas idénticas en todas las filas [`pares_columnas_identicas`].
- **Interpretación:** observación. **Hipótesis** sobre la causa: en la zona no hay precipitación sólida, así que la lluvia es toda la precipitación.
- **Implicación para el modelado:** usar una sola de las dos. Recomendación: `precip_total_mm`.
- **Confianza:** alta.
- **Pendiente / pregunta:** decidir si se elimina en el pipeline o en el feature engineering.

**Hallazgo 4 — La sociodemografía es casi toda interpolación, y la población tiene un quiebre 2017→2018**
- **Evidencia:**
  - Las 15 `fraccion_*` coinciden con la recta 2017→2025 (desvío máximo 1.1e-16) [`max_desvio_recta_fracciones`].
  - La población crece 6.8 % de mediana entre 2017 y 2018 (rango 1.27–13.09 %) y 0.67 % de mediana anual entre 2019 y 2025 [`crec_pob_2018_mediana_pct`, `crec_pob_2018_min_pct`, `crec_pob_2018_max_pct`, `crec_pob_2019_2025_mediana_pct`].
  - En los 65 distritos el salto de 2018 supera cualquier crecimiento anual posterior [`distritos_crec_2018_mayor_que_todo_2019_2025`]. En 63 supera también cualquier caída posterior en magnitud; las excepciones son Chalaco y Sicchez [`distritos_crec_2018_mayor_que_toda_variacion_abs_2019_2025`, `distritos_excepcion_magnitud`].
  - A nivel regional: 1 856 809 → 2 013 517 habitantes (+8.44 %) [`pob_regional_2017`, `pob_regional_2018`, `crec_pob_regional_2018_pct`]. Figura `01_poblacion_indice_2017.png`.
- **Interpretación:** el quiebre es una observación. **Hipótesis:** 2017 es conteo censal y 2018 en adelante son proyecciones que corrigen la omisión censal.
- **Implicación para el modelado:**
  - (a) Las fracciones solo aportan diferencias entre distritos, no dinámica temporal (de 2018 a 2024 son artefacto).
  - (b) El denominador de 2017 no es comparable con el de 2018+. **Si** la proyección es el denominador correcto, la tasa por 100 000 hab. de 2017 sobreestimaría ese brote frente al de 2023. Si lo correcto es el censo, el sesgo va al revés.
- **Confianza:** alta en el quiebre; baja en la causa.
- **Pendiente / pregunta:** confirmar la fuente de `poblacion` por año antes de definir el objetivo como tasa (fase 2).

**Hallazgo 5 — Cuatro pares de distritos cercanos comparten series climáticas idénticas**
- **Evidencia:**
  - Amotape – Tamarindo y Bellavista de la Unión – Rinconada Llicuar son idénticos en 7 de las 8 variables climáticas (todas salvo `et0_total`).
  - Los Órganos – Máncora y Montero – Sicchez son idénticos en 3 (precipitación, viento y radiación) [`pares_distritos_serie_climatica_identica`, `n_variables_identicas_por_par`].
  - Los centroides de cada par están a entre 4.9 y 10.6 km [`distancia_km_pares_clima_identico`]. Figura `02_pares_clima_identico.png`.
- **Interpretación:** observación. **Hipótesis:** los centroides caen en la misma celda de la rejilla del reanálisis, y las variables que difieren se ajustan según la elevación de cada coordenada.
- **Implicación para el modelado:** dentro de cada par, el clima (total o parcialmente) no discrimina entre los dos distritos. Es una limitación de resolución, no un error.
- **Confianza:** alta en la observación; media en la causa.
- **Pendiente / pregunta:** ninguno (se documenta como limitación).

**Hallazgo 6 — Los extremos climáticos no son valores aislados: coinciden con 2017 y 2023 o reflejan la representatividad del centroide**
- **Evidencia:**
  - Temperatura: ninguna semana tiene |z robusto| > 5 dentro de su distrito [`temp_semanas_extremas_z5`].
  - Concentración en 2017 y 2023: esos dos años son el 22.2 % de las filas del panel [`pct_filas_panel_en_2017_2023`], pero concentran el 88.6 % de las 184 semanas de humedad extrema y el 88.3 % de las semanas con precipitación por encima del p99 de cada distrito [`hum_extremas_total`, `hum_extremas_pct_en_2017_2023`, `precip_p99_pct_en_2017_2023`] (figura `03_extremos_por_anio.png`).
  - Máximo de precipitación: 706.3 mm en Salitral (Morropón, 200406) la semana del 2017-03-05. Esa semana la mediana regional fue 256.1 mm y 15 distritos superaron 400 mm; el segundo valor del mismo distrito es 583.9 mm [`precip_max_*`] (figura `04_precip_maxima_contexto.png`).
  - Mínimo de `temp_media`: 4.53 °C en El Carmen de la Frontera (2021-08-01), con z = −2.94 dentro de su distrito. El distrito promedia 6.96 °C, tiene 24 semanas con `temp_min` bajo 0 °C, el mínimo global de `temp_min` (−2.3 °C) y 13 semanas de humedad extrema, y suma 5 casos [`temp_media_min_*`, `el_carmen_*`, `temp_min_global_*`] (figura `05_temp_minima_contexto.png`).
- **Interpretación:** la concentración y el contexto son observaciones. **Hipótesis:** 2017 y 2023 fueron años de El Niño costero; el centroide de El Carmen cae en una zona alta, no representativa de sus centros poblados (el dataset no trae altitud para verificarlo). Open-Meteo es un reanálisis, no una medición: que no sean valores aislados no prueba que sean fieles al terreno.
- **Implicación para el modelado:** no recortar ni "limpiar" estos extremos. Como coinciden con los dos brotes, la señal climática va a depender de 2017 y 2023, y la fase 5 necesita la sensibilidad "dejando un año afuera".
- **Confianza:** alta en que no son valores aislados; baja en la explicación causal.
- **Pendiente / pregunta:** ninguno para esta fase.

**Hallazgo 7 — Los ceros son "sin notificación", 2025 viene de otra fuente y tres distritos nunca aparecen en el Excel**
- **Evidencia:**
  - El Excel solo trae filas con casos (0 filas con cero) [`excel_filas_con_cero_casos`]. Los 20 805 ceros de 2017-2024 [`panel_filas_cero_2017_2024`] se generan por ausencia de registro.
  - Lagunas, Montero y Sicchez nunca aparecen en el Excel [`distritos_nunca_en_excel`], pero el `.coverage.csv` marca las 30 485 filas como `verified` [`cobertura_fuentes`].
  - 2025 suma 1 114 casos, todos de la Sala [`casos_panel_2025`].
  - Empalme: la media semanal pasa de 72.9 (últimas 8 semanas de 2024) a 45.9 (primeras 8 de 2025). La razón, 0.63, está dentro del rango de las transiciones entre años de la misma fuente (0.27 a 7.17) [`media_semanal_ultimas8_2024`, `media_semanal_primeras8_2025`, `razon_media_8sem_inicio_sobre_fin_por_transicion`]. Figura `06_casos_regionales_por_fuente.png`.
- **Interpretación:** observación. Esta prueba de empalme casi no discrimina, porque las transiciones entre años varían muchísimo; con estos datos no se puede ni atribuir ni descartar un efecto de la ruptura de fuente. **Hipótesis:** 2025 tiene subregistro (el diccionario documenta una discrepancia sin resolver con otro panel, que no se puede verificar con este repo).
- **Implicación para el modelado:**
  - (a) Los ceros de Lagunas, Montero y Sicchez no se pueden distinguir de falta de reporte.
  - (b) 2025 no debería usarse como año comparable sin advertencia; eso condiciona el esquema de validación temporal.
- **Confianza:** alta en la procedencia; baja en la magnitud de un posible subregistro.
- **Pendiente / pregunta:** tratamiento de 2025 y de los tres distritos (decisión de Rosa y el asesor).

### Lo que este análisis NO permite concluir
- Que 2025 esté completo o incompleto: solo que viene de otra fuente y que su empalme no es anómalo respecto de otras transiciones de año (prueba de bajo poder).
- Que los extremos de 2017 y 2023 se deban a El Niño, ni que el clima "cause" los brotes.
- Que la población de 2017 esté mal: solo que no es comparable con la de 2018+ sin conocer su fuente.
- Que los ceros de 2017-2024 sean ausencia real de casos: son ausencia de notificación en el Excel.
- Que el clima de Open-Meteo refleje fielmente el de cada distrito: es un reanálisis sobre centroides.

### Problemas y propuestas de corrección (Rosa decide; nada se corrigió)
1. **Calendario epidemiológico** (`src/processing/agregacion_semanal.py`, `src/validation/expectations_integrado.py`, `src/update_dataset_module.py`): reemplazar `isocalendar()` de domingo + 3 días por la regla MMWR (semana 1 = la que contiene el primer miércoles del año; ver `semana_epi_mmwr()` en `src/eda/calidad.py`) e incorporar 2025-S53. Es obligatorio antes de extender el panel a 2026, y de nuevo relevante en 2031.
2. **Columna redundante:** eliminar `lluvia_total_mm` en la agregación semanal, o ignorarla en el feature engineering.
3. **Población:** documentar la fuente de 2017 frente a la de 2018-2025 en `socio_interpolacion.py`. Si se confirma que son fuentes distintas, decidir si se homogeniza (por ejemplo, usar la proyección también para 2017).
4. **Cobertura:** que `.coverage.csv` distinga "cero notificado" de "sin registro en la fuente" (hoy todo es `verified`), al menos para los distritos que nunca aparecen en el Excel.
5. **2025:** mantener la advertencia de subregistro hasta resolver la discrepancia con DIRESA o con la fuente alternativa.
6. **Nombres de distrito** (sin impacto en los cruces actuales):
   - Un sufijo artificial (`Salitral_s`) [`distritos_con_sufijo_en_nombre`].
   - Tildes inconsistentes (por ejemplo "Los Organos", "Mancora" frente a "Pariñas", "El Tallán").
   - Dos `distrito_key` de meteo silver con espacios perdidos [`distrito_key_meteo_silver_distinta_del_integrado`].
   - Propuesta: normalizar los nombres desde `data/reference/catalogo_ubigeos_piura.csv` en el pipeline.

---

## Fase 2 — Variable objetivo

Notebook: `notebooks/11_eda_variable_objetivo.ipynb` · Métricas: `docs/eda/metricas/fase2_variable_objetivo.json` · Figuras: `docs/eda/figuras/fase2_variable_objetivo/`

Supuestos mientras Rosa decide (vienen de la fase 1): 2025 se incluye marcado aparte, con cifras con y sin 2025; las tasas usan la `poblacion` del dataset, con sensibilidad para 2017; Lagunas, Montero y Sicchez se mantienen.

**Hallazgo 1 — El objetivo tiene inflación de ceros, cola larga y sobredispersión que persiste dentro de cada distrito-año**
- **Evidencia:**
  - Distribución: 77.93 % de ceros (76.76 % sin 2025); media 5.7, mediana 0, máximo 2 084; varianza/media = 360.1 [`pct_ceros`, `pct_ceros_sin_2025`, `media`, `mediana`, `maximo`, `varianza_sobre_media`].
  - Entre las semanas con casos: mediana 4, p99 387 [`mediana_casos_positivos`, `p90_p99_casos_positivos`].
  - Dentro de los 359 distrito-años con casos: varianza/media mediana 2.16, el 74.7 % tiene varianza > media y el 26.5 % tiene varianza/media > 10 [`distrito_anios_con_casos`, `vm_mediana_distrito_anio`, `pct_distrito_anios_sobredispersos`, `pct_distrito_anios_vm_mayor_10`].
  - Figuras `01_distribucion_casos.png` y `02_sobredispersion_distrito_anio.png`.
- **Interpretación:** observación: la variabilidad no se explica solo por mezclar distritos y años. Cautela: dentro de un distrito-año la media cambia con la estacionalidad, así que var > media también aparecería con un Poisson de media variable. Esto muestra heterogeneidad, no necesariamente sobredispersión condicional.
- **Implicación para el modelado:** **hipótesis** a verificar con los residuos de un modelo con estacionalidad: un Poisson simple sería insuficiente. Candidatos: binomial negativa, modelos con inflación de ceros, objetivo `log1p` o clasificación binaria de brote. Las métricas sobre conteos crudos estarían dominadas por unas pocas semanas extremas.
- **Confianza:** alta en la descripción; media en la necesidad de un modelo sobredisperso.
- **Pendiente / pregunta:** elegir la forma del objetivo (depende de la definición de brote).

**Hallazgo 2 — Conteo y tasa ordenan distinto a los distritos, y la comparación 2017 vs 2023 depende de la población de 2017**
- **Evidencia:**
  - Ranking de distritos: Spearman casos vs incidencia acumulada = 0.831, pero solo 3 del top 10 por casos siguen en el top 10 por tasa [`spearman_casos_vs_incidencia_distritos`, `top10_coinciden_casos_y_tasa`]. San Juan de Bigote encabeza por tasa (19 110 por 100 000 hab. acumulados) y es el puesto 21 por casos [`top10_por_tasa`] (figura `03_conteo_vs_tasa.png`).
  - Incidencia regional: 2 384.5 por 100 000 hab. en 2017 y 3 688.6 en 2023 [`incidencia_regional_anual`]. La razón 2023/2017 es 1.55 con la población propia de 2017 y 1.68 si se usa la de 2018 [`razon_2023_sobre_2017_pob_propia`, `razon_2023_sobre_2017_pob_2018`].
- **Interpretación:** observación.
- **Implicación para el modelado:** con conteos dominan las ciudades grandes; con tasas pesan los distritos pequeños y ruidosos. Opción intermedia (recomendación): conteo con la población como exposición (offset). Toda definición basada en tasa hereda la duda de 2017.
- **Confianza:** alta en los órdenes; la magnitud de 2017 depende de la fuente de población (fase 1, hallazgo 4).
- **Pendiente / pregunta:** la fuente de la población de 2017 (pendiente de la fase 1).

**Hallazgo 3 — Pocos distritos concentran la epidemia; Ayabaca y Huancabamba aportan muy pocos casos**
- **Evidencia:**
  - Concentración: 5 distritos suman el 50 % de los casos y 12 el 80 % [`distritos_para_50pct_casos`, `distritos_para_80pct_casos`].
  - Distritos silenciosos: 15 tienen casos en menos del 5 % de sus semanas, incluidos los 3 siempre en cero [`distritos_menos_5pct_semanas_con_casos`, `distritos_siempre_cero`].
  - Provincias (en conteo): Piura aporta el 52.4 % de los casos; Ayabaca + Huancabamba, el 0.7 % [`pct_casos_provincia`, `pct_casos_sierra_ayabaca_huancabamba`].
  - En tasa esas dos provincias no son despreciables: Suyo acumula 4 995 casos por 100 000 hab., frente a una mediana de 7 365 en las otras 6 provincias [`incidencia_acumulada_max_ayabaca_huancabamba`, `mediana_incidencia_acumulada_resto_provincias`]. "Sierra" es una aproximación por provincia: el dataset no trae altitud.
  - Figuras `04_concentracion_distritos.png` y `05_mapa_calor_distrito_semana.png`.
- **Interpretación:** observación. El mapa de calor sugiere que los episodios coinciden en el tiempo entre distritos de costa (**hipótesis**: un factor regional común; se cuantifica en la fase 4).
- **Implicación para el modelado:** en los distritos silenciosos el modelo solo aprenderá a predecir cero. Hay que decidir si se modelan aparte, se excluyen o se dejan en un modelo global con indicadores espaciales.
- **Confianza:** alta.
- **Pendiente / pregunta:** tratamiento de los distritos silenciosos (junto con la fase 4).

**Hallazgo 4 — En 2017-2025 hay solo tres temporadas grandes, y el Excel trae temporadas previas no usadas**
- **Evidencia:**
  - Temporadas grandes: solo 2017, 2023 y 2024 tienen ≥ 10 % de los casos del periodo. Juntas suman el 89.6 % (2017 + 2023 = 71.1 %) [`anios_con_10pct_o_mas_de_los_casos`, `pct_casos_2017_2023_2024`, `pct_casos_2017_2023`]. Sus picos regionales caen entre las semanas 14 y 20 [`semana_pico_rango_anios_grandes`].
  - En 2022 y 2024 los casos ya superan el 10 % del pico desde la semana 1, y 2025 tiene su máximo en la semana 4 con 58 casos [`temporadas`].
  - Historia previa: el Excel silver trae 2000-2016, con más de 5 000 casos en 2001, 2010, 2015 y 2016 (20 042 en 2015) [`excel_historia_anios_mas_de_5000_casos`, `excel_historia_casos_por_anio`]. Solo 54 de los 65 distritos tienen algún caso antes de 2017 [`excel_historia_distritos_distintos`, `excel_historia_distritos_ausentes`]. Figura `06_casos_anuales_con_historia.png`.
- **Interpretación:** observación. **Hipótesis:** las temporadas de 2022 y 2024 empiezan el año anterior (se verifica en la fase 3); la ausencia de algunos distritos antes de 2017 puede deberse a cambios de ubigeo o a subregistro.
- **Implicación para el modelado:**
  - El número efectivo de brotes para aprender y validar es de unas 3 temporadas, así que los folds "dejando un año afuera" serán muy desiguales.
  - Extender el panel hacia atrás sumaría temporadas independientes: casos del Excel más clima de Open-Meteo. Faltaría la sociodemografía de esos años, y habría que extrapolarla.
  - 2025 no muestra una temporada visible.
- **Confianza:** alta en las cifras; media en la utilidad de la historia previa (calidad y cobertura desconocidas).
- **Pendiente / pregunta:** ¿se amplía el alcance temporal del panel? (asesor).

**Hallazgo 5 — Las cuatro definiciones candidatas de brote dan desbalances de 1:5 a 1:39 y dependen de los mismos cuatro años**
- **Evidencia** (parámetros ilustrativos, no calibrados; detalle en `definiciones` y `D1_barrido_umbral`):

  | Definición | % positivos | Negativos por positivo | Episodios | % episodios de 1 semana | % casos cubiertos |
  |---|---|---|---|---|---|
  | D1: tasa ≥ 10/100 000 | 13.37 | 6.5 | 805 | 55.8 | 95.6 |
  | D2: > p90 del distrito | 6.96 | 13.4 | 516 | 54.1 | 82.0 |
  | D3: canal endémico | 17.12 | 4.8 | 1 176 | 58.6 | 96.9 |
  | D4: aumento sostenido | 2.48 | 39.4 | 153 | 0.0 | 39.2 |

  - D1 va de 20.78 % (umbral 1) a 3.51 % de positivos (umbral 100), perdiendo distritos en el camino.
  - D3 tiene el canal histórico en 0 (Q3 de los 5 años previos = 0) en el 73.9 % de las distrito-semanas, y de ahí sale el 65.2 % de sus positivos [`D3_pct_distrito_semanas_con_canal_en_cero`, `D3_pct_positivos_con_canal_en_cero`].
  - El 0 % de episodios de 1 semana de D4 es por construcción (exige ≥ 3 semanas). Desde el inicio de un episodio de D4 hasta el máximo del distrito en las 26 semanas siguientes pasan 7 semanas de mediana (p25-p75: 3-10); en el 51.6 % de los episodios ese máximo llega después de que el episodio termina [`D4_semanas_inicio_a_pico_mediana`, `D4_semanas_inicio_a_pico_p25_p75`, `D4_pct_episodios_pico_despues_del_episodio`].
  - En D1-D4, 2017, 2022, 2023 y 2024 aportan entre el 90.7 % y el 96.3 % de los positivos [`pct_positivos_en_2017_2022_2023_2024`] (figura `07_definiciones_positivos_por_anio.png`).
- **Interpretación:** observación.
  - D2 usa información futura si el percentil se calcula con todo el periodo.
  - D3 no usa el futuro, pero como en la mayoría de las distrito-semanas el canal es 0, en la práctica se parece mucho a "≥ 1 caso". Para que discrimine habría que, por ejemplo, exigir un mínimo de casos, usar media + 2 DE o agrupar semanas vecinas (alternativas no evaluadas).
  - D4 marca la fase de subida: sus episodios suelen empezar semanas antes del máximo local, aunque en cerca de la mitad de los casos el máximo llega cuando el episodio ya terminó.
  - La serie distrital es ruidosa: más de la mitad de los episodios de D1-D3 dura una sola semana.
- **Implicación para el modelado:** habrá desbalance de moderado a severo, así que hay que usar PR-AUC y recall de brotes, no exactitud. La definición fija si el modelo predice nivel (D1-D3) o arranque (D4). **Hipótesis de diseño:** para un aviso con 4 semanas, el arranque es lo más útil, pero también es la clase más rara. Suavizar episodios o exigir un mínimo de casos se decide en feature engineering.
- **Confianza:** alta en las cifras dados los parámetros; los parámetros son ilustrativos.
- **Pendiente / pregunta:** qué familia de definición llevar al asesor, y con qué parámetros.

### Lo que este análisis NO permite concluir
- Cuál definición de brote es "la correcta": depende del uso que se le quiera dar al aviso, y eso se decide con el asesor y el usuario final.
- Que 2025 tenga poca transmisión: puede ser subregistro (fase 1).
- Que la historia 2000-2016 sea comparable con 2017-2024 (cobertura de distritos y calidad no verificadas).
- Que la sincronía entre distritos implique contagio entre ellos (fase 4).

### Problemas y propuestas de corrección
- No se encontraron problemas nuevos de datos. Se confirma la dependencia del denominador de 2017 (fase 1, propuesta 3).

---

## Fase 3 — Dinámica temporal

Notebook: `notebooks/12_eda_temporal.ipynb` · Métricas: `docs/eda/metricas/fase3_temporal.json` · Figuras: `docs/eda/figuras/fase3_temporal/` · Revisión independiente (`revisor-eda`): aprobado con observaciones; todas quedaron incorporadas.

Supuestos de trabajo: los mismos de la fase 2. La marca binaria D1 (tasa ≥ 10 por 100 000 hab.) se usa solo para ilustrar; no es una elección.

**Hallazgo 1 — Hay un ciclo anual con valle hacia la semana 35, pero 2023 y 2024 son un brote continuo**
- **Evidencia:**
  - La mediana del perfil normalizado (semanas 1-52) toca fondo en la semana 35 y culmina en la 20 [`semana_valle`, `semana_mediana_perfil_maximo`]. En los años grandes el pico cae en las semanas 18 (2017), 20 (2023) y 14 (2024) [`semana_pico_anios_grandes`]. En el 92.3 % de las semanas 27-52 la mediana está bajo el 10 % del máximo anual [`pct_semanas_27_52_bajo_10pct_del_maximo_mediana`], así que la semana exacta del corte es una convención (tabla de sensibilidad 30-40 en [`sensibilidad_corte_semanas_30_40`]).
  - 2023 no se apaga: con cualquier corte entre las semanas 30 y 40, esa semana de 2023 tiene entre 270 y 1 367 casos regionales, y entre los picos de 2023 y 2024 la serie nunca baja de 141 casos por semana [`casos_regionales_2023_en_corte_min_max_sem30_40`, `min_casos_regionales_semanales_entre_picos_2023_2024`].
  - Con temporadas de la semana 35 a la 34, la temporada 2024 suma 36 160 casos (5 098 de fines de 2023), frente a 32 246 del año calendario [`casos_2024_calendario_vs_temporada`, `casos_semanas_valle_a_52_2023`]. 2017 y 2026 quedan incompletas [`temporadas_incompletas`]. Figura `02_perfil_estacional.png`.
- **Interpretación:** observación.
- **Implicación para el modelado:**
  - Partir por temporada (valle a valle) reduce el reparto de un brote entre entrenamiento y prueba, pero no lo evita entre 2023 y 2024: hace falta un margen (gap) de al menos el horizonte más el rezago máximo, y declarar que esas temporadas no son independientes.
  - Cualquier perfil estacional debe calcularse solo con las temporadas de entrenamiento.
- **Confianza:** alta en el ciclo; media en la semana exacta del corte.
- **Pendiente / pregunta:** ninguno.

**Hallazgo 2 — Tres regímenes: brote 2017, silencio 2018-2020 y nivel basal alto 2021-2024 (2025 aparte)**
- **Evidencia:**
  - Mediana de casos regionales por semana en las semanas 35-52: 28 (2017); 1, 0.5 y 0.5 (2018-2020); 62.5, 31.5, 249 y 67 (2021-2024); 5.5 (2025) [`mediana_casos_regionales_sem35_52_por_anio`].
  - Estacionariedad sobre `log1p` regional: ADF p = 0.088 y KPSS p ≤ 0.01 [`adf_pvalor_log_regional`, `kpss_pvalor_log_regional`]. Ninguna apoya la estacionariedad; con dos grandes brotes, ambas tienen poco poder.
  - Series provinciales: Spearman de 0.51 a 0.86 entre ellas (mediana 0.65) [`spearman_entre_provincias_min_mediana_max`]. Figura `01_series_por_provincia.png`.
- **Interpretación:** observación. **Hipótesis:** el nivel basal alto desde 2021 refleja transmisión sostenida o cambios de notificación; el bajo nivel de 2025 puede ser real o subregistro (fase 1).
- **Implicación para el modelado:** normalizar o escalar con estadísticas de todo el periodo mezclaría regímenes y usaría información futura. El nivel reciente es información útil.
- **Confianza:** alta en la observación; baja en las causas.
- **Pendiente / pregunta:** ninguno.

**Hallazgo 3 — El rezago 4 es informativo; los rezagos 6-8 aportan sobre todo el nivel de la temporada**
- **Evidencia:**
  - ACF de `log1p` en el rezago 4, versión bruta: regional 0.936; mediana dentro de los 31 distritos activos 0.827 (p25-p75: 0.761-0.874) [`acf_regional_rezagos_1_4_8_13_26`, `n_distritos_activos`, `acf_distrital_mediana_rezagos_1_4_8`, `acf_distrital_rezago4_p25_p75`]. Quitar la estacionalidad no la reduce [`acf_*_desest_*`].
  - Restando a cada distrito su media por temporada (sin el nivel de la temporada), la mediana distrital es 0.643 en el rezago 4 y 0.29 en el rezago 8; la regional, 0.691 y 0.401 [`acf_distrital_sin_nivel_temporada_mediana_rezagos_1_4_8`, `acf_regional_sin_nivel_temporada_rezagos_1_4_8`].
  - Dentro de cada temporada completa, la ACF regional en el rezago 4 va de −0.082 (2019) a 0.859 (2023) [`acf_regional_rezago4_dentro_de_cada_temporada`].
  - La PACF regional es 0.976 en el rezago 1 y 0.396 en el 2 [`pacf_regional_rezagos_1_a_4`]. Figura `03_autocorrelacion.png`.
- **Interpretación:** observación. La ACF bruta está inflada por los cambios de nivel entre temporadas, porque la serie no es estacionaria. Las versiones sin estacionalidad y sin nivel usan medias de todo el periodo o de toda la temporada: sirven para describir, no para modelar.
- **Implicación para el modelado:** a horizonte 4, el primer rezago disponible es el 4, y es informativo aun dentro de la temporada. Los rezagos 6-8 aportan sobre todo el nivel. **Recomendación:** considerar el rezago 4-5 más resúmenes del nivel reciente conocido, en lugar de muchos rezagos individuales. Lo decide el feature engineering.
- **Confianza:** media (depende del régimen, y es casi nula en temporadas de silencio).
- **Pendiente / pregunta:** ninguno.

**Hallazgo 4 — La persistencia a 4 semanas es una línea base exigente; el valor agregado está en los arranques**
- **Evidencia:**
  - Error absoluto medio en `log1p`, sobre las mismas 27 105 filas: persistencia 0.208, estacional ingenua (misma semana del año anterior, alineada por año y semana) 0.525, siempre cero 0.403 [`mae_log1p_mismas_filas`].
  - Marca D1: la persistencia logra F1 = 0.735 (precisión 0.735, sensibilidad 0.736); la estacional, 0.337 [`binaria_D1`].
  - Por año, el F1 de la persistencia va de 0.6 a 0.808 en 2021-2024 y es 0 (2018), 0.143 (2020) y 0.175 (2025) en años con pocos positivos. En 2019 no está definido porque no hay positivos [`f1_D1_por_anio`] (figura `04_lineas_base_f1_por_anio.png`).
  - Hay 249 **arranques** (brote sin ningún brote en las 8 semanas previas del distrito), el 6.1 % de los positivos D1; la persistencia no puede anticiparlos por construcción [`arranques_n`, `arranques_pct_de_positivos`].
- **Interpretación:** observación.
- **Implicación para el modelado:** la vara mínima es la persistencia a 4 semanas, no el azar ni la estacionalidad. Conviene reportar aparte los arranques y los cambios de nivel, porque ahí podría aportar el clima (fase 5). Las métricas deben darse por temporada.
- **Confianza:** alta en las cifras dada la marca D1; cambian con otra definición de brote.
- **Pendiente / pregunta:** ¿qué quiere anticipar el usuario final: el nivel o el arranque?

**Hallazgo 5 — Pocas temporadas sirven como fold de prueba, y los primeros folds dependen de 2017**
- **Evidencia:**
  - Con temporadas de la semana 35 a la 34: 3 de 10 tienen menos de 50 positivos D1 (2019, 2020, 2026) y 6 de 10 menos de 50 positivos D4 [`temporadas_con_menos_de_umbral_D1`, `temporadas_con_menos_de_umbral_D4`, `umbral_positivos_fold_util`].
  - Las 3 temporadas con más positivos D1 concentran el 76.8 % [`pct_D1_positivos_en_3_temporadas_mayores`].
  - En el origen móvil con prueba en 2021, el 89.9 % de los positivos de entrenamiento viene de la temporada 2017, que está incompleta [`pct_positivos_entrenamiento_fold_2021_de_temporada_2017`, `folds`]. Figura `05_positivos_por_temporada.png`.
- **Interpretación:** observación. El umbral de 50 positivos es ilustrativo.
- **Implicación para el modelado** (propuesta, no decisión):
  1. Nunca partir aleatoriamente por filas.
  2. Esquema principal: origen móvil por temporada, evaluando en las temporadas con suficientes positivos (2022, 2023, 2024), con un margen de horizonte + rezago máximo y cada fold reportado por separado.
  3. Robustez: dejar una temporada afuera, con el mismo margen.
  4. 2025 como prueba, solo con la advertencia de subregistro.
- **Riesgos de fuga de información para el feature engineering:**
  - rezagos menores que el horizonte;
  - ventanas centradas;
  - climatologías, perfiles, percentiles (D2) o escaladores calculados con todo el periodo;
  - la sociodemografía interpolada, porque los valores de 2018-2024 se construyen con el dato de 2025;
  - la población proyectada.
- **Confianza:** alta.
- **Pendiente / pregunta:** esquema de validación, para acordar con el asesor.

### Lo que este análisis NO permite concluir
- Que un modelo vaya a superar a la persistencia: solo se dimensionó la vara.
- Por qué cambió el régimen desde 2021 (transmisión o notificación).
- Que la semana del pico sea predecible: con 3 temporadas grandes, 6 semanas de variación no alcanzan para generalizar.
- Que las pruebas de estacionariedad sean concluyentes, dado su bajo poder con dos grandes brotes.

### Problemas y propuestas de corrección
- No se encontraron problemas nuevos de datos. La interpolación de la sociodemografía hacia 2025 se agrega como riesgo de fuga de información (complementa la fase 1, hallazgo 4).

---

## Fase 4 — Estructura espacial

Notebook: `notebooks/13_eda_espacial.ipynb` · Métricas: `docs/eda/metricas/fase4_espacial.json` · Figuras: `docs/eda/figuras/fase4_espacial/` · Revisión independiente (`revisor-eda`): aprobado con observaciones; todas quedaron incorporadas.

Supuestos y limitaciones:
- Se mantienen los supuestos de la fase 3.
- Solo hay centroides (no polígonos ni altitud), así que la vecindad se define por distancia y "sierra" se aproxima por provincia (Ayabaca, Huancabamba).
- D1 (tasa ≥ 10 por 100 000 hab.) es ilustrativa.
- Vecinos = los 5 más cercanos; la mediana de la distancia a ellos es 19.7 km [`distancia_k_vecinos_km_mediana`].

**Hallazgo 1 — La incidencia se concentra en la costa, pero varía mucho dentro de cada provincia**
- **Evidencia:**
  - Incidencia acumulada 2017-2025 por provincia: de 9 919 por 100 000 hab. (Piura) a 330 (Huancabamba). La mediana distrital es 41 en la sierra y 7 365 en el resto [`incidencia_acumulada_por_provincia`, `incidencia_acumulada_mediana_sierra_vs_resto`].
  - La provincia explica el 67.1 % de la varianza de `log1p(incidencia)` entre distritos, pero casi todo es la división costa/sierra: entre los distritos de costa explica solo el 17.7 % [`r2_provincia_log_incidencia`, `r2_provincia_log_incidencia_solo_costa`].
  - Dentro de una provincia el rango es amplio (Morropón: de 121 a 19 110) [`incidencia_acumulada_rango_dentro_de_provincia`].
  - Figuras `01_mapa_incidencia_acumulada.png` y `02_incidencia_por_provincia.png`.
- **Interpretación:** observación.
- **Implicación para el modelado:** un modelo global necesita capturar el nivel propio de cada distrito (su historia o un indicador distrital); la provincia sola no basta.
- **Confianza:** alta.
- **Pendiente / pregunta:** ninguno.

**Hallazgo 2 — Hay autocorrelación espacial positiva, también dentro de la costa**
- **Evidencia:**
  - I de Moran de `log1p(incidencia acumulada)` con 5 vecinos: 0.693 (p ≤ 0.001, 999 permutaciones). Con k = 3, k = 8 e inverso de la distancia va de 0.272 a 0.756, siempre con p ≤ 0.001.
  - Solo en los distritos de costa: 0.333 (p = 0.002).
  - Por temporada: 2017 = 0.39 (temporada parcial, semanas 1-34), 2022 = 0.515, 2023 = 0.658, 2024 = 0.644, 2025 = 0.589 [`moran`].
- **Interpretación:** observación. **Hipótesis:** los distritos cercanos comparten condiciones (clima, conectividad, sistema de salud) o hay transmisión entre ellos; el I de Moran no distingue entre las dos.
- **Implicación para el modelado:** la información de los vecinos es candidata. Una validación que mezcle distritos vecinos en entrenamiento y prueba en la misma semana sería optimista: hay que partir por tiempo.
- **Confianza:** alta en la observación; baja en la causa.
- **Pendiente / pregunta:** ninguno.

**Hallazgo 3 — Domina una señal regional común; la sincronía local es débil y depende de los distritos de actividad continua**
- **Evidencia:**
  - Entre los 31 distritos activos (465 pares), la correlación de Spearman entre series semanales tiene mediana 0.62 en bruto y 0.06 sin la señal regional común [`n_distritos_activos`, `spearman_pares_bruta_p25_mediana_p75`, `spearman_pares_residual_p25_mediana_p75`].
  - Relación con la distancia (prueba de Mantel, 999 permutaciones de distritos):
    - en bruto: rho −0.466 (p ≤ 0.001);
    - sin la señal común: rho −0.101 (p = 0.072);
    - sin la señal común y sin los 7 distritos de actividad casi continua (Piura, Castilla, Catacaos, Tambo Grande, Veintiséis de Octubre, Chulucanas, Sullana): rho −0.395 (p ≤ 0.001), con mediana 0.21 a ≤ 30 km frente a 0.07 a mayor distancia [`mantel_bruta_vs_distancia`, `mantel_residual_vs_distancia`, `mantel_residual_vs_distancia_sin_continuos`, `distritos_actividad_continua_excluidos`, `residual_mediana_hasta_30km_vs_mas_sin_continuos`].
  - El agrupamiento jerárquico residual (4 grupos) no reproduce las provincias [`grupos_residuales_por_provincia`]. Figura `03_sincronia_distritos.png`.
- **Interpretación:** observación. Restar la media común hace que los distritos con actividad casi continua salgan correlacionados negativamente con el resto, en parte como artefacto. Por eso la sincronía local aparece con claridad solo al excluirlos.
- **Implicación para el modelado:** la señal regional común es la estructura principal. La información de los vecinos puede aportar, sobre todo en los distritos de actividad intermitente. Los grupos no son geográficos y serían frágiles con 31 distritos. Recomendación, no decisión.
- **Confianza:** baja-media (depende de cómo se quite la señal común y de qué distritos se incluyan).
- **Pendiente / pregunta:** ninguno.

**Hallazgo 4 — No hay una dirección de propagación estable en ninguna temporada**
- **Evidencia:**
  - Se usó el primer arranque de cada distrito en la temporada (D1 sin D1 en las 8 semanas previas). La correlación de Spearman entre la semana de arranque y la distancia a los primeros distritos en arrancar fue 0.459 en 2017 (p = 0.0037), 0.133 en 2023 (p = 0.35) y −0.249 en 2024 (p = 0.22) [`propagacion`].
  - Esas correlaciones cambian mucho según la referencia:
    - tomando como foco cada distrito que arrancó en las 2 primeras semanas con arranques, rho va de −0.036 a 0.442 en 2017 (6 focos), de −0.144 a 0.126 en 2023 y de −0.405 a 0.222 en 2024 (3 focos cada una);
    - usando el primer D1 en vez del primer arranque, rho es 0.272 (2017), 0.388 (2023, p = 0.0037) y 0.249 (2024) [`propagacion`]. En 2024 esos "primeros" son casi toda la costa (D1 heredado de 2023) y en 2023 pueden ser la continuación de 2022, así que esas correlaciones no son evidencia de propagación.
  - El valor de 2017 depende de la censura del borde: no puede haber arranques antes de la semana 9 del panel, y 18 distritos ya tenían D1 en las semanas 1-8.
  - En 2024, 43 distritos tenían D1 en las primeras 8 semanas de la temporada, heredado de 2023.
  - Entre el primer y el último arranque pasan semanas (2023: de la semana 3 a la 45 de la temporada). Figura `04_inicio_por_temporada.png`.
- **Interpretación:** observación. **Hipótesis:** ningún patrón de difusión desde un foco es robusto a la definición. Los arranques escalonados son compatibles con propagación local o con condiciones regionales o locales.
- **Implicación para el modelado:** no modelar una dirección fija de propagación. Lo aprovechable son los desfases entre los arranques de distintos distritos (hallazgo 5).
- **Confianza:** baja.
- **Pendiente / pregunta:** ninguno.

**Hallazgo 5 — Un vecino con brote 4 semanas antes se asocia con ~3 veces más probabilidad de arranque, a igual actividad regional**
- **Evidencia:**
  - Análisis principal (descriptivo; candidatas sin D1 propio en t − 1 a t − 8): 22 866 distrito-semanas candidatas y 249 arranques, el 51.8 % de ellos con algún vecino con D1 en t − 4 [`n_candidatas_arranque`, `n_arranques`, `pct_arranques_con_vecino_D1`].
  - Razón de riesgos: 7.23 cruda y 2.82 estratificada por la fracción regional de distritos con D1 en t − 4 (Mantel-Haenszel), con IC95 % de 1.87 a 4.29 por bootstrap de temporadas [`rr_crudo_vecino`, `rr_mh_vecino_con_D1_t_menos_4`, `rr_mh_ic95_bootstrap_temporadas`].
  - Dejando afuera cada temporada con ≥ 10 arranques, la RR va de 2.46 a 3.1 [`rr_mh_dejando_una_temporada_afuera`, `arranques_por_temporada_candidatas`].
  - Sensibilidad con información disponible al predecir (candidatas sin D1 propio en t − 4 a t − 11; desenlace D1 en t; 22 685 candidatas, 490 positivos): RR MH = 3.46 [`rr_mh_candidatas_definidas_en_t_menos_4`, `n_candidatas_y_positivos_definidas_en_t_menos_4`].
  - En el estrato de mayor actividad (> 15 %), la probabilidad de arranque es 6.5 % con vecino y 2.1 % sin vecino (88/1 358 frente a 29/1 361) [`arranques_estratificados`]. Figura `05_vecinos_y_arranques.png`.
- **Interpretación:** observación de asociación, no causal. El estrato regional controla la confusión solo en parte.
- **Implicación para el modelado:** el estado rezagado de los vecinos (con rezago ≥ horizonte) es el candidato más directo para anticipar arranques, justo donde la persistencia no ayuda (fase 3). Cómo definir los vecinos (k, radio, pesos, qué medida) se decide en feature engineering, usando solo el pasado.
- **Confianza:** media-alta (estable entre temporadas, con el IC y con la definición en t − 4; con decenas de arranques por estrato).
- **Pendiente / pregunta:** ninguno.

### Lo que este análisis NO permite concluir
- Que haya contagio entre distritos: la asociación con los vecinos también puede deberse a condiciones compartidas.
- Que exista una dirección de propagación típica, ni que el patrón de 2017 sea difusión (depende de la censura del borde del panel).
- Nada sobre áreas reales, altitud o conectividad, porque solo hay centroides.
- Que los grupos del agrupamiento sean estables.

### Problemas y propuestas de corrección
- No se encontraron problemas nuevos de datos. Limitación: sin polígonos distritales ni altitud en el repo. Si el equipo quisiera vecindad por contigüidad o separar costa/sierra por altitud, habría que incorporar esas capas de referencia (decisión de Rosa).

---

## Fase 5 — Clima y casos

Notebook: `notebooks/14_eda_clima.ipynb` · Métricas: `docs/eda/metricas/fase5_clima.json` · Figuras: `docs/eda/figuras/fase5_clima/` · Revisión independiente (`revisor-eda`): aprobado con observaciones; todas quedaron incorporadas.

Supuestos:
- Se analizan los 31 distritos activos (≥ 20 % de semanas con casos) [`n_distritos_activos`].
- Se omite `lluvia_total_mm` (idéntica a la precipitación).
- Cada relación se mira en tres versiones:
  - **bruta**;
  - **anomalía**: menos la climatología por distrito × semana epidemiológica, calculada con todos los años (solo descriptiva);
  - **intra-temporada**: la anomalía menos la media del distrito en esa temporada.
- D1 (tasa ≥ 10 por 100 000 hab.) es ilustrativa.

**Hallazgo 1 — El ciclo del clima costero está adelantado respecto del de casos; las correlaciones crudas son en gran parte calendario**
- **Evidencia:**
  - Centro estacional circular de la climatología costera: semana 9.2 (temperatura media), 9.6 (temperatura mínima) y 9.5 (precipitación), frente a 18.6 de los casos 2017-2025 [`centro_estacional_semana_costa`, `centro_estacional_semana_casos`].
  - La temperatura media costera es una meseta de 26.0-26.5 °C entre las semanas 4 y 13 [`rango_temp_media_climatologia_costa_sem_4_13`].
  - El pico regional de casos varía entre años: de la semana 10 a la 22 en 2017-2024, y en la semana 4 en 2025, año con otra fuente y posible subregistro [`semana_pico_regional_por_anio`]. Figura `01_estacionalidad_clima.png`.
  - Correlación de Spearman dentro de cada distrito (mediana; mejor rezago ≥ 4 de cada versión): temperatura media 0.332 en bruto frente a 0.02 como anomalía; temperatura máxima 0.233 frente a −0.019 [`mejor_rezago_ge_4`]. Figura `03_correlacion_cruzada.png`.
- **Interpretación:** observación. "Adelantado" describe un desfase de fase de unas 9 semanas en un ciclo anual, no un orden causal. **Hipótesis:** compatible con un efecto rezagado o con dos ciclos estacionales simplemente desfasados.
- **Implicación para el modelado:** `temp_media` y `temp_max` aportarían sobre todo calendario, que el modelo ya recibe por la semana epidemiológica. El clima debe entrar como anomalía respecto de una climatología calculada solo con entrenamiento.
- **Confianza:** alta.
- **Pendiente / pregunta:** ninguno.

**Hallazgo 2 — Hay tres bloques redundantes; la precipitación va por su cuenta**
- **Evidencia:** pares con |rho| ≥ 0.8 [`pares_redundantes_abs_rho_ge_0_8`]:
  - temperatura media con la máxima y con la mínima (0.93 y 0.95 en bruto; 0.75 y 0.75 como anomalías dentro del distrito);
  - humedad con ET0 (−0.80 y −0.81);
  - radiación con ET0 (0.79 y 0.82).
  - La precipitación no forma pares fuertes. Figura `02_redundancia_clima.png`.
- **Interpretación:** observación.
- **Implicación para el modelado:** un representante por bloque: humedad (que además resume a la ET0), precipitación y, con cautela, la temperatura mínima (su anomalía se relaciona solo 0.33 con la de la máxima).
- **Confianza:** alta.
- **Pendiente / pregunta:** ninguno.

**Hallazgo 3 — Solo la humedad y la precipitación tienen una asociación robusta con los casos**
- **Evidencia:** Spearman (mediana de los 31 distritos) entre la anomalía media de los rezagos 4-8 y la anomalía de `log1p(casos)` [`robustez_ventana_4_8`] (figura `06_robustez.png`):
  - **humedad:** 0.285; intra-temporada 0.345; sin 2017, 2023 o 2024 va de 0.246 a 0.352 (intra-temporada: de 0.298 a 0.352); IC95 % por bootstrap de temporadas 0.089-0.551;
  - **precipitación:** 0.273; intra-temporada 0.218; de 0.244 a 0.314 sin cada temporada grande (intra-temporada: de 0.182 a 0.242); IC95 % 0.069-0.509;
  - **temperatura mínima:** 0.168, pero −0.01 sin 2024, −0.035 en la versión intra-temporada sin 2023, e IC95 % de −0.257 a 0.496;
  - **temperatura media y máxima:** alrededor de 0, y negativas sin 2024;
  - **viento, radiación y ET0:** negativas en todas las versiones, pero con IC que incluye el 0.
  - Solo humedad y precipitación tienen un IC que excluye el 0 [`variables_ic95_excluye_0`].
  - Las temporadas 2017 y 2023 fueron más lluviosas y húmedas que el promedio en los distritos activos (anomalía de precipitación +28.69 y +8.84 mm/semana) [`anomalia_media_por_temporada`].
- **Interpretación:** observación.
  - La asociación también aparece **dentro** de cada temporada, así que no es solo "los años de brote fueron húmedos".
  - **Hipótesis:** condiciones más húmedas y lluviosas favorecen la transmisión con semanas de retraso; 2017 sería compatible con El Niño costero (conocimiento general, no verificado con datos del repo).
  - El "mejor rezago" está mal identificado porque las curvas son planas entre los rezagos 4 y 12.
- **Implicación para el modelado:** incluir humedad y precipitación como anomalías rezagadas y agregadas en una ventana (por ejemplo, 4-8 semanas), no como un rezago único. La temperatura mínima queda como candidata débil.
- **Confianza:** media (correlaciones moderadas; el IC se basa en 10 temporadas, 2 de ellas incompletas).
- **Pendiente / pregunta:** ninguno.

**Hallazgo 4 — El clima aporta poco más allá de la persistencia, aunque la humedad y la precipitación conservan algo**
- **Evidencia:**
  - La correlación entre la anomalía climática rezagada (4-12) y el **cambio** a 4 semanas, log1p(casos_t) − log1p(casos_{t−4}), no pasa de |0.074|, y en algunas variables cambia de signo según el rezago [`corr_cambio_max_abs_por_variable`, `corr_cambio_rezago_del_maximo`, `corr_anomalia_con_cambio_4_semanas`].
  - La correlación parcial de la ventana 4-8 con la anomalía de casos, **controlando por la anomalía de casos en t − 4** (mediana de distritos), es 0.161 en precipitación, 0.12 en humedad y 0.024 en temperatura mínima [`corr_parcial_v48_controlando_casos_t4`].
- **Interpretación:** observación. **Hipótesis:** buena parte de la asociación entre clima y nivel de casos ya se refleja en los casos de t − 4, porque los años húmedos son también los años con casos altos.
- **Implicación para el modelado:** el aporte del clima debe medirse comparando modelos con y sin clima contra la línea base de persistencia (fase 3). Humedad y precipitación muestran una señal parcial pequeña, sin intervalo ni sensibilidad por temporada, que habría que confirmar en el modelado; la temperatura mínima no la muestra.
- **Confianza:** media.
- **Pendiente / pregunta:** ninguno.

**Hallazgo 5 — La "forma" clima-casos es sobre todo la diferencia entre años de brote y años tranquilos; dentro de una temporada solo la humedad muestra un gradiente claro**
- **Evidencia:** deciles dentro de cada distrito, rezago 6 [`forma_rezago6`] (figura `04_forma_relacion.png`):
  - En **anomalía** (sin calendario), el decil superior salta en las cuatro variables. Por ejemplo, en temperatura mínima la anomalía de `log1p` es 1.126, pero −0.362 sin 2023 y 2024. Entre el 60.7 % y el 77.4 % de las semanas de ese decil caen en las temporadas 2017, 2023 o 2024, muy por encima del peso de esas temporadas en el panel. En humedad y precipitación el salto persiste sin 2023 y 2024 (0.336 y 0.155) y depende además de 2017. En temperatura mínima, sin 2023 y 2024 el decil 10 (−0.362) queda al nivel de los demás deciles.
  - La U de la humedad en valores brutos desaparece con anomalías.
  - En **intra-temporada** (sin calendario ni año), la humedad crece de −0.252 (decil 1) a 0.454 (decil 10). Sin 2023 y 2024 sigue creciendo en los deciles 1-9 (desde −0.283), aunque el decil 10 baja (0.075). Las temperaturas quedan planas salvo en los deciles extremos, y esos extremos dependen de 2023 y 2024.
  - La tabla de interacción intra-temporada cambia sobre todo con la humedad (columnas) y poco con la temperatura mínima (filas). La diferencia entre las celdas alto-alto y bajo-bajo es 0.646, y 0.191 sin 2023 y 2024 [`interaccion_diferencia_l_it_alto_alto_menos_bajo_bajo`, `interaccion_diferencia_l_it_alto_alto_menos_bajo_bajo_sin_2023_2024`]. Figura `05_interaccion_tmin_humedad.png`.
- **Interpretación:** observación. Los años de brote fueron anómalamente cálidos o húmedos, y eso produce la mayor parte de la "forma" vista en anomalías. Dentro de una temporada, semanas más húmedas que lo habitual preceden algo más de casos.
- **Implicación para el modelado:** si se usan umbrales o interacciones climáticas, deben validarse con folds que dejen afuera temporadas de brote; si no, el modelo aprendería "año de brote" y no clima. La señal intra-temporada más clara es la humedad. No hay evidencia robusta de una interacción temperatura × humedad.
- **Confianza:** media para la humedad; baja para temperatura e interacción.
- **Pendiente / pregunta:** ninguno.

**Hallazgo 6 — El clima de las semanas previas no distingue de forma robusta a los arranques**
- **Evidencia:**
  - Se tomaron 22 685 candidatas sin D1 en t − 4 a t − 11, de las cuales 490 tuvieron D1 en t [`candidatas_arranque_n_y_positivos`].
  - A igual actividad regional, la diferencia en la anomalía media de los rezagos 4-8 fue +0.487 DE en precipitación y +0.255 DE en humedad, pero **ningún IC95 % excluye el 0** [`arranques_diferencia_anomalia_clima_v48_en_sd`, `arranques_variables_ic95_excluye_0`]. Figura `07_clima_antes_de_arranques.png`.
- **Interpretación:** observación: dirección coherente con el hallazgo 3, sin evidencia firme.
- **Implicación para el modelado:** para anticipar arranques, el estado rezagado de los vecinos (fase 4) es un candidato más sólido que el clima. El aporte del clima en arranques debe medirse, no suponerse.
- **Confianza:** baja.
- **Pendiente / pregunta:** ninguno.

### Lo que este análisis NO permite concluir
- Que el clima cause los brotes, ni que El Niño costero explique 2017 y 2023.
- Un rezago óptimo único: las curvas son planas entre 4 y 12 semanas.
- Que el clima vaya a mejorar el pronóstico sobre la persistencia.
- Nada sobre la sierra, que se excluyó por falta de casos.
- Que las anomalías calculadas aquí puedan usarse tal cual en el modelo: su climatología usa todos los años.

### Problemas y propuestas de corrección
- No se encontraron problemas nuevos de datos. Se reitera que `lluvia_total_mm` es redundante (fase 1).

---

## Fase 6 — Sociodemografía

Notebook: `notebooks/15_eda_sociodemografico.ipynb` · Métricas: `docs/eda/metricas/fase6_sociodemografico.json` · Figuras: `docs/eda/figuras/fase6_sociodemografico/` · Revisión independiente (`revisor-eda`): aprobado con observaciones; todas quedaron incorporadas.

Diseño:
- Corte transversal de 65 distritos (47 de costa) [`n_distritos`, `n_distritos_costa`].
- Fracciones de 2017 (observadas) como principal y de 2025 como sensibilidad.
- Desenlace: `log1p` de la incidencia acumulada 2017-2024 por 100 000 hab. (sin 2025 por la ruptura de fuente).
- IC95 % por bootstrap de distritos (2 000 réplicas, semilla 42). Son optimistas porque los distritos no son independientes (fase 4).
- "Costa" por provincia, con sensibilidad por clima: distritos cálidos (temperatura media ≥ 20 °C, 44) y costa y cálidos a la vez (42) [`n_distritos_calidos_temp_ge_20`, `n_distritos_costa_y_calidos`]. La provincia deja cinco distritos andinos de Morropón en la costa y dos distritos cálidos de Ayabaca en la sierra [`costa_por_provincia_no_calidos`, `sierra_por_provincia_calidos`].

**Hallazgo 1 — Entre 2017 y 2025 algunas fracciones cambian mucho, y en tres de ellas incluso cambia el orden de los distritos**
- **Evidencia:**
  - Mediana de "sin seguro": de 0.157 (2017) a 0.018 (2025); de celular: de 0.707 a 0.922 [`cambio_2017_2025`, `cambio_mediano_sin_seguro`].
  - El orden distrital se mantiene (Spearman ≥ 0.9) solo en 8 de 15 fracciones; es inestable (< 0.8) en `mujeres`, `agua_red` y `alumbrado_red` [`variables_orden_distrital_estable_rho_ge_0_9`, `variables_orden_distrital_inestable_rho_lt_0_8`].
- **Interpretación:** observación. **Hipótesis:** la caída de "sin seguro" reflejaría la ampliación del seguro público; el cambio de orden en `agua_red` (y en menor medida en `alumbrado_red`) podría deberse a diferencias de fuente o de definición entre años. En `mujeres`, el cambio de orden es esperable, porque varía muy poco entre distritos. No es verificable con el repo.
- **Implicación para el modelado:** usar las fracciones como rasgos estáticos por distrito, **fijados en un año observado anterior al periodo de prueba (2017)**. Los valores interpolados de 2018-2024 se construyen con el dato de 2025, así que usan información futura (fuga), y son especialmente dudosos en las variables que cambiaron mucho.
- **Confianza:** alta en las cifras; baja en la causa.
- **Pendiente / pregunta:** sí; se consolida en el documento final de problemas.

**Hallazgo 2 — Las 15 fracciones son casi un solo eje urbano-socioeconómico**
- **Evidencia:**
  - 20 pares con |rho| ≥ 0.85 y 5 de 15 variables con VIF > 10 [`pares_abs_rho_ge_0_85`, `n_variables_vif_mayor_10`, `vif_2017`].
  - El primer componente principal explica el 61.3 % de la varianza, y el segundo el 12.4 % [`varianza_explicada_cp`].
  - CP1 opone refrigeradora, celular, desagüe, alumbrado y agua de red a piso de tierra, leña, paredes precarias, analfabetismo y ruralidad [`cargas_cp1`]. Figura `01_colinealidad.png`.
- **Interpretación:** observación.
- **Implicación para el modelado:** usar el puntaje de CP1 (calculado solo con entrenamiento) o 2-3 variables representativas, no las 15.
- **Confianza:** alta.
- **Pendiente / pregunta:** ninguno.

**Hallazgo 3 — La relación con la incidencia es sobre todo frío vs cálido; dentro de la zona cálida es débil y sensible a la definición**
- **Evidencia:**
  - Spearman de CP1 con `log1p(incidencia)`, con IC95 % [`spearman_con_log_incidencia`, `cp1_rho_por_definicion_de_zona`]:

    | Zona | rho | IC95 % |
    |---|---|---|
    | Todos los distritos | 0.727 | 0.546-0.838 |
    | Costa por provincia | 0.386 | 0.069-0.632 |
    | Distritos cálidos | 0.355 | 0.051-0.626 |
    | Costa y cálidos (42) | 0.277 | −0.061-0.56 |

  - La mediana de |rho| entre variables baja de 0.617 a 0.314 al quedarse con la costa [`mediana_abs_rho_todos_vs_costa`].
  - Qué variables tienen un IC que excluye el 0 también cambia con la definición de zona (por ejemplo, `mujeres` y `menores_15` entran con los distritos cálidos y `piso_tierra` sale) [`variables_ic_costa_excluye_0`, `variables_ic_calidos_excluye_0`].
  - Sin cada temporada grande en el desenlace acumulado, el rho de CP1 en la costa es 0.309 (sin 2017), 0.501 (sin 2023) y 0.295 (sin 2024) [`cp1_costa_rho_sin_cada_temporada`].
  - Figuras `02_correlacion_con_incidencia.png` y `03_cp1_vs_incidencia.png`.
- **Interpretación:** observación ecológica, entre distritos. **Hipótesis:** dentro de la zona cálida, más urbano podría significar más densidad o conectividad, o mejor acceso a diagnóstico y notificación, y no necesariamente más riesgo biológico.
- **Implicación para el modelado:** la sociodemografía aporta sobre todo el nivel del distrito, que el modelo también obtiene de su historia de casos. Puede ser útil en distritos con poca historia, con expectativas bajas.
- **Confianza:** baja (la asociación dentro de la zona cálida depende de la definición de zona y de las temporadas).
- **Pendiente / pregunta:** ninguno.

**Hallazgo 4 — La asociación del eje urbano con la incidencia varía mucho entre temporadas**
- **Evidencia:** en la costa, el Spearman de CP1 con la incidencia de cada temporada va de 0.062 (2022) a 0.458 (2019). La temporada 2017 es parcial (0.276). En las temporadas de silencio muchos distritos tienen cero casos (33 de 47 en 2019) [`cp1_vs_incidencia_por_temporada_costa`].
- **Interpretación:** observación. En las temporadas de silencio la correlación mide sobre todo quién registra algún caso, no la intensidad del brote.
- **Implicación para el modelado:** su utilidad como predictor fijo es limitada. El modelo debería apoyarse más en la historia reciente y en los vecinos.
- **Confianza:** media.
- **Pendiente / pregunta:** ninguno.

**Hallazgo 5 — La variabilidad entre distritos es muy superior a la de Poisson; el tamaño del distrito importa poco**
- **Evidencia:**
  - La tasa anual media de la costa es 1 174.3 por 100 000 hab., y el 97.9 % de los distritos de costa cae fuera de los límites del 99.8 % del embudo de Poisson [`tasa_anual_costa_por_100k`, `pct_distritos_costa_fuera_limite_998`].
  - Con los límites ajustados por sobredispersión (cuasi-Poisson, phi = 587.4), solo el 2.1 % cae fuera [`phi_sobredispersion_costa`, `pct_distritos_costa_fuera_998_ajustado_sobredispersion`].
  - Spearman entre población (2017) y `log1p(incidencia)`: 0.241 con todos los distritos y 0.171 solo en la costa [`spearman_poblacion_vs_log_incidencia`].
  - La población media va de 1 249 a 192 874 habitantes [`poblacion_media_min_mediana_max`]. Figura `04_embudo_poblacion.png`.
- **Interpretación:** observación. **Hipótesis:** las diferencias pueden reflejar riesgo, pero también notificación o acceso; el embudo no las distingue.
- **Implicación para el modelado:** si el objetivo es una tasa, conviene suavizar o ponderar los distritos pequeños, o bien modelar conteos con la población como exposición.
- **Confianza:** alta.
- **Pendiente / pregunta:** ninguno.

### Lo que este análisis NO permite concluir
- Relaciones a nivel de personas u hogares (falacia ecológica).
- Que las condiciones urbanas causen más dengue: pueden reflejar acceso a la notificación.
- Dinámica temporal sociodemográfica: solo hay dos años observados.
- Que los intervalos por bootstrap sean exactos, porque los distritos no son independientes.

### Problemas y propuestas de corrección
- Posible inconsistencia de fuente o definición entre 2017 y 2025 en `agua_red` (y en menor medida `alumbrado_red`): el orden de los distritos cambia mucho. Propuesta: revisar la fuente de cada año en `socio_interpolacion.py` y en el Excel de bronze.
- Fuga de información por la interpolación hacia 2025 (complementa la fase 1): usar un año observado fijo anterior al periodo de prueba.
- Ambos se consolidan en el documento final de problemas.

---

## Fase 7 — Síntesis

Notebook: `notebooks/16_eda_sintesis.ipynb` · Métricas: `docs/eda/metricas/fase7_sintesis.json` · Figura: `docs/eda/figuras/fase7_sintesis/01_panorama.png` · Informe: `docs/eda/informe_eda.md` · Problemas y decisiones: `docs/eda/problemas_y_decisiones.md`

Esta fase no agrega análisis nuevos. Lee las métricas de las fases 1-6 y las ordena en tres tablas:
- hallazgo → decisión: 17 filas, 8 de prioridad A, 6 de B y 3 de C [`tabla_decisiones`, `n_decisiones_por_prioridad`];
- variables a mantener, transformar o descartar [`variables`];
- riesgos [`riesgos`].

La mayoría de las cifras citadas en el informe y en el documento de problemas están copiadas en [`cifras_clave`]; todas llevan su clave de fase entre corchetes.

**Hallazgo de síntesis — Recomendación: apoyar el modelo sobre todo en la historia propia y en la de los vecinos, con clima y sociodemografía como secundarios**
- **Evidencia:**
  - Persistencia a 4 semanas: F1 = 0.735 (D1).
  - Vecinos con brote en t − 4: RR de arranque = 2.82 (IC95 % 1.87-4.29).
  - Clima: solo humedad y precipitación son robustas, con correlación parcial frente a los casos de t − 4 de 0.12 y 0.161.
  - Sociodemografía: el eje urbano tiene rho = 0.277 en la costa cálida, con un IC que incluye el 0.
  - [`cifras_clave`]. Figura `01_panorama.png`.
- **Interpretación:** recomendación de diseño (hipótesis). Se apoya en asociaciones de las fases 3-6, medidas con métricas distintas y no comparables entre sí, y no anticipa el desempeño de ningún modelo.
- **Implicación para el modelado:** priorizar la historia propia y la de los vecinos, el esquema de validación temporal y la definición del objetivo. Medir el aporte del clima y de la sociodemografía como agregados, frente a la persistencia.
- **Confianza:** media (con 2-3 temporadas de brote).
- **Pendiente / pregunta:** las decisiones D1-D10 y las preguntas al asesor de `docs/eda/problemas_y_decisiones.md`.

### Lo que este análisis NO permite concluir
- Qué desempeño tendrá el modelo, ni que vaya a superar a la persistencia.
- Causalidad de ningún factor.

### Problemas y propuestas de corrección
- Consolidados en `docs/eda/problemas_y_decisiones.md` (P1-P8, limitaciones L1-L4 y decisiones D1-D10).
