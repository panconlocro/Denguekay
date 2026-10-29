# Guía para el frontend (contrato v1)

Para quien construye `apps/web/`. Explica cómo levantar la API en local con la BD de demostración, dónde
está el contrato, cómo generar tipos TypeScript y qué reglas debe respetar la interfaz. El plan de
pantallas está en [apps/web/README.md](../../apps/web/README.md).

## 1. El contrato

- **Contrato congelado:** [openapi_v1.json](openapi_v1.json) (OpenAPI 3.1, sin ejemplos). Es la fuente de
  verdad para el frontend: un test del CI falla si la API se aparta de él.
- **Con ejemplos reales:** [openapi.json](openapi.json) (el mismo contrato, más un ejemplo por lectura
  sacado de la BD de demostración).
- **Reglas y versiones:** [contrato_api.md](contrato_api.md). La versión del contrato es **1.0.0** y viaja
  en la cabecera `X-Version-Contrato` de cada respuesta. Un cambio aditivo sube la minor (1.1.0, …) y nunca
  rompe lo que ya funciona; un cambio que rompe iría en `/api/v2`.
- **URL base en desarrollo:** `http://127.0.0.1:8000/api/v1`. La documentación interactiva está en
  `http://127.0.0.1:8000/docs`.

## 2. Levantar la API en local

Necesitas Windows con PowerShell (o macOS/Linux con los comandos equivalentes), Python 3.12 y el
repositorio clonado. No necesitas `data/` ni PostgreSQL.

1. **Entorno de Python** (una vez), desde la raíz del repo:

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
   ```

   Crea `.venv` e instala `requirements.txt` y el paquete `denguekay` (en macOS/Linux, `scripts/setup.sh`).

2. **BD de demostración.** Rosa la genera en su PC (paso 4) y la comparte fuera de Git (Drive o un
   Release de GitHub): es la carpeta `demo/` con `denguekay_demo.sqlite` y `storage/`. Contiene los datos
   agregados reales de Piura (casos y clima por distrito y semana; sin datos personales) y el modelo v0
   publicado como demo experimental. Descomprímela, por ejemplo, en `models/serving/demo/` (esa carpeta
   no se versiona).

3. **Arrancar la API** apuntando a esa BD:

   ```powershell
   $env:DATABASE_URL = "sqlite:///models/serving/demo/denguekay_demo.sqlite"
   .\.venv\Scripts\python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
   ```

   Comprueba con `http://127.0.0.1:8000/api/v1/salud` (`"conexion_bd": true`) y
   `http://127.0.0.1:8000/api/v1/configuracion`. El origen CORS permitido es `http://localhost:5173`, el del
   servidor de desarrollo de Vite.

   Las lecturas no necesitan clave. Las escrituras (`POST /admin/*`) quedan fuera del frontend (C6).

4. **Generar la BD de demostración** (lo hace Rosa, en una PC con `data/`):

   ```powershell
   .\.venv\Scripts\python -m denguekay.serving.demo_database
   ```

   Escribe en `models/serving/demo/` (y el reporte de la publicación en `models/serving/ejecuciones/`, como
   toda publicación) y solo lee `data/`. Con `--reemplazar` rehace una demo anterior y con
   `--salida <carpeta>` usa otra carpeta. Su registro de MLflow queda dentro de esa carpeta, no en el
   `mlflow.db` del proyecto.

## 3. Tipos TypeScript desde el contrato

El paquete [`openapi-typescript`](https://www.npmjs.com/package/openapi-typescript) convierte OpenAPI 3.0 y
3.1 en tipos TypeScript. Versión vigente al 29/10/2026: **7.13.0** (verificada en `registry.npmjs.org`). Desde
`apps/web/`:

```bash
npx openapi-typescript@7.13.0 ../../docs/backend/openapi_v1.json -o src/api/schema.d.ts
```

Regenera los tipos cada vez que cambie la minor del contrato (el changelog está en `contrato_api.md`).

## 4. Reglas que la interfaz debe respetar

- **Nada en código duro.** Horizontes disponibles, horizonte por defecto (4), cortes de riesgo, niveles,
  leyenda del mapa, corte vigente y nota experimental salen de `GET /configuracion`.
- **Horizontes:** 2, 3 y 4 semanas. Un horizonte sin modelo (hoy, h=3) responde 200 con `disponible: false`
  y `motivo: "sin modelo para h=3"`: la interfaz lo muestra así, no como error.
- **Faltantes ≠ ceros.** Un `null` con `disponible: false` y `motivo` se muestra como «sin datos» con su
  motivo, nunca como 0. Un 0 sí es un dato (cero casos notificados).
- **`experimental: true` siempre visible.** Hoy ningún modelo cumple los umbrales de aceptación (HU0007-4);
  la nota de `/configuracion`, `/tablero/resumen` y `/modelos/activo` lo explica.
- **`ubigeo` es texto** de seis dígitos con ceros a la izquierda; nunca se convierte a número.
- **Intervalos de casos** (`casos_intervalo_inferior`, `casos_intervalo_superior`, `nivel_intervalo` = 0,80):
  hoy son `null` con `motivo_intervalo`, porque el modelo servido no los estima. La interfaz debe estar
  lista para mostrarlos cuando lleguen, sin cambiar el contrato.
- **Mapa:** `features[].geometry` puede ser `Point` (hoy, centroides), `Polygon` o `MultiPolygon` (cuando
  haya límites con licencia). Las coordenadas son `[longitud, latitud]`.
- Textos en español y unidades en los gráficos (casos, casos por 100 000 hab.).
