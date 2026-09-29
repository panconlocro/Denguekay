# Problemas de datos y decisiones pendientes — EDA Denguekay

Documento único que reúne todo lo detectado en las fases 1-6 del EDA. **Nada de esto se corrigió**: cada punto trae la evidencia, el impacto y una propuesta; Rosa decide qué hacer y cuándo.

Toda cifra está en `docs/eda/metricas/<fase>.json`; entre corchetes va `fase: clave`. El detalle de cada punto está en `docs/eda/hallazgos.md`.

---

## 1. Problemas de datos

| # | Problema | Evidencia | Impacto | Propuesta | Dónde se corrige |
|---|---|---|---|---|---|
| P1 | La regla de calendario del pipeline (`isocalendar()` de domingo + 3) diverge de la semana epidemiológica MMWR | Diverge desde la semana del 2025-12-28 y quedan fuera 3 casos de 2025-S53 [fase1: `primera_semana_regla_pipeline_difiere_mmwr`, `sala_casos_fuera_del_panel`]. Se repite en tramos futuros [fase1: `inicios_tramos_divergencia_pipeline_mmwr_hasta_2040`] | Hoy mínimo. Al actualizar a 2026, casos y clima quedarían desalineados una semana | Usar la regla MMWR (ver `semana_epi_mmwr()` en `src/eda/calidad.py`) e incorporar 2025-S53. Confirmar antes el calendario oficial de la Sala | `src/processing/agregacion_semanal.py`, `src/validation/expectations_integrado.py`, `src/update_dataset_module.py` |
| P2 | 2025 viene de otra fuente (Sala Situacional) y puede tener subregistro | 1 114 casos en 2025 [fase1: `casos_panel_2025`]; no se ve una temporada ese año [fase2: `temporadas`]. La documentación de extracción reporta una discrepancia sin resolver con otro panel (cifra no verificable en el repo) | 2025 no es comparable con los años previos. Afecta la validación | Mantener la advertencia hasta aclarar con DIRESA o la fuente alternativa. Ver decisión D1 | Fuente externa; `src/processing/epi_sala.py` |
| P3 | Salto de población entre 2017 y 2018 | Mediana +6.8 % en 2017→2018 frente a +0.67 %/año después [fase1: `crec_pob_2018_mediana_pct`, `crec_pob_2019_2025_mediana_pct`] | La tasa de 2017 no es comparable con la de 2023; la razón 2023/2017 pasa de 1.55 a 1.68 según qué población se use [fase2: `razon_2023_sobre_2017_pob_propia`, `razon_2023_sobre_2017_pob_2018`] | Documentar la fuente de cada año (¿censo vs proyección?) y, si son distintas, homogeneizar | `src/processing/socio_interpolacion.py` |
| P4 | `lluvia_total_mm` es idéntica a `precip_total_mm` | Único par de columnas idénticas [fase1: `pares_columnas_identicas`] | Variable duplicada | Conservar solo `precip_total_mm` | `src/processing/agregacion_semanal.py` o feature engineering |
| P5 | Los ceros de 2017-2024 son "sin notificación"; tres distritos nunca aparecen en el Excel, pero la cobertura marca todo como verificado | 0 filas con cero en el Excel [fase1: `excel_filas_con_cero_casos`]; Lagunas, Montero y Sicchez nunca aparecen [fase1: `distritos_nunca_en_excel`]; las 30 485 filas figuran como `verified` [fase1: `cobertura_fuentes`] | No se distingue un cero real de uno por falta de reporte | Que `.coverage.csv` distinga "cero notificado" de "sin registro". Ver decisión D2 | `src/update_dataset_module.py`, `src/validation/expectations_integrado.py` |
| P6 | Las fracciones sociodemográficas de 2018-2024 son interpolación hacia 2025, y la población de 2018+ probablemente es proyección, hipótesis de la fase 1 (fuga de información) | Desvío máximo respecto de la recta 2017→2025 = 1.1e-16 [fase1: `max_desvio_recta_fracciones`] | Usarlas como serie mete información futura en años pasados | Usar un año observado fijo, anterior al periodo de prueba (2017), y revisar qué información usa la proyección de población | Feature engineering (y documentar en `socio_interpolacion.py`) |
| P7 | El orden de los distritos cambia mucho entre 2017 y 2025 en `agua_red` y `alumbrado_red` | Spearman 2017 vs 2025 < 0.8 [fase6: `variables_orden_distrital_inestable_rho_lt_0_8`, `cambio_2017_2025`]. En `mujeres` es esperable por su rango estrecho | Posible diferencia de fuente o de definición entre años | Revisar la fuente de cada año | `src/processing/socio_interpolacion.py`, Excel de bronze |
| P8 | Nombres de distrito inconsistentes | Sufijo artificial `Salitral_s`; tildes inconsistentes; dos `distrito_key` de meteo silver con espacios perdidos [fase1: `distritos_con_sufijo_en_nombre`, `distrito_key_meteo_silver_distinta_del_integrado`] | Sin impacto en los cruces actuales; confunde en figuras y reportes | Normalizar los nombres desde `data/reference/catalogo_ubigeos_piura.csv` | Pipeline de nombres (`src/utils/keys.py` / processing) |

