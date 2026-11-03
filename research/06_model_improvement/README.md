# 06 · Mejora del modelo sobre la V2

- **Pregunta:** ¿hay una V3 que supere a la V2 (`CONFIG_2026`) con una regla preregistrada y una evaluación
  menos optimista? Hipótesis de trabajo: el cuello de botella es la poca historia, no la arquitectura.
- **Plan:** [docs/plan.md](docs/plan.md) (fases 0 a 7; cada una se cierra con el visto bueno de Rosa).
- **Estado:** en curso, rama `exp/model-improvement`. Fase 0 (diagnóstico sin entrenar) hecha.
- **Tag:** `study/model-improvement` al cerrar.

## Contenido

| Carpeta | Qué hay |
|---|---|
| `notebooks/` | `01_diagnostico_techo.ipynb` (fase 0) |
| `code/` | `phase0_diagnosis.py` |
| `tests/` | `test_phase0_diagnosis.py` |
| `docs/` | `plan.md`, `metricas/fase0.json` y `figuras/fase0/` |

Experimentos de MLflow: `denguekay/mejora_modelo_fase0_diagnostico`.

## Cómo reproducir

Desde la raíz del repositorio, con `data/` completo y las predicciones de la V2 del estudio 05 en
`models/experimentos/fe_hiperparametros/complemento_clima/` (no versionadas):

```powershell
.\.venv\Scripts\python -m unittest discover -s research/06_model_improvement/tests
.\.venv\Scripts\python -m jupyter nbconvert --to notebook --execute --inplace research/06_model_improvement/notebooks/01_diagnostico_techo.ipynb
```
