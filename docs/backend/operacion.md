# Operación del backend (esquema OE2, local)

Este documento cubre la operación local: PostgreSQL local (o SQLite para pruebas), uvicorn y artefactos en
`models/storage/`. El despliegue en Render, Supabase y Vercel está en [despliegue.md](despliegue.md) y lo hace
Rosa a mano; el código y los tests nunca se conectan a servicios reales. Comandos en **Windows
PowerShell**, desde la raíz del repo. Diseño: [especificación OE2](especificacion_oe2.md),
[DDL](ddl_oe2.sql) y [desviaciones](desviaciones_oe2.md).

## Variables de entorno

| Variable | Uso | Dónde |
|---|---|---|
| `DATABASE_URL` | BD de la app: `postgresql+psycopg://usuario:clave@127.0.0.1:5432/denguekay` (o `sqlite:///ruta.db`) | `.env` (no se versiona) o entorno |
| `API_KEY` | Clave de las escrituras (`X-API-Key`) | `.env` o entorno |
| `MIGRATION_DATABASE_URL`, `DB_PREPARED_STATEMENTS`, `CORS_ORIGINS`, `SERVIR_NO_VALIDADAS`, `STORAGE_BACKEND`, `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `STORAGE_CACHE_DIR` | Opcionales en local; reemplazan a `config.yaml` (ver [despliegue.md](despliegue.md#2-variables-de-entorno) y `.env.example`) | `.env` o entorno |
| `DENGUEKAY_PG_PRUEBAS_URL` | BD PostgreSQL **desechable** para los tests (su nombre debe contener «prueba») | variable de usuario |
| `MLFLOW_TRACKING_URI` | Opcional; por defecto `mlflow.db` en la raíz | entorno |

Las variables del proceso tienen prioridad sobre `.env`. Ningún comando imprime credenciales. Ojo: si `.env` define
`MIGRATION_DATABASE_URL`, `alembic upgrade head` migra esa BD aunque el proceso traiga otro `DATABASE_URL`; para
migrar una BD temporal, define también `MIGRATION_DATABASE_URL` en el proceso (o déjala vacía en `.env`).

## Levantar el demo

```powershell
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m pip install -e .
.\.venv\Scripts\python -m alembic upgrade head
.\.venv\Scripts\python -m denguekay.serving.load_data
.\.venv\Scripts\python -m denguekay.serving.publish --seleccionar-experimental --inferir
.\.venv\Scripts\python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

- `alembic upgrade head` deja la BD en la última revisión: `0003_oe2` (esquema OE2, semillas de
  `parametro_sistema`, RLS, roles `rol_api`/`rol_pipeline` si no existen, permisos y políticas), `0004_v1`
  (`horizonte_por_defecto`) y `0005_v1` (intervalo de casos, humedad en `double precision`, permisos de
  `rol_pipeline` en `prediccion` y `nivel_intervalo_casos`) y `0006_v1` (fila `seleccion_experimental` vacía y
  permiso de `rol_pipeline` para actualizar solo esa fila). La 0003 **reemplaza** el esquema 0001/0002:
  los datos anteriores se pierden y se recargan desde las fuentes.
- `load_data` valida GX y el linaje, y carga provincia, distrito, calendario MMWR y
  `observacion_semanal` (65 distritos, 30 485 observaciones, corte 27/12/2025). Es idempotente:
  con las mismas fuentes reutiliza la ingesta. Desde la fase 4 no toca `seleccion_experimental`.
- `publish` (≈2 min) construye el paquete del tipo configurado en `config.yaml` (`serving.paquete`; hoy
  `v2_e3_s4` con h=2, 3 y 4: recalcula el protocolo por bloques de `CONFIG_2026`, comprueba su huella de
  comportamiento cuando gold es el congelado y ajusta el regresor multisalida al corte de los datos),
  registra un run en MLflow, guarda el paquete en `models/storage/modelos/<codigo_paquete>/`
  (`manifest.json` y sus archivos, cada uno con SHA-256), crea las versiones `candidata` (una por tarea y
  horizonte, todas apuntando al manifiesto) e importa las predicciones OOS del protocolo.
  `--seleccionar-experimental` deja esas versiones como `seleccion_experimental` de sus horizontes en la misma
  transacción (qué modelo se sirve es un dato operativo: no lo fija una migración).
  **No** hace la inferencia vigente: en despliegue la hace la API (`POST /admin/inferencias`, decisión D2);
  `--inferir` la corre en el mismo proceso para uso local. Repetirla con las mismas entradas se reutiliza.
