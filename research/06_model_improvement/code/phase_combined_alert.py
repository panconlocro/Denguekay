"""Combined alert (preregistration ``COMBINED_ALERT``): calibrated p >= 0.50 OR the protocol's persistence alert,
computed on the saved predictions of d3 and b3 (no retraining) and compared with the 0.50 alert alone."""

from __future__ import annotations

import pandas as pd

from denguekay.evaluation import protocol as pa

import phase5_counts as p5
import preregistration as pr

ALERTS = ["alerta_050", "alerta_persistencia"]


def combine(data: pd.DataFrame) -> pd.DataFrame:
    """Evaluated rows with ``alerta_050`` replaced by ``alerta_050 | alerta_persistencia`` (the 0.50 alert alone
    kept as ``alerta_050_sola``)."""
    out = data.copy()
    out["alerta_050_sola"] = out.alerta_050.astype(bool)
    out["alerta_050"] = out.alerta_050.astype(bool) | out.alerta_persistencia.astype(bool)
    return out


def evaluate_both(pred: pd.DataFrame, series: pd.DataFrame) -> dict:
    """The study protocol (5a mixture) once; then metrics and lead time with the 0.50 alert alone and with the
    combined alert. Only the alert columns differ between the two."""
    base = p5.evaluate_mixture(pred, series)
    data = base["datos"]
    comb = combine(data)
    return {
        "sola": {"metricas": base["metricas"], "antelacion": base["antelacion"]},
        "combinada": {"metricas": pa.metrics_by_block(comb),
                      "antelacion": pa.clean_lead_time(comb, series, ALERTS)},
    }


def added_false_alarms(sola: pd.DataFrame, combinada: pd.DataFrame) -> pd.DataFrame:
    """Per horizon and block (seed medians): false alarms of each alert and the ones the combined alert adds."""
    key = ["horizonte", "bloque"]
    m = sola[key + ["fp_050", "vp_050"]].merge(combinada[key + ["fp_050", "vp_050"]], on=key,
                                                suffixes=("_sola", "_combinada"))
    m["fp_anadidas"] = m.fp_050_combinada - m.fp_050_sola
    m["vp_anadidos"] = m.vp_050_combinada - m.vp_050_sola
    return m


def false_alarms_by_regime(added: pd.DataFrame) -> pd.DataFrame:
    """Added false (and true) alarms summed per horizon over normal years and over Niño years (2017, 2026 and
    posterior_2026)."""
    normal = [pr.block_name(s) for s in pr.COMBINED_ALERT_NORMAL]
    nino = [pr.block_name(s) for s in pr.COMBINED_ALERT_NINO] + ["posterior_2026"]
    rows = []
    for regime, blocks in (("normales", normal), ("nino", nino)):
        g = added[added.bloque.isin(blocks)].groupby("horizonte")[["fp_anadidas", "vp_anadidos", "fp_050_sola"]].sum()
        rows.append(g.reset_index().assign(regimen=regime, bloques=", ".join(blocks)))
    return pd.concat(rows, ignore_index=True)
