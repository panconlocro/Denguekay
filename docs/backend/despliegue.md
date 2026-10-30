# Despliegue en Render, Supabase y Vercel

Fase 5 del encargo de la API v1 (`docs/backend/prompt_api_v1.md`). El repositorio queda **preparado** para
desplegar, pero desde el código y los tests no se despliega nada ni se conecta a servicios reales. El despliegue
lo hace Rosa a mano, siguiendo estos pasos. Las opciones de Render y Supabase se verificaron en su documentación
oficial el 29/10/2026 (fuentes al final). Lo que no está documentado o no se pudo confirmar se marca
**no verificado**.

Diseño físico (documento OE2, sección 3): la API FastAPI corre en un Web Service de Render (plan gratuito, 512 MB
de RAM y sistema de archivos efímero); PostgreSQL y Storage están en Supabase; el frontend, en Vercel. El ciclo
semanal en GitHub Actions llama a `POST /api/v1/admin/inferencias`; ese flujo no es parte de esta fase.

## 1. Qué rama despliega cada servicio

| Servicio | Rama | Cómo |
|---|---|---|
| Render (API de producción) | `main` | `render.yaml`: `branch: main` y `autoDeployTrigger: checksPass`, que despliega cuando el CI del commit pasa |
| Supabase (BD y Storage de producción) | — | No se despliega desde Git: Rosa corre las migraciones desde su PC antes de cada release (sección 3) |
| Supabase (BD y Storage de desarrollo) | `develop` y ramas | Proyecto aparte; Rosa migra y publica desde su PC |
| Vercel (frontend) | `main` = producción; las demás ramas generan *preview deployments* | Comportamiento por defecto de Vercel con Git |

`develop` no despliega en Render. Un release es el PR `develop → main` (ADR 0002); al mergearlo con el CI en verde,
Render despliega la API y Vercel, el frontend.

## 2. Variables de entorno

`configs/config.yaml` da los valores por defecto y el entorno los reemplaza (`denguekay.serving.settings`). Una
variable vacía se ignora. Plantilla sin secretos: `.env.example`.

| Variable | Uso | En Render |
|---|---|---|
| `DATABASE_URL` | Conexión de la API (`postgresql+psycopg://…?sslmode=require`), con un usuario que hereda `rol_api` | secreto (`sync: false`) |
| `MIGRATION_DATABASE_URL` | Conexión de `alembic upgrade head`, con el dueño del esquema. Vacía: alembic usa `DATABASE_URL` | **no se define**: solo en la PC de Rosa (sección 3) |
| `DB_PREPARED_STATEMENTS` | `false` desactiva las sentencias preparadas de psycopg 3 (`prepare_threshold=None`) | `true` (session mode) |
| `API_KEY` | Clave de escritura (`X-API-Key`) | `generateValue: true` |
| `CORS_ORIGINS` | Orígenes del frontend, separados por comas, sin barra final ni `*` | secreto (se completa al crear) |
| `SERVIR_NO_VALIDADAS` | `true` \| `false`: servir la selección experimental | `true` |
| `STORAGE_BACKEND` | `local` (`models/storage/`) \| `supabase` | `supabase` |
| `SUPABASE_URL` | `https://<ref>.supabase.co` | secreto |
| `SUPABASE_SECRET_KEY` | Clave secreta del proyecto (`sb_secret_…`, o la `service_role` heredada) | secreto |
| `STORAGE_CACHE_DIR` | Caché de los archivos descargados. Vacía: carpeta temporal del sistema | sin definir |
| `DENGUEKAY_XGB_DEVICE`, `DENGUEKAY_XGB_NJOBS` | XGBoost en CPU con un hilo | `cpu`, `1` |
| `PYTHON_VERSION` | Versión de Python en Render (debe ser completa, p. ej. `3.12.10`) | `3.12.10` |

## 3. Render (API)

### Lo que permite el plan gratuito (verificado)

- 0,1 CPU y 512 MB de RAM (`plan: free` en la especificación del Blueprint).
- Se duerme tras 15 minutos sin tráfico, y despertarlo toma alrededor de un minuto.
- Sistema de archivos efímero: los cambios se pierden en cada redespliegue, reinicio o suspensión. Por eso la API
  no guarda nada en disco salvo la caché de Storage, que se puede perder sin consecuencias.
