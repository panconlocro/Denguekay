# Desviaciones del backend respecto del documento OE2

Fuente de verdad: [`especificacion_oe2.md`](especificacion_oe2.md) y [`ddl_oe2.sql`](ddl_oe2.sql).
Este archivo registra cada diferencia entre el documento y el código y la decisión
tomada para el refactor. **Estado: decisiones de la Fase 0 aprobadas por Rosa
(2026-10-01); Fase 1 (esquema) implementada; Fases 2–3 pendientes.**

Código revisado: `src/db/modelos.py`, migraciones `0001_backend` y `0002_serving`,
`src/serving/`, `src/api/` y los tests del backend (`test_db_backend`, `test_serving_*`,
`test_api_*`).

Tipos de desviación:
- **Extensión**: tabla o columna opcional que no rompe ninguna restricción del documento.
- **Temporal**: se retira cuando exista un modelo que cumpla los umbrales.
- **Corrección del documento**: el DDL tiene un defecto; el documento OE2 debe cambiar.
- **Observación de datos**: el diseño se cumple; lo que llama la atención son los datos actuales.

## 1. Decisiones aprobadas

| # | Tema | Decisión | Tipo |
|---|---|---|---|
| a | Modelos que no cumplen umbrales | Se respeta `CHECK (estado <> 'activa' OR cumple_umbrales)`: las versiones quedan `candidata`. Nueva clave `parametro_sistema.seleccion_experimental` con el código de la versión de clasificación y de regresión por horizonte, sembrada desde `config.yaml`. La inferencia usa la versión `activa` si existe; si no, la de `seleccion_experimental` cuando `servir_no_validadas = true`; si es `false`, las predicciones se guardan `no_disponible` con motivo. La API devuelve `"experimental": true` en predicciones, alertas y tablero cuando la versión usada tiene `cumple_umbrales = false` (campo calculado, no columna). `ejecucion.detalle` registra que la ejecución fue experimental | Temporal |
| b | Predicciones OOS | Se guardan en `prediccion` como cortes pasados, con `id_version_clasificador` e `id_version_regresor` en NULL; el bloque y su origen van en `ejecucion.detalle`. No se crean versiones sin booster. Las métricas por bloque quedan en `version_modelo.metricas` de las versiones de servicio | Extensión (uso) |
| c | Vector de características | Se reconstruye en memoria desde la BD (`observacion_semanal` + `distrito.poblacion_censo_2017` + calendario) y se elimina `prediccion.caracteristicas`. Condición: un test compara, para una muestra de distritos y cortes, el vector reconstruido con el de gold (tolerancia 1e-9), y otro comprueba que la probabilidad resultante coincide con la del pipeline actual. Si no coinciden, se detiene el refactor | Conforme al documento |
| d | Tablas extra | `importancia_variable` se mantiene (HU0008-4) con FK a `version_modelo.id_version`. `carga_datos`, `ejecucion_prediccion` y `activacion_modelo` se absorben en `ejecucion` (`tipo` + `detalle`) | Extensión |
| e | Migraciones | Nueva revisión `0003_oe2` que reemplaza el esquema; la BD local se recarga desde las fuentes | — |
| f | Permisos del DDL | `rol_api` recibe además INSERT y UPDATE en `ejecucion` (registra inferencias y activaciones). `rol_pipeline` recibe además INSERT y UPDATE en `provincia`, `distrito`, `semana_epidemiologica` y `version_modelo` (carga y publicación) | Corrección del documento |
| — | Persistencia | No es una `version_modelo` (el DDL solo admite `clasificacion` y `regresion`). La línea base se calcula al vuelo: casos de la semana de corte en `observacion_semanal` | Conforme al documento |
| — | Idempotencia de cargas | La huella va en `ejecucion.detalle->>'huella'`. En PostgreSQL, índice por expresión sobre ese campo para `tipo = 'ingesta'` | Extensión |
| — | Bloque de validación | La semilla `umbrales_aceptacion` incluye `"bloque": "temporada_2024"`; `cumple_umbrales` se calcula leyendo umbrales y bloque de la BD, no de `config.yaml` | Corrección del documento |
| — | Horizonte 3 | La API responde `no_disponible` con motivo «sin modelo para h=3»; las escrituras con h=3 devuelven 409 | Conforme al documento |
| — | `alerta.motivo` | Se mantiene como columna opcional (nullable) que explica el retiro | Extensión |
| — | Reproducibilidad del modelo | Una sola columna opcional `version_modelo.reproducibilidad` jsonb con `device`, `version_xgboost`, `plataforma`, `particion_temporal` y fechas de entrenamiento | Extensión |

