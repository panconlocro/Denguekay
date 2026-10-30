# Evidencia: prueba de humo completa (contrato v1)

Generado por `python -m apps.api.tools.smoke_test --completa` el 2026-10-30T04:32:56+00:00.
Servidor: uvicorn en `http://127.0.0.1:8010`; BD: PostgreSQL 18.6 local, BD desechable denguekay_pruebas. Sin credenciales: la clave X-API-Key y las URL de conexión no se
registran.

Entorno: Python 3.12.10, Windows-11-10.0.26300-SP0; fastapi 0.142.2,
SQLAlchemy 2.1.1, psycopg 3.3.6, xgboost 3.4.1.

Pasos previos:

1. PostgreSQL 18.6 local (Windows), BD desechable de pruebas `denguekay_pruebas` llevada a `alembic downgrade base` (vacía)
2. `python -m alembic upgrade head` (1 s)
3. `python -m denguekay.serving.load_data` (26 s)
4. `python -m denguekay.serving.publish --seleccionar-experimental` (paquete v2, h=2, 3 y 4; 47 s)
5. `python -m uvicorn apps.api.main:app` (un worker); `POST /admin/inferencias` calcula la inferencia vigente

Cada ruta del contrato v1; las que dependen del horizonte, con h=2, 3 y 4. «ms (servidor)» es la cabecera
`X-Tiempo-Respuesta-ms`; «ms (cliente)» incluye el transporte local.