## 2. Limitaciones del dataset (no son errores, pero condicionan el modelo)

| # | Limitación | Evidencia | Consecuencia |
|---|---|---|---|
| L1 | Clima de baja resolución | 8 distritos comparten series climáticas idénticas con un vecino [fase1: `n_distritos_en_pares_clima_identico`] | Dentro de esos pares el clima no discrimina |
| L2 | Centroides poco representativos en zonas altas | El Carmen de la Frontera promedia 6.96 °C [fase1: `el_carmen_temp_media_promedio_c`] | El clima del centroide puede no ser el de la población |
| L3 | Sin polígonos ni altitud | Solo lat/lon; "costa/sierra" por provincia deja 5 distritos andinos en la costa [fase6: `costa_por_provincia_no_calidos`] | Vecindad solo por distancia; zona climática aproximada. Ver decisión D8 |
| L4 | Pocos brotes | El 89.6 % de los casos cae en 2017, 2023 y 2024 [fase2: `pct_casos_2017_2023_2024`] | Toda conclusión depende de 2-3 temporadas |

## 3. Decisiones pendientes para Rosa

| # | Decisión | Opciones | Recomendación del EDA (no vinculante) |
|---|---|---|---|
| D1 | Uso de 2025 | Excluir del entrenamiento / solo validar con advertencia / usar igual | Excluir del entrenamiento y, si se usa para validar, reportarlo aparte |
| D2 | Lagunas, Montero y Sicchez (sin registros en la fuente) | Excluir / mantener como "sin casos" | Mantener, marcados; reportar métricas con y sin ellos |
| D3 | Forma del objetivo | Conteo con exposición / tasa / log1p / binario | Conteo con la población como exposición (evita el ruido de las tasas pequeñas), o binario si se elige una definición de brote |
| D4 | Definición de brote y sus parámetros | Nivel (D1, D3 corregido) / arranque (D4); además, umbral, percentil, ventana, factor y duración mínima | Llevar ambas familias al asesor, con los parámetros a calibrar (los del EDA son ilustrativos). D3 tal como está equivale casi a "≥ 1 caso": el canal está en 0 en el 73.9 % [fase2: `D3_pct_distrito_semanas_con_canal_en_cero`] |
| D5 | Esquema de validación | Origen móvil por temporada / dejar una temporada afuera | Origen móvil por temporada, evaluando en 2022-2024, con margen de horizonte + rezago; nunca aleatorio |
| D6 | Variables climáticas | Solo humedad y precipitación / agregar temperatura mínima / todas | Humedad y precipitación (únicas con IC que excluye 0 [fase5: `variables_ic95_excluye_0`]); temperatura mínima opcional |
| D7 | Sociodemografía | CP1 fijado en 2017 / 2-3 variables / descartar | CP1 (o 2-3 variables) fijado en 2017, con expectativa baja; la asociación dentro de la zona cálida no es robusta [fase6: `cp1_rho_por_definicion_de_zona`] |
| D8 | Capas de referencia | Incorporar polígonos distritales y altitud / seguir con centroides | Solo si se quiere vecindad por contigüidad o una zona climática mejor definida |
| D9 | Distritos silenciosos | Modelo global / excluir / modelo aparte | Modelo global con el nivel propio del distrito; reportar métricas por grupo |
| D10 | Dónde eliminar `lluvia_total_mm` | Pipeline / feature engineering | Pipeline (una sola fuente de verdad) |

## 4. Preguntas para el asesor

1. **Anticipación:** ¿qué quiere anticipar el sistema, el nivel del brote o su arranque? Define la métrica principal, la definición de brote y sus parámetros (D4).
2. **Validación:** con solo tres temporadas útiles para evaluar, ¿basta el origen móvil por temporada, o conviene **ampliar el panel hacia atrás**? El Excel trae temporadas grandes antes de 2017 [fase2: `excel_historia_anios_mas_de_5000_casos`], pero faltaría la sociodemografía de esos años.
3. **Vecinos:** ¿es aceptable usar el estado rezagado de los vecinos como predictor, sabiendo que es una asociación y no una prueba de contagio [fase4: `rr_mh_vecino_con_D1_t_menos_4`]?
4. **Clima:** el clima aporta poco sobre la persistencia [fase5: `corr_parcial_v48_controlando_casos_t4`]. ¿El objetivo de la tesis admite un modelo donde el clima sea secundario?
5. **Sociodemografía:** ¿conviene mantenerla como rasgo estático (fijado en 2017) o descartarla?
6. **Calendario:** ¿la Sala Situacional usa oficialmente el calendario MMWR? El Excel histórico tiene una semana 53 en 2009, que no existe según MMWR [fase1: `anios_con_s53_en_excel_2000_2024`].

## 5. Preguntas para DIRESA o la fuente de datos

1. La discrepancia de casos de 2025 entre la Sala Situacional y el otro panel documentado.
2. La fuente de la población de 2017 frente a la de 2018-2025 (P3).
3. La fuente y definición de `agua_red` y `alumbrado_red` en 2017 y en 2025 (P7).
