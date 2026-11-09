# 06 · Mejora del modelo sobre la V2

- **Pregunta:** ¿hay una V3 que supere a la V2 (`CONFIG_2026`) con una regla preregistrada y una evaluación
  menos optimista? Hipótesis de trabajo: el cuello de botella es la poca historia, no la arquitectura.
- **Plan:** [docs/plan.md](docs/plan.md) (fases 0 a 7; cada una se cierra con el visto bueno de Rosa).
- **Decisión:** **V3** = L + 5a + d3 con los hiperparámetros del trial 191, congelada el 2026-11-09
  (`CONFIG_V3`, ficha [`models/registry/v3/ficha.md`](../../models/registry/v3/ficha.md), tag `model/v3`). b3
  queda como retadora para la evaluación prospectiva 2026–27. Protocolo en
  [`docs/modeling/protocolo_v3.md`](../../docs/modeling/protocolo_v3.md).
- **Estado:** **cerrado** (2026-11-09). Antes del cierre, rama `exp/model-improvement`. Fases 0, 1a y 2 cerradas; fase 3 cerrada (ninguna variante se adopta); fase 5: se adopta la mezcla del conteo con la persistencia (5a); fase 6 (lectura) cerrada: LightGBM empata con L + 5a y el GLM Poisson de la enmienda 6a′ empata o mejora (nada se adopta) (se entrena desde 2005; la calibración
  se queda en Platt por horizonte con 1e-6). 1b (clima 2000–2016) espera la descarga del equipo.
- **Tag:** `study/model-improvement` (el mismo commit que `model/v3`).

## Contenido

Después de la fase 1b′ se agregaron:

- **Notebooks:** 12 (lluvia CHIRPS), 13 (b3), 14 (ventanas d), 15 (temporada 2026), 16 (matriz de clima),
  17 (diagnóstico frente a la persistencia), 18 (alerta combinada) y 19 (ajuste de hiperparámetros).
- **Código:** `phase_b_rain.py`, `phase_b3_full_climate.py`, `phase_d_weather_windows.py`, `phase_2026.py`,
  `phase_climate_matrix.py`, `diagnosis_persistence.py`, `phase_combined_alert.py`, `phase_hp_tuning.py` y
  `phase_v3_close.py` (corrida de cierre de la V3 y paquetes del Release).
- **Métricas:** `paso_b`, `paso_b3`, `paso_d`, `datos_2026`, `temporada_2026`, `matriz_clima`,
  `diagnostico_persistencia`, `alerta_combinada`, `ajuste_hp` y `v3`.

La tabla de abajo es la de las primeras fases.

| Carpeta | Qué hay |
|---|---|
| `notebooks/` | `01_diagnostico_techo.ipynb` (fase 0), `02_fase1a_historia.ipynb` (1a), `03_fase1b_consistencia_clima.ipynb` (1b, consistencia del clima; lo corre el equipo), `04_fase2_calibracion.ipynb` (fase 2), `05_fase3_inicios.ipynb` (fase 3: 3a1, 3a2 y 3b), `06_fase3c_contexto_espacial.ipynb` (3c′), `07_fase5_conteo.ipynb` (fase 5), `08_fase6_otras_familias.ipynb` (fase 6, lectura), `09_fase6a_prima_glm_poisson.ipynb` (enmienda 6a′), `10_fase4_nino.ipynb` (fase 4), `11_fase1b_prima_humedad.ipynb` (1b′) |
| `code/` | `phase0_diagnosis.py`, `preregistration.py`, `phase1_history.py`, `phase1b_climate.py`, `phase2_calibration.py`, `phase3_onsets.py`, `phase5_counts.py`, `phase6_other_families.py`, `phase4_enso.py`, `phase1b_prime.py` |
| `tests/` | `test_phase0_diagnosis.py`, `test_preregistration.py`, `test_phase1_history.py`, `test_phase1b_climate.py`, `test_phase2_calibration.py`, `test_phase3_onsets.py`, `test_phase5_counts.py`, `test_phase6_other_families.py`, `test_phase4_enso.py`, `test_phase1b_prime.py` |
| `docs/` | `plan.md`, `mejora_modelo.md` (informe), `metricas/fase0.json`, `metricas/fase1a.json`, `metricas/fase2.json`, `metricas/fase3.json`, `metricas/fase3c.json`, `metricas/fase5.json`, `metricas/fase6.json`, `metricas/fase4.json`, `metricas/fase1b_prima.json`, `metricas/fase1b_consistencia.json` y `figuras/fase0/` |

Experimentos de MLflow: `denguekay/mejora_modelo_fase0_diagnostico` `denguekay/mejora_modelo_fase1a_historia` ,
`denguekay/mejora_modelo_fase2_calibracion` , `denguekay/mejora_modelo_fase3_inicios` `denguekay/mejora_modelo_fase5_conteo` `denguekay/mejora_modelo_fase6_otras_familias` `denguekay/mejora_modelo_fase4_nino` y `denguekay/mejora_modelo_fase1b_prima_humedad`.

