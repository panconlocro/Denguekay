# Desarrollo del frontend por fases

El frontend sigue el punto 6 de OE2 v1.3, los mockups de Figma y el contrato API 1.1.0. Se desarrolló en siete fases;
cada una se cerró con evidencia, límites documentados y un commit lógico, y se revisó antes de pasar a la siguiente.
El frontend solo consume lecturas de la API: no cambia datos, modelos ni el contrato para completar un mockup. La
regeneración de gold hecha durante la fase 1 se documenta como preparación de datos, separada de la interfaz.

## Punto de partida y control de versiones

La implementación inicial es el commit `33f483b`, `feat(web): add API-connected surveillance dashboard`, de la rama
`feat/web-dashboard`, creada desde `origin/develop` en `494ea34`. Incluía la base visual y versiones iniciales de varias
vistas, construidas antes de formalizar el cierre de las fases. La vista previa usaba una API temporal de pruebas,
seleccionada en el proceso de Vite y no como conexión de producción; las fixtures no se importan desde el código que se
entrega al navegador.

Ese commit se conservó: los ajustes posteriores se registraron en commits nuevos, sin reescribir el anterior. El código
del frontend vive en `apps/web/` con las convenciones de `CONTRIBUTING.md` (Conventional Commits en inglés, PR hacia
`develop` y merge commit). Los cambios de soporte fuera de esta carpeta, como el CI y la arquitectura global, se
prepararon por separado en `chore/web-ci`.

## Fases

| Fase                         | Entregable                                                                        | Condición de cierre                                                              | Informe                                  |
| ---------------------------- | --------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- | ---------------------------------------- |
| 1. Contrato y alcance        | Matriz componente → endpoint → campo; inventario de datos y brechas               | Fuentes, faltantes y condiciones de integración documentados sin inventar datos  | [fase 1](fase-01-contrato-y-datos.md)    |
| 2. Base visual e integración | Auditoría de la base existente, componentes, navegación, estados y cliente tipado | Fuente de API identificada, entorno de pruebas diferenciado y estados coherentes | [fase 2](fase-02-integracion-demo-v2.md) |
| 3. Tablero                   | Indicadores, priorización, resumen geográfico y vigencia                          | Datos comprobados por horizonte y alcance de filtros explícito                   | [fase 3](fase-03-tablero.md)             |
| 4. Mapa y detalle            | Mapa, selección, magnitud, intervalos y serie distrital                           | Recorrido completo, fechas coherentes y sin valores sustituidos                  | [fase 4](fase-04-mapa-y-detalle.md)      |
| 5. Alertas                   | Listados activos y retirados, filtros, orden y detalle                            | Paginación completa y avisos experimentales diferenciados                        | [fase 5](fase-05-avisos.md)              |
| 6. Desempeño y ayuda         | Métricas por bloque, persistencia, importancias y manual                          | Métricas trazables a una versión y recursos de ayuda reales                      | [fase 6](fase-06-desempeno-y-ayuda.md)   |
| 7. Validación de entrega     | Pruebas funcionales, accesibilidad, fidelidad visual, build y documentación       | Evidencia de la implementación acordada y CI del PR en verde                     | [fase 7](fase-07-validacion-entrega.md)  |

## Resumen de cada fase

- **Fase 1.** Identificó el contrato y las brechas de datos. Al cerrarla, la BD configurada era antigua y faltaba una
  demo actual de v2. Durante la fase se ejecutó el notebook 10 y se regeneró y validó gold; el
  [informe de actualización](actualizacion-gold-20261104.md) registra el respaldo, los hashes y una diferencia
  mínima de seno/coseno con el archivo antiguo. No se ejecutaron migraciones, entrenamiento ni publicación.
- **Fase 2.** Se preparó una demo local de v2 con el constructor existente del backend y el gold regenerado: una SQLite
  y artefactos nuevos, separados de la base antigua. El informe registra la integración, las verificaciones y sus
  límites.
- **Fase 3.** Paginación completa, comprobación de magnitud regional, alcance de los filtros y vigencia y anticipación
  desde la emisión real. Solo cambió el frontend: sin reentrenar, sin inferencias y sin cambios en la API ni en la base
  de demo.
- **Fase 4.** Selección geográfica, comparación de horizontes, observaciones del corte y series con umbrales históricos
  y rangos configurables, sobre la misma API y demo.
- **Fase 5.** Filtros, historial activo y retirado, orden sobre todas las páginas, detalle por identificador y
  distinción de registros históricos y experimentales.
- **Fase 6.** Métricas por bloque, comparación con persistencia, importancias publicadas y un manual PDF real con
  contenido compartido con la ayuda, sobre la API y la demo de las fases anteriores.
- **Fase 7.** Validación funcional y de accesibilidad, correcciones detectadas y límites de la suite general. El
  frontend y el soporte de CI y arquitectura entraron a `develop` con el PR #31 (`feat/web-dashboard`).

Después de la fase 7 el frontend pasó a usar las demos de v3 y v4; ver [README.md](../README.md).
