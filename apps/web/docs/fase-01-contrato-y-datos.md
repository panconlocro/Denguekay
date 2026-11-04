# Fase 1 Contrato de interfaz y disponibilidad de datos

Revisión del 04/11/2026. Se relacionan los componentes del punto 6 de OE2 v1.3 y los
[mockups de Figma](https://www.figma.com/design/YntyrKwEpxRMCkAoLLhdC6) con las 14 lecturas del
[contrato OpenAPI 1.1.0](../../../docs/backend/openapi_v1.json).
Se distingue que un campo exista en el contrato, que haya datos utilizables y que la interfaz ya lo implemente.
El diseño define la presentación; sus cifras ilustrativas no constituyen datos de la aplicación.

## Resultado de preparación

La API tiene los recursos necesarios para la base de consulta distrital, pero el entorno local no está
listo para verificar la publicación completa v2. La base seleccionada por el `.env` existe y tiene datos,
pero usa un esquema anterior al contrato actual. No se encontró una demo actual de v2 ni el directorio
de artefactos locales. Esto no demuestra que no existan en otra máquina o en un despliegue externo.

La inspección no cambió conexiones, bases, esquemas, fuentes, modelos ni el contrato. Se hicieron
lecturas SQLite en modo `ro` y solicitudes GET de FastAPI en proceso, también con conexión de solo lectura.
No se consultó una API externa de producción ni se ejecutó inferencia. Posteriormente, por indicación
expresa del usuario, se ejecutó el notebook 10 y se actualizó gold; el resultado se registra en el
[informe de regeneración](actualizacion-gold-20261104.md).

## Matriz de componentes

En las rutas de esta matriz se omite el prefijo común `/api/v1`.
«Directo» indica que existe un campo tipado; no certifica la calidad de una BD particular.
«Composición» requiere unir o presentar respuestas existentes respetando su alcance y su paginación.
«Brecha» indica información ausente o insuficiente para reproducir fielmente el componente.

| Vista y componente                                 | Lectura                                                                       | Campos o relación                                                                                       | Disponibilidad y límite                                                                                                                      |
| -------------------------------------------------- | ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| Cabecera y versión                                 | `/configuracion`, `/salud`                                                    | `version_contrato`, `version_api`, `fecha_actualizacion`, `fecha_corte_datos`                           | Directo. Contrato y aplicación tienen versiones distintas                                                                                    |
| Semana objetivo y corte                            | `/tablero/resumen`, `/predicciones`, `/mapa-riesgo`                           | `semana_objetivo`, `semana_corte` con fechas                                                            | Directo. «Vigente» significa último corte publicado, no que el objetivo siga siendo futuro                                                   |
| Horizonte y estado                                 | `/configuracion`                                                              | `horizontes`, `horizontes_disponibles`, `horizonte_por_defecto`, `disponible`, `experimental`, `motivo` | Directo. No copiar los estados Operativo del mockup                                                                                          |
| Anticipación efectiva                              | Fechas del objetivo y de consulta/generación                                  | La API no entrega un campo de anticipación efectiva                                                     | Brecha de especificación: acordar fecha de referencia y fórmula antes de mostrar una cifra; `h` por sí solo no la demuestra                  |
| Provincia y distrito                               | `/distritos`                                                                  | `ubigeo`, `ubigeo_provincia`, `nombre`, `provincia`                                                     | Composición del catálogo completo. `ubigeo` permanece como texto                                                                             |
| Selector histórico global                          | `/predicciones?corte=` admite corte; mapa y resumen solo horizonte            | No existe un catálogo de cortes ni un corte común aceptado por todas las vistas                         | Parcial. No simular que el selector modifica datos que el endpoint no filtra                                                                 |
| Tablero: casos observados                          | `/tablero/resumen`                                                            | `casos_observados_ultima_semana.{valor,disponible,motivo}`                                              | Directo, con problema conocido de cobertura de la suma. La respuesta no da el número de distritos con casos observados disponibles           |
| Tablero: distritos de riesgo alto                  | `/tablero/resumen`                                                            | `niveles_riesgo`, `distritos`, `distritos_con_prediccion`                                               | Composición de los conteos ya calculados por la API; no recalcular probabilidades ni niveles                                                 |
| Tablero: magnitud regional                         | `/tablero/resumen`                                                            | `casos_estimados_region.{valor,disponible,motivo}`                                                      | Directo, con corrección de completitud pendiente en el backend                                                                               |
| Tablero: incidencia                                | Sin lectura específica                                                        | El catálogo solo aporta `poblacion_censo_2017`, no población del periodo e incidencia                   | Brecha. No calcular incidencia actual con población censal antigua                                                                           |
| Tablero: distritos prioritarios                    | `/predicciones?horizonte=`, `/distritos`                                      | `probabilidad_brote`, `nivel_riesgo`, `casos_estimados`, distrito y provincia                           | Composición: leer todas las páginas, filtrar catálogo y ordenar la lista completa                                                            |
| Tablero: serie regional                            | Sin lectura específica                                                        | `/series/{ubigeo}` es distrital                                                                         | Brecha. No construir un total regional con una muestra parcial ni rellenar faltantes                                                         |
| Mapa: geometría y riesgo                           | `/mapa-riesgo?horizonte=`                                                     | `features[].geometry`, `properties`, `leyenda`                                                          | Directo para centroides actuales; el esquema también admite polígonos                                                                        |
| Mapa coroplético                                   | Misma ruta; falta la fuente de polígonos publicada                            | `Polygon` o `MultiPolygon`                                                                              | Brecha de geodatos/licencia. Los polígonos esquemáticos de Figma no son una fuente territorial                                               |
| Mapa: panel del distrito                           | `/mapa-riesgo`, `/predicciones`, `/distritos/{ubigeo}`                        | Probabilidad, casos, nivel, intervalo, distrito, fechas y horizonte                                     | Composición. Los intervalos de casos son orientativos y no calibrados                                                                        |
| Mapa: distritos por nivel                          | `/tablero/resumen` o listado del mapa                                         | `niveles_riesgo`; cada `properties.nivel_riesgo`                                                        | El resumen es regional. Un conteo sobre la selección del mapa debe rotular su alcance                                                        |
| Mapa: sin predicción                               | `/mapa-riesgo`                                                                | `estado`, `motivo`, nivel nulo                                                                          | Directo. Gris y explicación; nunca asignar riesgo bajo por ausencia                                                                          |
| Detalle: probabilidad y magnitud                   | `/predicciones?horizonte=&ubigeo=`                                            | Probabilidad, nivel, `casos_estimados`, intervalos y `motivo_intervalo`                                 | Directo. Comprobar `disponible` y cada campo anulable                                                                                        |
| Detalle: comparación entre horizontes              | Misma ruta para cada horizonte disponible                                     | Semana objetivo y corte de cada respuesta                                                               | Composición. Cada horizonte puede tener distinta semana objetivo o un corte publicado diferente                                              |
| Detalle: serie observada y predicha                | `/series/{ubigeo}?horizonte=&desde=&hasta=`                                   | `elementos[].semana`, `casos_dengue`, `observado`, `prediccion`                                         | Directo. Interrumpir líneas donde falten datos; distinguir retrospectiva de pronóstico futuro                                                |
| Detalle: umbral histórico de brote                 | `/observaciones?ubigeo=&desde=&hasta=`                                        | `umbral_brote_casos`, semana                                                                            | Composición por distrito y semana objetivo. No viene en `SerieSemana`                                                                        |
| Detalle: umbral futuro                             | No está expuesto en predicción ni en serie                                    | No extrapolar el último umbral observado a semanas futuras                                              | Brecha. Requiere extensión de API para mostrarlo con trazabilidad                                                                            |
| Detalle: último observado/persistencia             | `/predicciones`, `/observaciones`                                             | `casos_persistencia`; casos observados en el corte o en la semana consultada                            | Directo o composición según la etiqueta; no confundir ambas fechas                                                                           |
| Detalle: clima observado                           | `/observaciones`                                                              | Temperaturas, precipitación y humedad de la semana                                                      | Directo para valores semanales, no para medias de ventanas del modelo                                                                        |
| Detalle: vecinos, provincia y aportes individuales | Sin lectura específica                                                        | No hay vectores de entrada ni contribuciones individuales                                               | Brecha. Las importancias globales no sustituyen SHAP individual ni prueban causalidad                                                        |
| Alertas: listado y detalle                         | `/alertas`, `/alertas/{identificador}`                                        | `nivel`, `estado`, `cambio`, fechas, `motivo`, `experimental`, `prediccion`                             | Directo. Leer todas las páginas antes de reordenar globalmente                                                                               |
| Alertas: filtros y orden                           | `/alertas?horizonte=&ubigeo=&nivel=&estado=`                                  | Provincia se cruza con catálogo; el servidor ordena nivel/fecha, no probabilidad                        | Composición para orden global por probabilidad. No ordenar solo una página y presentarla como ranking completo                               |
| Alertas: nuevas/retiradas en la actualización      | `/alertas`                                                                    | `cambio`, `fecha_generacion`, `fecha_retiro`                                                            | Parcial. No hay agregado por actualización ni identificador de lote en la alerta; no usar un recuento histórico como «de esta actualización» |
| Alertas: próxima actualización                     | Sin lectura específica                                                        | No hay calendario de publicación garantizado                                                            | Brecha. No inventar una fecha sumando siete días                                                                                             |
| Desempeño: versión y selección                     | `/modelos/activo`, `/modelos/{identificador}`                                 | Tarea, horizonte, código, estado, validación y reproducibilidad                                         | Directo. «Modelo en uso» incluye la selección experimental                                                                                   |
| Desempeño: métricas por bloque                     | `/modelos/{identificador}`                                                    | `metricas` con bloques, clasificación, regresión y persistencia                                         | Disponible como objeto abierto. Hace falta un adaptador que compruebe claves y conserve nulos; no mezclar periodos o versiones               |
| Desempeño: umbrales de aceptación                  | `cumple_umbrales` existe; los umbrales numéricos no están en `/configuracion` | La autoridad es `parametro_sistema`, no valores del mockup                                              | Parcial. Mostrar el resultado de validación disponible; exponer criterios por API si se requiere una comparación dinámica exacta             |
| Desempeño: variables relevantes                    | `/modelos/{identificador}/variables`                                          | `elementos` y `nota`                                                                                    | Disponible como lista abierta. Verificar variable/importancia/rango; usar la nota para distinguir método SHAP/gain y no causalidad           |
| Desempeño: diagrama de validación temporal         | Detalle del modelo                                                            | `reproducibilidad` es abierto y anulable; no hay contrato tipado de ventanas                            | Parcial. No copiar años o folds ilustrativos como si fueran evidencia del modelo publicado                                                   |
| Ayuda: guía y búsqueda                             | Contenido editorial del frontend                                              | Definiciones consistentes con configuración y contrato                                                  | Implementable sin endpoint nuevo; los rangos de riesgo proceden de la API                                                                    |
| Ayuda: PDF, capacitación y soporte                 | No hay archivos o destinos acordados en el contrato                           | Recursos externos pendientes                                                                            | Brecha de contenido. No ofrecer botones con destinos ficticios                                                                               |
| Estados y móvil                                    | Estados de consulta y respuesta, misma API                                    | HTTP, `disponible`, `motivo`, campos nulos, `experimental`                                              | Transversal. No sustituir valores fallidos por cero ni conservar resultados anteriores como vigentes                                         |

## Inventario local comprobado

Se inspeccionaron las bases con SQLite en modo de solo lectura. No se imprimieron credenciales.

| Fuente                        | Revisión Alembic | Distritos | Observaciones | Predicciones | Horizontes con filas |
| ----------------------------- | ---------------- | --------- | ------------- | ------------ | -------------------- |
| `models/serving/fase1.sqlite` | `0002_serving`   | 65        | 30 485        | 27 170       | 2 y 4                |
| `models/serving/fase2.sqlite` | `0002_serving`   | 65        | 30 485        | 27 170       | 2 y 4                |
| `models/serving/fase3.sqlite` | `0002_serving`   | 65        | 30 485        | 27 300       | 2 y 4                |
| `models/serving/fase4.sqlite` | `0002_serving`   | 65        | 30 485        | 32 500       | 2 y 4                |

El `.env` local selecciona `fase4.sqlite`. Esas bases tienen 30 registros de versión cada una, pero
no cuentan con el esquema actual de `version_modelo`: no se interpretan esos registros como seis
versiones v2 publicadas ni como una selección compatible con la API actual.

La cabecera de Alembic del código es `0006_v1`. Contra `fase4.sqlite`, las seis lecturas comprobadas
(`/salud`, `/configuracion`, `/distritos`, `/predicciones?horizonte=4`,
`/tablero/resumen?horizonte=4`, `/mapa-riesgo?horizonte=4`) respondieron **503 `bd_no_disponible`**
y contrato `1.1.0`. Son solicitudes en proceso con conexión `ro`, no una prueba contra producción.
La existencia del archivo y sus filas no implica compatibilidad de esquema.

Otros hechos comprobados en esta máquina:

- No existe `models/serving/demo/denguekay_demo.sqlite` ni el directorio `models/storage/`.
- No se encontraron manifiestos `manifest.json` bajo `models/`; sí hay reportes y boosters antiguos.
- No hay URL ni clave de Supabase Storage configuradas en el entorno/.env inspeccionado.
- `configs/config.yaml` configura el predictor `v2_e3_s4`, horizontes 2/3/4 y selección experimental.
  Esa configuración no carga ni publica automáticamente el modelo en una BD.
- Al iniciar la inspección, el gold local tenía **48 columnas** y carecía de las tres B3 del contrato
  persistido actual de 20 columnas. Tras la solicitud de ejecutar el notebook 10, se regeneró con
  **30 485 filas y 20 columnas**, B3 incluida. El gold anterior h=2/h=4 y su manifiesto se conservaron
  en `data/gold/respaldo_pre_b3/`. La BD operacional y la publicación v2 no cambiaron.

## Datos de prueba frente a datos operacionales

El servidor `e2e/serve_api.py` crea una base temporal a partir de fixtures, con v0, datos suficientes
para tres distritos y modelos para h=2/h=4. La fixture fuerza la probabilidad de Piura h=2 a `0,8`
para comprobar una alerta. Esa cifra no es una salida original del modelo. El código del navegador
consulta la API y no importa las fixtures; aun así, una captura de ese servidor no es evidencia de
resultados de v2.

La vista previa anterior se inició con `API_PROXY_TARGET=http://127.0.0.1:18000`. Ese valor es del
proceso de desarrollo, no una conexión de producción guardada. El proxy por defecto apunta al puerto 8000. Cambiar la fuente de API no requiere descartar la implementación visual.

## Brechas y condiciones de avance

1. Elegir una fuente real compatible: demo actual de v2 ya publicada, o API de desarrollo verificada.
   Revisar `/salud`, `/configuracion`, versiones por horizonte, cortes y predicciones de distritos antes
   de llamarla integración de v2. La cobertura completa no se presupone aunque haya 65 distritos.
2. Si solo se dispone de esta copia local, preparar la BD/artefactos en un trabajo de backend separado.
   El gold ya se regeneró por autorización expresa; eso no migra la base ni publica modelos.
   No migrar a ciegas la única base antigua ni presentar el respaldo v0 como publicación v2.
3. Mantener registradas las correcciones previas de API: completitud de sumas regionales, consistencia
   al desactivar modelos experimentales y validación del rango con fecha final implícita.
4. Tratar las brechas de la matriz como faltantes explícitos o solicitudes de API por separado. Ninguna
   extensión del contrato ni fórmula pendiente queda aprobada por esta fase.
5. Revisar esta fase antes de continuar a la fase 2. El siguiente trabajo será auditar/adaptar la base
   existente y conectar la fuente elegida, no reconstruir automáticamente toda la interfaz.

Fuentes de verificación: [routers de datos](../../api/routers/data.py),
[vigilancia](../../api/routers/surveillance.py), [referencia](../../api/routers/reference.py),
[modelos](../../api/routers/models.py), [consultas](../../api/queries.py),
[guía de integración](../../../docs/backend/guia_frontend.md) y
[ficha v2](../../../models/registry/v2/ficha.md). Las cifras del inventario son de lecturas locales del
04/11/2026; no se confunden con los ejemplos incluidos en OpenAPI.
