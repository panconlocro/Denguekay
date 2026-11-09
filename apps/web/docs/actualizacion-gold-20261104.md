# Regeneración de gold desde el notebook 10

El 04/11/2026 el usuario solicitó ejecutar `pipelines/notebooks/10_silver_to_gold.ipynb` para preparar
los datos de v2. Se ejecutó ese notebook con el Python de `.venv`, sin alterar su código ni las fuentes
de silver. Es una actualización del esquema y las variables desde el panel local existente, no una
descarga de semanas nuevas ni un entrenamiento/publicación del modelo.

## Respaldo y ejecución

Antes de escribir, se validó el integrado y se comprobaron los hashes del gold anterior contra su
manifiesto. Se conservaron h=2, h=4 y el manifiesto en `data/gold/respaldo_pre_b3/`, junto con
`SHA256SUMS.txt`. El CSV antiguo h=4 quedó en ese respaldo, no se eliminó; gold activo solo persiste h=2,
como indica el contrato actual. La v0 puede seguir leyendo sus archivos exactos del respaldo.

El notebook se ejecutó completo dos veces. Las dos corridas produjeron el mismo hash de gold. Las copias
ejecutadas se guardaron como artefactos locales, sin añadir salidas al notebook versionado:

- `models/serving/validacion_gold_20261104/10_silver_to_gold.ejecutado.ipynb`
- `models/serving/validacion_gold_20261104/10_silver_to_gold.repeticion.ipynb`
- `models/serving/validacion_gold_20261104/great_expectations.json`

Las carpetas de datos y artefactos están ignoradas por Git; el commit contiene la evidencia escrita,
no los CSV. Las fuentes y las fixtures de equivalencia no se modificaron.

## Resultados verificados

| Comprobación                          | Resultado                                                                                       |
| ------------------------------------- | ----------------------------------------------------------------------------------------------- |
| Silver antes de ejecutar              | 30 485 filas, 35 columnas, 65 distritos, 0 llaves duplicadas                                    |
| Periodo de semanas objetivo           | 01/01/2017 a 21/12/2025; no se incorporaron semanas de 2026                                     |
| Gold persistido                       | 30 485 filas, 20 columnas, 65 distritos, 469 semanas por distrito                               |
| Variables                             | base_6, A3 y las tres B3; `ubigeo` textual de seis dígitos                                      |
| Ventanas completas según el validador | 30 095 filas; 390 con ventanas iniciales incompletas esperadas                                  |
| Etiqueta                              | 3 002 semanas distritales positivas; regla histórica de cinco años + 1,5 DE y mínimo de 2 casos |
| Casos observados de 2025              | 1 114, conservados desde silver                                                                 |
| Great Expectations silver             | 107 de 107 expectativas aprobadas                                                               |
| Great Expectations gold               | 42 de 42 expectativas aprobadas                                                                 |
| Contrato de traspaso y respaldo       | `audit_handoff()` y `audit_gold_backup()` aprobados                                             |
| Pruebas B3 y contrato del modelo      | 13 ejecutadas: 12 aprobadas y 1 fallo de igualdad exacta con el respaldo, explicado abajo       |
| Segunda ejecución                     | CSV idéntico a la primera, verificado por SHA-256                                               |

La celda temporal del notebook confirmó para Piura, objetivo 2025-S52, origen de pronóstico cerrado el
13/12/2025 y rezagos de casos tomados de las semanas correspondientes de silver. Las tres celdas de
código terminaron sin errores. Los nulos iniciales se conservaron; no se rellenaron con ceros.

## Hashes

| Archivo                       | SHA-256                                                            |
| ----------------------------- | ------------------------------------------------------------------ |
| Nuevo gold h=2                | `b5773a3436680164b646143c40912bbcdd78f9118eb2e2b7fbd13d765ae9088e` |
| Silver integrado, sin cambios | `b04dc8c31793a08b417e5bafd9db101f4a18c9299686cb2dd4bfe2e5049b6c88` |
| Cobertura, sin cambios        | `e85f7e68b1b78ef97bb31aef56247d22b7eebac3cd0e28ba82e980641cacfb67` |
| Respaldo antiguo h=2          | `0ff49650f0fa1043bf2ae562d401c0d84307550108ef71d427ba9a20cbd475e3` |
| Respaldo antiguo h=4          | `f9fbed66572e8641eee82ce1a148562f5121cf8dbd111498f73a8aa78f5f19c6` |

También se comprobaron, antes y después, los hashes del histórico epidemiológico, catálogo y centroides;
las cinco entradas inspeccionadas permanecieron idénticas.

## Diferencia numérica que permanece visible

La prueba `test_las_17_columnas_que_quedan_son_identicas_al_respaldo` exige igualdad exacta y falla.
Se compararon independientemente las 17 columnas compartidas: **15 son idénticas**, y solo difieren
`semana_epi_seno` (1 170 filas) y `semana_epi_coseno` (2 340 filas). La diferencia absoluta máxima en
ambas es **1,1102230246251565 × 10⁻¹⁶**.

La magnitud es compatible con redondeo de cálculo flotante y está por debajo de la tolerancia de
1e-12 documentada para variables calculadas fuera del entorno de referencia. Sin embargo, esa prueba
particular usa `check_exact=True`: no se cambió el test ni el respaldo para ocultar el fallo.
Las llaves, conteos, etiquetas, umbrales, clima y demás columnas compartidas permanecen idénticos.
La comparación de B3 contra `frozen_configs.origins` pasó.

Esto deja un resultado de calidad y traspaso aprobado con una discrepancia de igualdad exacta
documentada, no una suite completa en verde. Si se exige identidad binaria con el archivo antiguo,
debe resolverse en un cambio de reproducibilidad separado antes de declarar esa equivalencia.

## Próximo paso

Gold ya tiene el esquema requerido. Aún no se entrenó v2, no se publicó un paquete, no se migró la BD
configurada y no cambió la API usada por la vista previa. El siguiente trabajo se revisará como otra
fase: elegir una publicación v2 existente o preparar explícitamente entrenamiento, BD y artefactos.
