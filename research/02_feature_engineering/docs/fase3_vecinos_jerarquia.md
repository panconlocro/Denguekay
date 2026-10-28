# Fase 3 — vecinos y jerarquía

**Estado:** fase 3 ejecutada; la fase 4 ya fue reanudada y documentada en [`fase4_clima.md`](fase4_clima.md). El [notebook 19](../../notebooks/19_fe_vecinos_jerarquia.ipynb) se ejecutó sobre el integrado actual. Las [métricas](metricas/fase3_vecinos_jerarquia.json) y la [figura](figuras/fase3_vecinos_jerarquia/01_asociacion_contexto.png) quedan junto a este informe. No se escribió en `data/gold/`.

## Método

`src/modeling/vecinos_jerarquia.py` toma los 65 UBIGEO del panel, comprueba que provincia y centroide sean constantes por distrito y reutiliza las distancias y los pesos del EDA (`src/eda/espacial.py`). La opción principal conserva los cinco centroides más cercanos de cada distrito, con peso 1/5 y diagonal cero. El cálculo no cruza por nombre de distrito. Se probaron también `k=3`, `k=8`, pesos inversos a distancia dentro de los mismos cinco vecinos y pesos inversos considerando todos los demás distritos.

Para cada semana objetivo `t` y horizonte `h ∈ {2, 4}`, se calculan con observaciones de `t−h`:

- media ponderada de casos y fracción de vecinos con casos positivos;
- casos y fracción de distritos con casos positivos en el **resto de la provincia**;
- casos y fracción de distritos con casos positivos en el **resto del panel regional de Piura**.

El distrito objetivo se excluye de las seis variables espaciales. `>0 casos` es un indicador de actividad, **no** la definición ilustrativa de brote D1 del EDA. Se requiere el panel completo para no crear promedios con distritos ausentes. Como no constan fechas de publicación por observación, se supone provisionalmente que cada caso está disponible al cierre de su semana; el uso operativo debe comprobarlo.

## Hallazgos

1. **La vecindad principal reproduce el alcance geográfico del EDA.** Hay cinco vecinos por distrito y ocho provincias; la mediana de las 325 distancias dirigidas es **19,68 km**, consistente con los 19,7 km del EDA. La distancia de una arista va de 4,95 a 55,89 km. Ningún distrito se incluye a sí mismo.
2. **La cobertura temporal se conserva.** Las 30 485 filas y sus llaves únicas permanecen. Hay 30 355 filas con contexto en `h=2` y 30 225 en `h=4`; las 130 y 260 iniciales, respectivamente, carecen de origen dentro del panel. Las pruebas cambian casos posteriores al origen y confirman que las variables de la fila objetivo permanecen iguales.
3. **Los vecinos muestran asociación descriptiva, menor que la historia propia.** En las filas con origen, la correlación Spearman con los casos objetivo es **0,6207 / 0,6130** para la media de cinco vecinos a 2 / 4 semanas. La historia propia rezagada da **0,7785 / 0,7426**; el resto de la provincia, **0,5703 / 0,5620**; el resto regional, **0,4743 / 0,4688**. Estas cifras mezclan temporadas y niveles distritales y **no prueban aporte incremental** a XGBoost ni contagio entre distritos.
4. **El alcance importa más que cambiar los pesos de los mismos cinco vecinos.** Frente a la media uniforme de cinco, la correlación entre la propia variable y sus alternativas es **0,872** con tres vecinos, **0,888** con ocho, **0,9986** con pesos inversos dentro de los mismos cinco y **0,717** con pesos inversos entre todos los distritos (horizonte 2; horizonte 4 difiere menos de 0,001). Por ello, cinco vecinos uniformes es una opción inicial simple; la elección definitiva requiere ablación temporal.
5. **Ejemplo auditable:** para `ubigeo=200101`, objetivo 2023-S20 (1 527 casos), el origen a cuatro semanas es 2023-S16. Los cinco vecinos tenían **66, 17, 274, 18 y 71** casos y su media es **89,2**. El distrito objetivo tenía 301 casos, excluidos del contexto. Los otros distritos de su provincia sumaban **738** casos; los otros 64 distritos del panel, **1 817**. Ambos totales se recalcularon de forma independiente desde silver.

## Propuesta para las fases siguientes

Conservar como candidatos la media y fracción activa de cinco vecinos, el contexto provincial sin el distrito y la actividad regional sin el distrito. No adoptar una dirección fija de propagación ni interpretar estos agregados como relaciones causales. Comparar cada grupo contra historia propia y calendario mediante ablaciones con cortes temporales cuando se entrene un modelo; las correlaciones retrospectivas de esta fase no bastan para escoger features finales.

Rosa decidió que la alerta identifica cada semana distrital con nivel elevado de casos; sigue abierto el umbral concreto. También están pendientes el calendario 2025-S53/2026, los ceros históricos sin notificación explícita y la disponibilidad efectiva de los casos. Solo se conocen centroides, no polígonos, altitud ni movilidad. La fase 4 trató clima y está documentada por separado.

**Comprobación:** notebook ejecutado sin errores; pruebas sintéticas de ausencia de autocruce, causalidad, cruce de año, integridad geográfica, alternativas de pesos y panel incompleto; verificación independiente del ejemplo real y de las métricas de cobertura.
