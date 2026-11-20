"""Refit of the frozen V4 model (B3, ``b3_obs``) with newer data.

Refitting is not a new model: it fits the same configuration (columns, hyperparameters, formulation S4_s3, outbreak
rule) again with the data available at a later cutoff, and recalibrates it as the freeze did. It produces a package
folder that ``serving.predictors.v4_b3_live`` can serve (``paquete_dir`` option), without touching the Release copy.

What it computes, for one seed (17, the one the service serves):

- the booster fitted with every origin whose three targets closed at the cutoff, and its NB2 dispersion;
- the out-of-sample predictions of the seasons after the archived ones (each season is fitted at its first origin,
  as the protocol of ``docs/modeling/protocolo_v3.md`` does), appended to the archived history;
- Platt and the count mixture per horizon, fitted with the history whose label closed by the cutoff;
- the origin vectors, the observations and the demo out-of-sample file the package builder reads.

The package carries its own history (``historial_oos_b3_s17.csv.gz``) so the next refit continues from it. It also
carries the SHAP importances of its booster (``importancias_b3_s17.json``), computed with the matrix it was fitted
with, so that publishing never has to rebuild that matrix. Nothing is written to ``data/``; the output folder must be
new. See ``docs/modeling/reentrenamiento.md``.

The frozen V4 of the Release has no such file: ``frozen_training_matrix`` rebuilds its matrix from the Release inputs
(the same ``build_origins`` and selection as a fit), without fitting, and refuses to go on unless the rows, the
columns and the NB2 dispersions it implies equal the ones the package recorded.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import numpy as np
import pandas as pd
from xgboost import XGBRegressor

from denguekay.config.paths import (
    MODELS, OPERATIONAL_CHIRPS, OPERATIONAL_ENSO, OPERATIONAL_ERA5_LAND, OPERATIONAL_SALA, ROOT, V4_CHIRPS, V4_ENSO,
    V4_ERA5_LAND, V4_FROZEN, V4_GEOGRAPHY, V4_HISTORY, V4_INTEGRATED, V4_SALA,
)
from denguekay.data.loading import load_integrated
from denguekay.data.processing.district_locations import read_v4_era5
from denguekay.data.validation.integrated_expectations import coverage_path, load_case_coverage
from denguekay.data.validation.v4_panel import validate_confirmed_panel
from denguekay.evaluation import protocol as pa
from denguekay.features.b3 import GEO, NINO, WEATHER
from denguekay.features.long_history import long_inputs
from denguekay.model import horizon_strategies as eh, probabilistic_output as sp
from denguekay.serving.artifacts import sha256_bytes
from denguekay.serving.predictors import v2_e3_s4 as v2, v3_l5a_d3 as v3

DAY = pd.Timedelta(days=1)
SEED = 17
FORMULATION = "S4_s3"
HORIZONS = (2, 3, 4)
ARM = "b3_obs"
FIRST_REFIT_SEASON = 2027      # the seasons up to 2026 are archived with the V4
REPLACED_BLOCK = "posterior_2026"   # the partial block of the archive (season 2027), regenerated here
HISTORY_FILE = "historial_oos_b3_s17.csv.gz"
IMPORTANCES_FILE = f"importancias_{ARM}_s{SEED}.json"
DISPERSION_RTOL = 1e-6   # the alphas of the freeze were computed on another machine; 1e-9 is what was observed
ARCHIVE_HISTORY = MODELS / "experimentos" / "mejora_modelo" / "v3_confirmados" / "controles_espaciales" / "b3_obs_s17"
W_GRID = np.round(np.linspace(0, 1, 101), 2)
CLIMATE_SOURCE = {"hum_rel_media": "era", "precip_total_mm": "rain", "temp_media": "era"}
HISTORY_COLUMNS = ["bloque", "horizonte", "ubigeo", "anio", "semana", "semana_inicio", "origen_cierre", "casos_Dengue",
                   "brote", "umbral_brote_casos", "persistencia", "estacional", "mu_modelo", "probabilidad_cruda",
                   "probabilidad_calibrada", "conteo_publicado", "w_mezcla", "corte"]


# --- inputs ------------------------------------------------------------------------------------

def read(path, dates=()):
    return pd.read_csv(path, dtype={"ubigeo": str}, parse_dates=list(dates), float_precision="round_trip")


def window_means(frame, value, last_origin):
    """Per district and origin week: mean of the weeks o-6 ... o-2 (five weeks ending two before the origin week)."""
    data = frame[["ubigeo", "semana_inicio", value]].copy()
    data["semana_inicio"] = pd.to_datetime(data.semana_inicio)
    grid = pd.date_range(data.semana_inicio.min(), pd.Timestamp(last_origin), freq="W-SUN")
    full = pd.MultiIndex.from_product([sorted(data.ubigeo.unique()), grid], names=["ubigeo", "semana_inicio"])
    series = data.set_index(["ubigeo", "semana_inicio"])[value].reindex(full)
    means = series.groupby(level="ubigeo").transform(lambda s: s.rolling(5, min_periods=5).mean())
    shifted = means.groupby(level="ubigeo").shift(2)
    column = WEATHER[value][1]
    return shifted.rename(column).reset_index().rename(columns={"semana_inicio": "semana_origen"})


def nino_at_origins(origins, enso):
    """Mean of the last three consecutive Niño 1+2 months available at each origin close."""
    months = enso.sort_values(["anio", "mes"]).reset_index(drop=True)
    index = pd.PeriodIndex.from_fields(year=months.anio, month=months.mes, freq="M")
    if len(index) > 1 and not (index[1:] - index[:-1] == index.freq).all():
        raise ValueError("Meses faltantes o desordenados en el índice del Niño")
    available = pd.to_datetime(months.fecha_disponible)
    if not available.is_monotonic_increasing:
        raise ValueError("fecha_disponible del Niño no crece con los meses")
    features = pd.DataFrame({"fecha_disponible": available, NINO: months.nino12_anom.rolling(3).mean()})
    keys = pd.DataFrame({"origen_cierre": pd.to_datetime(origins.origen_cierre).to_numpy(),
                         "_pos": np.arange(len(origins))}).sort_values("origen_cierre")
    joined = pd.merge_asof(keys, features, left_on="origen_cierre", right_on="fecha_disponible", direction="backward")
    return joined.sort_values("_pos")[NINO].to_numpy()


def build_origins(inputs, geography, rain, era, enso):
    """The training origins with the geography and the observed B3 climate columns of the frozen model."""
    origins = inputs["origenes"].copy()
    origins["ubigeo"] = origins.ubigeo.astype(str)
    origins["semana_origen"] = pd.to_datetime(origins.origen_cierre) - 6 * DAY
    last = origins.semana_origen.max()
    origins = origins.merge(geography[["ubigeo", *GEO]], on="ubigeo", validate="many_to_one")
    for value, source in CLIMATE_SOURCE.items():
        fields = window_means(rain if source == "rain" else era, value, last)
        origins = origins.merge(fields, on=["ubigeo", "semana_origen"], how="left", validate="many_to_one")
    origins[NINO] = nino_at_origins(origins, enso)
    return origins.reset_index(drop=True)


class Training(SimpleNamespace):
    """What a fit reads: the long inputs, the training origins and the source tables behind their climate columns."""


def load_origins(*, panel_path, history_path, sala_path, era_path, chirps_path, enso_path, geography):
    """Read the sources of a fit and build its training origins, validating the confirmed panel first."""
    panel = load_integrated(panel_path)
    validate_confirmed_panel(panel, load_case_coverage(coverage_path(panel_path)))
    sala = read(sala_path)
    if not sala.tipo_dx.eq("C").all():
        raise ValueError("La Sala debe ser la serie de casos confirmados")
    inputs = long_inputs(panel, era_path, sala=sala, history_path=history_path, include_d3=False)
    geo = read(geography)
    rain = read(chirps_path, ("semana_inicio", "fecha_disponible"))
    era = read_v4_era5(era_path)
    enso = pd.read_csv(enso_path, parse_dates=["fecha_disponible"])
    return Training(inputs=inputs, origins=build_origins(inputs, geo, rain, era, enso), geo=geo, rain=rain, era=era,
                    enso=enso)


def training_rows(origins, cutoff):
    """The origins a fit at ``cutoff`` trains on (the three targets closed by it), without fitting."""
    return v2.service_rows(SimpleNamespace(origins=origins), cutoff)


# --- importances of the booster -------------------------------------------------------------------

def importances_payload(regressor, train, columns):
    """Mean |SHAP| of each output (horizon) of ``regressor`` over ``train``: the file a package keeps."""
    rows = v2.importances(regressor, train[list(columns)])
    return {"tipo": v2.IMPORTANCE, "filas": int(len(train)), "columnas": list(columns),
            "inicio": str(pd.to_datetime(train.semana_inicio).min().date()),
            "importancias": {str(h): rows[h] for h in HORIZONS}}


def write_importances(folder, regressor, train, columns):
    """Save the importances next to the package files (before the manifest hashes them)."""
    payload = importances_payload(regressor, train, columns)
    (Path(folder) / IMPORTANCES_FILE).write_text(
        json.dumps(payload, indent=1, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    return payload


def read_importances(folder, config):
    """The importances a package carries, checked against its own record (rows and columns of the fit)."""
    payload = json.loads((Path(folder) / IMPORTANCES_FILE).read_text(encoding="utf-8"))
    record = config["modelos"][f"{ARM}_s{config['semilla_demo']}"]
    columns = config["columnas"][ARM]
    if (payload.get("tipo") != v2.IMPORTANCE or payload.get("columnas") != columns
            or payload.get("filas") != record["filas_entrenamiento"] or set(payload.get("importancias", {})) != {"2", "3", "4"}):
        raise ValueError("Las importancias del paquete no corresponden a su ajuste")
    for rows in payload["importancias"].values():
        if sorted(row["variable"] for row in rows) != sorted(columns) or [row["rango"] for row in rows] != list(
                range(1, len(columns) + 1)):
            raise ValueError("Las importancias del paquete no cubren las variables del modelo")
    return {**payload, "importancias": {int(h): rows for h, rows in payload["importancias"].items()}}


# --- the matrix of the frozen V4 --------------------------------------------------------------------------

def frozen_sources():
    """Inputs of the Release copy, the ones the freeze read (never the weekly ``operativo`` files)."""
    return dict(panel_path=V4_INTEGRATED, history_path=V4_HISTORY, sala_path=V4_SALA, era_path=V4_ERA5_LAND,
                chirps_path=V4_CHIRPS, enso_path=V4_ENSO, geography=V4_GEOGRAPHY)


def check_frozen_sources(config, sources):
    """Every input is the file the package declares in ``fuentes`` (by repo path, file name or ``geografia``)."""
    declared = config["fuentes"]
    files = {**{key: Path(path) for key, path in sources.items() if key != "geography"},
             "coverage": coverage_path(sources["panel_path"])}
    expected = {name: declared.get(path.relative_to(ROOT).as_posix()) or declared.get(path.name)
                for name, path in files.items()}
    expected["geography"] = declared.get("geografia")
    files["geography"] = Path(sources["geography"])
    for name, path in files.items():
        if not path.is_file():
            raise ValueError(f"Falta el insumo {path.name} de la V4 congelada; en un clon limpio: python -m "
                             "denguekay.data.ingestion.release_bundles --version v4 --solo datos_v4.zip modelo_v4.zip")
        if expected[name] is None or sha256_file(path) != expected[name]:
            raise ValueError(f"El insumo {path.name} difiere del que declara el paquete V4")


def frozen_training_matrix(config, regressor):
    """The matrix the frozen booster was fitted with, rebuilt from the Release inputs and verified.

    It stops (``ValueError``) unless the rows equal ``filas_entrenamiento``, the columns of ``columnas.b3_obs`` exist
    and are finite, the last label closes at the recorded date and the NB2 dispersions of the frozen booster on this
    matrix equal the package's ``alphas`` (``DISPERSION_RTOL``): the same booster over the same matrix."""
    record = config["modelos"][f"{ARM}_s{config['semilla_demo']}"]
    columns = config["columnas"][ARM]
    sources = frozen_sources()
    check_frozen_sources(config, sources)
    origins = load_origins(**sources).origins
    cutoff = pd.Timestamp(config["corte"])
    train = training_rows(origins, cutoff)
    if len(train) != record["filas_entrenamiento"]:
        raise ValueError(f"La matriz reconstruida tiene {len(train)} filas y el paquete registra "
                         f"{record['filas_entrenamiento']}")
    if (any(column not in train for column in columns) or not np.isfinite(train[columns].to_numpy(float)).all()
            or regressor.get_booster().feature_names != columns):
        raise ValueError("Las columnas de la matriz reconstruida no son las de columnas.b3_obs")
    if str((train.semana_inicio_h4.max() + 6 * DAY).date()) != record["ultimo_cierre_h4"]:
        raise ValueError("El último cierre de la matriz reconstruida no es el del paquete")
    kind = sp.FORMULATIONS[FORMULATION]["conteo"]
    margin = sp.e3_margin(origins, FORMULATION)[train.index.to_numpy()]
    mu = sp.predict_count(regressor, train[columns], kind, margin)
    alphas = [sp.negative_binomial_dispersion(mu[:, j], train[f"casos_Dengue_h{h}"].to_numpy(float))
              for j, h in enumerate(HORIZONS)]
    if not np.allclose(alphas, record["alphas"], rtol=DISPERSION_RTOL, atol=0):
        raise ValueError("Las dispersiones del booster sobre la matriz reconstruida no son las del paquete")
    return train


