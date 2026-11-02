"""Diagnosis of outbreak onsets (phase 1 of the FE study on E3·S4_s2).

It describes what happens in the weeks before the **clean onsets** of the design
period (seasons 2017-2021; partition A agreed with Rosa) against comparable weeks
without an onset. It is descriptive: mean differences with a bootstrap CI per
episode, without p-values or causal language.

Everything is computed in memory. The "status" of a district in week ``w`` uses
only data of weeks <= ``w``; the profile of an onset at ``s`` looks at
``w = s - k`` with ``k = 1..12``. The climatology (anomalies), the core district
ranking and the terciles are fitted **only with the design period** and only
serve this diagnosis: in phase 2 they are recomputed with each block's training
data.

Controls (two kinds, both with the same epidemiological week, inside the design
period, without ``brote`` in the week nor in the 8 previous ones and with those
8 weeks observed):

- ``semana``: any district, any season of the period.
- ``distrito``: the same district in other seasons; if it has fewer than
  ``MIN_DISTRICT_CONTROLS``, districts of the same historical-cases tercile.

Consistency rule (fixed before seeing results), per variable and a-priori window,
with the mean onset - control difference averaged over the window:

- **observed**: the sign is the same in the 4 cells (2017 and 2018-2021 x
  control ``semana`` and ``distrito``) and the CI95 of the full period excludes 0
  with both controls;
- **hypothesis (2017 only)**: it does not meet the above, but in 2017 the sign
  agrees with both controls and its 2017 CI95 excludes 0 with both;
- **not observed**: the rest;
- **not evaluable**: one of those cells is missing (e.g. the previous season
  does not exist for 2017).
"""

import numpy as np
import pandas as pd

from denguekay.data.seasons import assign_season
from denguekay.evaluation import episodes as diag
from denguekay.features.climate import fit_climatology
from denguekay.evaluation.protocol import stratified_bootstrap
from denguekay.model.train import SEASON_START_WEEK
from denguekay.features.neighbors import geographic_catalog, neighborhood_matrix

DESIGN_SEASONS = (2017, 2018, 2019, 2020, 2021)
PERIODS = {"2017": (2017,), "2018_2021": (2018, 2019, 2020, 2021)}
LAGS = tuple(range(1, 13))
NO_PREVIOUS_OUTBREAK = diag.NO_PREVIOUS_OUTBREAK
MIN_DISTRICT_CONTROLS = 2
N_CORE = 5
K_NEIGHBORS = 5
CLIMATE = ("temp_media", "temp_min", "precip_total_mm", "hum_rel_media")
# A-priori windows (k = weeks before the onset, both ends included).
# origen_2_4: what the h=2, 3 and 4 origins see when the target is the
# onset week; previa_5_8: the earlier context. Climate: accumulations over
# 4-8 and 8-12 weeks agreed with Rosa (without picking the lag that stands out most).
WINDOWS = {"origen_2_4": (2, 4), "previa_5_8": (5, 8), "clima_4_8": (4, 8), "clima_8_12": (8, 12)}

FAMILIES = {
    "vecinos": ["vecinos_log_media_casos", "vecinos_frac_con_casos", "vecinos_frac_en_brote",
                "vecinos_n_casos_nuevos", "vecinos_log_media_casos_cambio_1", "vecinos_log_media_casos_cambio_4"],
    "jerarquia": ["provincia_log_otros_casos", "provincia_otros_frac_con_casos", "provincia_otros_frac_en_brote",
                  "provincia_log_otros_casos_cambio_1", "provincia_log_otros_casos_cambio_4",
                  "region_log_otros_casos", "region_otros_frac_con_casos", "region_otros_frac_en_brote",
                  "region_log_otros_casos_cambio_1", "region_log_otros_casos_cambio_4"],
    "nucleo": ["nucleo_log_casos", "nucleo_frac_en_brote", "nucleo_log_casos_cambio_4"],
    "propia": ["propia_log_casos", "propia_con_casos", "propia_semanas_desde_ultimo_caso",
               "propia_pendiente_4", "propia_aceleracion", "propia_log_casos_temporada_anterior"],
    "clima": [*CLIMATE, *(f"{c}_anomalia" for c in CLIMATE)],
}
FAMILY_WINDOWS = {"vecinos": ("origen_2_4", "previa_5_8"), "jerarquia": ("origen_2_4", "previa_5_8"),
                    "nucleo": ("origen_2_4", "previa_5_8"), "propia": ("origen_2_4", "previa_5_8"),
                    "clima": ("clima_4_8", "clima_8_12")}
