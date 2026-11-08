"""Season 2026 evaluation (``preregistration.SEASON_2026``): data extended to 2026 in memory, the four variants
(L + 5a, b3, d1, d2) in the usual blocks plus temporada_2026 and posterior_2026, the decision over 6 seasons,
the per-cell metrics and readings, and the leave-one-season-out reading.

The case series is the study's (2005-2025) plus the Sala 2026 weeks 1 to N-2 (the last 2 published weeks are
provisional and stay out). Climate: CHIRPS silver (final + preliminary weeks), ERA5-Land 2000-2026, Niño 1+2. The
days >= 20 mm of the preliminary weeks come from a daily polygon-mean file computed with the feat branch
(``PRELIM_DAILY``, an input of the experiment kept outside data/).
"""

import numpy as np
import pandas as pd

from denguekay.config.paths import MODELS, SILVER, SILVER_SALA
from denguekay.evaluation import protocol as pa
from denguekay.model import probabilistic_output as sp

import phase0_diagnosis as p0
import phase1_history as p1
import phase1b_prime as pb
import phase3_onsets as p3
import phase4_enso as p4
import phase5_counts as p5
import phase_b3_full_climate as b3
import phase_b_rain as pbr
import phase_d_weather_windows as pdw
import preregistration as pr

OUTPUT_DIR = MODELS / "experimentos" / "mejora_modelo" / "temporada_2026"
PRELIM_DAILY = OUTPUT_DIR / "chirps_prelim_diario_poligono.csv"
ERA5_2026 = SILVER / "meteo_humedad_era5_land_2000_2026.csv"
NEW_BLOCKS = [("temporada_2026", "temporada", 2026), ("posterior_2026", "temporada", 2027)]
OLD_BLOCK_TOLERANCE = 1e-6
LOSO_SEASONS = (2010, 2015, 2016, 2017, 2022, 2023, 2024, 2026)
LOSO_BUFFER_WEEKS = 4
CELL_SEASONS = (*pr.SEASON_2026_DECIDING, 2017, 2024)


def blocks() -> list[tuple[str, str, int]]:
    return [*p1.seasonal_blocks(p1.FIRST_BLOCK_SEASON_LONG), *NEW_BLOCKS]


def block_names(seasons) -> list[str]:
    return [pr.block_name(s) for s in seasons]


# --- Data ------------------------------------------------------------------------------------------------------

def sala_2026(provisional: int = pr.SEASON_2026_PROVISIONAL_WEEKS) -> tuple[pd.DataFrame, list[int]]:
    """Sala 2026 rows of the silver without the last ``provisional`` published weeks, with ``semana_inicio``."""
    sala = pd.read_csv(SILVER_SALA, dtype={"ubigeo": "string"})
    s = sala[sala.anio.eq(2026)].copy()
    s["ubigeo"] = s.ubigeo.astype(str)
    last = int(s.semana.max())
    dropped = list(range(last - provisional + 1, last + 1))
    s = s[s.semana.le(last - provisional)]
    s = s.merge(p0.week_grid(2026, 2026), on=["anio", "semana"], how="left", validate="many_to_one")
    if s.semana_inicio.isna().any():
        raise ValueError("Semanas de la Sala 2026 fuera de la grilla MMWR")
    return s[["ubigeo", "anio", "semana", "semana_inicio", "casos_Dengue"]], dropped


def sala_missing_2025(panel: pd.DataFrame) -> pd.DataFrame:
    """Sala 2025 weeks that the integrated panel lacks (week 53 of 2025, 2025-12-28): without them the series has a
    gap before 2026. Same source (silver epi_sala_semanal.csv) as the 2025 weeks of the panel."""
    sala = pd.read_csv(SILVER_SALA, dtype={"ubigeo": "string"})
    s = sala[sala.anio.eq(2025)].copy()
    s["ubigeo"] = s.ubigeo.astype(str)
    have = set(zip(panel.ubigeo.astype(str), panel.anio, panel.semana))
    s = s[[k not in have for k in zip(s.ubigeo, s.anio, s.semana)]]
    s = s.merge(p0.week_grid(2025, 2025), on=["anio", "semana"], how="left", validate="many_to_one")
    return s[["ubigeo", "anio", "semana", "semana_inicio", "casos_Dengue"]]


