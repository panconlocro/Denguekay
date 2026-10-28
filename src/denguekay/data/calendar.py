"""Epidemiological calendar shared by the pipeline, the EDA and the modelling."""

import pandas as pd


def mmwr_epi_week(week_start: pd.Series) -> pd.DataFrame:
    """Return the MMWR year and week for Sundays, keeping the index.

    Weeks run from Sunday to Saturday. Week 1 is the first one with at
    least four days in the new year: it contains the year's first Wednesday.
    It does not use the ISO numbering, whose weeks start on Monday.
    """
    dates = pd.to_datetime(week_start)
    if (dates.dt.weekday != 6).any():
        raise ValueError("semana_inicio debe ser domingo en todas las filas")
    year = (dates + pd.Timedelta(days=3)).dt.year
    january_1 = pd.to_datetime(year.astype(str) + "-01-01")
    sunday_0 = january_1 - pd.to_timedelta((january_1.dt.weekday + 1) % 7, unit="D")
    week1_start = sunday_0.where(sunday_0 + pd.Timedelta(days=3) >= january_1,
                                sunday_0 + pd.Timedelta(days=7))
    week = (dates - week1_start).dt.days // 7 + 1
    return pd.DataFrame({"anio_epi": year.astype(int), "semana_epi": week.astype(int)},
                        index=week_start.index)
