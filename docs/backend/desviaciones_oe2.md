# Desviaciones del backend respecto del documento OE2

Fuente de verdad: [`especificacion_oe2.md`](especificacion_oe2.md) y [`ddl_oe2.sql`](ddl_oe2.sql).
Este archivo registra cada diferencia entre el documento y el código y la decisión
tomada para el refactor. **Estado: decisiones de la Fase 0 aprobadas por Rosa
(2026-10-01); Fases 1 a 4 implementadas (refactor cerrado).**

Código revisado: `src/denguekay/db/models.py`, migraciones `0001_backend` y `0002_serving`,
`src/denguekay/serving/`, `apps/api/` y los tests del backend (`test_db_backend`, `test_serving_*`,
`test_api_*`).

Tipos de desviación:
- **Extensión**: tabla o columna opcional que no rompe ninguna restricción del documento.
- **Temporal**: se retira cuando exista un modelo que cumpla los umbrales.
- **Corrección del documento**: el DDL tiene un defecto; el documento OE2 debe cambiar.
- **Observación de datos**: el diseño se cumple; lo que llama la atención son los datos actuales.

## 1. Decisiones aprobadas

| # | Tema | Decisión | Tipo |
|---|---|---|---|
| a | Modelos que no cumplen umbrales | Se respeta `CHECK (estado <> 'activa' OR cumple_umbrales)`: las versiones quedan `candidata`. Nueva clave `parametro_sistema.seleccion_experimental` con el código de la versión de clasificación y de regresión por horizonte. Desde la fase 4 de la API v1 la fija la publicación (`publish --seleccionar-experimental`, en la misma transacción que registra el paquete); hasta entonces la sembraba `load_data` desde `config.yaml`. La inferencia usa la versión `activa` si existe; si no, la de `seleccion_experimental` cuando `servir_no_validadas = true`; si es `false`, las predicciones se guardan `no_disponible` con motivo. La API devuelve `"experimental": true` en predicciones, alertas y tablero cuando la versión usada tiene `cumple_umbrales = false` (campo calculado, no columna). `ejecucion.detalle` registra que la ejecución fue experimental | Temporal |
| b | Predicciones OOS | Se guardan en `prediccion` como cortes pasados, con `id_version_clasificador` e `id_version_regresor` en NULL; el bloque y su origen van en `ejecucion.detalle`. No se crean versiones sin booster. Las métricas por bloque quedan en `version_modelo.metricas` de las versiones de servicio | Extensión (uso) |
| c | Vector de características | Se reconstruye en memoria desde la BD (`observacion_semanal` + `distrito.poblacion_censo_2017` + calendario) y se elimina `prediccion.caracteristicas`. Condición: un test compara, para una muestra de distritos y cortes, el vector reconstruido con el de gold (tolerancia 1e-9), y otro comprueba que la probabilidad resultante coincide con la del pipeline actual. Si no coinciden, se detiene el refactor | Conforme al documento |
| d | Tablas extra | `importancia_variable` se mantiene (HU0008-4) con FK a `version_modelo.id_version`. `carga_datos`, `ejecucion_prediccion` y `activacion_modelo` se absorben en `ejecucion` (`tipo` + `detalle`) | Extensión |
| e | Migraciones | Nueva revisión `0003_oe2` que reemplaza el esquema; la BD local se recarga desde las fuentes | — |
| f | Permisos del DDL | `rol_api` recibe además INSERT y UPDATE en `ejecucion` (registra inferencias y activaciones). `rol_pipeline` recibe además INSERT y UPDATE en `provincia`, `distrito`, `semana_epidemiologica` y `version_modelo` (carga y publicación) | Corrección del documento |
| — | Persistencia | No es una `version_modelo` (el DDL solo admite `clasificacion` y `regresion`). La línea base se calcula al vuelo: casos de la semana de corte en `observacion_semanal` | Conforme al documento |
| — | Idempotencia de cargas | La huella va en `ejecucion.detalle->>'huella'`. En PostgreSQL, índice por expresión sobre ese campo para `tipo = 'ingesta'` | Extensión |
| — | Bloque de validación | La semilla `umbrales_aceptacion` incluye `"bloque": "temporada_2024"`; `cumple_umbrales` se calcula leyendo umbrales y bloque de la BD, no de `config.yaml` | Corrección del documento |
| — | `alerta.motivo` | Se mantiene como columna opcional (nullable) que explica el retiro | Extensión |
| — | Reproducibilidad del modelo | Una sola columna opcional `version_modelo.reproducibilidad` jsonb con `device`, `version_xgboost`, `plataforma`, `particion_temporal` y fechas de entrenamiento | Extensión |
| — | `GET /configuracion` (contrato v1, C2; aprobada por Rosa el 29/10/2026) | Extensión de lectura con horizontes disponibles y por defecto, cortes, niveles, leyenda, corte vigente y nota experimental. Nueva clave `parametro_sistema.horizonte_por_defecto` = `{"horizonte": 4}`, sembrada por la migración de solo datos `0004_v1`; si falta, 503 `parametros_no_configurados` | Extensión |
| — | Intervalo de casos (contrato v1, C3; aprobada por Rosa el 29/10/2026) | Campos anulables `casos_intervalo_inferior`, `casos_intervalo_superior`, `nivel_intervalo` (0,80) y `motivo_intervalo` en las predicciones y el mapa. La migración `0005_v1` agrega a `prediccion` dos columnas anulables `numeric(10,2)` con el CHECK `ck_prediccion_intervalo_coherente` (las dos juntas, solo en predicciones disponibles, `0 ≤ inferior ≤ superior`); las escribe el predictor que los estime. El nivel no es una columna: es `parametro_sistema.nivel_intervalo_casos` = `{"nivel": 0.80}` (sembrado por la 0005); el manifiesto de cada paquete declara su nivel y la inferencia rechaza (409) uno distinto. Cambiar el parámetro obliga a volver a inferir | Extensión |
| — | Humedad en `double precision` (M5; aprobada por Rosa el 29/10/2026) | `observacion_semanal.hum_rel_media_pct` pasa de `numeric(5,2)` a `double precision` (migración `0005_v1`) y `load_data` deja de redondearla: con dos decimales, la media de 5 semanas de A3 difería de gold hasta 0,0043 y la paridad ≤ 1e-9 de la v2 era imposible. El CHECK `BETWEEN 0 AND 100` se mantiene. En SQLite (solo pruebas) el tipo declarado no cambia porque SQLite guarda el `REAL` completo | Corrección del documento |
| f″ | Selección experimental por la publicación (P4; aprobada por Rosa el 29/10/2026) | Qué modelo se sirve es un dato operativo: lo fija `publish --seleccionar-experimental`, no una migración (en la transacción del registro; si la publicación se reutiliza, en una transacción propia). La migración `0006_v1` (solo permisos, sin datos de modelos) crea vacía la fila `seleccion_experimental` si falta, da a `rol_pipeline` `UPDATE (valor, fecha_actualizacion)` en `parametro_sistema` y lo acota por RLS a esa fila: la política de servicio de la tabla pasa a ser solo de lectura y `pipeline_seleccion_experimental` permite esa actualización. Sin selección para un horizonte, la API responde como cuando no hay modelo | Corrección del documento |
| f′ | Permisos de `rol_pipeline` (D2; aprobada por Rosa el 29/10/2026) | Amplía la decisión f: `rol_pipeline` recibe además INSERT y UPDATE en `prediccion` (migración `0005_v1`) para las predicciones OOS de cada paquete. La inferencia vigente la hace la API (`rol_api`), no la publicación | Corrección del documento |
| — | Paquete de modelo (M2; aprobada por Rosa el 29/10/2026) | `version_modelo.ruta_artefacto` apunta al manifiesto `modelos/<codigo_paquete>/manifest.json` y `sha256_artefacto` es su SHA-256. El manifiesto declara el tipo de predictor, horizontes, variables, nivel del intervalo y el SHA-256 de cada archivo; la inferencia verifica todos al cargar (409 `artefacto_invalido`). Sin columnas nuevas | Extensión (uso) |
| — | Versión del contrato (C5) | `info.version` del OpenAPI = versión del contrato (semver; `1.1.0` desde la fase 4), cabecera `X-Version-Contrato` en todas las respuestas; `version_api` de `/salud` sigue siendo la versión de la aplicación | Extensión |
| — | Geometría del mapa (C4) | El contrato admite `Point`, `Polygon` y `MultiPolygon`; hoy se sirven centroides (`Point`) | Conforme al documento |

