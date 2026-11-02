# Encargo: API v1 definitiva, independiente del modelo, y rama `develop`

## Objetivo

Dejar la API en su **versión 1 definitiva** para que Nicolás construya el frontend sin depender
de los experimentos de modelado. Rosa va a seguir cambiando el modelo (variables, estrategia,
horizontes, calibración, incluso el algoritmo); **ninguno de esos cambios debe obligar a cambiar el
contrato de la API ni el frontend**.

Hoy la API está atada a la v0: 4 boosters XGBoost (clasificación y regresión × h=2 y h=4),
variantes `base_6*` fijas en `serving/settings.py` (`ALLOWED_VARIANTS`) y en
`model/future_rows.py`, vector de variables con solo rezagos de casos, calendario y población 2017,
h=3 «sin modelo», y un artefacto que siempre es un booster XGBoost en JSON. La v2 vigente
(`models/registry/v2/ficha.md`, `denguekay.model.frozen_configs.CONFIG_2026`) ya no cabe en eso:
es **un regresor multisalida (E3) que predice t+2, t+3 y t+4**, con conteo `count:poisson`, probabilidad
`P(casos ≥ k)` de una binomial negativa NB2, calibración Platt y variables B3 (necesitan historia
anterior a 2017, `SILVER_EPI_HISTORICAL`) y A3 (clima, media de 5 semanas).

La idea central:

```
Frontend ──► Contrato v1 (apps/api, congelado y vigilado por un test)
                 │
                 ▼
             Tablas OE2 (prediccion, version_modelo, alerta, …)
                 ▲
                 │  escribe
Motor de predicción enchufable (src/denguekay/serving/predictors/)
   ├─ predictor "v0"  (adaptador de lo actual)
   ├─ predictor "v2"  (E3 · S4_s3 · Platt)
   └─ predictor "vN"  ← lo que Rosa agregue después, sin tocar apps/api
```

La API solo conoce las tablas y un **puerto `Predictor`**. Cada versión de modelo se publica como un
**paquete** (manifiesto + archivos en Storage) que dice qué predictor lo ejecuta. Un modelo nuevo
implica una clase de predictor nueva con su test, y una publicación; no implica cambiar routers,
esquemas ni el frontend.

## Fuentes de verdad y reglas

- Contrato y esquema: `docs/backend/especificacion_oe2.md`, `docs/backend/ddl_oe2.sql`,
  `docs/backend/contrato_api.md`, `docs/backend/openapi.json`. Desviaciones nuevas: en
  `docs/backend/desviaciones_oe2.md` y **solo con aprobación de Rosa**.
- Diseño físico del documento OE2 (sección 3): API FastAPI en un Web Service de Render (512 MB de
  RAM, sistema de archivos efímero), PostgreSQL y Storage en Supabase, frontend en Vercel, ciclo
  semanal en GitHub Actions que llama a `POST /admin/inferencias`. El constructor de
  características (HU0006) corre **dentro de la API**. Todo lo que diseñes debe poder desplegarse así.
- Respeta `CLAUDE.md`, `CONTRIBUTING.md`, `docs/architecture.md` (lee este último antes de crear
  cualquier archivo y actualízalo en el mismo cambio) y el ADR 0001: `data/` es de solo lectura,
  `ubigeo` es texto, las rutas salen de `config/paths.py`, el código va en inglés, los esquemas y
  handlers de la API conservan sus nombres en español (D2), CRLF y UTF-8 en archivos existentes,
  Windows + PowerShell con `.\.venv\Scripts\python`.
- **No despliegues nada** y no crees cuentas ni credenciales remotas. La fase 5 deja todo
  preparado; desplegar es un encargo aparte que Rosa autoriza.
- No leas `.env`. Tests siempre en BD temporal (SQLite o la PostgreSQL desechable del CI).
- No rompas las guardas: `tests/test_equivalence.py` (V1 y V2 bit a bit), `tests/test_layout.py`
  y la línea base de `tests/fixtures/equivalence/`, que **nunca** se regenera para que un test pase.
  Excepción prevista: la guarda «el contrato de `openapi.json` no cambia» se reemplaza en la
  fase 2 por la del contrato v1, con aprobación explícita de Rosa.

## Cómo trabajar

- Fase por fase. Antes de cada fase muestra el plan concreto (archivos a crear y modificar). Al
  cerrarla: suite completa, cobertura, subagente `revisor-backend` (pega su tabla) y **detente**
  a esperar la confirmación de Rosa.
- Una rama por fase, **saliendo de `develop`** (desde la fase 0), con PR hacia `develop`. Rosa
  mergea con «Create a merge commit». Nunca reescribas historia publicada.
