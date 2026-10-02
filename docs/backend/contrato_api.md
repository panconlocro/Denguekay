# Contrato de la API

Base: `/api/v1`. Lectura pública de datos agregados por distrito. Escritura
con `X-API-Key`, definida mediante `API_KEY` en `.env`. CORS permite únicamente
el origen de `serving.cors_origen`. La especificación [openapi.json](openapi.json)
incluye esquemas, parámetros, respuestas y ejemplos obtenidos de la BD local
de verificación, sin datos inventados. `/docs` muestra la documentación interactiva.

## Recursos

| Método y ruta | Filtros o parámetros | Comportamiento |
|---|---|---|
| GET `/salud` | — | Conexión real, versiones activas, última ejecución completada y corte |
| GET `/distritos` | `pagina`, `tamano_pagina` | Catálogo paginado, ubigeo como string |
| GET `/distritos/{ubigeo}` | Código de seis dígitos | Distrito o 404 |
| GET `/distritos/geojson` | — | FeatureCollection; centroides Point cuando no hay polígonos |
| GET `/observaciones` | `ubigeo`, `desde`, `hasta`, paginación | Registros observados y procedencia |
| GET `/predicciones` | `horizonte` obligatorio; `ubigeo`, `semana`, paginación | Última ejecución vigente del horizonte, sin rescatar resultados sustituidos |
| GET `/mapa` | `horizonte` obligatorio | Todos los distritos, riesgo o Sin datos, objetivo y leyenda |
| GET `/series/{ubigeo}` | `horizonte` obligatorio; `desde`, `hasta` | Observado y OOS/vigente, con semanas ausentes explícitas |
| GET `/tablero` | `horizonte` obligatorio | Indicadores, periodo y cobertura; total regional solo si está completo |
| GET `/alertas` | `horizonte`, `ubigeo`, `estado`, paginación | Muy alto antes de Alto; conserva alertas retiradas |
| GET `/alertas/{identificador}` | ID positivo | Indicadores, motivo de retiro y estado experimental/validado |
| GET `/modelos` | `horizonte`, paginación | Servicio e históricos, selección activa y validación calculada |
| GET `/modelos/{identificador}` | ID positivo | Métricas por bloque, particiones, columnas, parámetros y reproducibilidad |
| GET `/modelos/{identificador}/variables` | ID positivo | Gain guardado, rango y advertencia de no causalidad |
| POST `/modelos/{identificador}/activar` | ID positivo, `X-API-Key` | Selecciona versión compatible y reevalúa en una sola transacción |
| POST `/predicciones/recalcular` | `horizonte`, `X-API-Key` | Carga boosters de la BD y reevalúa vectores vigentes |

`desde` y `hasta` son fechas inclusivas `AAAA-MM-DD`. `semana` identifica el
domingo de inicio de la semana objetivo; no es un número ISO ni una búsqueda
por la fecha del servidor. Horizonte acepta 2, 3 y 4: sin modelo para h=3 las
lecturas informan ausencia; las escrituras se rechazan con 409. Paginación:
`pagina >= 1`, `1 <= tamano_pagina <= 100`; respuesta con `elementos`, `total`,
`pagina`, `tamano_pagina`, disponibilidad, motivo y fechas. La serie admite
hasta 1040 semanas por consulta; cubre todas las semanas del intervalo, sin
paginar su eje temporal. Mapa/GeoJSON contienen el catálogo completo.

## Identidad, faltantes y fechas

Cada observación o predicción incluye `ubigeo`, `distrito`, `anio`, `semana_epi`,
`semana_inicio`, `horizonte`, `tipo_dato`, `estado_validacion`,
`version_modelo_id`, `fecha_actualizacion` y `fecha_corte_datos`. Una observación
usa horizonte/version `null` y validación `no_aplica`. En predicciones,
`version_modelo_id` identifica clasificación; `version_regresion_id` y
`version_persistencia_id` identifican los otros componentes.

Cero casos es una observación disponible. Una ausencia devuelve `null`,
`disponible: false` y `motivo`. La serie materializa huecos calendáricos en
memoria; no inserta observaciones ni interpolaciones en la BD. Las listas de
observaciones/predicciones devuelven solo registros existentes: un filtro sin
registros tiene lista vacía y motivo. El mapa conserva cada distrito aunque
no tenga fila, con probabilidad/magnitud nulas y riesgo Sin datos.

