"""Phase 5: counts over L (trained from 2005, Platt per horizon with clip 1e-6).

Variants against L (``preregistration.PHASE5``):

- 5a mixture with persistence: count = w·μ + (1 − w)·persistence per horizon and block, with w fitted
  on the out-of-sample predictions of earlier blocks whose targets closed by the block's cut-off (the
  data available at the cut-off, like the chronological Platt). Only the count changes; μ of the
  probability does not.
- 5b max_delta_step chosen per block from an extended grid with an inner validation (the last closed
  season of the block's training), with the training origins only.
- 5c the season weights of 3a2 (predictions saved in phase 3).
"""

import numpy as np
import pandas as pd

from denguekay.config.paths import MODELS
from denguekay.evaluation import protocol as pa
from denguekay.model import probabilistic_output as sp

W_GRID = np.round(np.linspace(0, 1, 101), 2)
MDS_GRID = (0.7, 1.0, 2.0, 3.0, 5.0, 10.0)   # 0.7 = L (XGBoost default with count:poisson)
MDS_REFERENCE = 0.7
OUTPUT_DIR = MODELS / "experimentos" / "mejora_modelo" / "fase5"
SAVED_3A2 = MODELS / "experimentos" / "mejora_modelo" / "fase3" / "predicciones_3a2.csv.gz"


# ---------------------------------------------------------------------------
# 5a · mixture with persistence (chronological, per horizon)
# ---------------------------------------------------------------------------

def fit_w(mu: np.ndarray, persistence: np.ndarray, y: np.ndarray, grid: np.ndarray = W_GRID) -> float:
    """w of the grid with the lowest MAE of w·μ + (1 − w)·persistence; ties -> the largest w (closest to L)."""
    mae = np.array([np.abs(w * mu + (1 - w) * persistence - y).mean() for w in grid])
    best = np.flatnonzero(np.isclose(mae, mae.min(), rtol=0, atol=1e-12))
    return float(grid[best.max()])