## 2. Observaciones de datos (no son desviaciones de diseño)

- **`estado_cobertura`.** Las 30 485 filas del integrado tienen `source = verified` y ningún
  `casos_Dengue` nulo; con los datos actuales `estado_cobertura` vale siempre `verificado`.
  El EDA ya señaló (P5 en `docs/eda/problemas_y_decisiones.md`) que la cobertura no
  distingue cero notificado de sin registro.
- **Semana 53 de 2025.** El calendario MMWR la incluye (inicia 2025-12-28) y va a
  `semana_epidemiologica`; el panel termina en la semana 52 (inicio 2025-12-21), así que no
  tiene observaciones.
- **`poblacion_censo_2017`.** Viene de la columna `pob_censada_2017` del Excel bronze
  `data/bronze/socio/data_socio_2017_2025.xlsx`, que procede del INEI (Censos Nacionales
  2017 para `pob_censada_2017`; confirmado por Rosa el 2026-10-01). Coincide exactamente con
  la población 2017 de `socio_anual.csv` en los 65 distritos
  (`docs/feature_engineering/fase5_sociodemografia.md`).
- **Regla de brote, cortes y umbrales.** Los valores del manifiesto gold y de `config.yaml`
  (1,5 DE, 5 años, mínimo 2 casos; cortes 0,25/0,50/0,75; recall 0,80, precisión 0,60,
  F1 0,70, razón 0,85) coinciden con las semillas del DDL.
- **Claves OOS.** En el CSV del protocolo no se repite ningún `(ubigeo, origen_cierre)` entre
  bloques del mismo horizonte y variante; las OOS caben en la clave única de `prediccion`.
- **Variables de servicio.** Las variantes en uso (`base_6`, `base_6_poblacion_2017`) solo
  usan rezagos y resúmenes de casos, seno/coseno de la semana y `log(poblacion 2017)`;
  ninguna usa clima. `log_poblacion_censo_2017` del gold es exactamente `log(poblacion)` de
  `socio_anual.csv` para 2017.

## 3. Esquema