# --- out-of-sample blocks and calibration --------------------------------------------------------

def fit_w(mu, persistence, observed):
    """w of the grid with the lowest MAE of w·mu + (1 - w)·persistence; ties go to the largest w."""
    mae = np.array([np.abs(w * mu + (1 - w) * persistence - observed).mean() for w in W_GRID])
    best = np.flatnonzero(np.isclose(mae, mae.min(), rtol=0, atol=1e-12))
    return float(W_GRID[best.max()])


def mix_chronologically(pred):
    """Published count of every block: w fitted with the earlier blocks whose label closed by its first origin."""
    data = pred.copy()
    mixed = data.casos_predichos.to_numpy(float).copy()
    weight = np.ones(len(data))
    for h, by_h in data.groupby("horizonte"):
        onsets = by_h.groupby("bloque").semana_inicio.min().sort_values()
        for block, start in onsets.items():
            idx = by_h.index[by_h.bloque.eq(block)]
            cutoff = pa.block_cutoff(by_h.loc[idx])
            prev = by_h[by_h.bloque.map(onsets).lt(start)]
            prev = prev[(prev.semana_inicio + 6 * DAY).le(cutoff)]
            w = (fit_w(prev.casos_predichos.to_numpy(float), prev.persistencia.to_numpy(float),
                       prev.casos_Dengue.to_numpy(float)) if len(prev) else 1.0)
            pos = data.index.get_indexer(idx)
            mixed[pos] = w * data.casos_predichos.to_numpy(float)[pos] + (1 - w) * data.persistencia.to_numpy(float)[pos]
            weight[pos] = w
    return data.assign(conteo_publicado=mixed, w_mezcla=weight)


