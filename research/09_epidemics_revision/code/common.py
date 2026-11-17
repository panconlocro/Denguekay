"""Shared code of study 09 (re-analysis for the Epidemics revision).

Inputs are checked against the sources recorded in the V4 manifest. Origins, arms and fits reuse the functions of
study 08 (``run_spatial_controls``) without modifying them, so the fitted arms are the paper's arms. Fits are
cached under ``models/experimentos/revision_epidemics`` with a fingerprint; the notebooks only read them.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd
import requests

from denguekay.config.paths import PAPER_BUNDLE, ROOT

STUDY = ROOT / "research" / "09_epidemics_revision"
STUDY08 = ROOT / "research" / "08_v3_confirmed_cases"
sys.path.insert(0, str(STUDY08 / "code"))

import run_spatial_controls as spatial  # noqa: E402  (also loads run_experiment and the study-06 code)

archive = spatial.archive
cl = spatial.cl
OUTPUT = ROOT / "models" / "experimentos" / "revision_epidemics"
ARMS_DIR = OUTPUT / "brazos"
GEOGRAPHY = OUTPUT / "insumos" / "geografia_distritos.csv"
PROTOCOL = STUDY / "protocolo.md"
MANIFEST = STUDY08 / "manifiesto_b3_v4.json"
SEEDS = tuple(spatial.pa.SEEDS)
DECISION_SEASONS = tuple(spatial.DECIDING)
SEASONS = tuple(range(2009, 2027))
HORIZONS = (2, 3, 4)
DAY = pd.Timedelta(days=1)
ELEVATION_URL = "https://api.open-meteo.com/v1/elevation"
XGB_ENV = {"DENGUEKAY_XGB_DEVICE": "cpu", "DENGUEKAY_XGB_NJOBS": "2", "OMP_NUM_THREADS": "2",
           "OPENBLAS_NUM_THREADS": "1", "VECLIB_MAXIMUM_THREADS": "1"}


def sha256(path: Path) -> str:
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def source_path(key: str) -> Path:
    return ROOT / key if key.startswith("data/") else ROOT / "data" / "silver" / key


def check_sources() -> pd.DataFrame:
    """SHA-256 of every input recorded in the V4 manifest; raises if any differs."""
    rows = []
    for key, expected in manifest()["fuentes"].items():
        path = GEOGRAPHY if key == "geografia" else source_path(key)
        found = sha256(path) if path.exists() else None
        rows.append({"fuente": key, "archivo": str(path.relative_to(ROOT)), "sha256_manifiesto": expected[:12],
                     "sha256_local": found[:12] if found else None, "coincide": found == expected})
    table = pd.DataFrame(rows)
    data = table[table.fuente.ne("geografia")]
    if not data.coincide.all():
        raise ValueError(f"Inputs differ from the V4 manifest: {data.loc[~data.coincide, 'fuente'].tolist()}")
    return table


def build_geography(panel: pd.DataFrame, overwrite: bool = False) -> dict:
    """District latitude, longitude and Copernicus GLO-90 elevation (Open-Meteo elevation API)."""
    if GEOGRAPHY.exists() and not overwrite:
        return {"archivo": str(GEOGRAPHY), "sha256": sha256(GEOGRAPHY), "nuevo": False}
    keys = (panel[["ubigeo", "lat", "lon"]].assign(ubigeo=lambda d: d.ubigeo.astype(str))
            .drop_duplicates().sort_values("ubigeo").reset_index(drop=True))
    if len(keys) != 65 or keys.ubigeo.duplicated().any():
        raise ValueError("Expected one coordinate per district")
    response = requests.get(ELEVATION_URL, timeout=60, params={
        "latitude": ",".join(map(str, keys.lat)), "longitude": ",".join(map(str, keys.lon))})
    response.raise_for_status()
    elevation = np.asarray(response.json()["elevation"], dtype=float)
    if len(elevation) != len(keys) or not np.isfinite(elevation).all():
        raise ValueError("Incomplete elevation response")
    GEOGRAPHY.parent.mkdir(parents=True, exist_ok=True)
    # Column order of the archived file, whose SHA-256 the V4 manifest records.
    geo = keys.assign(elevacion_dem90=elevation)[["lat", "lon", "ubigeo", "elevacion_dem90"]]
    geo.to_csv(GEOGRAPHY, index=False)
    return {"archivo": str(GEOGRAPHY), "sha256": sha256(GEOGRAPHY), "nuevo": True}


def load_inputs(validate: bool = True) -> tuple[dict, dict | None]:
    """The paper's long inputs (study 08 ``training_data`` without its archived snapshot)."""
    check_sources()
    quality = archive.validate_modeling_inputs(silver_path=archive.PANEL) if validate else None
    archive.audit_handoff(silver_path=archive.PANEL, history_path=archive.HISTORY)
    sala = pd.read_csv(archive.SALA, dtype={"ubigeo": "string"})
    if not sala.tipo_dx.eq("C").all():
        raise ValueError("Sala rows without a confirmed diagnosis")
    inputs = archive.long_inputs(archive.load_integrated(archive.PANEL), archive.ERA5, sala=sala,
                                 history_path=archive.HISTORY)
    return inputs, quality