| Elemento | Documento | Código actual | Decisión |
|---|---|---|---|
| `provincia` | Tabla, PK `char(4)`, `nombre` | No existe; texto en `distrito.provincia` | **Adaptar**: se pobla con los 4 primeros dígitos del ubigeo |
| `semana_epidemiologica` | `id_semana = anio*100+semana`, fechas, `temporada` | No existe | **Adaptar**: desde `src/utils/calendario.py`; `temporada` con la regla del modelado (`asignar_temporada`, semana 35) |
| `parametro_sistema` | 3 semillas | No existe; valores en `config.yaml` | **Adaptar** + `seleccion_experimental` (temporal) y `bloque` en `umbrales_aceptacion` |
| `ejecucion` | Tabla única | `carga_datos`, `ejecucion_prediccion`, `activacion_modelo` | **Adaptar** (d); índice por expresión de la huella (PostgreSQL) |
| `distrito` | FK provincia, `numeric(9,6)` con rango Piura, `poblacion_censo_2017`, `activo` | `provincia` texto, `lat/lon` float, `geometria`, `motivo_geometria`, `fecha_actualizacion` | **Adaptar**; se eliminan `geometria`, `motivo_geometria` y `fecha_actualizacion`. El GeoJSON de `/mapa-riesgo` usa los centroides |
| `observacion_semanal` | PK `(ubigeo, id_semana)`, clima, enums, `fecha_extraccion`, `id_ejecucion` | `id` sustituto, `anio/semana/semana_inicio`, `procedencia`, `motivo`, `carga_id`, sin clima | **Adaptar**; se eliminan `motivo` y `fecha_corte_datos` |
| `version_modelo` | Columnas del DDL, booster en Storage | `huella`, `tipo`, `activa` bool, `artefacto` JSON y metadatos sueltos | **Adaptar**; se eliminan `huella`, `artefacto`, `origen`, `bloque`, `motivo_artefacto`, `criterios_validacion`; metadatos de reproducibilidad en `reproducibilidad` jsonb (extensión) |
| Versiones `persistencia` y `retrospectiva` | No caben | Existen | **Eliminar** |
| `ux_version_activa`, CHECK de activación | Sí | `uq_version_activa` sobre bool | **Adaptar** |
| `prediccion` | UNIQUE `(ubigeo, id_semana_corte, horizonte)` + UPSERT, `estado`, CHECK de coherencia | UNIQUE por ejecución, `tipo`, `casos_persistencia`, `alerta_modelo`, `version_persistencia_id`, `caracteristicas`, fechas | **Adaptar**; se pierde el historial de recálculos de un mismo corte (queda `id_ejecucion` y `fecha_generacion`). `casos_persistencia` y `alerta_modelo` se calculan al leer |
| `nivel_riesgo` | ENUM `bajo…muy_alto` | Texto `Bajo…Muy alto`, `Sin datos` | **Adaptar**; la API añade la etiqueta legible; «Sin datos» pasa a `no_disponible` |
| `alerta` | `cambio`, CHECK de nivel y retiro | Sin `cambio`; `horizonte`, `semana_inicio`, `motivo` | **Adaptar**; se eliminan `horizonte` y `semana_inicio`; `motivo` queda como extensión |
| `importancia_variable` | No existe | Existe | **Extensión** (d) |
| Tipos | ENUM nativos, `jsonb`, `numeric`, `timestamptz`, `char(n)`, identity | `String`, `JSON`, `Float` | **Adaptar** con variantes portables para SQLite |
| CHECK de ubigeo | Regex `~` | `substr` portable | **Adaptar**: regex en PostgreSQL; validación ORM (y `substr`) en SQLite |
| RLS, roles, GRANT, políticas | Sí | No | **Adaptar** (solo PostgreSQL) con los permisos ampliados de (f) |
| Nombres de restricciones | Los genera PostgreSQL | Convención `ck_<tabla>_<nombre>` | **Extensión** (no cambia la semántica; facilita `downgrade`) |

## 4. Carga, artefactos e inferencia

| Elemento | Documento | Código actual | Decisión |
|---|---|---|---|
| Fuente de `observacion_semanal` | Clima + casos + etiqueta | Casos/etiqueta de gold h=2, sin clima | **Adaptar**: casos y clima del integrado silver; `brote` y `umbral_brote_casos` de gold, sin recalcular |
| `fuente_casos` | ENUM | Texto | **Adaptar**: `excel_historico` ≤ 2024, `sala_situacional` 2025 |
| Booster | Storage `modelos/<codigo>.json` + hash | JSON en la BD | **Adaptar**: puerto `Almacenamiento` + adaptador local `models/storage/` (se añade a `estructuraRepo.md` y `.gitignore` en la Fase 2) |
| Umbrales y cortes | `parametro_sistema` | `config.yaml` | **Adaptar**; `config.yaml` solo siembra |
| Estado de validación | `cumple_umbrales` guardado | Calculado al vuelo | **Adaptar**: se calcula al publicar, con umbrales y bloque leídos de la BD |
| Inferencia | Por semana de corte desde la BD | Re-puntúa vectores guardados | **Adaptar** (c) |
| Modelo sin validar | `no_disponible` | Sirve experimentales | **Temporal** (a) |

## 5. API (base `/api/v1`)

