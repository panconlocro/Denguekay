"""Hyperparameter optimisation of E3·S4_s2 on matrix C3 (phase 3, HU0007-3).

``PHASE3_PREREGISTRATION`` fixes, before the study, the base, the objective, the
space, the sampler, the choice of the candidate, the adoption rule and the
robustness check. The protocol (``protocolo_arquitectura``) does not change: each
configuration is evaluated with ``salida_probabilistica.predecir_e3`` (S4_s2) and
``protocolo_arquitectura.evaluar`` (chronological Platt).
"""

import json
import math
import time

import numpy as np
import pandas as pd

from denguekay.model import horizon_strategies as eh
from denguekay.evaluation import protocol as pa
from denguekay.model import probabilistic_output as sp
from denguekay.model.train import BASE_PARAMS

FORMULATION = "S4_s2"
XGB_SEED = 17
TPE_SEED = 20261027
N_TRIALS = 100
TOP_K = 5
MAX_DELTA_STEP_POISSON = 0.7  # XGBoost default with count:poisson

# Optimisable hyperparameters of the base (C3 with the inherited fixed values), all explicit.
BASE = {"n_estimators": BASE_PARAMS["n_estimators"], "max_depth": BASE_PARAMS["max_depth"],
        "learning_rate": BASE_PARAMS["learning_rate"], "min_child_weight": BASE_PARAMS["min_child_weight"],
        "subsample": BASE_PARAMS["subsample"], "colsample_bytree": BASE_PARAMS["colsample_bytree"],
        "reg_lambda": BASE_PARAMS["reg_lambda"], "reg_alpha": 0.0, "gamma": 0.0,
        "max_delta_step": MAX_DELTA_STEP_POISSON}
# Trial 0 of the study: the base with reg_alpha at the minimum of the log space (Optuna does not allow 0 on a log scale).
TRIAL_0 = {**BASE, "reg_alpha": 1e-3}

# (type, minimum, maximum, log)
SPACE = {
    "max_depth": ("int", 2, 8, False),
    "min_child_weight": ("float", 1.0, 50.0, True),
    "learning_rate": ("float", 0.01, 0.3, True),
    "n_estimators": ("int", 100, 1500, False),
    "subsample": ("float", 0.5, 1.0, False),
    "colsample_bytree": ("float", 0.5, 1.0, False),
    "reg_lambda": ("float", 1e-3, 10.0, True),
    "reg_alpha": ("float", 1e-3, 10.0, True),
    "gamma": ("float", 0.0, 5.0, False),
    "max_delta_step": ("float", 0.3, 2.0, False),
}

PHASE3_PREREGISTRATION = {
    "fecha": "2026-10-27, antes del estudio (aprobado por Rosa)",
    "matriz": "C3 = base_6 + B3 (elegida en la fase 2c)",
    "base": {"parametros": BASE, "nota": "PARAMETROS_BASE heredados; reg_alpha y gamma en 0 y max_delta_step 0,7 "
                                         "(los valores por defecto de XGBoost con count:poisson), explícitos"},
    "objetivo": "log-loss de probabilidad_calibrada (Poisson → binomial negativa con α dentro de la muestra → "
                "Platt cronológico), media sobre h=2/3/4 × temporadas 2022 y 2023; F1 a 0,50 y AUPRC se registran "
                "por trial, no se optimizan",
    "espacio": {k: {"tipo": t, "min": lo, "max": hi, "log": lg} for k, (t, lo, hi, lg) in SPACE.items()},
    "nota_max_delta_step": "rango 0,3–2 (lineal) en lugar de 0–2: con count:poisson, 0 significa sin límite y puede "
                           "volver inestable la optimización; el rango incluye el 0,7 de la base",
    "trial_0": {"parametros": TRIAL_0,
                "nota": "la base exacta usa reg_alpha = 0, que Optuna no admite en escala log; el trial 0 es la base con "
                        "reg_alpha = 1e-3, el punto más cercano del espacio. Medido antes del estudio (semilla 17): "
                        "objetivo 0,220007 igual al sexto decimal, F1 y AUPRC idénticos en las 6 celdas, diferencia "
                        "máxima de casos predichos 0,0024. La regla compara contra la base exacta (C3 de la 2c, "
                        "reg_alpha = 0); el trial 0 solo sitúa el arranque de la curva"},
    "estudio": {"muestreador": "TPE", "semilla_tpe": TPE_SEED, "semilla_xgboost": XGB_SEED,
                "n_trials": N_TRIALS, "trial_0": "TRIAL_0, encolado con enqueue_trial", "pruning": False,
                "early_stopping": False,
                "fallidos": "un trial que falla o da objetivo no finito queda como FAIL en Optuna y en MLflow y se reporta"},
    "seleccion": f"las {TOP_K} mejores por el objetivo se reentrenan con las 5 semillas; se elige la de mejor mediana "
                 "del objetivo; solo esa se compara con la regla simétrica contra la base (+1 comparación, 17 en total)",
    "adopcion": "gana → se adopta; empata → se queda la base salvo que la candidata sea igual o más simple "
                "(n_estimators × max_depth); pierde → se queda la base",
    "robustez_solo_lectura": "candidata final frente a la base sin las 8 primeras semanas de orígenes de 2017; signos "
                             "de F1 y antelación en 2022 y 2023",
    "limite": "la búsqueda usa las mismas temporadas de selección (2022–2023): las métricas de la candidata son "
              "optimistas; 2024 solo de contraste",
}


