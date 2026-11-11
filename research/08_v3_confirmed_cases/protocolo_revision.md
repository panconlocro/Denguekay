# Protocolo de revisión del estudio de Piura

Preparado el 9 de noviembre de 2026 para revisión del equipo, después del diagnóstico archivado y antes de evaluar `b3` con confirmados. La pregunta principal es el aporte del clima al pronóstico semanal distrital cuando el modelo ya conoce la historia local de casos. Los bloques históricos ya sirvieron para desarrollar o examinar V3. Las nuevas comparaciones sobre ellos son retrospectivas.

## Insumos y cortes auditados

- La serie usa el CSV de confirmados para 2000–2024 y la Sala Situacional para 2025–2026. El panel integrado aporta las primeras 52 semanas de 2025 y la extensión con Sala incluye la SE 53. Para 2026 se usan las SE 1–41 y se separan las SE 42 y 43 como provisionales según el protocolo original. En el tramo histórico sin filas explícitas de cero se conserva la convención del estudio original para las semanas cubiertas. La coincidencia de los dos archivos en 2025 se verificó de forma separada.
- Un bloque regular va de la SE 35 del año previo a la SE 34 del año que lo nombra. Hay 19 temporadas completas, 2008–2026, y un bloque parcial posterior con siete semanas. El calendario abarca 999 semanas, 65 distritos y 64 935 filas por horizonte, incluidas 4 837 semanas distritales elevadas. Se recuperan las 18 semanas del 25 de agosto al 22 de diciembre de 2024 y se elimina la doble evaluación de 19 semanas del 24 de agosto al 28 de diciembre de 2025. El bloque posterior de 2026 es exploratorio.
- La temporada 2025 abarca del 25 de agosto de 2024 al 17 de agosto de 2025. Tiene 3 380 filas, 57 semanas distritales elevadas y 2 190 casos confirmados. El primer origen para ajustar los árboles es el 3 de agosto de 2024, que corresponde a h4. El calibrador de cada horizonte solo puede usar predicciones fuera de muestra de bloques anteriores cuya semana objetivo ya cerró. El primer bloque, 2008, aporta predicciones crudas para calibrar bloques posteriores y queda fuera de todas las métricas calibradas.
- En el solape de 2025 coinciden **3 445 de 3 445** pares distrito-semana, incluidos los 432 pares con casos. Ambas fuentes suman **1 117** confirmados. El CSV nacional tiene registros en las 53 semanas del año. Esta concordancia describe los archivos disponibles y el periodo comparado. Los casos de 2026 proceden de la Sala y las fechas de la primera notificación requerirían snapshots históricos.
- Se validaron silver y gold con Great Expectations, y se verificó que las 60 celdas de bloque y horizonte cubren las mismas llaves objetivo, sin solapes ni saltos. En 57 celdas hay historial elegible de calibración. La tabla de cortes, el solape detallado y el manifiesto con SHA-256 de los insumos actuales se generan en `models/experimentos/mejora_modelo/v3_confirmados/revision_protocolo/`. Los nuevos insumos climáticos se identificarán con sus propios hashes cuando termine el piloto.

```bash
.venv/bin/python -B research/08_v3_confirmed_cases/code/audit_revision_inputs.py
```

## Decisiones históricas y evidencia disponible

| Fecha | Registro | Decisión y alcance |
|---|---|---|
| 3 nov. 2026 | `6a29a8e` | La fase 1 fijó 2010, 2015, 2016, 2022 y 2023. 2010 se leía también aparte por su menor historia de entrenamiento. 2024 se reservó como contraste de desarrollo. El plan explicaba que ampliar el panel de temporadas reducía la dependencia de 2017 y de las dos temporadas usadas anteriormente. Falta una regla documentada que reproduzca la selección exacta de los cinco años. |
| 3 nov. 2026 | `ae762e7` | El archivo de resultados de fase 1a incluye 2024. Se reportará como contraste retrospectivo examinado durante el desarrollo. |
| 6 nov. 2026 | `658d0bd` | Se añadió un criterio con Brier al paso de ventanas meteorológicas. El criterio por F1 seguía visible. La revisión explicará el cambio de métrica y su fecha. |
| 8 nov. 2026 | `e02ebe1` | Se fijó la regla `SEASON_2026` con Brier y se añadió 2026 después de las primeras pruebas climáticas. Las seis temporadas son 2010, 2015, 2016, 2022, 2023 y 2026. |
| 8 nov. 2026 | `505b9b6`, `87aa8d5` | La matriz histórica aplicó 12 contrastes climáticos frente a la referencia y tres cruces adicionales entre variantes existentes. La regla adoptó `b3`. Después de inspeccionar la matriz, se escogió `d3` como base operativa. |
| 8–9 nov. 2026 | `b408371`, `02d7275`, `290dbaa`, `6894012` | Se completaron 255 ensayos de ajuste de `d3` en temporadas de desarrollo. Los cinco mejores se evaluaron con cinco semillas en esas temporadas. El ensayo 191 se comparó con el ajuste heredado en las seis temporadas, y el cierre repitió el contraste climático con ese ensayo en ambos brazos. |

En los archivos de la matriz y el cierre se identifican 15 configuraciones predictivas distintas evaluadas sobre las seis temporadas, contando la referencia y las 12 variantes heredadas, más `d3` y el par sin clima con el ensayo 191. Los tres cruces reutilizan modelos. La búsqueda de 255 ensayos y la validación dejando temporadas fuera se reportan por separado. La reconstrucción está limitada a las configuraciones archivadas que se pudieron identificar. La validación dejando una temporada fuera incluyó 2010, 2015, 2016, 2017, 2022, 2023, 2024 y 2026.

## Regla de lectura propuesta para la nueva comparación

- Presentar `b3` como contraste climático principal y `d3` como variante operativa. Comparar primero los brazos con los mismos hiperparámetros heredados. Reportar aparte el contraste con ajuste simétrico, con el presupuesto fijado antes de ejecutar la búsqueda. Mantener orígenes, filas, etiquetas y semillas pareadas.
- La medida principal será la diferencia de Brier `b3 − sin clima` por horizonte. Calcular la diferencia sobre las mismas filas por temporada y semilla, tomar la mediana de las cinco semillas dentro de cada temporada y promediar las seis temporadas con el mismo peso. Mostrar las seis diferencias individuales, el promedio sin 2026 y el resultado al retirar cada temporada. Reportar incertidumbre agrupada por temporada y sensibilidad a semilla. El resumen retrospectivo y la regla de adopción histórica cumplen funciones distintas. Tratar el resto de las variantes y horizontes como comparaciones descriptivas y explicitar la multiplicidad de la matriz original.
- Usar «prespecified» para los criterios internos fechados. Mostrar los cambios y las temporadas ya inspeccionadas. Un registro prospectivo externo requerirá un protocolo y un modelo congelados antes de observar los desenlaces de esa evaluación.

## Evidencia de sensibilidad ya disponible

En las cinco temporadas archivadas previas a 2026, el Brier de `d3` frente a su par sin clima cambió **+0,37 % en h2**, **−0,17 % en h3** y **−3,21 % en h4**. El resumen es el cociente de los promedios con igual peso por temporada de las medianas entre semillas. `d3` obtuvo menor Brier en dos de cinco temporadas para cada horizonte. El Brier skill score de `d3` frente a persistencia probabilística fue 0,065, 0,078 y 0,098 en h2, h3 y h4, respectivamente, con la misma agregación. Estos resultados corresponden a `d3` y al calendario archivado. La tabla principal y su sensibilidad sin 2026 usarán el calendario común y `b3`.
