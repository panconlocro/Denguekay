"""Phase 3: outbreak onsets over L (trained from 2005, Platt per horizon with clip 1e-6).

Variants, one at a time against L (``preregistration.PHASE3``):

- 3a1 sample weights on onset targets; 3a2 sample weights per season;
- 3b two regimes (district without / with outbreak at the origin), combined by the state at the origin;
- 3c B1 + B2 only in the onset regime of 3b.

``predict_blocks_weighted`` is ``phase1_history.predict_blocks`` with optional weights and regimes; with
neither it follows the same path (guard G8 checks it reproduces the saved L predictions).
"""

import numpy as np
import pandas as pd

from denguekay.config.paths import MODELS
from denguekay.evaluation import episodes as diag
from denguekay.model import horizon_strategies as eh
from denguekay.model import probabilistic_output as sp
from denguekay.model.train import SEASON_START_WEEK

ONSET_WEEKS = 2                  # "brote nuevo": first 2 weeks of an episode with a clean onset
ONSET_WEIGHT = 5.0               # 3a1, fixed a priori (one value, no grid)
SEASON_WEIGHT_CLIP = (0.25, 1.0)  # 3a2: no season weighs more than today (Rosa)
MIN_REGIME_ROWS = 100            # 3b: fewer training origins in a regime -> that block uses the single model
FORMULATION = "S4_s3"
OUTPUT_DIR = MODELS / "experimentos" / "mejora_modelo" / "fase3"
H = eh.STRATEGY_HORIZONS


# ---------------------------------------------------------------------------
# Weights (computed inside each block with its training origins only)
# ---------------------------------------------------------------------------

def onset_weeks(series: pd.DataFrame, weeks: int = ONSET_WEEKS) -> set[tuple[str, pd.Timestamp]]:
    """(ubigeo, week) of the outbreak weeks that open an episode with a clean onset, as in
    ``probabilistic_output.recall_by_week_type``. An episode start only depends on earlier labels."""
    eps = diag.episodes(series)
    clean = eps[eps.semanas_previas_sin_brote >= diag.NO_PREVIOUS_OUTBREAK]
    brote = set(zip(series.loc[series.brote.eq(1), "ubigeo"], pd.to_datetime(series.loc[series.brote.eq(1),
                                                                                            "semana_inicio"])))
    out = set()
    for ep in clean.itertuples(index=False):
        for k in range(weeks):
            key = (ep.ubigeo, ep.inicio + pd.Timedelta(weeks=k))
            if key in brote:
                out.add(key)
    return out


def onset_weights(train: pd.DataFrame, new_weeks: set, factor: float = ONSET_WEIGHT) -> np.ndarray:
    """``factor`` for the origins with at least one of their three targets in ``new_weeks``, 1 otherwise."""
    hit = np.zeros(len(train), bool)
    for h in H:
        hit |= np.fromiter(((u, w) in new_weeks for u, w in zip(train.ubigeo, train[f"semana_inicio_h{h}"])),
                           bool, len(train))
    return np.where(hit, factor, 1.0)


def target_season(weeks: pd.Series) -> np.ndarray:
    """Epidemiological season (week 35 to 34) of a target week, labelled by the year it ends."""
    from denguekay.data.calendar import mmwr_epi_week

    cal = mmwr_epi_week(pd.Series(pd.to_datetime(weeks).to_numpy()))
    return (cal.anio_epi + cal.semana_epi.ge(SEASON_START_WEEK).astype(int)).to_numpy()


def season_weights(train: pd.DataFrame, clip: tuple[float, float] = SEASON_WEIGHT_CLIP) -> np.ndarray:
    """Per season s of the h=2 target: median_s(C) / C_s clipped, with C_s the h=2 target cases of the
    block's training origins in s (0 cases -> the upper clip). Heavy seasons (2017, 2023) weigh less; none weighs more than 1."""
    season = target_season(train[f"semana_inicio_h{H[0]}"])
    totals = pd.Series(train[f"casos_Dengue_h{H[0]}"].to_numpy(float)).groupby(season).sum()
    med = float(totals.median())
    ratio = {s: (med / c if c > 0 else np.inf) for s, c in totals.items()}
    return np.clip(np.array([ratio[s] for s in season]), *clip)


