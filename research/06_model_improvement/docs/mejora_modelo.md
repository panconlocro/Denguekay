# Mejora del modelo sobre la V2

Informe del estudio 06. Plan y decisiones de Rosa en [plan.md](plan.md); preregistros en
`code/preregistration.py`.

## Fase 0 · Diagnóstico y techo (cerrada el 2026-11-03)

Notebook `01_diagnostico_techo.ipynb`, cifras en `metricas/fase0.json`, MLflow
`denguekay/mejora_modelo_fase0_diagnostico`. Resumen presentado a Rosa en el chat el 2026-11-03.

## Fase 1 · Más historia

### Preregistro

`code/preregistration.py → PHASE1`, commit `6a29a8e`, aprobado por Rosa antes de entrenar.

### Enmienda G1 (2026-11-03, antes de entrenar)

- **Qué falló:** G1 exigía que las 9 columnas de la V1 (`base_6` + B3) fueran iguales en la tabla de orígenes
  larga y en la de la V1. Ocho coinciden exactamente en los 30 160 orígenes comunes. `propia_semanas_desde_ultimo_caso`
  difiere en **134 orígenes** de **20 distritos**, con cierres entre el 2017-01-28 y el 2017-05-06.
- **Causa:** la V1 calcula esa variable con el panel desde 2017, sin las semanas anteriores. Un distrito que aún
  no tenía casos en 2017 recibe el tope (52, «sin caso conocido»); con la historia larga se ve su último caso de
  2016, entre 1 y 43 semanas antes (mediana 16).
- **Enmienda aprobada por Rosa:** esas filas se exceptúan de G1. En ellas, la tabla larga debe dar < 52 e igual
  al recálculo directo desde la serie de casos; se cumple en las 134.
- **Consecuencia para la comparación 1a:** L usa los valores largos y R conserva la tabla exacta de la V1. Esas
  134 filas de entrenamiento (todas de 2017) forman parte de la diferencia L − R, junto con las temporadas
  2005–2016.

### Limitación conocida de la V1 y la V2

La V1 y la V2 tienen el mismo defecto de inicio de panel en `propia_semanas_desde_ultimo_caso`: en las primeras
semanas de 2017 la variable no ve la historia anterior y queda en el tope 52 para los distritos sin casos en
2017. Afecta a 134 orígenes de entrenamiento, todos entre el 2017-01-28 y el 2017-05-06; no afecta a ninguna
semana evaluada (2021 en adelante), porque desde mayo de 2017 cada distrito ya tiene su último caso dentro del
panel o lleva 52 semanas sin casos. **Las versiones congeladas no se modifican:** la V1 y la V2 se reproducen tal
como se congelaron, con ese defecto.

### Cambios propuestos para `gold.py` (sin implementar; los ejecuta el equipo)

- `propia_semanas_desde_ultimo_caso` debe leer también la historia anterior a 2017 (`SILVER_EPI_HISTORICAL`), no
  solo para la temporada anterior (`propia_log_casos_temporada_anterior`, que ya la lee). Así las primeras
  semanas de 2017 dejan de quedar en el tope por falta de historia.
- Ese cambio movería la columna de gold en esas 134 filas: rompería la paridad bit a bit de gold con
  `frozen_configs.origins` de la V1/V2. Por eso solo entra si la configuración que lo usa reemplaza a la V2
  (decisión de Rosa en la fase 7), con su propia ficha y su propia huella.
