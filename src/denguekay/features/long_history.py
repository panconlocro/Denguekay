"""Long history of the V3: cases from 2000, labels, matrices h=2..4 and origins with B3 and d3, in memory.

The V3 (``frozen_configs.CONFIG_V3``) trains with origins from 2005, so its inputs are not gold (2017 onwards) but
this long series, built exactly as study 06 built it (``research/06_model_improvement``, tag ``model/v3``):

- cases: the historical epidemiological silver for 2000-2016 (district-weeks absent there are 0 cases, Rosa
  2026-11-02), the integrated panel from 2017 and, after the panel, the Sala Situacional silver weeks that the
  panel lacks (the last ``SALA_PROVISIONAL_WEEKS`` published weeks are provisional and stay out);
- labels: ``outbreak_label.future_outbreak_threshold`` with 1.5 SD, 5 previous years and at least 2 cases;
- matrices per horizon with ``history_calendar`` (``base_6``), origins with B3 on the whole series and the d3
  ERA5-Land temperature windows at the origin (``features.climate``).

Nothing is written to ``data/``.
"""

from __future__ import annotations

import pandas as pd

from denguekay.config.paths import SILVER_EPI_HISTORICAL, SILVER_SALA, UBIGEO_CATALOG
from denguekay.data.calendar import mmwr_epi_week
from denguekay.data.seasons import assign_season
from denguekay.data.validation.forecast_contract import KEY
from denguekay.features import climate as cl
from denguekay.features import onset_features as fi
from denguekay.features.history_calendar import build_history_calendar
from denguekay.features.outbreak_label import future_outbreak_threshold
from denguekay.model import horizon_strategies as eh
from denguekay.model.train import SEASON_START_WEEK

HISTORY_START = 2000
OUTBREAK_RULE = {"multiplicador": 1.5, "anios_previos": 5, "minimo_casos": 2}
SALA_PROVISIONAL_WEEKS = 2
SERIES_COLUMNS = ["ubigeo", "anio", "semana", "semana_inicio", "casos_Dengue"]


def piura_ubigeos(catalog_path=UBIGEO_CATALOG) -> list[str]:
    catalog = pd.read_csv(catalog_path, dtype={"ubigeo": "string"})
    return sorted(catalog.ubigeo.astype(str).str.zfill(6))


def week_grid(first_year: int, last_year: int) -> pd.DataFrame:
    """Every MMWR week (Sunday start) of the epidemiological years ``first_year..last_year``."""
    sundays = pd.Series(pd.date_range(f"{first_year - 1}-12-25", f"{last_year + 1}-01-07", freq="W-SUN"))
    weeks = mmwr_epi_week(sundays)
    grid = pd.DataFrame({"semana_inicio": sundays, "anio": weeks.anio_epi, "semana": weeks.semana_epi})
    return grid[grid.anio.between(first_year, last_year)].reset_index(drop=True)


def sala_after_panel(panel: pd.DataFrame, sala: pd.DataFrame,
                     provisional: int = SALA_PROVISIONAL_WEEKS) -> tuple[pd.DataFrame, list[tuple[int, int]]]:
    """Sala weeks after the start of the panel's last year that the panel lacks, without the last ``provisional``
    published weeks (returned apart), with ``semana_inicio`` from the MMWR grid."""
    last_year = int(panel.anio.max())
    s = sala[sala.anio.ge(last_year)].copy()
    s["ubigeo"] = s.ubigeo.astype(str).str.zfill(6)
    have = set(zip(panel.ubigeo.astype(str), panel.anio, panel.semana))
    s = s[[k not in have for k in zip(s.ubigeo, s.anio, s.semana)]]
    if s.empty:
        return s.reindex(columns=SERIES_COLUMNS), []
    published = s[["anio", "semana"]].drop_duplicates().sort_values(["anio", "semana"])
    dropped = [tuple(map(int, r)) for r in published.tail(provisional).itertuples(index=False)] if provisional else []
    s = s[[k not in set(dropped) for k in zip(s.anio, s.semana)]]
    s = s.merge(week_grid(int(s.anio.min()), int(s.anio.max())), on=["anio", "semana"], how="left",
                validate="many_to_one")
    if s.semana_inicio.isna().any():
        raise ValueError("Semanas de la Sala fuera de la grilla MMWR")
    return s[SERIES_COLUMNS].reset_index(drop=True), dropped


