# 09 · Re-analysis for the *Epidemics* revision

Se conserva en inglés el material original del estudio destinado al artículo (protocolos, notebooks, informes y figuras). Las aclaraciones de reproducción que siguen están en español. Todavía no hay tag de cierre del estudio 09: estas instrucciones corresponden a la revisión de Git que contiene este README.

- **Question:** does climate improve 2–4-week district dengue forecasts in Piura beyond case history and geography, once weather is limited to what was published at the forecast origin? And are the paper's results robust to the evaluation seasons, the aggregation, the calibration, the case definition and the outcome definition?
- **Protocol:** [protocolo.md](protocolo.md), written before the runs, with a dated amendment section after the first run. E8 follows a separate addendum, [protocolo_e8.md](protocolo_e8.md), written after E1–E7. E9–E13 follow [protocolo_revision.md](protocolo_revision.md), written after E1–E8 in response to external feedback (exploratory); the E11 event measures follow its [amendment 1](protocolo_revision_enmienda_1.md), written after a second review.
- **Data:** ten inputs, including the rebuilt district geography, match the SHA-256 recorded in [manifiesto_b3_v4.json](../08_v3_confirmed_cases/manifiesto_b3_v4.json). The original run used a local delivery named `data/data 5/`; that folder is not distributed or required by the code.
- **Code:** `code/`. It reuses study 08's functions without modifying them (`run_spatial_controls`, `run_experiment`, `evaluate_climate_without_history`, `run_statistical_benchmarks`).

## Verificar las tablas del artículo sin reentrenar

El paquete mínimo está incluido en [paper/](paper/README.md): `reproduce.py`, `manifest.json`, `predictions.csv.gz`, `main.tex` y `supplement.tex`. Su procedencia y sus sumas SHA-256 están documentadas allí. No requiere carpetas externas, descargar datos ni instalar dependencias adicionales a Python.

Desde la raíz del repositorio, con Python 3.12 disponible como `python` (o `py -3.12` en Windows):

```bash
python research/09_epidemics_revision/paper/reproducibility/reproduce.py --main-tex research/09_epidemics_revision/paper/main.tex --supplement-tex research/09_epidemics_revision/paper/supplement.tex --out models/experimentos/revision_epidemics/reproduced_paper
```

El script verifica el SHA-256 de las predicciones y coteja las tablas II y S16 y la sensibilidad sin 2026 con los textos del artículo. El notebook `01_reproduction_check` usa el mismo paquete mediante `PAPER_BUNDLE`, definido en [src/denguekay/config/paths.py](../../src/denguekay/config/paths.py).

## Run

El reentrenamiento necesita además los insumos de los estudios previos en `data/`. El [Release model/v4](https://github.com/panconlocro/Denguekay/releases/tag/model/v4) distribuye los paquetes de V4 y su manifiesto; consultar su `LEEME_V4.md` y las instrucciones del [estudio 08](../08_v3_confirmed_cases/README.md). El responsable de los datos debe preparar los insumos antes del análisis. `common.check_sources()` coteja las fuentes con el manifiesto de V4 (la geografía se reconstruye por separado); las sensibilidades adicionales usan también los insumos indicados en sus notebooks. Los experimentos no deben copiar ni sobrescribir `data/`.

From the repository root, with the inputs prepared and the pinned environment (macOS / Linux):

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt -c constraints.txt
.venv/bin/python -m pip install -e . -c constraints.txt
.venv/bin/python -m ipykernel install --sys-prefix --name denguekay-09
.venv/bin/python research/09_epidemics_revision/code/run_all.py
```

Windows / PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -c constraints.txt
.\.venv\Scripts\python.exe -m pip install -e . -c constraints.txt
.\.venv\Scripts\python.exe -m ipykernel install --sys-prefix --name denguekay-09
.\.venv\Scripts\python.exe research/09_epidemics_revision/code/run_all.py
```

`run_all.py` runs, in order: the leakage audit, the fits (`run_fits.py`, `run_extra.py`; cached with fingerprints under `models/experimentos/revision_epidemics/`) and every notebook. On an Apple M4 Max with CPU and two threads per fit, the full run from scratch takes about 25 minutes (E12 and E13 add about 5 minutes of fits); the fits are cached and reused on later runs.

## Notebooks

| Notebook | Content |
|---|---|
| `00_leakage_audit` | Code review, plus dynamic tests that replace the future with random values (case history, thresholds, weather, Niño 1+2), with a positive control |
| `01_reproduction_check` | Regenerated `b3_obs` / `historia_geo` against the paper's bundle; Table II and Table S16 via the paper's `reproduce.py`; training and calibration windows per block |
| `02_E1_main_comparison` | 18 seasons, pooled and equal-season, season bootstrap, six-season sensitivity, leave-one-season-out |
| `03_E2_weather_timing` | Weather lags 0, 1 and 2, and the wrong-year placebos |
| `04_E3_diagnostics` | CORP, AP, calibration, counts (MAE, RMSE, WIS) and net benefit on the fixed-hyperparameter models |
| `05_E4_calibration` | Out-of-sample NB2 dispersion and isotonic recalibration |
| `06_E5_skill_decomposition` | Four arms: geography, + climate, + case history, + both |
| `07_E6_case_and_outcome_definition` | Confirmed share, confirmed + probable, threshold without epidemic years, incidence rule |
| `08_E7_statistical_model` | NB2 regression with and without exactly the b3 block |
| `09_E8_longer_horizons` | A separate two-output model for 8 and 12 weeks ([addendum](protocolo_e8.md)), with its own leakage checks |
| `10_summary` | Headline numbers written from the result files (E1–E8) |
| `11_E9_alignments_and_development_seasons` | Weather alignments compared directly; the six development seasons against the other twelve |
| `12_E10_count_uncertainty` | Intervals for the count MAE change, by season, origin state and with one season left out |
| `13_E11_onset_and_continuation` | Brier score by origin state (quiet / active), onset detection, warning time and false alarms, district example |
| `14_E12_reporting_delays` | Primary pair refitted with simulated reporting delays (`code/reporting_delays.py`) |
| `15_E13_direct_classifier` | Primary pair with a direct classifier of elevated weeks (`code/direct_classifier.py`, formulation S3) |

Results are in `models/experimentos/revision_epidemics/resultados/` (generated CSV, not versioned) and [figures/](figures/) (eight PNG files included in the repository).

## Results

See [RESULTS.md](RESULTS.md) for the findings and what they mean for the manuscript. [RESULTS_TABLES.md](RESULTS_TABLES.md) has the full tables, generated from the CSV outputs by `code/write_results.py`.

## Referencias internas de los protocolos

Los siguientes nombres citados en los protocolos identifican documentos internos del proceso editorial, no archivos distribuidos ni enlaces de descarga:

| Documento interno | Protocolo que conserva la referencia |
|---|---|
| `Denguekay_experiment_plan.md` | [protocolo.md](protocolo.md) |
| `denguekay_epidemics_latex/review_feedback.md` | [protocolo_revision.md](protocolo_revision.md) |
| `denguekay_epidemics_latex/submission_readiness_review.md` | [protocolo_revision_enmienda_1.md](protocolo_revision_enmienda_1.md) |

Las decisiones ejecutables están recogidas en los protocolos versionados; los documentos internos no son entradas del código. Se conservan las referencias históricas y el contenido de los protocolos para no alterar sus hashes ni las huellas de los ajustes ya realizados.