## 2. Observaciones de datos (no son desviaciones de diseño)

- **`estado_cobertura`.** Las 30 485 filas del integrado tienen `source = verified` y ningún
  `casos_Dengue` nulo; con los datos actuales `estado_cobertura` vale siempre `verificado`.
  El EDA ya señaló (P5 en `research/01_eda/docs/problemas_y_decisiones.md`) que la cobertura no
  distingue cero notificado de sin registro.
- **Semana 53 de 2025.** El calendario MMWR la incluye (inicia 2025-12-28) y va a
  `semana_epidemiologica`; el panel termina en la semana 52 (inicio 2025-12-21), así que no
  tiene observaciones.
- **`poblacion_censo_2017`.** Viene de la columna `pob_censada_2017` del Excel bronze
  `data/bronze/socio/data_socio_2017_2025.xlsx`, que procede del INEI (Censos Nacionales
  2017 para `pob_censada_2017`; confirmado por Rosa el 2026-10-01). Coincide exactamente con
  la población 2017 de `socio_anual.csv` en los 65 distritos
  (`research/02_feature_engineering/docs/fase5_sociodemografia.md`).
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
| `semana_epidemiologica` | `id_semana = anio*100+semana`, fechas, `temporada` | No existe | **Adaptar**: desde `src/denguekay/data/calendar.py`; `temporada` con la regla del modelado (`asignar_temporada`, semana 35) |
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
| Inferencia | `POST /admin/inferencias` (semana de corte) | `POST /predicciones/recalcular` | **Adaptar**; un horizonte sin modelo → 409 |
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
- **Evidencia SQL offline** (`docs/backend/evidencia/migracion_0003_oe2_postgresql.sql`, versionada;
  se regenera con `python -m denguekay.db.export_migration_sql`): cubre `0002_serving → 0003_oe2`. No se puede generar desde `base` porque la migración
  histórica `0002_serving` consulta `version_modelo` y eso no funciona en modo `--sql`; es
  previo al refactor y no se edita una migración ya aplicada.
