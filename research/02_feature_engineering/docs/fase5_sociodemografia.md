# Fase 5 — sociodemografía y población

**Estado:** ejecutada y ampliada con demografía anual. El [notebook 21](../../notebooks/21_fe_sociodemografia.ipynb), las [métricas](metricas/fase5_sociodemografia.json) y la [figura](figuras/fase5_sociodemografia/01_ablacion_sociodemografia.png) reproducen el análisis. Esta fase no escribió en `data/gold/`; la integración posterior se documenta en [fase 6](fase6_integracion.md).

## Linaje y disponibilidad

`src/processing/socio_interpolacion.py` carga `pob_censada_2017` para 2017, usa `pob_proyectada_2018`…`pob_proyectada_2025` en los demás años y crea las 15 fracciones de 2018–2024 como rectas entre 2017 y 2025. Cada estimación anual se repite en todas las semanas de ese año. **Esta construcción es útil para actualizar el dataset con la mejor estimación disponible hoy.** La limitación se refiere a simular pronósticos emitidos antes de conocer el extremo de 2025: las fracciones interpoladas no estaban disponibles entonces. Rosa decidió ensayar su inclusión como reconstrucción retrospectiva y documentar esa anticipación de información. La fecha y versión de publicación de cada proyección anual del Excel local no constan. Si se asigna el valor del año objetivo a un pronóstico originado en el año anterior, también hay que comprobar que esa proyección estuviera disponible en el origen; aquí no se comprobó. Una columna calculada con información futura no se arregla con un simple `shift(h)`.

La [referencia de 2017](../../src/modeling/sociodemografia.py) extrae una fila por UBIGEO del panel. Se comprobó de forma independiente que `poblacion` y las **15 fracciones** coinciden exactamente con `pob_censada_2017` y las columnas `_2017` del Excel bronze en los **65 distritos** (desvío máximo **0**). La población y las fracciones son constantes entre las semanas de 2017. En la comparación fija, el rasgo poblacional es `log_poblacion_censo_2017`; no equivale a población actual ni a un offset o tasa.

