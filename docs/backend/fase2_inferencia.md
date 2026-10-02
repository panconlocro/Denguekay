# Fase 2 — inferencia real y publicación batch

## Resultado y alcance

La ejecución comprobada el 01/10/2026 conecta fuentes reales, GX, XGBoost,
MLflow y BD. Se ejecutó contra SQLite y PostgreSQL local 17.5; la API queda
para la fase 3. No se ha probado Supabase ni desplegado Render.

Evidencia: [SQLite](fase2_verificacion_sqlite.json) y
[PostgreSQL](fase2_verificacion_postgresql.json). Ambos esquemas migrados
coinciden con el ORM y conservan la carga de fase 1.

| Registro | Cantidad por BD de verificación |
|---|---:|
| Distritos | 65 |
| Observaciones | 30 485 |
| Versiones de servicio | 6 |
| Versiones históricas por bloque | 24 |
| Versiones históricas de clasificación/regresión sin booster | 16 |
| Importancias gain guardadas | 26 |
| Predicciones futuras | 130 |
| Predicciones retrospectivas | 27 040 |
| Alertas retrospectivas retiradas | 4 002 |
| Alertas activas actuales | 0 |
| Cambios de activación auditados | 6 |
| Ejecuciones tras publicar dos veces | 1 |

Los avisos retrospectivos son registros derivados de probabilidades reales
OOS, importados con estado retirado. No se atribuyen a avisos emitidos en
años anteriores; sus fechas son de importación y su motivo lo declara.

## Decisiones aprobadas

- Alerta visible desde **0,50**: riesgo Alto o Muy alto. Conservar además
  `alerta_modelo`, calculada con el umbral F1 del protocolo.
- Un cero registrado representa cero casos. Una variable ausente impide
  generar esa fila; el resumen de ejecución devuelve el motivo.
- Conservar las retrospectivas de Rosa como versiones históricas sin
  booster, no reactivables. Entrenar versiones nuevas para servir inferencia.
- Determinar aceptación mediante **temporada 2024**. Guardar **calendario
  2025** como sensibilidad separada, sin usarlo para decidir aceptación.

## Construcción y trazabilidad

`cargar_datos` reutiliza las validaciones y auditoría existentes. En esta
ejecución GX aprobó silver **107/107** y cada gold **92/92**. Se conservaron
sin cambios los SHA256 de **503 archivos** de entrada y resultados previos,
incluidos gold, referencias y los resultados originales de Rosa.

`protocolo` comprueba hashes de gold/manifiesto, columnas, llaves, etiquetas,
orígenes y cortes mediante las funciones temporales de `train.py`. Recalcula
las métricas con `evaluar_fold` para contrastarlas con el JSON de Rosa.
Recupera float32 solo para esa comprobación: importa las probabilidades y
conteos originales del CSV sin cambiarlos. Se contrastaron los bloques
2022–2024 y calendario 2025 de ambas variantes elegidas, en h=2 y h=4.

Clasificación usa `base_6_poblacion_2017`; regresión usa `base_6`. Se ajustan
mediante `ajustar_modelos`, con `PARAMETROS_BASE` y todas las etiquetas
cerradas al origen. El helper existente devuelve ambos objetivos; se
conserva el componente elegido de cada variante. La inversión log1p del
regresor se centralizó en `train.conteos_desde_log1p`, conservando la fórmula
previa. La persistencia devuelve el conteo observado en t−h.

Las versiones de servicio guardan booster JSON, columnas ordenadas,
parámetros, periodo de ajuste, hashes, plataforma, device y versión de
XGBoost. Esta ejecución ajustó en CPU con XGBoost 3.4.1; la evaluación
importada proviene de CUDA con la misma versión. La plataforma de los
modelos históricos es null porque el reporte original no la documenta.

Se registraron runs normales de MLflow: una raíz y seis hijos por publicación
nueva, todos FINISHED. Los folds importados no se registran como ajustes OOS
nuevos. El reporte indica que las métricas son evidencia histórica del
protocolo y **no evaluación del booster final sobre entrenamiento**.
No se realizaron registros en el Model Registry.

