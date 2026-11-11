# Transferencia del pronóstico de Piura a Lambayeque y Tumbes

La prueba mide si el paquete ajustado en Piura conserva su habilidad en otros departamentos. La pregunta climática se evalúa con el par emparejado de historia y geografía y el brazo `b3`. La política de alertas se compara con persistencia en las mismas filas. Los resultados se informarán por departamento, temporada y horizonte de 2, 3 y 4 semanas.

## Congelamiento en Piura

El contraste principal del manuscrito usa `b3` y su par sin clima con hiperparámetros fijos. El ajuste simétrico es una sensibilidad. Para materializar el paquete se debe acordar cuál configuración se traslada, el último origen de entrenamiento, el uso de las cinco semillas o su regla de agregación y el corte de alerta por horizonte. La decisión se registra antes de puntuar los destinos.

Se ajusta el paquete en Piura con los datos que corresponden al corte y se guardan los modelos, el orden de variables, las ventanas y reglas de disponibilidad, los parámetros de dispersión y calibración, la mezcla de conteos y los cortes de alerta. Se guardan también los parámetros que necesiten los comparadores probabilísticos, las reglas de persistencia, los hashes de código e insumos y el entorno. Una comprobación de inferencia local debe reproducir las predicciones generadas al guardar el paquete. Los pronósticos retrospectivos archivados se ajustaron por corte y no contienen por sí solos un paquete único de inferencia.

## Auditoría de insumos previa a la evaluación

Se revisó el CSV nacional `DatosDengueV2.csv` filtrando `tipo_dx=C` y el ZIP nacional COD-AB del IGN publicado por OCHA. Se verificaron los UBIGEO y el calendario MMWR sin calcular pronósticos ni métricas de desempeño.

| Departamento | Distritos COD-AB | Distritos con algún confirmado y polígono | Primer registro confirmado con semana válida | Último registro confirmado con semana válida |
|---|---:|---:|---|---|
| Lambayeque | 38 | 37 | 2001-SE05 | 2025-SE53 |
| Tumbes | 13 | 13 | 2000-SE19 | 2025-SE53 |

Los 51 polígonos tienen geometrías válidas. Todos los UBIGEO con confirmados coinciden con polígonos. El UBIGEO 140203 carece de confirmados en esta copia. La ausencia de notificaciones requiere verificar cobertura antes de completar el panel. Lambayeque tiene cinco notificaciones confirmadas con semana fuera de la grilla MMWR. Se deben reconciliar con la fuente o excluirlas con un registro explícito de la decisión. Las fechas de la tabla indican extremos observados de notificación.

- CSV nacional, SHA-256 `7865e8b2f5a7aef1e8dce159444891f2c2e59b311d574f28c55aaca5a9abb8ba`.
- ZIP COD-AB, SHA-256 `2f0ec51b7a0899b407546aa644621e1c3255cba59fdda76fcde6975ca6baafb3`.

Desde la raíz, con el entorno del proyecto y rutas a las copias locales:

```bash
python -m pip install -e .
python -B research/08_v3_confirmed_cases/code/audit_northern_transfer_inputs.py \
  --cases /ruta/DatosDengueV2.csv \
  --boundaries /ruta/per_admin_boundaries.geojson.zip
```

## Preparación de la prueba

1. Confirmar un periodo común posterior al corte del paquete. Si el ajuste incorpora Piura de 2026, el CSV auditado sirve para reconstruir historia local y se necesitan observaciones externas más recientes para puntuar. Si se quiere probar años ya cerrados, se requiere un corte de entrenamiento anterior en Piura y se reporta como transferencia retrospectiva.
2. Verificar cobertura del origen epidemiológico y continuidad de UBIGEO. Cuando se extienda la serie con la Sala, extraer solo confirmados y comprobar el tramo de solape por departamento.
3. Calcular la exposición con las fuentes, la resolución y las reglas del brazo que se congele. Preparar lluvia CHIRPS por intersección de celdas y polígonos, temperatura ERA5-Land con la regla del brazo y las covariables estáticas. Auditar fechas de disponibilidad, cobertura espacial y valores fuera del rango de entrenamiento de Piura.
4. Construir la historia local y el umbral de evento con la misma receta en cada distrito. Aplicar los modelos y calibradores de Piura sin reentrenar con datos de los destinos. Verificar llaves idénticas entre los brazos y reportar Brier pareado, AP, recall y costo de alertas con cortes fijados en Piura.
