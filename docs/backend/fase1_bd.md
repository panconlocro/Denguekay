# Cierre de fase 1: base de datos y carga real

La evidencia ejecutada está en [fase1_verificacion.json](fase1_verificacion.json).
Esta fase construye persistencia y carga; las tablas de modelos, predicciones
y alertas quedan vacías hasta la fase 2. No se entrenó ni publicó un modelo.

## Archivos creados

- `.env.example`, `alembic.ini`.
- `src/db/__init__.py`, `configuracion.py`, `sesion.py`, `modelos.py`.
- `src/db/migraciones/env.py`, `script.py.mako` y
  `versions/0001_backend_esquema_inicial_del_backend.py`.
- `src/serving/__init__.py`, `cargar_datos.py`.
- `tests/backend_soporte.py`, `test_db_backend.py`, `test_serving_carga.py`.
- `tests/fixtures/backend/gold_h2_muestra.csv`, `sala_muestra.csv`,
  `procedencia.json`: selección agregada real, sin datos personales.
- `docs/backend/operacion.md`, este cierre y `fase1_verificacion.json`.

Modificados: `requirements.txt`, `.gitignore`, `src/utils/paths.py`,
`README.md` y `docs/estructuraRepo.md`. Se conservaron los finales de línea
de los archivos existentes editados. Los dos CSV de referencia ya aparecían
modificados al iniciar la fase por la copia del paquete de Rosa; no fueron
modificados por el backend.

Los artefactos locales se guardan en `models/serving/` (ignorado por Git):
`fase1.sqlite`, `migracion_postgresql.sql` y `fase1_cobertura.json`. No se
creó `.env` ni se guardaron credenciales reales.

## Esquema y decisiones de esta fase

Nueve tablas de aplicación: `distrito`, `observacion_semanal`,
`version_modelo`, `importancia_variable`, `ejecucion_prediccion`,
`prediccion`, `alerta`, `activacion_modelo` y `carga_datos`.
Alembic añade su propia tabla `alembic_version`.

`carga_datos` amplía el mínimo aprobado para conservar hashes, resultados
GX, corte y conteos de cada carga. `activacion_modelo` prepara la auditoría
de reactivaciones de HU0009. No se usan borrados en cascada del historial.
La observación tiene una clave única por distrito/año/semana; una predicción
es única dentro de su ejecución, permitiendo conservar ejecuciones previas.
Clasificación y regresión tienen referencias de versión independientes.

La configuración acepta PostgreSQL mediante psycopg 3 y SQLite para pruebas;
una URL PostgreSQL sin sufijo de driver se normaliza a psycopg. Las claves
foráneas también se activan en SQLite. El esquema usa `JSON` portable y
`VARCHAR(6)` con comprobaciones de seis dígitos en ORM y SQL. Las conexiones
se crean explícitamente, sin conectar al importar los módulos.

El estado de validación del modelo se calculará en la fase 2 a partir de
`metricas_evaluacion` conservadas por bloque. No se creó una columna editable
para etiquetar manualmente un modelo como validado. El esquema ya admite el
artefacto XGBoost en JSON, columnas, hiperparámetros, cortes, partición,
MLflow, hashes, dispositivo, versión de XGBoost y plataforma.

La carga copia las etiquetas y umbrales de gold sin volver a calcularlos.
El cruce geográfico reutiliza la normalización del pipeline, ignora espacios
de nombres concatenados de GADM, exige correspondencia uno a uno y contrasta
los centroides contra silver auditado. Guarda geometría SQL NULL y un motivo
explícito porque no existen polígonos en las referencias actuales.

## Comandos y resultados ejecutados

1. `.venv/bin/python -m src.validation.calidad_gx`: silver **107/107**,
   gold h2 **92/92**, gold h4 **92/92**, todos exitosos.
2. Auditoría `auditar_traspaso()` y `preparar_carga()`: linaje y fuentes
   consistentes; lote preparado con **65 distritos y 30 485 observaciones**.
