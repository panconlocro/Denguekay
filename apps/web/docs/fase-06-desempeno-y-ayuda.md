# Fase 6 — Desempeño y ayuda

El usuario autorizó esta fase con «go fase 6», tras revisar la fase 5. El alcance sigue limitado a
`apps/web/`, en `feat/web-dashboard`: consultas de lectura sobre la misma demo v2 de fase 2.
No se ejecutó entrenamiento, inferencia, migración, publicación ni registro de modelos.

## Desempeño conectado

Se consultaron los mockups de Figma: [desempeño, nodo 3:405](https://www.figma.com/design/YntyrKwEpxRMCkAoLLhdC6/?node-id=3-405)
y [ayuda, nodo 3:754](https://www.figma.com/design/YntyrKwEpxRMCkAoLLhdC6/?node-id=3-754).
Las cifras ilustrativas se sustituyen por los campos realmente publicados. La comparación usa
**persistencia**, que es la referencia del servicio, y no la referencia lineal del dibujo.

| Componente                                   | Fuente                                   |
| -------------------------------------------- | ---------------------------------------- |
| Selección por tarea y horizonte              | `GET /api/v1/modelos/activo?horizonte=h` |
| Métricas, hiperparámetros y reproducibilidad | `GET /api/v1/modelos/{id}`               |
| Importancias y método                        | `GET /api/v1/modelos/{id}/variables`     |
| Horizontes y leyenda de riesgo               | `GET /api/v1/configuracion`              |

`/modelo` presenta recall, precisión, F1 y AUC-PR del clasificador; MAE y RMSE del regresor y su
persistencia; comparación del mismo bloque entre horizontes; importancias y ficha técnica.
Cada consulta usa la identidad de la versión. Un error de detalle no reutiliza cifras de otra
versión ni elimina importancias que pudieron consultarse por separado.

El selector `modelo_bloque` parte del bloque publicado con año más reciente. Conserva temporadas
y calendario separados y se mantiene al cambiar horizonte. Si falta el bloque en otra versión,
sus celdas indican «No disponible». Una URL con bloque desconocido permite restablecerlo.
La tarea de importancias se conserva en `modelo_importancia` y se resuelve contra la nueva versión
de ese horizonte. Los filtros geográficos no recalculan la evaluación ni las importancias.

El adaptador admite AUPRC de v0 dentro de `clasificacion.alerta_directa` y de v2 en `clasificacion`.
No convierte cadenas en cifras, no sustituye nulos por ceros y conserva ceros válidos. La razón
de errores se calcula como modelo / persistencia × 100; con persistencia cero queda indefinida.
Una razón inferior al 100 % indica menor error en ese bloque, sin decidir toda la aceptación.

**Aceptación y selección son campos distintos.** En la demo, el clasificador h2 cumple sus criterios
registrados, pero su selección de servicio sigue siendo experimental; el regresor no cumple.
Cambiar de bloque no recalcula ni cambia esa decisión. Los umbrales numéricos de aceptación no
están expuestos por configuración y no se copian del mockup.

Las métricas publicadas corresponden al protocolo por bloques, no a una evaluación nueva del
ajuste de servicio. Se muestran procedencia, fechas de ajuste, calibración, intervalo, huellas,
MLflow run e hiperparámetros. v2 no publica aquí las fechas de entrenamiento y objetivo de cada
bloque: quedan ausentes. En v0 sí se conservan las fechas publicadas; no se inventa un diagrama
de particiones a partir del año del nombre.

Las importancias preservan sus valores originales y la nota del servicio. v2 publica `|SHAP|`
medio de la salida del regresor por horizonte; v0 publica gain. Las barras solo comparan su
longitud respecto al máximo de esa versión, sin convertir los valores a porcentajes ni atribuir
causalidad. No son explicaciones individuales de un distrito o predicción.

## Ayuda y manual real

`/ayuda` incluye nueve temas, índice, búsqueda tolerante a tildes, navegación entre temas, estado
sin coincidencias y solución de problemas. `ayuda_tema` y `ayuda_buscar` se conservan en URL.
Limpiar la búsqueda mantiene horizonte y geografía. El tema de riesgo presenta la leyenda de la
configuración conectada, sin fijar sus rangos en el código de la guía.

El contenido se comparte en `../src/content/help.json`. `../tools/build_manual.py` produce
`../public/manual-usuario.pdf`: **4 páginas, 52 870 bytes**. La ayuda ofrece una descarga real.
Se verificaron el texto completo, los pies de página y las cuatro imágenes renderizadas; no
hay texto cortado ni superposiciones. Las páginas explican filtros, fechas, estimaciones,
incertidumbre, avisos, desempeño y faltantes. No fijan métricas ni límites de riesgo cambiantes.

El PDF se genera con ReportLab y se comprueba con pypdf; estas herramientas de autoría no se
añaden al bundle web. El icono de búsqueda es el asset original de Figma de 18 × 18 píxeles.
El canal de soporte, responsables y capacitación siguen pendientes de definición/publicación;
la interfaz no ofrece enlaces de contacto o reservas ficticias.

## Verificación y evidencia

Al iniciar la fase se validaron las entradas: **silver 107/107 y gold h2 42/42 expectativas**,
ambos con **30 485 filas**. Informe local ignorado: `models/serving/demo/validacion_inicio_fase6.json`.
Al cerrar, los hashes de gold, silver, SQLite de demo y SQLite antigua coinciden con el registro
de fase 2. La demo conserva seis versiones y el corte **27/12/2025**; sigue siendo histórica y
experimental. No se ejecutó investigación congelada ni se alteraron las entradas.

Pasaron **39 pruebas unitarias**, ESLint, TypeScript, build y formato. Playwright aprobó **76
recorridos**: **40 con v2 real** y **36 con fixtures v0**, repartidos entre escritorio y móvil.
Los casos nuevos cubren períodos/versiones, cambio de horizonte, método de importancia, cero/nulo,
persistencia cero, bloque desconocido, recuperación independiente tras 503, horizonte sin modelo,
búsqueda, leyenda y PDF.
Las respuestas sintéticas de esos casos solo se interceptan en el navegador de pruebas.

Durante la preparación se corrigieron selectores de prueba que no incluían el estado del botón
de horizonte o confundían los encabezados h1/h2 de ayuda. Un intento con seis workers agotó el
tiempo al crear un contexto de Chrome, antes de cargar la app. La concurrencia quedó en dos;
el perfil completo v2 pasó después de ese ajuste.

La revisión final detectó una carga indefinida al seleccionar un horizonte sin modelo. Se corrigió
con un estado explícito, sin reutilizar versiones en caché, y alternativas hacia horizontes
disponibles. Se añadió su recorrido y se repitieron completos ambos perfiles. Las **9 guardas de
estructura y contrato OpenAPI** también pasaron con los archivos nuevos preparados en el índice.

Capturas locales en `/private/tmp/denguekay-web-fase6/`: `desktop-models-demo-v2.png`,
`mobile-models-demo-v2.png`, `desktop-help-demo-v2.png`, `mobile-help-demo-v2.png` y equivalentes
con fixtures. Se inspeccionaron ambas vistas y tamaños. Las tablas móviles se desplazan dentro
de su contenedor, sin ampliar la página. Previsualizaciones del PDF en `manual/pagina-1.png`
hasta `manual/pagina-4.png` dentro de la misma carpeta temporal.

La suite Python completa y el CI no se repitieron; persisten los límites de entorno/equivalencia
documentados antes. La fase 7 queda pendiente de revisión, con validación de entrega y cambios
de soporte separados para CI y arquitectura global.
