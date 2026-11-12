# Denguekay web

Frontend de vigilancia de dengue en Piura, basado en el punto 6 de OE2 v1.3 y los
[mockups de Figma](https://www.figma.com/design/YntyrKwEpxRMCkAoLLhdC6). React, Vite y TypeScript;
tokens de Figma, Inter local, TanStack Query, React Leaflet y Recharts.
Solo consume lecturas de /api/v1; no lee datos, modelos ni la BD directamente.

## Trabajo por fases

El [plan de fases](PLAN.md) separa el commit inicial de la propuesta de los cierres que se revisarán con
el usuario. La [fase 1](docs/fase-01-contrato-y-datos.md) documenta el contrato de cada componente y el
inventario local. Después se [regeneró gold](docs/actualizacion-gold-20261104.md) por solicitud expresa.
La [fase 2](docs/fase-02-integracion-demo-v2.md) integra una demo local v2 autorizada por el usuario,
con base y artefactos separados de la BD antigua. La interfaz identifica el entorno y verifica las
versiones de v2 antes de mostrar sus resultados. Su corte sigue siendo diciembre de 2025.

La [fase 3](docs/fase-03-tablero.md) completa el tablero: listado paginado de todos los distritos,
cobertura de magnitud regional comprobada, alcance de filtros explícito y anticipación desde la
emisión real. Una semana objetivo se identifica como histórica desde que comienza.

La [fase 4](docs/fase-04-mapa-y-detalle.md) completa el mapa con selección y panel distrital, y el
detalle con comparación de horizontes, intervalos, observaciones del corte y series de 26/52 semanas
o rango personalizado. Los umbrales históricos se consultan por semana; no se extrapolan al objetivo.

La [fase 5](docs/fase-05-avisos.md) completa avisos: activos y retirados, filtros y página en la URL,
orden sobre todos los registros cargados y detalle por identificador con estado, fechas y motivo.
Un registro activo con objetivo iniciado se identifica como histórico.

La [fase 6](docs/fase-06-desempeno-y-ayuda.md) completa desempeño y ayuda con métricas por bloque,
persistencia, importancias y manual. La [fase 7](docs/fase-07-validacion-entrega.md) valida la entrega,
incorpora auditorías axe y corrige contraste, foco, acceso por teclado y paginación inconsistente.

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
Usa `VITE_DATA_SOURCE=api` para identificar la conexión a la API. La interfaz muestra las versiones
publicadas por el servicio, incluida V3 cuando está seleccionada. Si falta la etiqueta de fuente,
se muestra una advertencia.
En producción, VITE_API_BASE_URL es la URL pública completa terminada en /api/v1. Las variables VITE_*
son públicas y se incorporan al build: nunca colocar API_KEY ni credenciales de BD o Supabase.
Configurar CORS en la API para el origen del frontend y el hosting de la SPA para devolver index.html
al abrir rutas internas.

### Demo local V4 con b3

La demo V4 publica la semilla 17 del paquete congelado del paper, con origen en la SE 41 de 2026.
En la raíz del repositorio, indicar la carpeta que contiene el manifiesto y los boosters:

```bash
.venv/bin/python -m denguekay.serving.demo_database --paquete-v4 /ruta/v4_b3_confirmados
.venv/bin/python apps/web/tools/serve_demo.py --v4
```

En otra terminal, desde `apps/web`:

```bash
npm run dev:demo
```

La API abre `models/serving/demo_v4/denguekay_demo.sqlite` en modo lectura. El frontend verifica
la identidad de las seis versiones experimentales V4. La demo muestra casos confirmados de la Sala
desde la SE 01 de 2025, las predicciones archivadas y las del corte congelado. Las salidas vigentes
son probabilidad de brote y conteo puntual. El corte de 2026 se muestra como retrospectiva.

### Demo local V3

La [guía de V3](../../docs/modeling/reproducir_v3.md#8-ruta-del-producto-de-un-clon-de-develop-a-la-api-con-la-v3)
detalla los insumos, la generación de gold y la publicación. Con los insumos preparados, el
comando `.venv/bin/python -m denguekay.serving.demo_database` construye la demo local con el
modelo configurado en el repo.

Con la demo ya preparada, desde la raíz:

```bash
.venv/bin/python apps/web/tools/serve_demo.py
```

Desde esta carpeta, en otra terminal:

```bash
npm run dev:demo:v3
```

La API escucha en 18001 y abre solo `models/serving/demo/denguekay_demo.sqlite` en modo de lectura;
no migra la base antigua ni entrena al arrancar. Vite usa ese proxy y verifica los seis modelos
experimentales V3 para los horizontes 2, 3 y 4. Para abrir una demo histórica V2 que ya esté
preparada en esa ruta, usa `npm run dev:demo:v2`.

## Qué incluye

- Tablero conectado: indicadores regionales, predicciones priorizadas, mapa, avisos y horizontes.
- Filtros de provincia/distrito para mapa y listados; no alteran los indicadores regionales.
- Horizonte y predeterminado leídos de /configuracion; filtros conservados en la URL.
- Navegación de las seis vistas. Mapa con selección por clic o teclado, panel y recuentos de riesgo;
  detalle con comparación de horizontes, observaciones e intervalos. Versiones y ayuda conservan
  su implementación inicial hasta su fase específica.
- Avisos activos/retirados con filtros geográficos, nivel, semana y orden; detalle trazable y
  navegación de vuelta que conserva el listado. Las fechas se muestran en hora de Lima.
- Series con rangos de 26/52 semanas o fechas semanales personalizadas, guardados en la URL;
  umbral histórico por semana, huecos explícitos y tabla alternativa con procedencia del pronóstico.
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
- Desempeño muestra métricas por bloque, comparación con persistencia, importancias y trazabilidad
  de cada versión. Ayuda incluye búsqueda, leyenda vigente y un manual PDF descargable de cuatro
  páginas. Capacitación y canal de soporte siguen pendientes de definición y publicación.
- El objetivo corresponde al corte publicado: mapa y resumen no aceptan corte histórico.
  La serie permite rangos personalizados. El umbral futuro de brote sigue sin publicarse por la API.
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
- ./src/pages/: tablero, mapa, detalle, avisos, desempeño y ayuda.
- ./src/content/help.json: contenido compartido entre ayuda y manual.
- ./src/test/: configuración de pruebas unitarias.
- ./src/App.tsx: navegación, filtros en URL y estructura responsive.
- ./src/tokens.css y ./src/styles.css: guía visual.
- public/assets/: logotipo e iconos originales de Figma.
- public/manual-usuario.pdf: manual descargable desde Ayuda.
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
   Para una vista previa manual, usar `npm run dev:fixtures`: su banda visible distingue las fixtures
   de la demo v2 e informa que contienen valores alterados para pruebas de interfaz.

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

Para probar con la demo v2, iniciar `tools/serve_demo.py` y ejecutar:

```bash
WEB_TEST_SOURCE=demo-v2 npm run test:e2e
```

En PowerShell, definir primero `$env:WEB_TEST_SOURCE="demo-v2"`. Este perfil usa 18001 y comprueba
los tres horizontes, el recorrido distrital y el bloqueo de una conexión con otra versión.

El CI del frontend y el mapa global de arquitectura se prepararon como un commit de soporte en
`chore/web-ci`, desde `develop`. La rama de entrega reúne ese soporte con esta implementación para
su eventual PR hacia `develop`, sin fusionar automáticamente. Por decisión del usuario, la entrega
se conserva local: no hay rama publicada ni PR creado. La rama de frontend conserva el
alcance apps/web establecido en CONTRIBUTING.md.

Las lecturas tienen un plazo de 20 segundos y cancelación al cambiar de consulta. Los listados
completos usan hasta cuatro páginas simultáneas y verifican disponibilidad, corte, actualización,
total, tamaño, número de página y duplicados. Si el conjunto cambia durante su lectura, se muestra
un error con reintento; no se presenta un total parcial como completo.

## Desempeño y ayuda (fase 6)

`/modelo` conserva el bloque en `modelo_bloque` y la tarea de importancias en `modelo_importancia`.
Las métricas provienen del detalle de cada versión seleccionada por la API. Se muestra el mismo
bloque en la tabla de horizontes, sin sustituir períodos ausentes ni confundir la evaluación con
el ajuste de servicio. Las importancias conservan el método y los valores originales publicados:
gain en v0 y SHAP en la demo v2. Los filtros geográficos no recalculan métricas ni importancias.

`/ayuda` conserva tema y búsqueda en `ayuda_tema` y `ayuda_buscar`. La leyenda se consulta en la
configuración conectada. El manual evita copiar métricas y límites de riesgo que pueden cambiar.
Para regenerarlo tras modificar el contenido compartido, desde la raíz:

```bash
python apps/web/tools/build_manual.py
```

Requiere `reportlab` y `pypdf` en el entorno usado para autoría; no son dependencias del navegador.
El generador verifica las cuatro páginas y el texto compartido. Después de regenerar se deben
renderizar y revisar visualmente las páginas antes de versionar el PDF.

El [cierre de fase 6](docs/fase-06-desempeno-y-ayuda.md) detalla las fuentes, decisiones y pruebas.
