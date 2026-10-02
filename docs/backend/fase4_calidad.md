# Fase 4: calidad, rendimiento y documentación

Se incorporaron benchmark real, CI, documentación de arquitectura/decisiones y trazabilidad contra el Excel original. El tablero ahora incluye un resumen observado con semana, fecha de carga y cobertura propios, además de los indicadores pronosticados. El benchmark puede omitir la caché de lecturas mediante cabecera; conserva las comprobaciones de BD. No se modificaron etiquetas, variantes, umbrales ni resultados de Rosa.

## Archivos

- Nuevos: `src/api/benchmark.py`, `tests/test_api_benchmark.py`, `tests/test_serving_operacion.py`, `.coveragerc`, `.github/workflows/backend.yml`.
- Nuevos documentos: `arquitectura.md`, `decisiones_tecnicas.md`, `trazabilidad_hu.md`, este cierre y [fase4_verificacion.json](fase4_verificacion.json).
- Evidencia: [benchmark_sqlite.json](benchmark_sqlite.json) y [benchmark_postgresql.json](benchmark_postgresql.json), con muestras de duración individuales.
- Actualizados: `src/api/consultas.py`, `esquemas.py`, `dependencias.py`, `main.py`, `src/utils/paths.py`, `docs/estructuraRepo.md`, `README.md`, `operacion.md`, `contrato_api.md` y `openapi.json`.

## Comandos ejecutados y resultados

| Comando / comprobación | Resultado real |
|---|---|
| `python -m src.validation.calidad_gx` | Silver 107/107; gold h=2 y h=4 92/92 cada uno; 30485 filas por panel |
| `python -m pip check` | No broken requirements found |
| `python -m coverage run -m unittest discover -s tests` | 251 tests, OK, 51.099 s |
| `python -m coverage report --fail-under=80` | 90.16 % conjunta |
| `python -m coverage report --include="src/<paquete>/*" --fail-under=80` | API, serving y db superan el mínimo por separado |
| `python -m coverage xml` | Reporte XML local, ignorado por Git |
| `python -m src.api.exportar_openapi` con BD fase4 | 16 rutas y 16 operaciones; ejemplos obtenidos de esa BD |
| `python -m src.api.benchmark` con BD real, 2 repeticiones, sin escrituras | TestClient declarado; 42 casos y 4 POST no medidos; no modifica la BD |
| `python -m src.api.benchmark --url http://127.0.0.1:8765 --repeticiones 20 --incluir-escrituras --salida docs/backend/benchmark_sqlite.json` | HTTP/Uvicorn real sobre copia SQLite |
| Mismo benchmark en puerto 8766, salida `benchmark_postgresql.json` | HTTP/Uvicorn real sobre copia PostgreSQL |
| SHA256 de entradas protegidas | 503 archivos contrastados, ninguno modificado |

En macOS se usó `.venv/bin/python`; las credenciales de prueba solo existieron en el entorno de los procesos. No se creó un `.env`. Los dos servidores Uvicorn y PostgreSQL local se detuvieron después de medir. Las copias de BD permanecen locales; los datasets y modelos completos no se reentrenaron en esta fase. Los tests sí entrenan boosters sobre muestras reales y un run de prueba en MLflow temporal.

## Cobertura por paquete

| Paquete | Sentencias | Sin cubrir | Cobertura |
|---|---:|---:|---:|
| `src/api` | 849 | 40 | 95.29 % |
| `src/serving` | 717 | 138 | 80.75 % |
| `src/db` | 335 | 9 | 97.31 % |

Se incluyen CLI y migraciones: no se ocultaron módulos poco cubiertos. La suite prueba contrato, faltantes/ceros, errores, fronteras de riesgo, activación/rollback, corte sin fuga, reevaluación desde BD, historial, idempotencia, caché, fallos de CLI y actualizaciones de catálogo. Las ramas del pipeline completo y regeneración OOS no se ejercitan enteramente por unittest; las ejecuciones completas locales de fases anteriores están documentadas por separado.

## Benchmark HTTP contra BD real

Cada combinación usa 20 solicitudes medidas, con 2 calentamientos en GET y ninguno en POST. Los GET se miden con caché habilitada y con bypass de caché de lecturas; el booster puede permanecer residente. Se mide desde la llamada hasta recibir el cuerpo completo, no solo la cabecera de tiempo. La serie se consulta sin limitar el intervalo, y los IDs/distrito provienen de la BD. Los POST usan los boosters guardados; activación mide la versión ya seleccionada, sin fabricar cambios de modelo.

