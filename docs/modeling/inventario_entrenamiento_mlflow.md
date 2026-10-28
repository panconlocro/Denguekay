# Inventario del entrenamiento para migrar los experimentos a MLflow

> **Actualización (1 de octubre de 2026):** la migración descrita aquí ya se implementó, junto con validaciones de Great Expectations. Ver [MLflow y Great Expectations en el entrenamiento](mlflow_great_expectations.md). Este inventario se conserva como registro del estado previo.

**Estado al 30 de septiembre de 2026.** Este documento identifica los archivos que hoy preparan, ejecutan y documentan los experimentos. Es un mapa de migración; **MLflow todavía no está integrado**. La prohibición de MLflow en `CLAUDE.md` corresponde al flujo anterior de EDA; la decisión actual del equipo de migrar el entrenamiento prevalece para esta etapa.

## 1. En qué quedó el entrenamiento

Se completaron experimentos exploratorios de **dos enfoques**, cada uno para `h=2` y `h=4` semanas: XGBoost de regresión de casos seguido de la regla de alerta, y XGBoost de clasificación directa de la etiqueta `brote`. Se compararon con persistencia y se mantuvieron fijos los hiperparámetros de XGBoost. Las primeras comparaciones usaron `base_4` y `base_6`, y después se hicieron ablaciones espaciales, climáticas y sociodemográficas. El último experimento comparó tres matrices pequeñas con una calibración de umbral que solo usa etiquetas disponibles antes de cada bloque.

No se ha aprobado ni registrado un **modelo final para producción**. En el experimento progresivo, se eligió por validación 2022–2023 `base_6` para regresión (prácticamente empatada con `base_4`; según el JSON actual, generado con GPU) y `base_6 + log_poblacion_censo_2017` para clasificación, en ambos horizontes. La temporada 2024 ya se consultó varias veces y **no es un test independiente**; el año calendario 2025 contiene solo tres semanas positivas. Tampoco se ha hecho búsqueda de hiperparámetros ni se ha decidido el costo aceptable de los falsos avisos. Consultar [la explicación completa del entrenamiento](guia_para_asesor.md) y [la evaluación progresiva](validacion_temporal_compacta.md) antes de interpretar las métricas.

## 2. Flujo actual y archivos de entrada

```text
silver/integrado/meteo_socio_epi_piura_2017_2025.csv
  → notebooks 22–23 / src.modeling.features
  → gold h2 y gold h4 + manifest_fase6.json
  → auditoría del contrato XGBoost
  → notebooks 24–30 / módulos src.modeling.*
  → docs/modeling/metricas/*.json + models/experimentos/*
```

Los **notebooks 22 y 23 son del feature engineering**, no entrenan XGBoost: el 22 genera y valida `data/gold/meteo_socio_epi_piura_2017_2025_h2_gold.csv` y `..._h4_gold.csv`; el 23 audita las variables y el traspaso. El [manifiesto de fase 6](../../data/gold/manifest_fase6.json) registra el linaje de gold. Los CSV de `data/gold/` y los modelos/predicciones de `models/experimentos/` están ignorados por Git; deben estar disponibles por separado para reproducir resultados después del push. Los JSON de métricas y los informes en `docs/modeling/` sí son texto versionable.

Cada fila de gold es una distrito-semana **objetivo** `(ubigeo, anio, semana)`. El origen de pronóstico es `t−h`; las variables de casos, clima y vecinos no pueden usar semanas posteriores a ese origen. `casos_Dengue` y `brote` son objetivos, no predictores. Las primeras semanas con historia incompleta permanecen en gold y se apartan de las matrices correspondientes; no se rellenan con cero.

## 3. Notebooks que ejecutan el entrenamiento

Los notebooks son **orquestadores y tablas de inspección**: importan una función `ejecutar_*` de `src/modeling/` y muestran resúmenes. La lógica y la escritura de artefactos residen en los módulos Python. En una migración a MLflow conviene instrumentar esos módulos, para que una ejecución por CLI y una ejecución desde notebook registren lo mismo.