def inputs_2026() -> dict:
    """``phase3_onsets.phase3_inputs`` with the Sala 2025 weeks the panel lacks and the Sala 2026 appended to the
    panel (in memory)."""
    base = p3.phase3_inputs()
    panel = base["panel"]
    s26, provisional = sala_2026()
    s25 = sala_missing_2025(panel)
    recent = panel[["ubigeo", "anio", "semana", "semana_inicio", "casos_Dengue"]].assign(
        ubigeo=lambda d: d.ubigeo.astype(str), semana_inicio=lambda d: pd.to_datetime(d.semana_inicio))
    extended = pd.concat([recent, s25, s26], ignore_index=True)
    cases, _ = p0.long_case_series(extended)
    labels = p0.long_labels(cases)
    matrices = p1.long_matrices(cases, labels)
    origins = p1.long_origins(cases, matrices[2])
    series = labels[["ubigeo", "anio", "semana", "semana_inicio", "casos_Dengue", "brote"]].copy()
    series["semana_inicio"] = pd.to_datetime(series.semana_inicio)
    return {"casos": cases, "matrices": matrices, "origenes": origins, "serie": series, "etiquetas": labels,
            "panel": panel, "base": base, "sala_2026": s26, "sala_2025_agregada": s25,
            "semanas_provisionales": provisional}


def guard_series(inp: dict) -> dict:
    """G40: 2005-2025 cases and labels equal the study's on every row of the study's series (the only new rows
    before 2026 are the Sala weeks the panel lacked, reported); the 2026 rows are the Sala's (65 x weeks)."""
    key = ["ubigeo", "anio", "semana"]
    old = inp["base"]["etiquetas"]
    new = inp["etiquetas"]
    m = old.merge(new[new.anio.le(2025)], on=key, how="outer", suffixes=("_v", "_n"), indicator=True)
    added = m[m._merge.eq("right_only")]
    added_keys = set(zip(inp["sala_2025_agregada"].ubigeo, inp["sala_2025_agregada"].anio, inp["sala_2025_agregada"].semana))
    unexpected = int(sum(k not in added_keys for k in zip(added.ubigeo, added.anio, added.semana)))
    both = m[m._merge.eq("both")]
    diff = {c: int((both[f"{c}_v"] != both[f"{c}_n"]).sum()) for c in ("casos_Dengue", "umbral_brote_casos", "brote")}
    n26 = new[new.anio.eq(2026)].merge(inp["sala_2026"], on=key, suffixes=("", "_sala"), how="outer", indicator=True)
    out = {"filas_2005_2025": len(old), "sin_par": int(m._merge.eq("left_only").sum()), "distintas": diff,
           "filas_agregadas_2025": len(added), "semanas_agregadas_2025": sorted(set(map(int, added.semana))),
           "casos_agregados_2025": int(added.casos_Dengue_n.sum()), "agregadas_fuera_de_la_sala": unexpected,
           "filas_2026": int(new.anio.eq(2026).sum()), "distritos_2026": int(new[new.anio.eq(2026)].ubigeo.nunique()),
           "semanas_2026": int(new[new.anio.eq(2026)].semana.nunique()),
           "2026_sin_par_con_la_sala": int(n26._merge.ne("both").sum()),
           "2026_casos_distintos": int((n26.casos_Dengue != n26.casos_Dengue_sala).sum())}
    out["pasa"] = bool(out["sin_par"] == 0 and unexpected == 0 and not any(diff.values()) and out["2026_sin_par_con_la_sala"] == 0
                       and out["2026_casos_distintos"] == 0 and out["distritos_2026"] == 65)
    return out


def era5_2026(panel: pd.DataFrame) -> pd.DataFrame:
    t = b3.era5_land_temperature(panel, path=ERA5_2026)
    h = pb.era5_land_panel(panel, path=ERA5_2026)
    return t.merge(h, on=["ubigeo", "semana_inicio"], how="outer", validate="one_to_one")