El INEI anunció el acceso público a la base detallada del censo 2017 el **14 de septiembre de 2018** ([comunicado oficial](https://censo2017.inei.gob.pe/sistema-de-consulta-de-la-base-de-datos-de-los-censos-nacionales-se-publican-en-la-web-de-celadecepal/)). Como la fecha de publicación de los valores **derivados del Excel local** no está registrada, esta prueba adopta **2019-01-01** como barrera conservadora, **no** como fecha comprobada para ese archivo. Para **simular un pronóstico histórico**, `construir_sociodemografia` deja `NaN` si su origen `t−h` es anterior: así quedan 23 595 filas elegibles en `h=2` y 23 465 en `h=4`; las primeras fechas objetivo elegibles son 2019-01-13 y 2019-01-27. **Esa restricción no elimina etiquetas de 2017–2018 del entrenamiento realizado en un corte posterior**: cuando se ajusta el modelo antes de probar 2022, ya se conocen tanto esos casos como la referencia censal de 2017. La ablación conserva esos ejemplos y exige la disponibilidad censal solo en los orígenes de prueba. La fecha exacta de disponibilidad debe verificarse antes de evaluar pronósticos emitidos en años más antiguos.

## Representaciones fijas y anuales

Se probaron dos representaciones fijas de 2017:

1. **Tres fracciones interpretables:** `fraccion_rural`, `fraccion_menores_15` y `fraccion_desague_red`. Representan asentamiento, composición etaria y servicio de saneamiento. Se eligieron antes de mirar los resultados de la ablación; pueden estar correlacionadas y no se interpretan causalmente.
2. **Eje urbano CP1:** `ajustar_eje_urbano` estandariza las 15 fracciones y ajusta PCA **solo sobre distritos con filas de entrenamiento disponibles** en cada corte. El signo se fija para que refrigeradora sea positivo. En el panel actual los 65 distritos aparecen en todos los entrenamientos, por eso los ocho ajustes explican la misma proporción, **61,336 %**, que reproduce el **61,3 %** del EDA. Esto describe variación transversal, no poder predictivo. Si en otro estudio se separan distritos de train y test, la prueba sintética comprueba que los distritos retenidos no influyen en el ajuste.

No se incorporaron al dataset gold las 15 fracciones ni un puntaje CP1 ajustado globalmente. El puntaje debe recalcularse dentro de cada fold del modelado; incluir uno único antes de decidir la partición impediría auditar ese ajuste.

La ampliación de fase 5 compara también **población anual proyectada**, **tres fracciones anuales**, **las 15 fracciones anuales** y un **eje urbano anual**. La función `construir_sociodemografia_anual` verifica que cada variable sea constante dentro de `(ubigeo, anio)`, calcula `log_poblacion_anual` y transforma las fracciones de cada año con la **misma media, desviación y cargas** del PCA ajustado en 2017 con distritos de entrenamiento. Por tanto, hay **un puntaje por distrito y año**, copiado en sus semanas; la definición del eje no cambia de año en año. La función devuelve 17 candidatas anuales (15 fracciones, población logarítmica y eje), pero las ablaciones las comparan en bloques separados; no se añaden todas simultáneamente por defecto.

## Ablación temporal exploratoria

Se usaron temporadas completas **2022–2025** y horizontes **2 y 4 semanas**. Cada fold entrena una regresión ridge fija con `log1p(casos_Dengue)` hasta el primer origen de prueba y evalúa 3 380 distrito-semanas. **Las etiquetas históricas de 2017–2018 permanecen en entrenamiento**, aunque sus filas no se evalúen como pronósticos emitidos en esos años. Todas las variantes comparten las mismas filas de cada fold. La base tiene casos propios rezagados, media de cuatro semanas y calendario; se añadieron por separado población 2017, tres fracciones, CP1 y población + CP1. También se comparó población + CP1 **sobre una base con anomalías de humedad y precipitación**. La persistencia en `t−h` sirve de referencia. Ni ridge ni estos cortes fijan el modelo XGBoost o el test final.

| Variante añadida a historia + calendario | Cortes con menor MAE de casos | Mayor mejora | Mayor empeoramiento |
|---|---:|---:|---:|
| Población 2017 | 6/8 | −0,054 (h=4, 2024) | +0,039 (h=2, 2023) |
| Tres fracciones 2017 | 4/8 | −0,027 (h=4, 2024) | +0,035 (h=2, 2023) |
| CP1 2017 | 5/8 | −0,037 (h=4, 2024) | +0,017 (h=2, 2023) |
| Población + CP1 | 5/8 | −0,075 (h=4, 2024) | +0,047 (h=2, 2023) |

Sobre la base que también incluye clima, población + CP1 mejora **4/8** cortes, con la mayor ganancia en `h=4`, temporada 2024 (**−0,078 MAE**) y el mayor empeoramiento en `h=2`, temporada 2023 (**+0,049**). Los cambios son pequeños frente al MAE de varias unidades o decenas de casos de las temporadas activas. La temporada 2025 es válida como fuente epidemiológica, pero su bajo nivel produce mejoras de milésimas; no debe dominar la decisión por contar cortes positivos. El [JSON](metricas/fase5_sociodemografia.json) conserva MAE en casos y en `log1p`, tamaños de entrenamiento y fechas de corte.

### Comparación anual reconstruida

Las variantes anuales usan **los mismos 8 folds, filas y modelo ridge** que las fijas. Cada delta es MAE de la variante menos MAE de historia + calendario, excepto la última fila, que usa historia + calendario + clima como base.

| Variante anual añadida | Cortes con menor MAE de casos | Mayor mejora | Mayor empeoramiento |
|---|---:|---:|---:|
| Población anual | 6/8 | −0,056 (h=4, 2024) | +0,028 (h=2, 2023) |
| Tres fracciones anuales | 3/8 | −0,020 (h=4, 2024) | +0,022 (h=2, 2023) |
| CP1 anual | 4/8 | −0,030 (h=4, 2024) | +0,018 (h=2, 2023) |
| Las 15 fracciones anuales | 2/8 | −0,018 (h=2, 2024) | +0,071 (h=2, 2023) |
| Población + CP1 anual | 5/8 | −0,072 (h=4, 2024) | +0,038 (h=2, 2023) |
| Población + CP1 anual sobre clima | 3/8 | −0,079 (h=4, 2024) | +0,033 (h=2, 2023) |

Los ocho ajustes de PCA usan la referencia de 2017 del fold; así se evita que las fracciones de las temporadas de prueba cambien la definición del eje. **Esto no elimina la anticipación de información que ya existe en la serie interpolada**, ni convierte sus métricas en una validación de pronósticos que se hubieran podido emitir en 2022–2024. Los resultados solo muestran cómo rinden estas representaciones sobre el panel reconstruido hoy. Las 15 fracciones juntas no aportaron mejora estable en ridge; con XGBoost podría cambiar, por lo que siguen como candidatas de experimentación y no como conjunto elegido.

**Comprobación cruzada con la fase 4:** los modelos de persistencia, historia + calendario e historia + calendario + clima tienen exactamente los mismos MAE y tamaños de entrenamiento en ambos análisis. El primer fold usa **15 340** filas de entrenamiento para `h=2` y **15 080** para `h=4`. La corrección evita atribuir a la sociodemografía un efecto que en realidad se debía a excluir la temporada 2017 del entrenamiento.

## Decisión propuesta y límites

Mantener la población anual y una representación social pequeña **como candidatas**, junto a la referencia fija de 2017 para medir sensibilidad, sin imponerlas aún al XGBoost. La opción interpretable de tres fracciones no mostró mejora estable; CP1 reduce colinealidad pero exige ajuste por fold y tampoco mejoró de modo consistente. La señal social del EDA separa sobre todo zonas frías y cálidas y puede reflejar diferencias de notificación. En esta ablación, la historia reciente del distrito sigue siendo el punto de partida.

Para la integración posterior conviene conservar la referencia censal y su fecha de disponibilidad de forma explícita; cualquier rasgo dependiente de PCA debe transformarse dentro del entrenamiento. La población anual **estimada** es pertinente para un pronóstico operativo: se asigna el mismo valor a todas las semanas del año correspondiente y se actualiza cuando aparece una nueva fuente. Para interpretarla como exposición, tasa o peso y evaluarla sin fuga histórica, conviene documentar qué proyección o censo se conocía en cada origen y revisar el salto entre 2017 y 2018. Siguen abiertos el umbral de alerta elevada, el test definitivo y la disponibilidad operacional de casos y clima.

**Comprobación:** notebook ejecutado con validación de silver y cobertura; cruce independiente con las 16 columnas originales de 2017; pruebas de invariancia ante cambios de años posteriores para la referencia fija, repetición anual por semanas, constancia distrital anual, disponibilidad por origen para `h=2/4`, uso retrospectivo de etiquetas en entrenamiento, PCA sin distritos de prueba, errores de referencia y unicidad. Pasaron las **96 pruebas** del repositorio. La refactorización del ridge diagnóstico preservó exactamente las 24 métricas de la fase 4.
