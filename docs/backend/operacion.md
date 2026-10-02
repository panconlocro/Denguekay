# Operación del backend

## Alcance disponible: fases 1–4

Esquema relacional, carga validada, versiones XGBoost de servicio y publicación
batch con historial y API FastAPI. La inferencia carga boosters desde la BD;
activación/recalculado HTTP conservan historial en una transacción. Se comprobó PostgreSQL
local; no se ha desplegado ni comprobado una conexión a Supabase.

## Variables de entorno

Copiar `.env.example` como `.env`, ignorado por Git. `DATABASE_URL` es
obligatoria; las variables del entorno tienen prioridad sobre `.env`.
`API_KEY` protege las escrituras HTTP mediante `X-API-Key`. Configurar una
clave larga, aleatoria y privada. Si falta, las escrituras devuelven 503;
si es incorrecta o ausente en la solicitud, 401. No afecta la lectura pública.
No pegar credenciales en comandos compartidos ni en documentación.

Para PostgreSQL usar el formato
`postgresql+psycopg://usuario:clave@servidor:puerto/base`. En una conexión
Supabase configurar SSL con `?sslmode=require` y usar la cadena y el puerto
proporcionados por el proyecto. Una clave con caracteres especiales debe
estar codificada como parte de la URL. No se requieren PostGIS ni JSONB.

Para probar con SQLite usar `DATABASE_URL=sqlite:///models/serving/backend.db`
en `.env` y crear primero `models/serving/`. No existe una conexión automática
a una BD alternativa cuando falta configuración.

## Instalar, migrar y cargar

Ejecutar desde la raíz del repo. En macOS:

```bash
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -c "from src.utils.paths import SERVING_MODELS; SERVING_MODELS.mkdir(parents=True, exist_ok=True)"
.venv/bin/alembic upgrade head
.venv/bin/python -m src.serving.cargar_datos
.venv/bin/python -m src.serving.publicar --horizontes 2 4
.venv/bin/python -m unittest discover -s tests
```

En PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -c "from src.utils.paths import SERVING_MODELS; SERVING_MODELS.mkdir(parents=True, exist_ok=True)"
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\python.exe -m src.serving.cargar_datos
.\.venv\Scripts\python.exe -m src.serving.publicar --horizontes 2 4
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

La carga exige los dos gold, el integrado y su cobertura, el histórico, la
Sala, el catálogo, los centroides y `manifest_fase6.json`. Usa
`auditar_traspaso` y `validar_entradas_modelado`; no hay opción para omitir
esas validaciones. Verifica además la correspondencia de casos 2025 con la
Sala y el calendario MMWR compartido. Las semanas de Sala que no aparecen
en gold no se incorporan silenciosamente.

Una transacción inserta/actualiza distritos y observaciones junto con su
auditoría. Si falla, se revierte todo el lote. La huella incluye los SHA256
de nueve archivos y la revisión de la transformación. Repetir la misma
carga devuelve `reutilizada: true`, mantiene las fechas de actualización y
no crea otra ejecución. Ejecuciones concurrentes con la misma huella se
protegen por unicidad: una puede ser rechazada y se reintenta tras terminar
la otra. La carga se realiza localmente; la API desplegada leerá desde BD.

Los casos cero se conservan como cero. Una observación nula requiere motivo;
la carga completa actual exige casos poblados por las validaciones existentes.
No se fabrican semanas ausentes. Las etiquetas y umbrales de brote vienen de
gold, sin recalcularse.

## Publicar inferencia

`publicar` incluye la carga; ejecutar `cargar_datos` antes es opcional. Hace
las validaciones GX, contrasta hashes, fechas, etiquetas y métricas OOS con
el protocolo compacto, ajusta modelos mediante `train.ajustar_modelos` y
registra runs normales en MLflow. No usa el Model Registry. Requiere las
dependencias MLflow/GX del repo; el backend desplegado usará la BD y no
necesitará una copia del `mlflow.db` local para inferir.

Si falta `models/experimentos/validacion_temporal_compacta/predicciones_por_bloque.csv`,
ejecuta el módulo compacto existente con salida en
`models/serving/protocolo_regenerado/`, incluida su evaluación correspondiente.
Ese entrenamiento puede tardar más y producir variaciones CPU/GPU; no
sobrescribe las métricas de Rosa en `docs/modeling/metricas/`.

En `config/config.yaml`, `serving` configura variantes, horizontes, intervalos
de riesgo, alerta visible, criterio de aceptación y disponibilidad. Horizonte
3 admite configuración, pero su publicación se rechaza hasta contar con gold
y contrato. Con `servir_no_validadas: false`, la función de disponibilidad
rechaza versiones experimentales y los endpoints aplican esa regla.

