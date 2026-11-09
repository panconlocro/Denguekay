# R09 · Sensibilidad de la etiqueta de la V3

Fecha de propuesta: 2026-11-09 (America/Lima). Estado: aprobado para ejecución el 2026-11-09. Este plan se preparó después del cierre de la V3 y de las comparaciones descriptivas anteriores, y antes de calcular los resultados predictivos de A y B.

## Pregunta y escenarios

Evaluar si la comparación entre la V3 con temperatura y su referencia pareada sin clima se mantiene al variar la definición de semana distrital elevada. El criterio principal de esta comparación es el Brier de la probabilidad calibrada por temporada y horizonte. El alcance se limita a las dos configuraciones seleccionadas bajo la definición principal.

| Escenario | Multiplicador | Años previos de la misma semana | Mínimo de casos |
|---|---:|---:|---:|
| Principal | 1,5 DE | 5 | 2 |
| A | 2,0 DE | 5 | 2 |
| B | 1,5 DE | 3 | 2 |

La V3 utiliza un canal estacional por distrito. El manual OMS de 2016 describe el canal tradicional de cinco años con +2 DE, que motiva A. Benedum et al. emplearon 1,5 DE con la referencia de entrenamiento de cada localidad. La aplicación por distrito y misma semana y el mínimo de dos casos se documentan como decisiones del proyecto. B comprueba si la comparación depende de incluir los dos años más antiguos de la referencia. La formulación de A y B cambia un parámetro por vez. [OMS, 2016, sección 3.2.4](https://iris.who.int/bitstream/handle/10665/250240/9789241549738-eng.pdf?sequence=1). [Benedum et al., 2020](https://journals.plos.org/plosntds/article?id=10.1371/journal.pntd.0008710).

## Inventario verificado antes del análisis

- Clon independiente en `/Users/kanyewest/Documents/Denguekay-R09`, rama `exp/outbreak-label-sensitivity`, desde `model/v3` (`6894012a3b87ea63f8b0d3198eab0719abeef43c`). Configuración `CONFIG_V3`, L + 5a + d3, trial 191. Comparador L + 5a sin d3 con los mismos hiperparámetros.
- Entorno `.venv` con Python 3.12.13 en macOS arm64. Instalación con `requirements.txt` y `constraints.txt` del tag. `pip check` pasó. Se importaron NumPy 2.5.3, pandas 3.0.6, SciPy 1.18.1, scikit-learn 1.9.1 y XGBoost 3.4.1. La corrida archivada usó Windows y GPU, y este estudio reutiliza sus predicciones.
- Se verificaron los SHA-256 de `datos_v3.zip` y `predicciones_v3.zip` y de sus **332 archivos** contra el manifiesto del tag. Los conteos de filas con referencia en el manifiesto también coinciden. La copia de Downloads coincide en 328 de los 329 miembros del paquete de datos. El miembro restante, `models/experimentos/mejora_modelo/temporada_2026/chirps_prelim_diario_poligono.csv`, se obtuvo del Release junto con los otros insumos.
- Se usarán los archivos `predicciones_v3.csv.gz` y `predicciones_l5a_sin_clima.csv.gz` en `models/experimentos/mejora_modelo/v3/`. Cada uno contiene **975 000 filas**, 65 distritos, 20 bloques, 5 semillas y los horizontes 2, 3 y 4. Se verificaron las llaves únicas, `ubigeo` de seis dígitos, la presencia de las columnas requeridas, la dispersión positiva y la coincidencia de llaves, fechas de origen, casos observados y persistencia entre los dos archivos.
- La referencia de resultados es `research/06_model_improvement/docs/metricas/v3.json`. Los comparadores de otras familias quedan fuera de este análisis. La comprobación hasta aquí se limita a los insumos y el entorno. La reproducción de las métricas del principal abre la fase siguiente.

## Serie de casos y muestra

Usar la historia congelada del Release. Reconstruir la serie con la lógica de `phase0_diagnosis.long_case_series` y la extensión de `phase_2026.inputs_2026`. La historia previa al integrado empieza en 2000. La serie usa el integrado desde 2017, la semana 53 de 2025 de la Sala y las semanas de 2026 admitidas por el protocolo. Conservar la regla documentada de las últimas dos semanas provisionales de 2026 y el tratamiento de las ausencias en la historia cubierta. Si falta cobertura de un año requerido, detener la comprobación y documentar el dato faltante.

Calcular los umbrales con `future_outbreak_threshold` sobre la serie de casos por distrito, con DE muestral (`ddof=1`), la semana 53 sumada a la 52 para la referencia y años estrictamente anteriores al objetivo. Mantener el inicio común de la serie de etiquetas en 2005 para el análisis de episodios. La regla observada es `casos_Dengue > umbral` y `casos_Dengue >= 2`.

Preservar los bloques y filas del Release. Usar el mismo soporte para principal, A y B. Las temporadas de decisión de referencia son 2010, 2015, 2016, 2022, 2023 y 2026. Reportar 2024 como contraste, `calendario_2025` como sensibilidad y `posterior_2026` por separado. Las semanas sin predicción entre agosto y diciembre de 2024 permanecen fuera de la evaluación. Conservar el solape documentado entre `calendario_2025` y `temporada_2026` y su efecto en la calibración de `posterior_2026`. Identificarlo al informar este último bloque. La evaluación es retrospectiva y usa los archivos congelados.

## Puerta de reproducción del escenario principal

1. Unir las etiquetas reconstruidas a ambas tablas usando `ubigeo` y la semana objetivo, con unión muchos a uno. Exigir cero filas sin pareja y coincidencia exacta de los casos observados y de la etiqueta. Verificar las llaves por variante, semilla, bloque, horizonte, distrito y semana objetivo, preservando el identificador de bloque en los solapes.
2. Comparar el umbral reconstruido con el del Release con diferencia absoluta máxima de `1e-9` casos. Reconstruir la probabilidad cruda con `negative_binomial_probability(mu_modelo, alpha_usada, umbral_brote_casos)`. Exigir diferencia absoluta máxima de `1e-9` en la probabilidad cruda.
3. Recalcular Brier y *average precision* desde las probabilidades guardadas y contrastar todas las celdas con `v3.json` mediante el criterio de `phase_v3_close.verify_metrics` (`1e-12`, ninguna celda sin pareja). Replicar la calibración cronológica con el principal reconstruido. Propuesta de tolerancia de reproducción del reajuste en macOS: `1e-6` de diferencia absoluta máxima para probabilidades calibradas y métricas por celda, con coincidencia exacta de filas y positivos de calibración y de celdas sin calibrar. Informar las diferencias observadas.
4. Si falla alguna comprobación, documentar los bloques y las causas antes de calcular A y B. Cualquier cambio a estas tolerancias requiere una enmienda del protocolo.

## Cálculo tras aprobar el protocolo

1. Aplicar A y B a la misma serie y a las mismas filas. Conservar `mu_modelo`, `alpha_usada`, `w_mezcla`, `conteo_publicado`, persistencia, semillas, orígenes y predicciones fuera de muestra del Release. Las métricas de conteo usarán `conteo_publicado` y los mismos conteos observados.
2. Recalcular la probabilidad cruda NB2 con `mu_modelo`, `alpha_usada` y el nuevo `k = max(2, floor(umbral) + 1)`. Para evaluar el conteo, usar `conteo_publicado` como `casos_predichos`. Son salidas distintas de la V3.
3. Ajustar Platt por escenario, variante y semilla con `protocol.calibrate_chronologically` por bloque y horizonte. Usar solo predicciones fuera de muestra de bloques anteriores por fecha de inicio cuyas semanas objetivo hayan cerrado hasta el primer origen de ese horizonte en el bloque. Aplicar el recorte `[1e-6, 1 − 1e-6]` y la misma regresión logística del tag. Registrar filas y positivos de calibración. `temporada_2008` queda sin calibrar. Cualquier bloque que carezca de ambas clases se reporta sin probabilidad calibrada.
4. Aplicar `p ≥ 0,50` y reconstruir la alerta de persistencia con la definición de cada escenario. Para la antelación, reconstruir episodios con las etiquetas de cada escenario y usar el emparejamiento original. Reportar el tamaño del denominador y la convención de anticipación del protocolo. Usar las semillas 17, 29, 41, 53 y 67 y los horizontes 2, 3 y 4. Para la guarda de antelación que usa la semilla 17, reproducir esa misma convención.
5. Reportar por escenario, modelo, bloque y horizonte el número de positivos, semanas que cambian de etiqueta, Brier, *average precision*, F1, precisión, recall a 0,50 y antelación. Conservar los resultados por semilla y resumir con mediana. Comprobar igualdad de `mu_modelo`, `conteo_publicado` y métricas de conteo entre escenarios. Indicar las celdas sin calibración o sin denominador para una métrica.

## Lectura propuesta de cambios materiales

Comparar V3 y L + 5a dentro de cada escenario. Por celda de horizonte y temporada, calcular `ΔBrier = mediana(V3) − mediana(L + 5a)`. La tolerancia de empate `T` será el mayor rango entre semillas de los dos modelos en esa celda y escenario, siguiendo `protocol.tie_threshold`. Una diferencia menor que `−T` favorece a la V3, una mayor que `T` la desfavorece y el resto se clasifica como empate. Mostrar también las diferencias numéricas y la prevalencia de cada escenario.

Considerar material una inversión de favorable a desfavorable o viceversa en una temporada de decisión, o un cambio del veredicto por horizonte al aplicar `SEASON_2026` con sus guardas. Registrar también las transiciones hacia o desde empate. Si el nuevo número de positivos de `temporada_2026` cae por debajo de 30 para un horizonte, aplicar la regla de cinco temporadas prevista en el protocolo y mostrar aparte las seis celdas para distinguir un cambio de comparación de un cambio de cobertura. La tolerancia entre semillas es una regla de lectura, no un intervalo de confianza.

Entregar una tabla de los tres escenarios, el control de reproducción, los resultados por semilla, una interpretación para el manuscrito y el reporte de ejecución. Usar `research/07_outbreak_label_sensitivity/code/` y `tests/` para la implementación tras la aprobación, y `docs/metricas/` para cifras y trazabilidad. Conservar la V3 y sus predicciones de referencia como entradas. Registrar el análisis según la guía de MLflow del repositorio.

La revisión del equipo debe aprobar los escenarios, la regla de cambio material y las tolerancias de reproducción antes de pasar a los cálculos. Los resultados describirán la robustez de la V3 ya elegida. La selección de una nueva arquitectura bajo otras definiciones queda fuera del alcance de R09.