| BD local | Combinaciones | Solicitudes medidas | Errores | Mayor p95 | Mayor tiempo individual |
|---|---:|---:|---:|---:|---:|
| sqlite | 46 | 920 | 0 | 393.41 ms | 395.77 ms |
| postgresql | 46 | 920 | 0 | 360.65 ms | 430.62 ms |

Las 16 operaciones están representadas en los 46 casos, considerando horizontes y modos. Todas las solicitudes medidas respondieron 200; tanto p95 como los máximos observados quedaron por debajo de 5 s. Esto satisface el objetivo de la **medición local**. No acredita HU0016-3 completo: falta medir Render/Supabase, carga de páginas <10 s y disponibilidad ≥95 % durante un periodo explícito. No se midieron usuarios concurrentes ni arranque del proceso; tampoco se controló la carga de otros procesos de la laptop.

### p50/p95 de cada combinación

| Método y ruta real | Modo | SQLite p50 / p95 (ms) | PostgreSQL p50 / p95 (ms) |
|---|---|---:|---:|
| GET `/salud` | sin_cache_lecturas | 7.65 / 8.20 | 9.40 / 9.95 |
| GET `/salud` | cache_habilitada | 7.75 / 10.86 | 9.38 / 13.02 |
| GET `/distritos` | sin_cache_lecturas | 1.76 / 1.98 | 2.58 / 2.91 |
| GET `/distritos` | cache_habilitada | 1.37 / 1.51 | 1.75 / 1.93 |
| GET `/distritos/200101` | sin_cache_lecturas | 1.41 / 2.03 | 2.05 / 2.23 |
| GET `/distritos/200101` | cache_habilitada | 0.86 / 1.02 | 1.22 / 1.39 |
| GET `/distritos/geojson` | sin_cache_lecturas | 1.50 / 1.81 | 2.17 / 2.43 |
| GET `/distritos/geojson` | cache_habilitada | 1.22 / 1.37 | 1.55 / 1.72 |
| GET `/observaciones` | sin_cache_lecturas | 4.25 / 4.54 | 4.69 / 4.98 |
| GET `/observaciones` | cache_habilitada | 1.57 / 1.84 | 1.91 / 2.50 |
| GET `/modelos` | sin_cache_lecturas | 9.97 / 13.11 | 11.73 / 12.00 |
| GET `/modelos` | cache_habilitada | 1.47 / 1.64 | 1.85 / 2.04 |
| GET `/predicciones?horizonte=2` | sin_cache_lecturas | 332.20 / 348.50 | 293.11 / 297.25 |
| GET `/predicciones?horizonte=2` | cache_habilitada | 2.66 / 2.94 | 2.80 / 3.22 |
| GET `/mapa?horizonte=2` | sin_cache_lecturas | 333.11 / 378.44 | 300.72 / 308.65 |
| GET `/mapa?horizonte=2` | cache_habilitada | 3.66 / 4.09 | 3.65 / 4.18 |
| GET `/series/200101?horizonte=2` | sin_cache_lecturas | 53.51 / 112.06 | 52.50 / 111.08 |
| GET `/series/200101?horizonte=2` | cache_habilitada | 21.79 / 26.93 | 20.68 / 24.20 |
| GET `/tablero?horizonte=2` | sin_cache_lecturas | 338.57 / 393.41 | 307.76 / 315.12 |
| GET `/tablero?horizonte=2` | cache_habilitada | 0.98 / 1.11 | 1.34 / 1.41 |
| GET `/alertas?horizonte=2` | sin_cache_lecturas | 15.44 / 18.79 | 19.85 / 20.32 |
| GET `/alertas?horizonte=2` | cache_habilitada | 3.18 / 3.49 | 3.29 / 6.83 |
| POST `/predicciones/recalcular?horizonte=2` | escritura | 25.89 / 46.30 | 28.28 / 30.91 |
| GET `/predicciones?horizonte=4` | sin_cache_lecturas | 331.22 / 365.32 | 319.94 / 360.62 |
| GET `/predicciones?horizonte=4` | cache_habilitada | 2.72 / 3.10 | 3.16 / 3.34 |
| GET `/mapa?horizonte=4` | sin_cache_lecturas | 327.58 / 334.91 | 334.27 / 341.06 |
| GET `/mapa?horizonte=4` | cache_habilitada | 3.61 / 3.92 | 3.96 / 4.51 |
| GET `/series/200101?horizonte=4` | sin_cache_lecturas | 54.36 / 114.36 | 74.22 / 139.19 |
| GET `/series/200101?horizonte=4` | cache_habilitada | 21.70 / 32.89 | 21.76 / 26.12 |
| GET `/tablero?horizonte=4` | sin_cache_lecturas | 349.58 / 357.78 | 331.85 / 360.65 |
| GET `/tablero?horizonte=4` | cache_habilitada | 1.03 / 1.31 | 1.40 / 1.56 |
| GET `/alertas?horizonte=4` | sin_cache_lecturas | 16.48 / 17.87 | 20.60 / 24.21 |
| GET `/alertas?horizonte=4` | cache_habilitada | 3.16 / 3.63 | 3.33 / 3.58 |
| POST `/predicciones/recalcular?horizonte=4` | escritura | 25.53 / 26.85 | 50.48 / 63.72 |
| GET `/alertas/343 (PG: /alertas/3960)` | sin_cache_lecturas | 2.17 / 3.11 | 3.75 / 4.53 |
| GET `/alertas/343 (PG: /alertas/3960)` | cache_habilitada | 0.98 / 1.05 | 1.40 / 1.55 |
| GET `/modelos/1` | sin_cache_lecturas | 5.79 / 6.09 | 7.48 / 7.96 |
| GET `/modelos/1` | cache_habilitada | 1.12 / 1.27 | 1.58 / 1.67 |
| GET `/modelos/1/variables` | sin_cache_lecturas | 3.07 / 3.46 | 5.01 / 5.38 |
| GET `/modelos/1/variables` | cache_habilitada | 0.96 / 1.07 | 1.40 / 1.50 |
| POST `/modelos/1/activar` | escritura | 27.12 / 31.70 | 59.63 / 66.99 |
| GET `/modelos/4` | sin_cache_lecturas | 6.08 / 6.53 | 7.28 / 8.26 |
| GET `/modelos/4` | cache_habilitada | 1.18 / 1.24 | 1.71 / 2.03 |
| GET `/modelos/4/variables` | sin_cache_lecturas | 3.19 / 3.58 | 4.96 / 5.38 |
| GET `/modelos/4/variables` | cache_habilitada | 0.94 / 1.07 | 1.44 / 1.61 |
| POST `/modelos/4/activar` | escritura | 27.86 / 33.76 | 83.39 / 88.77 |