- Sin discos persistentes, sin *one-off jobs* y sin shell.
- 750 horas gratis por *workspace* al mes; al agotarlas, Render suspende los servicios gratuitos hasta el mes
  siguiente.
- **Sin `preDeployCommand`:** la página de despliegues lo ofrece solo para *paid web services*, *private services* y
  *background workers*. Render tampoco migra en el `startCommand`: **Rosa corre las migraciones desde su PC antes
  de cada release** (pasos más abajo), y la API se conecta solo con un usuario que hereda `rol_api` (decisión de Rosa,
  29/10/2026). Así Render nunca tiene credenciales del dueño del esquema.
- El servicio debe escuchar en `0.0.0.0` y en el puerto `PORT` (por defecto, 10000).
- Health check HTTP: una respuesta 2xx o 3xx en menos de 5 s marca la instancia como sana.
  `healthCheckPath: /api/v1/salud`. La página de health checks **no dice** si aplica en el plan gratuito, pero
  `healthCheckPath` figura en la especificación del Blueprint sin restricción de plan.

### Archivo `render.yaml` (Blueprint)

Está en la raíz del repo. Usa solo campos de la especificación: `type: web`, `runtime: python`, `plan: free`,
`region: oregon`, `branch: main`, `autoDeployTrigger: checksPass`, `buildCommand`, `startCommand`,
`healthCheckPath` y `envVars` (`value`, `sync: false` y `generateValue: true`).

- **Build:** `pip install -r requirements-api.txt && pip install --no-deps -e .`. Instala solo lo que la API
  necesita (sección 6). El paquete se instala **editable**: `config/paths.py` calcula la raíz del repo desde la
  ubicación del paquete. Con una instalación normal, la raíz apunta a `site-packages` y la API no encuentra
  `configs/config.yaml` (comprobado en la PC).
- **Start:** `python -m uvicorn apps.api.main:app --host 0.0.0.0 --port $PORT`. Sin migraciones.
- La región no se puede cambiar después de crear el servicio. Conviene que el proyecto de Supabase quede en una
  región cercana (**no verifiqué** qué regiones de Supabase corresponden a `oregon`).

### Pasos

1. En Render: *New → Blueprint* y elegir el repositorio. Render lee `render.yaml` y pide los secretos
   (`sync: false`): `DATABASE_URL`, `CORS_ORIGINS`, `SUPABASE_URL` y
   `SUPABASE_SECRET_KEY`. Render pide esos valores **solo al crear el Blueprint**; después se cambian en el
   Dashboard.
2. `API_KEY` la genera Render (`generateValue`). Para el ciclo semanal, cópiala desde el Dashboard a un secreto de
   GitHub Actions.
3. Comprobar `GET https://<servicio>.onrender.com/api/v1/salud` → 200 con `conexion_bd: true`, y
   `GET /api/v1/configuracion` → los horizontes publicados.

### Migraciones antes de cada release (desde la PC de Rosa)

Render no ejecuta `alembic`. Antes de mergear el PR `develop → main`:

1. En la PC, con `develop` actualizado, poner la conexión del dueño del esquema (el usuario `postgres` del proyecto de
   producción, por el session pooler) **solo en esa terminal**, sin guardarla en `.env`:

   ```powershell
   $env:MIGRATION_DATABASE_URL = "postgresql+psycopg://postgres.<ref>:<clave>@<pooler>:5432/postgres?sslmode=require"
   .\.venv\Scripts\python -m alembic current
   .\.venv\Scripts\python -m alembic upgrade head
   .\.venv\Scripts\python -m alembic current
   Remove-Item Env:MIGRATION_DATABASE_URL
   ```

   `alembic current` antes y después confirma la revisión. Si no hay migraciones nuevas, `upgrade head` no cambia
   nada.
2. Mergear el release. Render despliega cuando el CI pasa (`checksPass`).
3. Entre la migración y el despliegue, la API anterior corre contra el esquema nuevo. 0004 y 0006 solo agregan
   datos y permisos. 0005 sí cambia el esquema: agrega dos columnas anulables a `prediccion` y pasa
   `hum_rel_media_pct` a `double precision`. Una producción nueva parte de cero y no tiene ese problema. Si alguna
   vez una migración no fuera compatible con la API anterior, conviene migrar y mergear seguido, o aceptar unos
   minutos de errores 503.
