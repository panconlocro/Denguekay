"""Phase 4: the regional Niño 1+2 signal over L + 5a (``preregistration.PHASE4``).

The monthly anomaly of NOAA CPC (silver ``enso_nino12_mensual.csv``) enters only from its
``fecha_disponible`` (day 10 of the next month): a month is usable at an origin when that date is on or
before ``origen_cierre``. The value is the same for every district.

- 4a: anomaly of the last month available at the origin;
- 4b: mean of the last 3 months available at the origin.
"""

import numpy as np
import pandas as pd

from denguekay.config.paths import MODELS, SILVER_ENSO
from denguekay.evaluation import protocol as pa

OUTPUT_DIR = MODELS / "experimentos" / "mejora_modelo" / "fase4"
COLUMNS = ("nino12_anom_ultimo", "nino12_anom_media3")


def read_enso() -> pd.DataFrame:
    enso = pd.read_csv(SILVER_ENSO, parse_dates=["fecha_disponible"])
    return enso.sort_values(["anio", "mes"]).reset_index(drop=True)


def monthly_features(enso: pd.DataFrame) -> pd.DataFrame:
    """Per month: its anomaly and the mean of it and the 2 previous months (all usable when it is)."""
    out = enso.sort_values(["anio", "mes"]).reset_index(drop=True)
    months = pd.PeriodIndex.from_fields(year=out.anio, month=out.mes, freq="M")
    if len(months) > 1 and not (months[1:] - months[:-1] == months.freq).all():
        raise ValueError("Meses faltantes o desordenados en el índice del Niño")
    if not out.fecha_disponible.is_monotonic_increasing:
        raise ValueError("fecha_disponible no crece con los meses")
    out["nino12_anom_ultimo"] = out.nino12_anom
    out["nino12_anom_media3"] = out.nino12_anom.rolling(3).mean()
    out["mes_usado"] = months.astype(str)
    return out[["fecha_disponible", "mes_usado", *COLUMNS]]


def enso_at_origins(origins: pd.DataFrame, enso: pd.DataFrame) -> pd.DataFrame:
    """``origins`` with the two Niño columns and the month used, by the last month available at origen_cierre."""
    features = monthly_features(enso)
    o = origins[["origen_cierre"]].assign(_pos=np.arange(len(origins)),
                                          origen_cierre=pd.to_datetime(origins.origen_cierre))
    joined = pd.merge_asof(o.sort_values("origen_cierre"), features, left_on="origen_cierre",
                           right_on="fecha_disponible", direction="backward").sort_values("_pos")
    out = origins.copy()
    for c in (*COLUMNS, "mes_usado", "fecha_disponible"):
        out[c if c != "fecha_disponible" else "nino_fecha_disponible"] = joined[c].to_numpy()
    return out


def guard_g21(origins: pd.DataFrame) -> dict:
    """G21: no origin uses a month published after its origen_cierre."""
    late = pd.to_datetime(origins.nino_fecha_disponible) > pd.to_datetime(origins.origen_cierre)
    return {"origenes": len(origins), "con_mes_posterior": int(late.sum()), "pasa": not late.any()}


def guard_g23(origins: pd.DataFrame, since: str = "2005-01-01") -> dict:
    """G23: every origin since 2005 has both Niño columns."""
    sel = pd.to_datetime(origins.origen_cierre) >= pd.Timestamp(since)
    missing = int(origins.loc[sel, list(COLUMNS)].isna().any(axis=1).sum())
    return {"origenes_desde_2005": int(sel.sum()), "sin_valor": missing, "pasa": missing == 0}


def run_variant(inp: dict, origins: pd.DataFrame, variant: str, seeds) -> dict:
    """4a or 4b: predictions (5 seeds) with C3 + the variant's column, evaluated with the 5a mixture."""
    import phase1_history as p1
    import preregistration as pr
    from phase3_onsets import _config, predict_blocks_weighted
    from phase5_counts import evaluate_mixture

    columns, hp = _config()
    columns = [*columns, *pr.PHASE4_COLUMNS[variant]]
    blocks = p1.seasonal_blocks(p1.FIRST_BLOCK_SEASON_LONG)
    preds, evals, raw, fits = {}, {}, {}, []
    for seed in seeds:
        pred = predict_blocks_weighted(inp["matrices"], origins, blocks, seed, columns, hp)
        fits.append(pred.attrs.pop("ajustes").assign(semilla=seed))
        preds[seed] = pred
        evals[seed] = evaluate_mixture(pred, inp["serie"])
        raw[seed] = pa.evaluate(pred, inp["serie"])
    return {"predicciones": preds, "evaluaciones": evals, "evaluaciones_mu": raw,
            "ajustes": pd.concat(fits, ignore_index=True)}
