# Denguekay web

Primera entrega del frontend de vigilancia de dengue en Piura, basada en el punto 6 de OE2 v1.3 y los
[mockups de Figma](https://www.figma.com/design/YntyrKwEpxRMCkAoLLhdC6). React, Vite y TypeScript;
tokens de Figma, Inter local, TanStack Query, React Leaflet y Recharts.
Solo consume lecturas de /api/v1; no lee datos, modelos ni la BD directamente.

## Trabajo por fases

El [plan de fases](PLAN.md) separa el commit inicial de la propuesta de los cierres que se revisarán con
el usuario. La [fase 1](docs/fase-01-contrato-y-datos.md) documenta el contrato de cada componente y el
inventario local. Después se [regeneró gold](docs/actualizacion-gold-20261104.md) por solicitud expresa,
pero la BD configurada sigue con un esquema antiguo y aún no hay una demo actual de v2 en esta máquina.
No debe interpretarse la vista previa con fixtures como una publicación completa de v2.

## Ejecutar en desarrollo

Se necesita Node.js 20.19+ y una API configurada según
[la guía del backend](../../docs/backend/guia_frontend.md). Desde esta carpeta:

```bash
npm ci
npm run dev
```

Abrir http://127.0.0.1:5173. Vite reenvía /api/v1 a http://127.0.0.1:8000.
La API debe iniciarse aparte con la BD migrada y cargada. Un fallo de conexión se muestra con reintento;
no hay datos de ejemplo como reemplazo en ejecución.

Para otra URL, copiar .env.example a .env.local y ajustar API_PROXY_TARGET (proxy de desarrollo).
En producción, VITE_API_BASE_URL es la URL pública completa terminada en /api/v1. Las variables VITE_*
son públicas y se incorporan al build: nunca colocar API_KEY ni credenciales de BD o Supabase.
Configurar CORS en la API para el origen del frontend y el hosting de la SPA para devolver index.html
al abrir rutas internas.

## Qué incluye

- Tablero conectado: indicadores regionales, predicciones priorizadas, mapa, avisos y horizontes.
- Filtros de provincia/distrito para mapa y listados; no alteran los indicadores regionales.
- Horizonte y predeterminado leídos de /configuracion; filtros conservados en la URL.
- Navegación de las seis vistas. Mapa, selección distrital, serie, avisos paginados, versiones del modelo
  y ayuda tienen una implementación inicial funcional.
- Estados de carga, ausencia, error y reintento por consulta. Un resultado fallido no conserva datos
  anteriores en pantalla. Un cambio de horizonte no reutiliza predicciones de otro horizonte.
- Vista móvil a 390 px, navegación inferior, tabla alternativa al gráfico y movimiento reducido.
- Tipos generados del contrato 1.1.0; código y comentarios en inglés, interfaz en español.
- Assets originales locales de Figma; mapas y gráficos dinámicos desde la API.

## Límites y siguientes entregas

- El mapa usa centroides reales; no usa los polígonos esquemáticos de Figma. Soporta Point, Polygon y
  MultiPolygon. Los polígonos requieren una fuente publicable en el backend. El mapa base usa
  OpenStreetMap con atribución y conexión, sujeto a su
  [política de teselas](https://operations.osmfoundation.org/policies/tiles/).
  Si no cargan las teselas, los marcadores permanecen sobre el fondo del mapa.
- La API no publica serie regional ni incidencia: esos componentes explican su ausencia.
  Seleccionar un distrito muestra su serie real; no se inventan curvas ni poblaciones.
- Desempeño muestra versiones reales; las métricas por bloque e importancias completas quedan para su
  entrega. Ayuda contiene la guía inicial; PDF, capacitación y soporte están pendientes de publicación.
- El objetivo corresponde al corte publicado: mapa y resumen no aceptan corte histórico.
  Los rangos personalizados de la serie y los umbrales futuros quedan pendientes.
- No se muestran explicaciones individuales ni agregados de vecinos que la API no expone.
- Siguen pendientes las correcciones de backend de la revisión: sumas regionales incompletas, coherencia
  al desactivar modelos experimentales y rangos de series con fecha final implícita. Los casos observados
  indican «cobertura distrital no informada»: el valor de la API no certifica cobertura de los 65 distritos.
- Los modelos experimentales llevan banda visible. Sus avisos no son alertas operativas ni generan
  notificaciones. Disponible no significa validado.
- Si el objetivo ya pasó se marca «Consulta histórica». Los intervalos son orientativos y no calibrados.

## Estructura

- ./src/api/: cliente de lectura, consultas y tipos OpenAPI.
- ./src/components/: filtros, estados, mapa y serie temporal.
- ./src/lib/: formato numérico, fechas de Lima y colores de riesgo.
- ./src/pages/: tablero y versiones iniciales de las otras vistas.
- ./src/test/: configuración de pruebas unitarias.
- ./src/App.tsx: navegación, filtros en URL y estructura responsive.
- ./src/tokens.css y ./src/styles.css: guía visual.
- public/assets/: logotipo e iconos originales de Figma.
- e2e/: recorridos en navegador y API temporal aislada.

## Comprobaciones

```bash
npm run api:generate
npm run typecheck
npm run lint
npm test
npm run build
```

api:generate actualiza ./src/api/schema.d.ts desde docs/backend/openapi_v1.json. No modifica el contrato
ni sus fixtures. El lockfile se versiona; los builds y node_modules no.

Para probar con la API real sobre fixtures aisladas, sin usar la BD del proyecto:

1. Desde la raíz, con las dependencias Python completas instaladas:

   ```bash
   .venv/bin/python apps/web/e2e/serve_api.py
   ```

   En Windows: .venv\Scripts\python apps/web/e2e/serve_api.py. Crea una SQLite temporal migrada y publica
   modelos de prueba sobre fixtures; escucha en 127.0.0.1:18000. No escribe en data/.
   Las fixtures usan v0, h=2 y h=4; h=3 no disponible comprueba ese estado del contrato.

2. Desde apps/web, instalar el navegador una vez y ejecutar:

   ```bash
   npx playwright install chromium
   npm run test:e2e
   ```

   Usa Vite de pruebas en el puerto 5174. CHROME_PATH permite usar Chrome instalado.
   WEB_SCREENSHOT_DIR permite guardar capturas fuera del repositorio.

3. Detener la API temporal con Ctrl+C; su carpeta se limpia al cerrar.

Se prueban escritorio y móvil: filtros, navegación, avisos, assets, horizonte sin modelo y recuperación
tras 503. Los datos esperados son los de las fixtures, no los de una BD de desarrollo o producción.

El CI del frontend y el mapa global de arquitectura se integrarán como cambios de soporte separados.
Esta rama conserva el alcance apps/web establecido en CONTRIBUTING.md.