- **PostgreSQL 18.6 (Windows).** La verificación de la Fase 1 corrió en PostgreSQL 18.6 nativo
  sobre Windows, con un usuario sin superusuario (LOGIN, CREATEROLE); la verificación anterior
  del backend fue en PostgreSQL 17.5 sobre macOS. El DDL no mostró diferencias de
  comportamiento entre versiones: ENUM, identity, jsonb, regex, índices parciales y por
  expresión, RLS, roles (`DO … IF NOT EXISTS`), GRANT por columna y políticas funcionaron igual.

## 6b. Notas de implementación (Fase 2: carga y artefactos)

Elecciones simples registradas sin consulta (modo de trabajo acordado):
- **`fecha_extraccion`** = instante de la ingesta en la BD (las fuentes no traen su fecha de
  extracción por fila).
- **Calendario:** `semana_epidemiologica` cubre desde 2017-S01 hasta un año después del corte
  (objetivos futuros de inferencia); `temporada = anio + (semana >= 35)`, la regla del modelado.
- **Clima y numeric del DDL:** clima redondeado a 2 decimales (`numeric(5,2)`, `numeric(7,2)`);
  `probabilidad_brote` a 4 (`numeric(5,4)`) y `casos_estimados` a 2. El nivel de riesgo se
  calcula sobre la probabilidad ya redondeada, para que coincida con el valor guardado.
- **Vector reconstruido:** usa `construir_filas_futuras` del modelado sobre el panel leído de la
  BD. Esa función exige tres fracciones censales 2017 que la BD no guarda (no son variables de
  los modelos de servicio): se completan con 0 y se descartan. Verificado con datos reales en 13
  cortes (845 filas): diferencia máxima con gold 1,8e-15. Cortes con origen anterior a
  2019-01-01 dan `no_disponible`: es la barrera de disponibilidad del censo que ya aplica el
  pipeline (`FECHA_SOCIO_2017`).
- **Códigos de versión:** `clf-h{h}-v{n}` / `reg-h{h}-v{n}`; un booster idéntico (mismo SHA-256 y
  mismo dataset) reutiliza su versión. `seleccion_experimental` no se actualiza sola: si una
  nueva publicación crea `v2`, hay que actualizar ese parámetro en la BD (desde la fase 4 de la API v1,
  con `publish --seleccionar-experimental`).
- **Predicciones OOS:** se importan los bloques temporada 2022, 2023, 2024 y calendario 2025
  (los mismos que publicaba el backend anterior); no generan alertas (son históricas) y su
  marca `experimental` sale de las versiones de servicio del mismo horizonte.