def mix_chronologically(pred: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Replace ``casos_predichos`` by the mixture; w of a block uses the rows of earlier blocks of the same
    horizon whose label closed by the block's first origin (``protocol.block_cutoff``). No rows -> w = 1."""
    data = pred.copy()
    data["semana_inicio"] = pd.to_datetime(data.semana_inicio)
    data["origen_cierre"] = pd.to_datetime(data.origen_cierre)
    mixed = data.casos_predichos.to_numpy(float).copy()
    record = []
    for h, by_h in data.groupby("horizonte"):
        onsets = by_h.groupby("bloque").semana_inicio.min().sort_values()
        for block, start in onsets.items():
            idx = by_h.index[by_h.bloque.eq(block)]
            cutoff = pa.block_cutoff(by_h.loc[idx])
            prev = by_h[by_h.bloque.map(onsets).lt(start)]
            prev = prev[(prev.semana_inicio + pd.Timedelta(days=6)).le(cutoff)]
            w = (fit_w(prev.casos_predichos.to_numpy(float), prev.persistencia.to_numpy(float),
                       prev.casos_Dengue.to_numpy(float)) if len(prev) else 1.0)
            pos = data.index.get_indexer(idx)
            mixed[pos] = w * data.casos_predichos.to_numpy(float)[pos] + (1 - w) * data.persistencia.to_numpy(float)[pos]
            record.append({"horizonte": h, "bloque": block, "w": w, "filas_ajuste": len(prev), "corte": cutoff})
    data["casos_predichos"] = mixed
    return data, pd.DataFrame(record)


def evaluate_mixture(pred: pd.DataFrame, series: pd.DataFrame) -> dict:
    """The protocol with the mixed count; the probability (and so F1, AUPRC, Brier, lead time) is L's."""
    mixed, record = mix_chronologically(pred)
    result = pa.evaluate(mixed, series)
    result["w"] = record
    return result


# ---------------------------------------------------------------------------
# 5b · max_delta_step chosen per block (inner validation inside the training)
# ---------------------------------------------------------------------------

def _season_h(train: pd.DataFrame, h: int) -> np.ndarray:
    from phase3_onsets import target_season

    return target_season(train[f"semana_inicio_h{h}"])


def mds_selector(hyperparameters: dict, grid=MDS_GRID, reference: float = MDS_REFERENCE):
    """``hyperparameters_fn`` for ``phase3_onsets.predict_blocks_weighted``.

    Inside the block's training origins: validation = origins whose h=2 target is in the last season of
    the training; inner training = origins whose h=4 target is in an earlier season (no overlap). The
    value with the lowest mean MAE over the three horizons on the validation wins; ties -> the closest to
    0.7. With fewer than 2 seasons in the training, 0.7.
    """
    from phase3_onsets import FORMULATION, H, _fit

    f = sp.FORMULATIONS[FORMULATION]

    def choose(train: pd.DataFrame, margin_all: np.ndarray, columns: list[str], seed: int) -> dict:
        s2, s4 = _season_h(train, H[0]), _season_h(train, H[-1])
        last = s2.max()
        inner, valid = train[s4 < last], train[s2 == last]
        if inner.empty or valid.empty or len(np.unique(s4[s4 < last])) < 1:
            return {**hyperparameters, "max_delta_step": reference}
        y = np.column_stack([valid[f"casos_Dengue_h{h}"] for h in H])
        scores = {}
        for v in grid:
            extra = sp.e3_parameters({**hyperparameters, "max_delta_step": v})
            reg, _ = _fit(inner, seed, columns, extra, margin_all, None)
            mu = sp.predict_count(reg, valid[columns], f["conteo"], margin_all[valid.index])
            scores[v] = float(np.abs(mu - y).mean())
        best = min(scores.values())
        tied = [v for v, s in scores.items() if np.isclose(s, best, rtol=0, atol=1e-12)]
        return {**hyperparameters, "max_delta_step": min(tied, key=lambda v: (abs(v - reference), v))}

    return choose


def run_mds(inp: dict, seeds, grid=MDS_GRID) -> dict:
    """5b: predictions (5 seeds) with max_delta_step chosen per block, and the protocol evaluation."""
    import phase1_history as p1
    from phase3_onsets import _config, predict_blocks_weighted

    columns, hp = _config()
    blocks = p1.seasonal_blocks(p1.FIRST_BLOCK_SEASON_LONG)
    preds, evals, fits = {}, {}, []
    for seed in seeds:
        pred = predict_blocks_weighted(inp["matrices"], inp["origenes"], blocks, seed, columns, hp,
                                       hyperparameters_fn=mds_selector(hp, grid))
        fits.append(pred.attrs.pop("ajustes").assign(semilla=seed))
        preds[seed] = pred
        evals[seed] = pa.evaluate(pred, inp["serie"])
    return {"predicciones": preds, "evaluaciones": evals, "ajustes": pd.concat(fits, ignore_index=True)}


# ---------------------------------------------------------------------------
# 5c · 3a2 from the saved phase 3 predictions
# ---------------------------------------------------------------------------

def read_3a2() -> dict[int, pd.DataFrame]:
    saved = pd.read_csv(SAVED_3A2, dtype={"ubigeo": "string"}, float_precision="round_trip")
    saved["ubigeo"] = saved.ubigeo.astype(object)
    return {int(s): g.drop(columns="semilla").reset_index(drop=True) for s, g in saved.groupby("semilla")}


# ---------------------------------------------------------------------------
# Decision inputs: seed medians and ranges with the RMSE ratio
# ---------------------------------------------------------------------------

METRICS = ("razon_mae", "razon_rmse", "f1_050", "auprc", "brier")


def seed_median(variant: dict) -> pd.DataFrame:
    return pa.seed_median([e["metricas"] for e in variant["evaluaciones"].values()])


def seed_ranges(variant: dict) -> pd.DataFrame:
    every = pd.concat([e["metricas"][["horizonte", "bloque", *METRICS]] for e in variant["evaluaciones"].values()])
    g = every.groupby(["horizonte", "bloque"])[list(METRICS)]
    return (g.max() - g.min()).reset_index()


def tie_threshold(a: dict, b: dict) -> pd.DataFrame:
    ra, rb = seed_ranges(a).set_index(["horizonte", "bloque"]), seed_ranges(b).set_index(["horizonte", "bloque"])
    return np.maximum(ra, rb.reindex(ra.index)).reset_index()


# ---------------------------------------------------------------------------
# Reading (Rosa): the NB2 probability from the mixed μ, then Platt
# ---------------------------------------------------------------------------

L_ALPHAS = MODELS / "experimentos" / "mejora_modelo" / "fase1a" / "alfas_L.csv"


def read_l_alphas() -> pd.DataFrame:
    return pd.read_csv(L_ALPHAS, float_precision="round_trip")


def nb2_from_counts(pred: pd.DataFrame, alphas: pd.DataFrame, seed: int) -> pd.DataFrame:
    """``probabilidad_brote`` = P(cases >= k) with NB2(``casos_predichos``, α of L of the block, horizon and seed)."""
    a = alphas[alphas.semilla.eq(seed)].set_index(["bloque", "horizonte"]).alpha
    out = pred.copy()
    prob = np.empty(len(out))
    for (block, h), g in out.groupby(["bloque", "horizonte"]):
        pos = out.index.get_indexer(g.index)
        prob[pos] = sp.negative_binomial_probability(g.casos_predichos, float(a[(block, h)]), g.umbral_brote_casos)
    out["probabilidad_brote"] = prob
    return out


def same_mu_reading(preds: dict[int, pd.DataFrame], series: pd.DataFrame) -> dict:
    """5a with the probability also from the mixed μ: protocol evaluation per seed (does not decide).

    Check first that NB2 with L's μ and α reproduces the saved L probability (maximum difference).
    """
    alphas = read_l_alphas()
    check = max(float(np.abs(nb2_from_counts(p, alphas, s).probabilidad_brote - p.probabilidad_brote).max())
                for s, p in preds.items())
    evals = {}
    for s, p in preds.items():
        mixed, _ = mix_chronologically(p)
        evals[s] = pa.evaluate(nb2_from_counts(mixed, alphas, s), series)
    return {"diferencia_max_reproduccion_L": check, "evaluaciones": evals}
