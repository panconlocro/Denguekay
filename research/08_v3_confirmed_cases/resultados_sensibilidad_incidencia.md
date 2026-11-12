# Sensibilidad al umbral fijo de incidencia

La serie de `data/silver/socio_anual.csv` cubre 2017–2025 y coincide en los 585 valores distrito–año con el panel semanal de confirmados y con el Excel original `data/bronze/socio/data_socio_2017_2025.xlsx` del workspace Denguekay. El Excel local registra población censada para 2017 y proyectada para 2018–2025. Se usó para este análisis la edición de proyecciones distritales al 30 de junio de 2018–2026 del INEI. Cubre los 65 distritos de Piura y aporta 585 denominadores de una sola edición, incluido 2026. Entre los 520 pares que coinciden en distrito y año, dos tienen exactamente la misma población. La diferencia absoluta relativa mediana es 0,94%, el percentil 90 es 2,26% y el máximo es 3,68%. [Publicación del INEI](https://www.gob.pe/institucion/inei/informes-publicaciones/6894980-peru-poblacion-total-proyectada-al-30-de-junio-de-cada-ano-segun-departamento-provincia-y-distrito-2018-2026)

El soporte común incluye 27 170 semanas distritales por horizonte en las temporadas 2019–2026. Se aplicaron los tres cortes de incidencia del protocolo a los mismos casos confirmados. Se reutilizaron los conteos pronosticados y la dispersión NB2 de las cinco semillas, se recalculó la probabilidad de superar cada corte y se reajustó Platt por separado con bloques anteriores disponibles al corte. La definición principal y la persistencia probabilística se calibraron con el mismo calendario. El bloque 2019 aporta los primeros datos de calibración y carece de una evaluación calibrada. Para el corte de 20 por 100 000, 2020 también queda sin evaluación calibrada por ausencia de positivos previos. [Protocolo](protocolo_sensibilidad_incidencia.md)

## Semanas elevadas e inicios

Los conteos corresponden a las 10 205 semanas distritales de las temporadas decisivas cubiertas por el INEI, 2022, 2023 y 2026. Un inicio limpio requiere ocho semanas previas sin brote según su propia etiqueta. El emparejamiento exige el mismo distrito y una distancia máxima de cuatro semanas entre ambos inicios.

| Definición | Semanas elevadas | Prevalencia | Añadidas / retiradas frente a la principal | Positivos con un caso | Inicios limpios | Inicios de la principal emparejados |
|---|---:|---:|---:|---:|---:|---:|
| Principal | 1 563 | 15,32% | 0 / 0 | 0 | 110 | — |
| 5 por 100 000 | 2 362 | 23,15% | 884 / 85 | 343 | 157 | 51 |
| 10 por 100 000 | 2 009 | 19,69% | 610 / 164 | 177 | 137 | 62 |
| 20 por 100 000 | 1 546 | 15,15% | 329 / 346 | 30 | 107 | 55 |

El corte de 10 por 100 000 clasifica como elevada una semana con un caso si la población distrital es de 10 000 habitantes o menos. Esa condición se cumple en 4 082 semanas del conjunto y se observó exactamente un caso en 177 de ellas. De los 62 inicios emparejados con la definición principal, 31 ocurren en la misma semana. Con el corte de 20 por 100 000 la prevalencia se aproxima a la principal, pero cambia la clasificación de 675 semanas. Las coincidencias miden cuánto cambian los eventos bajo cada definición. El estudio carece de un catálogo independiente para establecer cuál de las definiciones identifica mejor los brotes reales.

## Comparación de probabilidades

La tabla muestra **Brier del modelo climático menos Brier del comparador con historia y geografía**, multiplicado por mil. Se toma la mediana de las diferencias pareadas entre las cinco semillas dentro de cada temporada y se da igual peso a las temporadas. Los valores negativos favorecen al modelo climático. Cada comparación usa una sola definición del evento.

| Definición | b3 h2 | b3 h3 | b3 h4 | d3 h2 | d3 h3 | d3 h4 |
|---|---:|---:|---:|---:|---:|---:|
| Principal | −2,77 | −2,25 | +0,26 | −1,20 | −0,41 | +1,26 |
| 5 por 100 000 | +0,90 | +6,38 | +13,03 | −1,12 | +1,47 | +5,05 |
| 10 por 100 000 | +0,38 | +4,30 | +9,70 | −1,04 | +0,41 | +3,25 |
| 20 por 100 000 | −1,37 | +0,16 | +4,50 | −1,16 | −0,26 | +1,76 |

A h4, el comparador con historia y geografía obtiene menor Brier promedio que ambos modelos climáticos en las cuatro definiciones. El signo se conserva al retirar 2026. A h2, `d3` mejora en las cuatro definiciones en promedio, mientras que el resultado de `b3` cambia según el corte. La magnitud de las diferencias se interpreta con cautela dado el soporte de tres temporadas.

Frente a la persistencia probabilística, a h4 `b3` tiene un Brier menor con la definición principal y con el corte de 20 por 100 000. Tiene un Brier mayor con los cortes de 5 y 10. `d3` tiene un Brier menor que persistencia en las cuatro definiciones. Esta comparación se refiere a las probabilidades calibradas. Evaluar el beneficio operativo bajo estas etiquetas exigiría volver a medir la política de alertas.

Los resultados se limitan al periodo cubierto por esta edición poblacional. La publicación se difundió después de las primeras temporadas analizadas. Se aplicó retrospectivamente para construir las etiquetas y se preservó el calendario de los pronósticos de conteo archivados. Los cortes sirven como sensibilidades analíticas y se mantiene la definición estacional como resultado principal.

Las tablas de etiquetas, inicios, Brier y AP por temporada y el manifiesto de insumos se guardaron en `models/experimentos/mejora_modelo/v3_confirmados/sensibilidad_incidencia/`. El análisis se reproduce con `code/evaluate_incidence_sensitivity.py`.
