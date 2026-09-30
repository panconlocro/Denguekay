# Fase 6 — integración y calidad de gold

**Estado:** ejecutada. Rosa autorizó esta fase. El [notebook 22](../../notebooks/22_fe_integracion.ipynb) genera los dos CSV locales de `data/gold/`; el [manifiesto local](../../data/gold/manifest_fase6.json) registra hashes de silver, cobertura y salidas. Esos datos se ignoran en Git y se regeneran con `src/modeling/features.py`. El traspaso posterior está en [fase 7](fase7_sintesis_traspaso.md).

## Contrato de salida

La entrada es `data/silver/integrado/meteo_socio_epi_piura_2017_2025.csv` con su `.coverage.csv`. Antes de construir variables se ejecutan `cargar_integrado()` y `validate_complete()`. El integrado actual tiene **30 485 filas**, **65 distritos**, **469 semanas por distrito**, **35 columnas** y llaves `(ubigeo, anio, semana)` únicas. Cada fila gold sigue representando la **semana objetivo** `t`; el origen de `h=2` o `h=4` es el cierre de `t−h`. Se conserva `casos_Dengue` como conteo y se añade `brote` como etiqueta binaria de semana elevada.

| Salida local | Filas | Columnas | Filas con todas las ventanas observadas | Filas iniciales con nulos esperados |
|---|---:|---:|---:|---:|
| `meteo_socio_epi_piura_2017_2025_h2_gold.csv` | 30 485 | 48 | 30 095 | 390 (6 por distrito) |
| `meteo_socio_epi_piura_2017_2025_h4_gold.csv` | 30 485 | 48 | 29 965 | 520 (8 por distrito) |

Los nulos corresponden a rezagos o ventanas que comienzan antes de 2017-01-01. Se conservan sin imputar para mostrar la cobertura original; una matriz de entrenamiento que exija todas las ventanas observadas seleccionará las filas completas de su horizonte. El gold no impone todavía qué años se usarán para entrenamiento o prueba. Los CSV mantienen `ubigeo` como texto y la semana objetivo con su `semana_inicio` de domingo.

## Familias integradas

- **Historia y calendario:** casos propios en `t−h` y `t−h−1`, media y número de semanas con casos en las cuatro semanas que terminan en `t−h`, más seno y coseno de la semana objetivo. `origen_inicio` y `origen_cierre` se conservan para auditar disponibilidad.
- **Contexto geográfico:** media y fracción activa de cinco vecinos por centroides, casos y fracción activa del resto de la provincia, y casos y fracción activa del resto de la región; todos observados en `t−h`, sin el propio distrito.
- **Clima observado:** medias de cinco semanas de `hum_rel_media` y `precip_total_mm`, terminadas en `t−h`. No se copia el clima de la semana objetivo ni `lluvia_total_mm`, redundante con precipitación.
- **Demografía:** logaritmo de la población censal de 2017 y tres fracciones fijas de ese censo; logaritmo de la población **anual** y las **15 fracciones anuales** del silver. Son candidatos para experimentar, no una selección conjunta obligatoria. Las dos marcas `socio_2017_disponible_al_origen` y `socio_fracciones_interpoladas_con_2025` son **metadatos de auditoría, no predictores**.
- **Etiqueta:** `brote=1` si los casos de la semana objetivo superan estrictamente la media de su misma semana epidemiológica en los **cinco años anteriores** más **1,5 desviaciones estándar muestrales** y hay al menos **2 casos**; en caso contrario `brote=0`. `umbral_brote_casos` conserva el valor usado para auditar la marca. La semana 53 se suma a la 52 solo en la referencia histórica. Rosa eligió el multiplicador 1,5; el mínimo de 2 es provisional tras revisar la sensibilidad. Ambos campos son **objetivo/metadato y no predictores**.