def daily_chirps(chirps: pd.DataFrame) -> pd.DataFrame:
    """Daily polygon means with the version of each week in the silver: Earth Engine final for the ``final``
    weeks, the preliminary (``PRELIM_DAILY``) for the ``prelim`` weeks (all 7 days, as the silver)."""
    ee = pdw.read_daily_ee()
    prelim = pd.read_csv(PRELIM_DAILY, dtype={"ubigeo": str}, parse_dates=["fecha"], float_precision="round_trip")
    week = lambda d: d.fecha.dt.to_period("W-SAT").dt.start_time
    prelim_weeks = set(pd.to_datetime(chirps.loc[chirps.version.eq("prelim"), "semana_inicio"]))
    ee = ee[~week(ee).isin(prelim_weeks)]
    prelim = prelim[week(prelim).isin(prelim_weeks)]
    return pd.concat([ee, prelim[["ubigeo", "fecha", "precip_mm"]]], ignore_index=True).sort_values(
        ["ubigeo", "fecha"]).reset_index(drop=True)


def add_climate(inp: dict) -> tuple[pd.DataFrame, dict]:
    """Origins with every climate column of b3, d1 and d2, and the sources used (for the guards)."""
    chirps = pbr.read_chirps()
    era5 = era5_2026(inp["panel"])
    weekly_daily = pdw.weekly_from_daily(daily_chirps(chirps))
    o = pdw.build_d1(inp["origenes"], chirps, era5, weekly_daily)
    o = pbr.add_rain(o, pbr.rain_by_origin_week(chirps))
    o = pb.add_humidity(o, pb.humidity_by_origin_week(era5[["ubigeo", "semana_inicio", "hum_rel_media"]]))
    o = b3.add_temperature(o, b3.temperature_by_origin_week(era5[["ubigeo", "semana_inicio", "temp_media"]]))
    o = p4.enso_at_origins(o, p4.read_enso())
    return o, {"chirps": chirps, "era5": era5, "semanal_diario": weekly_daily}


def variant_columns() -> dict[str, list[str]]:
    base, _ = p3._config()
    return {"L + 5a": list(base), "b3": [*base, *pr.STEP_B3_COLUMNS], "d1": [*base, *pr.STEP_D_COLUMNS],
            "d2": [*base, *pr.STEP_D_COLUMNS, b3.NINO_COLUMN]}


def guard_coverage(origins: pd.DataFrame, columns: list[str], last_close) -> dict:
    """G42: no origin from 2005 to the last one used has a missing climate column."""
    close = pd.to_datetime(origins.origen_cierre)
    sel = close.ge("2005-01-01") & close.le(pd.Timestamp(last_close))
    missing = origins.loc[sel, columns].isna()
    return {"origenes": int(sel.sum()), "sin_valor": int(missing.any(axis=1).sum()),
            "por_columna": {c: int(v) for c, v in missing.sum().items() if v}, "pasa": not missing.any().any()}


# --- Runs -------------------------------------------------------------------------------------------------------

def run_variant(inp: dict, origins: pd.DataFrame, columns: list[str], hp: dict, seeds=pr.SEEDS) -> dict:
    preds, evals, fits = {}, {}, []
    for seed in seeds:
        pred = p3.predict_blocks_weighted(inp["matrices"], origins, blocks(), seed, columns, hp)
        fits.append(pred.attrs.pop("ajustes").assign(semilla=seed))
        preds[seed] = pred
        evals[seed] = p5.evaluate_mixture(pred, inp["serie"])
    return {"predicciones": preds, "evaluaciones": evals, "ajustes": pd.concat(fits, ignore_index=True)}


def guard_old_blocks(preds: dict[int, pd.DataFrame], saved: dict[int, pd.DataFrame],
                     tol: float = OLD_BLOCK_TOLERANCE) -> dict:
    """G41: the rerun reproduces every saved prediction (each saved key is found and |diff| <= tol); new rows of
    the saved blocks (the targets of the added 2025 week) are counted apart."""
    key = ["ubigeo", "semana_inicio", "horizonte", "bloque"]
    worst, rows, missing, extra = {"casos_predichos": 0.0, "probabilidad_brote": 0.0}, 0, 0, 0
    for seed, s in saved.items():
        a = preds[seed]
        a = a[a.bloque.isin(set(s.bloque))].assign(semana_inicio=pd.to_datetime(a.semana_inicio).dt.strftime("%Y-%m-%d"))
        b = s.assign(semana_inicio=pd.to_datetime(s.semana_inicio).dt.strftime("%Y-%m-%d"))
        m = a.merge(b, on=key, suffixes=("", "_guardada"), how="outer", indicator=True, validate="one_to_one")
        missing += int(m._merge.eq("right_only").sum())
        extra += int(m._merge.eq("left_only").sum())
        both = m[m._merge.eq("both")]
        rows += len(both)
        for c in worst:
            worst[c] = max(worst[c], float(np.abs(both[c] - both[f"{c}_guardada"]).max()))
    return {"filas": rows, "guardadas_sin_par": missing, "filas_nuevas_en_bloques_guardados": extra,
            "diferencia_maxima": worst, "tolerancia": tol,
            "pasa": bool(missing == 0 and all(v <= tol for v in worst.values()))}