La aceptación comprueba **2024** y conserva **2025** como sensibilidad, sin
promediarlos. Las versiones de servicio conservan el JSON del booster en BD;
las versiones OOS históricas de clasificación/regresión no tienen booster y
son **no reactivables**, según lo aprobado. Sus predicciones siguen consultables.
La persistencia se guarda como referencia, con su regla y sus métricas.

La publicación genera un objetivo por horizonte desde el último cierre.
No extiende el panel con observaciones inventadas: los pasos intermedios de
calendario existen solo en memoria con casos ausentes. Una fila incompleta
queda en `ejecucion_prediccion.resumen.no_disponibles`, con distrito y motivo.

Identidad de ejecución: fuentes, protocolo, configuración, código, parámetros,
XGBoost y plataforma. Repetirlos devuelve `reutilizada: true` sin otra versión,
predicción, alerta ni run. Otra identidad crea una ejecución y conserva el
historial. Solo puede existir una versión activa por horizonte/tipo.

Las versiones, predicciones y cambios de alertas se confirman en una sola
transacción. Si falla, la ejecución queda `fallida`, sin confirmar ese lote,
y se puede reintentar. Una ejecución `en_proceso` impide otra publicación
idéntica. Si el proceso fue interrumpido abruptamente, comprobar que terminó
y revisar sus artefactos antes de marcar esa ejecución como fallida en BD;
el CLI no fuerza el desbloqueo de un proceso que podría seguir activo.

Los artefactos locales quedan en `models/serving/ejecuciones/<huella>/`:
reporte de servicio, evaluación temporal importada, JSON de modelos, vectores
futuros y resumen. La BD permite reevaluar sin acceso a esa carpeta.

Alertas visibles: riesgo Alto/Muy alto, desde 0,50. `alerta_modelo` conserva
el umbral F1 del protocolo, que puede ser distinto. Al publicar otro lote se
retiran alertas activas de esos horizontes; las alertas retrospectivas se
importan retiradas con motivo explícito, sin inventar fechas de avisos pasados.

## Verificación de la carga

Consultar `carga_datos` para hashes, resultado de GX, corte y número de filas.
Comprobar que `(ubigeo, anio, semana)` es único y que `ubigeo` conserva seis
dígitos. `fecha_corte_datos` es el sábado de cierre de la última semana
observada; `fecha_actualizacion` es el instante UTC de escritura. Ninguna
de esas fechas se interpreta como una actualización automática del panel.

Las geometrías se guardan como NULL con un motivo explícito: los archivos
disponibles contienen centroides. GeoJSON usa esos puntos como Point,
declarando la ausencia de polígonos.

## Levantar y comprobar la API

Con `.env` configurado y la BD migrada/poblada, desde la raíz:

```bash
.venv/bin/python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000
```

En PowerShell:

```powershell
.\.venv\Scripts\python.exe -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000
```

Abrir `/docs` y comprobar `/api/v1/salud` en ese servidor. Las lecturas son
públicas; en Authorize de Swagger, cargar la clave privada para los POST.
GET `/api/v1/predicciones?horizonte=2` y `/api/v1/mapa?horizonte=4` devuelven
el último lote por horizonte, con sus fechas. GET `/api/v1/modelos` identifica
los IDs reales para detalle y activación. No es necesario reentrenar al
iniciar la API ni para reevaluar.

Para la copia local ya verificada, usar en `.env`
`DATABASE_URL=sqlite:///models/serving/fase3.sqlite`; para la original de fase
2, `sqlite:///models/serving/fase2.sqlite`. Las escrituras modifican la BD
seleccionada, agregando otra ejecución; no intercambiar URLs sin comprobar
qué base se está operando. No se creó ni modificó un `.env` con credenciales
durante la verificación: las ejecuciones usaron variables locales de proceso.

La API requiere sus módulos Python, dependencias y `config/config.yaml`.
Lee únicamente la BD para servir observaciones, versiones y predicciones;
no requiere copiar los datasets ni los archivos de boosters a Render.
`serving.cors_origen` contiene el origen exacto del frontend. La caché de
lecturas dura diez segundos, comprueba cambios de publicación y se invalida
al escribir; es local a cada proceso.

La exportación usa la BD seleccionada y no ejecuta escrituras:

```bash
.venv/bin/python -m src.api.exportar_openapi
```

En PowerShell sustituir el ejecutable por `.\.venv\Scripts\python.exe`.
El contrato exportado y los ejemplos se versionan en `docs/backend/openapi.json`.
No regenerarlo con una BD vacía si se quieren conservar ejemplos de todos
los recursos. Las fuentes reales y la fecha de corte se conservan en cada
ejemplo; no usarlo como copia de datos actualizados.

