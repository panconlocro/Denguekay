"""District history and calendar known when a weekly forecast is issued."""

import numpy as np
import pandas as pd

from denguekay.data.validation.forecast_contract import KEY, EXPERIMENTAL_HORIZONS, audit_origin


def build_history_calendar(
    panel: pd.DataFrame, horizon: int, window: int = 4,
    *, allow_missing: bool = False,
) -> pd.DataFrame:
    """Build causal candidates per district and target week.

    For target ``t``, the case observations reach at most ``t-horizon``. The
    mean and the count of positive weeks cover ``t-horizon-window+1`` to
    ``t-horizon``. The first rows with insufficient history keep NaN. The
    calendar of the target week is known before the forecast. Missing values
    are not imputed and no dataset is written; the actual publication
    availability is audited separately.
    ``allow_missing`` allows future targets without observed cases: it keeps NaN
    in the incomplete windows, without imputing zeros. The default keeps the
    strict contract of gold and of training.
    """
    if horizon not in EXPERIMENTAL_HORIZONS:
        raise ValueError("El horizonte debe estar entre 1 y 6 semanas")
    if window < 2:
        raise ValueError("La ventana debe cubrir al menos dos semanas")
    if "casos_Dengue" not in panel:
        raise ValueError("Falta casos_Dengue")

    audit = audit_origin(panel, horizon)
    source = audit.merge(
        panel[KEY + ["casos_Dengue"]], on=KEY, how="left",
        validate="one_to_one", sort=False,
    )
    if len(source) != len(panel):
        raise ValueError("El cruce con casos cambió el número de filas")
    cases = pd.to_numeric(source["casos_Dengue"], errors="raise")
    present = cases.dropna()
    if ((not allow_missing and cases.isna().any())
            or not np.isfinite(present.to_numpy(dtype=float)).all() or (present < 0).any()):
        raise ValueError("casos_Dengue debe ser numérico, finito y no negativo")
    week = pd.to_numeric(source["semana"], errors="raise")
    if week.isna().any() or not week.between(1, 53).all() or not (week % 1 == 0).all():
        raise ValueError("semana debe ser un entero entre 1 y 53")

    output = source[KEY + ["semana_inicio", "origen_inicio", "origen_cierre"]].copy()
    group = cases.groupby(source["ubigeo"], sort=False)
    first = group.shift(horizon)
    output[f"casos_lag_{horizon}"] = first
    output[f"casos_lag_{horizon + 1}"] = group.shift(horizon + 1)
    output[f"casos_media_{window}_h{horizon}"] = first.groupby(
        source["ubigeo"], sort=False
    ).transform(lambda s: s.rolling(window, min_periods=window).mean())
    output[f"casos_semanas_positivas_{window}_h{horizon}"] = (
        first.gt(0).where(first.notna()).astype(float)
        .groupby(source["ubigeo"], sort=False)
        .transform(lambda s: s.rolling(window, min_periods=window).sum())
    )

    # Week 53 takes the same circular position as week 1.
    angle = 2 * np.pi * ((week.to_numpy(dtype=float) - 1) % 52) / 52
    output["semana_epi_seno"] = np.sin(angle)
    output["semana_epi_coseno"] = np.cos(angle)
    return output
