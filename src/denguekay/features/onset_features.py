"""New block B variables (phase 2b of the FE study on E3·S4_s2), in memory.

Each variable of an origin ``o`` is taken from the district's status in the
origin week (the one that closes at ``origen_cierre``), computed with weeks <=
``o`` (``diagnostico_inicios.estado_semanal``). Nothing is written to ``data/``.

- **B1** spatial dynamics and **B3** extended own history: they depend on no
  fit; they are computed once.
- **B2** core districts and **B5** climate anomalies: the core ranking and the
  climatology are fitted with the weeks closed at each block's ``cutoff``
  (``prepare_block``).
- **B3**, cases of the previous season: for season 2017 the 2016 season of the
  outbreak-rule history is used (no record = zero); if a needed year is missing
  from the history, it stays null.
- **B4** seasonal baseline: ``log(1 + threshold)`` of each target week t+2, t+3
  and t+4 with ``outbreak_label.future_outbreak_threshold`` (previous years only;
  it also works outside the panel).
"""

import numpy as np
import pandas as pd

from denguekay.evaluation import onsets as di
from denguekay.model import horizon_strategies as eh
from denguekay.features import variant_registry as pr
from denguekay.features.outbreak_label import future_outbreak_threshold
from denguekay.data.calendar import mmwr_epi_week

COLUMNS = {v["id"]: list(v["columnas"]) for v in pr.VARIANTS if v["bloque"] == "B"}
PER_BLOCK = ("B2", "B5")
B5_WINDOWS = {"o4_o": (0, 4), "o9_o5": (5, 9)}  # weeks before o, both ends included
B5_CLIMATE = ("temp_media", "temp_min", "hum_rel_media", "precip_total_mm")
PREVIOUS_SEASON_COLUMN = "propia_log_casos_temporada_anterior"


def origin_week(origins: pd.DataFrame) -> pd.Series:
    """Start (Sunday) of the week that closes at ``origen_cierre``."""
    return pd.to_datetime(origins.origen_cierre) - pd.Timedelta(days=6)


def previous_season(series: pd.DataFrame, history: pd.DataFrame) -> pd.DataFrame:
    """``log(1 + cases)`` of the whole previous season, per district and season.

    It uses the history before the panel (absences as zero) only if the years
    that cover that season are in the history; otherwise null.
    """
    s = series[["ubigeo", "anio", "semana", "casos_Dengue"]].copy()
    first = int(s.anio.min())
    h = history.loc[history.anio.lt(first) & history.ubigeo.isin(set(s.ubigeo)),
                     ["ubigeo", "anio", "semana", "casos_Dengue"]]
    everything = pd.concat([h, s], ignore_index=True)
    everything["temporada"] = di.con_temporada(everything)
    totals = everything.groupby(["ubigeo", "temporada"]).casos_Dengue.sum()
    available = set(h.anio) | set(s.anio)
    seasons = sorted(set(di.con_temporada(s)))
    rows = []
    for u in sorted(s.ubigeo.unique()):
        for t in seasons:
            previous = t - 1
            # The previous season covers weeks >= 35 of previous-1 and weeks < 35 of previous.
            value = np.log1p(totals.get((u, previous), 0.0)) if {previous - 1, previous} <= available else np.nan
            rows.append({"ubigeo": u, "temporada": t, PREVIOUS_SEASON_COLUMN: value})
    return pd.DataFrame(rows)


def weekly_table(panel: pd.DataFrame, series: pd.DataFrame, history: pd.DataFrame,
                  cutoff: pd.Timestamp) -> pd.DataFrame:
    """B1, B2, B3 and B5 per district and week ``w``, with data of weeks <= ``w``.

    The core (B2) and the climatology (B5) are fitted with weeks closed at the
    ``cutoff``; B1 and B3 do not depend on the cutoff.
    """
    status = di.estado_semanal(panel, series, cutoff)
    status = status.sort_values(["ubigeo", "semana_inicio"]).reset_index(drop=True)
    group = status.groupby("ubigeo")
    for c in B5_CLIMATE:
        anomaly = f"{c}_anomalia"
        for name, (k0, k1) in B5_WINDOWS.items():
            status[f"{anomaly}_{name}"] = (group[anomaly].shift(k0)
                                             .groupby(status.ubigeo).rolling(k1 - k0 + 1).mean()
                                             .reset_index(level=0, drop=True))
    weeks = series[["ubigeo", "semana_inicio", "anio", "semana"]].copy()
    weeks["semana_inicio"] = pd.to_datetime(weeks.semana_inicio)
    weeks["temporada"] = di.con_temporada(weeks)
    status = status.drop(columns=[PREVIOUS_SEASON_COLUMN]).merge(
        weeks[["ubigeo", "semana_inicio", "temporada"]], on=["ubigeo", "semana_inicio"], how="left",
        validate="one_to_one")
    status = status.merge(previous_season(series, history), on=["ubigeo", "temporada"], how="left",
                          validate="many_to_one")
    columns = [c for f in ("B1", "B2", "B3", "B5") for c in COLUMNS[f]]
    return status[["ubigeo", "semana_inicio", *columns]]


