# Denguekay

## Feature engineering con Codex

Las instrucciones locales de Codex están en `AGENTS.md` y la skill
`.codex/skills/feature-engineering-dengue/SKILL.md`. El plan por fases,
fundado en el EDA y contrastado con la investigación guardada en
`docs/feature_engineering/references/investigacion_series_epidemiologicas.pdf`, está en
`docs/feature_engineering/plan.md`. Cada fase requiere revisión de resultados
y aprobación de Rosa antes de iniciar la siguiente. El primer modelo previsto
es XGBoost, con anticipación mínima de dos semanas y objetivo principal de cuatro;
cada horizonte se evaluará por separado. El dataset integrado de `data/silver/integrado/` es la entrada sin
features y `data/gold/` contiene la salida validada de la fase 6.

Las fases 1–7 ya tienen notebooks ejecutados (`17`–`23`) e informes en
`docs/feature_engineering/`. La [fase 4](docs/feature_engineering/fase4_clima.md)
prueba ventanas climáticas causales. La [fase 5](docs/feature_engineering/fase5_sociodemografia.md)
compara demografía fija y anual reconstruida. La [fase 6](docs/feature_engineering/fase6_integracion.md)
integra candidatos para `h=2` y `h=4`, y conserva un manifiesto de linaje.
La [fase 7](docs/feature_engineering/fase7_sintesis_traspaso.md) audita los gold,
enumera las variables candidatas y documenta el contrato para el primer XGBoost.
El [primer experimento](docs/modeling/primer_xgboost.md) compara regresión de casos
y clasificación directa, con cortes temporales para ambos horizontes. La
[ablación espacial](docs/modeling/ablacion_espacial.md) prueba por separado
vecinos y jerarquía, y la [ablación climática](docs/modeling/ablacion_clima.md)
compara medias observadas y anomalías ajustadas por corte, conservando F1 como
criterio provisional. La [ablación sociodemográfica](docs/modeling/ablacion_sociodemografica.md)
separa rasgos censales fijos de estimaciones anuales reconstruidas; el
[cribado individual de fracciones](docs/modeling/ablacion_fracciones.md)
compara las 15 por separado. La [comparación condicional](docs/modeling/ablacion_poblacion_sin_seguro.md)
evalúa población censal fija y fracción sin seguro, solas y juntas. La
[validación temporal compacta](docs/modeling/validacion_temporal_compacta.md)
compara tres matrices pequeñas con umbrales calibrados solo en temporadas anteriores.
Ambos gold
incluyen `brote`, definido como
semana distrital con casos por encima de la media de esa semana en los cinco
años previos + **1,5 DE**, con un mínimo provisional de **2 casos**;
[la sensibilidad](docs/feature_engineering/revision_definicion_brote.md)
documenta el efecto de exigir 1 o 5 casos.

Para regenerar los dos CSV de `data/gold/` desde el silver completo:

```bash
.venv/bin/jupyter nbconvert --to notebook --execute --inplace notebooks/22_fe_integracion.ipynb
```

El gold conserva `casos_Dengue` como conteo junto a la etiqueta `brote` y su
umbral auditable. El entrenamiento excluye de los predictores
`casos_Dengue`, `brote` y `umbral_brote_casos`. El primer ensayo usa historia
propia y calendario; vecinos, jerarquía, clima y demografía se compararon en
bloques separados. Las variantes anuales de demografía son retrospectivas.

Para reproducir la auditoría de traspaso después de generar gold:

```bash
.venv/bin/jupyter nbconvert --to notebook --execute --inplace notebooks/23_fe_sintesis.ipynb
```

Para reproducir el primer entrenamiento y evaluación de ambos enfoques:

```bash
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m src.modeling.train
.venv/bin/python -m src.modeling.ablacion_espacial
.venv/bin/python -m src.modeling.ablacion_clima
.venv/bin/python -m src.modeling.ablacion_sociodemografica
.venv/bin/python -m src.modeling.ablacion_fracciones
.venv/bin/python -m src.modeling.ablacion_poblacion_sin_seguro
.venv/bin/python -m src.modeling.validacion_temporal_compacta
```

