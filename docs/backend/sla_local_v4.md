# Evidencia del SLA local con la V4 (HU0016-3)

*Medido el 17/11/2026 en el entorno local de desarrollo (Windows 11, Python 3.12.10, Chrome 158, Node 24). Es evidencia
local: la medición del servicio desplegado se cumple en el OE4.*

## Criterio

Con las predicciones ya publicadas, 20 repeticiones por operación de lectura de la API y por vista principal (build de
producción), una solicitud a la vez. Se cumple con:

- p95 de cada lectura de la API < 2 s;
- p95 de la carga de cada vista < 10 s.

## Cómo se midió

- **Datos.** Una BD SQLite temporal, fuera del repo, con la V4 publicada con el paquete congelado
  (`python -m denguekay.serving.demo_database --salida <carpeta temporal> --paquete-v4 models/experimentos/mejora_modelo/v4_b3_confirmados`):
  65 distritos con sus polígonos, h = 2, 3 y 4, corte del 17/10/2026. La API la abrió en solo lectura
  (`apps/web/tools/serve_demo.py --v4 --carpeta <carpeta temporal>`, uvicorn en `127.0.0.1:18001`). No se usó la BD
  PostgreSQL local ni `mlflow.db`.
- **API.** `python -m apps.api.tools.benchmark --url http://127.0.0.1:18001 --repeticiones 20 --calentamiento 2 --limite-segundos 2 --salida docs/backend/benchmark_v4_local.json`.
  Solo lecturas (no se pasó `--incluir-escrituras`): 33 operaciones de lectura, cada una en dos modos (sin caché de
  lecturas y con caché), por HTTP real y una a la vez; el tiempo incluye recibir el cuerpo completo y se exige HTTP 200.
  El archivo de salida es [benchmark_v4_local.json](benchmark_v4_local.json).
- **Vistas.** Build de producción (`vite build` con `VITE_DATA_SOURCE=demo-v4`) servido con `vite preview` y medido con
  `apps/web/tools/measure_load.mjs` (Playwright, Chrome): 20 cargas por vista, cada una en un contexto de navegador nuevo
  (sin caché del navegador). El tiempo es el de `performance.now()` desde el inicio de la navegación hasta que la vista
  muestra su contenido principal. El archivo de salida es [sla_vistas_v4_local.json](sla_vistas_v4_local.json).

## Resultados

### Lecturas de la API (límite: p95 < 2 s)

| Modo | Operaciones | Errores | p95 máximo | Operación del máximo | Cumple |
|---|---|---|---|---|---|
| Sin caché de lecturas | 33 | 0 | 105 ms | `/mapa-riesgo?horizonte=4` | sí |
| Con caché | 33 | 0 | 101 ms | `/mapa-riesgo?horizonte=4` | sí |

Las operaciones más lentas sin caché (p50 / p95): `/mapa-riesgo` h = 4, 34 / 105 ms; h = 3, 34 / 96 ms; h = 2, 31 / 91 ms
(llevan los 65 polígonos, unos 235 kB); `/distritos`, 11 / 70 ms; `/series/200101`, 18 / 24 ms. El detalle de cada operación
está en el JSON.

### Carga de vistas (límite: p95 < 10 s)

| Vista | p50 | p95 | Máximo | Errores | Cumple |
|---|---|---|---|---|---|
| Tablero | 650 ms | 1 049 ms | 1 129 ms | 0 | sí |
| Mapa | 951 ms | 967 ms | 972 ms | 0 | sí |
| Detalle del distrito | 338 ms | 378 ms | 392 ms | 0 | sí |
| Avisos | 235 ms | 339 ms | 349 ms | 0 | sí |
| Desempeño del modelo | 314 ms | 341 ms | 345 ms | 0 | sí |
| Ayuda y manual | 144 ms | 152 ms | 153 ms | 0 | sí |

**Conclusión (observación, no generalización):** en este entorno local, con una sola solicitud a la vez, todas las
lecturas y todas las vistas principales cumplen el criterio con amplio margen.

## Qué no cubre

- **No es una medición desplegada.** Render, Supabase y Vercel no están desplegados; la latencia de red, el arranque en
  frío y los recursos limitados (Render gratuito, ver `despliegue.md`) cambiarían las cifras. Esa medición se cumple en
  el OE4.
- **No hay concurrencia:** una solicitud a la vez, como pide el criterio.
- **Las escrituras no se midieron** (`POST /admin/inferencias`, activación): con la V4 la inferencia ocurre en la
  actualización semanal, no en una solicitud de la API.
- **Las vistas se midieron sin caché del navegador** y con la API local: la carga real depende de la red del usuario. El
  mapa base de OpenStreetMap lo descarga el navegador de un servicio externo; su tiempo puede entrar en lo medido.
- **La BD es una SQLite temporal** de la demo V4, no la BD de operación (PostgreSQL).
- La medición anterior (`benchmark_sqlite.json`, `benchmark_postgresql.json`) fue con la v2 y no se reemplaza.

## Cómo repetirlo

```powershell
# 1. BD temporal con la V4 y API de solo lectura (carpeta fuera del repo)
.\.venv\Scripts\python -m denguekay.serving.demo_database --salida $env:TEMP\denguekay_sla --paquete-v4 models\experimentos\mejora_modelo\v4_b3_confirmados
.\.venv\Scripts\python apps\web\tools\serve_demo.py --v4 --carpeta $env:TEMP\denguekay_sla
# 2. Lecturas de la API (otra terminal, desde la raíz)
.\.venv\Scripts\python -m apps.api.tools.benchmark --url http://127.0.0.1:18001 --limite-segundos 2 --salida docs/backend/benchmark_v4_local.json
# 3. Vistas (otra terminal, desde apps\web)
$env:API_PROXY_TARGET="http://127.0.0.1:18001"; $env:VITE_API_BASE_URL="/api/v1"; $env:VITE_DATA_SOURCE="demo-v4"
npx vite build --outDir $env:TEMP\denguekay_dist --emptyOutDir
npx vite preview --host 127.0.0.1 --port 4173 --outDir $env:TEMP\denguekay_dist
node tools\measure_load.mjs --base http://127.0.0.1:4173 --salida ../../docs/backend/sla_vistas_v4_local.json
```

En Git Bash, anteponga `MSYS_NO_PATHCONV=1` al build: de lo contrario convierte `/api/v1` en una ruta de Windows.