- **Primera publicación tras la reestructuración (decisión D6 del
  [ADR 0001](../decisions/0001-repo-restructure.md)).** La huella de una publicación incluye el
  SHA-256 de todo el código de `src/denguekay/` (`code_hashes()` de `denguekay.serving.publish`).
  La fase 3 movió y tradujo ese código sin cambiar su comportamiento, pero cambió sus bytes: la
  primera `publish` posterior no reutiliza la publicación anterior y registra un
  `reentrenamiento` y un run de MLflow nuevos. Las versiones de modelo se reutilizan si el booster
  sale idéntico byte a byte (mismo equipo, dispositivo y `n_jobs`); si sale distinto (otro equipo
  o GPU/CPU), se crean versiones `candidata` nuevas y hay que actualizar
  `parametro_sistema.seleccion_experimental`. Es esperado y no indica un cambio del modelo.
- La API queda en `http://127.0.0.1:8000/api/v1`; documentación en `/docs` y `/openapi.json`.

Con la BD ya poblada basta el último comando.

## Pasar la BD local a la v2 (fase 4)

```powershell
.\.venv\Scripts\python -m alembic upgrade head
.\.venv\Scripts\python -m denguekay.serving.publish --seleccionar-experimental --inferir
```

- `alembic upgrade head` aplica la `0006_v1`. Solo cambia permisos: la fila `seleccion_experimental` que ya
  tiene la BD local (con los códigos de la v0) se conserva.
- `load_data` no hace falta: la transformación no cambió y `publish` reutiliza la ingesta.
- `publish` registra las seis versiones de la v2 (`v2-clf-h2-1` … `v2-reg-h4-1`) y fija la selección
  experimental de h=2, 3 y 4 con ellas, en la misma transacción. Sus OOS 2022–2025 reemplazan a las de la v0 en
  la serie (mismo distrito, corte y horizonte; decisión M6). Con `--inferir`, la inferencia vigente ya usa la v2.
- Las versiones de la v0 quedan en la BD como historia, y su predictor sigue registrado (`v0_compact_xgb`).
- La v2 no sirve los orígenes cuyo t+2 cae en 2021 o antes: necesitan casos anteriores a 2017 (M4). Responden
  `no_disponible` con su motivo.

## Dejar la BD local al día después de la migración 0005 (fase 3)

Las versiones v0 anteriores al motor enchufable apuntan a un booster suelto
(`modelos/<codigo>.json`), no a un manifiesto de paquete, y la inferencia ya no las carga: **se
descartan y se republica** con el código nuevo (decisión P1 de la fase 3). La humedad cargada antes de la
0005 también estaba redondeada a dos decimales.

```powershell
.\.venv\Scripts\python -m alembic upgrade head
.\.venv\Scripts\python -m denguekay.serving.load_data
.\.venv\Scripts\python -m denguekay.serving.publish
```

- `load_data` vuelve a cargar todo porque cambió la versión de la transformación (la humedad ya no se
  redondea, M5).
- `publish` (**sin** `--inferir`) crea el paquete v0 y versiones nuevas (`clf-h2-v2`, …; la huella del
  código cambió, D6). No infiera todavía: la selección experimental sigue apuntando a las versiones `-v1`
  viejas, cuyo booster suelto la inferencia ya no carga (409 `artefacto_invalido`), y con `--inferir` ese
  rechazo desharía la publicación entera. Primero apunte `parametro_sistema.seleccion_experimental` a los
  códigos nuevos (hasta la fase 4, `configs/config.yaml` solo sembraba una BD que no tenía la clave; desde la
  fase 4 lo hace `publish --seleccionar-experimental`):

  ```sql
  UPDATE parametro_sistema SET valor = '{"2": {"clasificacion": "clf-h2-v2", "regresion": "reg-h2-v2"},
    "4": {"clasificacion": "clf-h4-v2", "regresion": "reg-h4-v2"}}' WHERE clave = 'seleccion_experimental';
  ```

  (use los códigos que imprimió `publish`) y después infiera: `POST /admin/inferencias` para h=2 y h=4, o
  `python -m denguekay.serving.publish --inferir` (la publicación se reutiliza y solo infiere). Las
  versiones viejas quedan en la BD como historia (sus predicciones guardadas no cambian), pero ya no se
  pueden usar para inferir.
- Alternativa más simple si no necesita conservar esa historia: borrar la BD local, recrearla vacía y
  correr `alembic upgrade head`, `load_data` y `publish --seleccionar-experimental --inferir`.