- **Alertas:** como máximo una alerta activa por distrito y horizonte (la del corte más reciente);
  al llegar un corte nuevo la anterior se retira con `fecha_retiro` y `motivo`. `cambio` compara con
  el nivel de la predicción de la semana de corte anterior (sin ella, `nueva`), por lo que recalcular un corte da el
  mismo resultado; inferir un corte pasado deja su alerta como `retirada` (historia).
- **Storage compartido:** `models/storage` es común a todas las BD locales y los códigos se
  reinician por BD; si `modelos/<codigo>.json` ya existe con otro contenido no se sobrescribe y se
  usa `modelos/<codigo>-<sha256[:12]>.json`. Un rollback puede dejar un artefacto sin versión
  (inofensivo: se identifica por su hash).
- **Auditoría de fallos:** las inferencias de la API que fallan (409/503) quedan como `ejecucion`
  `fallida`; la carga registra también los fallos de preparación (GX, linaje). Las observaciones
  que desaparezcan de la fuente no se borran (UPSERT sin borrado).
- **`config.yaml`:** se quitaron `riesgo`, `alerta_nivel_minimo` y `criterios_validacion`
  de `serving`; esos valores viven solo en `parametro_sistema`.
- **CPU frente a GPU:** el servicio predice en CPU. En este equipo XGBoost entrena en GPU y su
  `predict` difiere del booster en CPU en ~6e-8 (1 ULP de float32); no afecta al modelo.

## 6c. Notas de implementación (Fase 3: API)

- **Rutas:** las 10 de la Tabla 2 con sus nombres exactos más 5 extensiones (`/distritos/{ubigeo}`,
  `/observaciones`, `/alertas/{id}`, `/modelos/{id}`, `/modelos/{id}/variables`). Se eliminaron
  `/tablero`, `/mapa`, `/distritos/geojson`, `/modelos` (lista), `/predicciones/recalcular` y
  `/modelos/{id}/activar`, sin alias.
- **Corte vigente:** el último `id_semana_corte` generado por una inferencia operativa (publicación
  o API), no por la importación OOS. `/predicciones` acepta `corte` (anio*100+semana) para consultar
  cortes pasados; cada predicción indica `tipo` = `vigente` o `retrospectiva`.
- **h=3** (nota histórica de TB1; desviación retirada en la fase 4 de la API v1, cuando la v2 sirve h=3):
  las lecturas respondían 200 con `disponible: false` y motivo «sin modelo para h=3» (listas vacías; en el mapa,
  todos los distritos «Sin datos»); `POST /admin/inferencias` con h=3 respondía 409.
- **`/mapa-riesgo`:** GeoJSON `FeatureCollection` con un `Point` (centroide) por distrito; la
  referencia del proyecto no tiene polígonos, así que el bucket `geodatos` no se usa en TB1.
  Metadatos (horizonte, cortes, leyenda, `experimental`) van como miembros extra (RFC 7946).
- **`/modelos/activo`:** devuelve la versión en uso por tarea y horizonte: la `activa` o, en su
  defecto, la de `seleccion_experimental`, con `seleccion` y `experimental`.
- **`POST /admin/inferencias`:** cuerpo JSON `{horizonte, id_semana_corte?}`; sin corte usa la última
  semana observada. Inferir un corte pasado sobrescribe (UPSERT) la predicción OOS de ese corte y
  usa el modelo actual, que pudo ver datos posteriores: es una operación administrativa, no una
  evaluación histórica.
- **`POST /admin/modelos/{version}/activar`:** `{version}` es `id_version`. Exige
  `cumple_umbrales` (409 si no), archiva la activa previa, fija `fecha_activacion` y registra una
  `ejecucion` de tipo `mantenimiento`. No recalcula predicciones: se llama después a
  `/admin/inferencias`.
- **Errores 409:** `inferencia_no_disponible`, `artefacto_invalido`, `no_cumple_umbrales`, `ya_activa`.
- **Benchmark:** la activación no se mide (cambia el estado y hoy responde 409 por diseño); el
  reporte declara la cobertura incompleta.

## 6d. Notas de la Fase 4 (cierre TB1)

- **Prueba de humo:** la `DATABASE_URL` de `.env` (BD `denguekay`) rechazó la autenticación
  («password authentication failed for user denguekay»); según lo acordado, la prueba se hizo en
  `denguekay_pruebas` (PostgreSQL 18.6 local). Evidencia en `evidencia/evidencia_tb1.md`.