| Elemento | Documento | Código actual | Decisión |
|---|---|---|---|
| Tablero | `GET /tablero/resumen` | `GET /tablero` | **Adaptar**, sin alias |
| Mapa | `GET /mapa-riesgo` (GeoJSON) | `GET /mapa` + `GET /distritos/geojson` | **Adaptar**: un solo GeoJSON con el riesgo en `properties` |
| Modelo activo | `GET /modelos/activo` | `GET /modelos` (lista) | **Adaptar**; se elimina la lista. Sin versión activa, responde la selección experimental marcada `experimental: true` |
| Inferencia | `POST /admin/inferencias` (semana de corte) | `POST /predicciones/recalcular` | **Adaptar**; h=3 → 409 |
| Activación | `POST /admin/modelos/{version}/activar` | `POST /modelos/{id}/activar` | **Adaptar**; separada de la inferencia; una versión con `cumple_umbrales = false` no se activa (409) |
| Campo `experimental` | No existe | `estado_validacion` | **Temporal** (a): calculado en predicciones, alertas y tablero |
| Filtros de alertas | horizonte, distrito, nivel | horizonte, ubigeo, estado | **Adaptar**: se añade `nivel`; `estado` queda como filtro extra |
| `GET /distritos/{ubigeo}`, `/observaciones`, `/alertas/{id}`, `/modelos/{id}`, `/modelos/{id}/variables` | Permitidos | Existen | **Extensión** |
| Escritura | Token de servicio | `X-API-Key` | Equivalencia aceptada en la especificación |
| Caché | No se menciona | Revisión por 3 tablas | **Adaptar** a `max(id_ejecucion)` |

## 6. Notas de implementación (Fase 1)

- **`importancia_variable`** recibe RLS y la política `servicio_importancia_variable`, igual
  que las nueve tablas del documento; `rol_pipeline` tiene INSERT/UPDATE sobre ella porque la
  publicación la escribe. Es parte de la extensión (d).
- **Índice de huella:** `ux_ejecucion_huella_ingesta` es único sobre `(detalle ->> 'huella')`
  con `WHERE tipo = 'ingesta' AND estado = 'exitosa'`: una carga fallida puede reintentarse con
  la misma huella. Solo en PostgreSQL; en SQLite la idempotencia la garantiza el código.
- **`downgrade` de `0003_oe2`** vuelve al esquema 0002 vacío y no elimina `rol_api` ni
  `rol_pipeline`: son objetos globales del clúster.
- **RLS y propietario:** la API y la carga locales se conectan como `denguekay`, dueño de las
  tablas; en PostgreSQL el dueño no está sujeto a RLS salvo `FORCE ROW LEVEL SECURITY`, que el
  DDL no usa. Las políticas aplican a `rol_api`/`rol_pipeline` (y a futuros usuarios de Supabase).
- **Portabilidad:** las CHECK con regex y `fecha_fin = fecha_inicio + 6` se crean solo en
  PostgreSQL; en SQLite se usan equivalentes (`substr`, `date(fecha_inicio, '+6 days')`) y la
  validación del ORM. Los nombres de restricciones siguen la convención `ck_<tabla>_<nombre>`.
- **Evidencia SQL offline** (`models/serving/migracion_0003_oe2_postgresql.sql`, no versionada):
  cubre `0002_serving → 0003_oe2`. No se puede generar desde `base` porque la migración
  histórica `0002_serving` consulta `version_modelo` y eso no funciona en modo `--sql`; es
  previo al refactor y no se edita una migración ya aplicada.
- **PostgreSQL 18.6 (Windows).** La verificación de la Fase 1 corrió en PostgreSQL 18.6 nativo
  sobre Windows, con un usuario sin superusuario (LOGIN, CREATEROLE); la verificación anterior
  del backend fue en PostgreSQL 17.5 sobre macOS. El DDL no mostró diferencias de
  comportamiento entre versiones: ENUM, identity, jsonb, regex, índices parciales y por
  expresión, RLS, roles (`DO … IF NOT EXISTS`), GRANT por columna y políticas funcionaron igual.

## 7. Cambios pendientes en el documento OE2

Se completará en la Fase 4. Por ahora:
- Permisos ampliados de `rol_api` y `rol_pipeline` (f), incluido `importancia_variable`.
- `bloque` en la semilla `umbrales_aceptacion`.
- Clave `seleccion_experimental` (mientras dure la desviación temporal).
- Índice de idempotencia sobre `ejecucion.detalle->>'huella'`.
- Extensiones: `importancia_variable`, `alerta.motivo`, `version_modelo.reproducibilidad`,
  endpoints extra y campo `experimental` en la API.