MAX_WEEKS_WITHOUT_CASE = 52
LABELS = {
    "vecinos_log_media_casos": "Vecinos knn5: log(1 + casos medios)",
    "vecinos_frac_con_casos": "Vecinos knn5: fracción con casos",
    "vecinos_frac_en_brote": "Vecinos knn5: fracción en brote",
    "vecinos_n_casos_nuevos": "Vecinos knn5: nº con casos nuevos",
    "vecinos_log_media_casos_cambio_1": "Vecinos: cambio en 1 semana (log)",
    "vecinos_log_media_casos_cambio_4": "Vecinos: cambio en 4 semanas (log)",
    "provincia_log_otros_casos": "Provincia (sin el propio): log(1 + casos)",
    "provincia_otros_frac_con_casos": "Provincia: fracción con casos",
    "provincia_otros_frac_en_brote": "Provincia: fracción en brote",
    "provincia_log_otros_casos_cambio_1": "Provincia: cambio en 1 semana (log)",
    "provincia_log_otros_casos_cambio_4": "Provincia: cambio en 4 semanas (log)",
    "region_log_otros_casos": "Región (sin el propio): log(1 + casos)",
    "region_otros_frac_con_casos": "Región: fracción con casos",
    "region_otros_frac_en_brote": "Región: fracción en brote",
    "region_log_otros_casos_cambio_1": "Región: cambio en 1 semana (log)",
    "region_log_otros_casos_cambio_4": "Región: cambio en 4 semanas (log)",
    "nucleo_log_casos": "Núcleo (5 distritos, sin el propio): log(1 + casos)",
    "nucleo_frac_en_brote": "Núcleo: fracción en brote",
    "nucleo_log_casos_cambio_4": "Núcleo: cambio en 4 semanas (log)",
    "propia_log_casos": "Propio: log(1 + casos)",
    "propia_con_casos": "Propio: semana con casos (0/1)",
    "propia_semanas_desde_ultimo_caso": "Propio: semanas desde el último caso (tope 52)",
    "propia_pendiente_4": "Propio: pendiente 4 semanas (log)",
    "propia_aceleracion": "Propio: aceleración (log)",
    "propia_log_casos_temporada_anterior": "Propio: log(1 + casos de la temporada anterior)",
    "temp_media": "Temperatura media (°C)", "temp_min": "Temperatura mínima (°C)",
    "precip_total_mm": "Precipitación semanal (mm)", "hum_rel_media": "Humedad relativa media (%)",
    "temp_media_anomalia": "Anomalía de temperatura media (°C)",
    "temp_min_anomalia": "Anomalía de temperatura mínima (°C)",
    "precip_total_mm_anomalia": "Anomalía de precipitación (mm)",
    "hum_rel_media_anomalia": "Anomalía de humedad relativa (puntos %)",
}


# ---------------------------------------------------------------------------
# Onsets and design period
# ---------------------------------------------------------------------------

def with_season(data: pd.DataFrame) -> pd.Series:
    """Epidemiological season (week 35 onwards belongs to the next one)."""
    return assign_season(data.anio, data.semana, SEASON_START_WEEK)


def design_cutoff(series: pd.DataFrame, seasons: tuple[int, ...] = DESIGN_SEASONS) -> pd.Timestamp:
    """Close (Saturday) of the last week of the design period."""
    t = with_season(series)
    return pd.Timestamp(series.loc[t.isin(seasons), "semana_inicio"].max()) + pd.Timedelta(days=6)


