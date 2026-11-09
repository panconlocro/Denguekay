# R09 · Resultados de sensibilidad de la etiqueta V3

Ejecutado el 2026-11-09 en el clon `Denguekay-R09`, desde el tag `model/v3` (`6894012`). El [protocolo aprobado](protocolo.md) define la regla principal y las dos alternativas. Se reutilizaron las predicciones de la V3 con temperatura y del comparador pareado L + 5a sin clima, en las mismas filas, cinco semillas y tres horizontes.

## Resultado principal

**El veredicto de Brier es empate en los tres horizontes bajo las tres definiciones.** El resultado agregado se mantiene y hay sensibilidad por temporada. En particular, con la historia de tres años, la comparación a `h=2` en 2022 pasa de favorecer a la V3 a favorecer al modelo sin clima. Esa inversión cumple el criterio predeclarado de cambio material.

| Escenario | Regla | `h=2` | `h=3` | `h=4` | Celdas favorables / empate / desfavorables entre las 18 de decisión |
|---|---|---|---|---|---|
| Principal | +1,5 DE, 5 años | Empate | Empate | Empate | 13 / 2 / 3 |
| A | +2 DE, 5 años | Empate | Empate | Empate | 12 / 2 / 4 |
| B | +1,5 DE, 3 años | Empate | Empate | Empate | 12 / 1 / 5 |

El veredicto aplica la regla `SEASON_2026` a 2010, 2015, 2016, 2022, 2023 y 2026. Los tres escenarios alcanzan el mínimo de semanas elevadas en 2026 y conservan las seis temporadas en cada horizonte. El empate expresa el resultado de esa regla y del rango entre semillas.

## Cambios por temporada

Las cuatro transiciones en las celdas de decisión ocurren en 2022. `ΔBrier` es la mediana de V3 menos la mediana del comparador sin clima. Un valor negativo favorece a V3 cuando su magnitud supera la tolerancia de la celda.

| Alternativa | Horizonte | Lectura principal | Lectura alternativa | ΔBrier principal | ΔBrier alternativo | Tolerancia alternativa |
|---|---:|---|---|---:|---:|---:|
| A | 2 | Favorable | Empate | −0,000337 | −0,000076 | 0,000295 |
| A | 3 | Empate | Desfavorable | +0,000067 | +0,000448 | 0,000294 |
| B | 2 | Favorable | Desfavorable | −0,000337 | +0,000476 | 0,000255 |
| B | 3 | Empate | Desfavorable | +0,000067 | +0,000519 | 0,000317 |

En `h=4`, las lecturas de las seis temporadas permanecen iguales entre escenarios. En la temporada 2026, el Brier favorece a V3 en `h=2`, `h=3` y `h=4` bajo las tres definiciones. En `h=4` de esa temporada, `ΔBrier` es −0,000889 en el principal, −0,000697 en A y −0,000962 en B. Las seis temporadas, incluida 2026, forman parte de la evaluación retrospectiva de desarrollo.

## Cambios en la etiqueta

En las 20 410 filas objetivo de `h=4` de las seis temporadas de decisión se observó lo siguiente.

| Escenario | Semanas elevadas | Prevalencia | Cambios frente al principal | Pasa a positiva | Pasa a negativa |
|---|---:|---:|---:|---:|---:|
| Principal | 2 745 | 13,45 % | 0 | 0 | 0 |
| A | 2 604 | 12,76 % | 141 | 0 | 141 |
| B | 2 991 | 14,65 % | 468 | 357 | 111 |

Estos conteos representan semanas distrito que cambian de etiqueta bajo otra regla. B cambia etiquetas en ambos sentidos, como cabe esperar de una referencia histórica que puede subir o bajar por distrito y semana. La comparación predictiva se hace entre modelos dentro de cada escenario y sobre las mismas filas.

## Comprobaciones y alcance

- Great Expectations aprobó las **107 expectativas** del silver integrado.
- El principal reprodujo los Brier y *average precision* de las **570 celdas** archivadas. Las etiquetas y los umbrales coincidieron. La diferencia absoluta máxima de la probabilidad calibrada tras reajustar Platt fue `1,89e-15`.
- Los MAE, RMSE y sus razones frente a persistencia coincidieron exactamente entre escenarios al reutilizar los conteos publicados.
- `temporada_2008` se conserva para calibrar los bloques siguientes y se presenta sin métricas de probabilidad calibrada. Para la antelación se aplica el emparejamiento de la V3 en las filas con probabilidad calibrada. La guarda de decisión usa la semilla 17 y la antelación nominal del protocolo.
- Pasaron 3 pruebas del estudio y 18 pruebas existentes de umbral y protocolo. Se omitieron 4 comprobaciones de integración que requieren archivos gold ajenos a los insumos de este análisis.

La sensibilidad se interpreta condicionada a la configuración seleccionada bajo la etiqueta principal. Los resultados respaldan la estabilidad del veredicto agregado y muestran dependencia de la definición en comparaciones por temporada. El rango entre semillas es la tolerancia de lectura del protocolo.

## Redacción para el manuscrito

> We assessed sensitivity to the elevated-week definition using a 2.0 SD multiplier with five reference years and a three-year reference window with a 1.5 SD multiplier. Both analyses reused the frozen V3 and matched no-weather count forecasts and refitted the chronological probability calibration. The aggregate Brier comparison was a tie at all three horizons under all definitions. Season-specific comparisons were sensitive to the definition. In 2022 at the two-week horizon, the three-year reference reversed the comparison in favor of the no-weather model. At the four-week horizon, the cell classifications for the six deciding seasons were unchanged across definitions.

## Archivos y reproducción

- [Resultados por escenario, semilla, horizonte y bloque](metricas/r09.json).
- [Control de reproducción del principal](metricas/reproduccion_principal.json).
- [Registro de ejecución y run de MLflow](metricas/ejecucion.json).

Desde la raíz del clon, con los paquetes del Release verificados y el entorno de Python instalado:

```bash
.venv/bin/python -B research/07_outbreak_label_sensitivity/code/run_sensitivity.py
.venv/bin/python -B -m unittest discover -s research/07_outbreak_label_sensitivity/tests
```