| Notebook | Módulo invocado | Qué compara |
|---|---|---|
| [`24_modelado_xgboost_dos_objetivos.ipynb`](../../notebooks/24_modelado_xgboost_dos_objetivos.ipynb) | [`train.py`](../../src/modeling/train.py): `ejecutar_experimento()` | Primer XGBoost: `base_4`/`base_6`, regresión, clasificación y persistencia; h=2/4. |
| [`25_modelado_ablacion_espacial.ipynb`](../../notebooks/25_modelado_ablacion_espacial.ipynb) | [`ablacion_espacial.py`](../../src/modeling/ablacion_espacial.py): `ejecutar_ablacion_espacial()` | Base frente a vecinos, jerarquía provincia/región y combinación. |
| [`26_modelado_ablacion_clima.ipynb`](../../notebooks/26_modelado_ablacion_clima.ipynb) | [`ablacion_clima.py`](../../src/modeling/ablacion_clima.py): `ejecutar_ablacion_clima()` | Base frente a clima observado, anomalías por fold y combinación. |
| [`27_modelado_ablacion_sociodemografica.ipynb`](../../notebooks/27_modelado_ablacion_sociodemografica.ipynb) | [`ablacion_sociodemografica.py`](../../src/modeling/ablacion_sociodemografica.py): `ejecutar_ablacion_sociodemografica()` | Población, fracciones y eje urbano; rasgos fijos de 2017 frente a reconstrucciones anuales retrospectivas. |
| [`28_modelado_ablacion_fracciones.ipynb`](../../notebooks/28_modelado_ablacion_fracciones.ipynb) | [`ablacion_fracciones.py`](../../src/modeling/ablacion_fracciones.py): `ejecutar_ablacion_fracciones()` | Las 15 fracciones fijas y las 15 anuales, una por vez sobre la base. |
| [`29_modelado_ablacion_poblacion_sin_seguro.ipynb`](../../notebooks/29_modelado_ablacion_poblacion_sin_seguro.ipynb) | [`ablacion_poblacion_sin_seguro.py`](../../src/modeling/ablacion_poblacion_sin_seguro.py): `ejecutar_ablacion_poblacion_sin_seguro()` | Base, población censal, fracción sin seguro y ambas juntas. |
| [`30_modelado_validacion_temporal_compacta.ipynb`](../../notebooks/30_modelado_validacion_temporal_compacta.ipynb) | [`validacion_temporal_compacta.py`](../../src/modeling/validacion_temporal_compacta.py): `ejecutar_validacion_temporal_compacta()` | `base_4`, `base_6` y `base_6 + población`, con calibración temporal progresiva. |

## 4. Módulos Python y responsabilidad

### Núcleo compartido

| Archivo | Responsabilidad actual | Punto de migración |
|---|---|---|
| [`train.py`](../../src/modeling/train.py) | `PARAMETROS_BASE`, preparación de gold, cortes de temporada y año calendario, ajuste, predicción y primer experimento. Un modelo nuevo se entrena antes del primer origen de cada bloque y queda fijo dentro de ese bloque. | Registrar parámetros, horizonte, variante, columnas, corte, tamaño train/test, modelo por fold y predicciones. Conservar esta lógica de corte como fuente única. |
| [`evaluate.py`](../../src/modeling/evaluate.py) | Regla de alerta para conteos; MAE/RMSE, precisión, recall, F1, AUPRC; selección del umbral F1. | Registrar métricas **por bloque y objetivo**, junto al umbral aplicado. No sustituir este cálculo por una métrica con definición distinta sin explicitarlo. |
| [`contrato_xgboost.py`](../../src/modeling/contrato_xgboost.py) | Familias de candidatas, exclusiones y auditoría de esquema, llaves, hashes y linaje de gold. | Ejecutar la auditoría antes de abrir un run; registrar hashes y versión del manifiesto como tags o artefacto. |
| [`validacion_temporal_compacta.py`](../../src/modeling/validacion_temporal_compacta.py) | Matrices pequeñas y calibración de umbral con predicciones previas disponibles al primer origen de cada temporada. | Mantener separado el protocolo progresivo del umbral agregado de los ensayos iniciales. Registrar la política de calibración y las temporadas usadas. |