## Conservación de historia y fuentes

Cada copia empezó desde la BD de fase 3: 65 distritos, 30485 observaciones, 30 versiones, 27300 predicciones y 3 ejecuciones. El benchmark agregó 80 ejecuciones por copia y 5200 predicciones, dejando 32500 predicciones y 83 ejecuciones. Las versiones permanecen en 30; no se reentrenó ni se borró historia. La BD SQLite original `fase3.sqlite` conserva sus conteos iniciales. Las copias medidas son `models/serving/fase4.sqlite` y `denguekay_fase4_pruebas` en PostgreSQL local, no Supabase.

El corte es 27/12/2025. El último lote contiene 65 distritos por horizonte, objetivos 04/01/2026 (h=2) y 18/01/2026 (h=4). Las cuatro versiones activas XGBoost siguen **experimentales**; las dos persistencias son referencias. Fecha de actualización nueva no significa fuentes nuevas.

## CI y reproducción

Workflow de push/PR con Python 3.12 para Linux, Windows y macOS; usa CPU, instala requisitos, comprueba dependencias, corre unittest completo y exige cobertura conjunta y por paquete ≥80 %. Conserva XML por sistema. Su ejecución remota queda pendiente del push. Se contrastó localmente una copia con solo archivos versionables, sin gold completos, modelos completos, `.env` ni `mlflow.db`; usa los mismos fixtures reales. La copia aprobó 251 tests en 49.166 s y 90.16 % de cobertura conjunta, con los tres umbrales de paquete aprobados. Ver el resultado en el JSON de cierre.

## Pendientes al cerrar

- Fase 5: Render/Supabase y guion de demo, previa aprobación. No se desplegó en esta fase.
- React, polígonos, monitoreo de deriva, h=3 y aceptación operativa siguen pendientes conforme a [trazabilidad_hu.md](trazabilidad_hu.md).
- Riesgo visible ≥0,50 y bandera F1 se conservan según aprobación; uso operativo/calibración debe revisarse con Rosa.
- No afirmar CI Windows/Linux ejecutado ni SLA remoto a partir de la ejecución local.