def read_saved(path) -> dict[int, pd.DataFrame]:
    saved = pd.read_csv(path, dtype={"ubigeo": "string"}, float_precision="round_trip")
    saved["ubigeo"] = saved.ubigeo.astype(object)
    return {int(s): g.drop(columns="semilla").reset_index(drop=True) for s, g in saved.groupby("semilla")}


# --- Decision over 6 seasons --------------------------------------------------------------------------------------

def outbreak_weeks(series: pd.DataFrame, season: int = 2026) -> dict[int, int]:
    """Outbreak weeks of the season per horizon (every target week of the season has its origin)."""
    from denguekay.evaluation import onsets as ons

    n = int(series[ons.with_season(series).eq(season)].brote.sum())
    return {h: n for h in p3.H}


def compare_2026(candidate: dict, reference: dict, outbreaks: dict[int, int]) -> dict:
    """Brier (rule of SEASON_2026), alert and count verdicts over the 6 seasons (5 in a horizon under 30)."""
    med_c = pa.seed_median([e["metricas"] for e in candidate["evaluaciones"].values()])
    med_r = pa.seed_median([e["metricas"] for e in reference["evaluaciones"].values()])
    ranges = pa.tie_threshold(*(pa.seed_ranges([e["metricas"] for e in v["evaluaciones"].values()])
                                for v in (candidate, reference)))
    seed = pr.SEEDS[0]
    six = pr.SEASON_2026_DECIDING
    lead = pr.lead_time_difference_multi(candidate["evaluaciones"][seed]["antelacion"],
                                         reference["evaluaciones"][seed]["antelacion"], "alerta_050", six)
    brier = pr.decide_season_2026(med_c, med_r, ranges, lead, outbreaks)
    alert, count = [], []
    for h in p3.H:
        use6 = outbreaks.get(h, 0) >= pr.SEASON_2026_MIN_OUTBREAK_WEEKS
        seasons = six if use6 else pr.DECIDING_SEASONS
        k, veto = (pr.SEASON_2026_MIN_IN_FAVOUR, pr.SEASON_2026_GUARD_VETO) if use6 else (pr.MIN_IN_FAVOUR, pr.GUARD_VETO_AGAINST)
        blocks_ = block_names(seasons)
        sel = [x[x.horizonte.eq(h) & x.bloque.isin(blocks_)] for x in (med_c, med_r, ranges)]
        ld = lead[lead.horizonte.eq(h)] if use6 else pr.lead_time_difference_multi(
            candidate["evaluaciones"][seed]["antelacion"], reference["evaluaciones"][seed]["antelacion"],
            "alerta_050", seasons).query("horizonte == @h")
        alert.append(pr.decide_multi_season(*sel, ld, seasons=seasons, min_in_favour=k, guard_veto=veto))
        count.append(pr.decide_phase5(*sel, ld, seasons=seasons, min_in_favour=k, guard_veto=veto))
    alert, count = pd.concat(alert, ignore_index=True), pd.concat(count, ignore_index=True)
    return {"brier": brier, "alerta": alert, "conteo": count, "antelacion": lead,
            "adopta": pr.adopt_season_2026(brier, alert, count)}


# --- Per-cell metrics and readings -------------------------------------------------------------------------------

