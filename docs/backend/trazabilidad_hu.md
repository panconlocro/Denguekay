# Trazabilidad de historias de usuario (US v1.4)

*Actualizada: 17/11/2026, sobre `develop` con la V4 como configuración vigente.*

## Fuente y límites de esta tabla

- La fuente es el documento de criterios de aceptación (`US_Criterios_De_Aceptacion`, versión 1.4). **Ese archivo no
  está en el repo** (la versión 1 se leyó de Drive, carpeta Docs_TB1, SHA-256 de esa copia
  `59a3fecb7559dd07912ca7529c90a16ba81c342fa4db276f9c1dfadd486bf139`). Esta tabla se rehízo con los criterios de la
  v1.4 que se citaron en `PLAN_PENDIENTES_OE3.md` (HU0002-4, HU0003-4, HU0005-4 y -5, HU0007-4, HU0009-2, HU0014-1,
  HU0016-3, HU0017-3, HU0019 y HU0020) y con los títulos de la v1 para el resto. **Los criterios de las HU0001 a HU0006 y
  los títulos de la HU0017 que no están en esos textos figuran como «texto por verificar contra la US v1.4»**: no se
  inventó su redacción.
- **Cumplido** indica comportamiento comprobado por una prueba o por una ejecución citada; **parcial**, una parte
  hecha y lo que falta; **se cumple en el OE4**, lo que el alcance del OE3 deja fuera (la ejecución mensual de la
  HU0009-2, la HU0019 completa y la medición desplegada del SLA); **por verificar**, lo que no se pudo contrastar con
  el texto de la US.
- «Retrospectivo» significa evaluado con predicciones archivadas de temporadas ya cerradas; los umbrales de la
  HU0007-4 se revisaron el 17/11/2026, después de ver los resultados, y la evaluación independiente es la prospectiva
  2026-27 ([ficha de la V4](../../models/registry/v4/ficha.md)).
- Prefijo de rutas de la API: `/api/v1`. Los tests están en `tests/` y `apps/web/`.

## HU0001 a HU0006: datos, calidad y variables

| HU | Criterio | Módulo / documento | Evidencia | Estado |
|---|---|---|---|---|
| HU0001 | Texto por verificar contra la US v1.4 | Pipeline por versión (`pipelines/notebooks/V0` a `V4`), `docs/pipeline.md`, `docs/reproducibilidad.md` | `tests/pipelines/test_run_all.py`, `tests/data/test_v4_reproducibility.py` | **por verificar** |
| HU0002 | HU0002-4 — Fuentes climáticas: producto, rezago de publicación y disponibilidad al origen | `docs/pipeline.md` («Fuentes climáticas de la V4»); `features/b3.py`, `data/processing/enso_index.py`, `chirps_precipitation.py` | `tests/serving/test_v4_live.py::TestB3Availability`, `tests/data/test_enso.py`, `tests/data/test_chirps_prelim.py` | **cumplido** con reservas documentadas: las fechas de disponibilidad son reglas conservadoras (no se registró la fecha real de publicación de cada dato pasado) y no se verificó cuánto cambian los valores recientes al revisarse |
| HU0002 | HU0002-1 a HU0002-3 | Texto por verificar | — | **por verificar** |
| HU0003 | HU0003-4 — Variables sociodemográficas: año de referencia y regla temporal | `docs/pipeline.md` («Sociodemografía»); `data/processing/socio_interpolation.py` | `tests/pipelines/test_weekly_update.py` (extrapolación desde 2026) y `tests/features/test_sociodemographics.py` | **cumplido** con una reserva: la interpolación 2018-2024 usa el extremo de 2025; la V4 no usa variables sociodemográficas |
| HU0003 | HU0003-1 a HU0003-3 | Texto por verificar | — | **por verificar** |
| HU0004 | Texto por verificar | Gold y matriz B3 (`features/gold_v4.py`, `features/gold.py`) | `tests/features/`, `tests/fixtures/v4_gold/` | **por verificar** |
| HU0005 | HU0005-4 — Resumen de cobertura, faltantes, duplicados, descartados y transformaciones | `data/validation/quality_report.py` | `tests/data/test_quality_report.py`; reporte `docs/backend/evidencia/calidad_datos_v4.md` y `.json` | **cumplido**: el reporte se genera en solo lectura sobre el integrado de confirmados |
| HU0005 | HU0005-5 — Completitud ≥ 95 % y descartes ≤ 5 % | Idem | Idem. Corrida del 17/11/2026: completitud 100 % (30 485 de 30 485 filas esperadas, 65 distritos × 469 semanas); 3 de 171 569 registros originales descartados (0,002 %: las 3 notificaciones de la semana 53 de 2025, fuera del calendario del modelo) | **cumplido**, con la reserva de que `casos` es 100 % por construcción: las semanas sin notificación reciben cero en la unión (el reporte mide aparte que solo el 31,37 % tiene un conteo en la fuente) |
| HU0005 | HU0005-1 a HU0005-3 | Great Expectations: `data/validation/integrated_expectations.py`, `gold_expectations.py` | `tests/data/test_gx_quality.py` | **por verificar** |
| HU0006 | HU0006-3 — Diccionario de variables de la configuración final | `model/variable_dictionary.py` | `docs/modeling/diccionario_variables.md` (generado) | **parcial**: el diccionario generado describe la configuración de la v2 (C3 + A3 + B3), no la V4; las 16 columnas de la V4 están en el `paquete.json` congelado y en su ficha |
| HU0006 | HU0006-1, HU0006-2 | Texto por verificar | — | **por verificar** |

