# Especificación del backend según el documento OE2

Fuente de verdad: documento «OE2 Diseño de la Solución v1.1», sección 5 (Tablas 9–14),
Anexo B (DDL) y Tabla 2 (contrato de la API). El DDL completo está en
[`ddl_oe2.sql`](ddl_oe2.sql). Si este archivo y el DDL difieren, manda el DDL.

Alcance de TB1: **todo local**. PostgreSQL local (y SQLite para pruebas), FastAPI con
uvicorn, almacenamiento de artefactos en carpeta local. **No** se despliega en
Supabase ni Render en esta etapa.

## 1. Tablas objetivo

| Tabla | Clave | Notas obligatorias |
|---|---|---|
| `provincia` | `ubigeo_provincia` char(4) | Se deriva de los 4 primeros dígitos del ubigeo. |
| `distrito` | `ubigeo` char(6) | FK a provincia; `latitud`, `longitud` numeric(9,6) con rango de Piura; `poblacion_censo_2017`; `activo`. Ubigeo siempre string. |
| `semana_epidemiologica` | `id_semana` integer | `id_semana = anio*100 + semana` (ej. 202501). `fecha_fin = fecha_inicio + 6`; `temporada`. Calendario MMWR de `src/utils/calendario.py` (incluye semana 53 de 2025). |
| `ejecucion` | `id_ejecucion` identity | Unifica cargas, inferencias, reentrenamientos y mantenimiento: `tipo` (`ingesta`, `inferencia`, `reentrenamiento`, `mantenimiento`), `estado` (`en_curso`, `exitosa`, `fallida`), `id_semana_corte`, `inicio`, `fin`, `detalle` jsonb (hashes, resultados GX, conteos, duración, versiones usadas), `mensaje_error`. |
| `observacion_semanal` | PK compuesta `(ubigeo, id_semana)` | `casos_dengue` (NULL = sin dato, 0 = cero real), `umbral_brote_casos`, `brote`, clima semanal (`temp_media_c`, `temp_min_c`, `temp_max_c`, `precip_total_mm`, `hum_rel_media_pct`), `fuente_casos` enum, `estado_cobertura` enum, `fecha_extraccion`, `id_ejecucion` FK. CHECK de temperaturas y rangos. |
| `version_modelo` | `id_version` identity | `codigo` único (ej. `clf-h4-v1`), `tarea` enum, `horizonte` ∈ {2,3,4}, `algoritmo`, `variables`, `hiperparametros`, `metricas` jsonb, `umbral_probabilidad`, `cumple_umbrales`, `estado` enum (`candidata`, `activa`, `archivada`, `rechazada`), `mlflow_run_id`, `ruta_artefacto`, `sha256_artefacto`, `sha256_dataset`, `fecha_registro`, `fecha_activacion`. CHECK `estado <> 'activa' OR cumple_umbrales`. Índice único parcial: una sola activa por `(tarea, horizonte)`. |
| `prediccion` | `id_prediccion` identity | `ubigeo`, `id_semana_corte`, `id_semana_objetivo`, `horizonte`, `probabilidad_brote`, `nivel_riesgo` enum, `casos_estimados`, `estado` (`disponible`/`no_disponible`), `motivo_no_disponible`, `id_version_clasificador`, `id_version_regresor`, `id_ejecucion`, `fecha_generacion`. **UNIQUE `(ubigeo, id_semana_corte, horizonte)` → UPSERT**. CHECK de coherencia estado/probabilidad/nivel/motivo. |
| `alerta` | `id_alerta` identity | `id_prediccion` único, `ubigeo`, `nivel` ∈ {alto, muy_alto}, `estado` (`activa`/`retirada`), `cambio` (`nueva`, `se_mantiene`, `sube_nivel`, `baja_nivel`), `fecha_generacion`, `fecha_retiro`. CHECK `estado = 'activa' OR fecha_retiro IS NOT NULL`. |
| `parametro_sistema` | `clave` | Semillas: `regla_brote`, `cortes_riesgo` (0.25/0.50/0.75), `umbrales_aceptacion` (recall 0.80, precision 0.60, f1 0.70, razon_error_base 0.85). La API y el pipeline leen estos valores de la BD; `config.yaml` solo los siembra. |

