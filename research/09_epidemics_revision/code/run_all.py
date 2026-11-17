"""Reproduce study 09 from scratch: leakage audit, fits and every notebook, in order (``python run_all.py``)."""

import os
import subprocess
import sys
import time
from pathlib import Path

CODE = Path(__file__).resolve().parent
ARMS = ["historia_geo", "b3_obs", "b3_hist_geo", "b3_lag1", "b3_placebo_t1", "b3_placebo_t2", "b3_placebo_t3",
        "b3_placebo_conjunto"]
STEPS = [
    ("geography", ["-c", "import common as c; print(c.build_geography(c.archive.load_integrated(c.archive.PANEL)))"]),
    ("notebook", "00_leakage_audit.ipynb"),
    ("fits", ["run_fits.py", *ARMS]),
    ("notebook", "01_reproduction_check.ipynb"),
    ("notebook", "02_E1_main_comparison.ipynb"),
    ("notebook", "03_E2_weather_timing.ipynb"),
    ("notebook", "04_E3_diagnostics.ipynb"),
    ("notebook", "05_E4_calibration.ipynb"),
    ("fits", ["run_extra.py", "cuatro_brazos"]),
    ("fits", ["run_extra.py", "nb2", "--workers", "2"]),
    ("fits", ["run_extra.py", "confirmados_probables"]),
    ("notebook", "06_E5_skill_decomposition.ipynb"),
    ("notebook", "07_E6_case_and_outcome_definition.ipynb"),
    ("notebook", "08_E7_statistical_model.ipynb"),
    ("fits", ["run_extra.py", "horizontes_largos"]),
    ("notebook", "09_E8_longer_horizons.ipynb"),
    ("notebook", "10_summary.ipynb"),
    # E9–E13 (protocolo_revision.md)
    ("fits", ["run_extra.py", "retrasos"]),
    ("fits", ["run_extra.py", "clasificador"]),
    ("notebook", "11_E9_alignments_and_development_seasons.ipynb"),
    ("notebook", "12_E10_count_uncertainty.ipynb"),
    ("notebook", "13_E11_onset_and_continuation.ipynb"),
    ("notebook", "14_E12_reporting_delays.ipynb"),
    ("notebook", "15_E13_direct_classifier.ipynb"),
    ("results", ["write_results.py"]),
]


def main():
    env = {**os.environ, "DENGUEKAY_XGB_DEVICE": "cpu", "DENGUEKAY_XGB_NJOBS": "2", "OMP_NUM_THREADS": "2",
           "OPENBLAS_NUM_THREADS": "1", "VECLIB_MAXIMUM_THREADS": "1", "MLFLOW_DISABLE_AGENT_HINT": "1"}
    start = time.time()
    for kind, arg in STEPS:
        command = [sys.executable, "notebook_tools.py", "run", arg] if kind == "notebook" else [sys.executable, *arg]
        print(f"[{(time.time() - start) / 60:5.1f} min] {kind}: {arg if kind == 'notebook' else ' '.join(arg)}", flush=True)
        # "fits" and "results" steps both run a script of this folder
        subprocess.run(command, cwd=CODE, env=env, check=True)
    print(f"Study 09 reproduced in {(time.time() - start) / 60:.1f} min", flush=True)


if __name__ == "__main__":
    main()
