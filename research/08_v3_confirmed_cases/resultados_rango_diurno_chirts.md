# Rango diurno de CHIRTS en el pronóstico semanal de dengue

Se evaluó si añadir la diferencia diaria entre la máxima y la mínima mejora el pronóstico distrital cuando el modelo ya conoce el punto medio de esos dos extremos. Los experimentos entomológicos motivan examinar la amplitud térmica por separado del nivel de temperatura. Este contraste mide el aporte predictivo de una exposición semanal agregada en Piura. [Lambrechts et al., 2011](https://doi.org/10.1073/pnas.1101377108) · [Protocolo](protocolo_rango_diurno_chirts.md)

Se usó CHIRTS a 0,05° ponderado por población y se preservaron lluvia CHIRPS, humedad ERA5, Niño 1+2, geografía, historia de casos e hiperparámetros. Los dos brazos nuevos tienen el mismo soporte de **73 905 orígenes climáticos**. Cada combinación de brazo y semilla conserva **194 805 pronósticos** de los mismos 20 bloques, incluidos 2008 como historial inicial de calibración y el bloque parcial posterior a la temporada 2026. Great Expectations validó silver y gold. Se verificaron las llaves, etiquetas y filas de calibración contra la corrida archivada. [Comparación de resolución](resultado_resolucion_chirts.md)

## Resultados

Las cifras son cambios relativos de Brier. Un cambio positivo indica mayor error probabilístico. Se toma la mediana de las diferencias pareadas de las cinco semillas por temporada y se da igual peso a las seis temporadas de decisión del estudio. El contraste principal a h4 está en la primera fila.

| Contraste | h2 | h3 | h4 | h4 sin 2026 |
|---|---:|---:|---:|---:|
| Punto medio y rango frente a punto medio | +0,27% | +0,49% | +0,71% | +0,25% |
| Punto medio y rango frente a máxima y mínima | −0,03% | +0,33% | +0,42% | +0,50% |
| Punto medio frente al mismo modelo sin temperatura | −0,98% | −1,03% | −0,99% | −0,59% |

A h4, añadir el rango mejoró el Brier en **una de seis temporadas** y elevó el Brier absoluto promedio en **0,00023**. La precisión promedio (AP) bajó **0,36 puntos porcentuales**. En 2026 el Brier aumentó 3,01%. El aumento promedio se conserva al retirar esa temporada y también se observa por separado en los bloques de contraste de 2024 (+0,08%) y 2025 (+0,62%). La comparación entre punto medio y rango frente a máxima y mínima utiliza dos representaciones equivalentes de los mismos datos. La diferencia mide cómo los árboles usan esas variables.

El punto medio aporta una mejora pequeña sobre el bloque con lluvia, humedad y Niño 1+2, en cinco de seis temporadas a h4. El comparador de esa tercera fila ya incluye clima. El contraste principal de aporte climático frente a historia y geografía se reporta en su análisis propio. En este diseño retrospectivo, la evidencia permite conservar el rango diurno como sensibilidad y favorece mantener la especificación principal del paper. [Controles espaciales y ajuste simétrico](resultados_controles_espaciales.md)

## Cotejo meteorológico y alcance

En los siete días del 12 al 18 de marzo de 2023, el rango diario medio derivado de la celda CHIRTS cotejada fue **7,77 °C frente a 9,49 °C** en la estación de Piura y **3,76 °C frente a 10,72 °C** en Talara. Se usaron los pares Tmax y Tmin de la comparación NOAA GSOD archivada. El cotejo cubre dos estaciones costeras y una semana. Las convenciones horarias de los extremos diarios pueden contribuir a las diferencias. El rango del reanálisis describe una estimación agregada de exposición y su verificación en sierra y para la humedad sigue limitada. Los resultados predictivos se restringen a la fuente, el rezago, la ventana y los cortes estudiados. [Cotejo de fuentes y estaciones](comparacion_fuentes_clima.md)

## Reproducción

Las predicciones, los contrastes por semilla y temporada, las sensibilidades por exclusión y el manifiesto se guardaron en `models/experimentos/mejora_modelo/v3_confirmados/piloto_clima/resolucion_chirts/historico/sensibilidad_rango_diurno/`. Corrida MLflow `9db8039a91204a698c2ff249997f0572`.

```bash
DENGUEKAY_XGB_DEVICE=cpu DENGUEKAY_XGB_NJOBS=2 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 OMP_NUM_THREADS=2 \
  .venv/bin/python -B research/08_v3_confirmed_cases/code/evaluate_diurnal_range.py
```
