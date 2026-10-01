# Corrección del calendario epidemiológico

## Decisión y alcance

El 1 de octubre de 2026 el equipo solicitó corregir la discrepancia entre
la numeración del pipeline y el helper MMWR. Se reutiliza el algoritmo
existente, ahora en `src/utils/calendario.py`: semanas domingo–sábado;
semana 1 con al menos cuatro días en el año nuevo. El import desde
`src/eda/calidad.py` sigue disponible para los notebooks anteriores.

La [definición MMWR de CDC](https://stacks.cdc.gov/view/cdc/22305) documenta
esta regla. La [publicación de DIRESA Tacna](https://www.gob.pe/institucion/regiontacna-diresa/informes-publicaciones/7654456-boletin-epidemiologico-semana-n-01-diresa-tacna)
identifica el 4–10 de enero de 2026 como semana 1, coherente con el helper.
Esta comprobación no reinterpreta las semanas del Excel anterior a 2017.

## Qué se corrigió

- `agregar_a_semanal()` mantiene los mismos domingos, agregaciones y filtro
  de semanas completas; calcula año y semana con MMWR, reemplazando ISO
  sobre el miércoles.
- `prepare_dataset()` exige esa misma relación entre fecha, año y semana.
  El actualizador hereda ambas reglas por sus imports existentes.
- `validar_panel()` y `preparar_gold()` rechazan etiquetas de calendario
  inconsistentes antes del EDA/feature engineering o del entrenamiento.
- Se corrigió una prueba del actualizador que aceptaba incorrectamente
  2026-S01 con inicio 2025-12-28; ahora usa 2026-01-04. La fixture de
  entrenamiento deja de numerar domingos con ISO.

Los notebooks 10, 16 y 17 y los informes anteriores conservan la evidencia
del defecto anterior a este cambio. La expresión ISO que incluyen para
comparar reglas es una referencia histórica, no la convención vigente.

## Repercusiones comprobadas y riesgos de una ampliación sin corregir

| Componente | Panel actual hasta 2025-12-21 | Efecto que habría tenido la regla anterior al ampliar |
|---|---|---|
| Integración de casos y clima | Ninguna fila tiene año/semana desplazados. | El cruce por UBIGEO/año/semana asociaría semanas distintas; 2026-S02 climática correspondería a 2026-S01 epidemiológica. |
| Calendario predictor | Seno y coseno reconstruidos coinciden con gold. | La posición estacional quedaría adelantada una semana en 2026; afecta a ambas variantes compactas seleccionadas. |
| Rezagos, medias y vecinos | Sin cambios: se ordenan por fechas semanales continuas. | Renumerar no modifica la distancia de los rezagos, pero un cruce previo incorrecto contaminaría los casos utilizados. |
| Clima y climatología | Features actuales coinciden con gold. | Las ventanas crudas conservarían sus fechas; las anomalías agruparían por una semana estacional incorrecta. |
| Etiqueta de brote | Los umbrales y las etiquetas reconstruidos coinciden. | La referencia de la misma semana en años anteriores se consultaría con una semana errónea; 2025-S53 perdería su tratamiento de referencia 52. |
| Demografía | Sin cambios en población o fracciones. | 2025-12-28 tomaría demografía de 2026 al quedar etiquetado con ese año. |
| Particiones y evaluación | Entrenamiento, evaluación y cortes de todos los bloques comprobados son idénticos antes/después. | Cambiarían la asignación anual y la frontera de temporadas basada en la semana 35. |
| Contrato temporal | Los orígenes conservan su separación exacta de 2 o 4 semanas. | La auditoría de fechas por sí sola no detectaría casos unidos a una fecha incorrecta por el cruce territorial/temporal. |

Estos efectos futuros se deducen de los cruces y funciones del código; no
son mediciones de desempeño de un modelo entrenado con datos de 2026.

La Sala conserva 65 registros de 2025-S53 con tres casos en total fuera
del integrado. El panel carece de esa semana climática completa. La
corrección de numeración no incorpora automáticamente esos registros:
requiere completar las entradas y generar una versión nueva. Ningún
archivo de `data/` fue modificado.

## Verificación ejecutada

Las cifras y huellas están en
[`metricas/correccion_calendario.json`](metricas/correccion_calendario.json).

- Se comprobaron 30 485 filas, 65 distritos y 469 semanas sin discrepancias
  de calendario en el panel actual.
- Se reconstruyeron en memoria etiquetas y todas las familias de gold
  para h=2 y h=4: 30 485 filas y 48 columnas por horizonte. Se cotejaron
  con los CSV persistidos (tolerancia numérica de 1e-12). Las huellas de
  ambas reconstrucciones son idénticas antes/después de la corrección.
- Los bloques de temporadas 2021–2024 y calendario 2025 conservan
  exactamente sus filas, valores y cortes para ambos horizontes.
- Los hashes de 18 archivos de entradas, manifiesto, métricas publicadas
  y predicciones locales se mantienen iguales.
- `.venv/bin/python -m unittest tests.test_calendario tests.test_modeling_train tests.test_update_dataset_module tests.test_eda_carga tests.test_eda_calidad`:
  43 pruebas, OK.
- `.venv/bin/python -m unittest discover -s tests`: 160 pruebas, OK,
  8,434 segundos.
- `.venv/bin/python -m src.validation.calidad_gx`: silver 107/107,
  gold h2 92/92 y gold h4 92/92.

No se reentrenaron los experimentos históricos ni se sustituyeron sus
artefactos. La invariancia de sus matrices y particiones fue comprobada;
la diferencia entre artefactos de equipos distintos sigue siendo una
cuestión separada de este calendario.