- **`test_seguimiento_mlflow`:** fallaba en Windows porque MLflow deja abierta su `mlflow.db`
  temporal. Se corrigió solo en el test (cierra esos motores antes de borrar la carpeta); no se
  tocó `src/modeling` (hoy `src/denguekay/model`).
- **Dependencias:** se añadió `httpx2` (TestClient de Starlette 1.x); `httpx` se conserva para el
  benchmark. Faltaban instalados `psycopg` y `coverage`, ya listados en `requirements.txt`.
- **Documentos de fases anteriores** (`fase1_bd.md` … `fase4_calidad.md`, `fase*_verificacion*.json`)
  describen el backend previo al refactor; se conservan como historia, sin actualizar.

## 7. Cambios que debe reflejar el documento OE2

Lista consolidada al cierre del encargo de la API v1 (fase 6, 29/10/2026). Cada punto remite a la decisión
que lo aprobó (sección 1 y `docs/backend/api_v1_decisiones.md`, incluidas las precisiones de las fases 5 y 6).

Correcciones del DDL (Anexo B):
1. **Permisos:** `GRANT INSERT, UPDATE ON ejecucion TO rol_api` (la API registra inferencias y
   activaciones) y `GRANT INSERT, UPDATE ON provincia, distrito, semana_epidemiologica,
   version_modelo, importancia_variable TO rol_pipeline` (carga y publicación).
2. **Semilla `umbrales_aceptacion`:** añadir `"bloque": "temporada_2024"` (bloque que decide la aceptación).
3. **Índice de idempotencia:** `CREATE UNIQUE INDEX ux_ejecucion_huella_ingesta ON ejecucion
   ((detalle ->> 'huella')) WHERE tipo = 'ingesta' AND estado = 'exitosa'`.
4. **Roles:** crearlos con `DO … IF NOT EXISTS` (re-ejecutable) y aplicar RLS/política también a
   `importancia_variable`.

Extensiones del esquema (sección 5, Tablas 9–14):
5. Tabla `importancia_variable` (`id_importancia`, `id_version` FK, `variable`, `importancia`, `rango`; HU0008-4).
6. `alerta.motivo` (text, opcional): explica el retiro.
7. `version_modelo.reproducibilidad` (jsonb, opcional): device, versión de XGBoost, plataforma,
   partición temporal y fechas de entrenamiento.
8. Parámetro `seleccion_experimental` en `parametro_sistema` (mientras ningún modelo cumpla los umbrales).
8b. Contrato v1 (migraciones `0004_v1` y `0005_v1`):
    - parámetros `horizonte_por_defecto` (`{"horizonte": 4}`) y `nivel_intervalo_casos` (`{"nivel": 0.80}`);
    - columnas anulables `prediccion.casos_intervalo_inferior` y `casos_intervalo_superior` (`numeric(10,2)`), con el CHECK
      `ck_prediccion_intervalo_coherente`;
    - `observacion_semanal.hum_rel_media_pct` en `double precision` (corrección: `numeric(5,2)` redondeaba la humedad que usa A3);
    - `GRANT INSERT, UPDATE ON prediccion TO rol_pipeline` (predicciones OOS de cada paquete).
8c. Migración `0006_v1` (fase 4): fila `seleccion_experimental` vacía si falta; `GRANT UPDATE (valor,
    fecha_actualizacion) ON parametro_sistema TO rol_pipeline`, acotado por RLS a la fila `seleccion_experimental`
    (política `pipeline_seleccion_experimental`; `servicio_parametro_sistema` pasa a `FOR SELECT`).

API (Tabla 2):
9. Endpoints extra: GET `/distritos/{ubigeo}`, `/observaciones`, `/alertas/{id}`, `/modelos/{id}`,
   `/modelos/{id}/variables`.
10. Parámetros: `corte` en `/predicciones`; `desde`/`hasta` en `/series`; filtro extra `estado` en
    `/alertas`; cuerpo `{horizonte, id_semana_corte}` en `POST /admin/inferencias`; `{version}` =
    `id_version` en la activación.
11. Campo calculado `experimental` en predicciones, alertas, tablero y modelos. Un horizonte sin modelo
    responde `no_disponible` («sin modelo para h=N») en lecturas y 409 en la inferencia; con la v2 los tres
    horizontes del documento tienen modelo (la desviación de h=3 se retiró en la fase 4).