def block_predictions(inputs, origins, columns, hyperparameters, seed, cutoff):
    """Out-of-sample predictions of the seasons after the archived ones whose first origin closed by ``cutoff``."""
    args = sp.e3_parameters(hyperparameters)
    kind = sp.FORMULATIONS[FORMULATION]["conteo"]
    margin = sp.e3_margin(origins, FORMULATION)
    parts = []
    for season in range(FIRST_REFIT_SEASON, cutoff.year + 3):
        try:
            tests, block_cut = eh._common_cutoffs(inputs["matrices"], "temporada", season)
        except ValueError:
            break
        if block_cut > cutoff or any(t.empty for t in tests.values()):
            break
        fit = sp.fit_e3(origins, block_cut, seed, FORMULATION, columns, [], args, margin)
        first = min(t.origen_cierre.min() for t in tests.values())
        last = max(t.origen_cierre.max() for t in tests.values())
        selected = np.flatnonzero(origins.origen_cierre.between(first, last))
        targets = origins.iloc[selected][["ubigeo", "origen_cierre"]].copy()
        means = sp.predict_count(fit.regressor, origins.iloc[selected][columns], kind, margin[selected])
        for j, h in enumerate(HORIZONS):
            test = tests[h].assign(ubigeo=tests[h].ubigeo.astype(str)).merge(
                targets.assign(mu=means[:, j]), on=["ubigeo", "origen_cierre"], how="left", validate="one_to_one")
            if test.mu.isna().any():
                raise ValueError(f"Origen faltante en la temporada {season}, h{h}")
            p = sp.negative_binomial_probability(test.mu, fit.alphas[j], test.umbral_brote_casos)
            parts.append(eh._output(test, f"temporada_{season}", test.mu, p).assign(corte=block_cut))
    columns_out = [*eh.OUTPUT, "casos_predichos", "probabilidad_brote", "corte"]
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=columns_out)


