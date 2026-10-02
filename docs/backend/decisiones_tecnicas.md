# Decisiones técnicas del backend

Las diferencias con el documento OE2 y su justificación están en
[desviaciones_oe2.md](desviaciones_oe2.md); aquí se resumen las decisiones de implementación.

## Stack

- **FastAPI + Pydantic v2:** contrato tipado, OpenAPI generado, validación con 422 uniforme.
- **SQLAlchemy 2 + Alembic + psycopg 3:** un mismo esquema para PostgreSQL y SQLite (pruebas);
  las migraciones son la autoridad del esquema (nunca `create_all` al arrancar).
- **Portabilidad:** `sqlalchemy.Enum` nativo en PostgreSQL y CHECK en SQLite;
  `JSON().with_variant(JSONB)`; CHECK con regex o aritmética de fechas solo en PostgreSQL
  (`ddl_if`), con equivalentes en SQLite y validación en el ORM.

## Datos y modelo

- **El modelo no cambia:** el ajuste de servicio reutiliza `ajustar_modelos`, `PARAMETROS_BASE` y
  las variantes del protocolo compacto; las métricas son las del protocolo temporal guardado.
- **Vector reconstruido desde la BD:** `construir_filas_futuras` sobre el panel leído de
  `observacion_semanal`. Verificado contra gold (diferencia máxima 1,8e-15) y contra el pipeline
  anterior (probabilidades idénticas).
- **Booster en Storage**, no en la BD: ruta lógica `modelos/<codigo>.json` + SHA-256; un hash
  distinto bloquea la inferencia (409).
- **UPSERT de predicciones** por `(ubigeo, id_semana_corte, horizonte)`: el historial de un mismo
  corte no se conserva; queda la trazabilidad por `id_ejecucion` y `fecha_generacion`.
- **Parámetros en la BD:** cortes de riesgo, umbrales (con bloque decisor `temporada_2024`) y
  regla de brote viven en `parametro_sistema`; `config.yaml` solo siembra la selección experimental.

## Demo experimental (desviación temporal)

El CHECK `estado <> 'activa' OR cumple_umbrales` se respeta: las versiones quedan `candidata`. Si
no hay versión activa y `servir_no_validadas = true`, la inferencia usa
`parametro_sistema.seleccion_experimental` y la API marca `experimental: true`. Con
`servir_no_validadas = false` las predicciones se guardan `no_disponible` con motivo.

## Seguridad

- Escrituras con `X-API-Key` (comparación en tiempo constante); sin clave configurada, 503.
- RLS y roles `rol_api` / `rol_pipeline` (NOLOGIN) creados por la migración en PostgreSQL. La API
  local se conecta como propietario de las tablas, al que RLS no aplica.
- `.env` no se versiona; errores sin SQL ni credenciales; CORS restringido a `cors_origen`.

## Rendimiento

DTO por lotes (sin N+1), caché de lecturas de 10 s invalidada por `max(id_ejecucion)` y booster
cacheado en memoria. Benchmark local: lecturas p95 ≤ 32 ms; inferencia ≈ 3,6 s (< 5 s).

## Pendiente (fuera de TB1)

Adaptador Supabase Storage y despliegue (Supabase/Render), monitoreo de deriva, scheduler semanal,
un modelo que cumpla los umbrales y polígonos distritales para el mapa.