def weather_sources() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Weekly CHIRPS, weekly ERA5-Land (availability = week start + 13 days) and monthly Niño 1+2."""
    rain = pd.read_csv(spatial.SILVER_CHIRPS_PRECIP, dtype={"ubigeo": str},
                       parse_dates=["semana_inicio", "fecha_disponible"])
    panel = archive.load_integrated(archive.PANEL)
    era = archive.original.era5_2026(panel).assign(fecha_disponible=lambda d: d.semana_inicio + 13 * DAY)
    return rain, era, archive.original.p4.read_enso()


def weekly_fields_by_source(rain, era, rain_lag: int, era_lag: int, enso=None, strict: bool = True):
    """``run_spatial_controls.weekly_fields`` with one lag per source (equal to it when both lags agree).

    A lag of 0 reproduces the historical alignment, which accepts values published up to 14 days after the
    origin close; any other lag requires every value to be published by the origin close.
    """
    pbr = archive.original.pbr
    slots = []
    for frame, value, column, lag in (
        (rain, "precip_total_mm", pbr.COLUMN, rain_lag), (era, "temp_media", spatial.TEMP, era_lag),
        (era, "hum_rel_media", archive.original.pb.COLUMN, era_lag),
    ):
        means = pbr.rain_by_origin_week(frame, extra_lag=lag, value=value)
        present = means.R.notna()
        allowed = means.semana_origen + (6 if lag else 20) * DAY
        if strict and means.loc[present, "publicada_max"].gt(allowed[present]).any():
            raise ValueError(f"Value published after the cutoff for {column} (lag {lag})")
        slots.append(means.rename(columns={"R": column}).set_index(["ubigeo", "semana_origen"])[column])
    limits = {name: (a + era_lag, b + era_lag) for name, (a, b) in cl.D3_WINDOWS.items()}
    d3 = cl.weather_windows(era, windows=limits).set_index(["ubigeo", "semana_origen"])
    fields = pd.concat([*slots, d3], axis=1).reset_index()
    enso = archive.original.p4.read_enso() if enso is None else enso
    dates = fields[["semana_origen"]].drop_duplicates().assign(origen_cierre=lambda d: d.semana_origen + 6 * DAY)
    nino = archive.original.p4.enso_at_origins(dates, enso)
    if not archive.original.p4.guard_g21(nino)["pasa"]:
        raise ValueError("Niño value published after the origin")
    return fields.merge(nino[["semana_origen", archive.original.b3.NINO_COLUMN]], on="semana_origen",
                        validate="many_to_one")


def prepare(inputs: dict):
    """Origins and arms of the spatial controls plus the lag-1 arm (protocol D3) and ``b3_hist_geo``."""
    origins, arms, hp, schedules = spatial.prepare(inputs, GEOGRAPHY)
    rain, era, _ = weather_sources()
    lag1 = weekly_fields_by_source(rain, era, rain_lag=2, era_lag=1)
    values = spatial.weather_at(lag1, origins, origins.semana_origen)
    for column in spatial.B3:
        origins[f"{column}_lag1"] = values[column].to_numpy()
    arms["b3_lag1"] = [*arms["historia_geo"], *(f"{c}_lag1" for c in spatial.B3)]
    arms["b3_hist_geo"] = [*arms["historia_geo"], *(f"{c}_hist" for c in spatial.B3)]
    return origins, arms, hp, schedules


def fingerprint(arm: str, columns: list[str], hp: dict, extra: dict | None = None) -> str:
    # Only the code that determines the predictions: study 08's fitting module and this study's feature code.
    code = {"run_spatial_controls.py": sha256(Path(spatial.__file__)),
            **{f.__name__: hashlib.sha256(inspect.getsource(f).encode()).hexdigest()
               for f in (weekly_fields_by_source, prepare, fit_arm)}}
    info = {"brazo": arm, "columnas": columns, "parametros": hp, "protocolo": sha256(PROTOCOL), "codigo": code,
            "geografia": sha256(GEOGRAPHY), "fuentes": manifest()["fuentes"],
            "entorno": archive.device.xgboost_settings(), **(extra or {})}
    return hashlib.sha256(json.dumps(info, sort_keys=True, default=str).encode()).hexdigest()


def fit_arm(inputs, origins, arm, columns, hp, seed, out_dir: Path = ARMS_DIR, extra: dict | None = None) -> Path:
    """Fit one arm and seed on the 20 blocks (cached); same checks as ``run_spatial_controls.save_fit``."""
    print_ = f"{arm}_s{seed}"
    dest = out_dir / print_
    expected = fingerprint(arm, columns, hp, extra)
    if (dest / "control.json").exists():
        if json.loads((dest / "control.json").read_text())["huella"] != expected:
            raise ValueError(f"Cached fit from another configuration: {dest}")
        return dest
    pred, fits = spatial.predict(inputs, origins, spatial.BLOCK_LIST, columns, hp, seed,
                                 anomaly=(arm == "b3_anomalia"))
    table = archive.closure.full_table(pred, fits, arm, seed)
    guard = archive.closure.check_table(table)
    if (table.duplicated(archive.closure.KEY).any() or guard["alpha_nulos"] or guard["calibrada_sin_platt"]
            or guard["platt_diferencia_maxima"] > 1e-12 or guard["conteo_diferencia_maxima"] > 1e-12):
        raise ValueError(f"Invalid predictions in {print_}")
    return save_table(dest, table, fits, expected, guard)


def save_table(dest: Path, table: pd.DataFrame, fits: pd.DataFrame, expected: str, guard: dict | None = None) -> Path:
    """Write predictions, fits and control atomically (a half-written folder never looks complete)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=dest.parent) as temp:
        path = Path(temp)
        table.to_csv(path / "predicciones.csv.gz", index=False)
        fits.to_csv(path / "ajustes.csv", index=False)
        if "probabilidad_calibrada" in table and "variante" in table:
            archive.closure.block_metrics(table).to_csv(path / "metricas.csv", index=False)
        archive.write_json(path / "control.json", {"huella": expected, "filas": len(table), **(guard or {})})
        path.rename(dest)
    return dest


