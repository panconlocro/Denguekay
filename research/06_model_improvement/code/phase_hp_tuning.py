"""Hyperparameter tuning of L + 5a + d3 (preregistration ``HP_TUNING``; Rosa, 2026-11-08).

A trial trains only the tuning blocks (seasons that neither decide nor enter the leave-one-season-out filter),
calibrates them chronologically among themselves (Platt per horizon) and returns the objective: the mean over the
objective cells of the calibrated Brier relative to the inherited hyperparameters' (seed 17). The deciding
seasons' predictions and labels never enter the objective.
"""

from __future__ import annotations

import math
import time

import numpy as np
import pandas as pd

from denguekay.evaluation import protocol as pa
from denguekay.evaluation import tuning as t05

import phase1_history as p1
import phase3_onsets as p3
import preregistration as pr


def inherited() -> dict:
    """The V1 hyperparameters the study inherits (``CONFIG_2026_V1``), all explicit."""
    return dict(p3._config()[1])


def tuning_blocks() -> list[tuple[str, str, int]]:
    """The blocks a trial trains: ``HP_TUNING_TRAIN_SEASONS`` out of the study's seasonal blocks."""
    keep = {pr.block_name(s) for s in pr.HP_TUNING_TRAIN_SEASONS}
    return [b for b in p1.seasonal_blocks(p1.FIRST_BLOCK_SEASON_LONG) if b[0] in keep]


def suggest(trial) -> dict:
    params = {}
    for name, (kind, lo, hi, log) in pr.HP_TUNING_SPACE.items():
        params[name] = (trial.suggest_int(name, lo, hi, log=log) if kind == "int"
                        else trial.suggest_float(name, lo, hi, log=log))
    return params


def cell_scores(pred: pd.DataFrame, blocks=None) -> pd.DataFrame:
    """Calibrated Brier and log-loss per horizon and objective block (Platt among the trained blocks only)."""
    blocks = blocks or [pr.block_name(s) for s in pr.HP_TUNING_OBJECTIVE_SEASONS]
    data, _ = pa.calibrate_chronologically(pred)
    data = data[data.bloque.isin(blocks)]
    rows = []
    for (h, b), g in data.groupby(["horizonte", "bloque"]):
        y, p = g.brote.to_numpy(int), g.probabilidad_calibrada.to_numpy(float)
        rows.append({"horizonte": h, "bloque": b, "positivos": int(y.sum()),
                     "brier": float(np.mean((p - y) ** 2)) if np.isfinite(p).all() else np.nan,
                     "logloss": t05.logloss(y, p) if np.isfinite(p).all() else np.nan})
    return pd.DataFrame(rows)


def relative_objective(cells: pd.DataFrame, reference: pd.DataFrame) -> float:
    """Mean over the objective cells of brier / brier of the inherited configuration; NaN if a cell is missing."""
    key = ["horizonte", "bloque"]
    m = cells.merge(reference[key + ["brier"]], on=key, suffixes=("", "_heredados"), how="right")
    expected = len(p3.H) * len(pr.HP_TUNING_OBJECTIVE_SEASONS)
    if len(m) != expected or not np.isfinite(m.brier).all():
        return float("nan")
    return float((m.brier / m.brier_heredados).mean())


def run_trial(matrices, origins, columns, params: dict, seed: int = pr.HP_TUNING_XGB_SEED) -> pd.DataFrame:
    """Predictions of the tuning blocks with ``params`` and their per-cell scores."""
    pred = p3.predict_blocks_weighted(matrices, origins, tuning_blocks(), seed, columns, params)
    pred.attrs.pop("ajustes", None)
    return cell_scores(pred)


def time_trials(matrices, origins, columns, configurations: dict[str, dict]) -> pd.DataFrame:
    """Seconds of one trial per configuration. Only the time is reported (the scores are not looked at)."""
    rows = []
    for name, params in configurations.items():
        start = time.perf_counter()
        run_trial(matrices, origins, columns, params)
        rows.append({"configuracion": name, "segundos": time.perf_counter() - start})
    return pd.DataFrame(rows)


def study_columns() -> list[str]:
    return [*p3._config()[0], *pr.MATRIX_VARIANTS["d3"]]


def reference_scores(matrices, origins, columns, path) -> pd.DataFrame:
    """Per-cell scores of the exact inherited hyperparameters (reg_alpha = 0, seed 17), computed once and saved."""
    if path.exists():
        return pd.read_csv(path)
    ref = run_trial(matrices, origins, columns, inherited())
    ref.to_csv(path, index=False)
    return ref


def run_search(out_dir, n_trials: int = pr.HP_TUNING_N_TRIALS, timeout: float = pr.HP_TUNING_TIMEOUT_S):
    """Run (or resume) the preregistered TPE study, saved in ``out_dir/optuna.db``. The timeout caps this
    invocation's wall clock: no trial starts after it; the running one finishes."""
    import optuna

    import phase_2026 as p26

    out_dir.mkdir(parents=True, exist_ok=True)
    inp = p26.inputs_2026()
    origins, _ = p26.add_climate(inp)
    columns = study_columns()
    reference = reference_scores(inp["matrices"], origins, columns, out_dir / "referencia_heredados.csv")
    optuna.logging.set_verbosity(optuna.logging.INFO)
    st = optuna.create_study(study_name=STUDY_NAME, storage=f"sqlite:///{(out_dir / 'optuna.db').as_posix()}",
                             direction="minimize", load_if_exists=True,
                             sampler=optuna.samplers.TPESampler(seed=pr.HP_TUNING_TPE_SEED,
                                                                n_startup_trials=pr.HP_TUNING_STARTUP_TRIALS))
    if not st.trials:
        st.enqueue_trial({**inherited(), "reg_alpha": 1e-3}, user_attrs={"es_base": True})
    done = sum(t.state != optuna.trial.TrialState.WAITING for t in st.trials)
    start = time.perf_counter()
    if n_trials - done > 0:
        st.optimize(objective_fn(inp["matrices"], origins, columns, reference), n_trials=n_trials - done,
                    timeout=timeout, catch=(Exception,))
    return st, time.perf_counter() - start


STUDY_NAME = "ajuste_hp_d3"


def objective_fn(matrices, origins, columns, reference: pd.DataFrame):
    """Optuna objective."""
    def function(trial):
        params = suggest(trial)
        start = time.perf_counter()
        cells = run_trial(matrices, origins, columns, params)
        trial.set_user_attr("segundos", time.perf_counter() - start)
        trial.set_user_attr("logloss_media", float(cells.logloss.mean()))
        value = relative_objective(cells, reference)
        return value if math.isfinite(value) else float("nan")
    return function


if __name__ == "__main__":
    # Long search (overnight): python research/06_model_improvement/code/phase_hp_tuning.py
    from denguekay.config.paths import MODELS

    out = MODELS / "experimentos" / "mejora_modelo" / "ajuste_hp"
    st, seconds = run_search(out)
    states = pd.Series([t.state.name for t in st.trials]).value_counts().to_dict()
    print(f"FIN: {seconds:.0f} s en esta corrida; trials por estado {states}", flush=True)
