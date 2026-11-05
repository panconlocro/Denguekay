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

## Fase 2: integración posterior con la demo local v2

Por elección expresa del usuario se preparó una base nueva de demo v2 con el constructor existente,
sin migrar la base antigua. La vista previa ahora usa esa API en modo de lectura, con una banda de
procedencia y comprobación de versiones. Corte: 27/12/2025; 65 distritos por horizonte, h=2, 3 y 4.

Pasaron 12 pruebas unitarias, ESLint, TypeScript, build y formato. Playwright aprobó 4 recorridos
con v2 y 8 con fixtures, ambos perfiles en escritorio y móvil. También se comprobaron 39 respuestas
HTTP, los hashes de los artefactos y el rechazo de escrituras en la demo. Las capturas de escritorio
y móvil se inspeccionaron. Las 9 guardas de estructura y contrato OpenAPI pasaron tras preparar los
archivos en el índice. Great Expectations de la publicación: 107/107 en silver y 42/42 en gold.
El [informe de fase 2](docs/fase-02-integracion-demo-v2.md) contiene cifras y evidencia local.

No se repitió la suite Python completa y no se afirma que esté en verde. Persisten los límites de
entorno y equivalencia ya documentados. No se registró un modelo final en MLflow ni se desplegó.

## Fase 3: tablero

El 05/11/2026 pasaron 18 pruebas unitarias, ESLint, TypeScript, build y 20 recorridos de navegador:
12 con v2 y 8 con fixtures, en escritorio y móvil. Cubren paginación de los 65 distritos, filtros con
indicadores regionales estables, magnitud parcial, conteos ausentes, anticipación, URLs inválidas y
errores por consulta con recuperación. Los datos alterados de esos escenarios solo existen en el
navegador de pruebas; no se cambió la demo. La comprobación de dimensiones del mapa y de los assets
visibles pasó al repetir el recorrido principal después del ajuste visual; capturas inspeccionadas.

Great Expectations al iniciar la fase: silver 107/107, gold 42/42. Los hashes de datos y bases
verificados en fase 2 permanecen iguales. El [informe del tablero](docs/fase-03-tablero.md) documenta
la implementación y sus límites. No se entrenó ni se modificó la API. La suite Python completa sigue
pendiente por las incidencias registradas anteriormente.

## Fase 4: mapa y detalle

El 05/11/2026 pasaron 27 pruebas unitarias, ESLint, TypeScript, build, formato y 36 recorridos en
navegador: 20 con v2 y 16 con fixtures. Cubren mapa → panel → detalle, selección de marcador con
teclado y foco estable, horizontes, intervalos, umbral histórico, rangos de 26/52 semanas y fechas
personalizadas, recarga, ausencia de datos y recuperación de errores. Las capturas de escritorio y
móvil se inspeccionaron frente a los nodos Figma de mapa y detalle.

Pasaron las 9 guardas de estructura y contrato OpenAPI con los archivos preparados en el índice.

Great Expectations al iniciar la fase: silver 107/107 y gold 42/42. Los hashes de datos y bases
permanecen iguales a los comprobados en fase 2. No se entrenó ni se modificó la API. El
[informe de fase 4](docs/fase-04-mapa-y-detalle.md) registra el alcance y los límites. La suite Python
general mantiene sus incidencias documentadas; esta fase no certifica toda la suite en verde.

## Fase 5: avisos

El 05/11/2026 pasaron 34 pruebas unitarias, ESLint, TypeScript, build y 52 recorridos de navegador:
28 con v2 y 24 con fixtures. Cubren historial activo/retirado, paginación completa, orden, filtros,
detalle, fechas ausentes, enlace directo desalineado, recuperación y regresiones de fases anteriores.
Tras ajustar la presentación móvil se repitió el módulo de avisos en ambos perfiles, con capturas
inspeccionadas y comprobación de ausencia de recorte horizontal en la ficha móvil.

Great Expectations al iniciar la fase: silver 107/107 y gold 42/42. Los hashes de datos y bases se
mantienen iguales. La demo conserva sus cero avisos reales; los registros masivos solo se inyectan
en respuestas del navegador de pruebas. El [informe de fase 5](docs/fase-05-avisos.md) recoge las
limitaciones. No se reentrenó v2 ni se modificó la API. La suite Python completa sigue pendiente por
las incidencias ya documentadas.

Pasaron las 9 guardas de estructura y contrato OpenAPI con los archivos nuevos preparados en el índice.

## Fase 6: desempeño y ayuda

La fase 6 añade métricas por bloque, comparación con persistencia, importancias originales y
trazabilidad por versión. Ayuda incluye búsqueda, leyenda del servicio y un PDF real de cuatro
páginas, generado desde el mismo contenido de la interfaz.

Pasaron 39 pruebas unitarias, ESLint, TypeScript, build y formato. Playwright aprobó 40 recorridos
con la demo v2 y 36 con fixtures v0 (76 en total, escritorio y móvil). Se revisaron capturas de ambas
vistas y las cuatro páginas del manual. Los casos sintéticos solo alteran respuestas interceptadas
en pruebas; los datos de la demo permanecen de lectura. El perfil v2 completo pasó con dos workers
tras un agotamiento de tiempo al iniciar un contexto de Chrome con seis.

Se corrigió el estado de desempeño de un horizonte sin modelo y se comprobó su salida hacia otro
horizonte disponible. Las 9 guardas de estructura y contrato OpenAPI pasaron con los nuevos archivos
preparados en el índice.

La validación inicial de entradas aprobó silver 107/107 y gold h2 42/42, 30 485 filas cada uno.
Los hashes de las dos bases, gold y silver permanecen iguales a fase 2. No se repitió la suite
Python completa ni el CI; la validación de entrega de fase 7 espera revisión del usuario.
El [cierre de fase 6](docs/fase-06-desempeno-y-ayuda.md) describe fuentes y evidencia.
