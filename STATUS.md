# Estado del proyecto

*Actualizado: 16/11/2026. Se actualiza en cada release `develop → main`.*

## Etapa

OE3 (desarrollo completo). El EDA y OE2 (diseño) están cerrados.

## Modelo

| Versión | Qué es | Estado | Tag |
|---|---|---|---|
| v4 | `b3_obs` con casos confirmados de Piura; etiquetas hasta la SE 41 de 2026 (17/10/2026); comparador sin clima `historia_geo` | Congelada para el paper el 12/11/2026. Es la configuración de `serving.paquete` (`tipo: v4_b3_live`: usa los boosters congelados y calcula el vector con los datos de la BD al corte; no reentrena) y de la demo V4. Datos y artefactos en el Release de `model/v4` (manifiesto en `models/registry/v4/`) | `model/v4` (`305005c`) |
| v3 | L + 5a + d3, trial 191 del estudio 06 | Reemplazada como configuración del backend por la v4; sigue registrada como predictor `v3_l5a_d3` | `model/v3` |
| v0–v2 | Versiones anteriores | Reemplazadas; registradas y reentrenables con `python -m denguekay.model.reproduce` | `model/v0`–`model/v2` |

Cada versión tiene su pipeline de datos en `pipelines/notebooks/V0` … `V4` (`python -m denguekay.pipelines.run_all --version vN`). V4
escribe en `data/`; v0 a v3, en `data_anteriores/vN/`. La copia exacta de cada una es su Release; qué difiere al
regenerar desde las fuentes está en [docs/reproducibilidad.md](docs/reproducibilidad.md).

- Ninguna versión se sirve como validada (`servir_no_validadas: true`). La HU0007-4 no se evaluó para la v3.
- La v4 no está en `denguekay.model.reproduce`; se reproduce con [reproducir_v4.md](docs/modeling/reproducir_v4.md)
  (`run_all --version v4 --verificar`) y [congelamiento_b3_v4.md](research/08_v3_confirmed_cases/congelamiento_b3_v4.md).
- El scraper de la Sala Situacional toma casos confirmados (V4, por defecto) o notificados (v0 a v3).

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
- Despliegue.