- La demo para el frontend se regenera con `python -m denguekay.serving.demo_database --reemplazar`.

## Publicar un modelo nuevo sin tocar la API

La API solo conoce las tablas y el puerto `Predictor`. Un modelo nuevo (otras variables, otra estrategia,
otros horizontes u otro algoritmo) se agrega así, sin cambiar `apps/api/`, sus esquemas ni el frontend:

1. **Clase de predictor y su test de paridad.** Un módulo en `src/denguekay/serving/predictors/<tipo>.py`
   con la clase `Predictor` (atributos `kind`, `required_inputs` —subconjunto de `casos`, `clima`,
   `poblacion`, `calendario`, `regla_brote`—, `horizons`, `interval_level`, y los métodos
   `from_package(paquete)` y `predict(entradas, corte, horizontes)`, que devuelve las columnas de
   `predictors.base.OUTPUT_COLUMNS`) y las funciones del constructor del paquete: `validate`, `prepare`,
   `fingerprint_parameters` y `build`, que devuelve un `BuiltPackage`. Se registra en
   `predictors.PREDICTORS`. El test de paridad comprueba que el vector construido desde la BD y las
   predicciones coinciden con los del modelado (`denguekay.model`), sin copiar su lógica.
2. **Construir el paquete.** En `configs/config.yaml`, `serving.paquete.tipo` = el tipo nuevo, con sus
   `horizontes` y `opciones`. El manifiesto declara el tipo, los horizontes, las variables, el nivel de sus
   intervalos y el SHA-256 de cada archivo.
3. **Publicar como `candidata`:** `python -m denguekay.serving.publish`. Registra una versión por tarea y
   horizonte (todas apuntan al mismo manifiesto), con `cumple_umbrales` calculado desde
   `parametro_sistema.umbrales_aceptacion`, y sus predicciones OOS.
4. **Servirlo:** como selección experimental (`publish --seleccionar-experimental`, que fija
   `parametro_sistema.seleccion_experimental` con los códigos nuevos de sus horizontes) o, si cumple los umbrales, activándolo con `POST /admin/modelos/{version}/activar`. La activación
   es por horizonte y en pareja: activar una tarea activa también la otra del mismo paquete. Después,
   `POST /admin/inferencias` para cada horizonte.

Las guardas del contrato v1 (`tests/test_contract_v1_guards.py`) no deben cambiar con un modelo nuevo; si
un test de datos necesita otro modelo, va con fixtures nuevos y aparte de los del smoke.

## Nivel del intervalo de casos

`parametro_sistema.nivel_intervalo_casos` (0,80, sembrado por la 0005) es la probabilidad nominal de los
intervalos `casos_intervalo_inferior`/`casos_intervalo_superior`. Cada paquete registra en su manifiesto
(`nivel_intervalo`) el nivel con que los calcula, y la inferencia **rechaza (409)** un paquete cuyo nivel
no coincida con el parámetro. Un paquete sin intervalos (la v0) declara `null` y no se ve afectado.
**Cambiar el parámetro obliga a volver a inferir** con un paquete publicado a ese nivel: las predicciones
guardadas conservan los intervalos del nivel con que se calcularon.

## BD de demostración para el frontend (decisión D1)

```powershell
.\.venv\Scripts\python -m denguekay.serving.demo_database
```

Genera `models/serving/demo/` (no se versiona): `denguekay_demo.sqlite`, migrada con Alembic y con los datos
agregados reales y la v0 publicados, su `storage/` y su propio MLflow (`mlflow.db` y `mlartifacts/`), que no
toca el `mlflow.db` del proyecto. Solo lee `data/`; como toda publicación, deja además su reporte en
`models/serving/ejecuciones/<huella>/` (tampoco se versiona). `--reemplazar` rehace una demo existente y `--salida`
cambia la carpeta. La carpeta se comparte fuera de Git (Drive o un Release); cómo usarla está en
[guia_frontend.md](guia_frontend.md).

## Prueba de humo y evidencia

Con uvicorn levantado y `API_KEY` definida:

```powershell
.\.venv\Scripts\python -m apps.api.tools.smoke_test --url http://127.0.0.1:8000
```

Llama a cada endpoint de la Tabla 2 y a `GET /configuracion`, y escribe
[evidencia_tb1.md](evidencia/evidencia_tb1.md) (sin credenciales). La evidencia SQL de la migración OE2
(`0002_serving:0003_oe2`) se regenera con `.\.venv\Scripts\python -m denguekay.db.export_migration_sql`
(no se conecta a ninguna BD). El SQL de cada migración posterior es una línea base en
`tests/fixtures/contract_v1/`.