| BD comprobada | Run raíz de servicio |
|---|---|
| SQLite | `ef91d4125ca840efa8922af56f41f6c4` |
| PostgreSQL | `3056d2d538aa4d9a9b9455af6210b29a` |

## Origen, calendario y semanas futuras

`inferencia_futura` recorta el panel al cierre antes de calcular variables.
Reutiliza `construir_historia_calendario`, `construir_sociodemografia`, el
censo 2017 y el contrato de disponibilidad. Extiende el calendario solo
en memoria con casos ausentes; no escribe gold ni observaciones futuras.

Se publica **un objetivo por horizonte** desde el último origen observado.
Servir objetivos más cercanos con el booster ajustado al último cierre
incorporaría etiquetas posteriores a sus orígenes; no se hace esa sustitución.

| Horizonte | Origen cerrado | Objetivo MMWR | Inicio objetivo | Filas |
|---|---|---|---|---:|
| 2 | 27/12/2025 | 2026, semana 1 | 04/01/2026 | 65 |
| 4 | 27/12/2025 | 2026, semana 3 | 18/01/2026 | 65 |

El paso intermedio 28/12/2025 es la semana MMWR 53 de 2025. No se convierte
en semana 1 de 2026 ni se redistribuyen los casos de Sala fuera de gold.
En esta publicación no hubo filas insuficientes. Las probabilidades máximas
fueron **0,185261** (h=2) y **0,203759** (h=4), tomadas de BD; los 130
pronósticos tienen riesgo Bajo y `alerta_modelo=false`. Son pronósticos
desde el corte 2025, aunque el tipo guardado sea `vigente`; no representan
una actualización de los datos a octubre de 2026.

## Honestidad y dos criterios de alerta

El estado se deriva de métricas y criterios guardados en cada versión.
Clasificación exige Recall ≥0,80, Precision ≥0,60 y F1 ≥0,70; regresión exige
MAE y RMSE ≤85 % de persistencia. Si falta una métrica no se sustituye por
cero. Cada predicción y alerta obtiene su estado a partir de sus versiones.

| Contraste 2024 | h=2 | h=4 |
|---|---:|---:|
| Recall clasificación | 0,946324 | 0,925321 |
| Precision clasificación | 0,489144 | 0,462391 |
| F1 clasificación | 0,644930 | 0,616641 |
| MAE regresión | 5,638670 | 9,400846 |
| MAE persistencia | 4,956213 | 7,847633 |
| RMSE regresión | 23,848469 | 40,443304 |
| RMSE persistencia | 15,756824 | 25,454955 |

Los cuatro modelos XGBoost quedan **experimentales**; las persistencias
son **referencias**. Las métricas son las del JSON del protocolo guardado
en BD, por bloque, sin promediar 2024 y 2025.

Los cortes de riesgo son Bajo <0,25, Medio [0,25;0,50), Alto [0,50;0,75),
Muy alto ≥0,75. El umbral F1 de servicio se toma del último bloque del
protocolo, calendario 2025: **0,275** en h=2 y **0,225** en h=4. El rango
aproximado del encargo no es un parámetro: se conserva el valor real del
JSON. Una probabilidad que supera el umbral F1 pero no 0,50 activa
`alerta_modelo` y no una alerta visible. Hay casos reales de esa discrepancia
en las fixtures y se prueban ambos resultados.

La calibración progresiva del protocolo selecciona un **umbral F1**; no
equivale a calibrar las probabilidades como frecuencias observadas. Rosa
aprobó conservar ambos criterios. Sigue pendiente una evaluación de
calibración probabilística y su interpretación clínica; no se modifica el
modelo para resolverla en esta fase.

## Comandos y comprobaciones ejecutadas

Desde la raíz, con `DATABASE_URL` configurada en el entorno de cada ejecución:

```bash
.venv/bin/python -m src.validation.calidad_gx
.venv/bin/alembic upgrade head
.venv/bin/python -m src.serving.publicar --horizontes 2 4
.venv/bin/python -m src.serving.publicar --horizontes 2 4
.venv/bin/python -m coverage run --append --source=src/db,src/serving,src.modeling.inferencia_futura,src.validation.validacion_modelo -m unittest discover -s tests
.venv/bin/python -m coverage report -m
.venv/bin/python -m coverage json -o models/serving/cobertura_fase2.json
```

