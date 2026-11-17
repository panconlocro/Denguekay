"""E13: direct classifier of elevated weeks (formulation S3; ``protocolo_revision.md``).

The published count comes from the same Poisson model with the persistence offset as the primary arms. The
probability of an elevated week comes from a multi-output XGBoost classifier instead of the NB2 exceedance. The
classifier also receives ``log(k)`` of each target week, which the NB2 route uses through the exceedance.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import common as c

FORMULATION = "S3"
OUT_DIR = c.ARMS_DIR / "clasificador"
THRESHOLDS = [f"log_k_h{h}" for h in c.HORIZONS]


def with_thresholds(origins: pd.DataFrame, matrices: dict) -> pd.DataFrame:
    """``log(k)`` of the three target weeks of every origin (k = threshold count, known before the origin)."""
    out = origins
    for h in c.HORIZONS:
        k = matrices[h][["ubigeo", "semana_inicio"]].assign(
            **{f"log_k_h{h}": np.log(np.asarray(c.spatial.sp.count_threshold(matrices[h].umbral_brote_casos), float))})
        out = out.merge(k.rename(columns={"semana_inicio": f"semana_inicio_h{h}"}), on=["ubigeo", f"semana_inicio_h{h}"],
                        how="left", validate="many_to_one")
    if len(out) != len(origins) or not out.index.equals(origins.index):
        raise ValueError("Thresholds changed the origin table")
    return out


def predict(inputs: dict, origins: pd.DataFrame, blocks, columns: list[str], params: dict, seed: int):
    """``run_spatial_controls.predict`` with the S3 classifier as the probability."""
    sp, eh = c.spatial.sp, c.spatial.eh
    args = sp.e3_parameters(params)
    margin = sp.e3_margin(origins, FORMULATION)
    features = [*columns, *THRESHOLDS]
    parts, fits = [], []
    for block, kind, period in blocks:
        tests, cutoff = eh._common_cutoffs(inputs["matrices"], kind, period)
        fit = sp.fit_e3(origins, cutoff, seed, FORMULATION, columns, features, args, margin)
        first = min(t.origen_cierre.min() for t in tests.values())
        last = max(t.origen_cierre.max() for t in tests.values())
        selected = np.flatnonzero(origins.origen_cierre.between(first, last))
        rows = origins.iloc[selected]
        means = sp.predict_count(fit.regressor, rows[columns], sp.FORMULATIONS[FORMULATION]["conteo"], margin[selected])
        probs = fit.classifier.predict_proba(rows[features])
        targets = rows[["ubigeo", "origen_cierre"]]
        for j, h in enumerate(c.HORIZONS):
            test = tests[h].merge(targets.assign(mu=means[:, j], p=probs[:, j]), on=["ubigeo", "origen_cierre"],
                                  how="left", validate="one_to_one")
            if test[["mu", "p"]].isna().any().any():
                raise ValueError(f"Missing origin in {block}, h{h}")
            parts.append(eh._output(test, block, test.mu, test.p))
        fits.append({"bloque": block, "corte": cutoff, "semilla": seed, "regimen": None,
                     "filas_entrenamiento": len(fit.train), **{f"alpha_h{h}": np.nan for h in c.HORIZONS}})
    return pd.concat(parts, ignore_index=True), pd.DataFrame(fits)


def fit_arm(inputs, origins, arm: str, columns: list[str], hp: dict, seed: int, extra: dict) -> Path:
    """One arm and seed on the 20 blocks (cached), with the checks of ``common.fit_arm`` except the dispersion."""
    dest = OUT_DIR / f"{arm}_s{seed}"
    expected = c.fingerprint(arm, columns, hp, extra)
    if (dest / "control.json").exists():
        if json.loads((dest / "control.json").read_text())["huella"] != expected:
            raise ValueError(f"Cached fit from another configuration: {dest}")
        return dest
    pred, fits = predict(inputs, origins, c.spatial.BLOCK_LIST, columns, hp, seed)
    table = c.archive.closure.full_table(pred, fits, arm, seed)
    guard = c.archive.closure.check_table(table)
    if (table.duplicated(c.archive.closure.KEY).any() or guard["calibrada_sin_platt"]
            or guard["platt_diferencia_maxima"] > 1e-12 or guard["conteo_diferencia_maxima"] > 1e-12):
        raise ValueError(f"Invalid predictions in {arm}_s{seed}")
    return c.save_table(dest, table, fits, expected, guard)