- Ante una ambigüedad que cambie el contrato, el esquema o el despliegue, **pregunta** y da tu
  recomendación; no decidas en silencio.
- Al cerrar cada fase, resume en el chat, en texto plano y en español, qué cambió y qué rutas o
  comandos son nuevos.

---

## Fase 0 · Rama `develop` y flujo de trabajo

Rama: `chore/develop-branch` (sale de `main` actualizado; es la última que lo hace).

1. Comprueba el estado: el PR de `refactor/registry-and-docs` debe estar mergeado en `main`
   (si no, detente y avisa) y debe existir el tag `restructure-done` del cierre del ADR 0001
   (si falta, propónselo a Rosa, porque su creación es parte de ese cierre).
2. Crea `develop` desde `main` y súbela (`git push -u origin develop`).
3. Escribe el ADR `docs/decisions/0002-develop-branch.md` con este flujo:
   - `main` = producción. Cada merge a `main` despliega (Render y Vercel, según OE2). Solo
     recibe PR desde `develop` (release) o desde `fix/` (hotfix).
   - `develop` = integración. Todas las ramas `feat/`, `fix/`, `refactor/`, `docs/`, `chore/` y
     `exp/` salen de `develop` y vuelven por PR a `develop` con el CI en verde.
   - Release: PR `develop → main` con merge commit cuando Rosa lo decida (por sprint o entrega).
   - Hotfix: `fix/` desde `main` → PR a `main`; luego PR `main → develop` (merge, sin rebase).
   - Experimentos de Rosa: `exp/<nombre>` desde `develop`; los estudios van en
     `research/06_<nombre>/` y nunca tocan `apps/`.
   - Frontend de Nicolás: `feat/web-<pantalla>` desde `develop`, solo dentro de `apps/web/`.
   - Los tags (`model/vN`, `study/*`) se ponen donde se congela el commit; los merge commits
     conservan los hashes en `main`.
4. Actualiza `CONTRIBUTING.md`, `CLAUDE.md`, `AGENTS.md`, `README.md` y `docs/architecture.md`
   (allí donde digan «solo `main` es permanente» o «las ramas salen de `main`»).
5. CI: `.github/workflows/backend.yml` ya corre en todo `push` y `pull_request`; confírmalo. Si
   hace falta, limita `push` a `main`, `develop` y ramas con PR, para no duplicar corridas.
6. Escribe para Rosa los pasos en la web de GitHub que no se pueden hacer desde git (no hay `gh`
   en su PC): rama por defecto → `develop`; reglas de protección para `main` y `develop` (exigir
   PR, exigir los checks del CI, prohibir force push y borrado); en *Settings → General → Pull
   Requests* dejar habilitado solo «Allow merge commits» y activar «Automatically delete head
   branches».
7. Guarda este encargo en `docs/backend/prompt_api_v1.md` en esta misma rama.
8. PR `chore/develop-branch → develop`. Detente.

## Fase 1 · Diagnóstico y decisiones (sin tocar código)

Rama: `docs/api-v1-decisions`.

1. Lee `apps/api/`, `src/denguekay/serving/`, `src/denguekay/db/`, `model/future_rows.py`,
   `model/frozen_configs.py`, `model/probabilistic_output.py`, `model/horizon_strategies.py`,
   `features/onset_features.py`, `models/registry/`, `configs/config.yaml`, los tests de `api`,
   `serving` y `db`, y la sección 3 del documento OE2 (resumida arriba).
2. Haz un inventario de **todo lo que hoy ata la API o el serving a la v0**: horizontes fijos,
   tipos `Horizon`, `ALLOWED_VARIANTS`, `compact_variants`, `BASE_PARAMS`, `TASKS`, la pareja
   clasificador/regresor, `serialize_booster`/`load_booster`, `reference_from_db` (rellena con 0
   las fracciones socio), `OOS_BLOCKS`, el motivo «sin modelo para h=3», `servir_no_validadas`,
   `seleccion_experimental`, etc. Indica cada archivo y línea.