3. `.venv/bin/python -m alembic upgrade head`: revisión `0001_backend`
   aplicada a SQLite **3.53.0** y PostgreSQL **17.5**, local temporal.
4. `.venv/bin/python -m src.serving.cargar_datos`, dos veces en cada motor:
   primera carga `carga_id: 1, reutilizada: false`; segunda
   `carga_id: 1, reutilizada: true`. Ambas mantuvieron una sola carga y los
   mismos conteos, sin duplicar filas.
5. `.venv/bin/python -m coverage run --source=src/db,src/serving -m unittest discover -s tests`:
   **188 tests, OK**, en **21,322 s**; **160 existentes y 28 nuevos**.
   Las pruebas comprueban migración/reversión en BD temporal vacía,
   concordancia ORM, unicidad, claves foráneas, UBIGEO, ceros/nulos, calendario,
   procedencia, idempotencia, extensión de carga y rollback de un lote inválido.
6. Carga CLI real instrumentada con `coverage run --append`, seguida de
   `coverage report -m` y `coverage json`: **96,09 %** de cobertura conjunta
   de `src/db` y `src/serving`, incluyendo migraciones. Por módulo:
   **97,64 %** para BD y **93,55 %** para serving. El porcentaje comprende
   unittest más la integración CLI con los archivos completos reales;
   todavía no mide `src/api`, que corresponde a la fase 3.
7. Comparación de cada observación de ambas BD contra gold: igualdad de
   claves, fecha, casos, brote y umbral. Comparación Alembic/ORM: **sin
   diferencias** en ambos motores. `alembic upgrade head --sql` también
   generó SQL PostgreSQL con las nueve tablas y `alembic_version`.
8. `.venv/bin/python -m pip check`: **No broken requirements found**.
   Comprobación SHA256 de los **503 archivos** iniciales de datos y resultados
   de modelado: **0 alterados**. La fixture de doce filas coincide con su
   selección de gold; ocho contienen cero casos.

Se ejecutó una primera prueba de calendario cuyo cambio de semana provocaba
una llave duplicada. Se corrigió la selección del caso de prueba; la última
ejecución completa es la indicada arriba y pasó todos los tests.

## Cifras consultadas en ambas bases

| Resultado | Valor |
|---|---:|
| Distritos | 65 |
| Observaciones semanales | 30 485 |
| Observaciones con cero casos | 23 756 |
| Observaciones con casos nulos | 0 |
| Etiquetas de brote positivas | 3 002 |
| Filas históricas Excel MINSA | 27 105 |
| Casos históricos Excel MINSA | 172 768 |
| Filas Sala Situacional 2025 | 3 380 |
| Casos Sala Situacional dentro del panel | 1 114 |
| Cargas después de repetir | 1 |
| Modelos / predicciones publicados | 0 / 0 |

El último domingo observado es **2025-12-21** y su cierre,
`fecha_corte_datos`, es **2025-12-27**. Este corte representa el panel
disponible y no la fecha actual de ejecución. La semana 53 de Sala permanece
fuera del panel; la carga no la añade ni redistribuye sus casos.

## Pendientes y límites

- Supabase: no se probó porque aún no está configurada su conexión. Sí se
  comprobó PostgreSQL real local, con el mismo driver y migración.
- Windows: los módulos y comandos están preparados para ambos sistemas;
  la ejecución de esta fase ocurrió en macOS. No se afirma una ejecución
  en PowerShell.
- Inferencia, cálculo del estado del modelo, alertas, runs de servicio en
  MLflow y publicación idempotente de predicciones: fase 2, pendiente de
  aprobación. No se utilizó el Model Registry.
- API, cobertura de sus endpoints, benchmark, CI, documentación completa
  y despliegue: fases siguientes.
- Se conservan las decisiones aprobadas: ceros como ceros, alertas visibles
  desde probabilidad 0,50 y `alerta_modelo` independiente según umbral F1.
  Su discrepancia y el incumplimiento actual de los umbrales de aceptación
  siguen pendientes para la presentación de predicciones experimentales.

La fase se detiene aquí para revisión de Rosa antes de iniciar la fase 2.