def cell_metrics(variant: dict, series: pd.DataFrame, cells=CELL_SEASONS, extra_blocks=("posterior_2026",)) -> pd.DataFrame:
    """Seed medians of the protocol metrics plus BSS and AUPRC on onsets (persistencia < max(umbral, 2))."""
    names = [*block_names(cells), *extra_blocks]
    med = pa.seed_median([e["metricas"] for e in variant["evaluaciones"].values()])
    med = med[med.bloque.isin(names)]
    rep = []
    for seed, e in variant["evaluaciones"].items():
        data = e["datos"]
        rep.append(pdw.reported_metrics(data, pdw.climatology(data, series), names, floor=2.0))
    rep = pd.concat(rep).groupby(["horizonte", "bloque"]).median().reset_index()
    keep = ["horizonte", "bloque", "positivos", "f1_050", "precision_050", "recall_050", "auprc", "brier",
            "razon_mae", "razon_rmse"]
    return med[keep].merge(rep[["horizonte", "bloque", "bss_climatologia", "brier_climatologia", "n_bajo_umbral",
                                "positivos_bajo_umbral", "auprc_bajo_umbral"]], on=["horizonte", "bloque"])


def nino_by_origin(origins: pd.DataFrame, pred: pd.DataFrame, block_list=("temporada_2026", "posterior_2026")) -> pd.DataFrame:
    """Per origin date of the 2026 blocks: nino12_anom_media3 against the range of the block's training origins."""
    rows = []
    close = pd.to_datetime(origins.origen_cierre)
    for block in block_list:
        b = pred[pred.bloque.eq(block)]
        cutoff = pd.to_datetime(b.origen_cierre).min()
        train = origins[close.ge("2005-01-01") & (pd.to_datetime(origins[f"semana_inicio_h{p3.H[-1]}"]) + pd.Timedelta(days=6)).le(cutoff)]
        lo, hi = float(train[b3.NINO_COLUMN].min()), float(train[b3.NINO_COLUMN].max())
        dates = sorted(pd.to_datetime(b.origen_cierre).unique())
        for d in dates:
            v = float(origins.loc[close.eq(d), b3.NINO_COLUMN].iloc[0])
            rows.append({"bloque": block, "origen_cierre": str(pd.Timestamp(d).date()), "nino12_anom_media3": v,
                         "min_entrenamiento": lo, "max_entrenamiento": hi, "fuera_de_rango": bool(v < lo or v > hi)})
    return pd.DataFrame(rows)


def prelim_origins(origins: pd.DataFrame, chirps: pd.DataFrame, pred: pd.DataFrame,
                   block_list=("temporada_2026", "posterior_2026")) -> pd.DataFrame:
    """Origins of the 2026 blocks whose rainfall windows include a preliminary week (b3: 5 weeks; d1/d2: 13)."""
    prelim_weeks = set(pd.to_datetime(chirps.loc[chirps.version.eq("prelim"), "semana_inicio"]))
    rows = []
    for block in block_list:
        for d in sorted(pd.to_datetime(pred.loc[pred.bloque.eq(block), "origen_cierre"]).unique()):
            week = pd.Timestamp(d) - pd.Timedelta(days=6)
            used = lambda n: {week - pd.Timedelta(weeks=k) for k in range(n)}
            rows.append({"bloque": block, "origen_cierre": str(pd.Timestamp(d).date()),
                         "b3_semanas_prelim": len(used(5) & prelim_weeks), "d_semanas_prelim": len(used(13) & prelim_weeks)})
    return pd.DataFrame(rows)


# --- Leave one season out (reading) ------------------------------------------------------------------------------

