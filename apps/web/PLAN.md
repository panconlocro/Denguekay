# Plan del frontend por fases

El trabajo sigue el punto 6 de OE2 v1.3, los mockups de Figma y el contrato API 1.1.0.
Cada fase termina con evidencia, límites, un commit lógico y revisión del usuario antes de continuar.
El frontend solo consume lecturas de la API; no cambia datos, modelos ni el contrato para completar un mockup.
La regeneración de gold solicitada después por el usuario se documenta como preparación de datos
separada de la implementación de la interfaz.

## Punto de partida y control de versiones

La implementación inicial está en el commit local `33f483b`,
`feat(web): add API-connected surveillance dashboard`, de la rama `feat/web-dashboard`, creada desde
`origin/develop` en `494ea34`. Incluye base visual y versiones iniciales de varias vistas. Se construyó
antes de formalizar el cierre de las fases; su existencia no significa que esas fases estén aprobadas.

Ese commit no se publicó ni se fusionó durante este trabajo. La vista previa usa una API temporal de
pruebas; la selección de esa API se pasó al proceso de Vite y no quedó como conexión de producción.
Las fixtures no se importan desde el código que se entrega al navegador.

Conservar el commit permite revisar y aprovechar la implementación. No hace falta un rollback para
cambiar el origen de los datos. Los ajustes posteriores se registrarán en nuevos commits; no se
reescribirá el commit anterior para hacer desaparecer ese antecedente. Si se decide descartar partes,
se evaluará el cambio concreto antes de retirarlas.

Se mantiene la convención de `CONTRIBUTING.md`: código del frontend dentro de `apps/web/`, commits
Conventional Commits en inglés, revisión por PR hacia `develop` y merge commit al integrar. Los cambios
de soporte fuera de esta carpeta, como CI y arquitectura global, se tramitan por separado.

## Fases y condiciones de cierre

| Fase                         | Entregable                                                                   | Condición de cierre                                                                         | Estado                                                              |
| ---------------------------- | ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| 1. Contrato y alcance        | Matriz componente → endpoint → campo; inventario de datos y brechas          | Fuentes, faltantes y condiciones de integración documentados sin inventar datos             | Revisada; usuario autorizó continuar con «siguiente fase»           |
| 2. Base visual e integración | Auditar la base existente, componentes, navegación, estados y cliente tipado | Fuente de API identificada, entorno de pruebas claramente diferenciado y estados coherentes | Revisada; usuario autorizó continuar con «siguiente fase»           |
| 3. Tablero                   | Indicadores, priorización, resumen geográfico y vigencia                     | Datos comprobados por horizonte y alcance de filtros explícito                              | Revisada; usuario autorizó continuar con «ahora fase 4»             |
| 4. Mapa y detalle            | Mapa, selección, magnitud, intervalos y serie distrital                      | Recorrido completo, fechas coherentes y ausencia de valores sustituidos                     | Revisada; usuario autorizó continuar con «ahora haz la fase 5»      |
| 5. Alertas                   | Listados activos/retirados, filtros, orden y detalle                         | Paginación completa y avisos experimentales diferenciados                                   | Revisada; usuario autorizó continuar con «go fase 6»                |
| 6. Desempeño y ayuda         | Métricas por bloque, persistencia, importancias y manual                     | Métricas trazables a una versión y recursos de ayuda reales                                 | Revisada; usuario autorizó continuar con «go fase 7 pa ir a dormir» |
| 7. Validación de entrega     | Pruebas funcionales, accesibilidad, fidelidad visual, build y documentación  | Evidencia de la implementación acordada y CI del PR en verde                                | Validación local realizada; entrega para revisión y CI remoto       |

## Fase actual

La [fase 1](docs/fase-01-contrato-y-datos.md) identificó el contrato y las brechas de datos. Al cerrarla,
la BD configurada era antigua y faltaba una demo actual de v2.

Durante la fase 1 el usuario autorizó expresamente ejecutar el notebook 10. El gold se regeneró y
validó; su [informe de actualización](docs/actualizacion-gold-20261104.md) registra el respaldo, los
hashes y una diferencia mínima de seno/coseno con el archivo antiguo. No se ejecutaron migraciones,
entrenamiento ni publicación durante esa fase.

Para la fase 2 el usuario eligió expresamente «Preparar demo local de v2». Se ejecutó el constructor
existente del backend con el gold regenerado, generando una SQLite y artefactos nuevos, separados de
la base antigua. El [informe de fase 2](docs/fase-02-integracion-demo-v2.md) registra la integración,
las verificaciones y sus límites.

El usuario autorizó la fase 3 con «siguiente fase». El [cierre del tablero](docs/fase-03-tablero.md)
documenta la paginación completa, la comprobación de magnitud regional, los alcances de los filtros y
la vigencia y anticipación desde la emisión real. Solo cambió el frontend: no se entrenó de nuevo,
no se ejecutaron inferencias ni se modificaron la API o la base de demo.

El usuario autorizó la fase 4 con «ahora fase 4». El [cierre de mapa y detalle](docs/fase-04-mapa-y-detalle.md)
documenta selección geográfica, comparación de horizontes, observaciones del corte y series con
umbrales históricos y rangos configurables. Esta fase mantiene la misma API y demo.

El usuario autorizó la fase 5 con «ahora haz la fase 5». El [cierre de avisos](docs/fase-05-avisos.md)
documenta filtros, historial activo y retirado, orden sobre todas las páginas, detalle por
identificador y distinción de registros históricos y experimentales.

El usuario autorizó la fase 6 con «go fase 6». El [cierre de desempeño y ayuda](docs/fase-06-desempeno-y-ayuda.md)
documenta métricas por bloque, comparación con persistencia, importancias publicadas y un manual PDF
real con contenido compartido con la ayuda. Se conserva la API y demo de las fases anteriores.
El usuario autorizó la fase 7 con «go fase 7 pa ir a dormir». El [informe de entrega](docs/fase-07-validacion-entrega.md)
documenta validación funcional y de accesibilidad, correcciones detectadas y límites de la suite general.
La implementación permanece en `feat/web-dashboard`; CI y arquitectura se prepararon desde `develop`
en `chore/web-ci`. Una rama de entrega desde `develop` incorpora ambas mediante merge commits para
presentar un PR borrador con paquete y workflow completos, conservando la historia original.
El estado remoto del CI y la revisión del usuario determinan la integración; no se fusiona automáticamente.
