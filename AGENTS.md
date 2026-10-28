# Denguekay — instrucciones para Codex

Proyecto de tesis para pronosticar dengue por distrito y semana epidemiológica en Piura con **al menos dos semanas de anticipación y cuatro como objetivo principal**. El primer modelo previsto es XGBoost.

## Estructura y datos

- Leer `docs/estructuraRepo.md` antes de añadir rutas o módulos. La fuente integrada sin variables derivadas es `data/silver/integrado/meteo_socio_epi_piura_2017_2025.csv`; `data/gold/` se reserva para el resultado del feature engineering. Mantener la lógica reutilizable en `src/modeling/`, las comprobaciones en `src/validation/` y los notebooks como orquestación.
- Usar `src/utils/paths.py` para rutas del proyecto y conservar `ubigeo` como texto de seis dígitos. La llave del panel es `(ubigeo, anio, semana)` y la fecha semanal es `semana_inicio`.
- Tratar `data/bronze/` y `data/silver/` como entradas. No corregir silenciosamente problemas de origen en una transformación de features. Crear una salida en `data/gold/` solo en una fase de implementación aprobada y después de validarla.
- `CLAUDE.md` y `_claude_setup/` documentan el flujo anterior de EDA. Sus prohibiciones de hacer feature engineering y de escribir en `data/` están dirigidas a ese EDA; no sustituyen una solicitud explícita de feature engineering. Conservar sus invariantes útiles de estructura, trazabilidad, español y revisión por fase.

## Feature engineering

- Para tareas de construcción o revisión de variables del modelo, usar la skill local `.codex/skills/feature-engineering-dengue/SKILL.md` y el plan en `docs/feature_engineering/plan.md`.
- Rosa decidió que la alerta debe identificar **cada semana distrital con un nivel elevado de casos**. El primer arranque de un episodio no es la etiqueta principal. Para experimentar eligió media histórica + 1,5 DE; gold usa la misma semana de los cinco años anteriores y un mínimo provisional de 2 casos recomendado tras revisar la sensibilidad. Consultar `docs/feature_engineering/revision_definicion_brote.md` para las alternativas y la limitación de ceros sin registro. Las fases 4–7 se completaron; el modelado espera revisión y aprobación de Rosa.
- Fundar decisiones primero en `docs/eda/hallazgos.md`, `docs/eda/informe_eda.md`, `docs/eda/problemas_y_decisiones.md` y `docs/eda/metricas/`. El PDF en `docs/feature_engineering/references/investigacion_series_epidemiologicas.pdf` contempla horizontes de cuatro semanas y es apoyo metodológico. Sus ejemplos de código no muestran cómo alinear cada fila con una etiqueta futura; verificar esa alineación para cada horizonte y contrastar sus prioridades con el EDA. Las cifras predictivas del EDA corresponden a cuatro semanas; medir dos semanas por separado.
- Trabajar una fase por vez. Al cerrar una fase, mostrar resultados, cifras verificadas, límites y decisiones pendientes en español; esperar la aprobación de Rosa antes de pasar a la siguiente. No dar una decisión pendiente por aprobada.
- Indexar las filas por semana **objetivo**. Para horizonte `h ∈ {2, 4}`, predecir la semana `t` desde el cierre de `t−h`: los casos, el clima observado y los agregados de vecinos solo pueden usar semanas `≤ t−h`. Verificar esta disponibilidad por fecha real, no solo por nombre de columna. Ajustar climatologías, codificaciones aprendidas, imputaciones y selección de variables únicamente con el entrenamiento de cada corte temporal.
- Mantener separados los datos faltantes de los ceros epidemiológicos, especialmente en distritos sin notificaciones. Los casos de 2025 de la Sala Situacional son aceptados por el proyecto como fuente válida; conservar su procedencia sin excluirlos por defecto del entrenamiento ni asignarlos automáticamente a prueba. No usar `ubigeo` como número continuo ni presentar asociaciones como efectos causales.

## Seguimiento y calidad de datos

- Los módulos `ejecutar_*` de `src/modeling/` validan gold (y silver cuando lo leen) con Great Expectations antes de entrenar y registran cada corrida en MLflow al terminar. Guía: `docs/modeling/mlflow_great_expectations.md`.
- Las suites viven en `src/validation/expectations_gold.py` y `expectations_integrado.py`; `great_expectations/gx/`, `mlflow.db` y `mlartifacts/` son generados y no se versionan. Un experimento nuevo debe seguir la forma de reporte existente para registrarse sin cambios en `src/modeling/seguimiento_mlflow.py`.
- No registrar un modelo final en el Model Registry sin aprobación de Rosa.

## Comprobación

Usar `.venv/bin/python -m unittest discover -s tests` en macOS si existe el entorno, o el Python del proyecto. El integrado local ya fue comprobado tras ejecutar los notebooks 08 y 09; volver a validar su estado al iniciar cada fase, especialmente si se regenera. No inventar cifras ni afirmar que una validación se ejecutó cuando no fue así.
