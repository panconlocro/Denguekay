# Fase 3 — tablero con datos de la demo v2

Implementación del 05/11/2026.
El alcance sigue siendo `apps/web/`, en `feat/web-dashboard`. Se reutiliza la demo de fase 2: no se
entrenó, ejecutó inferencia ni modificaron endpoints, datos o bases.

## Comportamiento entregado

- Los cuatro indicadores siguen siendo regionales. Se identifica el alcance de mapa, listado y avisos;
  seleccionar provincia o distrito no recalcula las cifras regionales.
- La magnitud regional requiere resumen y predicciones del mismo horizonte, corte y objetivo, con
  una fila con magnitud por cada distrito. Nulos, duplicados y distritos ausentes impiden presentar
  un total completo aunque la API lo marque disponible. No se calcula una suma nueva.
- Los conteos ausentes no se sustituyen por cero. Los casos observados conservan la advertencia de
  cobertura desconocida: el contrato no aporta el recuento de observaciones completas.
- El listado permite recorrer los 65 distritos en páginas de nueve filas, por probabilidad descendente
  y UBIGEO en empates. Cambiar horizonte, geografía o corte reinicia la página. Las probabilidades
  nulas no muestran una barra que pueda confundirse con cero. Las magnitudes usan hasta dos decimales
  para evitar presentar valores pequeños positivos como «≈ 0».
- Mapa y listado indican cobertura. El mapa usa su propia semana objetivo. Se conserva la leyenda
  dinámica, los centroides reales y el acceso al catálogo. El mapa llena el espacio de su tarjeta.
- Una selección geográfica incompatible en la URL se identifica y puede limpiarse. Un catálogo
  pendiente o fallido no se confunde con una selección sin resultados.
- Cada consulta fallida oculta su resultado y permite reintentar; las otras secciones continúan
  disponibles. El contador pendiente/fallido de avisos muestra «—», no cero.

## Vigencia y anticipación

Conforme al punto 6 de OE2, se muestran corte, semana objetivo con fechas, emisión y anticipación
efectiva mínima entre los distritos con predicción disponible. Se usa `fecha_generacion`, no la
actualización general de la API, y el inicio del objetivo a medianoche en Piura (UTC−5).
La comparación con dos semanas usa el intervalo sin redondear (14 días). La cifra positiva visible
se trunca a una décima: 1,99 semanas no aparece como dos. Una fecha ausente produce «No disponible»;
una emisión coincidente con el inicio del objetivo o posterior produce «Sin anticipación».

El objetivo se identifica como histórico desde su **inicio**, en lugar de esperar al fin de semana.
El encabezado dice «Consulta histórica · objetivo iniciado». El estado no experimental se denomina
«Validado», evitando afirmar «Operativo» sin comprobar anticipación. La demo mantiene «Experimental»
para los tres horizontes.

## Datos y evidencia

Al iniciar la fase pasaron `audit_handoff` y Great Expectations: **107/107** expectativas en silver y
**42/42** en gold, ambos con 30 485 filas. Evidencia local ignorada por Git:
`models/serving/demo/validacion_inicio_fase3.json`. Los hashes de demo, base antigua, gold e integrado
coinciden con los de `models/serving/demo/verificacion_frontend.json` de fase 2.

La fuente mantiene corte **27/12/2025** y las cifras de fase 2:

| Horizonte | Objetivo | Predicciones disponibles | Magnitud regional | Avisos actuales |
| --------- | -------- | ------------------------ | ----------------- | --------------- |
| 2 semanas | 2026-S01 | 65                       | 10,98             | 0               |
| 3 semanas | 2026-S02 | 65                       | 13,12             | 0               |
| 4 semanas | 2026-S03 | 65                       | 15,58             | 0               |

La emisión local fue el 04/11/2026: los tres objetivos son históricos y sin anticipación desde esa
emisión. No se añadieron cifras ni avisos para llenar el diseño.

Pasaron 18 pruebas unitarias, ESLint, TypeScript, build y 20 recorridos de navegador (12 con v2 y 8 con
fixtures), a 1440 y 390 px. Se verifican las 65 posiciones, estabilidad de indicadores al filtrar,
falta de magnitud, conteos ausentes, anticipación inferior a dos semanas, errores independientes,
selección inválida y recuperación. Los datos alterados solo se inyectan en respuestas del navegador
de pruebas; no se modifican las bases.

Tras el ajuste visual se repitió el recorrido principal en ambas pantallas, comprobando el tamaño del
mapa y las dimensiones naturales de los assets visibles. Capturas inspeccionadas frente al tablero
Figma `1:261`: `/private/tmp/denguekay-web-fase3/desktop-demo-v2.png` y
`/private/tmp/denguekay-web-fase3/mobile-demo-v2.png`. Se conserva la base visual y se añaden el bloque
de vigencia requerido por OE2 y la navegación del listado.

## Límites

Serie regional, incidencia, variación semanal y consulta de cortes históricos siguen ausentes del
contrato; se explican sus ausencias y se ofrece la serie distrital. La verificación de magnitud en el
navegador no corrige el agregado incompleto del backend; esa corrección y la cobertura de observados
siguen pendientes por separado. No se repitió la suite Python completa ni se certifica verde.

La fase 4 cubre el mapa y el detalle distrital. Al cierre de esta fase, las vistas de fases
posteriores conservaban su implementación inicial.