## Respaldo y reversión

Respaldar PostgreSQL antes de cualquier operación que modifique el esquema.
`alembic downgrade base` **elimina las tablas**; solo se prueba en bases
temporales vacías y no es el mecanismo de rollback de modelos. Los registros
históricos de versiones, predicciones y alertas tienen claves foráneas sin
borrado en cascada. La migración 0002 conserva la carga previa; su downgrade
se comprueba solo en una BD temporal vacía, porque 0001 no admite boosters
históricos nulos. La activación transaccional con auditoría ya existe; su
exposición HTTP y reevaluación controlada están implementadas en fase 3.

Para volver a otra versión usar POST `/api/v1/modelos/{identificador}/activar`
con la clave: desactiva la previa, valida esquema/corte y reevalúa los vectores
vigentes. Conserva el historial, registra cambios reales y retira las alertas
previas del horizonte. Si falta artefacto o existe fuga temporal, responde
409 y revierte todo. Los históricos sin booster no son candidatos de rollback.
Esta selección de inferencia no sustituye la aprobación de producción.

Para reproducir la verificación local de SQLite de fase 2, usar
`DATABASE_URL=sqlite:///models/serving/fase2.sqlite`. Es un archivo físico
local bajo `models/serving/`; no se sube a Git. Las pruebas unitarias usan
archivos temporales separados y los eliminan al terminar. Consultar los
resultados medidos en `fase2_inferencia.md` y `fase2_verificacion_*.json`.

La verificación post-despliegue y el guion de demo quedan pendientes de la
fase 5 y de su aprobación.

## Calidad, cobertura y benchmark (fase 4)

Los tests usan SQLite temporal migrada y muestras agregadas reales versionadas en
`tests/fixtures/backend/`; su manifiesto identifica las fuentes. No requieren los
gold completos, `mlflow.db` ni boosters locales de Rosa. El pipeline de publicación
completo sí requiere esos archivos de entrada descritos arriba.

Desde la raíz, en macOS:

```bash
.venv/bin/python -m coverage run -m unittest discover -s tests
.venv/bin/python -m coverage report --fail-under=80
.venv/bin/python -m coverage xml
.venv/bin/python -m src.api.benchmark
```

En PowerShell:

```powershell
.\.venv\Scripts\python.exe -m coverage run -m unittest discover -s tests
.\.venv\Scripts\python.exe -m coverage report --fail-under=80
.\.venv\Scripts\python.exe -m coverage xml
.\.venv\Scripts\python.exe -m src.api.benchmark
```

`.coveragerc` mide todos los módulos de API, serving y BD, incluidas migraciones y
CLI. El último comando usa la BD real seleccionada por `DATABASE_URL` mediante
TestClient: declara que no mide una conexión HTTP de red. Para medir el servidor
Uvicorn ya levantado:

```bash
.venv/bin/python -m src.api.benchmark --url http://127.0.0.1:8000 --repeticiones 20
```

Por defecto mide solo lecturas: reporta las escrituras como no medidas y el SLA
completo como falso. Para medir las 16 operaciones, seleccionar una **copia de la
BD** en el servidor y usar `--incluir-escrituras`, con `API_KEY` en el entorno
privado del cliente. Cada POST agrega una ejecución y sus predicciones reales;
activar la versión ya seleccionada también reevalúa, sin inventar un cambio de
selección en la auditoría. El historial anterior permanece. No se necesita
reentrenar para estas mediciones. Ejemplo sobre un servidor que usa esa copia:

```bash
.venv/bin/python -m src.api.benchmark --url http://127.0.0.1:8000 --repeticiones 20 --incluir-escrituras
```

La salida predeterminada es `models/serving/benchmark.json`. `--salida` permite
una ruta bajo `models/` o `docs/backend/`, nunca `data/`. Hay dos mediciones de cada
GET: `Cache-Control: no-cache` y caché habilitada; los POST no tienen calentamiento.
Se conservan duraciones individuales, p50/p95 interpolados, estados HTTP, errores,
cabeceras de caché, versiones activas y corte. Retorno 0: SLA de los casos medidos
cumplido; 2: errores o p95 incumplido; 1: configuración/descubrimiento fallidos.
Comprobar siempre `cobertura_completa` y `no_medidos`, además del código de retorno.

Los reportes versionados son una evidencia fechada de la ejecución local, no una
promesa para Render. No incluyen URL de BD ni API key. No acreditan carga de
página, concurrencia, arranque en frío o disponibilidad mensual. Los servicios
locales usados para medir se detienen al cerrar la verificación.