def fit_arms(inputs, origins, arms: dict, hp, names, seeds=SEEDS, workers: int = 6, out_dir: Path = ARMS_DIR,
             extra: dict | None = None) -> list[Path]:
    jobs = [(name, seed) for name in names for seed in seeds]
    done = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fit_arm, inputs, origins, name, arms[name], hp, seed, out_dir, extra): (name, seed)
                   for name, seed in jobs}
        for future in as_completed(futures):
            done.append(future.result())
            print(f"{len(done)}/{len(jobs)} {done[-1].name}", flush=True)
    return done


def read_arm(arm: str, seeds=SEEDS, columns=None, folder: Path = ARMS_DIR) -> pd.DataFrame:
    """Predictions of one arm for all seeds (long format)."""
    parts = []
    for seed in seeds:
        path = folder / f"{arm}_s{seed}" / "predicciones.csv.gz"
        dates = [d for d in ("semana_inicio", "origen_cierre") if columns is None or d in columns]
        frame = pd.read_csv(path, dtype={"ubigeo": str}, parse_dates=dates, usecols=columns)
        parts.append(frame if columns is None else frame[list(columns)])
    return pd.concat(parts, ignore_index=True)


def season_of(block: pd.Series) -> pd.Series:
    """``temporada_2015`` -> 2015; other blocks -> NaN."""
    return pd.to_numeric(block.str.extract(r"^temporada_(\d{4})$")[0], errors="coerce")


def baselines(support: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    """Probabilistic persistence, deterministic persistence and climatology (``run_statistical_benchmarks``)."""
    k = spatial.sp.count_threshold(support.umbral_brote_casos)
    ratio = (support.persistencia + 0.5) / (k + 0.5)
    calendar = spatial.mmwr_epi_week(support.semana_inicio)
    pred = support.assign(anio=calendar.anio_epi, semana=calendar.semana_epi, probabilidad_brote=ratio / (1 + ratio))
    prob, _ = spatial.pa.calibrate_chronologically(pred)
    out = support.copy()
    out["persistencia_prob"] = prob.probabilidad_calibrada.to_numpy()
    out["persistencia_det"] = out.persistencia.ge(k).astype(float)
    out["climatologia"] = archive.original.pdw.climatology(support, labels)
    return out


def corp(p, y) -> dict:
    """Brier score with its CORP decomposition (PAV recalibration): miscalibration, discrimination, uncertainty."""
    from sklearn.isotonic import IsotonicRegression

    p, y = np.asarray(p, float), np.asarray(y, float)
    fitted = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(p, y).predict(p)
    brier, recal, unc = np.mean((p - y) ** 2), np.mean((fitted - y) ** 2), np.mean((y - y.mean()) ** 2)
    return {"brier": brier, "mcb": brier - recal, "dsc": unc - recal, "unc": unc}


def environment() -> dict:
    import platform
    import sklearn
    import xgboost

    return {"python": platform.python_version(), "plataforma": platform.platform(), "xgboost": xgboost.__version__,
            "pandas": pd.__version__, "numpy": np.__version__, "sklearn": sklearn.__version__,
            "xgb_settings": archive.device.xgboost_settings(),
            "variables": {k: os.environ.get(k) for k in XGB_ENV}}