def read_history(path):
    """The archived out-of-sample history of seed 17 (the Release file) or the one a previous refit saved."""
    path = Path(path)
    if path.is_dir():   # the archive folder of the Release: predictions and the cutoff of each block's fit
        table = read(path / "predicciones.csv.gz", ("semana_inicio", "origen_cierre"))
        fits = read(path / "ajustes.csv", ("corte",))
        table = table.merge(fits[["bloque", "corte"]], on="bloque", validate="many_to_one")
    else:
        table = read(path, ("semana_inicio", "origen_cierre", "corte"))
    if (table.empty or table.corte.gt(table.origen_cierre).any()
            or table.duplicated(["ubigeo", "semana_inicio", "horizonte"]).any()):
        raise ValueError("Historial fuera de muestra inválido")
    return table


def extend_history(history, new):
    """The history without the partial block, plus the new blocks with their calibrated probability and count."""
    base = history[~history.bloque.eq(REPLACED_BLOCK)].copy()
    if new.empty:
        return base[HISTORY_COLUMNS].reset_index(drop=True)
    old = base.rename(columns={"mu_modelo": "casos_predichos", "probabilidad_cruda": "probabilidad_brote"})
    combined = pd.concat([old[[c for c in new.columns if c in old.columns]], new], ignore_index=True)
    combined["ubigeo"] = combined.ubigeo.astype(str)
    calibrated, _ = pa.calibrate_chronologically(combined.drop(columns="corte"))
    mixed = mix_chronologically(combined)
    scored = combined.assign(probabilidad_calibrada=calibrated.probabilidad_calibrada.to_numpy(),
                             conteo_publicado=mixed.conteo_publicado.to_numpy(), w_mezcla=mixed.w_mezcla.to_numpy())
    scored = scored.rename(columns={"casos_predichos": "mu_modelo", "probabilidad_brote": "probabilidad_cruda"})
    fresh = scored[scored.bloque.isin(new.bloque.unique())]
    return pd.concat([base[HISTORY_COLUMNS], fresh[HISTORY_COLUMNS]], ignore_index=True)


