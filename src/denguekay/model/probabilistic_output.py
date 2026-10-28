"""Output formulations (phase 4 of the multi-horizon study).

Each formulation defines how the **cases** and the **outbreak probability** are
obtained, on top of strategy E1 (direct per horizon) or E3 (multi-output), with
the same variables, blocks, seeds and hyperparameters:

========  ==========================================  =======================================
Id        Cases                                        Probability
========  ==========================================  =======================================
S1        ``log1p`` + squared error                    classifier; chronological Platt
S2_pois   ``count:poisson``                            classifier; Platt
S2_twd    ``reg:tweedie`` (power 1.5, fixed)           classifier; Platt
S3        ``count:poisson`` with ``base_margin =``     classifier; Platt
          ``log(persistence + 0.5)``
S4_s2     mean of S2_pois                              P(cases >= k) negative binomial; Platt
S4_s3     mean of S3                                   P(cases >= k) negative binomial; Platt
S5_iso    ``log1p`` (as S1)                            classifier; chronological isotonic
S5_spw    ``log1p`` (as S1)                            classifier with ``scale_pos_weight``;
                                                       Platt
========  ==========================================  =======================================

In S4, ``k = max(floor(umbral_brote_casos) + 1, 2)`` reproduces the gold rule
(cases > threshold and >= 2). The threshold of the target week only uses the
same week of previous years; ``tests/features/test_outbreak_threshold_no_leak.py`` checks that
it does not depend on cases after ``t-h``. It is only used to turn the predicted
distribution into a probability, never as an input variable. The negative
binomial dispersion is estimated by maximum likelihood on the in-sample
predictions of the block's training data (causal, although it may underestimate
it); the subsequent Platt calibration fixes the scale.

With ``dispersion="oos"`` (phase 4.2 of the FE study) each block's alpha is
estimated with the out-of-sample predictions of the previous blocks whose
target week had closed at the cutoff (accumulated). The first block (season
2021) uses a pseudo-block ``temporada_2020`` that only serves that purpose.
Preregistered fallback: if the OOS alpha of a block and horizon does not
converge, ends at the optimizer bound or falls outside [min / 5, max x 5] of the
in-sample alphas of 2021-2024 (same horizon and seed), that block uses the
in-sample alpha and is flagged.
"""

import numpy as np
import pandas as pd
from scipy import optimize, special, stats
from xgboost import XGBClassifier, XGBRegressor

from denguekay.model import horizon_strategies as eh
from denguekay.model.train import MIN_OUTBREAK_CASES, counts_from_log1p

