# Política de reentrenamiento de la V4

*Criterio operativo, fijado el 17/11/2026. Deriva del protocolo y de los resultados citados abajo; no es un resultado
de un estudio propio.*

## Decisión

La V4 se reentrena **una vez por temporada epidemiológica, al cerrarla**. Reentrenar es **volver a ajustar el mismo
modelo** (misma configuración e hiperparámetros) con los datos nuevos: no es un modelo nuevo ni cambia de versión. La V4
sigue siendo la V4 hasta que se desarrolle otro modelo (otras variables, otra estrategia). Entre un reentrenamiento y el
siguiente el paquete queda fijo. No hay reentrenamiento automático: la actualización semanal
([operación](../backend/operacion.md#actualización-semanal-v4)) nunca ajusta un modelo.

## Cuándo

Cuando el corte no provisional alcanza el cierre de la SE 34 (la temporada va de la SE 35 a la SE 34). La V4 tiene
etiquetas hasta la SE 41 de 2026 (17/10/2026), así que el próximo reentrenamiento corresponde al cierre de la temporada
2027: SE 34 de 2027, que cierra el 28/08/2027 según el calendario MMWR del repo. Como la operación usa la última semana
publicada (`semanas_provisionales: 0`), el corte llega a esa SE cuando la Sala publica la SE 34; por el rezago
con que la Sala traía sus semanas (el 15/11/2026 ya publicaba la SE 44, que cerró el 07/11, y el 12/11 ya tenía la
SE 43, que cerró el 31/10: hasta 8 y 12 días de rezago), la SE 34 de 2027 (cierra el 28/08/2027) estaría entre el 5 y el
9 de setiembre de 2027. Es una estimación con dos observaciones, no una serie. El informe de cada corrida semanal lo avisa con `reentrenamiento_anual_pendiente`
(`denguekay.serving.emissions.retraining_due`, que lee `corte_etiquetas` de la
[ficha de la V4](../../models/registry/v4/ficha.json)).

## Por qué esa cadencia

1. **Es la cadencia que midió el protocolo, no el momento del corte.** Se ajusta un modelo por bloque de temporada,
   con el corte en el primer origen del bloque y fijo durante toda la temporada
   ([protocolo V3, sección 2](protocolo_v3.md)); el estudio 08 repite los 20 bloques con casos confirmados. Esta política
   corta al cierre de la temporada, y la V4 se cortó el 17/10/2026, siete semanas dentro de la temporada 2026–27: ninguno
   de los dos cortes coincide con los de los 20 bloques. Las métricas reportadas **aproximan** esa forma de operar; no la
   describen exactamente.
2. **Los contrastes del estudio 08 comparan ventanas, no frecuencias.** El entrenamiento expansivo elevó el AP a h4
   frente a la ventana móvil de tres años en las cinco temporadas del contraste, y calibrar con toda la historia redujo
   el Brier a h4 en cuatro de cinco; pero con probabilidades crudas el entrenamiento expansivo empeoró el Brier
   ([resultados](../../research/08_v3_confirmed_cases/resultados_historia_calibracion_comun.md)). Además, ese contraste es
   del comparador de historia y geografía sin clima (`historia_geo`), no del modelo principal, y es retrospectivo, con
   cinco temporadas y 2026 entre ellas. Es un indicio de que más historia no perjudica, no una medida del valor de
   agregar una temporada; por eso la decisión de no dejar el modelo fijo indefinidamente es un criterio, no un resultado.
3. **Platt y la mezcla de conteo se ajustan con predicciones fuera de muestra cuya etiqueta ya cerró en el corte**
   ([protocolo V3, sección 2](protocolo_v3.md)); en media temporada hay pocas filas nuevas de ese tipo.
4. **La Sala revisa semanas ya publicadas.** En el cotejo del 15/11/2026 cambiaron 102 conteos de 2026, 61 de ellos en
   la SE 41 o anteriores ([reproducibilidad](../reproducibilidad.md)). Eso sustenta no reentrenar cada semana; la misma
   fuente indica que esas revisiones cambiaron solo dos etiquetas de brote por horizonte, y que el cotejo no las
   desglosa por antigüedad de la semana. Cortar al cierre de la SE 34 no evita las revisiones: con
   `semanas_provisionales: 0` el corte incluye las semanas más recientes, cuyo conteo aún puede cambiar.
5. **La evaluación prospectiva archiva la fecha de emisión, los insumos y los pronósticos antes de conocer los
   desenlaces** ([congelamiento de la V4](../../research/08_v3_confirmed_cases/congelamiento_b3_v4.md)). Mantener el
   mismo modelo durante toda la temporada es una decisión del equipo para que esos pronósticos sean comparables; esa
   fuente no lo afirma.
6. **Un reentrenamiento no cambia de versión, pero debe quedar trazable:** con qué datos (corte y hashes de los insumos) y
   qué boosters resultaron, para que las emisiones archivadas indiquen con qué ajuste se hicieron.

## Alcance de la evidencia

Es un criterio operativo derivado del protocolo y de esos resultados. **Ningún estudio del repo compara frecuencias de
reentrenamiento** (ni a mitad de temporada ni con otra cadencia); no se afirma que la cadencia anual sea la óptima.

## Reentrenamiento extraordinario (revisión manual)

- Cambio en la definición de caso o en la serie que publica la Sala.
- Cambio de versión de CHIRPS, de ERA5-Land o del índice de NOAA.
- Cambio de la regla de brote (obliga a reetiquetar).
- Cambio en el conjunto de distritos.

Un cambio de los umbrales de aceptación **no** requiere reentrenar: se vuelve a publicar
(`python -m denguekay.serving.publish --seleccionar-experimental`).

## Seguimiento

El informe semanal trae, por horizonte, el Brier, los brotes observados frente a la suma de probabilidades y el MAE de
los casos, con su `n`, solo para las emisiones cuya semana objetivo ya tiene observación. Sirve a la revisión anual;
con pocos brotes no dispara nada por sí solo ni se interpreta como una conclusión.

## Cómo

Re-ajustando la configuración congelada de la V4 con los datos hasta el nuevo corte (el protocolo del estudio 08 es la
referencia: [congelamiento de la V4](../../research/08_v3_confirmed_cases/congelamiento_b3_v4.md)). **El procedimiento
aún no está implementado como código** y queda fuera de la actualización semanal. Puntos abiertos para cuando se
implemente:

- El predictor `v4_b3_live` comprueba los boosters contra el manifiesto del Release `model/v4`; los boosters re-ajustados
  necesitan otra forma de registrarse y verificarse.
- El aviso de reentrenamiento lee `corte_etiquetas` de la ficha de la V4; tras re-ajustar, ese corte debe actualizarse o el
  aviso seguiría activo.
- Si se automatiza (por ejemplo, un workflow lanzado a mano) o se deja manual.
