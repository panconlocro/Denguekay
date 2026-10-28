"""
Epidemiological seasons of the district-week panel.

The rest of the EDA's temporal analysis (autocorrelation, seasonal profile,
naive baselines) is frozen in research/01_eda/code/temporal.py.
"""

import pandas as pd


def assign_season(year: pd.Series, week: pd.Series, week_start: int) -> pd.Series:
    """
    Epidemiological season: from week `week_start` of year Y-1 to
    week `week_start` - 1 of year Y; it is labelled Y.
    """
    return year + (week >= week_start).astype(int)
