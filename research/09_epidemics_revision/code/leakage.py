"""Dynamic leakage tests: change the future and check that what the model sees at an origin does not change.

- Case history: every count after the origin week is replaced with random values; the predictors at the origin
  and the outbreak thresholds of its target weeks must be identical.
- Weather and Niño 1+2: every value published after the origin close is replaced with random values; the
  lag-2 and lag-1 predictors must be identical, while the historical lag-0 alignment must change (positive
  control: the test detects look-ahead when it exists).
- Calibration windows: Platt parameters and blend weights are refitted from earlier blocks whose labels closed by
  each block's cutoff and compared with the stored ones.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import common as c
from denguekay.features import long_history as lh

eh = c.spatial.eh
fi, long_labels, long_matrix = lh.fi, lh.long_labels, lh.long_matrix
WEATHER = [*c.spatial.B3, *c.spatial.D3]


def case_part(cases: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    """Matrices and origins built from a case series exactly as ``long_inputs`` builds them."""
    labels = long_labels(cases)
    matrices = {h: long_matrix(cases, labels, h) for h in eh.STRATEGY_HORIZONS}
    origins = fi.with_onset_columns(eh.origin_table(matrices[2]), cases,
                                    cases.iloc[:0][["ubigeo", "anio", "semana", "casos_Dengue"]])
    return matrices, origins


def case_history_test(inputs: dict, closes, columns: list[str], seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    cases = inputs["casos"]
    base_matrices, base_origins = case_part(cases)
    rows = []
    for close in pd.to_datetime(closes):
        week = close - 6 * c.DAY
        future = cases.semana_inicio.gt(week)
        perturbed = cases.copy()
        perturbed.loc[future, "casos_Dengue"] = rng.integers(0, 400, int(future.sum()))
        matrices, origins = case_part(perturbed)
        a = base_origins.loc[base_origins.origen_cierre.eq(close)].sort_values("ubigeo")[["ubigeo", *columns]]
        b = origins.loc[origins.origen_cierre.eq(close)].sort_values("ubigeo")[["ubigeo", *columns]]
        same_features = len(a) == 65 and a.reset_index(drop=True).equals(b.reset_index(drop=True))
        same_thresholds, targets = True, 0
        for h in eh.STRATEGY_HORIZONS:
            keep = ["ubigeo", "semana_inicio", "umbral_brote_casos", "persistencia"]
            x = base_matrices[h].loc[base_matrices[h].origen_cierre.eq(close), keep].sort_values("ubigeo")
            y = matrices[h].loc[matrices[h].origen_cierre.eq(close), keep].sort_values("ubigeo")
            # The last origins have no t+3/t+4 target yet: both sides are then empty.
            same_thresholds &= len(x) == len(y) and x.reset_index(drop=True).equals(y.reset_index(drop=True))
            targets += len(x)
        later = base_origins.origen_cierre.gt(close + 7 * c.DAY)
        moved = (base_origins.loc[later, columns].reset_index(drop=True)
                 .ne(origins.loc[origins.origen_cierre.gt(close + 7 * c.DAY), columns].reset_index(drop=True))
                 .any(axis=1).mean()) if later.any() else np.nan
        rows.append({"origen_cierre": close.date(), "filas_futuras_alteradas": int(future.sum()),
                     "objetivos_comparados": targets,
                     "predictores_iguales": bool(same_features), "umbrales_y_persistencia_iguales": bool(same_thresholds),
                     "control_origenes_posteriores_cambian": None if np.isnan(moved) else round(float(moved), 3)})
    return pd.DataFrame(rows)


def weather_test(closes, seed: int = 2) -> tuple[pd.DataFrame, dict]:
    rng = np.random.default_rng(seed)
    rain, era, enso = c.weather_sources()
    equivalence = {}
    for lag in (0, 2):
        mine = c.weekly_fields_by_source(rain, era, lag, lag)
        theirs = c.spatial.weekly_fields(rain, era, lag)
        pd.testing.assert_frame_equal(mine.sort_values(["ubigeo", "semana_origen"]).reset_index(drop=True),
                                      theirs.sort_values(["ubigeo", "semana_origen"]).reset_index(drop=True))
        equivalence[f"lag {lag}"] = "identical to run_spatial_controls.weekly_fields"
    configs = {"lag0_historico": (0, 0), "lag1": (2, 1), "lag2_obs": (2, 2)}
    base = {name: c.weekly_fields_by_source(rain, era, *lags) for name, lags in configs.items()}
    rows = []
    for close in pd.to_datetime(closes):
        week = close - 6 * c.DAY
        r, e, n = rain.copy(), era.copy(), enso.copy()
        late_r, late_e, late_n = r.fecha_disponible.gt(close), e.fecha_disponible.gt(close), n.fecha_disponible.gt(close)
        r.loc[late_r, "precip_total_mm"] = rng.uniform(0, 300, int(late_r.sum()))
        for column in ("temp_media", "hum_rel_media"):
            e.loc[late_e, column] = rng.uniform(0, 60, int(late_e.sum()))
        n.loc[late_n, "nino12_anom"] = rng.uniform(-5, 5, int(late_n.sum()))
        record = {"origen_cierre": close.date()}
        for name, lags in configs.items():
            new = c.weekly_fields_by_source(r, e, *lags, enso=n)
            x = base[name].loc[base[name].semana_origen.eq(week)].sort_values("ubigeo")[["ubigeo", *WEATHER]]
            y = new.loc[new.semana_origen.eq(week)].sort_values("ubigeo")[["ubigeo", *WEATHER]]
            changed = x.reset_index(drop=True).ne(y.reset_index(drop=True)).any(axis=1)
            record[f"{name}: distritos con valores alterados"] = int(changed.sum())
        rows.append(record)
    return pd.DataFrame(rows), equivalence


def calibration_windows(arm: str, seed: int) -> pd.DataFrame:
    """Refit Platt and the blend weight per block from earlier blocks with labels closed by the cutoff."""
    pa, p5 = c.spatial.pa, c.archive.original.p5
    table = c.read_arm(arm, seeds=(seed,))
    rows = []
    for h, by_h in table.groupby("horizonte"):
        onsets = by_h.groupby("bloque").semana_inicio.min().sort_values()
        for block, start in onsets.items():
            part = by_h[by_h.bloque.eq(block)]
            cutoff = pa.block_cutoff(part)
            earlier = by_h[by_h.bloque.map(onsets).lt(start)]
            used = earlier[(earlier.semana_inicio + 6 * c.DAY).le(cutoff)]
            row = {"horizonte": h, "bloque": block, "corte": cutoff.date(), "filas": len(used),
                   "ultima_etiqueta": (used.semana_inicio.max() + 6 * c.DAY).date() if len(used) else None,
                   "primer_origen_prueba": part.origen_cierre.min().date()}
            if used.brote.nunique() == 2 and part.platt_a.notna().all():
                model = pa.fit_platt(used.probabilidad_cruda.to_numpy(float), used.brote.to_numpy(int))
                row["platt_a_dif"] = abs(float(model.coef_[0][0]) - float(part.platt_a.iloc[0]))
                row["platt_b_dif"] = abs(float(model.intercept_[0]) - float(part.platt_b.iloc[0]))
            if len(used):
                w = p5.fit_w(used.mu_modelo.to_numpy(float), used.persistencia.to_numpy(float),
                             used.casos_Dengue.to_numpy(float))
                row["w_dif"] = abs(w - float(part.w_mezcla.iloc[0]))
            rows.append(row)
    return pd.DataFrame(rows)