### Experimentos de variables

| Archivo | Responsabilidad actual |
|---|---|
| [`ablacion_espacial.py`](../../src/modeling/ablacion_espacial.py) | Valida columnas espaciales, entrena variantes y elige por F1 medio de validación. |
| [`ablacion_clima.py`](../../src/modeling/ablacion_clima.py) | Prepara filas comunes; ajusta anomalías climáticas dentro de cada fold. |
| [`ablacion_sociodemografica.py`](../../src/modeling/ablacion_sociodemografica.py) | Compara rasgos fijos y anuales; calcula eje urbano por fold. |
| [`ablacion_fracciones.py`](../../src/modeling/ablacion_fracciones.py) | Criba las 15 fracciones una a una, en versiones fijas y anuales. |
| [`ablacion_poblacion_sin_seguro.py`](../../src/modeling/ablacion_poblacion_sin_seguro.py) | Comparación condicional de población y fracción sin seguro. |

### Dependencias de preparación y validación, sin entrenamiento XGBoost

| Archivo(s) | Uso en el flujo |
|---|---|
| [`features.py`](../../src/modeling/features.py), [`etiqueta_brote.py`](../../src/modeling/etiqueta_brote.py), [`historia_calendario.py`](../../src/modeling/historia_calendario.py), [`vecinos_jerarquia.py`](../../src/modeling/vecinos_jerarquia.py), [`clima.py`](../../src/modeling/clima.py), [`sociodemografia.py`](../../src/modeling/sociodemografia.py) | Construyen los gold y las variables que las ablaciones consumen o recalculan por fold. |
| [`contrato_pronostico.py`](../../src/validation/contrato_pronostico.py) y [`expectations_integrado.py`](../../src/validation/expectations_integrado.py) | Reglas de llave, fechas, disponibilidad y calidad de entradas. |
| [`temporal.py`](../../src/eda/temporal.py), [`carga.py`](../../src/eda/carga.py), [`socio_interpolacion.py`](../../src/processing/socio_interpolacion.py), [`paths.py`](../../src/utils/paths.py) | Asignación de temporadas, carga, fuente demográfica y rutas compartidas. |

Los diagnósticos `src/modeling/diagnostico.py`, `diagnostico_clima.py` y `diagnostico_socio.py` pertenecen a las comparaciones exploratorias de **feature engineering con ridge**, anteriores a los XGBoost de los notebooks 24–30. Conviene conservar esa distinción en MLflow si se importan experimentos históricos.

## 5. Resultados y artefactos existentes

| Experimento | Métricas versionables | Artefactos generados, ignorados por Git |
|---|---|---|
| Primer XGBoost | [`primer_xgboost.json`](metricas/primer_xgboost.json) y [`primer_xgboost.md`](primer_xgboost.md) | `models/experimentos/`: modelos XGBoost y `predicciones_por_fold.csv`. |
| Espacio | [`ablacion_espacial.json`](metricas/ablacion_espacial.json) y [`ablacion_espacial.md`](ablacion_espacial.md) | `models/experimentos/ablacion_espacial/`. |
| Clima | [`ablacion_clima.json`](metricas/ablacion_clima.json) y [`ablacion_clima.md`](ablacion_clima.md) | `models/experimentos/ablacion_clima/`. |
| Sociodemografía | [`ablacion_sociodemografica.json`](metricas/ablacion_sociodemografica.json) y [`ablacion_sociodemografica.md`](ablacion_sociodemografica.md) | `models/experimentos/ablacion_sociodemografica/`. |
| Fracciones | [`ablacion_fracciones.json`](metricas/ablacion_fracciones.json) y [`ablacion_fracciones.md`](ablacion_fracciones.md) | `models/experimentos/ablacion_fracciones/`. |
| Población y sin seguro | [`ablacion_poblacion_sin_seguro.json`](metricas/ablacion_poblacion_sin_seguro.json) y [`ablacion_poblacion_sin_seguro.md`](ablacion_poblacion_sin_seguro.md) | `models/experimentos/ablacion_poblacion_sin_seguro/`. |
| Evaluación progresiva | [`validacion_temporal_compacta.json`](metricas/validacion_temporal_compacta.json) y [`validacion_temporal_compacta.md`](validacion_temporal_compacta.md) | `models/experimentos/validacion_temporal_compacta/predicciones_por_bloque.csv`; este módulo no guarda modelos. |