## HU0007 a HU0009: modelo, desempeño y monitoreo

| HU | Criterio | Módulo / endpoint | Evidencia | Estado |
|---|---|---|---|---|
| HU0007 | HU0007-1 — Modelo base de referencia | `serving/` + protocolo + MLflow; la persistencia sale en las métricas por bloque (`casos_persistencia`) | `tests/serving/test_publish.py` | **cumplido** |
| HU0007 | HU0007-2 — Validación cruzada temporal | `model/train.py`, `data/validation/forecast_contract.py` | `tests/serving/test_future_rows.py`, `tests/data/test_forecast_contract.py` | **cumplido** |
| HU0007 | HU0007-3 — Optimización de hiperparámetros | `evaluation/tuning.py` (preregistro, espacio, objetivo y estudio TPE) | `tests/evaluation/test_tuning.py`. La V4 usa los hiperparámetros de su congelamiento | **cumplido** en la investigación; no se reoptimiza en el producto |
| HU0007 | HU0007-4 — Umbrales de aceptación: Recall ≥ 0,65, Precision ≥ 0,60, F1 ≥ 0,70 (p ≥ 0,50), MAE y RMSE ≤ 90 % de la persistencia, bloque agregado `temporadas_2022_2026` | Migración `0009_v4`, `evaluation/acceptance.py`, `serving/demo_b3_v4.py` (`block_metrics`) | `tests/serving/test_v4_acceptance.py`, `tests/db/test_oe2_schema.py`. V4, semilla 17: h2 0,769 / 0,824 / 0,795; h3 0,723 / 0,827 / 0,772; h4 0,666 / 0,820 / 0,735 (Recall / Precision / F1) | **cumplido, retrospectivo**: las seis versiones de la V4 quedan `validado`; el agregado descansa en 2022-2024 (2025 y 2026 no cumplen por separado), con una semilla y umbrales revisados después de ver los resultados. La v0 a la v3 no traen el bloque: `experimental` |
| HU0007 | HU0007-5 — Horizonte no validado | `GET /predicciones` y `GET /configuracion` (`experimental`); inferencia sin versión utilizable → `no_disponible` | `tests/api/test_api.py`, `tests/serving/test_inference.py`, `tests/api/test_contract_v1.py` | **cumplido** (el mecanismo; con la V4 los tres horizontes salen sin la marca) |
| HU0008 | HU0008-1 — Métricas del clasificador | `GET /modelos/{id}` | `tests/api/test_api.py` | **cumplido** |
| HU0008 | HU0008-2 — Métricas del regresor | `GET /modelos/{id}` | `tests/api/test_api.py` | **cumplido** |
| HU0008 | HU0008-3 — Validación temporal | `GET /modelos/{id}` (`reproducibilidad.particion_temporal`) | `tests/serving/test_publish.py` | **cumplido** |
| HU0008 | HU0008-4 — Variables relevantes y limitaciones | `GET /modelos/{id}/variables` | `tests/api/test_api.py` | **cumplido** |
| HU0009 | HU0009-1 — Registro de versión del modelo | `serving/publish.py`, `version_modelo`, Storage, MLflow; fichas en `models/registry/` | `tests/serving/test_publish.py`, `tests/model/test_registry.py` | **cumplido** |
| HU0009 | HU0009-2 — Monitoreo de deriva | `serving/drift.py`; informe de `v4_weekly` (`monitoreo_deriva`); `python -m denguekay.serving.drift` | `tests/serving/test_drift.py`, `tests/pipelines/test_v4_weekly.py` | **cumplido en el código** (Precision, Recall, F1, MAE y RMSE de las semanas cerradas frente a la referencia de la HU0007-4; marca > 10 % desde 8 semanas; solo registra, nunca reentrena). **La ejecución mensual se cumple en el OE4** |
| HU0009 | HU0009-3 — Reentrenamiento controlado | `docs/modeling/reentrenamiento.md`; `serving/emissions.py` (`retraining_due`); `serving/publish.py` | `tests/serving/test_emissions.py` | **parcial**: el reentrenamiento es anual, a mano, y la actualización semanal avisa pero nunca entrena; el primero corresponde al cierre de la temporada 2027 |
| HU0009 | HU0009-4 — Retorno a una versión validada | `POST /admin/modelos/{version}/activar` | `tests/api/test_api.py::test_activacion`, `tests/serving/test_v4_acceptance.py` (activación de una versión V4 validada) | **cumplido**: archiva la activa anterior, audita en `ejecucion` y exige `cumple_umbrales` |