3. Escribe `docs/backend/api_v1_decisiones.md` con el inventario y las decisiones de abajo.
   **Pregúntale a Rosa cada una**, con tu recomendación y el porqué. No elijas tú.

   **Contrato (lo que ve el frontend)**
   - **C1. Horizontes.** Recomendación: la API acepta 2, 3 y 4 (como el DDL) y los horizontes
     disponibles salen de la BD (versiones publicadas), no del código. Un horizonte sin modelo
     responde como hoy h=3 (`disponible: false` y motivo genérico «sin modelo para h=N»).
   - **C2. Endpoint de configuración** (extensión): `GET /configuracion` con horizontes
     disponibles, horizonte por defecto, cortes y etiquetas de riesgo, leyenda del mapa, semana de
     corte vigente, `experimental` y su nota. Así el frontend no tiene nada en código duro.
   - **C3. Incertidumbre de casos:** campos opcionales y anulables `casos_intervalo_inferior` y
     `casos_intervalo_superior` (y su nivel, p. ej. 0,80), `null` con motivo si el modelo no los da.
     La v2 puede calcularlos con NB2. Agregarlos ahora evita romper el contrato después.
   - **C4. Geometría del mapa:** el contrato admite `Point`, `Polygon` y `MultiPolygon` desde ya
     (hoy centroides; polígonos cuando haya una fuente con licencia, según la Tabla 35 de OE2).
   - **C5. Versión del contrato:** `info.version = "1.0.0"` en OpenAPI, semver documentado en
     `contrato_api.md`, cabecera `X-Version-Contrato` en todas las respuestas. Cambio aditivo =
     minor; cambio que rompe = `/api/v2` y `feat(api)!`.
   - **C6. Fuera de v1** (confirmar): explicación por distrito, autenticación de usuarios finales
     y escrituras desde el navegador.

   **Motor y esquema**
   - **M1. Puerto `Predictor`.** Propuesta: `Predictor.predict(inputs, cutoff, horizons) ->
     DataFrame[ubigeo, horizonte, probabilidad_brote, casos_estimados, casos_intervalo_*]`, con
     `required_inputs` declarados (casos, clima, población, historia previa). Un registro de tipos
     (`"v0_compact_xgb"`, `"v2_e3_s4"`, …) en `src/denguekay/serving/predictors/`.
   - **M2. Paquete de modelo.** Propuesta: `modelos/<codigo_paquete>/manifest.json` + archivos
     (boosters, parámetros de Platt, dispersión α, umbral k), cada uno con SHA-256. El manifiesto
     declara: tipo de predictor, horizontes, variables, versión mínima del paquete `denguekay`,
     métricas, `cumple_umbrales` y huella de comportamiento (D1 del ADR 0001).
   - **M3. Encaje en `version_modelo`.** El DDL tiene una fila por `(tarea, horizonte)`, pero la v2
     es un solo modelo para todo. Opciones: (a) sin cambiar el esquema, una fila por tarea y
     horizonte que apunta al mismo paquete, con activación atómica del paquete completo;
     (b) una tabla nueva `paquete_modelo` (desviación de OE2). Recomendación: (a), y documentarla.
     En la v2, ¿la «clasificación» es la probabilidad derivada del conteo? Confírmalo con Rosa.
   - **M4. Historia anterior a 2017 para B3.** La BD solo tiene observaciones desde 2017. Opciones:
     cargar las semanas previas de `epi_piura_semanal.csv` en `observacion_semanal` (con su
     calendario), o una tabla de referencia. Propón una y explica su impacto en el DDL.
     Esa historia (2000–2024) también alimenta la regla de brote (5 años previos, `manifest_fase6.json`).
     Ya verificado con Rosa: Montero, Sicchez y Lagunas (sierra) no aparecen en la historia porque
     nunca tuvieron casos; la ausencia se trata como cero (es correcto, no es un dato faltante).
   - **M7. B3 en gold.** Gold h=2 ya tiene A3 (`*_media5_h2`) pero no B3; hoy la v2 se entrena con
     gold h=2 + B3 en memoria desde silver. Por la regla 3 de `CLAUDE.md`, **propón** (no ejecutes) el
     cambio en `features/gold.py` para que el equipo regenere gold con el notebook 10, y di si la
     fase 4 debe esperar ese gold nuevo o puede entrenar con gold + B3 en memoria como el estudio.
   - **M5. Clima de las variables A3.** Confirma que `observacion_semanal` tiene todo lo que A3
     necesita (media de 5 semanas hasta el origen) y que da los mismos valores que gold.
   - **M6. Qué se sirve.** Recomendación: la v2 como selección experimental (h=2, 3 y 4) y la v0
     se conserva como predictor registrado (para reproducir lo que ya está en la BD).

   **Despliegue y trabajo del frontend**
   - **D1. Datos para Nicolás.** Él no tiene `data/` (está fuera de Git). Opciones: (a) un volcado
     de una BD de demostración (SQLite o `pg_dump`) generado con un comando y compartido fuera de
     Git; (b) una API de desarrollo en Render conectada a un proyecto de Supabase de desarrollo
     (exige levantar la restricción de `CLAUDE.md`). Recomendación: (a) ya en la fase 2 y (b) en
     el encargo de despliegue.
   - **D2. Roles en Supabase:** con qué rol se conecta la API (`rol_api`) y cuál usa la
     publicación (`rol_pipeline`), y cómo se mantiene RLS. Solo diseño; no se crea nada remoto.