MARGIN_EPS = 0.5
TWEEDIE_POWER = 1.5
FORMULATIONS = {
    "S1": {"conteo": "log1p", "probabilidad": "clasificador", "calibracion": "platt"},
    "S2_pois": {"conteo": "poisson", "probabilidad": "clasificador", "calibracion": "platt"},
    "S2_twd": {"conteo": "tweedie", "probabilidad": "clasificador", "calibracion": "platt"},
    "S3": {"conteo": "poisson_margen", "probabilidad": "clasificador", "calibracion": "platt"},
    "S4_s2": {"conteo": "poisson", "probabilidad": "binomial_negativa", "calibracion": "platt"},
    "S4_s3": {"conteo": "poisson_margen", "probabilidad": "binomial_negativa", "calibracion": "platt"},
    "S5_iso": {"conteo": "log1p", "probabilidad": "clasificador", "calibracion": "isotonica"},
    "S5_spw": {"conteo": "log1p", "probabilidad": "clasificador_spw", "calibracion": "platt"},
}
DISPERSIONS = ("dentro_muestra", "oos")
# Pseudo-block that only estimates the OOS alpha of the first block; it is not evaluated and does not enter Platt.
INITIAL_ALPHA_BLOCK = ("temporada_2020", "temporada", 2020)
LOG_ALPHA_BOUNDS = (-12.0, 6.0)
LOG_ALPHA_BOUND_TOLERANCE = 1e-3
ALPHA_RANGE_FACTOR = 5.0
ALPHA_RANGE_BLOCKS = ("temporada_2021", "temporada_2022", "temporada_2023", "temporada_2024")
# Models trained and deployed per strategy (S4 uses no classifier).
MODELS = {(e, f): (n // 2 if FORMULATIONS[f]["probabilidad"] == "binomial_negativa" else n)
           for e, n in eh.MODELS_PER_STRATEGY.items() for f in FORMULATIONS}


def count_objective(count: str) -> dict:
    """XGBoost parameters for each way of modelling the cases."""
    if count == "log1p":
        return {"objective": "reg:squarederror"}
    if count in ("poisson", "poisson_margen"):
        return {"objective": "count:poisson"}
    if count == "tweedie":
        return {"objective": "reg:tweedie", "tweedie_variance_power": TWEEDIE_POWER}
    raise ValueError(f"Conteo desconocido: {count}")


def persistence_margin(persistence) -> np.ndarray:
    """``log(persistence + 0.5)``: starting point of model S3 on the log scale."""
    p = np.asarray(persistence, float)
    if (p < 0).any() or not np.isfinite(p).all():
        raise ValueError("Persistencia inválida para base_margin")
    return np.log(p + MARGIN_EPS)


def fit_count(x, y, count: str, seed: int, margin=None, **extra) -> XGBRegressor:
    """Case regressor for the formulation (``y`` may have several columns)."""
    model = XGBRegressor(**count_objective(count), **eh.parameters(seed, **extra))
    y = np.asarray(y, float)
    if count == "log1p":
        model.fit(x, np.log1p(y))
    elif count == "poisson_margen":
        model.fit(x, y, base_margin=margin)
    else:
        model.fit(x, y)
    return model


def predict_count(model: XGBRegressor, x, count: str, margin=None) -> np.ndarray:
    """Expected cases on the original scale."""
    if count == "log1p":
        return counts_from_log1p(model.predict(x))
    pred = model.predict(x, base_margin=margin) if count == "poisson_margen" else model.predict(x)
    pred = np.asarray(pred, float)
    if not np.isfinite(pred).all() or (pred < 0).any():
        raise ValueError("El modelo de conteo produjo valores inválidos")
    return pred


def negative_binomial_dispersion(mu, y) -> float:
    """alpha of the NB2 negative binomial (var = mu + alpha mu^2) by maximum likelihood."""
    return negative_binomial_dispersion_detail(mu, y)["alpha"]


def negative_binomial_dispersion_detail(mu, y) -> dict:
    """NB2 alpha by maximum likelihood, with convergence and whether it ended at an optimizer bound."""
    mu = np.clip(np.asarray(mu, float).ravel(), 1e-6, None)
    y = np.asarray(y, float).ravel()

    def nll(log_alpha):
        a = np.exp(log_alpha)
        r = 1 / a
        return -np.sum(special.gammaln(y + r) - special.gammaln(r) - special.gammaln(y + 1)
                       + r * np.log(r / (r + mu)) + y * np.log(mu / (r + mu)))
    lo, hi = LOG_ALPHA_BOUNDS
    result = optimize.minimize_scalar(nll, bounds=(lo, hi), method="bounded")
    x = float(result.x)
    return {"alpha": float(np.exp(x)), "convergio": bool(result.success) and np.isfinite(x),
            "en_limite": min(x - lo, hi - x) < LOG_ALPHA_BOUND_TOLERANCE, "n": int(mu.size)}


def oos_alphas(tests_by_block: dict, cutoffs: dict, in_sample_alphas: dict) -> pd.DataFrame:
    """OOS alpha per block and horizon, with the preregistered fallback.

    ``tests_by_block[block][h]`` holds ``semana_inicio``, ``casos_predichos`` and
    ``casos_Dengue`` of the block's test, in chronological block order (the
    pseudo-block first). For each evaluated block the tests of the previous
    blocks whose target week was closed at its cutoff are pooled.
    """
    names = list(tests_by_block)
    rows = []
    for i, block in enumerate(names):
        if block == INITIAL_ALPHA_BLOCK[0]:
            continue
        cutoff = cutoffs[block]
        for h, a_in_sample in in_sample_alphas[block].items():
            previous = pd.concat([tests_by_block[b][h] for b in names[:i]], ignore_index=True)
            previous = previous[(previous.semana_inicio + pd.Timedelta(days=6)).le(cutoff)]
            span = [in_sample_alphas[b][h] for b in ALPHA_RANGE_BLOCKS if b in in_sample_alphas]
            minimum, maximum = min(span) / ALPHA_RANGE_FACTOR, max(span) * ALPHA_RANGE_FACTOR
            if previous.empty:
                d = {"alpha": np.nan, "convergio": False, "en_limite": False, "n": 0}
            else:
                d = negative_binomial_dispersion_detail(previous.casos_predichos, previous.casos_Dengue)
            in_range = bool(np.isfinite(d["alpha"]) and minimum <= d["alpha"] <= maximum)
            fallback = not (d["convergio"] and not d["en_limite"] and in_range)
            rows.append({"bloque": block, "horizonte": h, "alpha_dentro_muestra": a_in_sample,
                          "alpha_oos": d["alpha"], "n_oos": d["n"], "convergio": d["convergio"],
                          "en_limite": d["en_limite"], "rango_minimo": minimum, "rango_maximo": maximum,
                          "en_rango": in_range, "respaldo": fallback,
                          "alpha_usada": a_in_sample if fallback else d["alpha"],
                          "bloques_previos": ",".join(sorted(previous.bloque_origen.unique()))
                          if not previous.empty else ""})
    return pd.DataFrame(rows)


def count_threshold(outbreak_threshold) -> np.ndarray:
    """Minimum k of cases for the week to be ``brote`` (cases > threshold and >= 2)."""
    return np.maximum(np.floor(np.asarray(outbreak_threshold, float)) + 1, MIN_OUTBREAK_CASES)


def negative_binomial_probability(mu, alpha: float, outbreak_threshold) -> np.ndarray:
    """P(cases >= k) with cases ~ NB2(mu, alpha)."""
    mu = np.clip(np.asarray(mu, float), 1e-9, None)
    k = count_threshold(outbreak_threshold)
    r = 1 / alpha
    return stats.nbinom.sf(k - 1, r, r / (r + mu))


def _classifier(seed: int, spw: float | None = None, **extra) -> XGBClassifier:
    params = eh.parameters(seed, **extra)
    if spw is not None:
        params["scale_pos_weight"] = spw
    return XGBClassifier(objective="binary:logistic", eval_metric="logloss", **params)


def _spw(outbreak) -> float:
    b = np.asarray(outbreak).ravel()
    return float((b == 0).sum() / max((b == 1).sum(), 1))


# ---------------------------------------------------------------------------
# E1 with formulation
# ---------------------------------------------------------------------------

def predict_e1(matrices: dict[int, pd.DataFrame], seed: int, formulation: str,
                horizons: tuple[int, ...] = eh.STRATEGY_HORIZONS) -> pd.DataFrame:
    """E1 (one model per horizon) with the given formulation."""
    f = FORMULATIONS[formulation]
    parts = []
    for h in horizons:
        data = matrices[h]
        col_reg, col_cls = eh.model_columns(h)
        for block, kind, period in eh.blocks():
            train, test, _ = eh.split(data, kind, period)
            m_tr = persistence_margin(train.persistencia) if f["conteo"] == "poisson_margen" else None
            m_te = persistence_margin(test.persistencia) if f["conteo"] == "poisson_margen" else None
            reg = fit_count(train[col_reg], train.casos_Dengue, f["conteo"], seed, m_tr)
            counts = predict_count(reg, test[col_reg], f["conteo"], m_te)
            if f["probabilidad"] == "binomial_negativa":
                alpha = negative_binomial_dispersion(
                    predict_count(reg, train[col_reg], f["conteo"], m_tr), train.casos_Dengue)
                prob = negative_binomial_probability(counts, alpha, test.umbral_brote_casos)
            else:
                spw = _spw(train.brote) if f["probabilidad"] == "clasificador_spw" else None
                cls = _classifier(seed, spw).fit(train[col_cls], train.brote.to_numpy(int))
                prob = cls.predict_proba(test[col_cls])[:, 1]
            parts.append(eh._output(test, block, counts, prob))
    return pd.concat(parts, ignore_index=True).assign(estrategia="E1", formulacion=formulation, semilla=seed)


# ---------------------------------------------------------------------------
# E3 with formulation
# ---------------------------------------------------------------------------

def predict_e3(matrices: dict[int, pd.DataFrame], seed: int, formulation: str,
                return_models: bool = False, columns: list[str] | None = None,
                origins: pd.DataFrame | None = None, hyperparameters: dict | None = None,
                prepare_block=None, dispersion: str = "dentro_muestra"):
    """E3 (multi-output from the same origin) with the given formulation.

    In S3 the ``base_margin`` has one column per output; all three are
    ``log(origin cases + 0.5)`` because the persistence of h=2, 3 and 4 is the
    same value observed at the origin.

    Without optional arguments it reproduces the architecture study. The FE and
    hyperparameter study passes ``columns`` (``base_6`` + new variables),
    ``origins`` (``eh.origin_table`` with those columns already added, in generic
    names) and ``hyperparameters`` (they override the fixed ones).
    ``prepare_block(origins, cutoff)`` returns the origins with the columns that
    depend on a learned transformation (e.g. the socio PC1), fitted only with
    what was closed at the block's ``cutoff``.

    ``dispersion`` (S4 only): ``"dentro_muestra"`` (default) or ``"oos"``
    (see the module docstring). The alphas of each block and horizon end up in
    ``output.attrs["alfas"]``.
    """
    f = FORMULATIONS[formulation]
    if dispersion not in DISPERSIONS:
        raise ValueError(f"Dispersión desconocida: {dispersion}")
    if dispersion == "oos" and f["probabilidad"] != "binomial_negativa":
        raise ValueError("La α OOS solo aplica a las formulaciones S4")
    oos = dispersion == "oos"
    H = eh.STRATEGY_HORIZONS
    base_origins = eh.origin_table(matrices[2]) if origins is None else origins
    col_reg = list(eh.GENERIC) if columns is None else list(columns)
    col_cls = [*col_reg, eh.POPULATION]
    if prepare_block is None:
        missing = [c for c in col_reg if c not in base_origins]
        if missing:
            raise ValueError(f"Columnas ausentes en la tabla de orígenes: {missing}")
    targets = [f"semana_inicio_h{h}" for h in H]
    extra = {"multi_strategy": "multi_output_tree", **(hyperparameters or {})}
    margin_all = (np.repeat(persistence_margin(base_origins.hist_lag_a)[:, None], len(H), axis=1)
                   if f["conteo"] == "poisson_margen" else None)
    parts, models = [], {}
    oos_tests, cutoffs, in_sample_alphas, pending = {}, {}, {}, []
    items = [INITIAL_ALPHA_BLOCK, *eh.blocks()] if oos else eh.blocks()
    for block, kind, period in items:
        pseudo = block == INITIAL_ALPHA_BLOCK[0]
        test_sets, cutoff = eh._common_cutoffs(matrices, kind, period)
        cutoffs[block] = cutoff
        origins = base_origins if prepare_block is None else prepare_block(base_origins, cutoff)
        if prepare_block is not None and (len(origins) != len(base_origins)
                                            or not origins.index.equals(base_origins.index)):
            raise ValueError("preparar_bloque no puede quitar ni reordenar orígenes")
        complete = origins.dropna(subset=targets)
        last = complete[f"semana_inicio_h{H[-1]}"]
        sel = (last + pd.Timedelta(days=6)).le(cutoff)
        train = complete[sel]
        if train.empty or not train.origen_cierre.lt(train.semana_inicio).all():
            raise ValueError("Entrenamiento multi-salida vacío o con fuga")
        m_tr = margin_all[complete.index[sel]] if margin_all is not None else None
        y_cases = np.column_stack([train[f"casos_Dengue_h{h}"] for h in H])
        y_outbreak = np.column_stack([train[f"brote_h{h}"] for h in H]).astype(int)
        reg = fit_count(train[col_reg], y_cases, f["conteo"], seed, m_tr, **extra)
        counts = predict_count(reg, origins[col_reg], f["conteo"], margin_all)
        cls, alphas = None, None
        if f["probabilidad"] == "binomial_negativa":
            fit = predict_count(reg, train[col_reg], f["conteo"], m_tr)
            alphas = [negative_binomial_dispersion(fit[:, i], y_cases[:, i]) for i in range(len(H))]
            if not pseudo:
                in_sample_alphas[block] = dict(zip(H, alphas))
        else:
            spw = _spw(y_outbreak) if f["probabilidad"] == "clasificador_spw" else None
            cls = _classifier(seed, spw, **extra).fit(train[col_cls], y_outbreak)
            prob_all = cls.predict_proba(origins[col_cls])
        if return_models and not pseudo:
            models[block] = {"regresor": reg, "clasificador": cls, "alphas": alphas,
                               "x_reg": train[col_reg], "x_cls": train[col_cls]}
        for step, h in enumerate(H):
            pred = pd.DataFrame({"ubigeo": origins.ubigeo, "semana_inicio": origins[f"semana_inicio_h{h}"],
                                 "origen_cierre_mimo": origins.origen_cierre, "casos_predichos": counts[:, step]})
            if cls is not None:
                pred["probabilidad_brote"] = prob_all[:, step]
            test = test_sets[h].merge(pred.dropna(subset=["semana_inicio"]), on=["ubigeo", "semana_inicio"],
                                    how="left", validate="one_to_one")
            if test.casos_predichos.isna().any() or not test.origen_cierre_mimo.eq(test.origen_cierre).all():
                raise ValueError(f"Predicciones multi-salida incompletas o con origen distinto en h={h}")
            if oos:
                oos_tests.setdefault(block, {})[h] = test[["semana_inicio", "casos_predichos", "casos_Dengue"]] \
                    .assign(bloque_origen=block)
                if not pseudo:
                    pending.append((block, h, test))
                continue
            if cls is None:
                test["probabilidad_brote"] = negative_binomial_probability(
                    test.casos_predichos, alphas[step], test.umbral_brote_casos)
            parts.append(eh._output(test, block, test.casos_predichos, test.probabilidad_brote))
    if oos:
        alfas = oos_alphas(oos_tests, cutoffs, in_sample_alphas)
        used = alfas.set_index(["bloque", "horizonte"]).alpha_usada
        for block, h, test in pending:
            test["probabilidad_brote"] = negative_binomial_probability(
                test.casos_predichos, used[(block, h)], test.umbral_brote_casos)
            parts.append(eh._output(test, block, test.casos_predichos, test.probabilidad_brote))
    else:
        alfas = pd.DataFrame([{"bloque": b, "horizonte": h, "alpha_dentro_muestra": a, "alpha_usada": a}
                              for b, d in in_sample_alphas.items() for h, a in d.items()])
    output = pd.concat(parts, ignore_index=True).assign(estrategia="E3", formulacion=formulation, semilla=seed)
    output.attrs["alfas"] = alfas.assign(dispersion=dispersion, semilla=seed) if len(alfas) else alfas
    return (output, models) if return_models else output


PREDICTORS = {"E1": predict_e1, "E3": predict_e3}


# ---------------------------------------------------------------------------
# Importance per horizon (HU0008-4) and compatibility
# ---------------------------------------------------------------------------

def shap_importance_by_horizon(model, x: pd.DataFrame) -> pd.DataFrame:
    """Mean |SHAP| per variable and output of a multi-output model."""
    import xgboost as xgb

    contrib = model.get_booster().predict(xgb.DMatrix(x), pred_contribs=True)
    if contrib.ndim == 2:
        contrib = contrib[:, None, :]
    margin = model.predict(x, output_margin=True).reshape(contrib.shape[0], contrib.shape[1])
    if not np.allclose(contrib.sum(-1), margin, atol=1e-3):
        raise ValueError("SHAP no es aditivo respecto del margen")
    table = pd.DataFrame(np.abs(contrib[:, :, :-1]).mean(0), columns=list(x.columns),
                         index=[f"h={h}" for h in eh.STRATEGY_HORIZONS[:contrib.shape[1]]])
    return table


def multi_output_compatibility(devices: tuple[str, ...] = ("cuda", "cpu"), n: int = 2000) -> pd.DataFrame:
    """Check on synthetic data what works with ``multi_strategy="multi_output_tree"``.

    For each capability it is not enough that the call does not fail: a numeric
    property is verified (SHAP additivity, Poisson mean, exact margin).
    """
    import xgboost as xgb

    rng = np.random.default_rng(0)
    x = rng.normal(size=(n, 6))
    y = rng.poisson(np.exp(0.5 * x[:, :3])).astype(float)
    b = (y > 1).astype(int)
    rows = []

    def trial(capability, function):
        for d in devices:
            p = dict(tree_method="hist", multi_strategy="multi_output_tree", n_estimators=40, max_depth=3, device=d)
            try:
                ok, detail = function(p)
            except Exception as error:  # noqa: BLE001 - reported in the table
                ok, detail = False, f"{type(error).__name__}: {str(error).splitlines()[0][:120]}"
            rows.append({"capacidad": capability, "dispositivo": d, "funciona": bool(ok), "verificacion": detail})

    def poisson(p):
        m = XGBRegressor(objective="count:poisson", **p).fit(x, y)
        err = float(np.abs(m.predict(x).mean(0) - y.mean(0)).max())
        return err < 0.05, f"media predicha − real por salida ≤ {err:.4f}"

    def tweedie(p):
        m = XGBRegressor(objective="reg:tweedie", tweedie_variance_power=TWEEDIE_POWER, **p).fit(x, y)
        return m.predict(x).shape == y.shape, f"salida {m.predict(x).shape}"

    def margin(p):
        mg = np.log(y + MARGIN_EPS)
        m = XGBRegressor(objective="count:poisson", **p).fit(x, y, base_margin=mg)
        diff = m.predict(x, base_margin=mg, output_margin=True) - m.predict(x, base_margin=np.zeros_like(mg), output_margin=True)
        err = float(np.abs(diff - mg).max())
        return err < 1e-4, f"base_margin (n, 3) aplicado por columna; error {err:.1e}; (n,) se rechaza"

    def importance(p):
        m = XGBRegressor(objective="count:poisson", importance_type="gain", **p).fit(x, y)
        return m.feature_importances_.shape == (6,), "feature_importances_ es agregada (una por variable, no por salida)"

    def shap(p):
        m = XGBRegressor(objective="count:poisson", **p).fit(x, y)
        t = shap_importance_by_horizon(m, pd.DataFrame(x, columns=[f"x{i}" for i in range(6)]))
        own = all(t.iloc[i].idxmax() == f"x{i}" for i in range(3))
        return own, "pred_contribs (n, 3, p+1), aditivo por salida; detecta la variable propia de cada salida"

    def shap_cls(p):
        m = XGBClassifier(objective="binary:logistic", **p).fit(x, b)
        shap_importance_by_horizon(m, pd.DataFrame(x, columns=[f"x{i}" for i in range(6)]))
        return True, "clasificador multietiqueta: SHAP aditivo por salida"

    def spw(p):
        q1 = XGBClassifier(objective="binary:logistic", **p).fit(x, b).predict_proba(x).mean()
        q5 = XGBClassifier(objective="binary:logistic", scale_pos_weight=5.0, **p).fit(x, b).predict_proba(x).mean()
        return q5 > q1, f"un solo valor para las 3 salidas; prob. media {q1:.3f} → {q5:.3f}"

    trial("count:poisson", poisson)
    trial("reg:tweedie", tweedie)
    trial("base_margin con varias salidas (S3)", margin)
    trial("importancia de variables (gain)", importance)
    trial("SHAP por horizonte, regresor", shap)
    trial("SHAP por horizonte, clasificador", shap_cls)
    trial("scale_pos_weight (S5)", spw)
    for d in devices:
        rows.append({"capacidad": "calibrador por salida (S5/S4)", "dispositivo": d, "funciona": True,
                      "verificacion": "posterior al modelo: Platt/isotónica por horizonte en protocolo_arquitectura"})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Preregistered choice of formulation and of strategy + formulation pair
# ---------------------------------------------------------------------------

def pair_key(strategy: str, formulation: str) -> str:
    """Name of a strategy + formulation pair (``"E3|S4_s2"``)."""
    return f"{strategy}|{formulation}"


def pair_models(name: str) -> int:
    """Models trained and deployed for a pair."""
    return MODELS[tuple(name.split("|"))]


def choose(evaluations: dict[str, dict], candidates: list[str], reference: str,
           coherence: pd.DataFrame) -> dict:
    """Preregistered rule: against the reference, adoption and tie-break.

    1. Each candidate is compared with the reference (``decidir`` with seed
       medians and ranges). It is adoptable if it wins in some horizon and loses
       in none.
    2. If there are several adoptable ones, they are compared with each other in
       both directions. The one that **loses** in some horizon against another
       adoptable one, or that another one **beats**, is discarded. If more than one
       remains, or if all discard each other (each better in different
       horizons), tie-break.
    3. If none is adoptable, tie-break between the reference and the tied ones.
    Tie-break: coherence across horizons, then number of models.
    """
    verdicts = pd.concat([eh.decide_against_reference(evaluations, c, reference) for c in candidates],
                           ignore_index=True)
    adoption = eh.adoption(verdicts)
    adoptable = adoption.query("resultado == 'adoptable'").candidata.tolist()
    models = {n: pair_models(n) for n in [reference, *candidates]}
    crossings = pd.DataFrame()
    if len(adoptable) > 1:
        crossings = pd.concat([eh.decide_against_reference(evaluations, a, b)
                            for a in adoptable for b in adoptable if a != b], ignore_index=True)
        expired = (set(crossings.loc[crossings.veredicto.eq("gana"), "referencia"])
                    | set(crossings.loc[crossings.veredicto.eq("pierde"), "candidata"]))
        finalists = [a for a in adoptable if a not in expired] or adoptable
    else:
        finalists = adoptable
    if len(finalists) == 1:
        decision = {"elegida": finalists[0], "criterio": "gana según la regla preregistrada"}
    elif finalists:
        decision = {**eh.break_tie(finalists, coherence, models=models), "empatadas": finalists}
    else:
        tied = [reference, *adoption.query("resultado == 'empate'").candidata]
        decision = {**eh.break_tie(tied, coherence, models=models), "empatadas": tied}
    return {"veredictos": verdicts, "adopcion": adoption, "cruces": crossings, "decision": decision}


def compare_counts(medians: pd.DataFrame, ranges: pd.DataFrame, strategy: str,
                     blocks=("temporada_2022", "temporada_2023")) -> pd.DataFrame:
    """MAE ratio of each count model against ``log1p`` (informative, it does not decide).

    Formulations S2 and S3 only change the cases, so the alert rule leaves them
    tied with S1; this table shows whether their count improves by more than the
    seed range in both selection seasons.
    """
    counts = {"log1p": "S1", "poisson": "S2_pois", "tweedie": "S2_twd", "poisson_margen": "S3"}
    ref = medians[medians.par.eq(pair_key(strategy, "S1"))].set_index(["horizonte", "bloque"])
    rows = []
    for count, f in counts.items():
        pair = pair_key(strategy, f)
        m = medians[medians.par.eq(pair)].set_index(["horizonte", "bloque"])
        r = ranges[ranges.par.isin([pair, pair_key(strategy, "S1")])].groupby(["horizonte", "bloque"]).razon_mae.max()
        for h in eh.STRATEGY_HORIZONS:
            delta = {b: m.at[(h, b), "razon_mae"] - ref.at[(h, b), "razon_mae"] for b in blocks}
            rows.append({"estrategia": strategy, "conteo": count, "horizonte": h,
                          **{f"razon_mae_{b}": m.at[(h, b), "razon_mae"] for b in blocks},
                          **{f"razon_rmse_{b}": m.at[(h, b), "razon_rmse"] for b in blocks},
                          "mejora_en_ambas": all(delta[b] < -r.at[(h, b)] for b in blocks),
                          "empeora_en_alguna": any(delta[b] > r.at[(h, b)] for b in blocks),
                          "cumple_085_en_ambas": all(m.at[(h, b), "razon_mae"] <= 0.85 and m.at[(h, b), "razon_rmse"] <= 0.85
                                                     for b in blocks)})
    return pd.DataFrame(rows)


def formulation_reliability_figure(reliabilities: dict[str, pd.DataFrame], title: str):
    """Reliability curves (calibrated probability) per formulation, horizon and season."""
    import matplotlib.pyplot as plt

    names = list(reliabilities)
    horizons = eh.STRATEGY_HORIZONS
    fig, axes = plt.subplots(len(names), len(horizons), figsize=(4 * len(horizons), 2.6 * len(names)),
                             squeeze=False, sharex=True, sharey=True)
    for i, name in enumerate(names):
        t = reliabilities[name]
        for j, h in enumerate(horizons):
            ax = axes[i, j]
            ax.plot([0, 1], [0, 1], color="grey", linestyle="--", linewidth=0.8)
            for block in ("temporada_2022", "temporada_2023", "temporada_2024"):
                g = t[t.horizonte.eq(h) & t.bloque.eq(block)]
                ax.plot(g.prob_media, g.frecuencia_observada, marker="o", markersize=3,
                        label=block.replace("temporada_", ""))
            ax.set_title(f"{name}, h={h}", fontsize=9)
            if j == 0:
                ax.set_ylabel("Frecuencia observada")
            if i == len(names) - 1:
                ax.set_xlabel("Probabilidad calibrada")
    axes[0, 0].legend(fontsize=7)
    fig.suptitle(title)
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Complementary diagnostics of S4
# ---------------------------------------------------------------------------

def poisson_probability(mu, outbreak_threshold) -> np.ndarray:
    """P(cases >= k) with cases ~ Poisson(mu): the negative binomial limit as alpha -> 0."""
    return stats.poisson.sf(count_threshold(outbreak_threshold) - 1, np.clip(np.asarray(mu, float), 1e-9, None))


def recall_by_week_type(data: pd.DataFrame, series: pd.DataFrame, alert: str = "alerta_050",
                           onset_weeks: int = 2) -> pd.DataFrame:
    """Recall on ``brote`` weeks of new outbreaks against ongoing outbreaks.

    "New outbreak": the first ``onset_weeks`` weeks of an episode with a clean
    onset (no outbreak in the previous 8 weeks). "Ongoing": the rest of the
    ``brote`` weeks. It separates anticipating new outbreaks from doing better
    on outbreaks that already started.
    """
    from denguekay.evaluation import episodes as diag

    eps = diag.episodios(series)
    clean = eps[eps.semanas_previas_sin_brote >= diag.SIN_BROTE_PREVIO]
    new_columns = set()
    for ep in clean.itertuples(index=False):
        for k in range(onset_weeks):
            new_columns.add((ep.ubigeo, ep.inicio + pd.Timedelta(weeks=k)))
    pos = data[data.brote.eq(1) & data.probabilidad_calibrada.notna()].copy()
    pos["tipo"] = ["brote_nuevo" if (u, s) in new_columns else "en_curso" for u, s in zip(pos.ubigeo, pos.semana_inicio)]
    return (pos.groupby(["horizonte", "bloque", "tipo"])[alert]
            .agg(semanas="size", recall="mean").reset_index())


# ---------------------------------------------------------------------------
# HU0007-4 compliance (baseline; not a decision criterion)
# ---------------------------------------------------------------------------

HU0007_4_THRESHOLDS = {"precision_050": 0.60, "recall_050": 0.80, "f1_050": 0.70,
                     "razon_mae": 0.85, "razon_rmse": 0.85}


def hu0007_4_compliance(metrics: pd.DataFrame) -> pd.DataFrame:
    """Flag, per horizon and block, which HU0007-4 acceptance thresholds are met.

    Classification: P >= 0.60, R >= 0.80 and F1 >= 0.70 with p >= 0.50.
    Regression: MAE and RMSE <= 85 % of the persistence ones.
    """
    output = metrics[["horizonte", "bloque", *HU0007_4_THRESHOLDS]].copy()
    for m, u in HU0007_4_THRESHOLDS.items():
        output[f"cumple_{m}"] = output[m].le(u) if m.startswith("razon") else output[m].ge(u)
    output["cumple_clasificacion"] = output[["cumple_precision_050", "cumple_recall_050", "cumple_f1_050"]].all(axis=1)
    output["cumple_regresion"] = output[["cumple_razon_mae", "cumple_razon_rmse"]].all(axis=1)
    return output
