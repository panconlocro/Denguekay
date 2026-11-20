"""The completeness criterion of the V4 panel (HU0005-5, US v1.4), defined once.

- Columns: ubigeo, year, week, week start, cases, mean, minimum and maximum temperature, precipitation, humidity and
  population (the three temperatures are in the criterion, not only the mean).
- Calendar: 65 districts x the MMWR weeks of the contractual period of the panel, from epidemiological week 1 of 2017
  to week 52 of 2025. The period is fixed by contract and is never deduced from the data: a panel that lacks its first
  or last week has fewer rows than expected, not a shorter period. Week 53 of 2025 is not in the panel.
- A case count assigned as 0 by the merge counts as a present value (HU0005-5); whether the source has a record for that
  week is reported apart (``case_source``).
"""

import pandas as pd

from denguekay.data.calendar import mmwr_epi_week

MANDATORY = {"ubigeo": "ubigeo", "año": "anio", "semana": "semana", "inicio de semana": "semana_inicio",
             "casos": "casos_Dengue", "temperatura media": "temp_media", "temperatura mínima": "temp_min",
             "temperatura máxima": "temp_max", "precipitación": "precip_total_mm", "humedad": "hum_rel_media",
             "población": "poblacion"}
COMPLETENESS_MIN = 0.95
PERIOD_FIRST = (2017, 1)    # (epidemiological year, MMWR week) of the first week of the panel
PERIOD_LAST = (2025, 52)    # and of the last one
EXPECTED_WEEKS = 469        # 9 years x 52 weeks + the week 53 of 2020
EXPECTED_DISTRICTS = 65


def contractual_week_starts() -> pd.DatetimeIndex:
    """The Sundays that start each MMWR week of the contractual period, from ``denguekay.data.calendar``."""
    sundays = pd.Series(pd.date_range("2016-12-25", "2026-01-31", freq="W-SUN"))
    weeks = mmwr_epi_week(sundays)
    key = list(zip(weeks.anio_epi, weeks.semana_epi))
    inside = [PERIOD_FIRST <= pair <= PERIOD_LAST for pair in key]
    starts = pd.DatetimeIndex(sundays[inside])
    if len(starts) != EXPECTED_WEEKS:
        raise ValueError(f"El calendario contractual debe tener {EXPECTED_WEEKS} semanas, tiene {len(starts)}")
    return starts
