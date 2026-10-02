# Evidencia TB1: prueba de humo local

Generado por `python -m src.api.prueba_humo` el 2026-10-02T05:26:33+00:00.
Servidor: uvicorn en `http://127.0.0.1:8000`; BD: PostgreSQL 18.6 local (Windows), BD denguekay_pruebas; la BD denguekay rechazó la contraseña del .env. Sin credenciales: la clave X-API-Key no se registra.

Entorno: Python 3.12.10, Windows-11-10.0.26300-SP0; fastapi 0.142.2,
SQLAlchemy 2.1.1, psycopg 3.3.6, xgboost 3.4.1.

| Método | Ruta | HTTP | ms (servidor) | Resumen de la respuesta |
|---|---|---|---|---|
| GET | `/salud` | 200 | 3.972 | estado=ok; conexion_bd=True; fecha_corte_datos=2025-12-27; ultima_ejecucion={'id_ejecucion': 12, 'tipo': 'inferencia', 'estado': 'exitosa', 'id_semana_corte': 202552, 'fin': '2026-10-02T00:26:15.125595-05:00'} |
| GET | `/distritos` | 200 | 14.773 | total=65; disponible=True |
| GET | `/predicciones?horizonte=4` | 200 | 48.277 | total=65; disponible=True; ejemplo 200101 corte=202552 objetivo=202603 p=0.0413 nivel=bajo casos=0.25 experimental=True |
| GET | `/predicciones?horizonte=2` | 200 | 21.530 | total=65; disponible=True; ejemplo 200101 corte=202552 objetivo=202601 p=0.0297 nivel=bajo casos=0.16 experimental=True |
| GET | `/series/200101?horizonte=4` | 200 | 19.757 | distrito=Piura; semanas=26 (2025-07-27 a 2026-01-18); semanas_con_prediccion=23 |
| GET | `/tablero/resumen?horizonte=4` | 200 | 34.258 | distritos=65; con_prediccion=65; niveles={'bajo': 65, 'medio': 0, 'alto': 0, 'muy_alto': 0}; alertas_activas=0; experimental=True; casos_estimados_region=5.02 |
| GET | `/mapa-riesgo?horizonte=4` | 200 | 25.914 | type=FeatureCollection; features=65; disponibles=65; experimental=True; corte=202552 |
| GET | `/alertas?horizonte=4` | 200 | 7.398 | total=0; disponible=True |
| GET | `/modelos/activo` | 200 | 15.798 | clf-h2-v1 (experimental, cumple_umbrales=False); reg-h2-v1 (experimental, cumple_umbrales=False); clf-h4-v1 (experimental, cumple_umbrales=False); reg-h4-v1 (experimental, cumple_umbrales=False) |
| POST | `/admin/inferencias` {"horizonte": 4} | 200 | 3302.405 | id_ejecucion=13; corte=202552; objetivo=202603; predicciones=65; disponibles=65; experimental=True; versiones={'clasificacion': 'clf-h4-v1', 'regresion': 'reg-h4-v1'} |
| POST | `/admin/inferencias` {"horizonte": 3} | 409 | 1.958 | codigo=inferencia_no_disponible; mensaje=sin modelo para h=3 |
| POST | `/admin/modelos/1/activar` | 409 | 4.691 | codigo=no_cumple_umbrales; mensaje=La versión no cumple los umbrales de aceptación; se sirve solo como experimental |
| POST | `/admin/inferencias (sin X-API-Key)` {"horizonte": 4} | 401 | 0.920 | codigo=clave_invalida; mensaje=Clave de API ausente o inválida |

Notas:
- Las versiones de modelo no cumplen los umbrales de aceptación: se sirven como `experimental: true`
  (desviación temporal, `docs/backend/desviaciones_oe2.md`). Por eso la activación responde 409
  `no_cumple_umbrales`, que es el comportamiento exigido por el CHECK del DDL.
- `POST /admin/inferencias` con h=3 responde 409 («sin modelo para h=3»); sin `X-API-Key`, 401.
