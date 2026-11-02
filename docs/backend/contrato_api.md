# Contrato de la API (Tabla 2 del documento OE2) · v1.1.0

Base: `/api/v1`. **Contrato congelado:** [openapi_v1.json](openapi_v1.json) (sin ejemplos; lo vigila
`tests/test_contract_v1_guards.py`). **Con ejemplos reales:** [openapi.json](openapi.json) (mismo contrato,
ejemplos de la BD de demostración). Lecturas públicas; escrituras con cabecera `X-API-Key`. Detalle de diseño y
desviaciones: [especificacion_oe2.md](especificacion_oe2.md), [desviaciones_oe2.md](desviaciones_oe2.md);
decisiones del contrato v1: [api_v1_decisiones.md](api_v1_decisiones.md). Guía para el frontend:
[guia_frontend.md](guia_frontend.md).

## Versión del contrato (semver)

- `info.version` del OpenAPI es la **versión del contrato** (hoy `1.1.0`), y cada respuesta la trae en la
  cabecera `X-Version-Contrato`. `version_api` de `/salud` es la versión de la **aplicación** (`2.0.0`); las
  dos se mueven por separado (decisión C5).
- **Cambio aditivo** (ruta nueva, campo opcional nuevo, valor nuevo de un campo que el cliente ya trata como
  texto): sube la minor (`1.1.0`), se anota en el changelog de abajo y se regenera `openapi_v1.json` a
  propósito: `.\.venv\Scripts\python -m apps.api.tools.export_openapi --contrato`.
- **Cambio que rompe** (renombrar o quitar un campo o una ruta, cambiar un tipo, volver obligatorio un campo
  opcional): no se permite en `/api/v1`. Va en `/api/v2`, con un commit `feat(api)!`.
- El contrato no depende del modelo: un modelo nuevo se publica sin tocar rutas, esquemas ni el frontend.

## Endpoints de la Tabla 2

| Método y ruta | Acceso | HU | Respuesta |
|---|---|---|---|
| GET `/salud` | Público | HU0016 | Estado, conexión a la BD, corte de datos, última ejecución exitosa y versión de la aplicación |
| GET `/distritos` | Público | HU0012–HU0015 | Página de distritos: ubigeo (texto), provincia, centroide, población censo 2017 |
| GET `/predicciones?horizonte=&ubigeo=&corte=` | Público | HU0010, HU0011 | Predicciones del corte vigente (o de `corte`): probabilidad, nivel, casos estimados, intervalo, línea base, `experimental` |
| GET `/series/{ubigeo}?horizonte=&desde=&hasta=` | Público | HU0013 | Semanas continuas con casos observados y la predicción cuyo objetivo es esa semana |
| GET `/tablero/resumen?horizonte=` | Público | HU0012 | Conteo por nivel, alertas activas, casos estimados regionales (null si falta un distrito) y observados |
| GET `/mapa-riesgo?horizonte=` | Público | HU0014 | GeoJSON `FeatureCollection` (geometría `Point`, `Polygon` o `MultiPolygon`; hoy centroides) con nivel o «Sin datos» y leyenda |
| GET `/alertas?horizonte=&ubigeo=&nivel=&estado=` | Público | HU0015 | Alertas alto/muy_alto con `cambio`, estado y su predicción |
| GET `/modelos/activo?horizonte=` | Público | HU0008 | Versión en uso por tarea y horizonte (`seleccion`: activa o experimental) |
| POST `/admin/inferencias` | `X-API-Key` | HU0009 | Cuerpo `{"horizonte": 2|3|4, "id_semana_corte": opcional}`; resumen de la ejecución |
| POST `/admin/modelos/{version}/activar` | `X-API-Key` | HU0009 | Activa `id_version` si cumple umbrales; archiva la anterior |

Extensiones (no están en la Tabla 2): GET `/configuracion`, `/distritos/{ubigeo}`, `/observaciones`,
`/alertas/{id}`, `/modelos/{id}` y `/modelos/{id}/variables`.

## Configuración (GET `/configuracion`)

Todo lo que el frontend necesita para no tener valores en código duro: `version_contrato`,
`horizontes_disponibles` (los que tienen un modelo en uso en la BD), `horizonte_por_defecto`
(`parametro_sistema.horizonte_por_defecto`, hoy 4), `horizontes` (disponibilidad, motivo, corte vigente y
`experimental` de cada horizonte 2, 3 y 4), `cortes_riesgo`, `niveles`, `leyenda` (la misma del mapa),
`experimental` y `nota`. Si falta un parámetro en la BD responde 503 `parametros_no_configurados`.

