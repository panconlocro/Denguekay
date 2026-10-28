# Encargo: refactorizar el backend para que cumpla el diseño del documento OE2

## Contexto

El backend actual (FastAPI + SQLAlchemy + Alembic, migraciones `0001_backend` y
`0002_serving`) funciona y está bien probado, pero **su esquema de BD y su API no
coinciden con el diseño aprobado en el documento OE2** (sección 5, Anexo B, Tabla 2).
Para la entrega TB1 la rúbrica exige un backend integrado con la BD y las HU críticas
del Sprint 1 programadas y funcionales, **coherentes con el diseño documentado**.

Fuente de verdad: `docs/backend/especificacion_oe2.md` y `docs/backend/ddl_oe2.sql`.
El código se adapta al documento. Reutiliza todo lo que ya sirve (carga, GX,
calendario MMWR, publicación, reevaluación con boosters, caché, errores uniformes,
benchmark): **esto es un refactor, no una reescritura**.

**Restricción de alcance:** no se despliega nada. Todo local: PostgreSQL local,
SQLite para pruebas, uvicorn local, artefactos en carpeta local. No configures
Supabase, Render ni credenciales remotas.

## Diferencias ya identificadas (verifícalas, no las des por ciertas)

Esquema:
1. Faltan `provincia`, `semana_epidemiologica`, `parametro_sistema` y la tabla
   unificada `ejecucion` (hoy existen `carga_datos`, `ejecucion_prediccion` y
   `activacion_modelo` por separado).
2. `distrito`: `provincia` es texto en vez de FK; `lat/lon` float sin CHECK; falta
   `poblacion_censo_2017` y `activo`; sobran `geometria`/`motivo_geometria`.
3. `observacion_semanal`: id sustituto en vez de PK `(ubigeo, id_semana)`; usa
   `anio/semana/semana_inicio` en vez de FK a `semana_epidemiologica`; faltan las
   columnas de clima, `fuente_casos` y `estado_cobertura` (enums), `fecha_extraccion`.
4. `version_modelo`: faltan `codigo`, `tarea`, `algoritmo`, `cumple_umbrales`,
   `estado` (enum), `ruta_artefacto`, `sha256_artefacto`, `fecha_activacion`; el
   booster vive en la BD (`artefacto` JSON) en vez de en Storage; `activa` bool en
   vez de `estado`.
5. `prediccion`: clave única por ejecución (historial) en vez de
   `UNIQUE (ubigeo, id_semana_corte, horizonte)` con UPSERT; falta `estado`
   disponible/no_disponible y su CHECK de coherencia; columnas extra (`tipo`,
   `casos_persistencia`, `alerta_modelo`, `version_persistencia_id`, `caracteristicas`).
6. `alerta`: falta `cambio` (enum) y el CHECK de nivel; `nivel` es texto.
7. Tipos: `JSON` en vez de `JSONB`, `String` en vez de ENUM; sin RLS ni roles.

API (base `/api/v1`): `/tablero` → `/tablero/resumen`; `/mapa` → `/mapa-riesgo`
(GeoJSON); `/modelos` (activa) → `/modelos/activo`; `/predicciones/recalcular` →
`POST /admin/inferencias`; `/modelos/{id}/activar` → `POST /admin/modelos/{version}/activar`;
`/distritos/geojson` se absorbe en `/mapa-riesgo`.

## Cómo trabajar

- Fase por fase. Al cerrar cada fase: corre los tests, invoca al subagente
  `revisor-backend`, pega su tabla y **detente** a esperar mi confirmación.
- Antes de cada fase, muéstrame el plan concreto (archivos a crear/modificar).
- Ante cualquier ambigüedad que cambie el diseño, **pregunta**; no decidas en silencio.
- Respeta `CLAUDE.md`: `data/` solo lectura, `ubigeo` string, rutas desde
  `src/utils/paths.py`, CRLF y UTF-8 en archivos existentes, español, Windows + PowerShell.
- No leas `.env`. Tests siempre en BD temporal.

## Fase 0 — Diagnóstico y decisiones (sin tocar código)

1. Lee `especificacion_oe2.md`, `ddl_oe2.sql`, `src/db/modelos.py`, las migraciones,
   `src/serving/`, `src/api/` y `tests/`. Confirma o corrige la lista de diferencias.
2. Escribe `docs/backend/desviaciones_oe2.md` con una tabla
   «Elemento | Documento | Código actual | Propuesta (adaptar / mantener como extensión / eliminar)».
3. Pregúntame explícitamente estas decisiones, con tu recomendación:
   a. **Modelos no validados.** El DDL impide activar una versión con
      `cumple_umbrales = false`, y hoy ningún modelo cumple los umbrales. Opciones:
      (i) aplicar el diseño estricto: sin versión activa, las predicciones se guardan
      `no_disponible` con motivo; (ii) mantener la demo con predicciones
      experimentales, p. ej. inferencia con la mejor `candidata` y marca
      `experimental` en `ejecucion.detalle` / respuesta de la API, documentado como
      desviación temporal. No elijas tú.
   b. **Predicciones retrospectivas (OOS)** para la serie: confirmar que se guardan
      como predicciones de cortes pasados dentro de la misma tabla (encajan en la
      clave única) o si se dejan fuera.
   c. **Vector de características:** hoy se guarda en `prediccion.caracteristicas`.
      Con el clima en `observacion_semanal`, ¿la inferencia reconstruye las
      características en memoria desde la BD (diseño del documento) o se mantiene el
      vector como extensión?
   d. **Tablas extra:** mantener `importancia_variable` como extensión (HU0008-4) y
      absorber `carga_datos`, `ejecucion_prediccion` y `activacion_modelo` en
      `ejecucion` (`tipo` + `detalle`). Confirmar.
   e. **Migraciones:** nueva revisión `0003_oe2` que reemplaza el esquema (la BD
      local se recarga desde las fuentes; no hay datos de producción). Confirmar.
