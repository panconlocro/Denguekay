# Estado del proyecto

*Actualizado: 12/11/2026. Se actualiza en cada release `develop → main`.*

## Etapa

OE3 (desarrollo completo). El EDA y OE2 (diseño) están cerrados.

## Modelo

| Versión | Qué es | Estado | Tag |
|---|---|---|---|
| v4 | `b3_obs` con casos confirmados de Piura; etiquetas hasta la SE 41 de 2026 (17/10/2026); comparador sin clima `historia_geo` | Congelada para el paper el 12/11/2026. Se sirve solo en la demo V4 (BD aislada). Sus artefactos son locales (`models/experimentos/`), no están en un Release | `model/v4` (`305005c`) |
| v3 | L + 5a + d3, trial 191 del estudio 06 | Es la que construye la publicación del backend (`serving.paquete.tipo: v3_l5a_d3`), como selección experimental | `model/v3` |
| v0–v2 | Versiones anteriores | Reemplazadas; registradas y reentrenables con `python -m denguekay.model.reproduce` | `model/v0`–`model/v2` |

- Ninguna versión se sirve como validada (`servir_no_validadas: true`). La HU0007-4 no se evaluó para la v3.
- La v4 no está en `denguekay.model.reproduce`; se reproduce con
  [congelamiento_b3_v4.md](research/08_v3_confirmed_cases/congelamiento_b3_v4.md).
- El scraper de la Sala Situacional toma solo casos confirmados.

## Producto

- **API:** FastAPI, contrato `1.1.0` (`api/v1.1.0`). Esquema hasta la migración `0007_v3`.
- **Frontend:** `apps/web/` con las fases 1–7 cerradas (tablero, mapa y detalle, avisos, desempeño y ayuda,
  validación con auditorías de accesibilidad). Demos locales con v2, v3 y v4 (`npm run dev:demo` abre la v4).
- **Despliegue:** el repo está preparado para Render, Supabase y Vercel; no hay nada desplegado.

## Investigación

Estudios 01–08 en `research/` ([índice](research/README.md)). El 08 reúne la evaluación con casos confirmados,
la congelación de la v4 y la transferencia a Lambayeque y Tumbes.

## Pendiente

- Evaluación prospectiva 2026–27 de la v3 y de b3 con datos publicados después del 09/11/2026.
- Actualización semanal automática (Sala Situacional, ERA5-Land y la serie desde 2000 que usa la v3).
- Publicar los datos y los artefactos de la v4 en el Release de `model/v4`.
- Despliegue.
