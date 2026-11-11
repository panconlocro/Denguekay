"""Fit in Piura and score the fixed 2025 external transfer on matched support."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score
from xgboost import XGBRegressor

from denguekay.config.paths import SILVER_CHIRPS_PRECIP
from denguekay.data.processing.chirps_precipitation import pentad_publication
from denguekay.data.validation.gx_quality import validate_modeling_inputs
from denguekay.evaluation import protocol as pa
from denguekay.features import long_history as lh, onset_features
from denguekay.model import horizon_strategies as eh, probabilistic_output as sp

YEAR = 2025
LAST_WEEK = 38
DAY = pd.Timedelta(days=1)
FIRST_TARGET = lh.week_grid(YEAR, YEAR).semana_inicio.min()
LAST_TARGET = FIRST_TARGET + (LAST_WEEK - 1) * 7 * DAY
CUTOFF = FIRST_TARGET - 4 * 7 * DAY + 6 * DAY
HORIZONS = eh.STRATEGY_HORIZONS
ARMS = ("historia_geo", "b3_obs")
BLOCK = "externa_2025_se01_38"
DEPT = {"14": "Lambayeque", "24": "Tumbes"}
KEY = ["ubigeo", "semana_inicio", "horizonte"]


def digest(path: Path) -> str:
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def read(path: Path, dates: tuple[str, ...] = ()) -> pd.DataFrame:
    return pd.read_csv(path, dtype={"ubigeo": str}, parse_dates=list(dates), float_precision="round_trip")


def write_json(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def origin_table(cases: pd.DataFrame, matrices: dict[int, pd.DataFrame]) -> pd.DataFrame:
    empty = cases.iloc[:0][["ubigeo", "anio", "semana", "casos_Dengue"]]
    return onset_features.with_onset_columns(eh.origin_table(matrices[2]), cases, empty).reset_index(drop=True)


def add_weather(spatial, origins: pd.DataFrame, rain: pd.DataFrame, era: pd.DataFrame) -> pd.DataFrame:
    fields = spatial.weekly_fields(rain, era, lag=2)
    keys = origins[["ubigeo"]].assign(semana_origen=origins.origen_cierre - 6 * DAY)
    joined = keys.merge(fields, on=["ubigeo", "semana_origen"], how="left", validate="many_to_one")
    return origins.assign(**{f"{col}_obs": joined[col].to_numpy() for col in spatial.B3})


def calibrator(train: pd.DataFrame, probability: np.ndarray) -> dict:
    fit = pa.fit_platt(probability, train.brote.to_numpy())
    return {
        "a": float(fit.coef_[0, 0]), "b": float(fit.intercept_[0]),
        "filas": len(train), "positivos": int(train.brote.sum()),
        "ultimo_cierre": str((train.semana_inicio.max() + 6 * DAY).date()),
    }


def archive_rows(folder: Path) -> pd.DataFrame:
    table = read(folder / "predicciones.csv.gz", ("semana_inicio", "origen_cierre"))
    fits = read(folder / "ajustes.csv", ("corte",))
    table = table.loc[(table.semana_inicio + 6 * DAY).le(CUTOFF)].merge(
        fits[["bloque", "corte"]], on="bloque", validate="many_to_one"
    )
    if table.empty or table.corte.gt(table.origen_cierre).any() or table.duplicated(KEY).any():
        raise ValueError(f"Invalid Piura out-of-sample calibration archive: {folder}")
    return table


def raw_persistence(data: pd.DataFrame) -> np.ndarray:
    k = sp.count_threshold(data.umbral_brote_casos)
    odds = (data.persistencia.to_numpy() + 0.5) / (k + 0.5)
    return odds / (1 + odds)


def recalibration_rows(spatial, inputs, origins, history, columns, hp, seed):
    blocks = [block for block in spatial.BLOCK_LIST if block[0] in set(history.bloque)]
    raw, fits = spatial.predict(inputs, origins, blocks, columns, hp, seed)
    raw = raw.loc[(raw.semana_inicio + 6 * DAY).le(CUTOFF)].merge(
        fits[["bloque", "corte"]], on="bloque", validate="many_to_one"
    )
    matched = [*KEY, "bloque", "origen_cierre", "corte", "casos_Dengue", "brote", "persistencia"]
    order = ["horizonte", "semana_inicio", "ubigeo"]
    a = raw.sort_values(order).reset_index(drop=True)
    b = history.sort_values(order).reset_index(drop=True)
    pd.testing.assert_frame_equal(a[matched], b[matched], check_dtype=False)
    if a.corte.gt(a.origen_cierre).any():
        raise ValueError("Recalibration used labels unavailable in Piura")
    return a.rename(columns={"probabilidad_brote": "probabilidad_cruda", "casos_predichos": "mu_modelo"})


def fit_piura(archive, spatial, geography: Path, output: Path, *, without_latitude=False, workers=1) -> None:
    source = archive.OUTPUT / "controles_espaciales"
    report = json.loads((source / "resultados.json").read_text())
    if digest(geography) != report["geografia"]:
        raise ValueError("Piura geography differs from the paper archive")
    for relative, expected in report["epidemiologia"].items():
        if digest(archive.ROOT / relative) != expected:
            raise ValueError(f"Changed source: {relative}")
    for path in (SILVER_CHIRPS_PRECIP, spatial.SILVER_ENSO):
        if digest(path) != report["fuentes"][path.name]:
            raise ValueError(f"Changed weather source: {path.name}")
    with TemporaryDirectory() as tmp:
        quality = validate_modeling_inputs(silver_path=archive.PANEL, gx_directory=Path(tmp))
    sala = read(archive.SALA)
    if not sala.tipo_dx.eq("C").all():
        raise ValueError("Unexpected diagnosis in Piura surveillance")
    panel = archive.load_integrated(archive.PANEL)
    inputs = lh.long_inputs(panel, archive.ERA5, sala=sala, history_path=archive.HISTORY)
    geo = read(geography)
    origins = inputs["origenes"].merge(geo[["ubigeo", *spatial.GEO]], on="ubigeo", validate="many_to_one")
    rain = read(SILVER_CHIRPS_PRECIP, ("semana_inicio", "fecha_disponible"))
    era = archive.original.era5_2026(panel).assign(fecha_disponible=lambda d: d.semana_inicio + 13 * DAY)
    origins = add_weather(spatial, origins, rain, era)
    train = origins.loc[(origins.semana_inicio_h4 + 6 * DAY).le(CUTOFF)]
    original_columns = {arm: report["variantes"][arm] for arm in ARMS}
    columns = {
        arm: [col for col in original_columns[arm] if not (without_latitude and col == "lat")]
        for arm in ARMS
    }
    if train.empty or train[columns["b3_obs"]].isna().any().any() or len(origins) != len(inputs["origenes"]):
        raise ValueError("Missing Piura predictors in the frozen training period")

    output.mkdir(parents=True, exist_ok=True)
    parameters = sp.e3_parameters(report["hiperparametros"])
    margin = sp.e3_margin(origins, spatial.FORM)
    bundle = {
        "corte": str(CUTOFF.date()), "primera_semana_objetivo": str(FIRST_TARGET.date()),
        "ultima_semana_objetivo": str(LAST_TARGET.date()), "formulacion": spatial.FORM,
        "parametros": report["hiperparametros"], "columnas": columns,
        "semillas": report["semillas"], "corte_alerta": 0.5, "modelos": {},
        "validacion_piura": {key: quality["suites"][key]["evaluadas"] for key in quality["suites"]},
        "fuentes_piura": report["epidemiologia"] | report["fuentes"] | {"geografia": report["geografia"]},
        "sha256_informe_piura": digest(source / "resultados.json"),
    }
    epi_report = json.loads((archive.OUTPUT / "resultados.json").read_text())
    baseline_paths = dict(zip(pa.SEEDS, spatial.compatible_geo(
        original_columns, geography, epi_report, report["hiperparametros"]
    ), strict=True))
    if without_latitude:
        bundle["sensibilidad"] = "sin_latitud"
        if any(set(original_columns[arm]) - set(columns[arm]) != {"lat"} for arm in ARMS):
            raise ValueError("Latitude must be the sole predictor removed")

    def fit_variant(job):
        arm, seed = job
        name = f"{arm}_s{seed}"
        calibration_path = baseline_paths[seed] if arm == "historia_geo" else source / name
        previous = archive_rows(calibration_path)
        calibration_digest = digest(calibration_path / "predicciones.csv.gz")
        if without_latitude:
            previous = recalibration_rows(spatial, inputs, origins, previous, columns[arm], report["hiperparametros"], seed)
            calibration_file = output / f"{name}_calibracion_piura.csv.gz"
            previous.to_csv(calibration_file, index=False)
            calibration_digest = digest(calibration_file)
        records = {}
        for h, history in previous.groupby("horizonte"):
            records[str(h)] = {
                "platt": calibrator(history, history.probabilidad_cruda.to_numpy()),
                "peso_modelo": archive.closure.p5.fit_w(
                    history.mu_modelo.to_numpy(), history.persistencia.to_numpy(), history.casos_Dengue.to_numpy()
                ),
            }
        fit = sp.fit_e3(origins, CUTOFF, seed, spatial.FORM, columns[arm], [], parameters, margin)
        sample = fit.train.iloc[:7]
        count_model = sp.FORMULATIONS[spatial.FORM]["conteo"]
        expected = sp.predict_count(fit.regressor, sample[columns[arm]], count_model, margin[sample.index])
        path = output / f"{name}.ubj"
        fit.regressor.save_model(path)
        restored = XGBRegressor()
        restored.load_model(path)
        np.testing.assert_allclose(
            sp.predict_count(restored, sample[columns[arm]], count_model, margin[sample.index]), expected,
            rtol=0, atol=0,
        )
        model_record = {
            "brazo": arm, "semilla": seed, "sha256": digest(path), "alphas": fit.alphas, "por_horizonte": records,
            "filas_entrenamiento": len(fit.train), "ultimo_objetivo_h4": str(fit.train.semana_inicio_h4.max().date()),
            "sha256_calibracion": calibration_digest,
        }
        print(name, len(fit.train), flush=True)

        return name, model_record

    jobs = [(arm, seed) for arm in ARMS for seed in bundle["semillas"]]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        bundle["modelos"] = dict(pool.map(fit_variant, jobs))

    reference = archive_rows(baseline_paths[bundle["semillas"][0]])
    bundle["persistencia_prob"] = {
        str(h): calibrator(history, raw_persistence(history)) for h, history in reference.groupby("horizonte")
    }
    write_json(output / "paquete.json", bundle)


def read_sala(path: Path, year: int, districts: set[str], weeks: int) -> pd.DataFrame:
    records = read(path)
    valid = records.tipo_dx.eq("C") & records.anio.eq(year) & records.casos_Dengue.ge(0)
    if not valid.all() or not records.casos_Dengue.mod(1).eq(0).all():
        raise ValueError("Unexpected diagnosis, date or case count in Sala")
    if records.duplicated(["ubigeo", "anio", "semana"]).any() or set(records.ubigeo) != districts:
        raise ValueError("Incomplete or duplicated Sala district series")
    selected = records.loc[records.semana.between(1, weeks)]
    if not selected.groupby("ubigeo").size().eq(weeks).all():
        raise ValueError("Sala lacks district weeks in the required interval")
    return selected[["ubigeo", "anio", "semana", "casos_Dengue"]]


def destination_cases(csv: Path, geography: pd.DataFrame, *, year=YEAR, sala=None, overlap=None) -> tuple[pd.DataFrame, dict]:
    cases = pd.read_csv(csv, usecols=["departamento", "tipo_dx", "ubigeo", "ano", "semana"], dtype="string")
    cases["departamento"] = cases.departamento.str.strip().str.title()
    cases = cases.loc[cases.departamento.isin(DEPT.values())].copy()
    cases["ubigeo"] = cases.ubigeo.str.strip().str.zfill(6)
    known = cases.ubigeo.isin(geography.ubigeo)
    if not known.all():
        raise ValueError("External surveillance contains an unknown UBIGEO")
    expected = cases.ubigeo.str[:2].map(DEPT)
    if not cases.departamento.eq(expected).all():
        raise ValueError("External UBIGEO does not match department")
    cases["anio"] = cases.ano.astype(int)
    cases["semana"] = cases.semana.astype(int)
    cases["confirmed"] = cases.tipo_dx.str.strip().str.upper().eq("C")
    grid = lh.week_grid(2000, year)
    validated = cases.merge(grid, on=["anio", "semana"], how="left", validate="many_to_one")
    valid = validated.loc[validated.semana_inicio.notna()]
    eligible = sorted(valid.loc[valid.anio.between(2020, 2024), "ubigeo"].unique())
    coverage = valid.loc[valid.anio.eq(YEAR)].groupby("departamento").semana.agg(set)
    if any(not set(range(1, LAST_WEEK + 1)).issubset(coverage[region]) for region in DEPT.values()):
        raise ValueError("External department has weeks without any registered notification in the scoring period")
    counts = valid.loc[valid.confirmed].groupby(["ubigeo", "anio", "semana"]).size().rename("casos_Dengue").reset_index()
    panel = pd.DataFrame({"ubigeo": eligible}).merge(grid, how="cross")
    first_target = lh.week_grid(year, year).semana_inicio.min()
    last_target = first_target + (LAST_WEEK - 1) * 7 * DAY
    panel = panel.loc[panel.semana_inicio.le(last_target)]
    panel = panel.merge(counts, on=["ubigeo", "anio", "semana"], how="left", validate="one_to_one")
    panel["casos_Dengue"] = panel.casos_Dengue.fillna(0).astype(int)
    report = {
        "sha256_csv": digest(csv),
        "distritos_sin_notificaciones_2020_2024": sorted(set(geography.ubigeo) - set(eligible)),
        "confirmados_fuera_del_calendario": int((validated.semana_inicio.isna() & validated.confirmed).sum()),
        "distritos_incluidos": {region: sum(u.startswith(code) for u in eligible) for code, region in DEPT.items()},
    }
    if year > YEAR:
        if sala is None or overlap is None or year != 2026:
            raise ValueError("2026 requires explicit Sala series and a 2025 overlap archive")
        districts = set(geography.ubigeo)
        key = ["ubigeo", "anio", "semana"]
        history = read_sala(overlap, YEAR, districts, 53)
        counts_2025 = history[key].merge(counts, on=key, how="left", validate="one_to_one")
        delta = history.merge(counts_2025.fillna({"casos_Dengue": 0}), on=key, suffixes=("_sala", "_csv"))
        delta["cambio"] = delta.casos_Dengue_sala - delta.casos_Dengue_csv
        source = read_sala(sala, year, districts, LAST_WEEK)
        future = panel.loc[panel.anio.eq(year), [*key, "semana_inicio"]].merge(
            source, on=key, how="left", validate="one_to_one"
        )
        if future.casos_Dengue.isna().any():
            raise ValueError("The 2026 panel cannot be completed with published observations")
        panel = pd.concat([panel.loc[panel.anio.lt(year)], future], ignore_index=True)
        report["sha256_sala_2026"] = digest(sala)
        report["sha256_sala_2025"] = digest(overlap)
        report["solape_2025"] = {
            "semanas_distritales": len(delta), "coincidencias": int(delta.cambio.eq(0).sum()),
            "casos_csv": int(delta.casos_Dengue_csv.sum()), "casos_sala": int(delta.casos_Dengue_sala.sum()),
            "coincidencias_se01_38": int((delta.semana.le(LAST_WEEK) & delta.cambio.eq(0)).sum()),
        }
    return panel.sort_values(["ubigeo", "semana_inicio"]).reset_index(drop=True), report


def weekly_inputs(folder: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    def aggregate(filename, date, columns, agg):
        daily = read(folder / filename, (date,))
        if daily.duplicated(["ubigeo", date]).any():
            raise ValueError(f"Duplicate district-day: {filename}")
        weekly = daily.assign(semana_inicio=daily[date] - pd.to_timedelta((daily[date].dt.dayofweek + 1) % 7, unit="D"))
        grouped = weekly.groupby(["ubigeo", "semana_inicio"])
        if not grouped.size().eq(7).all() or weekly[columns].isna().any().any():
            raise ValueError(f"Incomplete daily weather: {filename}")
        return grouped[columns].agg(agg).reset_index()

    rain = aggregate("chirps_diario.csv", "fecha", ["precip_mm"], "sum").rename(
        columns={"precip_mm": "precip_total_mm"}
    )
    rain["fecha_disponible"] = pentad_publication(rain.semana_inicio + 6 * DAY)
    era = aggregate("era5_land_diario.csv", "time", ["temperature_2m_mean", "relative_humidity_2m_mean"], "mean")
    era = era.rename(columns={"temperature_2m_mean": "temp_media", "relative_humidity_2m_mean": "hum_rel_media"})
    era["fecha_disponible"] = era.semana_inicio + 13 * DAY
    return rain, era


def score_models(archive, spatial, csv: Path, weather: Path, output: Path, *, year=YEAR, sala=None, overlap=None) -> None:
    bundle = json.loads((output / "paquete.json").read_text())
    geo = read(weather / "geografia.csv")
    cases, report = destination_cases(csv, geo, year=year, sala=sala, overlap=overlap)
    first_target = lh.week_grid(year, year).semana_inicio.min()
    last_target = first_target + (LAST_WEEK - 1) * 7 * DAY
    cutoff = pd.Timestamp(bundle["corte"])
    labels = lh.long_labels(cases)
    matrices = {h: lh.long_matrix(cases, labels, h) for h in HORIZONS}
    full = origin_table(cases, matrices).merge(geo[["ubigeo", *spatial.GEO]], on="ubigeo", validate="many_to_one")
    support = {h: matrix.loc[matrix.semana_inicio.between(first_target, last_target)].copy() for h, matrix in matrices.items()}
    expected = len(cases.ubigeo.unique()) * LAST_WEEK
    for h, table in support.items():
        if len(table) != expected or table.origen_cierre.min() < cutoff:
            raise ValueError(f"Incomplete or premature scoring support at h={h}")
        if not table.origen_cierre.eq(table.semana_inicio - h * 7 * DAY + 6 * DAY).all():
            raise ValueError(f"Invalid origin-target alignment at h={h}")
    needed = pd.concat(support.values())[["ubigeo", "origen_cierre"]].drop_duplicates()
    origins = needed.merge(full, on=["ubigeo", "origen_cierre"], validate="one_to_one").reset_index(drop=True)
    if len(origins) != len(needed):
        raise ValueError("Missing destination origins")
    rain, era = weekly_inputs(weather)
    origins = add_weather(spatial, origins, rain, era)
    if origins[bundle["columnas"]["b3_obs"]].isna().any().any():
        raise ValueError("Missing predictors on common scoring support")
    margin = sp.e3_margin(origins, bundle["formulacion"])
    count_model = sp.FORMULATIONS[bundle["formulacion"]]["conteo"]
    apply = archive.closure.apply_platt
    predictions = []
    for name, info in bundle["modelos"].items():
        path = output / f"{name}.ubj"
        if digest(path) != info["sha256"]:
            raise ValueError(f"Unexpected model file {name}")
        model = XGBRegressor()
        model.load_model(path)
        mu = sp.predict_count(model, origins[bundle["columnas"][info["brazo"]]], count_model, margin)
        for i, h in enumerate(HORIZONS):
            target = support[h].merge(
                origins[["ubigeo", "origen_cierre"]].assign(mu=mu[:, i]),
                on=["ubigeo", "origen_cierre"], validate="one_to_one",
            )
            if len(target) != expected:
                raise ValueError(f"Incomplete prediction keys at h={h}")
            calibration = info["por_horizonte"][str(h)]
            raw = sp.negative_binomial_probability(target.mu, info["alphas"][i], target.umbral_brote_casos)
            platt = calibration["platt"]
            weight = calibration["peso_modelo"]
            predictions.append(target.assign(
                brazo=info["brazo"], semilla=info["semilla"], p=apply(raw, platt["a"], platt["b"]),
                casos_predichos=weight * target.mu + (1 - weight) * target.persistencia,
            ))
    for h, target in support.items():
        platt = bundle["persistencia_prob"][str(h)]
        for arm, probability in (
            ("persistencia_prob", apply(raw_persistence(target), platt["a"], platt["b"])),
            ("persistencia_det", target.persistencia.ge(sp.count_threshold(target.umbral_brote_casos)).astype(float)),
        ):
            predictions.append(target.assign(brazo=arm, semilla=0, p=probability, casos_predichos=target.persistencia))

    data = pd.concat(predictions, ignore_index=True).assign(departamento=lambda d: d.ubigeo.str[:2].map(DEPT))
    if data.duplicated([*KEY, "brazo", "semilla"]).any() or not data.p.between(0, 1).all():
        raise ValueError("Duplicated or invalid predictions")
    rows = []
    for (department, h, arm, seed), part in data.groupby(["departamento", "horizonte", "brazo", "semilla"]):
        alerts = part.p.ge(0.5)
        y = part.brote.astype(bool)
        tp, fp, fn = int((alerts & y).sum()), int((alerts & ~y).sum()), int((~alerts & y).sum())
        rows.append({
            "departamento": department, "horizonte": int(h), "brazo": arm, "semilla": int(seed),
            "n": len(part), "positivos": int(y.sum()), "brier": float(np.mean((part.p - y.astype(int)) ** 2)),
            "ap": float(average_precision_score(y, part.p)) if y.any() else None,
            "mae": float(np.mean(np.abs(part.casos_predichos - part.casos_Dengue))),
            "tp": tp, "fp": fp, "fn": fn, "recall": tp / (tp + fn) if tp + fn else None,
        })
    report["insumos_clima"] = {name: digest(weather / name) for name in (
        "geografia.csv", "era5_land_diario.csv", "chirps_diario.csv"
    )}
    report["sha256_paquete"] = digest(output / "paquete.json")
    report["periodo"] = {"anio": year, "semanas": [1, LAST_WEEK], "corte_entrenamiento": bundle["corte"]}
    with TemporaryDirectory(dir=output) as temp:
        staging = Path(temp)
        data[[*KEY, "departamento", "origen_cierre", "brazo", "semilla", "casos_Dengue", "brote", "p", "casos_predichos"]].to_csv(
            staging / "predicciones.csv.gz", index=False
        )
        pd.DataFrame(rows).to_csv(staging / "metricas.csv", index=False)
        report["salidas"] = {name: digest(staging / name) for name in ("predicciones.csv.gz", "metricas.csv")}
        write_json(staging / "evaluacion.json", report)
        for name in (*report["salidas"], "evaluacion.json"):
            (staging / name).replace(output / name)



def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("fit", "score"))
    parser.add_argument("--piura", type=Path, required=True, help="Checkout with the Piura paper and archived inputs")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--geography", type=Path)
    parser.add_argument("--cases", type=Path)
    parser.add_argument("--weather", type=Path)
    parser.add_argument("--year", type=int, choices=(2025, 2026), default=YEAR)
    parser.add_argument("--sala", type=Path)
    parser.add_argument("--overlap", type=Path)
    parser.add_argument("--without-latitude", action="store_true")
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    sys.path.insert(0, str(args.piura / "research/08_v3_confirmed_cases/code"))
    import run_experiment as archive
    import run_spatial_controls as spatial

    if archive.ROOT != args.piura.resolve():
        parser.error("Set PYTHONPATH to the src directory of --piura")
    if args.stage == "fit":
        if args.geography is None:
            parser.error("fit requires --geography")
        output = args.output.resolve()
        if output.exists():
            parser.error("Choose a new output directory to preserve the existing package")
        output.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=output.parent) as temp:
            staging = Path(temp) / output.name
            fit_piura(archive, spatial, args.geography, staging,
                      without_latitude=args.without_latitude, workers=args.workers)
            staging.rename(output)
    else:
        if args.cases is None or args.weather is None:
            parser.error("score requires --cases and --weather")
        if (args.output / "evaluacion.json").exists():
            parser.error("Preserve the existing evaluation before scoring again")
        score_models(archive, spatial, args.cases, args.weather, args.output,
                     year=args.year, sala=args.sala, overlap=args.overlap)


if __name__ == "__main__":
    main()