## HU0010 a HU0015: pronóstico, tablero, series, mapa y alertas

La V4 se sirve con el predictor `v4_b3_live` (boosters congelados; el vector se calcula con los datos de la BD al corte). Las
vistas son `apps/web/` (pruebas de Vitest y de Playwright en `apps/web/e2e/`).

| HU | Criterio | Endpoint / módulo | Evidencia | Estado |
|---|---|---|---|---|
| HU0010 | HU0010-1 — Consulta de probabilidad de brote | `GET /predicciones`; `serving/risk.py` | `tests/api/test_api.py`, `tests/serving/test_policies.py` | **cumplido** (retrospectivo, ver HU0007-4) |
| HU0010 | HU0010-2 — Horizonte mínimo de alerta | `GET /predicciones?horizonte=2` | `tests/serving/test_v4_live.py`, `tests/serving/test_demo_b3_v4.py` | **cumplido**: h = 2 cumple la HU0007-4 |
| HU0010 | HU0010-3 — Horizontes de tres y cuatro semanas (meta) | `GET /predicciones?horizonte=3` y `4` | `tests/serving/test_v4_acceptance.py` | **cumplido**: h = 3 y h = 4 cumplen la HU0007-4 (el margen del h = 4 es corto: Recall 0,666 frente a 0,65) |
| HU0010 | HU0010-4 — Predicción no disponible | `GET /predicciones`, `/mapa-riesgo` | `tests/serving/test_inference.py` | **cumplido**: `no_disponible` con motivo; nunca un riesgo sin vector |
| HU0011 | HU0011-1 — Consulta de magnitud estimada | `GET /predicciones` (`casos_estimados`, intervalo si existe) | `tests/api/test_api.py` | **cumplido** |
| HU0011 | HU0011-2 — Coherencia con la selección | `GET /predicciones?ubigeo=`, `/series` | `apps/web/e2e/map-detail.spec.ts` | **cumplido** |
| HU0011 | HU0011-3 — Estimación no disponible | `GET /predicciones` | `tests/serving/test_inference.py` | **cumplido**: nunca un cero ficticio |
| HU0012 | HU0012-1 — Vista consolidada | `GET /tablero/resumen`; `DashboardPage` | `tests/api/test_api.py`, `apps/web/e2e/dashboard.spec.ts` | **cumplido** |
| HU0012 | HU0012-2 — Filtrado del tablero | `GET /tablero/resumen?horizonte=` | `apps/web/e2e/dashboard.spec.ts` | **cumplido** |
| HU0012 | HU0012-3 — Observado frente a pronosticado | `GET /tablero/resumen`, `GET /series` | `tests/api/test_benchmark.py` | **cumplido** |
| HU0012 | HU0012-4 — Ausencia parcial de datos | `GET /tablero/resumen` | `tests/api/test_api.py` | **cumplido**: la suma regional es `null` si falta un distrito |
| HU0013 | HU0013-1 — Serie histórica y pronosticada | `GET /series/{ubigeo}` | `tests/api/test_api.py`, `apps/web/e2e/map-detail.spec.ts` | **cumplido** |
| HU0013 | HU0013-2 — Cambio de distrito o periodo | `GET /series/{ubigeo}?desde=&hasta=` | `apps/web/e2e/map-detail.spec.ts` | **cumplido** |
| HU0013 | HU0013-3 — Semanas sin información | `GET /series/{ubigeo}` | `tests/api/test_api.py` | **cumplido**: `null` explícito |
| HU0014 | HU0014-1 — Mapa distrital de riesgo | `GET /mapa-riesgo`; migración `0010_v4` (`distrito.geometria`); `serving/geometries.py` | `tests/serving/test_geometries.py`, `tests/api/test_api.py::test_mapa_riesgo_poligonos_con_respaldo_de_centroide`, `apps/web/e2e/map-detail.spec.ts` (polígonos), `apps/web/src/lib/district.test.ts` | **cumplido**: 65 polígonos (COD-AB de Perú, IGN, OCHA/HDX, CC BY-IGO 3.0, con atribución en el mapa), centroide de respaldo. **Riesgo:** su publicación en un servicio desplegado se decide antes del despliegue |
| HU0014 | HU0014-2 — Selección de horizonte | `GET /mapa-riesgo?horizonte=` | `apps/web/e2e/map-detail.spec.ts` | **cumplido** |
| HU0014 | HU0014-3 — Detalle del distrito | `GET /distritos/{ubigeo}`, `/predicciones?ubigeo=` | `apps/web/e2e/map-detail.spec.ts` | **cumplido** |
| HU0014 | HU0014-4 — Distrito sin predicción | `GET /mapa-riesgo` | `tests/api/test_api.py`, `apps/web/e2e/map-detail.spec.ts` | **cumplido**: «Sin datos» con motivo |
| HU0015 | HU0015-1 — Generación de alerta | `serving/inference.py` (`update_alerts`), `GET /alertas` | `tests/serving/test_inference.py` | **cumplido** |
| HU0015 | HU0015-2 — Priorización de alertas | `GET /alertas?horizonte=&ubigeo=&nivel=` | `tests/api/test_api.py`, `apps/web/e2e/alerts.spec.ts` | **cumplido** |
| HU0015 | HU0015-3 — Consulta del detalle | `GET /alertas/{id}` | `tests/api/test_api.py` | **cumplido** |
| HU0015 | HU0015-4 — Actualización del estado de alerta | `serving/inference.py`, `v4_weekly` | `tests/serving/test_inference.py`, `tests/pipelines/test_v4_weekly.py` | **cumplido**: la actualización semanal recalcula alertas y retira las que dejan de aplicar |