def calibrate(data, p):
    fit = pa.fit_platt(p, data.brote.to_numpy(int))
    return {"a": float(fit.coef_[0, 0]), "b": float(fit.intercept_[0]), "filas": len(data),
            "ultimo_cierre": str((data.semana_inicio.max() + 6 * DAY).date())}


# --- package -------------------------------------------------------------------------------------------

def sha256_file(path):
    return sha256_bytes(Path(path).read_bytes())


def write_csv_gz(frame, path, **options):
    frame.to_csv(path, index=False, compression={"method": "gzip", "mtime": 0}, **options)


def refit(output, *, base, cutoff=None, geography=V4_GEOGRAPHY, history=None, panel_path=V4_INTEGRATED,
          history_path=V4_HISTORY, sala_path=OPERATIONAL_SALA, era_path=OPERATIONAL_ERA5_LAND,
          chirps_path=OPERATIONAL_CHIRPS, enso_path=OPERATIONAL_ENSO, seed=SEED, created=None):
    """Fit the frozen configuration of ``base`` (a package folder) with the data up to ``cutoff`` into ``output``.

    ``cutoff`` (a Saturday) defaults to the close of the last validated week; it can be earlier, never later."""
    output = Path(output)
    config = json.loads((Path(base) / "paquete.json").read_text(encoding="utf-8"))
    columns = config["columnas"][ARM]
    hyperparameters = config["hiperparametros"]
    loaded = load_origins(panel_path=panel_path, history_path=history_path, sala_path=sala_path, era_path=era_path,
                          chirps_path=chirps_path, enso_path=enso_path, geography=geography)
    inputs, origins, geo, rain, era, enso = (loaded.inputs, loaded.origins, loaded.geo, loaded.rain, loaded.era,
                                             loaded.enso)
    last_closed = pd.Timestamp(inputs["ultima_semana"]) + 6 * DAY
    cutoff = last_closed if cutoff is None else pd.Timestamp(cutoff)
    if cutoff > last_closed or cutoff.dayofweek != 5:
        raise ValueError(f"El corte debe ser un sábado no posterior al último cierre validado ({last_closed.date()})")
    train = origins[(origins.semana_inicio_h4 + 6 * DAY).le(cutoff)]
    if train.empty or not np.isfinite(train[columns].to_numpy(float)).all():
        raise ValueError("Variables de entrenamiento incompletas")

    # Current origin: the vectors the demo snapshot of the package carries.
    origin_start = cutoff - 6 * DAY
    cases = inputs["casos"].loc[inputs["casos"].semana_inicio.le(origin_start)].copy()
    now, reasons = v2._base_6(cases, SimpleNamespace(fecha_fin=cutoff.date()))
    if reasons:
        raise ValueError(f"Historiales incompletos en el origen: {reasons}")
    current = now.join(v2._b3(cases, origin_start)).join(geo.set_index("ubigeo")[list(GEO)])
    for value, source in CLIMATE_SOURCE.items():
        fields = window_means(rain if source == "rain" else era, value, origin_start)
        current = current.join(fields[fields.semana_origen.eq(origin_start)].set_index("ubigeo")[WEATHER[value][1]])
    current[NINO] = nino_at_origins(pd.DataFrame({"origen_cierre": [cutoff]}), enso)[0]
    if len(current) != 65 or not np.isfinite(current[columns].to_numpy(float)).all():
        raise ValueError("Vector de origen incompleto")
    rule = config["regla_brote"]
    thresholds = v3.target_thresholds(cases, origin_start, list(current.index), rule)
    snapshot = current[columns].join(thresholds.rename(columns={h: f"umbral_h{h}" for h in HORIZONS}))

    # Fit, history and calibration.
    margin = sp.e3_margin(origins, FORMULATION)
    fit = sp.fit_e3(origins, cutoff, seed, FORMULATION, columns, [], sp.e3_parameters(hyperparameters), margin)
    if fit.train.semana_inicio_h4.max() + 6 * DAY > cutoff:
        raise ValueError("El entrenamiento incluye etiquetas posteriores al corte")
    history_source = Path(history) if history else (
        Path(base) / HISTORY_FILE if (Path(base) / HISTORY_FILE).is_file() else ARCHIVE_HISTORY)
    prior = read_history(history_source)
    new = block_predictions(inputs, origins, columns, hyperparameters, seed, cutoff)
    table = extend_history(prior, new)
    previous = table[(table.semana_inicio + 6 * DAY).le(cutoff)]
    if previous.empty:
        raise ValueError("No hay historial fuera de muestra cerrado al corte")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()   # a new folder: the previous package is never replaced
    snapshot.to_csv(output / "origen.csv", float_format="%.17g")
    observations = cases.merge(inputs["etiquetas"][["ubigeo", "semana_inicio", "brote", "umbral_brote_casos"]],
                               on=["ubigeo", "semana_inicio"], how="left", validate="one_to_one")
    write_csv_gz(observations.loc[observations.anio.ge(2017)], output / "observaciones.csv.gz")
    model_file = output / f"{ARM}_s{seed}.ubj"
    fit.regressor.save_model(model_file)
    restored = XGBRegressor()
    restored.load_model(model_file)
    kind = sp.FORMULATIONS[FORMULATION]["conteo"]
    snap_margin = sp.e3_margin(snapshot.reset_index(), FORMULATION)
    np.testing.assert_array_equal(sp.predict_count(fit.regressor, snapshot[columns], kind, snap_margin),
                                  sp.predict_count(restored, snapshot[columns], kind, snap_margin))
    write_importances(output, restored, fit.train, columns)
    write_csv_gz(table, output / HISTORY_FILE)
    write_csv_gz(previous[["ubigeo", "semana_inicio", "horizonte", "bloque", "origen_cierre", "probabilidad_calibrada",
                           "conteo_publicado"]], output / f"oos_b3_s{seed}.csv.gz")

    per_horizon = {}
    for h, rows in previous.groupby("horizonte"):
        per_horizon[str(h)] = {"platt": calibrate(rows, rows.probabilidad_cruda),
                               "peso_modelo": fit_w(rows.mu_modelo.to_numpy(), rows.persistencia.to_numpy(),
                                                    rows.casos_Dengue.to_numpy())}
    persistence = {}
    for h, rows in previous.groupby("horizonte"):
        odds = (rows.persistencia + 0.5) / (sp.count_threshold(rows.umbral_brote_casos) + 0.5)
        persistence[str(h)] = calibrate(rows, odds / (1 + odds))
    sources = {path.relative_to(ROOT).as_posix(): sha256_file(path)
               for path in (panel_path, coverage_path(panel_path), history_path, sala_path, era_path, chirps_path,
                            enso_path, Path(geography)) if Path(path).is_file() and Path(path).is_relative_to(ROOT)}
    new_config = {
        "version": config["version"], "corte": str(cutoff.date()),
        "congelado_utc": created or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tipo": "reentrenamiento", "paquete_base": Path(base).name,
        "formulacion": config["formulacion"], "columnas": {ARM: columns}, "hiperparametros": hyperparameters,
        "semillas": [seed], "semilla_demo": seed, "corte_alerta": config["corte_alerta"], "regla_brote": rule,
        "horizontes": list(HORIZONS), "validaciones": config.get("validaciones", {}),
        "fuentes": {**sources, "geografia": sha256_file(geography)},
        "commit": _commit(),
        "modelos": {f"{ARM}_s{seed}": {
            "brazo": ARM, "semilla": seed, "sha256": sha256_file(model_file), "alphas": fit.alphas,
            "filas_entrenamiento": len(fit.train), "ultimo_cierre_h4": str((fit.train.semana_inicio_h4.max() + 6 * DAY).date()),
            "archivo_calibracion_sha256": sha256_file(output / HISTORY_FILE), "por_horizonte": per_horizon}},
        "persistencia_prob": persistence,
    }
    new_config["archivos"] = {p.name: sha256_file(p) for p in sorted(output.iterdir())}
    (output / "paquete.json").write_text(json.dumps(new_config, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                                         encoding="utf-8")
    return new_config


def _commit():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
                                       stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--salida", type=Path, required=True, help="Carpeta nueva del paquete (no se reemplaza nada)")
    parser.add_argument("--corte", default=None, help="Sábado de corte; por defecto, el último cierre validado")
    parser.add_argument("--base", type=Path, default=V4_FROZEN, help="Paquete cuya configuración se reajusta")
    parser.add_argument("--historial", type=Path, default=None, help="Historial fuera de muestra (por defecto el del paquete base o el archivo del Release)")
    args = parser.parse_args(argv)
    config = refit(args.salida, base=args.base, cutoff=args.corte, history=args.historial)
    record = config["modelos"][f"{ARM}_s{SEED}"]
    print(json.dumps({"salida": str(args.salida), "corte": config["corte"], "filas_entrenamiento": record["filas_entrenamiento"],
                      "alphas": record["alphas"], "por_horizonte": record["por_horizonte"]}, ensure_ascii=False, indent=2))
    folder = Path(args.salida).resolve().relative_to(ROOT).as_posix() if Path(args.salida).resolve().is_relative_to(ROOT) else str(args.salida)
    print(f"\nPara servirlo: en configs/config.yaml, serving.paquete.opciones.paquete_dir: {folder}; luego "
          "python -m denguekay.serving.publish --seleccionar-experimental")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