12. `/mapa-riesgo` devuelve centroides (`Point`), no polígonos; el contrato admite `Point`, `Polygon` y
    `MultiPolygon` (C4).
12b. **Endpoint `GET /configuracion`** (C2): horizontes disponibles (leídos de la BD) y por defecto, cortes y
    niveles de riesgo, leyenda, corte vigente y nota experimental; 503 `parametros_no_configurados` si falta
    `horizonte_por_defecto`.
12c. **Intervalo de casos** (C3) en predicciones y mapa: `casos_intervalo_inferior`, `casos_intervalo_superior`,
    `nivel_intervalo` (0,80) y `motivo_intervalo`, anulables. En la v2 es el intervalo central de la NB2 de cada
    horizonte (cuantiles 0,10 y 0,90) y **no está calibrado**.
12d. **h=3 servido:** los tres horizontes del documento (2, 3 y 4) tienen modelo con la v2; los horizontes
    disponibles no están fijos en la API, salen de las versiones en uso (C1).
12e. **Versión del contrato** (C5): `info.version` = versión del contrato (`1.1.0`), cabecera
    `X-Version-Contrato` en todas las respuestas; `/salud.version_api` es la versión de la aplicación.

Operación y datos:
13. Storage: puerto con dos adaptadores, local (`models/storage/<bucket>/`) y Supabase Storage por HTTP
    (`STORAGE_BACKEND`), con los buckets privados del documento y verificación por SHA-256 de cada archivo.
14. Predicciones OOS del protocolo guardadas como cortes pasados (`id_version_*` NULL; bloque en
    `ejecucion.detalle`); persistencia calculada al vuelo, sin versión propia.
15. Modo demo experimental: versiones `candidata` servidas como experimentales hasta que una cumpla
    los umbrales (desviación temporal).
16. Paquete de modelo: `version_modelo.ruta_artefacto` apunta a `modelos/<codigo_paquete>/manifest.json`
    y `sha256_artefacto` es su hash; varias filas (una por tarea y horizonte) comparten el paquete y se
    activan por horizonte en pareja (§8).
17. Motor de predicción enchufable (M1): la API depende solo del puerto `Predictor` y de las tablas; cada tipo
    de paquete (hoy `v0_compact_xgb`, registrado, y `v2_e3_s4`, servido) es un módulo con su test. Un modelo nuevo
    no cambia el contrato.
18. Historia anterior a 2017 (M4): no se carga en la BD; los orígenes que la necesitan se publican como no
    disponibles con su motivo.

Despliegue (diseño físico, sección 3 del documento):
19. Render (plan gratuito) sin `preDeployCommand`: las migraciones no corren en Render; Rosa las corre desde su
    PC antes de cada release, y la API se conecta solo con un usuario que hereda `rol_api` (D2).
20. Configuración por entorno (`DATABASE_URL`, `API_KEY`, `CORS_ORIGINS`, `SERVIR_NO_VALIDADAS`,
    `STORAGE_BACKEND`, credenciales de Storage) sobre los valores por defecto de `config.yaml`; la API se instala
    con `requirements-api.txt`, sin las dependencias de investigación.
21. Conexión a Supabase por el *shared pooler* (IPv4; Render no tiene IPv6 saliente); en transaction mode se
    desactivan las sentencias preparadas (`DB_PREPARED_STATEMENTS=false`). Detalle: `despliegue.md`.
22. **Propuesta pendiente de aprobación (no implementada):** el ciclo semanal ejecuta un comando de inferencia (la
    misma `serving.inference.infer`) en GitHub Actions, en lugar de llamar a `POST /admin/inferencias`. Con 0,1 CPU,
    la inferencia de la v2 se estima en 28 a 50 s por horizonte, frente a los 5 s de la HU0016-3. El contrato no
    cambia (`despliegue.md` §8).

## 8. Modelo multi-salida: varias filas por paquete (aprobada, adaptada a E3·S4_s3)

Origen: encargo de arquitectura multi-horizonte (`research/04_horizon_architecture/docs/arquitectura_horizontes.md`, fase 5), propuesta para E3·S4_s2. **Aprobada por Rosa el 29/10/2026 (decisión M3 de `api_v1_decisiones.md`) y adaptada a la v2 (E3·S4_s3).** La fase 3 del encargo de la API v1 implementa el encaje genérico:
- **Implementado en la fase 3** para todo paquete:
  - una fila de `version_modelo` por `(tarea, horizonte)` que apunta al mismo manifiesto;
  - la activación por horizonte y en pareja;
  - la regla de brote (`parametro_sistema.regla_brote`) como entrada disponible para los predictores (`ServingInputs.outbreak_rule`).
