# Investigación (estudios congelados)

Cada carpeta es un estudio cerrado: su pregunta, sus notebooks, el código y los tests propios del
estudio, y sus informes, métricas y figuras. Se movieron aquí **tal como estaban** en la
reestructuración ([ADR 0001](../docs/decisions/0001-repo-restructure.md)):

- no se vuelven a correr en `main`, no corren en el CI y no se garantiza que importen;
- sus resultados ya están en los informes, en `metricas/` y en MLflow (`mlflow.db` y `mlartifacts/`
  en la raíz del repo);
- las rutas escritas en el texto de sus informes y notebooks (`src/...`, `notebooks/...`,
  `docs/...`) describen el repositorio **en el tag del estudio**, no el de hoy. Los enlaces de
  Markdown sí apuntan a los archivos actuales.

Para reproducir un estudio se parte de su tag (ver el README de cada uno). `pre-restructure`
(`3ad8312`) es una alternativa válida para cualquiera de ellos.

| Estudio | Pregunta | Resultado | Tag |
|---|---|---|---|
| [01_eda](01_eda/README.md) | ¿Cómo es el panel distrito × semana y qué condiciona al modelo? | Hallazgos y recomendaciones para el feature engineering | `archive/EDA` |
| [02_feature_engineering](02_feature_engineering/README.md) | ¿Qué variables sin fuga y qué etiqueta de brote van a gold? | Gold h=2 y h=4 (`manifest_fase6.json`) | `archive/feature-engineering` |
| [03_first_models_and_ablations](03_first_models_and_ablations/README.md) | ¿Regresión o clasificación, y qué bloques de variables aportan? | **V0** (servida hoy) | `archive/training` |
| [04_horizon_architecture](04_horizon_architecture/README.md) | ¿Qué arquitectura para h=2, 3 y 4? | E3·S4_s2, base del estudio 05 | `study/horizon-architecture` |
| [05_fe_hyperparameters](05_fe_hyperparameters/README.md) | ¿Qué variables e hiperparámetros sobre E3·S4_s2? | **V1** (reemplazada) y **V2** (vigente) | `study/fe-hyperparameters` |

## Qué no está aquí

- El código que también usa el producto (protocolo, salida probabilística, tabla de orígenes,
  variables B3, umbral de brote, evaluación de variantes, tuning, configuraciones congeladas, MLflow,
  caché) sigue en `src/` y pasa al paquete `denguekay` en la fase 3 (decisión D4).
- El notebook 22 regenera gold y se queda con el pipeline (decisión D3).
- `docs/modeling/metricas/validacion_temporal_compacta.json` y las predicciones de
  `models/experimentos/validacion_temporal_compacta/` las lee serving (V0); quedan en su lugar hasta
  la fase 4 (decisión D5).
- Las salidas pesadas de los estudios (`models/experimentos/`) no se versionan y no se movieron.

## Estudios nuevos

Un estudio nuevo va en `research/06_<nombre>/` con la misma forma (`README.md`, `notebooks/`,
`code/`, `tests/`, `docs/`), importa el paquete `denguekay` y nunca al revés: el producto no
importa `research/`. Al cerrarlo se crea el tag `study/<nombre>`.