def suggest(trial) -> dict:
    """Sample a configuration from the preregistered space."""
    params = {}
    for name, (kind, lo, hi, log) in SPACE.items():
        if kind == "int":
            params[name] = trial.suggest_int(name, lo, hi, log=log)
        else:
            params[name] = trial.suggest_float(name, lo, hi, log=log)
    return params


def logloss(y, p, eps: float = pa.EPS) -> float:
    y = np.asarray(y, float)
    p = np.clip(np.asarray(p, float), eps, 1 - eps)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def objective(evaluation: dict, blocks: tuple[str, ...] = pa.SELECTION_BLOCKS) -> tuple[float, pd.DataFrame]:
    """Mean calibrated log-loss over h x selection seasons and the per-cell table."""
    data = evaluation["datos"]
    data = data[data.bloque.isin(blocks) & data.probabilidad_calibrada.notna()]
    cells = (data.groupby(["horizonte", "bloque"])
              .apply(lambda g: logloss(g.brote, g.probabilidad_calibrada), include_groups=False)
              .rename("logloss").reset_index())
    expected = len(eh.STRATEGY_HORIZONS) * len(blocks)
    if len(cells) != expected:
        return float("nan"), cells
    return float(cells.logloss.mean()), cells


def evaluate_configuration(matrices, series, origins, columns, params: dict, seed: int = XGB_SEED) -> dict:
    """E3·S4_s2 prediction with ``params`` and full protocol evaluation."""
    pred = sp.predict_e3(matrices, seed, FORMULATION, columns=columns, origins=origins, hyperparameters=params)
    return pa.evaluate(pred, series, sp.FORMULATIONS[FORMULATION]["calibracion"]) | {"predicciones": pred}


def trial_summary(evaluation: dict) -> dict:
    """Objective and per-cell metrics saved in each trial."""
    value, cells = objective(evaluation)
    met = evaluation["metricas"].set_index(["horizonte", "bloque"])
    output = {"objetivo": value}
    for _, c in cells.iterrows():
        suffix = f"h{int(c.horizonte)}_{c.bloque.replace('temporada_', '')}"
        output[f"logloss_{suffix}"] = float(c.logloss)
    for (h, b), row in met.iterrows():
        if b in (*pa.SELECTION_BLOCKS, pa.CONTRAST_BLOCK):
            suffix = f"h{int(h)}_{b.replace('temporada_', '')}"
            output[f"f1_050_{suffix}"] = float(row.f1_050)
            output[f"auprc_{suffix}"] = float(row.auprc)
    return output


def study(matrices, series, origins, columns, storage: str, name: str = "fase3_c3",
            n_trials: int = N_TRIALS):
    """Run (or resume) the preregistered TPE study up to ``n_trials`` trials in total."""
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    st = optuna.create_study(study_name=name, storage=storage, direction="minimize", load_if_exists=True,
                             sampler=optuna.samplers.TPESampler(seed=TPE_SEED))
    if not st.trials:
        st.enqueue_trial(TRIAL_0, user_attrs={"es_base": True})

    def function(trial):
        params = suggest(trial)
        start = time.perf_counter()
        r = trial_summary(evaluate_configuration(matrices, series, origins, columns, params))
        trial.set_user_attr("segundos", time.perf_counter() - start)
        for k, v in r.items():
            if k != "objetivo":
                trial.set_user_attr(k, v)
        return r["objetivo"] if math.isfinite(r["objetivo"]) else float("nan")

    # The enqueued trial (WAITING) does not count as done until it runs.
    done = sum(t.state != optuna.trial.TrialState.WAITING for t in st.trials)
    remaining = n_trials - done
    if remaining > 0:
        st.optimize(function, n_trials=remaining, catch=(Exception,))
    return st


def trials_table(st) -> pd.DataFrame:
    """One trial per row: number, status, objective, parameters, seconds and metrics."""
    rows = []
    for t in st.trials:
        rows.append({"numero": t.number, "estado": t.state.name, "objetivo": t.value,
                      "es_base": bool(t.user_attrs.get("es_base", False)),
                      **{f"param_{k}": v for k, v in t.params.items()}, **t.user_attrs})
    return pd.DataFrame(rows)


