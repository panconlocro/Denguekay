"""Read-only diagnosis against persistence (after the climate matrix; Rosa, 2026-11-08).

No variant is trained and the model is not changed: everything is computed from the saved predictions of
L + 5a, b3 (``temporada_2026``) and d3 (``matriz_clima``), re-evaluated with the study protocol (Platt per horizon
from earlier blocks and the 5a mixture with the w of earlier blocks).

1. Count error per phase of the regional curve (valle, subida, pico, bajada), with the mixed count, the model's μ
   (w = 1) and persistence (w = 0).
2. The 5a weight w per block, and the MAE ratio that w = 0, w = 1 and the w that would have been best in hindsight
   give (a reading, never a choice).
3. The calibrated probability before each clean onset against the persistence signal.
4. Calibration: mean calibrated probability against the observed outbreak rate, per horizon and block.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from denguekay.evaluation import episodes as diag

import phase5_counts as p5

DIAGNOSIS_BLOCKS = ("temporada_2026", "posterior_2026")
PREVIOUS_WEEKS = 4          # target weeks inicio-4 .. inicio-1 before an onset


def seed_median_frame(frames: list[pd.DataFrame], keys: list[str]) -> pd.DataFrame:
    """Median over seeds of every numeric column, per ``keys``."""
    every = pd.concat(frames, ignore_index=True)
    numeric = [c for c in every.columns if c not in keys and pd.api.types.is_numeric_dtype(every[c])]
    return every.groupby(keys, observed=True)[numeric].median().reset_index()


def with_counts(data: pd.DataFrame, raw: pd.DataFrame) -> pd.DataFrame:
    """Evaluated rows (mixed count in ``casos_predichos``) plus the model's own μ (``casos_modelo``)."""
    key = ["ubigeo", "semana_inicio", "horizonte", "bloque"]
    mu = raw[key + ["casos_predichos"]].rename(columns={"casos_predichos": "casos_modelo"})
    mu = mu.assign(semana_inicio=pd.to_datetime(mu.semana_inicio))
    out = data.assign(semana_inicio=pd.to_datetime(data.semana_inicio))
    return out.merge(mu, on=key, how="left", validate="one_to_one")


def phase_errors(data: pd.DataFrame, blocks=DIAGNOSIS_BLOCKS) -> pd.DataFrame:
    """MAE, bias and predicted/observed sum per phase of the curve for the mixed count, the model's μ and
    persistence. Bias = mean(predicted - observed): negative = falls short."""
    d = data[data.bloque.isin(blocks)].copy()
    d["fase"] = diag.curve_phase(d)
    rows = []
    for (h, block, phase), g in d.groupby(["horizonte", "bloque", "fase"], observed=True):
        y = g.casos_Dengue.to_numpy(float)
        row = {"horizonte": h, "bloque": block, "fase": phase, "n": len(g), "semanas": g.semana_inicio.nunique(),
               "casos_observados": float(y.sum())}
        per_mae = np.abs(g.persistencia.to_numpy(float) - y).mean()
        for name, col in (("mezcla", "casos_predichos"), ("modelo", "casos_modelo"), ("persistencia", "persistencia")):
            p = g[col].to_numpy(float)
            row[f"mae_{name}"] = float(np.abs(p - y).mean())
            row[f"sesgo_{name}"] = float((p - y).mean())
            row[f"suma_{name}_sobre_real"] = float(p.sum() / y.sum()) if y.sum() else np.nan
            if name != "persistencia":
                row[f"razon_mae_{name}"] = float(row[f"mae_{name}"] / per_mae) if per_mae else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def mixture_reading(data: pd.DataFrame, w_used: pd.DataFrame, blocks=DIAGNOSIS_BLOCKS,
                    grid: np.ndarray = p5.W_GRID) -> pd.DataFrame:
    """Per horizon and block: the w used, and the MAE ratio against persistence with that w, with w = 1 (model
    only), w = 0 (persistence only, 1 by definition) and with the grid w of lowest MAE in the block itself
    (hindsight; a reading, not a choice)."""
    rows = []
    for (h, block), g in data[data.bloque.isin(blocks)].groupby(["horizonte", "bloque"]):
        y = g.casos_Dengue.to_numpy(float)
        mu = g.casos_modelo.to_numpy(float)
        per = g.persistencia.to_numpy(float)
        per_mae = np.abs(per - y).mean()
        w = float(w_used.loc[w_used.horizonte.eq(h) & w_used.bloque.eq(block), "w"].iloc[0])
        ratio = lambda v: float(np.abs(v * mu + (1 - v) * per - y).mean() / per_mae)
        best = p5.fit_w(mu, per, y, grid)
        rows.append({"horizonte": h, "bloque": block, "w_usado": w, "razon_mae_w_usado": ratio(w),
                     "razon_mae_w1": ratio(1.0), "razon_mae_w0": ratio(0.0), "w_retrospectivo": best,
                     "razon_mae_w_retrospectivo": ratio(best)})
    return pd.DataFrame(rows)