- **Implementado en la fase 4** (servir la v2, predictor `v2_e3_s4`):
  - el umbral de brote de las semanas objetivo, calculado en memoria con `outbreak_label.future_outbreak_threshold`
    desde `observacion_semanal.casos_dengue` (no desde la columna redondeada); un test exige el mismo valor que gold;
  - `algoritmo = 'xgboost_multisalida_bn'`, `grupo_artefacto` = código del paquete y `umbral_probabilidad = 0,500`;
  - importancias SHAP por horizonte calculadas al publicar (no en la API);
  - códigos `v2-clf-h2-1` … `v2-reg-h4-1`;
  - el paquete: `booster.json`, `dispersion.json` (α por horizonte) y `platt.json` (a y b por horizonte); el
    intervalo de casos es el central de la NB2 al 0,80 y **no está calibrado** (Platt solo calibra la probabilidad);
  - h=3 tiene modelo: se retira la desviación «sin modelo para h=3».
- La v0 también es un paquete (cuatro boosters), con sus cuatro filas sobre el mismo manifiesto.

La tabla siguiente es la propuesta original:

| Tema | Propuesta | Tipo |
|---|---|---|
| Un modelo para 2 tareas y 3 horizontes | Se registran **seis filas** de `version_modelo`, una por `(tarea, horizonte)` con horizonte ∈ {2, 3, 4}, que comparten `ruta_artefacto` y `sha256_artefacto`. `algoritmo = 'xgboost_multisalida_bn'`; `variables`, `hiperparametros` y `metricas` son las de cada (tarea, horizonte); `umbral_probabilidad = 0,500`. Una clave `grupo_artefacto` dentro de `reproducibilidad` identifica a las seis filas hermanas. `prediccion.id_version_clasificador` e `id_version_regresor` apuntan a las filas (clasificación, h) y (regresión, h), igual que hoy. | Extensión (uso) |
| Activación | Se mantiene el índice único parcial de una versión activa por `(tarea, horizonte)`. La activación se hace **por horizonte y en pareja**: clasificación y regresión del mismo h salen de la misma salida del modelo, así que activar una sin la otra mezclaría artefactos. `POST /admin/modelos/{version}/activar` activa también la fila hermana del mismo horizonte, en una sola transacción, y lo registra en `ejecucion.detalle`. `cumple_umbrales` se evalúa por fila, como hoy. | Extensión (uso) |
| Artefacto | Paquete único: booster multi-salida, α de la binomial negativa por horizonte y calibradores Platt por horizonte. Se verifica con un SHA-256 al cargar. | Conforme al documento |
| Horizonte 3 | Se retiran la respuesta `no_disponible` («sin modelo para h=3») y el 409 de las escrituras con h=3. | Retiro de una desviación |
| Umbral de brote de semanas futuras | S4 necesita `umbral_brote_casos` de las semanas objetivo o+2, o+3 y o+4, que en producción aún no están en el panel. Se agrega una función que lo calcula con la misma regla de `src/denguekay/features/outbreak_label.py`: misma semana de los 5 años previos, semana 53 sumada a la 52, media + multiplicador · DE muestral, parámetros de `parametro_sistema`. Funciona también para semanas de un año todavía ausente. La acompaña un test que exige el mismo valor que gold en todas las semanas ya observadas. La inferencia la usa para convertir la media de casos en probabilidad; no es una variable de entrada. | Conforme al documento (cálculo en memoria, sin columna nueva) |
| Importancia de variables (HU0008-4) | `importancia_variable` por `id_version`: SHAP medio por horizonte de la salida correspondiente. | Conforme a la extensión (d) |

**Justificación.** La opción mantiene intacto el DDL del Anexo B: tablas, ENUM, CHECK e índice de versión activa. La única diferencia es de uso: varias filas comparten un artefacto y la activación se coordina por horizonte. Las alternativas (una sola fila con horizonte nulo o una tarea combinada) obligarían a cambiar `tarea_t`, el CHECK de `horizonte` y la semántica de las dos FK de `prediccion`, es decir, a corregir el documento OE2. El modelo elegido no cumple todavía los umbrales de la HU0007-4, así que se seguiría sirviendo como experimental según la decisión (a).