| Método | Ruta | HTTP | ms (servidor) | ms (cliente) | Resumen de la respuesta |
|---|---|---|---|---|---|
| GET | `/salud` | 200 | 3.940 | 9.6 | estado=ok; conexion_bd=True; fecha_corte_datos=2025-12-27; ultima_ejecucion={'id_ejecucion': 14, 'tipo': 'inferencia', 'estado': 'exitosa', 'id_semana_corte': 202548, 'fin': '2026-10-29T23:32:44.032386-05:00'} |
| GET | `/configuracion` | 200 | 29.130 | 30.3 | version_contrato=1.1.0; horizontes_disponibles=[2, 3, 4]; horizonte_por_defecto=4; experimental=True |
| GET | `/distritos` | 200 | 12.332 | 13.5 | total=65; disponible=True |
| GET | `/distritos/200101` | 200 | 2.889 | 3.9 | {"ubigeo": "200101", "nombre": "Piura", "ubigeo_provincia": "2001", "provincia": "Piura", "latitud": -5.08299, "longitud": -80.668078, "poblacion_censo_2017": 158495, "activo": true} |
| GET | `/observaciones` | 200 | 28.138 | 29.1 | total=30485; disponible=True |
| POST | `/admin/inferencias` {"horizonte": 2} | 200 | 4123.610 | 4125.0 | id_ejecucion=15; corte=202552; objetivo=202601; predicciones=65; disponibles=65; experimental=True; versiones={'clasificacion': 'v2-clf-h2-1', 'regresion': 'v2-reg-h2-1'} |
| POST | `/admin/inferencias` {"horizonte": 3} | 200 | 2444.435 | 2445.9 | id_ejecucion=16; corte=202552; objetivo=202602; predicciones=65; disponibles=65; experimental=True; versiones={'clasificacion': 'v2-clf-h3-1', 'regresion': 'v2-reg-h3-1'} |
| POST | `/admin/inferencias` {"horizonte": 4} | 200 | 2451.063 | 2452.5 | id_ejecucion=17; corte=202552; objetivo=202603; predicciones=65; disponibles=65; experimental=True; versiones={'clasificacion': 'v2-clf-h4-1', 'regresion': 'v2-reg-h4-1'} |
| GET | `/predicciones?horizonte=2` | 200 | 32.337 | 33.8 | total=65; disponible=True; ejemplo 200101 corte=202552 objetivo=202601 p=0.0 nivel=bajo casos=0.38 experimental=True |
| GET | `/series/200101?horizonte=2` | 200 | 30.605 | 31.9 | distrito=Piura; semanas=26 (2025-07-13 a 2026-01-04); semanas_con_prediccion=25 |
| GET | `/tablero/resumen?horizonte=2` | 200 | 20.901 | 22.1 | distritos=65; con_prediccion=65; niveles={'bajo': 65, 'medio': 0, 'alto': 0, 'muy_alto': 0}; alertas_activas=0; experimental=True; casos_estimados_region=11.16 |
| GET | `/mapa-riesgo?horizonte=2` | 200 | 26.195 | 27.6 | type=FeatureCollection; features=65; disponibles=65; experimental=True; corte=202552 |
| GET | `/alertas?horizonte=2` | 200 | 6.729 | 7.8 | total=0; disponible=True |
| GET | `/predicciones?horizonte=3` | 200 | 24.456 | 25.8 | total=65; disponible=True; ejemplo 200101 corte=202552 objetivo=202602 p=0.0 nivel=bajo casos=0.45 experimental=True |
| GET | `/series/200101?horizonte=3` | 200 | 21.664 | 23.0 | distrito=Piura; semanas=26 (2025-07-20 a 2026-01-11); semanas_con_prediccion=24 |
| GET | `/tablero/resumen?horizonte=3` | 200 | 19.552 | 20.8 | distritos=65; con_prediccion=65; niveles={'bajo': 65, 'medio': 0, 'alto': 0, 'muy_alto': 0}; alertas_activas=0; experimental=True; casos_estimados_region=13.46 |
| GET | `/mapa-riesgo?horizonte=3` | 200 | 22.970 | 24.2 | type=FeatureCollection; features=65; disponibles=65; experimental=True; corte=202552 |
| GET | `/alertas?horizonte=3` | 200 | 4.545 | 5.6 | total=0; disponible=True |
| GET | `/predicciones?horizonte=4` | 200 | 19.718 | 20.9 | total=65; disponible=True; ejemplo 200101 corte=202552 objetivo=202603 p=0.0 nivel=bajo casos=0.55 experimental=True |
| GET | `/series/200101?horizonte=4` | 200 | 21.745 | 22.9 | distrito=Piura; semanas=26 (2025-07-27 a 2026-01-18); semanas_con_prediccion=23 |
| GET | `/tablero/resumen?horizonte=4` | 200 | 18.309 | 19.5 | distritos=65; con_prediccion=65; niveles={'bajo': 65, 'medio': 0, 'alto': 0, 'muy_alto': 0}; alertas_activas=0; experimental=True; casos_estimados_region=16.3 |
| GET | `/mapa-riesgo?horizonte=4` | 200 | 22.310 | 23.6 | type=FeatureCollection; features=65; disponibles=65; experimental=True; corte=202552 |
| GET | `/alertas?horizonte=4` | 200 | 5.414 | 6.5 | total=0; disponible=True |
| GET | `/modelos/activo` | 200 | 9.241 | 10.2 | v2-clf-h2-1 (experimental, cumple_umbrales=True); v2-reg-h2-1 (experimental, cumple_umbrales=False); v2-clf-h3-1 (experimental, cumple_umbrales=True); v2-reg-h3-1 (experimental, cumple_umbrales=False); v2-clf-h4-1 (experimental, cumple_umbrales=True); v2-reg-h4-1 (experimental, cumple_umbrales=False) |
| GET | `/modelos/1` | 200 | 2.839 | 3.8 | {"id_version": 1, "codigo": "v2-clf-h2-1", "tarea": "clasificacion", "horizonte": 2, "algoritmo": "xgboost_multisalida_bn", "estado": "candidata", "cumple_umbrales": true, "experimental": false, "umbral_probabilidad": 0.5, "mlflow_run_id": "b72b4676cf704c189bb84f1fceb3a499", "fecha_registro": "2026- |
| GET | `/modelos/1/variables` | 200 | 7.377 | 8.4 | variables=11; primeras=propia_semanas_desde_ultimo_caso, hist_media_4, semana_epi_seno; nota=Importancia SHAP: /SHAP/ medio de la salida de este horizonte del regresor multi |
| GET | `/modelos/2` | 200 | 2.288 | 3.4 | {"id_version": 2, "codigo": "v2-reg-h2-1", "tarea": "regresion", "horizonte": 2, "algoritmo": "xgboost_multisalida_bn", "estado": "candidata", "cumple_umbrales": false, "experimental": true, "umbral_probabilidad": null, "mlflow_run_id": "b72b4676cf704c189bb84f1fceb3a499", "fecha_registro": "2026-10- |
| GET | `/modelos/2/variables` | 200 | 3.983 | 4.9 | variables=11; primeras=propia_semanas_desde_ultimo_caso, hist_media_4, semana_epi_seno; nota=Importancia SHAP: /SHAP/ medio de la salida de este horizonte del regresor multi |
| GET | `/modelos/3` | 200 | 2.118 | 3.1 | {"id_version": 3, "codigo": "v2-clf-h3-1", "tarea": "clasificacion", "horizonte": 3, "algoritmo": "xgboost_multisalida_bn", "estado": "candidata", "cumple_umbrales": true, "experimental": false, "umbral_probabilidad": 0.5, "mlflow_run_id": "b72b4676cf704c189bb84f1fceb3a499", "fecha_registro": "2026- |
| GET | `/modelos/3/variables` | 200 | 4.252 | 5.1 | variables=11; primeras=propia_semanas_desde_ultimo_caso, hist_media_4, semana_epi_seno; nota=Importancia SHAP: /SHAP/ medio de la salida de este horizonte del regresor multi |
| GET | `/modelos/4` | 200 | 2.210 | 3.2 | {"id_version": 4, "codigo": "v2-reg-h3-1", "tarea": "regresion", "horizonte": 3, "algoritmo": "xgboost_multisalida_bn", "estado": "candidata", "cumple_umbrales": false, "experimental": true, "umbral_probabilidad": null, "mlflow_run_id": "b72b4676cf704c189bb84f1fceb3a499", "fecha_registro": "2026-10- |
| GET | `/modelos/4/variables` | 200 | 4.001 | 4.9 | variables=11; primeras=propia_semanas_desde_ultimo_caso, hist_media_4, semana_epi_seno; nota=Importancia SHAP: /SHAP/ medio de la salida de este horizonte del regresor multi |
| GET | `/modelos/5` | 200 | 2.124 | 3.1 | {"id_version": 5, "codigo": "v2-clf-h4-1", "tarea": "clasificacion", "horizonte": 4, "algoritmo": "xgboost_multisalida_bn", "estado": "candidata", "cumple_umbrales": true, "experimental": false, "umbral_probabilidad": 0.5, "mlflow_run_id": "b72b4676cf704c189bb84f1fceb3a499", "fecha_registro": "2026- |
| GET | `/modelos/5/variables` | 200 | 4.133 | 5.9 | variables=11; primeras=propia_semanas_desde_ultimo_caso, hist_media_4, semana_epi_coseno; nota=Importancia SHAP: /SHAP/ medio de la salida de este horizonte del regresor multi |
| GET | `/modelos/6` | 200 | 2.288 | 3.2 | {"id_version": 6, "codigo": "v2-reg-h4-1", "tarea": "regresion", "horizonte": 4, "algoritmo": "xgboost_multisalida_bn", "estado": "candidata", "cumple_umbrales": false, "experimental": true, "umbral_probabilidad": null, "mlflow_run_id": "b72b4676cf704c189bb84f1fceb3a499", "fecha_registro": "2026-10- |
| GET | `/modelos/6/variables` | 200 | 4.018 | 4.9 | variables=11; primeras=propia_semanas_desde_ultimo_caso, hist_media_4, semana_epi_coseno; nota=Importancia SHAP: /SHAP/ medio de la salida de este horizonte del regresor multi |
| POST | `/admin/modelos/1/activar` | 409 | 5.055 | 6.0 | codigo=no_cumple_umbrales; mensaje=La versión v2-reg-h2-1 no cumple los umbrales de aceptación; se sirve solo como experimental |
| POST | `/admin/inferencias (sin X-API-Key)` {"horizonte": 4} | 401 | 0.672 | 1.6 | codigo=clave_invalida; mensaje=Clave de API ausente o inválida |

Notas:
- Las versiones se sirven por la selección experimental (`docs/backend/desviaciones_oe2.md`). `cumple_umbrales`
  se lee por versión en `/modelos/activo`; la activación es por horizonte y en pareja, así que responde 409
  `no_cumple_umbrales` si alguna de las dos versiones del horizonte no cumple.
- Sin `X-API-Key`, `POST /admin/inferencias` responde 401.
