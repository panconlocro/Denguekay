"""Cutoff of each source for a frozen model version.

A run from the sources captures what the sources publish today, which is later than what a version was frozen with.
The cutoff of a version trims each silver to the extent of its Release (``datos_v4.zip``), so the regenerated files
are comparable row by row with the frozen ones. ``None`` (no cutoff) keeps everything the sources have.
"""

from dataclasses import dataclass
from datetime import date

import pandas as pd


@dataclass(frozen=True)
class VersionCutoff:
    sala_last_week: tuple[int, int]        # (epidemiological year, week): last Sala week kept
    labels: date | None                    # last day of the labelled weeks (the gold cutoff); None if the version has none
    weekly_last_start: date                # last ``semana_inicio`` kept of the weekly climate (ERA5-Land, CHIRPS)
    enso_last_month: tuple[int, int]       # (year, month): last Niño 1+2 month kept
    provisional_weeks: int                 # Sala weeks treated as provisional (dropped by ``sala_after_panel``)


# Read from the files of datos_v4.zip: Sala 2025 complete and 2026 up to week 43, 2 provisional weeks, labels up to
# 2026-10-17, ERA5-Land and CHIRPS up to the week of 2026-10-25 and Niño 1+2 up to 2026-10.
V4_CUTOFF = VersionCutoff(sala_last_week=(2026, 43), labels=date(2026, 10, 17), weekly_last_start=date(2026, 10, 25),
                          enso_last_month=(2026, 10), provisional_weeks=2)


# v0 to v3 (notified cases): the Sala silver, ERA5-Land, CHIRPS and Niño 1+2 files of datos_v2.zip and datos_v3.zip have
# the same extent as those of V4 (6 240 Sala rows up to week 43 of 2026, 91 000 weekly climate rows, 538 months), and the
# v3 and V4 climate files are byte-identical. v0 and v1 do not ship those sources.
NOTIFIED_CUTOFF = VersionCutoff(sala_last_week=(2026, 43), labels=None, weekly_last_start=date(2026, 10, 25),
                                enso_last_month=(2026, 10), provisional_weeks=2)
CUTOFFS = {"v0": NOTIFIED_CUTOFF, "v1": NOTIFIED_CUTOFF, "v2": NOTIFIED_CUTOFF, "v3": NOTIFIED_CUTOFF, "v4": V4_CUTOFF}


def clip_sala(frame: pd.DataFrame, cutoff: VersionCutoff | None) -> pd.DataFrame:
    if cutoff is None:
        return frame
    year, week = cutoff.sala_last_week
    keep = frame.anio.lt(year) | (frame.anio.eq(year) & frame.semana.le(week))
    return frame.loc[keep].reset_index(drop=True)


def clip_weekly(frame: pd.DataFrame, cutoff: VersionCutoff | None) -> pd.DataFrame:
    if cutoff is None:
        return frame
    keep = pd.to_datetime(frame.semana_inicio).le(pd.Timestamp(cutoff.weekly_last_start))
    return frame.loc[keep].reset_index(drop=True)


def clip_enso(frame: pd.DataFrame, cutoff: VersionCutoff | None) -> pd.DataFrame:
    if cutoff is None:
        return frame
    year, month = cutoff.enso_last_month
    keep = frame.anio.lt(year) | (frame.anio.eq(year) & frame.mes.le(month))
    return frame.loc[keep].reset_index(drop=True)