La prueba principal es la temporada epidemiológica 2024; el año calendario
2025, con solo tres semanas distritales positivas, se reporta por separado
como sensibilidad. Las métricas de cada ensayo están en
`docs/modeling/metricas/`; los modelos y las predicciones están en
`models/experimentos/`.

## Actualización selectiva del dataset

El dataset integrado (`data/silver/integrado/meteo_socio_epi_piura_2017_2025.csv`)
tiene una fila por `ubigeo`, `anio` y `semana`. El
actualizador inspecciona sus filas, completa únicamente los componentes
faltantes y conserva los valores históricos ya poblados. Los datos de clima
proceden de Open-Meteo; los demográficos, del Excel y la tabla anual local;
y los nuevos casos de dengue, de la Sala Situacional MINSA/DGE.

Instala las dependencias con `./run_setup.sh`. Desde la raíz del repositorio:

```bash
.venv/bin/python -m src.update_dataset_module \
  --input data/silver/integrado/meteo_socio_epi_piura_2017_2025.csv \
  --output data/silver/integrado/meteo_socio_epi_piura_2017_2025.csv \
  --dry-run
```

Quita `--dry-run` para efectuar la actualización. Para escribir otro archivo,
indica una ruta distinta en `--output`. El CLI informa cuántas filas necesitan
cada componente y cuáles fuentes ejecutará. Las opciones
`--force-epidemiological`, `--force-weather` y `--force-demographic` fuerzan una
actualización explícita; requieren `--start-date` y `--end-date` con los
domingos de inicio de la primera y última semana solicitadas.

El archivo `<dataset>.coverage.csv`, junto al dataset, registra las semanas
con casos verificados. Si aún no existe, el primer uso considera los valores
ya poblados como la línea base validada. Tras ello, una fila nueva sin estado
de cobertura epidemiológica se consulta en la Sala aunque tenga un cero. Una
solicitud fallida no escribe ceros de relleno ni marca cobertura exitosa.
Las columnas climáticas y demográficas se revisan por valores faltantes.
Ejecuta una vez sin `--dry-run` sobre el snapshot actual antes de agregar
semanas nuevas, para dejar creada esa línea base de cobertura.

Si solo `casos_Dengue` falta en filas nuevas, la inspección indica
`[RUN] epidemiological`, `[SKIP] weather` y `[SKIP] demographic`.

El scraper reutilizable vive en `src/ingestion/scrape_minsa_dengue.py`. Sus
respuestas y exportaciones normalizadas se guardan como artefactos de ejecución
en `data/bronze/epi/sala/` y `data/silver/epi_sala_semanal.csv`; ninguno es
necesario en Git para ejecutar el actualizador. El catálogo pequeño de UBIGEO
vive en `data/reference/` y sí se versiona.

## Alcance y procedencia

El snapshot actual conserva los casos históricos del Excel epidemiológico
hasta 2024. Para 2025, las 3 380 filas de semanas 1–52 suman **1 114** casos
de la Sala. Sus **3** casos de semana 53 se mantienen en el artefacto de
fuente porque esa semana no corresponde a una fila completa de clima del
modelo. La trazabilidad original está en el archivo local
`trazabilidad_scraper_dengue_piura_2025.zip`.

La documentación de esa extracción señala una discrepancia no resuelta:
otro panel registró 12 067 casos para semanas 1–52 de 2025. El actualizador
usa la serie de la Sala para las nuevas consultas, sin mezclar ambos conteos.
Para la tesis, Rosa confirmó que los casos de la Sala son una fuente de verdad
válida; el cambio de procedencia se registra y no determina por sí solo el
corte de entrenamiento o prueba.

Los valores demográficos de 2017–2025 se conservan. Para filas nuevas de
2026 en adelante, se extrapola la tendencia de los extremos 2017 y 2025;
las fracciones se acotan a `[0, 1]` con un registro de cada ajuste, y la
población se redondea a un entero positivo. No se recalculan filas históricas
salvo con una opción de actualización forzada.
