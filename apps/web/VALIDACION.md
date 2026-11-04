# Validación de la primera entrega

Comprobación local del 04/11/2026 en macOS arm64, Node.js 20.19 y Python 3.12.
La implementación se limita a apps/web. No se cambiaron la API, el modelo, las fuentes ni las fixtures.

| Comprobación                                  | Resultado                                  |
| --------------------------------------------- | ------------------------------------------ |
| Build de producción y TypeScript              | Aprobado                                   |
| ESLint y formato                              | Aprobados                                  |
| Vitest                                        | 9 pruebas aprobadas                        |
| Playwright con FastAPI real y SQLite temporal | 8 recorridos aprobados, escritorio y móvil |
| Guardas de estructura y contrato OpenAPI      | 9 pruebas aprobadas                        |
| Humo de Uvicorn y contrato v1                 | Aprobado al habilitar el puerto local      |
| Auditoría npm al instalar el lockfile         | 0 vulnerabilidades detectadas              |

Los recorridos comprueban filtros geográficos, navegación al distrito, separación de ceros y faltantes,
horizonte sin modelo, rechazo de resultados anteriores tras 503, reintento, avisos, assets y ausencia de
desbordamiento horizontal a 1440 y 390 px. Las capturas se revisaron frente al diseño de Figma.
La API temporal usa las fixtures reales del backend (v0, h=2 y h=4). No certifica el contenido de una BD
de producción ni reemplaza una prueba de integración del modelo v2 publicado por Rosa.

## Suite general del repositorio

También se ejecutó la suite Python completa: 465 pruebas, 2 fallos, 7 errores y 32 omitidas.
No se presenta como una validación completa en verde:

- Tres errores son importaciones de Optuna, que falta en el entorno Python local.
- Tres errores de subpruebas B3 y un fallo de esquema corresponden al gold local: contiene 48 columnas
  y no las 20 del contrato actual, incluidas las tres B3 requeridas. Se confirmó en la prueba específica.
- La guarda de predicciones congeladas en CPU produjo huellas diferentes a su línea base.
  No se regeneró ni modificó la línea base para hacerla pasar.
- Un error de humo se debió al bloqueo de puertos del sandbox. La misma prueba pasó al repetirla con
  el permiso para abrir su servidor local.

La suite completa se ejecutó antes de preparar el commit final. Después de añadir el frontend al índice,
las guardas de estructura y contrato se repitieron y pasaron. No se alteraron las guardas para admitir
el frontend. La suite general necesita resolver los puntos de entorno/datos anteriores antes de un PR
con validación local completa; PostgreSQL requiere su BD desechable y el CI del proyecto.

## Alcance pendiente

La primera entrega termina en tablero y navegación con versiones funcionales iniciales de las demás
vistas. El README detalla lo pendiente: métricas e importancias completas, rangos personalizados,
polígonos publicables, serie regional, incidencia, manual PDF y soporte. También siguen pendientes los
problemas de backend señalados en la revisión previa y los cambios de soporte de CI/arquitectura.

## Actualización posterior de gold

Por solicitud expresa del usuario se ejecutó el notebook 10 después de esta validación inicial.
El [informe de regeneración](docs/actualizacion-gold-20261104.md) registra el gold de 20 columnas,
Great Expectations aprobado y B3 verificada. El problema de esquema antiguo de gold descrito arriba
ya no representa su estado actual. Permanece una diferencia de igualdad exacta en seno/coseno
respecto al respaldo, medida en 1,11e-16. No se repitió la suite Python completa ni se afirma que esté
en verde. La BD operacional y la selección del servidor de vista previa no cambiaron.
