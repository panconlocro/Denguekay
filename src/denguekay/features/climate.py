"""Causal climate variables for a district target week.

The climatology is fitted per time cutoff. The EDA's descriptive anomaly uses
every year and must not be used directly for forecasting.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from denguekay.data.validation.forecast_contract import KEY, EXPERIMENTAL_HORIZONS, audit_origin


MAIN_CLIMATE = ("hum_rel_media", "precip_total_mm")
CANDIDATE_CLIMATE = ("temp_min",)


@dataclass(frozen=True)
class Climatology:
    """Means per district and week estimated with the climate available at the cutoff."""

    table: pd.DataFrame
    cutoff_date: pd.Timestamp
    variables: tuple[str, ...]


def _validate_climate(panel: pd.DataFrame, variables: tuple[str, ...]) -> pd.DataFrame:
    missing = set(variables) - set(panel)
    if missing:
        raise ValueError(f"Faltan variables climáticas: {sorted(missing)}")
    audit = audit_origin(panel, 1)
    data = audit.merge(panel[KEY + list(variables)], on=KEY,
                        how="left", validate="one_to_one", sort=False)
    if len(data) != len(panel):
        raise ValueError("El cruce climático cambió el número de filas")
    for variable in variables:
        values = pd.to_numeric(data[variable], errors="raise")
        if values.isna().any() or not np.isfinite(values.to_numpy(float)).all():
            raise ValueError(f"{variable} debe ser numérica, finita y completa")
        data[variable] = values
    week = pd.to_numeric(data["semana"], errors="raise")
    if week.isna().any() or not week.between(1, 53).all() or not (week % 1 == 0).all():
        raise ValueError("semana debe ser un entero entre 1 y 53")
    data["semana_clima"] = week.clip(upper=52).astype(int)
    return data


def fit_climatology(
    panel: pd.DataFrame,
    cutoff_date: str | pd.Timestamp,
    variables: tuple[str, ...] = MAIN_CLIMATE,
) -> Climatology:
    """Fit district x week means only with weeks closed at the cutoff.

    ``cutoff_date`` must be the close date of the validation's first origin,
    not the last date of the panel. Week 53 shares its climatological cell with
    week 52, following the EDA's descriptive convention.
    """
    if not variables or len(set(variables)) != len(variables):
        raise ValueError("Indique variables climáticas distintas")
    cutoff = pd.Timestamp(cutoff_date)
    if pd.isna(cutoff):
        raise ValueError("fecha_corte inválida")
    data = _validate_climate(panel, variables)
    training = data.loc[data["semana_inicio"] + pd.Timedelta(days=6) <= cutoff]
    if training.empty:
        raise ValueError("No hay semanas climáticas cerradas antes del corte")
    table = training.groupby(["ubigeo", "semana_clima"], as_index=False)[list(variables)].mean()
    # Avoid applying the climatology of another district or of weeks without history.
    expected = data[["ubigeo", "semana_clima"]].drop_duplicates()
    coverage = expected.merge(table[["ubigeo", "semana_clima"]], on=["ubigeo", "semana_clima"],
                                how="left", indicator=True, validate="one_to_one")
    if coverage["_merge"].ne("both").any():
        example = coverage.loc[coverage["_merge"].ne("both"), ["ubigeo", "semana_clima"]].head().to_dict("records")
        raise ValueError(f"Climatología sin historia para distrito-semana: {example}")
    return Climatology(table, cutoff, variables)


def build_climate(
    panel: pd.DataFrame, horizon: int, climatology: Climatology,
    window: int = 5,
) -> pd.DataFrame:
    """Build raw means and anomalies from ``t-h-window+1`` to ``t-h``.

    With h=4 and window=5, the window uses t-8,...,t-4. The first h+4 rows of
    each district stay without history. No outputs are built for the duplicated
    precipitation ``lluvia_total_mm``.
    """
    if horizon not in EXPERIMENTAL_HORIZONS or window < 2:
        raise ValueError("Use horizonte de 1 a 6 y ventana de al menos 2 semanas")
    data = _validate_climate(panel, climatology.variables)
    table = climatology.table
    expected = {"ubigeo", "semana_clima", *climatology.variables}
    if not expected.issubset(table) or table.duplicated(["ubigeo", "semana_clima"]).any():
        raise ValueError("La climatología tiene columnas faltantes o llaves duplicadas")
    data = data.merge(table, on=["ubigeo", "semana_clima"], how="left",
                        suffixes=("", "_climatologia"), validate="many_to_one", sort=False)
    if len(data) != len(panel):
        raise ValueError("La climatología cambió el número de filas")
    output = data[KEY + ["semana_inicio"]].copy()
    for variable in climatology.variables:
        base = data[f"{variable}_climatologia"]
        if base.isna().any() or not np.isfinite(base.to_numpy(float)).all():
            raise ValueError(f"Climatología incompleta para {variable}")
        for kind, values in (("media", data[variable]), ("anomalia_media", data[variable] - base)):
            rolling = values.groupby(data["ubigeo"], sort=False).transform(
                lambda s: s.rolling(window, min_periods=window).mean()
            )
            output[f"{variable}_{kind}{window}_h{horizon}"] = (
                rolling.groupby(data["ubigeo"], sort=False).shift(horizon)
            )
    return output


def build_observed_climate(
    panel: pd.DataFrame, horizon: int, window: int = 5,
    variables: tuple[str, ...] = MAIN_CLIMATE,
) -> pd.DataFrame:
    """Build causal climate means without fitting a global climatology.

    It serves to publish candidates in gold before the folds are defined. The
    anomalies are still built with ``fit_climatology`` and ``build_climate``
    inside each training cutoff.
    """
    if horizon not in EXPERIMENTAL_HORIZONS or window < 2 or not variables or len(set(variables)) != len(variables):
        raise ValueError("Use horizonte de 1 a 6, ventana >= 2 y variables distintas")
    data = _validate_climate(panel, variables)
    output = data[KEY + ["semana_inicio"]].copy()
    for variable in variables:
        rolling = data[variable].groupby(data["ubigeo"], sort=False).transform(
            lambda s: s.rolling(window, min_periods=window).mean()
        )
        output[f"{variable}_media{window}_h{horizon}"] = (
            rolling.groupby(data["ubigeo"], sort=False).shift(horizon)
        )
    return output