def baseline(origins: pd.DataFrame, panel: pd.DataFrame, history: pd.DataFrame, rule: dict) -> pd.DataFrame:
    """B4: ``log(1 + threshold)`` of the target weeks o+h for h=2, 3 and 4 (one column per h)."""
    base = origin_week(origins)
    output = pd.DataFrame(index=origins.index)
    for h in eh.STRATEGY_HORIZONS:
        destination = base + pd.Timedelta(weeks=h)
        cal = mmwr_epi_week(pd.Series(destination.to_numpy()))
        targets = pd.DataFrame({"ubigeo": origins.ubigeo.to_numpy(), "anio": cal.anio_epi.to_numpy(),
                                  "semana": cal.semana_epi.to_numpy()}, index=origins.index)
        threshold = future_outbreak_threshold(panel, history, targets, multiplicador=rule["multiplicador"],
                                     anios_previos=rule["anios_previos"])
        output[f"linea_base_log_umbral_h{h}"] = np.log1p(threshold.to_numpy())
    return output


def add(origins: pd.DataFrame, weekly: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Join columns of the weekly table to the origins by district and origin week (same index)."""
    key = pd.DataFrame({"ubigeo": origins.ubigeo.astype("string").to_numpy(),
                          "semana_inicio": origin_week(origins).to_numpy()}, index=origins.index)
    joined = key.merge(weekly[["ubigeo", "semana_inicio", *columns]], on=["ubigeo", "semana_inicio"],
                        how="left", validate="many_to_one")
    joined.index = origins.index
    return origins.drop(columns=[c for c in columns if c in origins]).join(joined[columns])


class OnsetFeatures:
    """Compute and keep in memory the weekly tables per cutoff."""

    def __init__(self, panel: pd.DataFrame, series: pd.DataFrame, history: pd.DataFrame, rule: dict):
        # Same as build_labels: the history only contributes years before the panel.
        history = history.loc[history.anio.lt(int(panel.anio.min()))]
        self.panel, self.series, self.history, self.rule = panel, series, history, rule
        self._by_cutoff: dict[pd.Timestamp, pd.DataFrame] = {}

    def weekly(self, cutoff: pd.Timestamp) -> pd.DataFrame:
        cutoff = pd.Timestamp(cutoff)
        if cutoff not in self._by_cutoff:
            self._by_cutoff[cutoff] = weekly_table(self.panel, self.series, self.history, cutoff)
        return self._by_cutoff[cutoff]

    def origins(self, base: pd.DataFrame, families: list[str], reference_cutoff: pd.Timestamp) -> pd.DataFrame:
        """Origins with the columns of the requested families.

        B2 and B5 are computed here with ``reference_cutoff`` only to locate the
        start-up nulls; in the experiment, ``prepare_block`` replaces them with
        those of each block's cutoff.
        """
        output = base
        weekly = [c for f in families if f != "B4" for c in COLUMNS[f]]
        if weekly:
            output = add(output, self.weekly(reference_cutoff), weekly)
        if "B4" in families:
            output = output.join(baseline(output, self.panel, self.history, self.rule))
        return output

    def prepare_block(self, families: list[str]):
        """``prepare_block`` for ``predict_e3``: recompute B2/B5 with the block's cutoff."""
        columns = [c for f in families if f in PER_BLOCK for c in COLUMNS[f]]
        if not columns:
            return None

        def prepare(origins: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame:
            return add(origins, self.weekly(cutoff), columns)
        return prepare
