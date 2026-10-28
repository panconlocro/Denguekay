# Arquitectura del backend (esquema OE2)

Fuente de diseño: documento «OE2 Diseño de la Solución v1.1» (sección 5, Anexo B, Tabla 2),
resumido en [especificacion_oe2.md](especificacion_oe2.md). En TB1 todo es local.

## Contexto

```mermaid
flowchart LR
  fuentes[Excel MINSA, Sala Situacional, Open-Meteo, INEI] --> pipeline[Pipeline de datos y modelado<br/>bronze → silver → gold]
  pipeline --> batch[Carga y publicación<br/>src/serving]
  batch --> bd[(PostgreSQL local<br/>esquema OE2)]
  batch --> storage[(models/storage<br/>modelos/geodatos/reportes)]
  batch --> mlflow[(MLflow local)]
  api[FastAPI<br/>src/api] --> bd
  api --> storage
  frontend[Frontend React<br/>fuera de TB1 backend] --> api
```

## Contenedores y componentes

| Componente | Responsabilidad |
|---|---|
| `src/db` | Esquema SQLAlchemy portable (PostgreSQL / SQLite), migraciones Alembic (`0003_oe2`), sesiones y UPSERT |
| `src/serving/cargar_datos` | Ingesta validada (GX + linaje) de provincia, distrito, calendario y observaciones |
| `src/serving/modelos`, `publicar` | Ajuste de servicio con `src/modeling/train.py`, MLflow, versiones `candidata` y booster en Storage |
| `src/serving/almacenamiento` | Puerto `Almacenamiento` (`guardar`, `leer`, `existe`) y adaptador local; adaptador Supabase futuro |
| `src/serving/inferencia` | Vector desde la BD (`construir_filas_futuras`), selección activa/experimental, UPSERT, alertas, OOS |
| `src/serving/parametros` | Lectura de `parametro_sistema` (cortes, umbrales y bloque, selección experimental) |
| `src/api` | Routers de la Tabla 2, DTO por lotes, errores uniformes, caché por revisión, OpenAPI con ejemplos reales |

## Modelo de datos

Nueve tablas del DDL (`provincia`, `distrito`, `semana_epidemiologica`, `ejecucion`,
`observacion_semanal`, `version_modelo`, `prediccion`, `alerta`, `parametro_sistema`) más la
extensión `importancia_variable`. `ejecucion` audita todo (`ingesta`, `inferencia`,
`reentrenamiento`, `mantenimiento`). En PostgreSQL: ENUM nativos, `jsonb`, identity, CHECK con
regex, RLS y roles `rol_api` / `rol_pipeline`.

## Secuencia: publicación

```mermaid
sequenceDiagram
  participant CLI as publicar
  participant F as Fuentes (data/, solo lectura)
  participant M as train.py + MLflow
  participant S as Storage local
  participant BD as PostgreSQL
  CLI->>F: GX, linaje y hashes
  CLI->>BD: ejecucion ingesta + upsert de catálogo y observaciones
  CLI->>M: ajuste de servicio (mismos hiperparámetros) y run MLflow
  CLI->>S: modelos/<codigo>.json
  CLI->>BD: version_modelo candidata (sha256, cumple_umbrales con parametro_sistema)
  CLI->>BD: predicciones OOS como cortes pasados
  CLI->>BD: inferencia del corte vigente (UPSERT) y alertas
  CLI->>BD: ejecucion reentrenamiento exitosa (una transacción)
```

## Secuencia: inferencia por la API

```mermaid
sequenceDiagram
  participant C as Cliente (X-API-Key)
  participant A as POST /admin/inferencias
  participant BD as PostgreSQL
  participant S as Storage
  C->>A: {horizonte, id_semana_corte}
  A->>BD: versión activa o seleccion_experimental
  A->>BD: panel de casos + población 2017 hasta el corte
  A->>A: construir_filas_futuras (en memoria, sin persistir)
  A->>S: booster y verificación SHA-256
  A->>BD: UPSERT prediccion, alertas, ejecucion inferencia
  A-->>C: resumen (experimental, disponibles, alertas)
```

## Límites

- Corte de datos publicado: 27/12/2025; sin actualización automática ni scheduler.
- Ninguna versión cumple los umbrales: la demo sirve predicciones `experimental: true`.
- El mapa usa centroides; no hay polígonos en la referencia del proyecto.