La primera publicación por BD devolvió 27 170 filas; la segunda,
`reutilizada: true`, manteniendo ejecuciones, modelos, predicciones, alertas y
run. Se usó SQLite físico en `models/serving/fase2.sqlite` y un clúster local
PostgreSQL aislado. También se conserva `models/serving/fase1.sqlite`, con
la primera prueba de publicación, sin borrar su historial.

Además se ejecutó una comparación completa desde BD: las **27 040** filas
retrospectivas conservan exactamente probabilidades/conteos del CSV y sus
vectores coinciden con gold; las **130** futuras reproducen exactamente
clasificación, regresión y persistencia al cargar los artefactos de BD.
Todas las predicciones cumplen la distancia objetivo−origen y el corte de
entrenamiento ≤origen. Se verificaron también los estados FINISHED de MLflow
y la igualdad del esquema migrado con el ORM en ambos motores.

**218 tests aprobados**, incluidos los existentes y **30 nuevos** de fase 2,
en **28,094 s** para la última suite instrumentada. Prueban anti-fuga mediante
alteración de datos posteriores al corte, igualdad contra gold, calendario,
ceros/faltantes, límites de riesgo, aceptación 2024, sensibilidad separada,
booster real, rechazo de históricos sin booster, idempotencia, activación sin
borrar historial, alertas activas/retiradas y rollback de una transacción
incompatible con el origen. Las fixtures provienen de gold/CSV reales; los
boosters de pruebas se ajustan sobre esas muestras, sin mocks.

Cobertura de líneas de **src/db + src/serving: 93,19 %** (930/998).
Incluyendo los nuevos helpers de inferencia y validación: **93,65 %**
(1033/1103). Se midió con la suite completa y el CLI real SQLite instrumentado;
no es cobertura de la API, aún pendiente. Las comprobaciones completas y
conteos están en los dos JSON de evidencia enlazados arriba.

`git diff --check` detecta CRLF de los dos CSV de referencia copiados por el
usuario antes de esta fase. Excluyendo esos archivos, pasó sin observaciones;
no se cambiaron sus bytes ni sus finales de línea.

## Archivos creados o modificados

- Nuevos: `src/modeling/inferencia_futura.py`,
  `src/validation/validacion_modelo.py`, siete módulos de servicio
  (`configuracion`, `protocolo`, `modelos`, `artefactos`, `riesgo`,
  `publicacion`, `publicar`), migración 0002 y helper `tests/serving_soporte.py`.
- Pruebas: `test_serving_futuras.py`, `test_serving_politicas.py`,
  `test_serving_protocolo.py`, `test_serving_publicacion.py`, siete CSV/JSON
  de muestra y su procedencia bajo `tests/fixtures/backend/`.
- Modificados: `src/db/modelos.py`, `src/modeling/historia_calendario.py`
  (opción de faltantes solo para inferencia), `src/modeling/train.py`
  (inversión log1p compartida), `src/utils/paths.py`, `config/config.yaml`,
  `README.md`, `docs/estructuraRepo.md` y `docs/backend/operacion.md`.
- Evidencia nueva: este cierre y los JSON de verificación SQLite/PostgreSQL.
  Artefactos, BD y cobertura completa quedan en `models/serving/`, ignorado
  por Git; tracking MLflow y GX mantienen sus rutas existentes ignoradas.

## Limitaciones y trabajo pendiente

Los umbrales de aceptación no se cumplen. El corte sigue en 2025, las
probabilidades no tienen calibración probabilística y CPU/GPU pueden variar.
No hay gold h=3 ni polígonos disponibles; se conservan centroides y motivos.
La regeneración automática del protocolo si falta su CSV está implementada
con el módulo existente, pero no fue necesaria ni ejecutada en esta revisión.
Windows tiene comandos y código portable; no se ejecutó esta fase en un PC
Windows. Supabase, API, benchmark HTTP, OpenAPI, CI y despliegue siguen en
sus fases respectivas. Se requiere aprobación de Rosa para iniciar fase 3.