## HU0016 a HU0020: API, ayuda, operación y actualización

| HU | Criterio | Módulo / documento | Evidencia | Estado |
|---|---|---|---|---|
| HU0016 | HU0016-1 — Contrato de la API | Todos los routers; OpenAPI v1.1.0 (`openapi_v1.json`, congelado) | `tests/api/test_contract_v1.py`, `tests/test_contract_v1_guards.py` | **cumplido**. El OpenAPI no cambió con los polígonos ni con los umbrales |
| HU0016 | HU0016-2 — Integración con los servicios de datos | `GET /observaciones`, `/predicciones`, `/series` | `tests/api/test_api.py`, `apps/web/e2e/` | **cumplido** |
| HU0016 | HU0016-3 — Tiempos de respuesta (SLA) | `apps/api/tools/benchmark.py`, evidencia local de la fase 6 | Ver el documento de evidencia del SLA local (se enlaza al cerrar la fase 6) | **parcial**: medición local; la medición desplegada **se cumple en el OE4** |
| HU0016 | HU0016-4 — Manejo de carga y fallos | `apps/api/errors.py`, `dependencies.py`, caché | `tests/api/test_api.py`, `apps/web/e2e/map-detail.spec.ts` | **cumplido**: errores uniformes, BD caída (503) y estados de error y reintento en las vistas |
| HU0017 | HU0017-3 — Soporte y capacitación | `apps/web/src/content/help.json`, `apps/web/public/manual-usuario.pdf` | `apps/web/e2e/models-help.spec.ts` | **parcial**: el soporte está a cargo de Nicolás Miranda y Rosa Rodríguez y la capacitación se coordina en el OE4; **el canal de contacto figura como «[canal de soporte por confirmar]»** (pendiente de Rosa) |
| HU0017 | Resto de los criterios (ayuda, búsqueda, manual descargable) | `HelpPage`, `manual-usuario.pdf` | `apps/web/e2e/models-help.spec.ts` | **por verificar** contra el texto de la US v1.4 |
| HU0018 | HU0018-1 — Documentación de arquitectura | `docs/architecture.md`, `docs/backend/arquitectura.md` | Revisión de diagramas contra módulos | **cumplido** |
| HU0018 | HU0018-2 — Reproducción del pipeline y los modelos | `docs/reproducibilidad.md`, `docs/modeling/reproducir_v4.md`, `docs/backend/operacion.md` | `tests/data/test_v4_reproducibility.py` | **cumplido** (con los datos del Release de `model/v4`) |
| HU0018 | HU0018-3 — Despliegue y configuración | `docs/backend/despliegue.md`, `render.yaml`, `.env.example` | Job `humo-api` del CI, `tests/serving/test_settings.py` | **parcial**: el repo está preparado para Render, Supabase y Vercel; el despliegue lo hace Rosa y queda para el final |
| HU0018 | HU0018-4 — Mantenimiento y recuperación | `docs/backend/operacion.md` (respaldo, reversión) | `tests/api/test_api.py::test_activacion` | **cumplido** |
| HU0019 | Texto por verificar contra la US v1.4 | — | — | **se cumple en el OE4** |
| HU0020 | Actualización semanal | `pipelines/v4_weekly.py`, `serving/emissions.py`, `scripts/weekly_v4.ps1`, `docs/backend/operacion.md` | `tests/pipelines/test_v4_weekly.py`, `tests/serving/test_emissions.py` | **cumplido**: trae las fuentes que cambian, carga la BD, emite h2 a h4 con el paquete congelado y archiva cada emisión; no entrena. Registrar la tarea programada es decisión de quien opera |

## Pendientes que esta tabla deja visibles

1. Contrastar con el texto de la US v1.4 las filas **por verificar** (HU0001 a HU0006 salvo lo citado, HU0017 y HU0019).
2. Confirmar el canal de soporte (HU0017-3).
3. Decidir antes del despliegue si se publican los polígonos distritales (CC BY-IGO 3.0, con atribución).
4. Grabar las líneas base de las guardas del contrato para las migraciones `0009_v4` y `0010_v4` (comando en el PR).
5. Se cumplen en el OE4: la ejecución mensual del monitoreo de deriva (HU0009-2), la HU0019 y la medición desplegada
   del SLA (HU0016-3).
