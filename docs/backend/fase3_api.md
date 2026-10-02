# Fase 3: API integrada con BD y modelos

## Trabajo realizado

Se implementaron las 16 operaciones HTTP del encargo en `/api/v1`, con FastAPI
y Pydantic v2. Los routers separan catálogo, datos, vigilancia y modelos.
Lecturas SQLAlchemy usan únicamente la BD; la reevaluación importa el servicio
existente de inferencia y lee el booster JSON y los vectores almacenados.
No se reentrenaron las versiones de servicio ya publicadas ni se importaron
nuevos resultados de Rosa. Las pruebas sí ajustan XGBoost sobre la muestra
real ya versionada, en bases temporales independientes.

La API distingue ceros/faltantes, muestra procedencia y corte, conserva las
retrospectivas OOS y calcula validación desde métricas. Mapas incluyen todos
los distritos y usan centroides reales; no hay polígonos inventados. Los POST
usan clave privada, guardan otra ejecución y conservan el historial.
Una activación incompatible o con fuga se revierte. La promoción a producción
sigue pendiente: seleccionar una versión experimental para la demo no la valida.

Se agregó caché acotada con TTL y revisión en BD, CORS restringido, cabeceras
de tiempo y errores homogéneos. OpenAPI documenta parámetros/esquemas en
español y tiene ejemplos reales para las 16 operaciones, incluidos POST
obtenidos de ejecuciones ya guardadas. Su exportación no publica predicciones.

## Archivos creados o modificados

Nuevos: `src/api/` (aplicación, dependencias, errores, esquemas, consultas,
caché, OpenAPI/exportador y cuatro routers), `src/serving/reevaluacion.py`,
`tests/test_api_backend.py`, `docs/backend/contrato_api.md`, `openapi.json`,
`fase3_verificacion.json` y este cierre.

Modificados: `src/serving/publicacion.py` acepta motivo de activación;
`src/serving/artefactos.py` controla errores de carga del booster;
`src/utils/paths.py` centraliza las nuevas salidas; `.env.example` documenta
la clave; `README.md`, `docs/estructuraRepo.md` y `docs/backend/operacion.md`
describen estructura y uso. No hubo cambio de esquema ni migración nueva.

## Ejecuciones y cifras verificadas

Evidencia reproducible: [fase3_verificacion.json](fase3_verificacion.json).
Comandos ejecutados desde la raíz en macOS:

```bash
.venv/bin/python -m src.validation.calidad_gx
.venv/bin/python -m unittest discover -s tests -p test_api_backend.py
.venv/bin/python -m coverage run --source=src/api,src/serving,src/db -m unittest discover -s tests
DATABASE_URL=sqlite:///models/serving/fase3.sqlite .venv/bin/python -m coverage run --append --source=src/api,src/serving,src/db -m src.api.exportar_openapi
.venv/bin/python -m coverage report --fail-under=80
.venv/bin/python -m coverage json -o models/serving/cobertura_fase3.json
```

GX: silver 107/107 expectativas; gold h2 y h4, 92/92 cada uno. Cada entrada
tiene 30 485 filas. La suite completa pasó **241 tests**, incluidos **23
nuevos de API**, en 41,657 segundos en la ejecución reportada. La cobertura
de líneas de API/serving/db fue **89,94 %** (1582/1759); API **98,87 %**
(699/707). Incluye suite completa y exportación real con `coverage --append`;
no incluye scripts manuales HTTP. El JSON completo queda local, sin versionar.

Se creó `models/serving/fase3.sqlite` mediante respaldo SQLite de la BD de
fase 2. Se levantó Uvicorn en localhost y se probaron por HTTP real las 14
lecturas y 2 escrituras: **16 respuestas HTTP 200**. Se probó además
401 sin clave, 404 distrito desconocido, 422 horizonte inválido y caché
MISS/HIT. Las pruebas unitarias comprueban 503 ante ausencia/fallo de BD,
incluso si había una lectura en caché. Una prueba aislada bloquea aperturas
de archivos bajo `data/` y `models/` y comprueba consultas y POST de inferencia.

Se creó `denguekay_fase3_pruebas` como copia del PostgreSQL local de fase 2,
sin modificar esa base original. Se comprobaron las mismas **16 operaciones**
con TestClient y PostgreSQL real. La verificación PostgreSQL no es una
prueba de Supabase ni un despliegue remoto.

Ambas copias finalizaron con 65 distritos, 30 485 observaciones, 30 versiones,
27 300 predicciones, 3 ejecuciones, 6 cambios históricos de selección y
4002 alertas conservadas. Cada POST agregó 65 filas de h=2; el POST de
activación solicitó la versión ya activa y registró reevaluación sin inventar
otro cambio de selección. Los tests sí verifican activar otra versión real
y retornar a la anterior, con auditoría y predicciones preservadas.

Los vigentes consultables son 65 por horizonte. Objetivos de la BD:
h2 **2026-01-04** y h4 **2026-01-18**, con corte **2025-12-27**, riesgo Bajo
en todos los distritos de esas publicaciones y estado experimental.
Reevaluar no avanzó el calendario ni alteró los OOS. Se comprobó que
actualizar h2 conserva filas y fecha de h4. Comparación SHA256 de **503
archivos** de entradas/métricas/experimentos: **0 modificados**.

## Límites y pendientes

La fase 3 no incorpora datos observados posteriores a 2025. Las métricas
no cumplen aceptación; la demo permite experimentales por la configuración
aprobada. Se conserva la distinción riesgo visible ≥0,50 frente a umbral F1;
su discrepancia sigue expuesta, sin afirmar calibración. No hay gold/modelo
h3 ni geometrías poligonales disponibles. Los históricos sin booster son
no reactivables; la auditoría opcional de otros boosters de Rosa queda pendiente.

No se ejecutó Windows ni una conexión Supabase; la verificación fue en
macOS, SQLite y PostgreSQL local. No hubo Model Registry, promoción ni
despliegue. Los scripts de prueba detuvieron los servidores locales al
terminar; las copias de BD permanecen disponibles para desarrollo.

Quedan en fase 4: benchmark SLA p50/p95, CI y documentación integral de
arquitectura/decisiones/trazabilidad. Quedan en fase 5, previa aprobación:
Render/Supabase, verificación post-despliegue y guion de demo. No se interpreta
la latencia de una llamada de esta verificación como cumplimiento del SLA.
