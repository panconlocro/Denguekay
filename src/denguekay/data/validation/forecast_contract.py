"""Time contract of a target row for weekly forecasts."""

import pandas as pd

KEY = ["ubigeo", "anio", "semana"]
# Horizons allowed to build matrices in memory. Persisted gold
# stays limited to features.HORIZONTES (2 and 4) until the team decides.
EXPERIMENTAL_HORIZONS = (1, 2, 3, 4, 5, 6)


def audit_origin(panel: pd.DataFrame, horizon: int = 4) -> pd.DataFrame:
    """Assign each target week the last admissible weekly close.

    Requires a continuous weekly panel per district. The first ``horizon``
    rows of each district have no origin inside the panel and stay NaT.
    It does not modify ``panel`` nor build predictors.
    """
    if horizon < 1:
        raise ValueError("El horizonte debe ser al menos una semana")
    missing = set(KEY + ["semana_inicio"]) - set(panel.columns)
    if missing:
        raise ValueError(f"Faltan columnas del contrato temporal: {sorted(missing)}")
    if panel.empty or panel[KEY + ["semana_inicio"]].isna().any().any():
        raise ValueError("El panel está vacío o tiene llaves/fechas faltantes")
    if panel.duplicated(KEY).any():
        raise ValueError("Hay llaves distrito-año-semana duplicadas")

    audit = panel[KEY + ["semana_inicio"]].copy()
    audit["semana_inicio"] = pd.to_datetime(audit["semana_inicio"], errors="raise")
    if (audit["semana_inicio"].dt.weekday != 6).any():
        raise ValueError("semana_inicio debe ser domingo")
    audit = audit.sort_values(["ubigeo", "semana_inicio"]).reset_index(drop=True)
    gap = audit.groupby("ubigeo")["semana_inicio"].diff().dt.days.dropna()
    if not gap.eq(7).all():
        raise ValueError("El panel contiene huecos o fechas repetidas por distrito")

    audit["origen_inicio"] = audit.groupby("ubigeo")["semana_inicio"].shift(horizon)
    distance = (audit["semana_inicio"] - audit["origen_inicio"]).dt.days.dropna()
    if not distance.eq(7 * horizon).all():
        raise ValueError("El origen no está a la distancia temporal esperada")
    audit["origen_cierre"] = audit["origen_inicio"] + pd.Timedelta(days=6)
    return audit


def available_observations(
    audit: pd.DataFrame,
    observed_week: pd.Series,
    available_date: pd.Series,
) -> pd.Series:
    """Tell whether each observation existed at the close of its row's origin.

    ``observed_week`` is the starting Sunday of the data point and
    ``available_date`` is its actual publication. A missing origin
    returns False.
    """
    required = {"origen_inicio", "origen_cierre"}
    if not required.issubset(audit):
        raise ValueError("La auditoría carece de fechas de origen")
    if len(audit) != len(observed_week) or len(audit) != len(available_date):
        raise ValueError("Las fechas de observación no se alinean con las filas")
    week = pd.to_datetime(pd.Series(observed_week).reset_index(drop=True))
    available = pd.to_datetime(pd.Series(available_date).reset_index(drop=True))
    origin = audit.reset_index(drop=True)
    return (origin["origen_inicio"].notna()
            & week.notna() & available.notna()
            & week.le(origin["origen_inicio"])
            & available.le(origin["origen_cierre"]))
