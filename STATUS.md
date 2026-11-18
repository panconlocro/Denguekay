# Estado del proyecto

*Actualizado: 17/11/2026. Se actualiza en cada release `develop → main`.*

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

- **Aceptación (HU0007-4, US v1.4).** Con los umbrales de la migración `0009_v4` (Recall ≥ 0,65, Precision ≥ 0,60, F1 ≥ 0,70, MAE y
  RMSE ≤ 90 % de la persistencia, bloque agregado `temporadas_2022_2026`) las seis versiones de la V4 (clasificación y regresión en h2, h3 y h4) quedan `validado`, es decir, cumplen los
  umbrales de forma retrospectiva y con una sola semilla
  (h2: 0,769 / 0,824 / 0,795; h3: 0,723 / 0,827 / 0,772; h4: 0,666 / 0,820 / 0,735 en Recall / Precision / F1). Los umbrales
  se revisaron el 17/11/2026, **después de ver los resultados**, así que la evaluación independiente es la prospectiva
  2026-27. El agregado descansa en 2022–2024; 2025 y 2026 no cumplen por separado (ficha de la V4). La v3 y las anteriores no traen el bloque y quedan `experimental`; `servir_no_validadas: true` se mantiene.
- La v4 no está en `denguekay.model.reproduce`; se reproduce con [reproducir_v4.md](docs/modeling/reproducir_v4.md)
  (`run_all --version v4 --verificar`) y [congelamiento_b3_v4.md](research/08_v3_confirmed_cases/congelamiento_b3_v4.md).
- El scraper de la Sala Situacional toma casos confirmados (V4, por defecto) o notificados (v0 a v3).

## Producto

- **API:** FastAPI, contrato `1.1.0` (`api/v1.1.0`). Esquema hasta la migración `0010_v4` (`0009` fija los umbrales de la US v1.4; `0010` guarda la geometría de cada distrito).
- **Frontend:** `apps/web/` con las fases 1–7 cerradas (tablero, mapa y detalle, avisos, desempeño y ayuda,
  validación con auditorías de accesibilidad). Demos locales con v2, v3 y v4 (`npm run dev:demo` abre la v4). El mapa
  muestra los límites distritales (COD-AB de Perú, IGN, OCHA/HDX, CC BY-IGO 3.0) con el centroide como respaldo.
- **Calidad de datos:** `python -m denguekay.data.validation.quality_report` (solo lectura) genera
  `docs/backend/evidencia/calidad_datos_v4.md`: completitud 100 % y 3 de 171 569 registros descartados (HU0005-4 y -5).
- **Deriva:** `python -m denguekay.serving.drift` y el informe semanal registran la degradación frente a la referencia de la
  HU0007-4; no reentrenan (HU0009-2). La ejecución mensual es del OE4.
- **Trazabilidad:** [trazabilidad_hu.md](docs/backend/trazabilidad_hu.md) (HU0001 a HU0020, US v1.4).
- **Despliegue:** el repo está preparado para Render, Supabase y Vercel; no hay nada desplegado.

## Investigación

Estudios 01–08 en `research/` ([índice](research/README.md)). El 08 reúne la evaluación con casos confirmados,
la congelación de la v4 y la transferencia a Lambayeque y Tumbes.

## Pendiente

- Evaluación prospectiva 2026–27 de la v3 y de b3 con datos publicados después del 09/11/2026. La V4 archiva cada
  emisión semanal (fecha, insumos, pronósticos y vectores) en `models/serving/actualizacion_semanal/emisiones/`
  ([operación](docs/backend/operacion.md#actualización-semanal-v4)).
- Reentrenamiento anual de la V4 al cierre de la temporada 2027: el comando `denguekay.model.refit_v4` ya existe y está
  verificado contra la V4; se corre a mano ([política y procedimiento](docs/modeling/reentrenamiento.md)).
- Registrar la tarea programada de la actualización semanal (`scripts\register_weekly_v4_task.ps1`) en la BD que se use.
- Canal de soporte de la ayuda (figura como «[canal de soporte por confirmar]») y decisión sobre publicar los polígonos
  distritales (CC BY-IGO 3.0) antes del despliegue.
- Grabar las líneas base de las guardas del contrato para las migraciones `0009_v4` y `0010_v4`
  (`python tests/contract_v1_support.py record`).
- Se cumplen en el OE4: la ejecución mensual de la deriva, la HU0019 y la medición desplegada del SLA.
- Despliegue.