La etiqueta se calcula con `src/modeling/etiqueta_brote.py` una vez por llave y se anexa idéntica a los dos horizontes. Para 2017–2021 se completan los cinco años previos con `data/silver/epi_piura_semanal.csv` (2012–2016), sin consultar años posteriores a la semana objetivo. Ese Excel es disperso: una ausencia se interpreta como cero, igual que en el canal exploratorio del EDA, pero **no demuestra que se notificó cero**. Con mínimo 1, **742 de las 3 744 semanas positivas** tienen exactamente un caso; con el mínimo provisional de 2 quedan **3 002 semanas positivas** en 2017–2025. Los conteos por año y los hashes de las fuentes están en el manifiesto. El contraste de definiciones está en [`revision_definicion_brote.md`](revision_definicion_brote.md).

No se escriben anomalías climáticas ni eje PCA preajustados sobre todos los años. `ajustar_climatologia()` y `ajustar_eje_urbano()` deben aprenderse con el entrenamiento de **cada fold** antes de transformar ese fold; publicar una única versión global utilizaría información del periodo de prueba. El gold tampoco convierte `ubigeo` en variable numérica continua. La fase de modelado elegirá entre candidatos y construirá su matriz con un esquema explícito de columnas.

## Validación y reproducibilidad

`construir_gold()` reutiliza los módulos de las fases 2–5 y la etiqueta de brote. Cada cruce exige llaves únicas, la misma cantidad de filas, fecha objetivo idéntica y ausencia de columnas repetidas. `validar_gold()` comprueba llaves, conteo igual a silver, coherencia de `brote` con sus casos y umbral, fechas de origen, finitud numérica y que los únicos nulos de las variables causales sean los del arranque de cada serie. El notebook vuelve a cargar y valida los dos CSV persistidos. Para `ubigeo=200101`, 2025-S52 en `h=4`, confirmó `casos_lag_4=1` y `origen_cierre=2025-11-29`, tal como se auditó en fase 2.

Los CSV y el manifiesto se generan después de validar ambos horizontes. La segunda ejecución sobre el mismo silver y la misma regla produjo **hashes idénticos** para ambos CSV y un manifiesto idéntico. Pasaron las **104 pruebas** del repositorio, incluidas pruebas de referencia histórica causal, semana 53, etiqueta alterada, valores, cambio de casos/clima posteriores al origen, llaves, nulos inesperados, escritura repetida y fallo de la fuente sin archivo final.

## Límites y siguientes decisiones

1. **La etiqueta está definida para experimentar, no validada como alerta operativa.** Rosa eligió media + 1,5 DE. El mínimo provisional de 2 casos se recomendó a partir de la sensibilidad local; el equipo debe revisarlo. Un umbral histórico igual a cero puede convertir dos casos en positivos. `brote` y `umbral_brote_casos` deben excluirse de la matriz predictora. La etiqueta de la semana objetivo se conoce solo después de observar sus casos; las features siguen limitadas al origen `t−h`.
2. **La demografía anual es una reconstrucción retrospectiva.** Las fracciones de 2018–2024 usan el extremo de 2025; la población de 2018–2025 procede de proyecciones cuya fecha y versión de publicación no constan. Por decisión de Rosa se conservan como candidatas, con esta limitación visible. `socio_2017_disponible_al_origen` utiliza 2019-01-01 como barrera conservadora supuesta, no como fecha verificada del Excel. Los rasgos fijos de 2017 se conservan también en filas anteriores para permitir entrenamiento retrospectivo después de conocido el censo; esa marca debe respetarse al simular pronósticos históricos.
3. **La latencia real de casos y clima no está documentada.** Las features de historia, vecinos y clima usan semanas terminadas en `t−h` bajo la hipótesis de disponibilidad al cierre semanal. Si la publicación tarda más, hay que desplazar ese límite.
4. **El calendario de 2025-S53/2026, el significado de ceros sin notificación y el corte final de prueba siguen abiertos.** El gold reproduce las semanas presentes del silver y no inventa filas para la semana 53.

Para regenerar desde la raíz del repositorio:

```bash
.venv/bin/jupyter nbconvert --to notebook --execute --inplace notebooks/22_fe_integracion.ipynb
```

Como entrada programática se puede llamar `generar_gold(SILVER_INTEGRADO, GOLD, brote=ConfiguracionBroteEstacional(multiplicador=1.5, anios_previos=5, minimo_casos=2))` desde `src.modeling.features`, importando la configuración de `src.modeling.etiqueta_brote`. Ambos métodos validan la cobertura del integrado antes de escribir.
