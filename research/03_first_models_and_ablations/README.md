# 03 · Primeros modelos XGBoost y ablaciones

- **Pregunta:** ¿regresión de log1p(casos) con regla de alerta o clasificación directa de `brote`?
  ¿Aportan los bloques de vecinos, clima y sociodemografía? ¿Qué matriz compacta elegir con una
  validación temporal progresiva?
- **Decisión (provisional):** regresión con `base_6` y clasificación con `base_6_poblacion_2017`, en
  h=2 y h=4 ([validacion_temporal_compacta.md](docs/validacion_temporal_compacta.md), «Decisión
  provisional y límites»). Las ablaciones no respaldaron añadir clima ni contexto espacial por
  defecto ([ablacion_clima.md](docs/ablacion_clima.md), [ablacion_espacial.md](docs/ablacion_espacial.md),
  [ablacion_sociodemografica.md](docs/ablacion_sociodemografica.md),
  [ablacion_fracciones.md](docs/ablacion_fracciones.md),
  [ablacion_poblacion_sin_seguro.md](docs/ablacion_poblacion_sin_seguro.md)).
- **Versión de modelo resultante:** **V0**, la que se sirve hoy: 4 XGBoost experimentales E1·S1
  (`clf-h2-v1`, `reg-h2-v1`, `clf-h4-v1`, `reg-h4-v1`), sin h=3; ninguno cumple HU0007-4
  (tag `model/v0`, `3d59090`).
- **Tag del estudio:** `archive/training` (`573219d`). Contiene los notebooks 24–30 y todo su código.
  Alternativa: `pre-restructure` (`3ad8312`).

## Contenido

| Carpeta | Qué hay |
|---|---|
| `notebooks/` | 24 (dos objetivos), 25–29 (ablaciones), 30 (validación temporal compacta) |
| `code/` | los cinco `ablacion_*.py` |
| `tests/` | sus cinco tests |
| `docs/` | `primer_xgboost.md`, los cinco informes de ablación, `validacion_temporal_compacta.md`, el inventario previo a MLflow y `metricas/` |

Lo que sigue en `src/`, porque lo usa el producto: `train.py`, `evaluate.py`, `contrato_xgboost.py`,
`validacion_temporal_compacta.py` y `seguimiento_mlflow.py`. También se quedan
`docs/modeling/metricas/validacion_temporal_compacta.json` y
`models/experimentos/validacion_temporal_compacta/`, que serving lee para V0; pasan a
`models/registry/v0/` en la fase 4 (decisión D5).

Experimentos de MLflow: `denguekay/primer_xgboost`, `denguekay/ablacion_*` y
`denguekay/validacion_temporal_compacta`.

## Cómo reproducir

```powershell
git worktree add ..\denguekay-training archive/training
cd ..\denguekay-training
# data/ no está en git: copia (o enlaza) la carpeta data/ del repo principal.
python -m venv .venv   # entorno propio: las dependencias pueden diferir de las de main
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m src.modeling.train
.\.venv\Scripts\python -m src.modeling.validacion_temporal_compacta
```

Las ablaciones se corren igual (`-m src.modeling.ablacion_espacial`, etc.). `train.py` y
`seguimiento_mlflow.py` cambiaron después de este tag: corrección del calendario de 2025, horizontes
generalizados y deduplicación de runs en MLflow. `archive/training` reproduce el estudio tal como se
corrió; `pre-restructure` lo corre con el código corregido. Las cifras citadas se generaron con GPU
(`device="cuda"`). En CPU pueden cambiar decimales y, en la regresión, la matriz elegida (ver
[reproducibilidad entre equipos](docs/primer_xgboost.md#reproducibilidad-entre-equipos)).