## Identidad, semanas y faltantes

- `ubigeo` es texto de 6 dígitos. Las semanas son MMWR (domingo a sábado) con
  `id_semana = anio*100 + semana`; cada respuesta incluye `fecha_inicio` y `fecha_fin`.
- `semana_corte` es la última semana con datos usada; `semana_objetivo` = corte + h semanas.
- Un valor ausente es `null` con `disponible: false` y `motivo`; un cero es un dato.
- `tipo`: `vigente` (último corte publicado por una inferencia operativa) o `retrospectiva`
  (cortes pasados, incluidas las predicciones OOS del protocolo).
- **Horizontes:** la API acepta 2, 3 y 4 (como el DDL). Los disponibles salen de la BD, no del código (con la
  v2 servida, los tres). Un horizonte sin modelo responde 200 en las lecturas con `disponible: false` y motivo
  «sin modelo para h=N»; `POST /admin/inferencias` responde 409 `inferencia_no_disponible`.
- **Intervalo de casos:** `casos_intervalo_inferior`, `casos_intervalo_superior` y `nivel_intervalo` (0,80)
  son anulables; si el modelo no los estima (la v0) valen `null` y `motivo_intervalo` explica por qué.
  Con la v2 son el intervalo central de la binomial negativa NB2(μ, α) de cada horizonte (cuantiles 0,10 y 0,90). **El intervalo no está calibrado:** Platt corrige la probabilidad de brote, no la distribución de los casos, así que su cobertura real puede apartarse del 80 %.

## Riesgo, alertas y modo experimental

- `nivel_riesgo` ∈ `bajo|medio|alto|muy_alto` según `parametro_sistema.cortes_riesgo`
  (0,25 / 0,50 / 0,75); `nivel_riesgo_etiqueta` da el texto legible.
- Una alerta se genera para `alto` y `muy_alto`; `cambio` compara con el nivel de la semana de
  corte anterior (`nueva`, `se_mantiene`, `sube_nivel`, `baja_nivel`). Hay como máximo una alerta
  activa por distrito y horizonte: al llegar otro corte la anterior pasa a `retirada` con
  `fecha_retiro` y `motivo`.
- `experimental: true` indica que la versión usada no cumple los umbrales de aceptación (hoy, todas).
  `alerta_modelo` compara la probabilidad con el umbral de la versión; es independiente de la alerta.
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
(`max(id_ejecucion)`); `Cache-Control: no-cache` la evita. Cabeceras `X-Cache`,
`X-Tiempo-Respuesta-ms` y `X-Version-Contrato`. Benchmark local (p95): lecturas ≤ 32 ms e inferencia ≈ 3,6 s,
en SQLite y PostgreSQL ([benchmark_postgresql.json](benchmark_postgresql.json)).

## Regenerar el contrato

- `openapi.json` (con ejemplos): `.\.venv\Scripts\python -m apps.api.tools.export_openapi` (usa `DATABASE_URL`;
  exige conexión real y no escribe en la BD).
- `openapi_v1.json` (contrato congelado): solo después de subir la minor por un cambio aditivo, con
  `.\.venv\Scripts\python -m apps.api.tools.export_openapi --contrato`.

## Changelog del contrato

| Versión | Fecha | Cambios |
|---|---|---|
| 1.1.0 | 29/10/2026 | Solo textos, ningún esquema: el summary de `GET /modelos/{identificador}/variables` y la descripción de `VariablesRespuesta` dejan de decir «gain» y quedan neutros («importancias de la versión; el método va en `nota`»), porque la v2 guarda importancias SHAP. El `nota` de la respuesta explica el método de cada versión. |
| 1.0.0 | 29/10/2026 | Primera versión congelada (decisiones C1–C5 de `api_v1_decisiones.md`). Respecto del contrato de TB1 (`info.version` 2.0.0, que era la versión de la aplicación): horizontes 2, 3 y 4 con los disponibles leídos de la BD y motivo genérico «sin modelo para h=N»; nueva extensión `GET /configuracion`; campos anulables `casos_intervalo_inferior`, `casos_intervalo_superior`, `nivel_intervalo` y `motivo_intervalo` en las predicciones y en el mapa; GeoJSON tipado (`Point`, `Polygon`, `MultiPolygon`) y leyenda tipada; cabecera `X-Version-Contrato`; 503 `parametros_no_configurados` también en lecturas. Ningún campo existente se renombró ni se quitó. |
