"""E8: a separate two-output model for horizons 8 and 12 weeks (protocol addendum ``protocolo_e8.md``).

The predictors are the origin rows of the paper's arms (``historia_geo`` and ``b3_obs``); only the targets and the
fitted model change. Training, calibration and the count blend follow the same chronological rules as the
(2, 3, 4) arms.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import common as c

HORIZONS = (8, 12)
FORMULATION = "S4_s3"
ADDENDUM = c.STUDY / "protocolo_e8.md"
OUT_DIR = c.ARMS_DIR / "largo_plazo"
BLOCKS = [b for b in c.spatial.BLOCK_LIST if b[1] == "temporada"]


def with_long_targets(origins: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    """Origins plus target week, cases, label and threshold at origin + h for h in ``HORIZONS``."""
    out = origins.copy()
    week = out.origen_cierre - 6 * c.DAY
    table = labels[["ubigeo", "anio", "semana", "semana_inicio", "casos_Dengue", "brote", "umbral_brote_casos"]].copy()
    table["semana_inicio"] = pd.to_datetime(table.semana_inicio)
    for h in HORIZONS:
        keys = pd.DataFrame({"ubigeo": out.ubigeo.astype(str).to_numpy(), "semana_inicio": (week + pd.Timedelta(weeks=h)).to_numpy()})
        joined = keys.merge(table, on=["ubigeo", "semana_inicio"], how="left", validate="many_to_one")
        for column in ("semana_inicio", "anio", "semana", "casos_Dengue", "brote", "umbral_brote_casos"):
            out[f"{column}_h{h}"] = joined[column].to_numpy()
    return out


def test_set(origins: pd.DataFrame, season: int, h: int) -> pd.DataFrame:
    """Rows whose target week (origin + h) falls in ``season``, in the column layout of ``eh._output``."""
    target = origins[f"semana_inicio_h{h}"]
    available = target.notna() & origins[f"brote_h{h}"].notna()
    data = origins.loc[available].copy()
    data["temporada"] = c.spatial.assign_season(data[f"anio_h{h}"].astype(int), data[f"semana_h{h}"].astype(int), 35)
    data = data[data.temporada.eq(season)]
    return pd.DataFrame({
        "ubigeo": data.ubigeo.astype(str).to_numpy(), "anio": data[f"anio_h{h}"].astype(int).to_numpy(),
        "semana": data[f"semana_h{h}"].astype(int).to_numpy(), "semana_inicio": pd.to_datetime(data[f"semana_inicio_h{h}"]).to_numpy(),
        "origen_cierre": data.origen_cierre.to_numpy(), "horizonte": h, "casos_Dengue": data[f"casos_Dengue_h{h}"].astype(int).to_numpy(),
        "brote": data[f"brote_h{h}"].astype(int).to_numpy(), "umbral_brote_casos": data[f"umbral_brote_casos_h{h}"].to_numpy(float),
        "persistencia": data.hist_lag_a.to_numpy(float), "_fila": data.index.to_numpy(),
    })


def fit_predict(origins: pd.DataFrame, columns: list[str], hp: dict, seed: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Raw predictions of every season block for one arm and seed, with the block records."""
    sp = c.spatial.sp
    margin = np.repeat(sp.persistence_margin(origins.hist_lag_a)[:, None], len(HORIZONS), axis=1)
    params = sp.e3_parameters(hp)
    parts, records = [], []
    for block, _, season in BLOCKS:
        tests = {h: test_set(origins, season, h) for h in HORIZONS}
        if any(t.empty for t in tests.values()):
            continue
        firsts = [t.loc[t.semana_inicio.eq(t.semana_inicio.min()), "origen_cierre"].min() for t in tests.values()]
        cutoff = min(firsts)
        complete = origins.dropna(subset=[f"semana_inicio_h{h}" for h in HORIZONS] + [f"casos_Dengue_h{h}" for h in HORIZONS])
        closed = (pd.to_datetime(complete[f"semana_inicio_h{HORIZONS[-1]}"]) + 6 * c.DAY).le(cutoff)
        train = complete[closed]
        last_label = max((pd.to_datetime(train[f"semana_inicio_h{h}"]) + 6 * c.DAY).max() for h in HORIZONS)
        if train.empty or last_label > cutoff or not (train.origen_cierre < cutoff).all():
            raise ValueError(f"Training window leaks into {block}")
        y = np.column_stack([train[f"casos_Dengue_h{h}"].to_numpy(float) for h in HORIZONS])
        reg = sp.fit_count(train[columns], y, "poisson_margen", seed, margin[train.index], **params)
        fitted = sp.predict_count(reg, train[columns], "poisson_margen", margin[train.index])
        alphas = [sp.negative_binomial_dispersion(fitted[:, i], y[:, i]) for i in range(len(HORIZONS))]
        for i, h in enumerate(HORIZONS):
            t = tests[h]
            if (t.origen_cierre < cutoff).any():
                raise ValueError(f"Test origin before the cutoff in {block}")
            rows = t._fila.to_numpy()
            mu = sp.predict_count(reg, origins.loc[rows, columns], "poisson_margen", margin[rows])[:, i]
            p = sp.negative_binomial_probability(mu, alphas[i], t.umbral_brote_casos)
            parts.append(t.drop(columns="_fila").assign(bloque=block, casos_predichos=mu, probabilidad_brote=p,
                                                         alpha_usada=alphas[i]))
            records.append({"bloque": block, "horizonte": h, "corte": cutoff, "ultima_etiqueta_entrenamiento": last_label,
                            "primer_origen_prueba": t.origen_cierre.min(), "filas_entrenamiento": len(train),
                            "alpha": alphas[i], "semilla": seed})
    return pd.concat(parts, ignore_index=True), pd.DataFrame(records)


def finish(pred: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Chronological Platt and count blend (same functions as the (2, 3, 4) arms)."""
    calibrated, record = c.spatial.pa.calibrate_chronologically(pred)
    mixed, weights = c.archive.original.p5.mix_chronologically(pred)
    out = pred.rename(columns={"casos_predichos": "mu_modelo", "probabilidad_brote": "probabilidad_cruda"})
    out["probabilidad_calibrada"] = calibrated.probabilidad_calibrada.to_numpy()
    out["conteo_publicado"] = mixed.casos_predichos.to_numpy()
    return out, record.merge(weights[["horizonte", "bloque", "w"]], on=["horizonte", "bloque"], how="left")