## Inferencia y activación desde la API

```powershell
$h = @{ "X-API-Key" = $env:API_KEY }
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/admin/inferencias -Headers $h -ContentType application/json -Body '{"horizonte": 4}'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/admin/modelos/1/activar -Headers $h
```

- La inferencia carga el paquete de las versiones en uso (verifica el SHA-256 del manifiesto y de cada
  archivo), pide a su predictor una fila por distrito con las entradas reconstruidas desde la BD y hace
  UPSERT por `(ubigeo, id_semana_corte, horizonte)`. Sin `id_semana_corte` usa la última semana
  observada. Un horizonte sin ninguna versión responde 409 («sin modelo para h=N»).
- La activación exige `cumple_umbrales = true` en la versión y en su hermana del mismo paquete y
  horizonte (se activan en pareja); hoy ninguna versión lo cumple y responde 409 (por diseño). Tras
  activar, ejecute de nuevo la inferencia.
- Si cambian las versiones (p. ej. `v2-clf-h4-2`), publique con `--seleccionar-experimental` (una publicación
  reutilizada también fija la selección con sus versiones).

## Tests, cobertura y benchmark

```powershell
$env:DENGUEKAY_PG_PRUEBAS_URL = [Environment]::GetEnvironmentVariable('DENGUEKAY_PG_PRUEBAS_URL','User')
.\.venv\Scripts\python -m coverage run --source=src/denguekay/db,src/denguekay/serving,apps/api -m unittest discover -s tests
.\.venv\Scripts\python -m coverage report -m
.\.venv\Scripts\python -m apps.api.tools.benchmark --horizontes 2 4 --incluir-escrituras --salida docs/backend/benchmark_postgresql.json
```

Los tests usan SQLite temporal y, si existe `DENGUEKAY_PG_PRUEBAS_URL`, repiten esquema e
inferencia en esa BD (la devuelven a `base` al terminar). Nunca usan `DATABASE_URL`. El benchmark
con `--incluir-escrituras` agrega ejecuciones: úselo sobre una copia o la BD de pruebas.

**Benchmark con la v2 (fase 4, 29/10/2026).**
- **Cómo se midió:** sobre una copia de la BD de demostración (65 distritos, v2 con h=2, 3 y 4), uvicorn local
  por HTTP real, CPU, 20 repeticiones con 2 de calentamiento, escrituras incluidas
  (`--url http://127.0.0.1:8765 --incluir-escrituras --salida models/serving/benchmark_v2.json`, sin versionar).
- **Resultado:** 67 casos medidos, todos bajo el SLA de 5 s.
  - **Lecturas:** p95 máximo de 31 ms (`/mapa-riesgo?horizonte=4`); con h=3, `/predicciones` 29 ms y `/mapa-riesgo` 28 ms.
  - **Inferencia** (`POST /admin/inferencias`, 65 distritos): p95 de 2,5 a 2,7 s por horizonte. La mayor parte es
    rearmar el vector de la v2 desde la BD.
- **Sin medir:** 2 casos, igual que antes: no hay alertas guardadas para medir un detalle, y la activación se prueba
  en los tests.

## Respaldo, reversión y mantenimiento

- **Respaldo:** `pg_dump` de la BD y copia de `models/storage/` (los paquetes no están en la BD).
- **Volver al esquema anterior:** `alembic downgrade 0005_v1` quita el permiso de `rol_pipeline` sobre la
  selección experimental (y la fila, solo si sigue vacía); `alembic downgrade 0004_v1` quita el intervalo y devuelve la humedad a
  `numeric(5,2)` (redondeada); `alembic downgrade 0002_serving` deja el esquema 0002 vacío (no borra los
  roles, que son globales del clúster).
- **Artefacto alterado o ausente:** si el manifiesto o un archivo del paquete no coincide con su SHA-256
  o falta, la inferencia responde 409 `artefacto_invalido`; restaure el archivo desde el respaldo o vuelva
  a publicar.
- **Datos nuevos:** regenerar silver/gold con el pipeline (fuera del backend), luego `load_data`
  y `publish`. Las métricas de las versiones siguen siendo las del protocolo temporal guardado;
  una evaluación nueva requiere repetir el protocolo (fase de modelado).
- **Auditoría:** cada carga, publicación, inferencia y activación es una fila de `ejecucion`
  (`tipo`, `estado`, `detalle`, `mensaje_error`).