4. Antes de una migración que cambie el esquema (no solo datos), hacer un respaldo manual con `pg_dump` de producción.

La BD de desarrollo se migra igual, con su propia conexión de dueño.

## 4. Supabase (BD y Storage)

### Proyectos

Uno de **desarrollo** (pruebas de Rosa y de Nicolás) y otro de **producción** (el que usa Render). Cada uno tiene su
BD, su Storage y sus claves. **No verificado:** cuántos proyectos gratuitos permite Supabase por organización.

### Conexión desde Render: pooler y sentencias preparadas

- Render **no admite IPv6 saliente** (guía de Render). La conexión directa de Supabase usa IPv6, salvo con el
  complemento IPv4 pago, así que no sirve desde Render.
- El *shared pooler* (Supavisor) usa IPv4 en todos los planes:
  - **session mode, puerto 5432:** admite sentencias preparadas;
  - **transaction mode, puerto 6543:** no las admite.
- **Recomendación:** session mode (5432) con `DB_PREPARED_STATEMENTS=true`. La API es un proceso de larga duración
  con un pool chico (SQLAlchemy por defecto: 5 conexiones más 10 de desborde). Supabase recomienda la conexión
  directa o el session mode para *persistent backends*. La guía de Render recomienda transaction mode para tráfico
  de petición y respuesta. Si se usa transaction mode, `DB_PREPARED_STATEMENTS=false` hace que psycopg 3 no prepare
  sentencias (`prepare_threshold=None`, documentación de psycopg).
- **No verificado:** el límite de conexiones del session mode en el plan gratuito.
- Formato (copiar el servidor desde el diálogo *Connect*; el índice del clúster no se deduce de la región):

  ```text
  postgresql+psycopg://denguekay_api.<ref>:<clave>@aws-<indice>-<region>.pooler.supabase.com:5432/postgres?sslmode=require
  ```

  Con un rol propio, el usuario del pooler es `<rol>.<ref>`. `sslmode=require` cifra la conexión pero no verifica el
  servidor; para verificarlo hacen falta `sslmode=verify-full` y `sslrootcert`.

### Esquema y roles (decisión D2)

1. Migrar como dueño del esquema (el usuario `postgres` del proyecto) desde la PC, con
   los pasos de «Migraciones antes de cada release» (sección 3). La migración 0003 crea los
   roles `NOLOGIN` `rol_api` y `rol_pipeline`, activa RLS en las tablas y crea las políticas `servicio_*`.
   **No verificado** contra un proyecto real de Supabase: que el usuario `postgres` pueda crear esos roles.
2. Crear los usuarios `LOGIN`, que heredan los roles y no son dueños de nada (SQL Editor de Supabase):

   ```sql
   CREATE ROLE denguekay_api LOGIN PASSWORD '<clave larga>' IN ROLE rol_api;
   CREATE ROLE denguekay_pipeline LOGIN PASSWORD '<otra clave>' IN ROLE rol_pipeline;
   ```

   `DATABASE_URL` de Render usa `denguekay_api`. Las cargas y publicaciones desde la PC usan `denguekay_pipeline`.
   Las migraciones las corre Rosa desde la PC con el dueño del esquema (sección 3). `rol_api` no puede ejecutar DDL
   ni leer `alembic_version`, y Render no tiene otra credencial.
3. **API REST automática de Supabase (hipótesis D2, verificada en parte):**
   - Con RLS activo y sin políticas, la clave publicable no accede a ningún dato («no data is accessible through the
     API when using a publishable key, until you create policies»). Las políticas `servicio_*` son solo para
     `rol_api` y `rol_pipeline`, así que `anon` y `authenticated` quedan sin acceso.
   - Pero en los proyectos existentes, una tabla nueva de `public` nace con permisos para los tres roles, y agregar
     políticas no los quita.
   - Recomendación: `REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon, authenticated;` o desactivar la API de
     datos para `public`. **No verificado:** dónde se desactiva en el Dashboard.
   - El frontend no usa esa API: lee la API de Render.