def period_of(season: int) -> str:
    for name, seasons in PERIODS.items():
        if season in seasons:
            return name
    return "seleccion_2022_2023" if season in (2022, 2023) else "fuera_diseno"


def clean_onsets(series: pd.DataFrame) -> pd.DataFrame:
    """Episodes with a clean onset, their season, period and whether they are verifiable.

    Verifiable: the ``NO_PREVIOUS_OUTBREAK`` weeks before the onset are inside the
    panel (in January-February 2017 it cannot be checked).
    """
    eps = diag.episodes(series)
    eps = eps[eps.semanas_previas_sin_brote >= NO_PREVIOUS_OUTBREAK].copy()
    calendar = series[["ubigeo", "semana_inicio", "anio", "semana"]].rename(columns={"semana_inicio": "inicio"})
    eps = eps.merge(calendar, on=["ubigeo", "inicio"], how="left", validate="one_to_one")
    eps["temporada"] = with_season(eps)
    eps["periodo"] = eps.temporada.map(period_of)
    first = pd.Timestamp(series.semana_inicio.min())
    eps["verificable"] = (eps.inicio - first).dt.days // 7 >= NO_PREVIOUS_OUTBREAK
    eps["semana_clima"] = eps.semana.clip(upper=52).astype(int)
    eps = eps.sort_values(["inicio", "ubigeo"]).reset_index(drop=True)
    eps["id_inicio"] = np.arange(len(eps))
    return eps


def onset_counts(onsets: pd.DataFrame) -> pd.DataFrame:
    """Clean and verifiable onsets per season and period."""
    return (onsets.groupby(["periodo", "temporada"])
            .agg(limpios=("id_inicio", "size"), verificables=("verificable", "sum"),
                 distritos=("ubigeo", "nunique"), semanas_brote_mediana=("semanas_brote", "median"))
            .reset_index())


# ---------------------------------------------------------------------------
# Weekly status (only data of weeks <= w)
# ---------------------------------------------------------------------------

def _width(data: pd.DataFrame, column: str, ids: pd.Index) -> pd.DataFrame:
    table = data.pivot(index="semana_inicio", columns="ubigeo", values=column).reindex(columns=ids)
    if table.isna().any().any():
        raise ValueError(f"Faltan distrito-semanas en {column}")
    return table.sort_index()


def _slope(y: pd.DataFrame, window: int = 4) -> pd.DataFrame:
    """OLS slope of the last ``window`` weeks (``w`` included)."""
    x = np.arange(window) - (window - 1) / 2
    weights = x / (x ** 2).sum()
    return sum(y.shift(window - 1 - i) * weights[i] for i in range(window))