def top_k(st, k: int = TOP_K) -> list:
    """The ``k`` best complete configurations by objective (excluding the enqueued base)."""
    import optuna

    complete = [t for t in st.trials if t.state == optuna.trial.TrialState.COMPLETE
                 and math.isfinite(t.value) and not t.user_attrs.get("es_base", False)]
    return sorted(complete, key=lambda t: t.value)[:k]


def complexity(params: dict) -> int:
    """Trees x depth: the simplicity criterion of the adoption."""
    return int(params["n_estimators"]) * int(params["max_depth"])


def adopt(verdicts: pd.DataFrame, candidate: dict, base: dict = BASE) -> dict:
    """Preregistered adoption rule from the verdicts per horizon (candidate against base)."""
    result = eh.adoption(verdicts).resultado.iloc[0]
    if result == "adoptable":
        return {"adoptada": "candidata", "criterio": "gana a la base"}
    if result == "empate" and complexity(candidate) <= complexity(base):
        return {"adoptada": "candidata", "criterio": "empata y es igual o más simple que la base"}
    if result == "empate":
        return {"adoptada": "base", "criterio": "empata y la candidata es más compleja"}
    return {"adoptada": "base", "criterio": "la candidata pierde en algún horizonte"}


def time_configuration(matrices, series, origins, columns, params: dict, repetitions: int = 2) -> pd.DataFrame:
    """Seconds of a complete trial (5 blocks, 1 seed and protocol) for a configuration."""
    rows = []
    for i in range(repetitions):
        start = time.perf_counter()
        evaluate_configuration(matrices, series, origins, columns, params)
        rows.append({"repeticion": i + 1, "segundos": time.perf_counter() - start})
    return pd.DataFrame(rows)


def trials_fingerprint(trials: pd.DataFrame) -> str:
    """Fingerprint of the study for MLflow: parameters, states and objectives of every trial."""
    import hashlib

    columns = ["numero", "estado", "objetivo", *sorted(c for c in trials if c.startswith("param_"))]
    text = trials[columns].sort_values("numero").to_json(orient="records", double_precision=15)
    return hashlib.sha256((text + json.dumps(PHASE3_PREREGISTRATION, sort_keys=True, default=str)).encode()).hexdigest()


def top_fingerprint(best: list) -> str:
    """Fingerprint of the best configurations (number and parameters): the selection is recomputed only if they change."""
    import hashlib

    text = json.dumps([[t.number, t.params] for t in best], sort_keys=True, default=float)
    return hashlib.sha256((text + json.dumps(PHASE3_PREREGISTRATION, sort_keys=True, default=str)).encode()).hexdigest()


def curve_figure(trials: pd.DataFrame, base_value: float):
    """Objective per trial and running best; trial 0 flagged and the exact base as a line."""
    import matplotlib.pyplot as plt

    t = trials.sort_values("numero")
    ok = t[t.estado.eq("COMPLETE")]
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.scatter(ok.numero, ok.objetivo, s=14, color="#0072B2", alpha=0.6, label="Trial")
    ax.plot(ok.numero, ok.objetivo.cummin(), color="#D55E00", label="Mejor acumulado")
    zero = ok[ok.es_base]
    ax.scatter(zero.numero, zero.objetivo, s=60, marker="D", color="#009E73", label="Trial 0 (base, reg_alpha = 1e-3)")
    ax.axhline(base_value, color="grey", linestyle="--", linewidth=1, label="Base exacta (reg_alpha = 0, 5 semillas)")
    failed = t[t.estado.ne("COMPLETE")]
    if len(failed):
        ax.scatter(failed.numero, [base_value] * len(failed), marker="x", color="black", label="Fallido")
    ax.set_xlabel("Trial")
    ax.set_ylabel("Log-loss calibrado (media h=2/3/4 × 2022–2023)")
    ax.set_title("Curva de optimización TPE, E3·S4_s2 con C3")
    ax.legend(fontsize=8)
    fig.tight_layout()
    return fig


def importance_figure(importance: dict[str, float]):
    """Hyperparameter importance (Optuna fANOVA)."""
    import matplotlib.pyplot as plt

    s = pd.Series(importance).sort_values()
    fig, ax = plt.subplots(figsize=(7, 0.4 * len(s) + 1.5))
    ax.barh(s.index, s.values, color="#0072B2")
    ax.set_xlabel("Importancia relativa en el objetivo")
    ax.set_title("Importancia de hiperparámetros (fANOVA)")
    fig.tight_layout()
    return fig