El workflow `.github/workflows/backend.yml` instala requisitos, ejecuta toda la
suite, exige 80 % de cobertura y publica XML por sistema: Linux, Windows y macOS.
Se activa en push/PR o manualmente. Una ejecución local de la misma suite sobre
una copia con solo archivos versionables comprueba independencia de entradas
ignoradas. El resultado remoto del workflow debe revisarse tras hacer push;
no se considera ejecutado en Windows por haber escrito su configuración.
Referencias: [workflow Python oficial](https://docs.github.com/en/actions/tutorials/build-and-test-code/python),
[setup-python](https://github.com/actions/setup-python),
[artefactos de CI](https://github.com/actions/upload-artifact).

## Preparación de Supabase y comprobación posterior (fase 5 pendiente)

Esta es una guía de preparación; el despliegue requiere aprobación de su fase.
Crear/seleccionar el proyecto Supabase, obtener la cadena PostgreSQL desde su
panel y conservarla en `.env` local y en los secretos del servicio. Elegir la
conexión directa o el pooler de sesión compatible con el entorno y sus puertos,
según [la guía oficial de conexión](https://supabase.com/docs/guides/database/connecting-to-postgres).
El pipeline y Alembic necesitan operaciones transaccionales: comprobar la
modalidad de conexión antes de migrar. Añadir `sslmode=require` y probar conexión
sin imprimir la URL. No usar una clave del frontend como contraseña PostgreSQL.

Ejecutar `alembic upgrade head` y `src.serving.publicar --horizontes 2 4`
localmente con esa conexión. Confirmar esquema, cortes, disponibilidad y hashes
antes de apuntar la API al proyecto. Render necesitará Python/dependencias,
`config/config.yaml`, módulos `src/`, `DATABASE_URL` y `API_KEY`, además del origen
React en la configuración. La manifestación concreta de Render se prepara en
fase 5; no se ha publicado un servicio en esta fase.

Después del despliegue, el equipo debe registrar la URL y fecha de verificación:

1. GET `/api/v1/salud`: 200, conexión, versiones, corte y última ejecución reales.
2. Consultar catálogo, observado, predicción, mapa, serie, alertas y modelo;
   comparar los IDs/cortes con la misma BD publicada localmente.
3. Probar 404 de recurso, 422 de parámetros y 401 sin clave en un POST. No provocar
   una caída de la BD compartida; comprobar 503 en un entorno de ensayo separado.
4. En un entorno de ensayo con clave, recalcular un horizonte; comprobar que usa
   el booster de BD, conserva OOS/historial y no cambia el corte ni el otro horizonte.
5. Activar una versión compatible disponible, verificar auditoría y revertir;
   una versión experimental no se denomina validada por esta operación.
6. Exportar OpenAPI contra esa BD y medir HTTP con `benchmark --url` remoto;
   medir también arranque en frío y registrar condiciones de infraestructura.
7. Con React, verificar selección, huecos, leyendas, CORS y carga de páginas;
   medir disponibilidad durante un periodo explícito. HU0016-3 requiere API <5 s,
   página <10 s y disponibilidad ≥95 %, no solo un benchmark local.

## Mantenimiento, datos recientes y responsables

El equipo de soporte revisa salud, errores HTTP, corte de fuentes y última
publicación. Un servicio sano con corte antiguo no implica datos recientes. La
frecuencia objetivo es semanal cuando haya un boletín disponible; no se creó
una automatización ni se simula la llegada de fuentes.

Ante datos nuevos: ejecutar el pipeline documentado en README y `docs/estructuraRepo.md`,
validar silver/gold y calendario, repetir el protocolo temporal y contrastar sus
hashes/resultados; entonces publicar una versión nueva. Si cambian gold y métricas
no corresponden, la publicación debe fallar, no reutilizar la evaluación anterior.
La reevaluación HTTP usa los mismos vectores y no sustituye este proceso.

Rosa revisa decisiones de modelado y aceptación conforme a las reglas del repo;
el equipo desarrollador opera migraciones/publicación y conserva evidencia.
Acordar el responsable concreto de credenciales, backups y monitoreo antes del
despliegue. No hay detector automático de deriva implementado ni umbrales
aprobados: HU0009-2 queda pendiente. Registrar cualquier sospecha de degradación,
revisar métricas por bloque y evaluar/reentrenar antes de promover una versión.

Para recuperar un fallo: respaldar la BD, comprobar proceso/conexión/migraciones,
revisar último lote y activar una versión anterior compatible con artefacto mediante
el POST protegido. Si no existe versión validada, el retorno es técnico y
experimental; no satisface por sí mismo una recuperación a producción validada.
La restauración desde backup es distinta de activar un modelo; ensayarla en una
BD separada antes de sustituir datos compartidos. No borrar versiones ni ejecutar
downgrade sobre una BD de trabajo para resolver un fallo de inferencia.