def own_history(y: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Weeks since the last week with cases (capped) and the 4-week slope of ``log(1 + cases)``.

    ``y`` holds cases per week (rows, in order and without gaps) and district (columns). Each district only
    uses its own weeks <= ``w``, so it also serves the vector of the serving origin (B3).
    """
    last = pd.DataFrame(np.where(y.to_numpy() > 0, np.arange(len(y))[:, None], np.nan),
                          index=y.index, columns=y.columns).ffill()
    start = np.arange(len(y))[:, None] - last
    return {"propia_semanas_desde_ultimo_caso": start.fillna(MAX_WEEKS_WITHOUT_CASE).clip(upper=MAX_WEEKS_WITHOUT_CASE),
            "propia_pendiente_4": _slope(np.log1p(y))}


def core_ranking(series: pd.DataFrame, cutoff: pd.Timestamp) -> pd.Series:
    """Cases accumulated per district in weeks closed at the cutoff, from highest to lowest."""
    closed = series[(series.semana_inicio + pd.Timedelta(days=6)).le(cutoff)]
    return closed.groupby("ubigeo").casos_Dengue.sum().sort_values(ascending=False, kind="stable")


def terciles(series: pd.DataFrame, cutoff: pd.Timestamp) -> pd.Series:
    """Tercile of the cases accumulated at the cutoff (low, medium, high) per district."""
    cumulative = core_ranking(series, cutoff)
    return pd.qcut(cumulative.rank(method="first"), 3, labels=["bajo", "medio", "alto"]).astype(str)


def weekly_status(panel: pd.DataFrame, series: pd.DataFrame, cutoff: pd.Timestamp,
                   n_core: int = N_CORE) -> pd.DataFrame:
    """Descriptors per district and week ``w`` computed with data of weeks <= ``w``.

    ``series`` holds ``casos_Dengue`` and ``brote`` (the label of ``w`` uses the
    same week of previous years and the cases of ``w``: it is known when ``w``
    closes). The core (the ``n_core`` districts with the most cases at the
    cutoff, excluding the district itself) and the anomaly climatology are
    fitted only with weeks closed at the ``cutoff``.
    """
    geo = geographic_catalog(panel)
    weights, _ = neighborhood_matrix(geo, k=K_NEIGHBORS)
    ids = weights.index
    s = series.copy()
    s["semana_inicio"] = pd.to_datetime(s.semana_inicio)
    y = _width(s, "casos_Dengue", ids).astype(float)
    b = _width(s, "brote", ids).astype(float)
    w = weights.to_numpy()
    active = (y > 0).astype(float)
    new_rows = ((y > 0) & (y.shift(1) == 0)).astype(float)

    provinces = geo.set_index("ubigeo").loc[ids, "provincia"].to_numpy()
    prov = (provinces[:, None] == provinces[None, :]).astype(float)
    np.fill_diagonal(prov, 0)
    region = np.ones_like(prov) - np.eye(len(ids))
    n_prov, n_reg = prov.sum(axis=1), region.sum(axis=1)

    order = list(core_ranking(s, cutoff).index)
    core = np.zeros_like(prov)
    for i, u in enumerate(ids):
        for v in [v for v in order if v != u][:n_core]:
            core[i, ids.get_loc(v)] = 1.0

    def frame(m):
        return pd.DataFrame(np.asarray(m), index=y.index, columns=ids)

    vals = {
        "vecinos_log_media_casos": np.log1p(frame(y.to_numpy() @ w.T)),
        "vecinos_frac_con_casos": frame(active.to_numpy() @ w.T),
        "vecinos_frac_en_brote": frame(b.to_numpy() @ w.T),
        "vecinos_n_casos_nuevos": frame(new_rows.to_numpy() @ (w > 0).T.astype(float)),
        "provincia_log_otros_casos": np.log1p(frame(y.to_numpy() @ prov.T)),
        "provincia_otros_frac_con_casos": frame(active.to_numpy() @ prov.T / n_prov),
        "provincia_otros_frac_en_brote": frame(b.to_numpy() @ prov.T / n_prov),
        "region_log_otros_casos": np.log1p(frame(y.to_numpy() @ region.T)),
        "region_otros_frac_con_casos": frame(active.to_numpy() @ region.T / n_reg),
        "region_otros_frac_en_brote": frame(b.to_numpy() @ region.T / n_reg),
        "nucleo_log_casos": np.log1p(frame(y.to_numpy() @ core.T)),
        "nucleo_frac_en_brote": frame(b.to_numpy() @ core.T / n_core),
    }
    for base in ("vecinos_log_media_casos", "provincia_log_otros_casos", "region_log_otros_casos"):
        vals[f"{base}_cambio_1"] = vals[base] - vals[base].shift(1)
        vals[f"{base}_cambio_4"] = vals[base] - vals[base].shift(4)
    vals["nucleo_log_casos_cambio_4"] = vals["nucleo_log_casos"] - vals["nucleo_log_casos"].shift(4)

    ly = np.log1p(y)
    vals["propia_log_casos"] = ly
    vals["propia_con_casos"] = active
    vals.update(own_history(y))
    vals["propia_aceleracion"] = (ly - ly.shift(1)) - (ly.shift(1) - ly.shift(2))
    weeks = s.drop_duplicates("semana_inicio").set_index("semana_inicio").loc[y.index]
    season = with_season(weeks).to_numpy()
    # Cases of the whole previous season: closed before any w of the current one.
    by_season = y.groupby(season).sum()
    previous = by_season.shift(1).reindex(season)
    previous.index = y.index
    vals["propia_log_casos_temporada_anterior"] = np.log1p(previous)

    length = []
    for name, m in vals.items():
        length.append(m.stack(future_stack=True).rename(name))
    status = pd.concat(length, axis=1).reset_index()

    climate = panel[["ubigeo", "semana_inicio", "anio", "semana", *CLIMATE]].copy()
    climate["semana_inicio"] = pd.to_datetime(climate.semana_inicio)
    climate["semana_clima"] = climate.semana.clip(upper=52).astype(int)
    climatology = fit_climatology(panel, cutoff, CLIMATE).table
    climate = climate.merge(climatology, on=["ubigeo", "semana_clima"], how="left", suffixes=("", "_clim"),
                        validate="many_to_one")
    for c in CLIMATE:
        climate[f"{c}_anomalia"] = climate[c] - climate[f"{c}_clim"]
    status = status.merge(climate[["ubigeo", "semana_inicio", *CLIMATE, *(f"{c}_anomalia" for c in CLIMATE)]],
                          on=["ubigeo", "semana_inicio"], how="left", validate="one_to_one")
    status["ubigeo"] = status.ubigeo.astype("string")
    return status.sort_values(["ubigeo", "semana_inicio"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------

def eligible_weeks(series: pd.DataFrame, seasons: tuple[int, ...] = DESIGN_SEASONS) -> pd.DataFrame:
    """District-weeks without an outbreak in the week nor in the 8 previous ones, observed, of the period."""
    s = series.sort_values(["ubigeo", "semana_inicio"]).copy()
    s["temporada"] = with_season(s)
    previous_value = (s.groupby("ubigeo").brote.transform(lambda x: x.rolling(NO_PREVIOUS_OUTBREAK + 1, min_periods=1).max()))
    first = pd.Timestamp(s.semana_inicio.min())
    observed = (s.semana_inicio - first).dt.days // 7 >= NO_PREVIOUS_OUTBREAK
    ok = previous_value.eq(0) & observed & s.temporada.isin(seasons)
    output = s.loc[ok, ["ubigeo", "semana_inicio", "temporada", "semana"]].copy()
    output["semana_clima"] = output.semana.clip(upper=52).astype(int)
    return output.drop(columns="semana").reset_index(drop=True)


def controls(onsets: pd.DataFrame, eligible: pd.DataFrame, tercile: pd.Series,
              min_district: int = MIN_DISTRICT_CONTROLS) -> pd.DataFrame:
    """Onset -> control pairs of both kinds (``semana`` and ``distrito``).

    ``distrito`` uses the same district in other seasons; with fewer than
    ``min_district``, districts of the same ``tercile`` (``tipo_efectivo`` is set
    to ``tercil``).
    """
    base = onsets[["id_inicio", "ubigeo", "temporada", "semana_clima"]]
    by_week = base.merge(eligible.rename(columns={"ubigeo": "ubigeo_control", "semana_inicio": "semana_control",
                                                      "temporada": "temporada_control"}),
                            on="semana_clima")
    week = by_week.assign(tipo="semana", tipo_efectivo="semana")
    same = by_week[by_week.ubigeo_control.eq(by_week.ubigeo)
                       & by_week.temporada_control.ne(by_week.temporada)]
    n = same.groupby("id_inicio").size().reindex(base.id_inicio, fill_value=0)
    missing = n[n < min_district].index
    t = by_week.ubigeo.map(tercile)
    t_control = by_week.ubigeo_control.map(tercile)
    fallback = by_week[by_week.id_inicio.isin(missing) & t.eq(t_control)
                          & ~(by_week.ubigeo_control.eq(by_week.ubigeo)
                              & by_week.temporada_control.eq(by_week.temporada))]
    district = pd.concat([same[~same.id_inicio.isin(missing)].assign(tipo_efectivo="distrito"),
                          fallback.assign(tipo_efectivo="tercil")], ignore_index=True).assign(tipo="distrito")
    cols = ["id_inicio", "tipo", "tipo_efectivo", "ubigeo_control", "semana_control"]
    return pd.concat([week[cols], district[cols]], ignore_index=True)


# ---------------------------------------------------------------------------
# Profiles and summaries
# ---------------------------------------------------------------------------

def profiles(status: pd.DataFrame, onsets: pd.DataFrame, pairs: pd.DataFrame,
             variables: list[str], lags: tuple[int, ...] = LAGS) -> pd.DataFrame:
    """Onset - mean of controls difference for each onset, kind, variable and ``k``."""
    est = status.set_index(["ubigeo", "semana_inicio"])[variables]
    rows = []
    for k in lags:
        delta = pd.Timedelta(weeks=k)
        ini = est.reindex(pd.MultiIndex.from_arrays([onsets.ubigeo, onsets.inicio - delta])).to_numpy()
        ini = pd.DataFrame(ini, columns=variables).assign(id_inicio=onsets.id_inicio.to_numpy())
        ctl = est.reindex(pd.MultiIndex.from_arrays([pairs.ubigeo_control, pairs.semana_control - delta])).to_numpy()
        ctl = (pd.DataFrame(ctl, columns=variables)
               .assign(id_inicio=pairs.id_inicio.to_numpy(), tipo=pairs.tipo.to_numpy())
               .groupby(["id_inicio", "tipo"])[variables].mean())
        n_ctl = pairs.groupby(["id_inicio", "tipo"]).size().rename("n_controles")
        for kind in pairs.tipo.unique():
            c = ctl.xs(kind, level="tipo").reindex(ini.id_inicio)
            diff = ini[variables].to_numpy() - c.to_numpy()
            length = pd.DataFrame(diff, columns=variables).assign(id_inicio=ini.id_inicio.to_numpy()).melt(
                "id_inicio", var_name="variable", value_name="diferencia")
            v_ini = ini.melt("id_inicio", var_name="variable", value_name="valor_inicio")
            v_ctl = c.reset_index().melt("id_inicio", var_name="variable", value_name="valor_control")
            length = length.merge(v_ini, on=["id_inicio", "variable"]).merge(v_ctl, on=["id_inicio", "variable"])
            rows.append(length.assign(tipo_control=kind, k=k)
                         .merge(n_ctl.xs(kind, level="tipo").rename("n_controles").reset_index(), on="id_inicio",
                                how="left"))
    table = pd.concat(rows, ignore_index=True)
    return table.merge(onsets[["id_inicio", "periodo", "temporada"]], on="id_inicio", how="left")


def _summary(g: pd.DataFrame, value: str = "diferencia") -> pd.Series:
    g = g.dropna(subset=[value])
    if g.empty:
        return pd.Series({"inicios": 0, "media": np.nan, "media_inicio": np.nan, "media_control": np.nan,
                          "ic95_inferior": np.nan, "ic95_superior": np.nan})
    means = stratified_bootstrap(g[value].to_numpy(float), g.periodo.to_numpy())
    return pd.Series({"inicios": len(g), "media": float(g[value].mean()),
                      "media_inicio": float(g.valor_inicio.mean()) if "valor_inicio" in g else np.nan,
                      "media_control": float(g.valor_control.mean()) if "valor_control" in g else np.nan,
                      "ic95_inferior": float(np.quantile(means, 0.025)),
                      "ic95_superior": float(np.quantile(means, 0.975))})


def _with_full_period(table: pd.DataFrame) -> pd.DataFrame:
    return pd.concat([table, table.assign(periodo_resumen="2017_2021")], ignore_index=True)


def summary_by_lag(table: pd.DataFrame) -> pd.DataFrame:
    """Mean and bootstrap CI95 (per episode, stratified by period) per ``k``."""
    t = _with_full_period(table.assign(periodo_resumen=table.periodo))
    return (t.groupby(["periodo_resumen", "tipo_control", "variable", "k"])
            .apply(_summary, include_groups=False).reset_index())


def by_window(table: pd.DataFrame, families: dict = FAMILIES) -> pd.DataFrame:
    """Mean difference of each onset inside the a-priori windows of its family."""
    family = {v: f for f, vs in families.items() for v in vs}
    parts = []
    for name, (k0, k1) in WINDOWS.items():
        sel = table[table.k.between(k0, k1) & table.variable.map(family).map(
            lambda f: name in FAMILY_WINDOWS.get(f, ()))]
        if sel.empty:
            continue
        agg = (sel.groupby(["id_inicio", "periodo", "tipo_control", "variable"])
               [["diferencia", "valor_inicio", "valor_control"]].mean().reset_index().assign(ventana=name))
        parts.append(agg)
    output = pd.concat(parts, ignore_index=True)
    output["familia"] = output.variable.map(family)
    return output


def windows_summary(windows: pd.DataFrame) -> pd.DataFrame:
    """Mean and CI95 per period (2017, 2018-2021 and full), control, variable and window."""
    t = _with_full_period(windows.assign(periodo_resumen=windows.periodo))
    return (t.groupby(["familia", "variable", "ventana", "tipo_control", "periodo_resumen"])
            .apply(_summary, include_groups=False).reset_index())


def consistency(summary: pd.DataFrame) -> pd.DataFrame:
    """Apply the consistency rule of the module docstring to each variable and window."""
    rows = []
    for (family, variable, window), g in summary.groupby(["familia", "variable", "ventana"]):
        r = g.set_index(["tipo_control", "periodo_resumen"])
        def cell(kind, period, col="media"):
            return float(r.loc[(kind, period), col]) if (kind, period) in r.index else np.nan
        signs = [np.sign(cell(t, p)) for t in ("semana", "distrito") for p in PERIODS]
        excludes = lambda t, p: (cell(t, p, "ic95_inferior") > 0) or (cell(t, p, "ic95_superior") < 0)
        same_sign = len(set(signs)) == 1 and signs[0] != 0 and not np.isnan(signs[0])
        observed = same_sign and all(excludes(t, "2017_2021") for t in ("semana", "distrito"))
        s17 = {np.sign(cell(t, "2017")) for t in ("semana", "distrito")}
        only_2017 = (len(s17) == 1 and 0 not in s17 and all(excludes(t, "2017") for t in ("semana", "distrito")))
        cells = [cell(t, p) for t in ("semana", "distrito") for p in (*PERIODS, "2017_2021")]
        if any(np.isnan(x) for x in cells):
            verdict = "no_evaluable"
        else:
            verdict = "observada" if observed else ("hipotesis_solo_2017" if only_2017 else "no_observada")
        rows.append({"familia": family, "variable": variable, "ventana": window, "veredicto": verdict,
                      "signo": int(signs[0]) if same_sign else 0,
                      **{f"media_{t}_{p}": cell(t, p) for t in ("semana", "distrito")
                         for p in (*PERIODS, "2017_2021")}})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 2021 onsets with reference B (the only block of the design period)
# ---------------------------------------------------------------------------

def onsets_with_prediction(onsets: pd.DataFrame, predictions: pd.DataFrame,
                           block: str = "temporada_2021") -> pd.DataFrame:
    """Raw probability and predicted cases for the onset week, per horizon.

    Median across seeds. In 2021 (initial calibration block) there is no
    calibrated probability; the raw one and the count are described.
    """
    p = predictions[predictions.bloque.eq(block)]
    med = (p.groupby(["ubigeo", "semana_inicio", "horizonte"])
           [["probabilidad_brote", "casos_predichos", "persistencia", "casos_Dengue"]].median().reset_index())
    ini = onsets[onsets.temporada.eq(int(block.split("_")[-1]))][["id_inicio", "ubigeo", "inicio", "semanas_brote"]]
    return ini.merge(med.rename(columns={"semana_inicio": "inicio"}), on=["ubigeo", "inicio"], how="left")


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

def profiles_figure(summary: pd.DataFrame, variables: list[str], title: str, labels: dict | None = None):
    """Onset - control difference per ``k`` (CI95), per period and control kind."""
    import matplotlib.pyplot as plt

    labels = labels or {}
    n = len(variables)
    columns = 3
    rows = int(np.ceil(n / columns))
    fig, axes = plt.subplots(rows, columns, figsize=(5.2 * columns, 3.4 * rows), squeeze=False)
    styles = {("2017", "semana"): ("#0072B2", "-"), ("2017", "distrito"): ("#0072B2", "--"),
               ("2018_2021", "semana"): ("#D55E00", "-"), ("2018_2021", "distrito"): ("#D55E00", "--")}
    for ax, v in zip(axes.ravel(), variables):
        for (period, kind), (color, line) in styles.items():
            g = summary[summary.variable.eq(v) & summary.periodo_resumen.eq(period)
                        & summary.tipo_control.eq(kind)].sort_values("k")
            ax.plot(-g.k, g.media, color=color, linestyle=line, marker="o", markersize=3,
                    label=f"{period.replace('_', '–')} · control {kind}")
            ax.fill_between(-g.k, g.ic95_inferior, g.ic95_superior, color=color, alpha=0.08)
        ax.axhline(0, color="grey", linewidth=0.8)
        ax.set_title(labels.get(v, v), fontsize=9)
        ax.set_xlabel("Semanas antes del inicio (−k)")
        ax.set_ylabel("Inicio − control")
    for ax in axes.ravel()[n:]:
        ax.axis("off")
    axes[0, 0].legend(fontsize=7)
    fig.suptitle(title)
    fig.tight_layout()
    return fig


def errors_by_phase(evaluations: list[dict], blocks: tuple[str, ...]) -> pd.DataFrame:
    """Median and range across seeds of the errors per phase of the regional curve."""
    every = pd.concat([e["errores_por_fase"] for e in evaluations], ignore_index=True)
    every = every[every.bloque.isin(blocks)].astype({"fase": str})
    columns = ["razon_mae", "razon_rmse", "sesgo_modelo", "sesgo_persistencia", "suma_predicha_sobre_real"]
    g = every.groupby(["horizonte", "bloque", "fase"])
    output = g[["n", *columns]].median()
    span = (g[["razon_mae", "razon_rmse"]].max() - g[["razon_mae", "razon_rmse"]].min()).add_prefix("rango_")
    return output.join(span).reset_index()


def phase_errors_figure(table: pd.DataFrame):
    """MAE relative to persistence per curve phase, horizon and season."""
    import matplotlib.pyplot as plt

    order = [f for f in diag.PHASE_ORDER if f in set(table.fase)]
    blocks = sorted(table.bloque.unique())
    fig, axes = plt.subplots(1, len(blocks), figsize=(6 * len(blocks), 4), squeeze=False)
    for ax, block in zip(axes.ravel(), blocks):
        t = table[table.bloque.eq(block)]
        x = np.arange(len(order))
        for i, h in enumerate(sorted(t.horizonte.unique())):
            g = t[t.horizonte.eq(h)].set_index("fase").reindex(order)
            ax.bar(x + (i - 1) * 0.27, g.razon_mae, 0.27, yerr=g.rango_razon_mae / 2, label=f"h={h}")
        ax.axhline(1, color="grey", linewidth=0.8)
        ax.set_xticks(x, order)
        ax.set_ylabel("MAE modelo / MAE persistencia")
        ax.set_title(block.replace("temporada_", "Temporada "))
        ax.legend(fontsize=8)
    fig.suptitle("E3·S4_s2 (referencia B): error de casos por fase de la curva regional")
    fig.tight_layout()
    return fig
