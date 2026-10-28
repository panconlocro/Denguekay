# Operación del backend (esquema OE2, TB1 local)

Todo corre en local: PostgreSQL local (o SQLite para pruebas), uvicorn y artefactos en
`models/storage/`. No se despliega en Supabase ni Render en TB1. Comandos en **Windows
PowerShell**, desde la raíz del repo. Diseño: [especificación OE2](especificacion_oe2.md),
[DDL](ddl_oe2.sql) y [desviaciones](desviaciones_oe2.md).

## Variables de entorno

| Variable | Uso | Dónde |
|---|---|---|
| `DATABASE_URL` | BD de la app: `postgresql+psycopg://usuario:clave@127.0.0.1:5432/denguekay` (o `sqlite:///ruta.db`) | `.env` (no se versiona) o entorno |
| `API_KEY` | Clave de las escrituras (`X-API-Key`) | `.env` o entorno |
| `DENGUEKAY_PG_PRUEBAS_URL` | BD PostgreSQL **desechable** para los tests (su nombre debe contener «prueba») | variable de usuario |
| `MLFLOW_TRACKING_URI` | Opcional; por defecto `mlflow.db` en la raíz | entorno |

Las variables del proceso tienen prioridad sobre `.env`. Ningún comando imprime credenciales.

## Levantar el demo

```powershell
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m alembic upgrade head
.\.venv\Scripts\python -m src.serving.cargar_datos
.\.venv\Scripts\python -m src.serving.publicar --horizontes 2 4
.\.venv\Scripts\python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000
```

- `alembic upgrade head` deja la BD en `0003_oe2` (esquema OE2, semillas de `parametro_sistema`,
  RLS, roles `rol_api`/`rol_pipeline` si no existen, permisos y políticas). **Reemplaza** el
  esquema 0001/0002: los datos anteriores se pierden y se recargan desde las fuentes.
- `cargar_datos` valida GX y el linaje, y carga provincia, distrito, calendario MMWR y
  `observacion_semanal` (65 distritos, 30 485 observaciones, corte 27/12/2025). Es idempotente:
  con las mismas fuentes reutiliza la ingesta. Siembra `seleccion_experimental` desde `config.yaml`
  sin pisar un valor existente.
- `publicar` (≈1 min) ajusta los boosters con `src/modeling/train.py` (sin cambiar el modelo),
  registra un run en MLflow, guarda cada booster en `models/storage/modelos/<codigo>.json` con su
  SHA-256, crea las versiones `candidata`, importa las predicciones OOS del protocolo (27 040
  filas) e infiere el corte vigente para h=2 y h=4. Repetirla con las mismas entradas se reutiliza.
- La API queda en `http://127.0.0.1:8000/api/v1`; documentación en `/docs` y `/openapi.json`.

Con la BD ya poblada basta el último comando.

## Prueba de humo y evidencia

Con uvicorn levantado y `API_KEY` definida:

```powershell
.\.venv\Scripts\python -m src.api.prueba_humo --url http://127.0.0.1:8000
```

Llama a cada endpoint de la Tabla 2 y escribe [evidencia_tb1.md](evidencia/evidencia_tb1.md)
(sin credenciales). La evidencia SQL de la migración se regenera con
`.\.venv\Scripts\python -m src.db.exportar_sql_migracion` (no se conecta a ninguna BD).

## Inferencia y activación desde la API

```powershell
$h = @{ "X-API-Key" = $env:API_KEY }
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/admin/inferencias -Headers $h -ContentType application/json -Body '{"horizonte": 4}'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/admin/modelos/1/activar -Headers $h
```

- La inferencia reconstruye los vectores desde la BD, aplica la versión en uso y hace UPSERT por
  `(ubigeo, id_semana_corte, horizonte)`. Sin `id_semana_corte` usa la última semana observada.
- La activación exige `cumple_umbrales = true`; hoy ninguna versión lo cumple y responde 409 (por
  diseño). Tras activar, ejecute de nuevo la inferencia.
- Si cambian las versiones (p. ej. `clf-h4-v2`), actualice `parametro_sistema.seleccion_experimental`.

## Tests, cobertura y benchmark

```powershell
$env:DENGUEKAY_PG_PRUEBAS_URL = [Environment]::GetEnvironmentVariable('DENGUEKAY_PG_PRUEBAS_URL','User')
.\.venv\Scripts\python -m coverage run --source=src/db,src/serving,src/api -m unittest discover -s tests
.\.venv\Scripts\python -m coverage report -m
.\.venv\Scripts\python -m src.api.benchmark --horizontes 2 4 --incluir-escrituras --salida docs/backend/benchmark_postgresql.json
```

Los tests usan SQLite temporal y, si existe `DENGUEKAY_PG_PRUEBAS_URL`, repiten esquema e
inferencia en esa BD (la devuelven a `base` al terminar). Nunca usan `DATABASE_URL`. El benchmark
con `--incluir-escrituras` agrega ejecuciones: úselo sobre una copia o la BD de pruebas.

## Respaldo, reversión y mantenimiento

- **Respaldo:** `pg_dump` de la BD y copia de `models/storage/` (los boosters no están en la BD).
- **Volver al esquema anterior:** `alembic downgrade -1` deja el esquema 0002 vacío (no borra los
  roles, que son globales del clúster).
- **Artefacto alterado o ausente:** la inferencia responde 409 `artefacto_invalido`; restaure el
  archivo desde el respaldo o vuelva a publicar.
- **Datos nuevos:** regenerar silver/gold con el pipeline (fuera del backend), luego `cargar_datos`
  y `publicar`. Las métricas de las versiones siguen siendo las del protocolo temporal guardado;
  una evaluación nueva requiere repetir el protocolo (fase de modelado).
- **Auditoría:** cada carga, publicación, inferencia y activación es una fila de `ejecucion`
  (`tipo`, `estado`, `detalle`, `mensaje_error`).