4. Detente.

## Fase 1 — Esquema y migración

1. Reescribe `src/db/modelos.py` según el DDL: nombres, tipos, nulabilidad, PK/FK,
   UNIQUE, CHECK, índices (incluido el único parcial de versión activa) y ENUM
   portables (`sqlalchemy.Enum` nativo en PostgreSQL, CHECK en SQLite;
   `JSON().with_variant(JSONB, "postgresql")`).
2. Migración `0003_oe2` con `upgrade` y `downgrade` probados. En PostgreSQL: ENUM
   nativos, CHECK con regex, semillas de `parametro_sistema`, RLS, roles `rol_api` y
   `rol_pipeline` creados solo si no existen, GRANT y políticas. En SQLite se omiten
   RLS/roles.
3. Tests de esquema: concordancia ORM ↔ migración, cada CHECK rechaza un caso
   inválido, unicidad de versión activa, UPSERT de predicción, coherencia
   disponible/no_disponible, `alerta.nivel` solo alto/muy_alto.
4. Verifica `alembic upgrade head` / `downgrade -1` / `upgrade head` en SQLite y en
   PostgreSQL local. Genera `alembic upgrade head --sql` como evidencia en
   `models/serving/`.

## Fase 2 — Carga y artefactos

1. `cargar_datos`: poblar `provincia`, `distrito` (con población censo 2017),
   `semana_epidemiologica` (MMWR, `id_semana = anio*100+semana`) y
   `observacion_semanal` con clima, `fuente_casos` (`excel_historico` hasta 2024,
   `sala_situacional` 2025) y `estado_cobertura`. Registra cada carga como
   `ejecucion` tipo `ingesta` (hashes, GX y conteos en `detalle`). Idempotente.
   Lee solo de `data/` (sin escribir) y sin persistir feature engineering.
2. Adaptador de almacenamiento local (puerto `Almacenamiento`: `guardar`, `leer`,
   `existe`) sobre `models/storage/<bucket>/` (`modelos`, `geodatos`, `reportes`),
   ruta definida en `src/utils/paths.py` e ignorada por Git. Deja el puerto listo
   para un adaptador Supabase futuro, sin implementarlo.
3. Publicación: guarda el booster en `modelos/<codigo>.json`, registra
   `ruta_artefacto` y `sha256_artefacto`; al cargar, verifica el hash (409 si no
   coincide). `cumple_umbrales` se calcula con los umbrales de `parametro_sistema`.
4. Comprueba conteos contra las cifras de `docs/backend/fase1_bd.md`
   (65 distritos, 30 485 observaciones, etc.) y explica cualquier diferencia.

## Fase 3 — Inferencia, alertas y API

1. Inferencia: crea `ejecucion` tipo `inferencia`, hace UPSERT por
   `(ubigeo, id_semana_corte, horizonte)`, asigna `nivel_riesgo` con
   `cortes_riesgo`, y marca `no_disponible` con motivo cuando no hay versión
   utilizable (según la decisión 0.a).
2. Alertas: nivel alto/muy_alto; `cambio` nueva/se_mantiene/sube_nivel/baja_nivel
   respecto del corte anterior; retiro con `fecha_retiro`.
3. Activación: cambia `estado` a `activa` (archiva la anterior) y fija
   `fecha_activacion`, en una transacción, auditada como `ejecucion` tipo
   `mantenimiento`.
4. Routers alineados a la Tabla 2 con los nombres exactos; extensiones permitidas:
   `/distritos/{ubigeo}`, `/observaciones`, `/alertas/{id}`, `/modelos/{id}`,
   `/modelos/{id}/variables`. Elimina las rutas antiguas. POST con `X-API-Key`.
5. Actualiza los tests de API y regenera `docs/backend/openapi.json`.

## Fase 4 — Cierre y evidencia para TB1

1. Suite completa + cobertura (`src/db`, `src/serving`, `src/api`) ≥ 80 %, con
   números reales. Corre todo en **Windows PowerShell** con `.venv\Scripts\python`.
2. Prueba de humo local: PostgreSQL local → `alembic upgrade head` → `cargar_datos`
   → publicación → `uvicorn` → llamada real a cada endpoint de la Tabla 2. Guarda
   la salida en `docs/backend/evidencia_tb1.md` (sin credenciales).
3. Repite el benchmark local si cambió alguna consulta.
4. Actualiza `docs/backend/` (arquitectura, contrato_api, decisiones_tecnicas,
   operacion, trazabilidad_hu) y `README.md`.
5. Entrégame una lista final de **qué debe cambiar en el documento OE2** para
   reflejar las desviaciones aprobadas (tablas extra, columnas, endpoints extra),
   para que yo actualice el documento.