4. PR con el documento. Detente hasta tener todas las respuestas.

## Fase 2 · Contrato v1 congelado (Nicolás arranca al cerrar esta fase)

Rama: `feat/api-contract-v1`.

1. Aplica a `apps/api/schemas.py`, routers y `queries.py` las decisiones C1–C5. Solo cambios
   **aditivos** o de horizontes; no renombres campos existentes. Los handlers siguen en español (D2).
2. Quita de `apps/api/` toda referencia a horizontes, variantes o tareas fijas: se leen de la BD.
3. **Guarda del contrato:** un test que genera el esquema OpenAPI (sin los ejemplos de BD real) y
   lo compara con un archivo versionado (`docs/backend/openapi_v1.json` o el que acuerdes). Si
   cambia, el CI falla con un mensaje que explica: cambio aditivo → subir minor y regenerar a
   propósito; cambio que rompe → no se permite en `/api/v1`. Reemplaza la guarda anterior
   del ADR 0001 con aprobación de Rosa.
4. Test de contrato con datos: cada endpoint de la Tabla 2 y las extensiones devuelve una
   respuesta que valida contra el esquema, con h=2, 3 y 4 y con un horizonte sin modelo.
5. Regenera `openapi.json`, actualiza `contrato_api.md` (v1.0.0, semver y changelog del contrato)
   y `trazabilidad_hu.md`.
6. Entrega para Nicolás `docs/backend/guia_frontend.md`: cómo levantar la API local, cómo
   obtener la BD de demostración (D1), la URL base, cómo generar tipos TypeScript desde el
   OpenAPI (p. ej. `openapi-typescript`; verifica el nombre y la versión vigentes), y las reglas
   de `apps/web/README.md` (faltantes ≠ cero, `experimental` visible, `ubigeo` texto). Actualiza
   `apps/web/README.md` para que apunte a esta guía.
7. Comando reproducible para generar la BD de demostración (decisión D1), que corre en la PC de
   Rosa y no escribe en `data/`.
8. PR → `develop`. Detente.

## Fase 3 · Motor de predicción enchufable

Rama: `refactor/pluggable-predictor`. **Sin cambios de comportamiento para la v0**: las
predicciones que la v0 escribe en la BD deben ser idénticas antes y después (prueba explícita).

1. Puerto `Predictor`, registro de tipos y paquete de modelo según M1 y M2.
2. `ServingInputs` construido desde la BD con todo lo que puedan pedir los predictores: casos,
   clima, población 2017 (y fracciones si se cargan), historia previa (M4), calendario MMWR.
   Construcción en memoria; nada se persiste ni se escribe en `data/`.
3. Adaptador `v0_compact_xgb` que envuelve lo actual (`build_future_rows`, boosters, `log1p`).
4. `inference.infer` y `publish` trabajan con paquetes y predictores; desaparecen
   `ALLOWED_VARIANTS`, los horizontes fijos y la suposición «un booster por tarea».
5. Migración Alembic nueva **solo si** M3 o M4 la exigen, con `upgrade`/`downgrade` probados en
   SQLite y PostgreSQL. Las migraciones son la autoridad del esquema; nunca `create_all`.
6. Verificación del SHA-256 de cada archivo del paquete al cargarlo (409 `artefacto_invalido`
   como hoy) y caché en memoria por SHA.
7. Test de arquitectura: `apps/api` no importa nada de `denguekay.model`, `denguekay.features`
   ni de un predictor concreto; solo el puerto y las tablas.
8. Documenta en `docs/backend/operacion.md` **cómo se publica un modelo nuevo sin tocar la API**:
   clase de predictor + test de paridad → construir paquete → publicar como `candidata` →
   seleccionar como experimental o activar.
9. PR → `develop`. Detente.

## Fase 4 · Servir la v2 (prueba de que el diseño aguanta un modelo distinto)

Rama: `feat/serve-model-v2`.

1. Predictor `v2_e3_s4` que reproduce `CONFIG_2026`: E3 multisalida, `count:poisson` con
   `base_margin`, NB2 con α dentro de la muestra, `k = max(⌊umbral⌋ + 1, 2)`, Platt cronológico y
   semilla 17. Reutiliza las funciones de `denguekay.model` (no copies lógica).
