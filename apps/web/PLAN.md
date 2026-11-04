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

| Fase                         | Entregable                                                                   | Condición de cierre                                                                         | Estado                                                   |
| ---------------------------- | ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- | -------------------------------------------------------- |
| 1. Contrato y alcance        | Matriz componente → endpoint → campo; inventario de datos y brechas          | Fuentes, faltantes y condiciones de integración documentados sin inventar datos             | Documentada; pendiente de revisión del usuario           |
| 2. Base visual e integración | Auditar la base existente, componentes, navegación, estados y cliente tipado | Fuente de API identificada, entorno de pruebas claramente diferenciado y estados coherentes | Pendiente; existe código inicial reutilizable            |
| 3. Tablero                   | Indicadores, priorización, resumen geográfico y vigencia                     | Datos comprobados por horizonte y alcance de filtros explícito                              | Pendiente; existe versión inicial                        |
| 4. Mapa y detalle            | Mapa, selección, magnitud, intervalos y serie distrital                      | Recorrido completo, fechas coherentes y ausencia de valores sustituidos                     | Pendiente; existe versión inicial                        |
| 5. Alertas                   | Listados activos/retirados, filtros, orden y detalle                         | Paginación completa y avisos experimentales diferenciados                                   | Pendiente; existe versión inicial                        |
| 6. Desempeño y ayuda         | Métricas por bloque, persistencia, importancias y manual                     | Métricas trazables a una versión y recursos de ayuda reales                                 | Pendiente; existen vistas iniciales                      |
| 7. Validación de entrega     | Pruebas funcionales, accesibilidad, fidelidad visual, build y documentación  | Evidencia de la implementación acordada y CI del PR en verde                                | Pendiente; las pruebas previas no sustituyen este cierre |

## Fase actual

La [fase 1](docs/fase-01-contrato-y-datos.md) identifica qué está expuesto por la API y qué datos
operacionales existen en esta máquina. El resultado de preparación de datos es **no listo para validar
la publicación completa v2**: la BD configurada es antigua y no se encontró la demo actual de v2.

Durante la fase 1 el usuario autorizó expresamente ejecutar el notebook 10. El gold se regeneró y
validó; su [informe de actualización](docs/actualizacion-gold-20261104.md) registra el respaldo, los
hashes y una diferencia mínima de seno/coseno con el archivo antiguo. No se ejecutaron migraciones,
entrenamiento ni publicación. La BD y los artefactos de v2 siguen pendientes.

El siguiente paso requiere revisar estos resultados y elegir la fuente real para integrar: una demo
actual ya publicada de v2 o una API de desarrollo compatible y verificada. Entrenar/publicar v2
localmente sería trabajo adicional de backend; ejecutar el notebook de gold no realizó esos pasos.