## Dependencias fuera de `requirements.txt`

La fase 6 usa LightGBM, que el producto no necesita: se instala solo en el `.venv`, con la versión fijada
(`statsmodels` ya está en `requirements.txt`; la fase 6 corrió con la 0.15.0):

```powershell
.\.venv\Scripts\python -m pip install lightgbm==4.7.0
```

## Cómo reproducir

**La V3 desde un clon limpio** (sin `data/` local): sigue
[`docs/modeling/reproducir_v3.md`](../../docs/modeling/reproducir_v3.md).

- Crea el entorno con `constraints.txt` y descarga los datos del Release con
  `python -m denguekay.data.ingestion.release_bundles`.
- Reentrena con `python research/06_model_improvement/code/phase_v3_close.py verificar --semilla 17` y comprueba
  la huella (sin argumentos corre `cierre`, que sobrescribe las predicciones de referencia: no la uses para verificar).

Desde el tag:

```powershell
git switch --detach study/model-improvement
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt -c constraints.txt
.\.venv\Scripts\python -m pip install -e . -c constraints.txt
.\.venv\Scripts\python -m denguekay.data.ingestion.release_bundles
.\.venv\Scripts\python research/06_model_improvement/code/phase_v3_close.py verificar --semilla 17
```

Los notebooks 01–19 son la historia del estudio. Sus insumos están en los Releases (no en otra PC):

```powershell
.\.venv\Scripts\python -m denguekay.data.ingestion.release_bundles --version v3
.\.venv\Scripts\python -m denguekay.data.ingestion.release_bundles --version v2
.\.venv\Scripts\python -m denguekay.data.ingestion.release_bundles --estudio 06_model_improvement
```

- `--version v3`: entradas de datos, predicciones de la V3 y comparadores.
- `--version v2`: las predicciones de la V2 del estudio 05 (`fe_hiperparametros/complemento_clima/`).
- `--estudio 06_model_improvement`: el estudio de Optuna del ajuste (`ajuste_hp/optuna.db`), las predicciones por
  fase y los cachés bronze (ERA5, ERA5-Land, Open-Meteo, CHIRPS por FTP, NOAA y polígonos de HDX).

**No vuelvas a correr las búsquedas largas:** el ajuste de hiperparámetros (`code/phase_hp_tuning.py`, tope de
10 h) quedó guardado en `optuna.db`, y el notebook 19 lo lee de ahí. Las corridas que reentrenan (matriz de clima,
temporada 2026, cierre) se reutilizan desde las predicciones guardadas cuando la guarda G41 lo permite.

Después, desde la raíz:

```powershell
.\.venv\Scripts\python -m unittest discover -s research/06_model_improvement/tests
.\.venv\Scripts\python -m jupyter nbconvert --to notebook --execute --inplace research/06_model_improvement/notebooks/01_diagnostico_techo.ipynb
.\.venv\Scripts\python -m jupyter nbconvert --to notebook --execute --inplace research/06_model_improvement/notebooks/02_fase1a_historia.ipynb
.\.venv\Scripts\python -m jupyter nbconvert --to notebook --execute --inplace research/06_model_improvement/notebooks/04_fase2_calibracion.ipynb
.\.venv\Scripts\python -m jupyter nbconvert --to notebook --execute --inplace research/06_model_improvement/notebooks/05_fase3_inicios.ipynb
.\.venv\Scripts\python -m jupyter nbconvert --to notebook --execute --inplace research/06_model_improvement/notebooks/06_fase3c_contexto_espacial.ipynb
.\.venv\Scripts\python -m jupyter nbconvert --to notebook --execute --inplace research/06_model_improvement/notebooks/07_fase5_conteo.ipynb
.\.venv\Scripts\python -m jupyter nbconvert --to notebook --execute --inplace research/06_model_improvement/notebooks/08_fase6_otras_familias.ipynb
.\.venv\Scripts\python -m jupyter nbconvert --to notebook --execute --inplace research/06_model_improvement/notebooks/09_fase6a_prima_glm_poisson.ipynb
.\.venv\Scripts\python -m jupyter nbconvert --to notebook --execute --inplace research/06_model_improvement/notebooks/10_fase4_nino.ipynb
.\.venv\Scripts\python -m jupyter nbconvert --to notebook --execute --inplace research/06_model_improvement/notebooks/11_fase1b_prima_humedad.ipynb
```

La 1a deja sus predicciones en `models/experimentos/mejora_modelo/fase1a/` (no versionadas). El notebook 03
necesita antes el caché `data/bronze/meteo/cache_meteo_era5_2017_2025/` (celda A de
`pipelines/notebooks/02_ingesta_meteo.ipynb`).
