# Fase 5 — avisos activos, retirados y detalle

Implementación del 05/11/2026. El trabajo sigue en `feat/web-dashboard` y solo modifica `apps/web/`. Se reutiliza la demo
v2, sin reentrenarla, ejecutar inferencias sobre ella ni cambiar la API o las bases de trabajo.

## Listados y filtros

La pantalla se adapta del nodo Figma `3:62`, conservando cuatro indicadores, listado, historial de
retirados y explicación de la regla. Los listados se consultan por separado: una falla en activos
no impide ver retirados, y un fallo no se presenta como cero.

Los filtros de estado, nivel, orden, semana objetivo y página se conservan en `aviso_estado`,
`aviso_nivel`, `aviso_orden`, `aviso_semana` y `aviso_pagina`. Se combinan con provincia, distrito y
horizonte globales. Cambiar un filtro reinicia la página. Las URL inválidas tienen un estado
explícito y una acción para restablecer filtros.

Se cargan todas las páginas del servicio antes de filtrar, ordenar y paginar a diez registros por
página. El orden predeterminado usa nivel guardado, probabilidad vinculada, generación e identificador;
también se puede priorizar probabilidad o fecha. La probabilidad de una predicción no disponible no
se usa como si fuera válida. Los filtros respetan el distrito, horizonte y semana propios de cada fila.

Los indicadores cuentan registros activos, activos marcados «Nueva» y retirados de la selección.
**No son novedades de una actualización**: el contrato no identifica lotes. La próxima publicación
figura como «No disponible», sin sumar siete días a una fecha anterior. Los niveles de la regla
actual proceden de configuración; los niveles del historial no se recalculan con esos cortes.

«Activo» describe el estado del registro, no la vigencia de su objetivo. Los objetivos iniciados se
marcan históricos. Si el horizonte ya no tiene modelo disponible, la pantalla informa esa condición
y permite consultar su historial, sin presentarlo como un nuevo pronóstico.

En móvil, cada fila se dispone como ficha con etiquetas para conservar sus campos sin recorte.
La presentación experimental se diferencia con etiqueta y borde discontinuo; no genera notificaciones.

## Detalle por identificador

`/alertas/:id` consulta el registro real en `/api/v1/alertas/{identificador}`. Presenta estado,
cambio, generación, retiro, motivo, UBIGEO, predicción, ejecución y versiones vinculadas. Las fechas
se convierten a hora de Lima; una fecha o motivo ausente permanece explícitamente sin publicar.

El registro se abre con su horizonte, provincia, distrito y estado. Un enlace directo desalineado
se normaliza antes de mostrar cifras. La vuelta al listado conserva los filtros y página de origen;
un identificador inválido, un 404 y un error temporal tienen estados distintos.

El nivel guardado del aviso se separa del nivel y probabilidad de su predicción vinculada. En
retirados esa predicción puede haberse actualizado: no hay una instantánea anterior en el contrato
para reconstruir el «antes y después». Los intervalos solo se muestran con límites y nivel nominal
válidos. Los enlaces al distrito y al mapa advierten que consultan el último corte publicado,
que puede ser distinto del registro histórico.

## Datos y verificación

La demo conserva el corte **27/12/2025**, los modelos de fase 2 y **0 avisos activos y 0 retirados**
para h=2/3/4. Se muestra ese resultado vacío real. La API temporal de fixtures permite comprobar un
aviso de Piura al 80 %, marcado como muestra v0 de pruebas; no es una salida de v2.

Al iniciar la fase pasaron `audit_handoff` y Great Expectations: silver **107/107**, gold **42/42**,
ambos con 30 485 filas. Evidencia local: `models/serving/demo/validacion_inicio_fase5.json`.
Los hashes de demo, base antigua, integrado y gold permanecen iguales a la verificación de fase 2.

Pasaron **34 pruebas unitarias**, ESLint, TypeScript, build y formato. Playwright aprobó **52
recorridos** en escritorio (1440 px) y móvil (390 px): 28 con v2 y 24 con fixtures. Incluyen las
regresiones de tablero, mapa y detalle, y los nuevos casos de avisos.

Para probar paginación y retirados se interceptan respuestas solo en el navegador de pruebas: 135
activos y 12 retirados. Se comprueba que el registro prioritario de la segunda página del servicio
aparece primero, que se pueden recorrer todos los registros, que los filtros sobreviven al detalle
y que un fallo en una página posterior no produce un total parcial. También se prueban fechas
ausentes, recuperación del detalle y alineación de enlaces directos. No se insertan esos registros
en la demo ni se invocan endpoints de escritura.

Se inspeccionaron capturas en `/private/tmp/denguekay-web-fase5/`: `desktop-demo-v2-alerts.png`,
`mobile-demo-v2-alerts.png`, `desktop-fixtures-alerts.png`, `mobile-fixtures-alerts.png` y los detalles
con sufijo `fixtures-alert-detail.png`. Tras ajustar anchos móviles se repitieron los ocho recorridos
del módulo en cada perfil y se comprobó que la ficha no requiere desplazamiento horizontal.

Las 9 guardas de estructura y contrato OpenAPI pasaron con los archivos nuevos preparados en el índice.

## Límites

No se infieren una fecha de próxima actualización, cambios agregados por lote, probabilidades
anteriores al retiro ni razones ausentes. Los avisos son registros de consulta; esta fase no añade
notificaciones, activaciones ni mutaciones del historial. La suite Python general conserva las
incidencias de `VALIDACION.md`; no se repitió completa ni se certifica verde. La fase 6 cubre
desempeño y ayuda.