def loso_predictions(inp: dict, origins: pd.DataFrame, columns: list[str], hp: dict, seed: int,
                     seasons=LOSO_SEASONS, buffer_weeks: int = LOSO_BUFFER_WEEKS) -> pd.DataFrame:
    """Uncalibrated predictions of each left-out season, trained with every other origin (past and future) except
    those whose origin week or any target falls in the season widened by ``buffer_weeks`` on each side."""
    from denguekay.model import horizon_strategies as eh

    f = sp.FORMULATIONS[p3.FORMULATION]
    extra = sp.e3_parameters(hp)
    margin_all = sp.e3_margin(origins, p3.FORMULATION)
    complete = origins.dropna(subset=[f"semana_inicio_h{h}" for h in p3.H])
    complete = complete[pd.to_datetime(complete.origen_cierre).ge("2005-01-01")]
    parts = []
    for s in seasons:
        tests = {h: eh.split(inp["matrices"][h], "temporada", s)[1] for h in p3.H}
        start = min(t.semana_inicio.min() for t in tests.values()) - pd.Timedelta(weeks=buffer_weeks)
        end = max(t.semana_inicio.max() for t in tests.values()) + pd.Timedelta(weeks=buffer_weeks, days=6)
        inside = lambda col: pd.to_datetime(col).between(start, end)
        touch = inside(pd.to_datetime(complete.origen_cierre) - pd.Timedelta(days=6))
        for h in p3.H:
            touch |= inside(complete[f"semana_inicio_h{h}"])
        train = complete[~touch]
        reg, alphas = p3._fit(train, seed, list(columns), extra, margin_all, None)
        counts = sp.predict_count(reg, origins[list(columns)], f["conteo"], margin_all)
        for step, h in enumerate(p3.H):
            pr_ = pd.DataFrame({"ubigeo": origins.ubigeo, "semana_inicio": origins[f"semana_inicio_h{h}"],
                                "origen_cierre_mimo": origins.origen_cierre, "casos_predichos": counts[:, step]})
            test = tests[h].merge(pr_.dropna(subset=["semana_inicio"]), on=["ubigeo", "semana_inicio"], how="left",
                                  validate="one_to_one")
            if test.casos_predichos.isna().any():
                raise ValueError(f"Predicciones incompletas al dejar fuera {s} h={h}")
            test["probabilidad_brote"] = sp.negative_binomial_probability(test.casos_predichos, alphas[step],
                                                                          test.umbral_brote_casos)
            out = eh._output(test, f"fuera_{s}", test.casos_predichos, test.probabilidad_brote)
            parts.append(out.assign(filas_entrenamiento=len(train)))
    return pd.concat(parts, ignore_index=True)


def loso_calibrate_and_mix(pred: pd.DataFrame) -> pd.DataFrame:
    """Cross-fitted Platt and 5a w: each left-out season uses the out-of-sample rows of the other ones."""
    data = pred.copy()
    data["probabilidad_calibrada"] = np.nan
    data["umbral_diagnostico_f1"] = np.nan
    mixed = data.casos_predichos.to_numpy(float).copy()
    for (h, block), g in data.groupby(["horizonte", "bloque"]):
        others = data[data.horizonte.eq(h) & data.bloque.ne(block)]
        cal = pa.fit_calibrator(others.probabilidad_brote, others.brote)
        data.loc[g.index, "probabilidad_calibrada"] = cal(g.probabilidad_brote)
        w = p5.fit_w(others.casos_predichos.to_numpy(float), others.persistencia.to_numpy(float),
                     others.casos_Dengue.to_numpy(float))
        pos = data.index.get_indexer(g.index)
        mixed[pos] = w * g.casos_predichos.to_numpy(float) + (1 - w) * g.persistencia.to_numpy(float)
    data["casos_predichos"] = mixed
    return pa.add_protocol_alerts(data)


def loso_climatology(data: pd.DataFrame, series: pd.DataFrame) -> pd.Series:
    """Climatology of the leave-one-season-out reading: the step d definition with every other season's labels."""
    from denguekay.evaluation import onsets as ons

    s = series.assign(temporada=ons.with_season(series))
    out = pd.Series(np.nan, index=data.index, dtype=float)
    for block, g in data.groupby("bloque"):
        season = int(block.removeprefix("fuera_"))
        hist = s[s.temporada.ne(season)].drop(columns="temporada")
        fake = g.assign(origen_cierre=pd.Timestamp("2100-01-01"))   # every other label counts as closed
        clim = pdw.climatology(fake.assign(bloque="todo"), hist)
        out.loc[g.index] = clim.to_numpy()
    return out


def loso_metrics(pred_by_seed: dict[int, pd.DataFrame], series: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for seed, pred in pred_by_seed.items():
        data = loso_calibrate_and_mix(pred)
        m = pa.metrics_by_block(data)
        rep = pdw.reported_metrics(data, loso_climatology(data, series), data.bloque.unique(), floor=2.0)
        rows.append(m.merge(rep[["horizonte", "bloque", "bss_climatologia", "auprc_bajo_umbral"]],
                            on=["horizonte", "bloque"]).assign(semilla=seed))
    every = pd.concat(rows, ignore_index=True)
    keep = ["positivos", "f1_050", "auprc", "brier", "razon_mae", "razon_rmse", "bss_climatologia", "auprc_bajo_umbral"]
    return every.groupby(["horizonte", "bloque"])[keep].median().reset_index()