La probabilidad y la magnitud tienen disponibilidad independiente en
`componentes`. Si falta un componente, el otro no se sustituye ni se rellena.
El tablero declara la cobertura de los agregados parciales; `casos_estimados_region`
es nulo si falta algún distrito. Un conteo real de cero alertas sí puede ser
cero; si no existe probabilidad para evaluar alertas, el indicador es nulo.

`fecha_corte_datos` proviene de la carga/ejecución. `fecha_actualizacion` es
el instante de escritura en UTC. Recalcular hoy conserva el corte y objetivo
originales. Vigente significa última publicación respecto de ese corte;
no significa que el pronóstico sea vigente respecto de la fecha de hoy.
La actualización de h=2 no cambia la selección ni las fechas de h=4.

## Modelo experimental y alertas

La aceptación se calcula con las métricas y criterios guardados: 2024 es el
contraste y 2025 se muestra como sensibilidad separada. Las métricas temporales
importadas evalúan el protocolo; no se presentan como una evaluación nueva del
ajuste de servicio. `activa` indica selección para inferencia en la demo y
no acredita promoción a producción. Las versiones históricas sin booster
siguen consultables y no son reactivables.

Con `servir_no_validadas: false`, los componentes experimentales se ocultan
con valores nulos y motivo «Predicción no disponible: modelo no validado».
También se ocultan sus niveles e indicadores de alertas y se rechazan
reevaluaciones/activaciones de esas versiones. La demo usa `true`, conforme
al encargo y a las decisiones aprobadas; sigue pendiente la aceptación antes
de cualquier promoción prevista en OE2.

La alerta visible usa Alto/Muy alto, desde 0,50 con la configuración aprobada.
`alerta_modelo` conserva el umbral F1 de la versión. La discrepancia se expone
sin calibrar ni cambiar probabilidades. Las alertas retrospectivas permanecen
retiradas y no se presentan como avisos vigentes. Los umbrales, nivel mínimo
y origen CORS proceden de `config/config.yaml`.

## Escrituras, caché y errores

La API no entrena ni lee gold, silver, reference, boosters locales o MLflow.db.
La reevaluación valida columnas y ajuste anterior o igual al origen. Solo usa
vectores vigentes, nunca OOS. Cada POST exitoso crea una ejecución con hashes,
versiones usadas y duración; mantiene el historial. Activación y predicciones
se confirman conjuntamente; cualquier fallo las revierte. Una petición de
activación sobre la versión ya activa reevalúa y registra ejecución sin
inventar un cambio de selección. El historial de cambios reales está en
`activacion_modelo`. Repetir un POST solicita otra ejecución auditada; la
idempotencia del CLI `publicar` se conserva como contrato separado.

La caché tiene TTL de diez segundos y hasta 128 entradas por proceso. Consulta
la revisión de carga/ejecución/activación antes de usarla y se limpia después
de escribir. Un acierto no oculta una BD caída. Incluye `X-Cache` HIT/MISS y
`X-Tiempo-Respuesta-ms`; CORS expone ambas cabeceras al frontend. No sustituye
el benchmark p50/p95 de la fase 4.

Errores uniformes: `codigo`, `mensaje`, `detalle`. No incluyen contraseñas,
SQL ni vectores. Códigos HTTP:

| HTTP | Uso |
|---|---|
| 401 | Clave de escritura ausente o incorrecta |
| 404 | Distrito, modelo, alerta o ruta inexistente |
| 409 | Sin versión/vectores, artefacto incompatible o falta de aceptación requerida |
| 422 | Ubigeo inválido, horizonte fuera de rango, fecha inválida, rango o paginación incorrectos |
| 503 | BD inaccesible/no configurada o clave de escritura sin configurar |
| 500 | Error interno inesperado, con mensaje público controlado |

## Exportar y comprobar

```bash
.venv/bin/python -m src.api.exportar_openapi
.venv/bin/python -m unittest discover -s tests -p test_api_backend.py
```

La exportación requiere `DATABASE_URL`, tablas migradas y consulta real exitosa.
Omite ejemplos de recursos inexistentes; no fabrica versiones ni alertas para
documentar un endpoint. Los ejemplos de POST vienen de ejecuciones API ya
guardadas, sin ejecutar escrituras durante la exportación. La documentación
interactiva sigue accesible si la BD cae, sin ejemplos inventados de respaldo.

Pendientes de las fases siguientes: benchmark SLA reproducible, documentación
C4/trazabilidad completa, CI y despliegue aprobado en Render/Supabase. Windows
no se ha ejecutado en este equipo; no hay afirmación de verificación remota.
