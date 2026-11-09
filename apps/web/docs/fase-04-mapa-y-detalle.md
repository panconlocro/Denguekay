# Fase 4 — mapa y detalle distrital

Implementación del 05/11/2026, autorizada con «ahora fase 4», pendiente de revisión antes de la fase 5.
El código sigue limitado a `apps/web/`, en `feat/web-dashboard`. Se utiliza la demo de fase 2: no se
entrenó, ejecutó inferencia ni modificaron la API, sus tipos generados o la base de datos.

## Mapa

La pantalla presenta mapa, panel seleccionado, recuentos por nivel y lista de distritos sin riesgo
calculado, adaptados del nodo Figma `2:112`. Seleccionar un marcador conserva el mapa abierto y
guarda `seleccion` en la URL. El selector del panel ofrece una alternativa de teclado. Los marcadores
aceptan Enter y espacio, anuncian su nombre y estado y conservan el foco al seleccionarlos.

El panel muestra probabilidad, magnitud, intervalo nominal si existe, objetivo, horizonte y fecha
de actualización de la API. Sus enlaces abren detalle y avisos con UBIGEO, provincia y horizonte
coherentes. Los filtros geográficos siguen controlando los distritos representados; la selección
del panel es distinta del filtro global de distrito.

Los colores se acompañan de etiquetas y leyenda dinámica. Un estado `no_disponible` se pinta gris y
no muestra probabilidades o magnitudes arrastradas, aunque una respuesta contuviera valores antiguos.
Los recuentos corresponden al mapa filtrado, no a toda Piura por defecto.

## Detalle

El nodo Figma `2:436` guía la composición: probabilidad y magnitud, comparación por horizonte, serie,
contexto observado y avisos asociados. Las páginas se separaron de `SecondaryPages.tsx`; alertas,
modelo y ayuda conservan su implementación inicial.

- Cada horizonte consulta la predicción del UBIGEO elegido y conserva su propia semana objetivo.
  Las filas permiten cambiar el horizonte. Uno sin modelo no reutiliza cifras de otro.
- La magnitud mantiene hasta dos decimales. El intervalo requiere ambos límites ordenados y un nivel
  nominal válido; ausencias no se convierten en cero. Se informa que el intervalo es orientativo y
  no calibrado.
- Corte, emisión, objetivo y anticipación efectiva se muestran para el distrito, reutilizando el
  componente de vigencia de fase 3 con su alcance explícito.
- El contexto observado consulta exactamente la semana de corte: casos, umbral histórico, clima,
  fuente y cobertura. No se presenta como SHAP, contribución causal ni agregado de vecinos.
- Los avisos asociados se filtran por distrito, horizonte y semana objetivo. Su enlace lleva al
  listado existente; el desarrollo completo del módulo de alertas corresponde a fase 5.
- Carga, error, falta de catálogo, distrito desconocido y predicción ausente se distinguen. Las
  consultas de pronóstico, serie y contexto tienen recuperación independiente.

El **umbral de la semana objetivo no está en el contrato**. Se indica su ausencia; no se sustituye
por el umbral observado del corte.

## Serie semanal

La serie permite últimas 26 semanas, 52 semanas y rango personalizado, conservado en `serie_ventana`,
`serie_desde` y `serie_hasta` de la URL. Los rangos personalizados requieren dos domingos ordenados y
como máximo 520 semanas. Se envían inicio y fin explícitos, evitando depender del fin implícito del
backend. Cambiar de horizonte mantiene un rango personalizado; recargar la página lo conserva.

Los umbrales históricos se unen por UBIGEO y semana a `/observaciones`, con paginación completa.
La curva observada es continua; la pronosticada, discontinua; el umbral histórico, rojo discontinuo.
Los puntos permiten ver pronósticos aislados. Los huecos históricos se sombrean y las líneas no se
unen a través de nulos. Las semanas posteriores al corte se diferencian visualmente sin llamarlas
futuras respecto del día de consulta.

La tabla alternativa distingue cero, ausencia, magnitud, umbral, intervalo y procedencia retrospectiva
o del último corte. No se extrapolan umbrales a semanas sin observación. Un fallo de umbrales no
suprime la serie de casos, pero se muestra y elimina su curva. Solo se representan las semanas
publicadas dentro del intervalo; seleccionar fechas no genera datos ni nuevas semanas en la base.

## Evidencia

Al iniciar la fase pasaron `audit_handoff` y Great Expectations: silver **107/107** y gold **42/42**,
ambos con 30 485 filas. Reporte local: `models/serving/demo/validacion_inicio_fase4.json`.
Los hashes de demo, base antigua, integrado y gold coinciden con la verificación de fase 2.

Ejemplo comprobado por API y navegador para Piura (`200101`), h=2: objetivo 2026-S01, probabilidad
0 %, magnitud 0,37 casos e intervalo nominal del 80 % de 0 a 1 casos. En su corte 2025-S52 hay 0 casos
observados y un umbral observado de 12,96; el umbral de 2026-S01 permanece sin publicar. El corte
general sigue siendo 27/12/2025 y la emisión local 04/11/2026: son consultas históricas experimentales.

Pasaron 27 pruebas unitarias, ESLint, TypeScript, build y formato. Playwright aprobó 36 recorridos:
20 con v2 y 16 con fixtures, en escritorio (1440 px) y móvil (390 px). Incluyen selección por teclado
y conservación del foco, mapa → detalle, tres horizontes, falta de modelo, intervalos, rangos,
validación local, recarga, respuesta con valores antiguos no disponibles, errores y recuperación.
Las alteraciones artificiales de respuestas solo existen en el navegador de pruebas; no cambian la demo.

Las 9 guardas de estructura y contrato OpenAPI pasaron con los archivos nuevos preparados en el índice.
Capturas inspeccionadas frente a los diseños: `/private/tmp/denguekay-web-fase4/`, archivos
`desktop-demo-v2-map.png`, `desktop-demo-v2-detail.png`, `mobile-demo-v2-map.png` y
`mobile-demo-v2-detail.png`. Se reutilizan los assets locales y los componentes existentes; los mapas
usan centroides reales, no los polígonos esquemáticos del prototipo.

## Límites y siguiente fase

Los polígonos publicables, umbrales futuros, explicaciones individuales y agregados de vecinos siguen
pendientes de fuentes o extensiones del contrato. No se inventan esos componentes del mockup.
La suite Python completa conserva las incidencias de `VALIDACION.md`; no se repitió completa ni se
certifica verde. La siguiente fase es completar alertas, tras la revisión del usuario.