def long_case_series(recent: pd.DataFrame, history_path=SILVER_EPI_HISTORICAL, start: int = HISTORY_START,
                     catalog_path=UBIGEO_CATALOG) -> pd.DataFrame:
    """Cases per district-week from ``start``: the historical silver before 2017 (absences as 0) and ``recent``
    (the panel from 2017 plus the Sala weeks after it)."""
    ubigeos = piura_ubigeos(catalog_path)
    first_panel = int(recent.anio.min())
    hist = pd.read_csv(history_path, dtype={"ubigeo": "string"})
    hist["ubigeo"] = hist.ubigeo.astype(str).str.zfill(6)
    hist = hist[hist.ubigeo.isin(ubigeos)]
    grid = week_grid(start, first_panel - 1)
    full = pd.MultiIndex.from_product([ubigeos, range(len(grid))], names=["ubigeo", "i"]).to_frame(index=False)
    full = full.join(grid, on="i").drop(columns="i")
    early = hist[hist.anio.between(start, first_panel - 1)]
    merged = full.merge(early, on=["ubigeo", "anio", "semana"], how="left", validate="one_to_one")
    merged["casos_Dengue"] = merged.casos_Dengue.fillna(0).astype(int)
    recent = recent[SERIES_COLUMNS].copy()
    recent["semana_inicio"] = pd.to_datetime(recent.semana_inicio)
    series = pd.concat([merged[SERIES_COLUMNS], recent], ignore_index=True)
    return series.sort_values(["ubigeo", "semana_inicio"]).reset_index(drop=True)


def long_labels(cases: pd.DataFrame, start: int = HISTORY_START, rule: dict | None = None) -> pd.DataFrame:
    """``brote`` from ``start + anios_previos`` onwards: cases > threshold and cases >= the minimum."""
    rule = OUTBREAK_RULE if rule is None else rule
    targets = cases[cases.anio.ge(start + rule["anios_previos"])].reset_index(drop=True)
    threshold = future_outbreak_threshold(cases, None, targets, multiplicador=rule["multiplicador"],
                                          anios_previos=rule["anios_previos"])
    out = targets.assign(umbral_brote_casos=threshold.to_numpy())
    out["brote"] = ((out.casos_Dengue > out.umbral_brote_casos)
                    & (out.casos_Dengue >= rule["minimo_casos"])).astype("int8")
    return out


def long_matrix(cases: pd.DataFrame, labels: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Matrix of one horizon: rows with a label and a full ``base_6`` (``eh.horizon_matrix`` conventions)."""
    hist = build_history_calendar(cases, horizon)
    data = hist.merge(cases[KEY + ["casos_Dengue"]], on=KEY, validate="one_to_one")
    data = data.merge(labels[KEY + ["umbral_brote_casos", "brote"]], on=KEY, how="inner", validate="one_to_one")
    data = data.dropna(subset=eh.model_columns(horizon)[0]).copy()
    data["semana_inicio"] = pd.to_datetime(data.semana_inicio)
    if not data.origen_cierre.lt(data.semana_inicio).all():
        raise ValueError(f"Fuga temporal en la matriz larga h={horizon}")
    series = cases[KEY + ["semana_inicio", "casos_Dengue"]].copy()
    series["semana_inicio"] = pd.to_datetime(series.semana_inicio)
    series = series.sort_values(["ubigeo", "semana_inicio"])
    series["estacional"] = series.groupby("ubigeo").casos_Dengue.shift(eh.SEASONAL_LAG)
    data = data.merge(series[KEY + ["estacional"]], on=KEY, how="left", validate="one_to_one")
    data["persistencia"] = data[f"casos_lag_{horizon}"]
    data["horizonte"] = horizon
    data["temporada"] = assign_season(data.anio, data.semana, SEASON_START_WEEK)
    return data.sort_values(["semana_inicio", "ubigeo"]).reset_index(drop=True)


def long_inputs(panel: pd.DataFrame, era5_land_path, sala: pd.DataFrame | None = None,
                history_path=SILVER_EPI_HISTORICAL) -> dict:
    """Series, labels, matrices h=2..4 and origins (``base_6`` + B3 + d3, RangeIndex) of the V3."""
    sala = pd.read_csv(SILVER_SALA, dtype={"ubigeo": "string"}) if sala is None else sala
    recent = panel[SERIES_COLUMNS].assign(ubigeo=lambda d: d.ubigeo.astype(str),
                                          semana_inicio=lambda d: pd.to_datetime(d.semana_inicio))
    after, provisional = sala_after_panel(panel, sala)
    cases = long_case_series(pd.concat([recent, after], ignore_index=True), history_path)
    labels = long_labels(cases)
    matrices = {h: long_matrix(cases, labels, h) for h in eh.STRATEGY_HORIZONS}
    origins = fi.with_onset_columns(eh.origin_table(matrices[2]), cases, cases.iloc[:0][
        ["ubigeo", "anio", "semana", "casos_Dengue"]])
    windows = cl.weather_windows(cl.era5_land_weekly(era5_land_path, panel))
    origins = cl.add_weather_windows(origins, windows).reset_index(drop=True)
    series = labels[["ubigeo", "anio", "semana", "semana_inicio", "casos_Dengue", "brote"]].copy()
    series["semana_inicio"] = pd.to_datetime(series.semana_inicio)
    return {"casos": cases, "etiquetas": labels, "matrices": matrices, "origenes": origins, "serie": series,
            "semanas_provisionales": provisional, "ultima_semana": cases.semana_inicio.max()}
