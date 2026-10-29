# apps/web · Frontend (plan)

Todavía no hay código: este README fija el plan para cuando empiece el encargo del frontend. Lo que
aquí figura como «por decidir» se acuerda con Rosa antes de implementarlo.

**Para empezar:** [docs/backend/guia_frontend.md](../../docs/backend/guia_frontend.md) explica cómo levantar
la API en local con la BD de demostración, dónde está el contrato v1 y cómo generar los tipos TypeScript.

## Qué es

Una aplicación web de una sola página que muestra a los usuarios de vigilancia el riesgo de brote de
dengue por distrito de Piura. **Solo consume la API** (`apps/api`, `/api/v1`): no lee la BD, ni `data/`,
ni los modelos, y no recalcula nada. Todo lo que muestra sale de la respuesta de un endpoint.

## Stack

- **React + Vite** (decisión del [ADR 0001](../../docs/decisions/0001-repo-restructure.md)).
- El servidor de desarrollo de Vite usa `http://localhost:5173`, que ya es el origen CORS permitido por la
  API (`serving.cors_origen` en `configs/config.yaml`).
- Por decidir: TypeScript (los tipos se pueden generar del contrato; ver la guía), librería de mapas (el mapa
  de riesgo llega como GeoJSON),
  librería de gráficos, gestor de estado/consultas y framework de tests.

## Pantallas y endpoints

| Pantalla | Endpoints | HU |
|---|---|---|
| Arranque: horizontes disponibles y por defecto, leyenda, cortes y nota experimental | `GET /configuracion` | — |
| Tablero del corte vigente: niveles de riesgo, alertas activas, casos estimados de la región | `GET /tablero/resumen?horizonte=` | HU0012 |
| Mapa de riesgo por distrito (centroides; «Sin datos» cuando no hay predicción) | `GET /mapa-riesgo?horizonte=` | HU0014 |
| Serie del distrito: casos observados y predicciones semana a semana | `GET /series/{ubigeo}?horizonte=&desde=&hasta=` | HU0013 |
| Predicciones por distrito para un corte | `GET /predicciones?horizonte=&corte=` | HU0010, HU0011 |
| Alertas, con filtros por horizonte, distrito, nivel y estado, y su detalle | `GET /alertas`, `GET /alertas/{identificador}` | HU0015 |
| Modelo en uso, su detalle y sus importancias | `GET /modelos/activo`, `GET /modelos/{identificador}`, `.../variables` | HU0008 |
| Catálogo de distritos y observaciones | `GET /distritos`, `GET /distritos/{ubigeo}`, `GET /observaciones` | — |
| Estado del servicio | `GET /salud` | HU0016 |

Las escrituras (`POST /admin/inferencias` y `POST /admin/modelos/{version}/activar`) exigen `X-API-Key`.
Quedan fuera de la primera versión del frontend: la clave no debe viajar a un navegador público.

## Reglas que el frontend debe respetar

- **El contrato es `docs/backend/openapi_v1.json`** (v1.0.0; `openapi.json` es el mismo con ejemplos
  reales). Los campos están en español (por ejemplo `probabilidad_brote`, `nivel_riesgo`, `semana_corte`) y
  no se renombran en la interfaz de datos. La versión del contrato llega en la cabecera `X-Version-Contrato`.
- **Nada en código duro:** horizontes, horizonte por defecto, cortes, niveles y leyenda salen de
  `GET /configuracion`.
- **`ubigeo` es texto de seis dígitos** (con ceros a la izquierda): nunca se convierte a número.
- **`experimental: true` se muestra siempre.** Hoy ninguna versión cumple los umbrales de aceptación
  (HU0007-4) y la API sirve la [v0](../../models/registry/v0/ficha.md) como demo experimental; la interfaz
  lo dice en cada vista que muestre predicciones (el tablero y `/modelos/activo` traen el texto en `nota`).
- **Faltantes, no ceros:** un valor `null` con `disponible: false` y `motivo` se muestra como «sin datos»
  con su motivo, no como 0. Un horizonte sin modelo (hoy h=3) responde «sin modelo para h=N» y la interfaz
  lo explica.
- **Horizontes 2, 3 y 4 semanas**, elegibles por el usuario entre los `horizontes_disponibles`; el horizonte
  por defecto es el de `/configuracion` (4).
- **Intervalos de casos:** hoy son `null` con `motivo_intervalo`; la interfaz debe mostrarlos cuando lleguen.
- **Mapa:** la geometría puede ser `Point` (hoy), `Polygon` o `MultiPolygon`.
- Textos en español y unidades en los gráficos (casos, casos por 100 000 hab.).

## Cómo se integrará en el repo

- Código en `apps/web/` con su propio `package.json`; no se mezcla con el paquete Python.
- La URL de la API se configura por variable de entorno de Vite (nombre por decidir); en desarrollo,
  `http://127.0.0.1:8000/api/v1`.
- Un job del CI para `apps/web` (instalación, lint, tests y build) se agrega en el mismo encargo.
- Al empezar, se actualiza `docs/architecture.md` con la estructura interna de `apps/web/`.
