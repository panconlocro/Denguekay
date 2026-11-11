# Conteo esperado de la distribución recalibrada

Se evaluó si las distribuciones de conteos que ya se habían recalibrado mejoran también el número de casos que se publica. Se usaron los mismos mapas PIT globales y por nivel, aprendidos con etiquetas de temporadas anteriores, y los pronósticos archivados de b3, d3 e historia y geografía. No se ajustó otra regla con los desenlaces de evaluación. El cálculo usa la media de la distribución discreta completa.

Para una CDF NB2 base F y un mapa PIT H, la distribución recalibrada tiene CDF H(F(k)). Su media se obtiene integrando la función cuantílica de F con respecto a H. Se integró por tramos lineales del mapa guardado, con momentos truncados de la NB2 y el momento total para el extremo superior. La prueba con el mapa identidad recuperó la media NB2 y la comparación con sumas directas de la masa discreta verificó el cálculo para distintos niveles de dispersión. Se reprodujeron exactamente las métricas del conteo publicado de la evaluación anterior. [Evaluación de intervalos](resultados_intervalos_conteos.md) · [Distribución NB2 en SciPy](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.nbinom.html)

## Qué cambia para b3 a cuatro semanas

Son medianas de cinco semillas por temporada, promediadas con igual peso en las seis temporadas decisivas. El sesgo es el pronóstico menos lo observado. La razón durante brotes promedia por temporada los casos esperados divididos entre los observados.

| Métrica | Conteo publicado | Media PIT global | Media PIT por nivel |
|---|---:|---:|---:|
| Casos esperados / observados durante brotes | 59,5% | 62,2% | 75,2% |
| Sesgo durante brotes, casos | −12,43 | −11,65 | −8,05 |
| MAE durante brotes, casos | 18,52 | 18,38 | 18,58 |
| MAE en semanas sin brote, casos | 0,86 | 0,90 | 0,99 |
| MAE en todas las semanas, casos | 3,86 | 3,88 | 4,05 |
| RMSE en todas las semanas, casos | 18,84 | 18,71 | 18,49 |

La media por nivel reduce la subestimación de b3 y el RMSE, pero el MAE durante brotes queda prácticamente igual y el MAE global aumenta. El MAE global mejora en una de seis temporadas. El aumento de la media es más fuerte en semanas donde el modelo ya pronosticaba al menos cinco casos. En ese estrato, definido al emitir, el promedio observado fue 39,58. El conteo publicado promedió 28,69 y la media por nivel 35,89, pero el MAE subió de 24,13 a 25,27. Se redujo el sesgo medio y permaneció la dificultad para distinguir exactamente cuánto subir en cada semana.

d3 repite el intercambio principal. Su media por nivel sube de 65,8% a 78,9% de lo observado durante brotes y su MAE global aumenta de 3,97 a 4,16. En historia y geografía, pasa de 73,9% a 85,0%, con MAE global de 4,00 a 4,20. La recalibración por nivel mejora el WIS de la distribución. Como estimación de conteo, la media recalibrada favorece el sesgo y puede favorecer el RMSE, mientras que el desempeño medido por MAE muestra un costo. Los resultados permiten justificar conservar el conteo publicado como referencia para MAE y mantener la media recalibrada como candidato para objetivos que penalicen más los errores grandes.

Las predicciones por fila, las 5 670 celdas de métricas y las diferencias pareadas se guardaron en `models/experimentos/mejora_modelo/v3_confirmados/intervalos_revision/media_recalibrada/`. La evaluación usa 61 230 filas por modelo y semilla sobre las mismas llaves, etiquetas y orígenes. Se reproduce con `code/evaluate_recalibrated_count_mean.py`.