# ---------------------------------------------------------------------------
# State at the origin (known when the origin week closes)
# ---------------------------------------------------------------------------

def origin_state(origins: pd.DataFrame, series: pd.DataFrame) -> np.ndarray:
    """``brote`` of the origin week (the week that closes at ``origen_cierre``); its label uses the same
    week of previous years and the cases of that week, so it is known at the origin. Missing -> 0."""
    week = pd.to_datetime(origins.origen_cierre) - pd.Timedelta(days=6)
    lab = series[["ubigeo", "semana_inicio", "brote"]].assign(semana_inicio=lambda d: pd.to_datetime(d.semana_inicio))
    key = pd.DataFrame({"ubigeo": origins.ubigeo.astype(str).to_numpy(), "semana_inicio": week.to_numpy()})
    joined = key.merge(lab.assign(ubigeo=lab.ubigeo.astype(str)), on=["ubigeo", "semana_inicio"], how="left",
                       validate="many_to_one")
    return joined.brote.fillna(0).astype(int).to_numpy()


# ---------------------------------------------------------------------------
# Block loop with weights and regimes
# ---------------------------------------------------------------------------

def _training(origins: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame:
    complete = origins.dropna(subset=[f"semana_inicio_h{h}" for h in H])
    sel = (complete[f"semana_inicio_h{H[-1]}"] + pd.Timedelta(days=6)).le(cutoff)
    train = complete[sel]
    if train.empty or not train.origen_cierre.lt(train.semana_inicio).all():
        raise ValueError("Entrenamiento multi-salida vacío o con fuga")
    return train


def _fit(train: pd.DataFrame, seed: int, col_reg: list[str], extra: dict, margin_all: np.ndarray,
         weights: np.ndarray | None):
    """The S4_s3 regressor of ``sp.fit_e3`` with an optional ``sample_weight``; α unweighted, in-sample."""
    f = sp.FORMULATIONS[FORMULATION]
    m_tr = margin_all[train.index]
    y = np.column_stack([train[f"casos_Dengue_h{h}"] for h in H])
    if weights is None:
        reg = sp.fit_count(train[col_reg], y, f["conteo"], seed, m_tr, **extra)
    else:
        from xgboost import XGBRegressor

        reg = XGBRegressor(**sp.count_objective(f["conteo"]), **eh.parameters(seed, **extra))
        reg.fit(train[col_reg], np.asarray(y, float), base_margin=m_tr, sample_weight=weights)
    fit = sp.predict_count(reg, train[col_reg], f["conteo"], m_tr)
    alphas = [sp.negative_binomial_dispersion(fit[:, i], y[:, i]) for i in range(len(H))]
    return reg, alphas


def predict_blocks_weighted(matrices: dict[int, pd.DataFrame], origins: pd.DataFrame,
                            blocks: list[tuple[str, str, int]], seed: int, columns: list[str],
                            hyperparameters: dict, weights_fn=None, state: np.ndarray | None = None,
                            onset_columns: list[str] | None = None, prepare_block=None) -> pd.DataFrame:
    """E3 · S4_s3 OOS predictions per block, like ``phase1_history.predict_blocks``.

    ``weights_fn(train) -> weights`` (3a). ``state`` (3b): 0/1 per origin; one model per state, each
    trained with the training origins of its state, predicting the origins of its state. A state with
    fewer than ``MIN_REGIME_ROWS`` training origins in a block falls back to the single model there.
    ``onset_columns`` (3c): extra columns of the state-0 model; ``prepare_block(origins, cutoff)`` adds
    the columns fitted per block (B2).
    """
    f = sp.FORMULATIONS[FORMULATION]
    col_reg = list(columns)
    extra = sp.e3_parameters(hyperparameters)
    margin_all = sp.e3_margin(origins, FORMULATION)
    parts, record = [], []
    for block, kind, period in blocks:
        test_sets, cutoff = eh._common_cutoffs(matrices, kind, period)
        o = prepare_block(origins, cutoff) if prepare_block is not None else origins
        train = _training(o, cutoff)
        counts = np.full((len(o), len(H)), np.nan)
        alpha_rows = np.full((len(o), len(H)), np.nan)
        groups = [(None, np.ones(len(o), bool), col_reg)]
        if state is not None:
            groups = [(s, state == s, col_reg + (list(onset_columns or []) if s == 0 else [])) for s in (0, 1)]
        for s, mask, cols in groups:
            sub = train[mask[train.index]] if s is not None else train
            fallback = s is not None and len(sub) < MIN_REGIME_ROWS
            use, use_cols = (train, col_reg) if fallback else (sub, cols)
            w = weights_fn(use) if weights_fn is not None else None
            reg, alphas = _fit(use, seed, use_cols, extra, margin_all, w)
            idx = np.flatnonzero(mask)
            counts[idx] = sp.predict_count(reg, o.iloc[idx][use_cols], f["conteo"], margin_all[idx])
            alpha_rows[idx] = alphas
            record.append({"bloque": block, "regimen": s, "filas_entrenamiento": len(use), "respaldo": fallback,
                           **{f"alpha_h{h}": a for h, a in zip(H, alphas)}, "corte": cutoff})
        for step, h in enumerate(H):
            pred = pd.DataFrame({"ubigeo": o.ubigeo, "semana_inicio": o[f"semana_inicio_h{h}"],
                                 "origen_cierre_mimo": o.origen_cierre, "casos_predichos": counts[:, step],
                                 "alpha": alpha_rows[:, step]})
            test = test_sets[h].merge(pred.dropna(subset=["semana_inicio"]), on=["ubigeo", "semana_inicio"],
                                      how="left", validate="one_to_one")
            if test.casos_predichos.isna().any() or not test.origen_cierre_mimo.eq(test.origen_cierre).all():
                raise ValueError(f"Predicciones incompletas o con origen distinto en {block} h={h}")
            prob = np.empty(len(test))
            for a in np.unique(test.alpha):
                m = test.alpha.eq(a).to_numpy()
                prob[m] = sp.negative_binomial_probability(test.casos_predichos[m], a, test.umbral_brote_casos[m])
            test["probabilidad_brote"] = prob
            parts.append(eh._output(test, block, test.casos_predichos, test.probabilidad_brote))
    output = pd.concat(parts, ignore_index=True).assign(estrategia="E3", formulacion=FORMULATION, semilla=seed)
    output.attrs["ajustes"] = pd.DataFrame(record)
    return output


# ---------------------------------------------------------------------------
# Phase 3 run: inputs, guard G8, variants, verdicts and readings
# ---------------------------------------------------------------------------

def phase3_inputs() -> dict:
    """Long cases, labels, matrices and origins of L (as in phase 1a) and the label series."""
    import phase1_history as p1
    from phase0_diagnosis import load_integrated, long_case_series, long_labels

    panel = load_integrated()
    cases, _ = long_case_series(panel)
    labels = long_labels(cases)
    matrices = p1.long_matrices(cases, labels)
    origins = p1.long_origins(cases, matrices[2])
    series = labels[["ubigeo", "anio", "semana", "semana_inicio", "casos_Dengue", "brote"]].copy()
    series["semana_inicio"] = pd.to_datetime(series.semana_inicio)
    return {"casos": cases, "matrices": matrices, "origenes": origins, "serie": series, "etiquetas": labels,
            "panel": panel}


def _config():
    from denguekay.model import frozen_configs as cf

    c = cf.CONFIG_2026_V1
    return c["columnas"], c["hiperparametros"]


def guard_g8(inp: dict, saved_l17: pd.DataFrame) -> dict:
    """G8: without weights nor regimes the loop reproduces the saved L (seed 17); with weights = 1, report."""
    import phase1_history as p1

    columns, hp = _config()
    blocks = p1.seasonal_blocks(p1.FIRST_BLOCK_SEASON_LONG)
    plain = predict_blocks_weighted(inp["matrices"], inp["origenes"], blocks, 17, columns, hp)
    ones = predict_blocks_weighted(inp["matrices"], inp["origenes"], blocks, 17, columns, hp,
                                   weights_fn=lambda t: np.ones(len(t)))
    exact = p1.compare_predictions(plain, saved_l17)
    with_ones = p1.compare_predictions(ones, saved_l17)
    return {"sin_pesos": exact, "pesos_1": {"diferencia_maxima": with_ones["diferencia_maxima"]},
            "pasa": exact["pasa"]}


def weights_for(variant: str, series: pd.DataFrame):
    if variant == "3a1":
        new = onset_weeks(series)
        return lambda train: onset_weights(train, new)
    if variant == "3a2":
        return season_weights
    return None


def run_variant(inp: dict, variant: str, seeds) -> dict:
    """Predictions (5 seeds) and protocol evaluation of 3a1, 3a2 or 3b."""
    import phase1_history as p1
    from denguekay.evaluation import protocol as pa

    columns, hp = _config()
    blocks = p1.seasonal_blocks(p1.FIRST_BLOCK_SEASON_LONG)
    state = origin_state(inp["origenes"], inp["serie"]) if variant == "3b" else None
    preds, evals, fits = {}, {}, []
    for seed in seeds:
        pred = predict_blocks_weighted(inp["matrices"], inp["origenes"], blocks, seed, columns, hp,
                                       weights_fn=weights_for(variant, inp["serie"]), state=state)
        fits.append(pred.attrs.pop("ajustes").assign(semilla=seed))
        preds[seed] = pred
        evals[seed] = pa.evaluate(pred, inp["serie"])
    return {"predicciones": preds, "evaluaciones": evals, "ajustes": pd.concat(fits, ignore_index=True)}


def reference_l(series: pd.DataFrame) -> dict:
    """L as saved in phase 1a, evaluated with the protocol (Platt per horizon, 1e-6)."""
    import phase2_calibration as p2
    from denguekay.evaluation import protocol as pa

    preds = p2.read_l_predictions()
    return {"predicciones": preds, "evaluaciones": {s: pa.evaluate(p, series) for s, p in preds.items()}}


def compare(candidate: dict, reference: dict) -> dict:
    """Preregistered verdict (``decide_multi_season``) plus the per-season metrics of both."""
    import preregistration as pr
    from denguekay.evaluation import protocol as pa

    blocks = [pr.block_name(s) for s in pr.DECIDING_SEASONS]
    med = {k: pa.seed_median([e["metricas"] for e in v["evaluaciones"].values()])
           for k, v in (("cand", candidate), ("ref", reference))}
    ranges = pa.tie_threshold(*(pa.seed_ranges([e["metricas"] for e in v["evaluaciones"].values()])
                                for v in (candidate, reference)))
    seed = pr.SEEDS[0]
    lead = pr.lead_time_difference_multi(candidate["evaluaciones"][seed]["antelacion"],
                                         reference["evaluaciones"][seed]["antelacion"], "alerta_050")
    verdict = pr.decide_multi_season(*(m[m.bloque.isin(blocks)] for m in (med["cand"], med["ref"])),
                                     ranges[ranges.bloque.isin(blocks)], lead)
    no_2010 = (2015, 2016, 2022, 2023)
    b4 = [pr.block_name(s) for s in no_2010]
    lead4 = pr.lead_time_difference_multi(candidate["evaluaciones"][seed]["antelacion"],
                                          reference["evaluaciones"][seed]["antelacion"], "alerta_050", no_2010)
    reading = pr.decide_multi_season(*(m[m.bloque.isin(b4)] for m in (med["cand"], med["ref"])),
                                     ranges[ranges.bloque.isin(b4)], lead4, seasons=no_2010, min_in_favour=3,
                                     guard_veto=pr.GUARD_VETO_AGAINST)
    both = med["cand"].merge(med["ref"], on=["horizonte", "bloque"], suffixes=("_cand", "_ref"))
    cols = ["horizonte", "bloque", "positivos_cand"] + [f"{m}_{v}" for m in (
        "f1_050", "recall_050", "precision_050", "auprc", "brier", "razon_mae", "razon_rmse") for v in ("cand", "ref")]
    report = [*blocks, pr.block_name(pr.CONTRAST_SEASON)]
    return {"veredicto": verdict, "antelacion": lead, "umbral_empate": ranges[ranges.bloque.isin(blocks)],
            "lectura_sin_2010": reading, "metricas": both[both.bloque.isin(report)][cols]}


def by_regime(variant: dict, series: pd.DataFrame, blocks: list[str]) -> dict:
    """Reading (Rosa): calibrated Brier and reliability per regime (state at the origin), seed median / seed 17."""
    import preregistration as pr
    from phase1_history import seed_median_of

    def regime(data):
        week = pd.to_datetime(data.origen_cierre) - pd.Timedelta(days=6)
        lab = series[["ubigeo", "semana_inicio", "brote"]].rename(columns={"semana_inicio": "w", "brote": "regimen"})
        key = pd.DataFrame({"ubigeo": data.ubigeo.astype(str).to_numpy(), "w": week.to_numpy()})
        reg = key.merge(lab.assign(ubigeo=lab.ubigeo.astype(str)), on=["ubigeo", "w"], how="left",
                        validate="many_to_one").regimen.fillna(0).astype(int).to_numpy()
        return data.assign(regimen=reg)

    briers, curves = {}, []
    for seed, e in variant["evaluaciones"].items():
        d = regime(e["datos"][e["datos"].bloque.isin(blocks) & e["datos"].probabilidad_calibrada.notna()])
        briers[seed] = (d.assign(se=(d.probabilidad_calibrada - d.brote) ** 2)
                        .groupby(["horizonte", "bloque", "regimen"])
                        .agg(n=("se", "size"), positivos=("brote", "sum"), brier=("se", "mean"),
                             prob_media=("probabilidad_calibrada", "mean"), prevalencia=("brote", "mean"))
                        .reset_index())
        if seed == pr.SEEDS[0]:
            for (h, b, r), g in d.groupby(["horizonte", "bloque", "regimen"]):
                curves.append(diag.reliability_curve(g.brote, g.probabilidad_calibrada, 10)
                              .reset_index(names="bin").assign(horizonte=h, bloque=b, regimen=r))
    return {"brier_por_regimen": seed_median_of(briers, ["horizonte", "bloque", "regimen"]),
            "fiabilidad_por_regimen_semilla_17": pd.concat(curves, ignore_index=True)}


# ---------------------------------------------------------------------------
# 3c: B1 and B2 on the long series (2000-2025), in memory
# ---------------------------------------------------------------------------

def _b1_b2_columns() -> tuple[list[str], list[str]]:
    from denguekay.features import onset_features as fi

    return list(fi.COLUMNS["B1"]), list(fi.COLUMNS["B2"])


def long_spatial_table(geography: pd.DataFrame, cases: pd.DataFrame, labels: pd.DataFrame,
                       cutoff: pd.Timestamp) -> pd.DataFrame:
    """B1 and B2 per district and week ``w`` with data of weeks <= ``w``, on the long series.

    The same formulas as ``evaluation.onsets.weekly_status`` (knn5 neighbours, province and region without
    the district itself, core = 5 districts with the most cases closed at ``cutoff``), but the cases start in
    2000 and the label in 2005 (before 2005 the outbreak fractions are null; no origin uses them). Only
    the core ranking depends on ``cutoff``.
    """
    from denguekay.evaluation import onsets as di
    from denguekay.features.neighbors import geographic_catalog, neighborhood_matrix

    geo = geographic_catalog(geography)
    weights, _ = neighborhood_matrix(geo, k=di.K_NEIGHBORS)
    ids = weights.index
    c = cases.assign(semana_inicio=pd.to_datetime(cases.semana_inicio), ubigeo=cases.ubigeo.astype("string"))
    y = c.pivot(index="semana_inicio", columns="ubigeo", values="casos_Dengue").reindex(columns=ids).sort_index()
    if y.isna().any().any():
        raise ValueError("Faltan distrito-semanas en la serie de casos")
    lab = labels.assign(semana_inicio=pd.to_datetime(labels.semana_inicio), ubigeo=labels.ubigeo.astype("string"))
    b = lab.pivot(index="semana_inicio", columns="ubigeo", values="brote").reindex(index=y.index, columns=ids)
    b = b.astype(float)
    w = weights.to_numpy()
    yv, bv = y.to_numpy(float), b.to_numpy(float)
    active = (yv > 0).astype(float)
    new_rows = ((y > 0) & (y.shift(1) == 0)).to_numpy(float)
    provinces = geo.set_index("ubigeo").loc[ids, "provincia"].to_numpy()
    prov = (provinces[:, None] == provinces[None, :]).astype(float)
    np.fill_diagonal(prov, 0)
    region = np.ones_like(prov) - np.eye(len(ids))
    n_prov, n_reg = prov.sum(axis=1), region.sum(axis=1)
    order = list(di.core_ranking(c, cutoff).index)
    core = np.zeros_like(prov)
    for i, u in enumerate(ids):
        for v in [v for v in order if v != u][:di.N_CORE]:
            core[i, ids.get_loc(v)] = 1.0

    def frame(m):
        return pd.DataFrame(np.asarray(m), index=y.index, columns=ids)

    vals = {
        "vecinos_log_media_casos": np.log1p(frame(yv @ w.T)),
        "vecinos_frac_en_brote": frame(bv @ w.T),
        "vecinos_n_casos_nuevos": frame(new_rows @ (w > 0).T.astype(float)),
        "provincia_log_otros_casos": np.log1p(frame(yv @ prov.T)),
        "provincia_otros_frac_en_brote": frame(bv @ prov.T / n_prov),
        "region_log_otros_casos": np.log1p(frame(yv @ region.T)),
        "region_otros_frac_en_brote": frame(bv @ region.T / n_reg),
        "nucleo_log_casos": np.log1p(frame(yv @ core.T)),
        "nucleo_frac_en_brote": frame(bv @ core.T / di.N_CORE),
    }
    for base in ("vecinos_log_media_casos", "provincia_log_otros_casos", "region_log_otros_casos"):
        vals[f"{base}_cambio_1"] = vals[base] - vals[base].shift(1)
        vals[f"{base}_cambio_4"] = vals[base] - vals[base].shift(4)
    vals["nucleo_log_casos_cambio_4"] = vals["nucleo_log_casos"] - vals["nucleo_log_casos"].shift(4)
    b1, b2 = _b1_b2_columns()
    out = pd.concat({k: vals[k].stack(future_stack=True) for k in b1 + b2}, axis=1)
    out = out.rename_axis(["semana_inicio", "ubigeo"]).reset_index()
    out["ubigeo"] = out.ubigeo.astype("string")
    return out[["ubigeo", "semana_inicio", *b1, *b2]]


def add_spatial(origins: pd.DataFrame, table: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """The columns of the origin week (``onset_features.add``)."""
    from denguekay.features import onset_features as fi

    return fi.add(origins, table, columns)


def spatial_prepare_block(geography: pd.DataFrame, cases: pd.DataFrame, labels: pd.DataFrame):
    """``prepare_block`` for 3c: B1 (no fit) and B2 with the core ranking of each block's cut-off."""
    b1, b2 = _b1_b2_columns()
    cache: dict = {}

    def prepare(origins: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame:
        key = pd.Timestamp(cutoff)
        if key not in cache:
            cache[key] = long_spatial_table(geography, cases, labels, key)
        return add_spatial(origins, cache[key], b1 + b2)
    return prepare


def run_3c_prime(inp: dict, seeds) -> dict:
    """3c' (amendment): L + B1 + B2 in the single model, B2 with each block's core ranking."""
    import phase1_history as p1
    from denguekay.evaluation import protocol as pa

    columns, hp = _config()
    b1, b2 = _b1_b2_columns()
    prepare = spatial_prepare_block(inp["panel"], inp["casos"], inp["etiquetas"])
    blocks = p1.seasonal_blocks(p1.FIRST_BLOCK_SEASON_LONG)
    preds, evals = {}, {}
    for seed in seeds:
        pred = predict_blocks_weighted(inp["matrices"], inp["origenes"], blocks, seed, [*columns, *b1, *b2], hp,
                                       prepare_block=prepare)
        pred.attrs.pop("ajustes")
        preds[seed] = pred
        evals[seed] = pa.evaluate(pred, inp["serie"])
    return {"predicciones": preds, "evaluaciones": evals}