Índices: `ix_pred_objetivo (id_semana_objetivo, horizonte)`, `ix_alerta_estado (estado, nivel)`,
`ix_obs_semana (id_semana)`, `ix_ejecucion_tipo_inicio (tipo, inicio DESC)`.

## 2. Tipos y portabilidad

- En PostgreSQL: ENUM nativos con los nombres del DDL (`fuente_casos_t`, `nivel_riesgo_t`, …),
  `jsonb`, `numeric`, `timestamptz`, `char(n)`.
- En SQLite (solo pruebas): `sqlalchemy.Enum(..., name="<nombre>_t")` con `native_enum` en
  PostgreSQL y CHECK en SQLite; `JSON().with_variant(JSONB, "postgresql")`.
- Las CHECK con regex (`~`) solo se crean en PostgreSQL; en SQLite se validan en el ORM.
- `nivel_riesgo` se guarda como `bajo|medio|alto|muy_alto`; la API puede devolver además
  la etiqueta legible (`Bajo`, `Medio`, `Alto`, `Muy alto`).

## 3. Seguridad (solo PostgreSQL local)

- RLS activado en las nueve tablas, roles `rol_api` y `rol_pipeline` (NOLOGIN) con los GRANT
  y políticas del DDL. La migración crea los roles solo si no existen (bloque `DO`) y solo
  cuando el dialecto es PostgreSQL; en SQLite se omite.
- Escrituras de la API protegidas con `X-API-Key` (equivale al «token de servicio» de la Tabla 2).
- `.env` no se lee ni se versiona; credenciales nunca en código, tests ni reportes.

## 4. Artefactos (Storage local)

El documento define buckets de Supabase Storage `modelos/`, `geodatos/`, `reportes/`.
En TB1 se implementa un **adaptador de almacenamiento local** (puerto `Almacenamiento`
con `guardar`, `leer`, `existe`) sobre `models/storage/<bucket>/` (ruta desde
`src/utils/paths.py`, ignorada por Git). `version_modelo.ruta_artefacto` guarda la ruta
lógica (`modelos/clf-h4-v1.json`) y `sha256_artefacto` su hash; al cargar el booster se
verifica el hash. El adaptador Supabase queda como trabajo de despliegue (fuera de TB1).

## 5. Contrato de la API (Tabla 2) — base `/api/v1`

| Método y ruta | Acceso | HU |
|---|---|---|
| GET `/salud` | Público | HU0016 |
| GET `/distritos` | Público | HU0012–HU0015 |
| GET `/predicciones` | Público | HU0010, HU0011 |
| GET `/series/{ubigeo}` | Público | HU0013 |
| GET `/tablero/resumen` | Público | HU0012 |
| GET `/mapa-riesgo` (GeoJSON) | Público | HU0014 |
| GET `/alertas` (filtros horizonte, distrito, nivel) | Público | HU0015 |
| GET `/modelos/activo` | Público | HU0008 |
| POST `/admin/inferencias` (semana de corte) | `X-API-Key` | HU0009 |
| POST `/admin/modelos/{version}/activar` | `X-API-Key` | HU0009 |

Endpoints adicionales permitidos (ya existen y aportan a HU): `GET /distritos/{ubigeo}`,
`GET /observaciones`, `GET /alertas/{id}`, `GET /modelos/{id}`, `GET /modelos/{id}/variables`.
Se documentan como extensiones del contrato. Las rutas antiguas (`/tablero`, `/mapa`,
`/modelos` como lista activa, `/predicciones/recalcular`, `/modelos/{id}/activar`,
`/distritos/geojson`) se eliminan, sin alias.

## 6. Desviaciones aceptables (deben quedar documentadas)

Solo con justificación escrita en `docs/backend/desviaciones_oe2.md`:
- Tablas extra de soporte (p. ej. `importancia_variable` para HU0008-4).
- Columnas extra **opcionales** que no rompan las restricciones del documento.
- Cualquier otra diferencia requiere aprobación de Rosa antes de implementarse, y
  luego se reflejará en el documento OE2.