### Datos y modelo

Desde la PC de Rosa:

1. Cargar con `.\.venv\Scripts\python -m denguekay.serving.load_data`, con `DATABASE_URL` de `denguekay_pipeline`.
2. Publicar con `python -m denguekay.serving.publish --seleccionar-experimental`, con `STORAGE_BACKEND=supabase`,
   `SUPABASE_URL` y `SUPABASE_SECRET_KEY`.
3. Para las predicciones vigentes, llamar a `POST /api/v1/admin/inferencias` en la API de Render (D2), con
   `X-API-Key`.

### Storage

- Crear los buckets `modelos`, `geodatos` y `reportes` como **privados** (es el valor por defecto de Supabase).
- `SupabaseStorage` (`denguekay.serving.storage`) usa la API HTTP con `httpx`, sin SDK:
  - **subir:** `POST /storage/v1/object/{bucket}/{ruta}` con `x-upsert: true`. Sin ese encabezado, un objeto
    existente responde `400 Asset Already Exists`. La publicación nunca sobrescribe contenido distinto
    (`package.save_package` lo comprueba antes);
  - **leer de un bucket privado:** `GET /storage/v1/object/authenticated/{bucket}/{ruta}`;
  - **existencia:** `HEAD /storage/v1/object/{bucket}/{ruta}`. Es la llamada de `exists()` en storage-js. **No está
    descrita en las guías**, solo en el código del cliente oficial.
- La clave va en el encabezado `apikey`, como indica Supabase para las claves `sb_secret_…`, que no son JWT. Una clave
  heredada `service_role` (un JWT) va también en `Authorization: Bearer`.
- **No verificado:** que Storage acepte una clave `sb_secret_…` solo en `apikey`, sin `Authorization`. La página de
  claves no cubre Storage. Si responde 401 o 403, prueba con la `service_role` heredada y avísame para ajustar el
  adaptador.
- Las claves secretas omiten RLS, también en Storage. Por eso solo van en Render y en la PC, nunca en el frontend.
  Supabase devuelve 401 si detecta una clave secreta usada desde un navegador.
- **Caché:** cada archivo descargado cuyo SHA-256 se conoce (el manifiesto y sus archivos) se guarda en
  `STORAGE_CACHE_DIR` (por defecto, la carpeta temporal) con su hash como nombre. Solo se usa mientras el hash
  coincide. Igual, `load_package` verifica cada SHA-256 en cada carga (409 `artefacto_invalido`). Un objeto
  inexistente (404, o 400 con `statusCode` 404) se trata como «no existe».
- Los paquetes miden poco. Las subidas estándar son para archivos de hasta 6 MB; por encima, Supabase recomienda
  subidas reanudables (TUS), que el adaptador no implementa.

## 5. Vercel (frontend)

El frontend (`apps/web/`) todavía es un plan, así que estos pasos son para cuando exista:

1. *New Project* → el repositorio → **Root Directory** `apps/web` → variables de entorno con la URL de la API de
   Render (el nombre de la variable lo define Nicolás en `apps/web`).
2. Rama de producción: Vercel elige `main` por defecto. Cada push a otra rama crea un *preview deployment* con su
   propio dominio.
3. `CORS_ORIGINS` en Render debe incluir el dominio de producción de Vercel, exacto y sin barra final. Los dominios
   de *preview* cambian por rama y no tienen comodín en la API (`*` se rechaza). Para probar un *preview* contra la
   API de producción, hay que agregar su dominio a mano. Otra opción: un *preview* apunta a una API local.
4. **Quién crea el proyecto (decisión de Rosa, 29/10/2026):** la cuenta de Vercel de Rosa, que es la que mergea a
   `main`. Producción despliega desde `main`.