2. **Test de paridad de variables** (evita el sesgo entrenamiento/servicio): para varios orígenes
   históricos, el vector construido desde la BD es igual al que se construye desde gold y silver
   (columnas base_6, B3 y A3), distrito por distrito.
3. **Test de paridad de predicciones:** el paquete entrenado con los datos cerrados a un corte,
   servido desde la BD, da las mismas predicciones que `frozen_configs.predict` con ese mismo
   ajuste (tolerancia ≤ 1e-9 en CPU con `n_jobs` fijo, como D1). Si no pueden coincidir, explica
   por qué y pregunta.
4. Publica la v2 (h=2, 3 y 4) como `candidata`, con `cumple_umbrales` calculado desde
   `parametro_sistema`, y sírvela como selección experimental (M6). El contrato no cambia: el
   test de la fase 2 sigue en verde sin regenerar nada.
5. Actualiza `models/registry/v2/ficha.*` («servida») y `CHANGELOG.md`, y quita el desvío
   «sin modelo para h=3» de `desviaciones_oe2.md` (la fila «Retiro de una desviación» ya existe).
6. Benchmark local (`apps/api/tools/benchmark.py`): p95 de lecturas e inferencia con la v2.
7. PR → `develop`. Detente.

## Fase 5 · Listo para Render y Supabase (sin desplegar)

Rama: `chore/deploy-ready`.

1. **Configuración por entorno:** `DATABASE_URL`, `API_KEY`, `CORS_ORIGINS` (lista; hoy es un
   solo origen fijo en `config.yaml`), `STORAGE_BACKEND` (`local` | `supabase`), credenciales de
   Storage, `SERVIR_NO_VALIDADAS`. `config.yaml` da los valores por defecto y el entorno los
   reemplaza. Actualiza `.env.example` sin secretos.
2. **Adaptador `SupabaseStorage`** del puerto `Storage` (HTTP con `httpx`, sin SDK si no hace
   falta), con caché local en un directorio temporal y verificación de SHA-256. Tests con un
   transporte simulado; nada contra servicios reales. Verifica la API de Supabase Storage en su
   documentación oficial antes de escribirlo.
3. **Dependencias livianas:** `requirements-api.txt` (o un extra `[api]` en `pyproject.toml`)
   solo con lo que la API necesita en ejecución. Test: importar `apps.api.main` no importa
   `mlflow`, `great_expectations`, `optuna`, `matplotlib` ni `geopandas` (separa `publish` y
   `load_data` del arranque de la API si hace falta).
4. **Memoria:** mide el RSS de la API después de cargar el paquete de la v2 y responder cada
   endpoint; debe quedar con margen bajo los 512 MB de Render. Reporta la cifra medida.
5. **Archivos de despliegue:** `render.yaml` (Blueprint) o `Dockerfile`, lo que convenga para el
   plan gratuito: comando de build, `alembic upgrade head` antes de arrancar, `uvicorn` en
   `$PORT`, health check en `/api/v1/salud`. Verifica en la documentación vigente de Render qué
   opciones existen en el plan gratuito (p. ej. si hay comando previo al despliegue) y en la de
   Supabase cómo conectarse con psycopg 3 a través del pooler (sentencias preparadas). No inventes
   opciones.
6. Job del CI que instala solo `requirements-api.txt` y arranca la API con SQLite (prueba de humo).
7. `docs/backend/despliegue.md`: pasos para Render, Supabase (BD de desarrollo y de producción,
   Storage, roles D2) y Vercel, y qué rama despliega cada servicio (`main` a producción). Cubre los
   criterios 3 y 4 de la HU0018 en lo que se pueda sin desplegar.
8. Actualiza la regla «Alcance TB1» de `CLAUDE.md` solo si Rosa lo aprueba.
9. PR → `develop`. Detente.

## Fase 6 · Cierre

1. Suite completa en Windows (PowerShell) y en el CI (Linux, Windows, macOS y PostgreSQL),
   cobertura ≥ 80 % en `apps/api`, `serving` y `db`, con cifras reales.
2. Prueba de humo completa en local: PostgreSQL → `alembic upgrade head` → `load_data` → publicar
   v2 → `uvicorn` → cada endpoint con h=2, 3 y 4. Evidencia en `docs/backend/evidencia/` sin
   credenciales.
3. `revisor-backend` final y su tabla.
4. Lista para Rosa de **qué cambiar en el documento OE2** (desviaciones nuevas, endpoint de
   configuración, paquete de modelo, h=3 servido, intervalos).
5. Propón el PR de release `develop → main` y el tag de la API (`api/v1.0.0`, si Rosa lo acepta);
   no lo mergees tú.
