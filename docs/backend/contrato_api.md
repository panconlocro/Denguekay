# Contrato de la API (Tabla 2 del documento OE2)

Base: `/api/v1`. Especificación generada: [openapi.json](openapi.json) (con ejemplos de una BD
real). Lecturas públicas; escrituras con cabecera `X-API-Key`. Detalle de diseño y
desviaciones: [especificacion_oe2.md](especificacion_oe2.md), [desviaciones_oe2.md](desviaciones_oe2.md).

## Endpoints de la Tabla 2

| Método y ruta | Acceso | HU | Respuesta |
|---|---|---|---|
| GET `/salud` | Público | HU0016 | Estado, conexión a la BD, corte de datos y última ejecución exitosa |
| GET `/distritos` | Público | HU0012–HU0015 | Página de distritos: ubigeo (texto), provincia, centroide, población censo 2017 |
| GET `/predicciones?horizonte=&ubigeo=&corte=` | Público | HU0010, HU0011 | Predicciones del corte vigente (o de `corte`): probabilidad, nivel, casos estimados, línea base, `experimental` |
| GET `/series/{ubigeo}?horizonte=&desde=&hasta=` | Público | HU0013 | Semanas continuas con casos observados y la predicción cuyo objetivo es esa semana |
| GET `/tablero/resumen?horizonte=` | Público | HU0012 | Conteo por nivel, alertas activas, casos estimados regionales (null si falta un distrito) y observados |
| GET `/mapa-riesgo?horizonte=` | Público | HU0014 | GeoJSON `FeatureCollection` de centroides `Point` con nivel o «Sin datos» y leyenda |
| GET `/alertas?horizonte=&ubigeo=&nivel=&estado=` | Público | HU0015 | Alertas alto/muy_alto con `cambio`, estado y su predicción |
| GET `/modelos/activo?horizonte=` | Público | HU0008 | Versión en uso por tarea y horizonte (`seleccion`: activa o experimental) |
| POST `/admin/inferencias` | `X-API-Key` | HU0009 | Cuerpo `{"horizonte": 2|4, "id_semana_corte": opcional}`; resumen de la ejecución |
| POST `/admin/modelos/{version}/activar` | `X-API-Key` | HU0009 | Activa `id_version` si cumple umbrales; archiva la anterior |

Extensiones (no están en la Tabla 2): GET `/distritos/{ubigeo}`, `/observaciones`,
`/alertas/{id}`, `/modelos/{id}` y `/modelos/{id}/variables`.

## Identidad, semanas y faltantes

- `ubigeo` es texto de 6 dígitos. Las semanas son MMWR (domingo a sábado) con
  `id_semana = anio*100 + semana`; cada respuesta incluye `fecha_inicio` y `fecha_fin`.
- `semana_corte` es la última semana con datos usada; `semana_objetivo` = corte + h semanas.
- Un valor ausente es `null` con `disponible: false` y `motivo`; un cero es un dato.
- `tipo`: `vigente` (último corte publicado por una inferencia operativa) o `retrospectiva`
  (cortes pasados, incluidas las predicciones OOS del protocolo).
- **h=3:** no hay modelo. Las lecturas responden 200 con `disponible: false` y motivo
  «sin modelo para h=3»; `POST /admin/inferencias` responde 409.

## Riesgo, alertas y modo experimental

- `nivel_riesgo` ∈ `bajo|medio|alto|muy_alto` según `parametro_sistema.cortes_riesgo`
  (0,25 / 0,50 / 0,75); `nivel_riesgo_etiqueta` da el texto legible.
- Una alerta se genera para `alto` y `muy_alto`; `cambio` compara con el nivel de la semana de
  corte anterior (`nueva`, `se_mantiene`, `sube_nivel`, `baja_nivel`). Hay como máximo una alerta
  activa por distrito y horizonte: al llegar otro corte la anterior pasa a `retirada` con
  `fecha_retiro` y `motivo`.
- `experimental: true` indica que la versión usada no cumple los umbrales de aceptación (hoy, todas).
  `alerta_modelo` compara la probabilidad con el umbral F1 de la versión; es independiente de la alerta.
- `casos_persistencia` es la línea base: casos observados en la semana de corte.

## Errores

Formato uniforme `{"codigo", "mensaje", "detalle"}`, sin SQL ni credenciales.

| HTTP | Códigos |
|---|---|
| 401 | `clave_invalida` |
| 404 | `distrito_no_encontrado`, `alerta_no_encontrada`, `modelo_no_encontrado`, `solicitud_invalida` |
| 409 | `inferencia_no_disponible`, `artefacto_invalido`, `no_cumple_umbrales`, `ya_activa`, `version_rechazada`, `sin_datos` |
| 422 | `parametro_invalido`, `rango_invalido` |
| 503 | `bd_no_disponible`, `escritura_no_configurada`, `parametros_no_configurados` |

## Caché y tiempos

Las lecturas se cachean 10 s y se invalidan cuando aparece una ejecución nueva
(`max(id_ejecucion)`); `Cache-Control: no-cache` la evita. Cabeceras `X-Cache` y
`X-Tiempo-Respuesta-ms`. Benchmark local (p95): lecturas ≤ 32 ms y inferencia ≈ 3,6 s, en SQLite
y PostgreSQL ([benchmark_postgresql.json](benchmark_postgresql.json)).

## Regenerar el contrato

`.\.venv\Scripts\python -m src.api.exportar_openapi` (usa `DATABASE_URL`; exige conexión real).
