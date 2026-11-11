# Resultado del ajuste de cortes de alerta

El corte es la probabilidad mínima que dispara una alerta. Se eligió con las mismas seis temporadas de desarrollo para b3 y la persistencia probabilística. Se aplicó a las temporadas 2022, 2023 y 2026. Los cortes quedaron fijos después de desarrollo y los modelos y calibradores son los de las predicciones archivadas por bloque. [Protocolo](protocolo_cortes_alerta.md)

A cuatro semanas, con el presupuesto de desarrollo de un falso aviso por distrito cada 52 semanas, el corte mediano de b3 fue **27,85%** (27,14% a 28,10% entre las cinco semillas) y el de persistencia fue **13,16%**. Las 20 215 filas de desarrollo por horizonte permiten hasta 388 falsas alarmas. b3 usó 388 en cada semilla. La persistencia usó 322 porque el siguiente grupo empatado de probabilidades excedía el presupuesto. El último sábado de etiquetas elegibles fue el 7 de agosto de 2021.

## Evaluación principal a cuatro semanas

La anticipación se mide en inicios avisados con al menos dos semanas nominales. Los recuentos son medianas entre semillas dentro de cada temporada. La fila conjunta suma esas medianas.

| Temporada | Inicios | b3 a 0,50, inicios / falsas alarmas | b3 ajustado, inicios / falsas alarmas | Persistencia a 0,50, inicios / falsas alarmas | Persistencia ajustada, inicios / falsas alarmas |
|---|---:|---:|---:|---:|---:|
| 2022 | 30 | 0 / 8 | 8 / 139 | 1 / 53 | 7 / 227 |
| 2023 | 52 | 5 / 31 | 31 / 191 | 2 / 24 | 9 / 119 |
| 2026 | 20 | 2 / 4 | 10 / 37 | 5 / 6 | 13 / 65 |
| Conjunto | 102 | 7 / 43 | 49 / 367 | 8 / 83 | 29 / 411 |

Ambos métodos detectaron más inicios al bajar su corte y generaron más falsas alarmas. Con los cortes ajustados, b3 detectó 20 inicios adicionales en conjunto frente a la persistencia probabilística y generó 44 falsas alarmas menos. La diferencia de detección se concentra en 2023, cuando b3 también generó más falsas alarmas. En 2026 la persistencia detectó tres inicios más a cambio de 28 falsas alarmas adicionales.

Con el objetivo de un falso aviso en desarrollo, las tasas alcanzadas en evaluación fueron 1,87 por distrito por 52 semanas para b3 y 2,09 para persistencia. Ambas quedaron por encima del objetivo en 2022 y 2023. En la sensibilidad con 0,5 como objetivo de desarrollo, b3 avisó 34 inicios con 195 falsas alarmas y la persistencia 20 con 213, sobre el mismo conjunto de temporadas. Estas comparaciones mantienen el corte y muestran el costo observado de cada método. La superioridad operativa en una temporada futura requiere validación prospectiva.

Las tablas de h2, h3 y h4, los cortes por semilla, los episodios individuales y el manifiesto de huellas se guardaron en `models/experimentos/mejora_modelo/v3_confirmados/cortes_alerta/`. Se verificaron las mismas llaves y etiquetas para ambos métodos, el máximo de falsas alarmas en desarrollo y las cinco semillas por celda. La evaluación se reproduce con `code/evaluate_alert_cutoffs.py`.
