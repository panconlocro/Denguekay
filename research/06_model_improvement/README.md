# 06 · Mejora del modelo sobre la V2

- **Pregunta:** ¿hay una V3 que supere a la V2 (`CONFIG_2026`) con una regla preregistrada y una evaluación
  menos optimista? Hipótesis de trabajo: el cuello de botella es la poca historia, no la arquitectura.
- **Plan:** [docs/plan.md](docs/plan.md) (fases 0 a 7; cada una se cierra con el visto bueno de Rosa).
- **Estado:** en curso, rama `exp/model-improvement`. Fases 0, 1a y 2 cerradas; fase 3 cerrada (ninguna variante se adopta); fase 5: se adopta la mezcla del conteo con la persistencia (5a) (se entrena desde 2005; la calibración
  se queda en Platt por horizonte con 1e-6). 1b (clima 2000–2016) espera la descarga del equipo.
- **Tag:** `study/model-improvement` al cerrar.

## Contenido

| Carpeta | Qué hay |
|---|---|
| `notebooks/` | `01_diagnostico_techo.ipynb` (fase 0), `02_fase1a_historia.ipynb` (1a), `03_fase1b_consistencia_clima.ipynb` (1b, consistencia del clima; lo corre el equipo), `04_fase2_calibracion.ipynb` (fase 2), `05_fase3_inicios.ipynb` (fase 3: 3a1, 3a2 y 3b), `06_fase3c_contexto_espacial.ipynb` (3c′), `07_fase5_conteo.ipynb` (fase 5) |
| `code/` | `phase0_diagnosis.py`, `preregistration.py`, `phase1_history.py`, `phase1b_climate.py`, `phase2_calibration.py`, `phase3_onsets.py`, `phase5_counts.py` |
| `tests/` | `test_phase0_diagnosis.py`, `test_preregistration.py`, `test_phase1_history.py`, `test_phase1b_climate.py`, `test_phase2_calibration.py`, `test_phase3_onsets.py`, `test_phase5_counts.py` |
| `docs/` | `plan.md`, `mejora_modelo.md` (informe), `metricas/fase0.json`, `metricas/fase1a.json`, `metricas/fase2.json`, `metricas/fase3.json`, `metricas/fase3c.json`, `metricas/fase5.json` y `figuras/fase0/` |

Experimentos de MLflow: `denguekay/mejora_modelo_fase0_diagnostico` `denguekay/mejora_modelo_fase1a_historia` ,
`denguekay/mejora_modelo_fase2_calibracion` , `denguekay/mejora_modelo_fase3_inicios` y `denguekay/mejora_modelo_fase5_conteo`.

## Dependencias fuera de `requirements.txt`

La fase 6 usa LightGBM, que el producto no necesita: se instala solo en el `.venv`, con la versión fijada
(`statsmodels` ya está en `requirements.txt`; la fase 6 corrió con la 0.15.0):

```powershell
.\.venv\Scripts\python -m pip install lightgbm==4.7.0
```

## Cómo reproducir

Desde la raíz del repositorio, con `data/` completo y las predicciones de la V2 del estudio 05 en
`models/experimentos/fe_hiperparametros/complemento_clima/` (no versionadas):

```powershell
.\.venv\Scripts\python -m unittest discover -s research/06_model_improvement/tests
.\.venv\Scripts\python -m jupyter nbconvert --to notebook --execute --inplace research/06_model_improvement/notebooks/01_diagnostico_techo.ipynb
.\.venv\Scripts\python -m jupyter nbconvert --to notebook --execute --inplace research/06_model_improvement/notebooks/02_fase1a_historia.ipynb
.\.venv\Scripts\python -m jupyter nbconvert --to notebook --execute --inplace research/06_model_improvement/notebooks/04_fase2_calibracion.ipynb
.\.venv\Scripts\python -m jupyter nbconvert --to notebook --execute --inplace research/06_model_improvement/notebooks/05_fase3_inicios.ipynb
.\.venv\Scripts\python -m jupyter nbconvert --to notebook --execute --inplace research/06_model_improvement/notebooks/06_fase3c_contexto_espacial.ipynb
.\.venv\Scripts\python -m jupyter nbconvert --to notebook --execute --inplace research/06_model_improvement/notebooks/07_fase5_conteo.ipynb
```

La 1a deja sus predicciones en `models/experimentos/mejora_modelo/fase1a/` (no versionadas). El notebook 03
necesita antes el caché `data/bronze/meteo/cache_meteo_era5_2017_2025/` (celda A de
`pipelines/notebooks/02_ingesta_meteo.ipynb`).