Los módulos de ablación guardan predicciones de validación y prueba, además de los modelos seleccionados; algunos comprimen la predicción de validación. Los JSON ya incluyen gran parte del linaje (hashes de gold, y de silver cuando aplica), cortes, variables y métricas. **No equivalen a un tracking server**: el historial actual se consulta mediante archivos y no hay un registro de runs de MLflow.

## 6. Contrato recomendado para la futura migración a MLflow

Sin cambiar ahora el protocolo estadístico, cada **run de fold** debería permitir reconstruir una comparación:

- **Identidad:** experimento (`base`, `espacial`, `clima`, etc.), horizonte `h`, enfoque (`regresion` o `clasificacion`), variante, bloque (`temporada_2021`…`temporada_2024` o `calendario_2025`) y semilla.
- **Datos y código:** hash de cada gold y de `manifest_fase6.json`, versión de código/commit, lista ordenada de predictores, número de filas y positivos train/test, primera y última semana objetivo, corte de ajuste y versión de XGBoost.
- **Ajuste:** `PARAMETROS_BASE`, objetivo de XGBoost, transformación `log1p` para regresión, método de selección de variante y política de umbral. Registrar explícitamente si el umbral viene de 2021–2023 agregados o de calibración progresiva.
- **Métricas:** MAE/RMSE de casos cuando corresponda; VP, FP, FN, precisión, recall, F1 y AUPRC de alerta; persistencia en el mismo bloque. Mantener métricas separadas por temporada, sin un promedio que oculte los tres positivos de 2025.
- **Artefactos:** modelo del fold cuando se guarda, predicciones por distrito-semana con llaves y fechas, reporte JSON y columnas usadas. Los archivos actuales pueden importarse como referencia histórica, pero no se debe describir un experimento antiguo como si hubiese sido ejecutado originalmente con MLflow.

Es razonable usar un run padre por experimento/variante y runs hijos por `h × enfoque × bloque`; esa estructura aún es **una propuesta de migración**, no código implementado. Se deben conservar los cortes temporales y los resultados de referencia al instrumentar; la primera prueba de la migración debería comparar métricas y predicciones de una corrida antes/después. Evitar registrar como modelo final una variante elegida con 2024, porque ese bloque ya participó en la exploración.

## 7. Comprobación antes del push y reproducción

1. Versionar los notebooks 24–30, `src/modeling/*.py`, `docs/modeling/*.md`, `docs/modeling/metricas/*.json` y los tests correspondientes. En este checkout varios de ellos todavía aparecen como **no rastreados**: un `git push` por sí solo no los incluirá; hay que agregarlos y confirmarlos en un commit.
2. No esperar que el push incluya automáticamente `data/gold/*.csv` ni `models/experimentos/`: `.gitignore` excluye esos artefactos. Para reproducirlos se necesita el silver local y ejecutar la fase 6, y después los módulos de modelado.
3. Comprobar el contrato y tests con `.venv/bin/python -m unittest discover -s tests`. Los módulos de los notebooks también admiten `python -m src.modeling.train` y sus equivalentes `python -m src.modeling.ablacion_*` / `python -m src.modeling.validacion_temporal_compacta`, con argumentos de ruta opcionales. Ejecutarlos **vuelve a entrenar y escribir salidas**, por lo que no son una verificación de solo lectura.

Este inventario no aprueba una nueva fase de modelado ni instala MLflow. Define qué conservar al efectuar la migración solicitada.