5. **Plan Hobby (verificado en la documentación de Vercel):**
   - El plan Hobby es gratuito y solo para uso personal y no comercial ([Hobby plan](https://vercel.com/docs/plans/hobby)).
     Que una tesis universitaria entre en esa categoría es una lectura nuestra, no una afirmación de Vercel.
   - Un equipo Hobby **no puede desplegar un repositorio privado de una organización de GitHub**. Además, en un
     repositorio privado el autor de cada commit debe ser el dueño del equipo Hobby
     ([Deploying Git repositories](https://vercel.com/docs/git), sección «Deploying private Git repositories»).
   - El repositorio `panconlocro/Denguekay` es **público** y es de una **cuenta personal** (API pública de GitHub,
     29/10/2026). Mientras siga así, esas dos restricciones no aplican. Esto corrige la fase 5, donde dije que los
     commits de Nicolás no se desplegarían: eso solo vale si el repo pasa a privado.
   - Para importar o conectar el repositorio de una cuenta personal hay que ser su **Owner** en GitHub; un
     colaborador no puede ([Vercel for GitHub](https://vercel.com/docs/git/vercel-for-github), sección «Personal
     account repositories»). Por eso el proyecto lo crea la cuenta dueña del repo.
   - Si el repo pasara a privado, producción seguiría desplegándose, porque el commit que llega a `main` es el merge
     commit de Rosa. Lo que dejaría de desplegarse son los *previews* de los commits de Nicolás.
6. **Nicolás desarrolla en local contra la API local:** `uvicorn` en `http://127.0.0.1:8000` con la BD SQLite de
   demostración (ver `guia_frontend.md`). El origen de Vite (`http://localhost:5173`) ya está en `config.yaml`. No
   necesita Render, Supabase ni Vercel para trabajar.

## 6. Dependencias livianas y memoria

`requirements-api.txt` lista solo lo que la API usa en ejecución: pandas, scipy, xgboost, scikit-learn, PyYAML,
SQLAlchemy, Alembic, psycopg, python-dotenv, FastAPI, Pydantic, uvicorn y httpx. Cada línea es idéntica a una de
`requirements.txt` (`tests/api/test_dependencies.py`).

- scikit-learn sigue en la lista: `evaluation.protocol` y `evaluation.metrics`, que el predictor v2 importa para Platt
  y el umbral de alerta, lo importan al cargarse.
- Para que la API no cargue Great Expectations, la importación de `gx_quality` pasó a hacerse dentro de las funciones
  que validan datos: `model/train.py`, `evaluation/compact_validation.py` y `serving/protocol.py`. Es el mismo patrón
  que ya usaba `load_data`, y no cambia ninguna lógica.
- La API ya importaba `publish` y `load_data` solo como CLI aparte.
- MLflow ya se importaba de forma diferida.
- `tests/api/test_dependencies.py` exige que importar `apps.api.main`, la inferencia y los dos predictores
  registrados no cargue `mlflow`, `great_expectations`, `optuna`, `matplotlib` ni `geopandas`.
- El job `humo-api` del CI instala solo `requirements-api.txt`, comprueba que esas bibliotecas no estén instaladas,
  migra una BD SQLite, arranca `uvicorn` y consulta rutas de lectura.

**Memoria medida (29/10/2026, Windows 11, Python 3.12.10, entorno con solo `requirements-api.txt`):**

- **Montaje:** una copia de la BD de demostración (v2 servida en h=2, 3 y 4) y su storage, servida con `uvicorn` y un
  worker.
- **Peticiones:** se respondió cada endpoint del contrato (las 16 rutas) tres veces: cada lectura con h=2, 3 y 4,
  `POST /admin/inferencias` por horizonte (carga el paquete de la v2 e infiere los 65 distritos) y
  `POST /admin/modelos/{id}/activar` (responde 409 por diseño).
- **Resultado:** RSS de 117 MB al arrancar, **335 MB** después de cargar la v2 y responder todo (334,5 MB tras la
  primera ronda, estable en las siguientes) y pico de 344,5 MB. Quedan unos 170 MB de margen bajo los 512 MB de Render.
- **No medido en Linux ni en Render:** la cifra es del *working set* de Windows. El job `humo-api` imprime el RSS de
  Linux sin modelo cargado. Con 0,1 CPU, la inferencia de un horizonte puede tardar bastante más que los 2,5 a 2,7 s
  medidos en la PC. **No verifiqué** el tiempo máximo de respuesta HTTP de Render.

## 7. Criterios 3 y 4 de la HU0018

- **HU0018-3 (despliegue y configuración):** la configuración por entorno (sección 2), `render.yaml`, este documento
  y el job `humo-api` cubren lo que se puede hacer sin desplegar. Falta el despliegue real, que hace Rosa.
- **HU0018-4 (mantenimiento y recuperación):**
  - si el build o el health check fallan, Render conserva el último despliegue sano (despliegues sin caída);
  - las migraciones se corren desde la PC, con `alembic current` antes y después y un `pg_dump` previo (sección 3);
  - el SHA-256 de cada archivo del paquete se verifica al cargarlo;
  - la reversión de esquema está en `docs/backend/operacion.md`;
  - las ejecuciones quedan auditadas en `ejecucion`.

  **No verificado:** los respaldos automáticos de Supabase en el plan gratuito. Antes de migrar producción, conviene
  un `pg_dump` manual.

## 8. Inferencia en Render: qué calcula cada endpoint y cuánto tardaría

Fase 6, pedido de Rosa (29/10/2026). Es una **estimación, no una medición en Render**. Perfil completo:
[evidencia/perfil_cpu_api_v2.json](evidencia/perfil_cpu_api_v2.json).

### Qué hace cada endpoint

Comprobado en el código de `apps/api/routers/`: solo `admin.py` importa `denguekay.serving.inference.infer`.

| Endpoint | Predicciones |
|---|---|
| `POST /admin/inferencias` | **Calcula en la petición**: carga y verifica el paquete (con caché por SHA-256), arma las entradas desde la BD, corre el predictor v2 para los 65 distritos y escribe `prediccion`, `alerta` y `ejecucion` |
| `GET /predicciones`, `/series/{ubigeo}`, `/tablero/resumen`, `/mapa-riesgo`, `/alertas`, `/alertas/{id}` | Leen predicciones y alertas guardadas en la BD |
| `GET /configuracion`, `/modelos/activo`, `/modelos/{id}`, `/modelos/{id}/variables` | Leen versiones, parámetros e importancias guardadas (las importancias SHAP se calculan al publicar, no en la API) |
| `GET /salud`, `/distritos`, `/distritos/{ubigeo}`, `/observaciones` | Leen la BD; no tocan predicciones |
| `POST /admin/modelos/{version}/activar` | Cambia el estado de las versiones; no recalcula (su respuesta lo dice) |

### Estimación con 0,1 CPU

**Método.** Medí los segundos de CPU (user + system) que el proceso `uvicorn` consume por petición, con
`psutil.Process.cpu_times()`. El montaje fue:

- una copia de la BD de demostración (v2, h=2, 3 y 4), servida con solo `requirements-api.txt`;
- un worker y XGBoost en CPU con un hilo, como en `render.yaml`;
- lecturas sin caché (`Cache-Control: no-cache`).

La estimación con 0,1 CPU es CPU / 0,1. Supone un núcleo tan rápido como el de la PC y nada de espera de E/S. Es una
**hipótesis**: no verifiqué cómo reparte Render la CPU del plan gratuito, ni si permite ráfagas.

| Petición | CPU medida (PC) | Estimado con 0,1 CPU |
|---|---|---|
| `POST /admin/inferencias`, primera de cada horizonte (carga el paquete) | 2,8 a 5,0 s | **28 a 50 s** |
| `POST /admin/inferencias`, siguientes (paquete en caché) | 2,8 a 3,0 s | **28 a 30 s** |
| Lecturas (`/predicciones`, `/mapa-riesgo`, `/tablero`, `/series`, `/alertas`, `/modelos`) | ≤ 0,031 s | ≤ 0,31 s |
| `GET /configuracion`, primera petición después de arrancar | 0,20 s | 2,0 s |
| Arranque del proceso hasta el primer `/salud` (imports y app) | 1,36 s | 13,6 s, más el minuto que Render documenta para despertar un servicio dormido |

El reloj de CPU de Windows tiene una resolución de unos 15,6 ms, así que las lecturas más rápidas marcan 0.
`GET /alertas/{identificador}` no se perfiló: la BD de demostración no tiene alertas guardadas. Hace la misma
consulta por clave que `/modelos/{id}`.

**Conclusión.** Las lecturas medidas quedan dentro de los 5 s del SLA (HU0016-3), salvo el arranque en frío. La inferencia
**no**: con unos 30 s por horizonte, la superaría unas 6 a 10 veces.

- La prueba de humo en PostgreSQL midió 2,6 a 4,0 s de reloj por horizonte en la PC
  ([evidencia_api_v1.md](evidencia/evidencia_api_v1.md)).
- **No verificado:** el tiempo máximo que Render espera una respuesta HTTP. Si corta antes, el cliente recibe un
  error aunque el servidor termine la inferencia.

### Propuesta (no implementada): que el ciclo semanal calcule y la API solo lea

1. **Un comando de inferencia fuera de la API**, por ejemplo `python -m denguekay.serving.infer_current
   --horizontes 2 3 4`.
   - Llama a la misma `denguekay.serving.inference.infer` que usa el endpoint, con `origin="ciclo_semanal"`.
   - Escribe las mismas filas de `prediccion`, `alerta` y `ejecucion`.
   - Ya existe casi entero: `publish.infer_current`, que hoy usa `publish --inferir`.
2. **Dónde corre:** en el workflow semanal de GitHub Actions, en un runner Linux en lugar de Render.
   - Se conecta a Supabase con un usuario que hereda `rol_api`, que ya tiene `INSERT` y `UPDATE` en `prediccion`,
     `alerta` y `ejecucion`, y lee Storage con la clave secreta, ambos como secretos del repositorio.
   - El mismo comando sirve desde la PC de Rosa.
   - **No verificado:** los recursos de los runners de GitHub.
3. **La API solo lee.** Las lecturas ya ven las predicciones nuevas sin reiniciar nada:
   - la caché de la API se invalida con la revisión de `ejecucion` (`max(id_ejecucion)` y `max(fin)`), que se consulta
     en cada lectura;
   - una inferencia hecha fuera de la API crea su fila en `ejecucion`.
4. **Contrato: sin cambios.**
   - `POST /admin/inferencias` sigue igual en el contrato v1. Queda para uso manual o local, y la documentación dice
     que en Render puede tardar decenas de segundos.
   - Ninguna ruta, ningún esquema y ningún código de estado cambian, así que `openapi_v1.json` no cambia.
   - Cambia el documento OE2: el ciclo semanal ejecuta el comando en vez de llamar al endpoint.
5. **Alternativas descartadas:**
   - una inferencia asíncrona (202 más una consulta de estado) cambia el contrato;
   - pasar a un plan pago de Render no es parte del diseño OE2 (plan gratuito).
6. **Pendiente para decidir:** quién carga los datos semanales antes de la inferencia. `load_data` lee `data/` en la
   PC de Rosa, y `data/` no está en el repo ni en el CI.

## Fuentes (consultadas el 29/10/2026)

- Render: [Free instances](https://render.com/docs/free), [Deploys (pre-deploy command)](https://render.com/docs/deploys),
  [Blueprint spec](https://render.com/docs/blueprint-spec), [Python version](https://render.com/docs/python-version),
  [Health checks](https://render.com/docs/health-checks), [Web services (PORT)](https://render.com/docs/web-services),
  [Connect a Render service to Supabase Postgres](https://render.com/articles/how-to-connect-a-render-service-to-supabase-postgres).
- Supabase: [Connecting to Postgres](https://supabase.com/docs/guides/database/connecting-to-postgres),
  [Standard uploads](https://supabase.com/docs/guides/storage/uploads/standard-uploads),
  [Serving downloads](https://supabase.com/docs/guides/storage/serving/downloads),
  [Buckets fundamentals](https://supabase.com/docs/guides/storage/buckets/fundamentals),
  [Storage access control](https://supabase.com/docs/guides/storage/security/access-control),
  [API keys](https://supabase.com/docs/guides/api/api-keys),
  [Row Level Security](https://supabase.com/docs/guides/database/postgres/row-level-security),
  [storage-js `StorageFileApi.ts`](https://github.com/supabase/storage-js/blob/main/src/packages/StorageFileApi.ts).
- psycopg 3: [Prepared statements](https://www.psycopg.org/psycopg3/docs/advanced/prepare.html).
- Vercel: [Deploying Git repositories](https://vercel.com/docs/git), [Hobby plan](https://vercel.com/docs/plans/hobby),
  [Vercel for GitHub](https://vercel.com/docs/git/vercel-for-github) (consultadas el 29/10/2026).
