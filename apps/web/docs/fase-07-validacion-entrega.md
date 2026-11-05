# Fase 7 — Validación de entrega

El usuario autorizó esta fase con «go fase 7 pa ir a dormir». Se revisaron las seis vistas,
integración con API, accesibilidad, datos ausentes, compilación, documentación y soporte CI.
Los cambios de interfaz permanecen en `feat/web-dashboard`, dentro de `apps/web/`.
El commit de CI y arquitectura se prepara aparte en `chore/web-ci`, desde `origin/develop`.
Una rama de entrega desde esa misma base reúne ambas con merge commits y un PR borrador hacia
`develop`. Se preservan los commits previos y no se fusionan las ramas permanentes.

## Correcciones verificadas

- **Paginación:** una página HTTP 200 no disponible, un cambio de corte/actualización/total,
  páginas incompletas o repetidas y registros duplicados rechazan toda la lectura. Se mantienen
  las páginas vacías válidas. Hasta cuatro lecturas simultáneas, sin límite que trunque el historial.
- **Espera y cancelación:** cada lectura HTTP dispone de 20 segundos, incluida la lectura del
  cuerpo; combina ese plazo con la cancelación del consumidor y limpia timers/listeners.
  Un vencimiento tiene mensaje y reintento; no queda cargando indefinidamente.
- **Disponibilidad:** el resumen de avisos del tablero ya no ordena ni muestra probabilidades
  retenidas de una predicción marcada no disponible. El historial conserva su nivel registrado.
- **Contraste:** texto de menú, navegación móvil, estado experimental, resumen de avisos y ejes
  de series. La probabilidad del distrito seleccionado usa el texto oscuro del nivel, reservando
  el color brillante para indicadores gráficos. Foco oscuro en superficies claras y claro en sidebar.
- **Teclado:** tablas distritales y de desempeño son regiones etiquetadas enfocables y se
  desplazan con flechas. Escape cierra tooltips de Leaflet conservando el foco del marcador.
- **Navegación:** título del documento por vista; foco al contenido al cambiar ruta, sin robarlo
  al iniciar, cambiar filtros o escribir. Elegir un tema de ayuda enfoca su encabezado.
- **Semántica:** los estados usan h2 fuera de tarjetas tituladas y h3 dentro de ellas;
  grupos de indicadores y leyenda tienen roles y nombres explícitos.

Estas correcciones conservan datos, objetivos, etiquetas experimentales, colores de nivel y assets
originales. No se sustituyen los centroides por polígonos esquemáticos ni se inventan funciones que
la API no publica. No se modificaron el contrato, los modelos, las bases ni la investigación.

## Comprobación local

| Comprobación                                | Resultado                                             |
| ------------------------------------------- | ----------------------------------------------------- |
| Instalación limpia con `npm ci`             | Aprobada; 0 vulnerabilidades informadas por npm       |
| Tipos generados desde OpenAPI               | Sin diferencias en el archivo versionado              |
| Vitest                                      | 80 pruebas aprobadas; 45 corresponden al cliente HTTP |
| ESLint, formato, TypeScript y build         | Aprobados                                             |
| E2E con fixtures v0                         | 56 recorridos, escritorio y móvil                     |
| E2E con demo v2 real                        | 60 recorridos, escritorio y móvil                     |
| Axe, seis vistas en ambos perfiles/tamaños  | Sin infracciones automáticas detectadas               |
| Teclado, foco, 320 px y movimiento reducido | Aprobados en Chromium                                 |

Las nueve guardas de estructura y contrato OpenAPI pasaron con los archivos nuevos preparados
en el índice, tanto en el checkout de implementación como en el soporte CI.

La suite cubre tablero, mapa, distrito, avisos, desempeño y ayuda; también rutas inexistentes,
descarga del PDF, recuperación tras errores y cambio entre horizontes. Las respuestas sintéticas
solo se interceptan en el navegador de pruebas. La demo no se escribe.

Las capturas y 24 informes axe por vista están en `/private/tmp/denguekay-web-fase7/`.
Se revisan además el panel seleccionado del mapa y el estado de página inexistente con axe.
No se deshabilitan reglas ni se excluyen componentes del análisis. Los resultados `incomplete`
de contraste —por contenido fuera del área visible, tablas desplazables y mapa— requieren
revisión visual; cero infracciones automáticas **no certifica conformidad WCAG completa**.
Se comprobaron nombres/etiquetas, colores legibles, desplazamiento y geometría de assets.
No se ensayaron Safari, Firefox ni un lector de pantalla real.

Los SVG conservan sus dimensiones originales. Inter se sirve localmente. La organización y
contenido siguen los mockups y el documento; las diferencias justificadas por contrato/datos
permanecen documentadas en las fases anteriores. El manual PDF de cuatro páginas ya validado
en fase 6 se conserva; no se regeneró en esta fase.

## Estado de datos y suite general

Al iniciar se validó el integrado: **107/107 expectativas**, y gold h2: **42/42**, ambos con
**30 485 filas**. Informe local: `models/serving/demo/validacion_inicio_fase7.json` (ignorado).
Se comprueba que las huellas de gold, silver, SQLite de demo y SQLite antigua permanecen
iguales al registro de fase 2. El corte de demo sigue siendo **27/12/2025**, con seis versiones
experimentales. No se ejecutaron notebooks de investigación ni entrenamiento productivo.

Se instaló el paquete editable y Optuna, ya declarada en requirements, para ejecutar correctamente
la suite general. El intento anterior sin paquete instalado fallaba en importaciones y no se
toma como resultado de producto. La ejecución completa terminó en **465 pruebas, 4 fallos,
0 errores y 30 omisiones**; por tanto, la suite general local **no está en verde**.

Los fallos son tres comparaciones exactas de gold con el respaldo en seno/coseno (h2, h4 y B3)
y la huella de predicciones congeladas en CPU. Sus pruebas y líneas base no se cambiaron.
PostgreSQL y CUDA no se validaron localmente; las omisiones deben consultarse en el log.
La suite usa datos y bases temporales para sus pruebas; no equivale a reabrir un estudio.

Log completo: `/private/tmp/denguekay-phase7-python.log`. Los logs de navegador están en
`/private/tmp/denguekay-phase7-fixtures.log` y `/private/tmp/denguekay-phase7-demo.log`.

## CI y entrega

El workflow de soporte instala desde lockfile, regenera el contrato y exige diff vacío, ejecuta
lint/formato/unitarias/build y Playwright con Chromium contra una API de fixtures temporal.
Tiene espera acotada de salud, limpieza del proceso y diagnóstico de fallos. No depende de gold
local, no importa investigación y no sustituye la demo v2 con métricas de fixtures.
El workflow backend conserva las pruebas de PostgreSQL y cobertura existentes.

Al preparar este informe, el CI remoto aún no se ha ejecutado; el resultado se consulta en el
PR de entrega. La omisión del job cuando falta `package.json` no se considera una validación.
La integración requiere revisión y los checks del PR aprobados. No se despliega ni se fusiona
automáticamente `develop` o `main`.

Permanecen los límites del contrato ya identificados: serie regional e incidencia ausentes,
polígonos publicables pendientes, futuro umbral distrital no expuesto y canal de soporte/capacitación
sin publicar. La demo histórica y experimental sirve para revisar el frontend, no para alertas operativas.