def onset_probabilities(data: pd.DataFrame, lead: pd.DataFrame, blocks=("temporada_2026",),
                        previous: int = PREVIOUS_WEEKS) -> pd.DataFrame:
    """For each clean onset (``lead`` = protocol ``antelacion``) and horizon: the calibrated probability for the
    onset week and the highest one for the ``previous`` target weeks before it; persistence (cases at the origin)
    against the threshold; and the lead time of the 0.50 alert and of the persistence alert."""
    week = pd.Timedelta(days=7)
    d = data[data.bloque.isin(blocks)]
    by = {k: g.set_index("semana_inicio") for k, g in d.groupby(["horizonte", "ubigeo"])}
    rows = []
    for ep in lead[lead.bloque.isin(blocks)].itertuples(index=False):
        g = by.get((ep.horizonte, ep.ubigeo))
        start = pd.Timestamp(ep.inicio)
        at = g.loc[start] if g is not None and start in g.index else None
        before = g.loc[start - previous * week: start - week] if g is not None else pd.DataFrame()
        rows.append({
            "horizonte": ep.horizonte, "ubigeo": ep.ubigeo, "inicio": start,
            "p_semana_inicio": float(at.probabilidad_calibrada) if at is not None else np.nan,
            "p_max_previas": float(before.probabilidad_calibrada.max()) if len(before) else np.nan,
            "persistencia_semana_inicio": float(at.persistencia) if at is not None else np.nan,
            "umbral": float(at.umbral_brote_casos) if at is not None else np.nan,
            "alerta_persistencia_semana_inicio": bool(at.alerta_persistencia) if at is not None else False,
            "antelacion_050": ep.alerta_050, "antelacion_persistencia": ep.alerta_persistencia,
        })
    return pd.DataFrame(rows)


def onset_summary(table: pd.DataFrame, min_lead: int = 2) -> pd.DataFrame:
    """Per horizon: onsets, median probability for the onset week, how many get p >= 0.50 for the onset week,
    how many are warned >= ``min_lead`` weeks ahead by each alert, and how many persistence flags."""
    rows = []
    for h, g in table.groupby("horizonte"):
        rows.append({"horizonte": h, "inicios": len(g),
                     "p_mediana_semana_inicio": float(g.p_semana_inicio.median()),
                     "p_mediana_max_previas": float(g.p_max_previas.median()),
                     "con_p_050_semana_inicio": int(g.p_semana_inicio.ge(0.5).sum()),
                     "persistencia_alerta_semana_inicio": int(g.alerta_persistencia_semana_inicio.sum()),
                     "avisados_050": int(g.antelacion_050.ge(min_lead).sum()),
                     "avisados_persistencia": int(g.antelacion_persistencia.ge(min_lead).sum())})
    return pd.DataFrame(rows)


def calibration_in_large(data: pd.DataFrame, blocks=DIAGNOSIS_BLOCKS) -> pd.DataFrame:
    """Mean calibrated probability against the observed outbreak rate, per horizon and block (ratio > 1 =
    over-forecast), plus the same within the observed outbreak weeks and the non-outbreak ones."""
    rows = []
    for (h, block), g in data[data.bloque.isin(blocks)].groupby(["horizonte", "bloque"]):
        p, y = g.probabilidad_calibrada.to_numpy(float), g.brote.to_numpy(int)
        rows.append({"horizonte": h, "bloque": block, "n": len(g), "brotes": int(y.sum()),
                     "tasa_observada": float(y.mean()), "prob_media": float(p.mean()),
                     "razon_prob_tasa": float(p.mean() / y.mean()) if y.mean() else np.nan,
                     "prob_media_en_brote": float(p[y == 1].mean()) if y.any() else np.nan,
                     "prob_media_sin_brote": float(p[y == 0].mean())})
    return pd.DataFrame(rows)
