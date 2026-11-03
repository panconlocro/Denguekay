# 06 · Mejora del modelo sobre la V2

- **Pregunta:** ¿hay una V3 que supere a la V2 (`CONFIG_2026`) con una regla preregistrada y una evaluación
  menos optimista? Hipótesis de trabajo: el cuello de botella es la poca historia, no la arquitectura.
- **Plan:** [docs/plan.md](docs/plan.md) (fases 0 a 7; cada una se cierra con el visto bueno de Rosa).
- **Estado:** en curso, rama `exp/model-improvement`. Fases 0 y 1a cerradas (se adopta entrenar desde 2005). 1b
  (clima 2000–2016) espera la descarga del equipo; fase 2 (calibración) en preregistro.
- **Tag:** `study/model-improvement` al cerrar.

## Contenido

| Carpeta | Qué hay |
|---|---|
| `notebooks/` | `01_diagnostico_techo.ipynb` (fase 0), `02_fase1a_historia.ipynb` (1a), `03_fase1b_consistencia_clima.ipynb` (1b, consistencia del clima; lo corre el equipo) |
| `code/` | `phase0_diagnosis.py`, `preregistration.py`, `phase1_history.py`, `phase1b_climate.py` |
| `tests/` | `test_phase0_diagnosis.py`, `test_preregistration.py`, `test_phase1_history.py`, `test_phase1b_climate.py` |
| `docs/` | `plan.md`, `mejora_modelo.md` (informe), `metricas/fase0.json`, `metricas/fase1a.json` y `figuras/fase0/` |

Experimentos de MLflow: `denguekay/mejora_modelo_fase0_diagnostico` y `denguekay/mejora_modelo_fase1a_historia`.

## Cómo reproducir

Desde la raíz del repositorio, con `data/` completo y las predicciones de la V2 del estudio 05 en
`models/experimentos/fe_hiperparametros/complemento_clima/` (no versionadas):

```powershell
.\.venv\Scripts\python -m unittest discover -s research/06_model_improvement/tests
.\.venv\Scripts\python -m jupyter nbconvert --to notebook --execute --inplace research/06_model_improvement/notebooks/01_diagnostico_techo.ipynb
.\.venv\Scripts\python -m jupyter nbconvert --to notebook --execute --inplace research/06_model_improvement/notebooks/02_fase1a_historia.ipynb
```

La 1a deja sus predicciones en `models/experimentos/mejora_modelo/fase1a/` (no versionadas). El notebook 03
necesita antes el caché `data/bronze/meteo/cache_meteo_era5_2017_2025/` (celda A de
`pipelines/notebooks/02_ingesta_meteo.ipynb`).
