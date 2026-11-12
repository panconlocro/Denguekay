"""Run the confirmed-case contribution contrasts from protocolo_contribucion.md."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

import run_experiment as archive
from denguekay.data.validation.gx_quality import validate_modeling_inputs
from denguekay.evaluation import episodes, protocol
from denguekay.model import probabilistic_output as probability

SEEDS = protocol.SEEDS
HISTORY_SEASONS = (2021, 2022, 2023, 2024, 2026)
ALERT_SEASONS = archive.rules.SEASON_2026_DECIDING
START_SHORT = "2017-01-01"
BUDGETS = (0.5, 1.0, 2.0)
KEY = archive.closure.KEY
OBS = archive.OBSERVATIONS
DAY = pd.Timedelta(days=1)
OUTPUT = archive.OUTPUT / "contribucion"
STUDY = "v3_confirmados_contribucion"


def load_archive(variant, seed):
    file = archive.OUTPUT / f"{variant}_s{seed}" / "predicciones.csv.gz"
    data = pd.read_csv(file, usecols=[*OBS, "probabilidad_cruda"],
                       dtype={"ubigeo": "string"}, parse_dates=["semana_inicio", "origen_cierre"],
                       float_precision="round_trip")
    data = data.loc[data.bloque.str.startswith("temporada_")].reset_index(drop=True)
    if data.duplicated(["horizonte", "ubigeo", "semana_inicio"]).any():
        raise ValueError("Semanas repetidas en el archivo de temporadas regulares")
    if not data.probabilidad_cruda.between(0, 1).all():
        raise ValueError("Probabilidades crudas archivadas inválidas")
    return data


def training_data():
    snapshot = json.loads((archive.OUTPUT / "resultados.json").read_text())
    for path, expected in snapshot["configuracion"]["insumos"].items():
        if archive.sha256(archive.ROOT / path) != expected:
            raise ValueError(f"Insumo distinto del archivo de confirmados: {path}")
    handoff = archive.audit_handoff(silver_path=archive.PANEL, history_path=archive.HISTORY)
    quality = validate_modeling_inputs(silver_path=archive.PANEL)
    sala = pd.read_csv(archive.SALA, dtype={"ubigeo": "string"})
    if not sala.tipo_dx.eq("C").all():
        raise ValueError("La Sala tiene filas sin diagnóstico confirmado")
    inputs = archive.long_inputs(archive.load_integrated(archive.PANEL), archive.ERA5,
                                 sala=sala, history_path=archive.HISTORY)
    return snapshot, handoff, quality, inputs


def fit_short(inputs, config, seed):
    origins = inputs["origenes"]
    origins = origins.loc[origins.semana_inicio.ge(START_SHORT)].reset_index(drop=True)
    blocks = [b for b in archive.original.blocks() if b[1] == "temporada" and 2018 <= b[2] <= 2026]
    pred = archive.original.p3.predict_blocks_weighted(
        inputs["matrices"], origins, blocks, seed, config["variables"]["L + 5a"],
        config["configuracion"]["parametros"],
    )
    fits = pred.attrs.pop("ajustes").assign(semilla=seed, primer_objetivo_h2=origins.semana_inicio.min())
    pred = pred.rename(columns={"probabilidad_brote": "p_entrenamiento_corto"})
    print(f"Historia corta, semilla {seed}: {len(blocks)} ajustes", flush=True)
    return pred[[*OBS, "p_entrenamiento_corto"]], fits


def block_folds(data):
    for horizon, group in data.groupby("horizonte"):
        blocks = sorted(group.bloque.unique())
        for i, block in enumerate(blocks):
            test = group.loc[group.bloque.eq(block)]
            cutoff = protocol.block_cutoff(test)
            earlier = group.loc[group.bloque.isin(blocks[:i])]
            available = earlier.loc[(earlier.semana_inicio + 6 * DAY).le(cutoff)]
            yield horizon, block, test, available, cutoff


def calibrate(data, columns, window=None):
    output = pd.DataFrame(np.nan, index=data.index, columns=columns)
    audits = []
    for h, block, test, earlier, cutoff in block_folds(data):
        if window:
            previous = sorted(earlier.bloque.unique())[-window:]
            earlier = earlier.loc[earlier.bloque.isin(previous)]
        if earlier.brote.nunique() < 2:
            continue
        for column in columns:
            model = protocol.fit_platt(earlier[column], earlier.brote)
            logits = protocol.platt_logit(test[column]).reshape(-1, 1)
            output.loc[test.index, column] = model.predict_proba(logits)[:, 1]
            audits.append({
                "bloque": block, "horizonte": h, "serie": column, "corte": cutoff,
                "ventana": window or "larga", "filas": len(earlier),
                "positivos": int(earlier.brote.sum()),
                "temporadas": earlier.bloque.nunique(),
                "ultimo_cierre": earlier.semana_inicio.max() + 6 * DAY,
                "pendiente": float(model.coef_[0, 0]), "intercepto": float(model.intercept_[0]),
            })
    return output, pd.DataFrame(audits)


def score(y, p):
    actual = y.to_numpy(int)
    forecast = p.to_numpy(float)
    brier = float(np.mean((forecast - actual) ** 2))
    bins = np.minimum((10 * forecast).astype(int), 9)
    groups = pd.DataFrame({"y": actual, "p": forecast}).groupby(bins).agg(
        observado=("y", "mean"), predicho=("p", "mean"), filas=("y", "size"))
    weight = groups.filas / len(y)
    reliability = float((weight * (groups.predicho - groups.observado) ** 2).sum())
    resolution = float((weight * (groups.observado - actual.mean()) ** 2).sum())
    uncertainty = float(actual.mean() * (1 - actual.mean()))
    return {
        "brier": brier, "ap": float(average_precision_score(actual, forecast)),
        "probabilidad_media": forecast.mean(), "prevalencia": actual.mean(),
        "confiabilidad_10": reliability, "resolucion_10": resolution, "incertidumbre": uncertainty,
        "residuo_bins": brier - (reliability - resolution + uncertainty),
    }


def history_metrics(data, seed):
    columns = ["p_entrenamiento_corto", "p_entrenamiento_largo"]
    short, audit_short = calibrate(data, columns, window=2)
    long, audit_long = calibrate(data, columns)
    rows = []
    for horizon, block, test, available, _ in block_folds(data):
        if int(block[-4:]) not in HISTORY_SEASONS or available.bloque.nunique() < 3:
            continue
        for window, predictions in (("cruda", data), ("corta", short), ("larga", long)):
            for column in columns:
                rows.append({
                    "semilla": seed, "bloque": block, "horizonte": horizon,
                    "entrenamiento": column.split("_")[-1], "calibracion": window,
                    "filas": len(test), **score(test.brote, predictions.loc[test.index, column]),
                })
    return rows, pd.concat([audit_short, audit_long], ignore_index=True).assign(semilla=seed)


def budget_cutoff(p, y, budget):
    negative = np.sort(p.loc[y.eq(0)].to_numpy(float))[::-1]
    cap = int(np.floor(len(p) * budget / 52))
    if cap >= len(negative):
        return -np.inf
    return np.nextafter(negative[cap], np.inf)


def alert_metrics(data, labels, seed):
    k = probability.count_threshold(data.umbral_brote_casos)
    # Logit of this score is exactly log((persistencia + 0.5) / (k + 0.5)).
    ratio = (data.persistencia + 0.5) / (k + 0.5)
    data["persistencia_prob"] = ratio / (1 + ratio)
    data["persistencia_determinista"] = data.persistencia.ge(k)
    methods = ["sin_clima", "v3", "persistencia_prob"]
    calibrated, audits = calibrate(data, methods)
    rows, operating, forecasts = [], [], []
    for h, block, test, available, _ in block_folds(data):
        if int(block[-4:]) not in ALERT_SEASONS:
            continue
        report = test[OBS + ["persistencia_determinista"]].copy()
        row = {"bloque": block, "horizonte": h, "semilla": seed}
        by_alert = {"persistencia_determinista": {**row, "metodo": "persistencia_determinista",
                                                  "politica": "original", "presupuesto": np.nan}}
        for method in methods:
            p = calibrated.loc[test.index, method]
            rows.append({**row, "metodo": method, "filas": len(test), **score(test.brote, p)})
            past = calibrated.loc[available.index, method].dropna()
            for policy, reference in (("previa", past), ("descriptiva", p)):
                for budget in BUDGETS:
                    cutoff = budget_cutoff(reference, data.loc[reference.index, "brote"], budget)
                    field = f"{method}_{policy}_{budget:g}"
                    report[field] = p.ge(cutoff)
                    by_alert[field] = {**row, "metodo": method, "politica": policy, "presupuesto": budget,
                                       "corte": cutoff}
        events = episodes.episode_lead_time(report, labels, list(by_alert))
        events = events.loc[
            events.semanas_previas_sin_brote.ge(episodes.NO_PREVIOUS_OUTBREAK)
            & events.inicio.ge(test.semana_inicio.min() + 7 * episodes.ADJACENCY_WINDOW * DAY)
        ]
        for field, record in by_alert.items():
            false_alerts = int((report[field] & report.brote.eq(0)).sum())
            operating.append({
                **record, "filas": len(test), "falsos_avisos": false_alerts,
                "falsos_por_distrito_52_semanas": false_alerts * 52 / len(test),
                "episodios": len(events), "anticipados_2": int(events[field].ge(protocol.MIN_LEAD_TIME).sum()),
            })
        forecasts.append(report.assign(semilla=seed, **{m: calibrated.loc[test.index, m] for m in methods}))
    return rows, operating, audits.assign(semilla=seed), pd.concat(forecasts, ignore_index=True)


def audit_observations(data, labels, cases):
    by_week = ["ubigeo", "semana_inicio"]
    y = data.merge(labels[by_week + ["brote", "umbral_brote_casos", "casos_Dengue"]],
                   on=by_week, how="left", suffixes=("", "_reconstruido"), validate="many_to_one")
    for field in ("brote", "umbral_brote_casos", "casos_Dengue"):
        np.testing.assert_allclose(y[field], y[f"{field}_reconstruido"], rtol=0, atol=1e-10)
    close = data.semana_inicio - pd.to_timedelta(data.horizonte * 7 - 6, unit="D")
    if not close.eq(data.origen_cierre).all():
        raise ValueError("La fecha de origen difiere de la regla t−h")
    lag = data.assign(semana_inicio=close - 6 * DAY).merge(
        cases[by_week + ["casos_Dengue"]], on=by_week, suffixes=("", "_origen"), validate="many_to_one")
    if len(lag) != len(data) or not lag.persistencia.eq(lag.casos_Dengue_origen).all():
        raise ValueError("La persistencia difiere del conteo confirmado al origen")


def main():
    snapshot, handoff, quality, inputs = training_data()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    print("Insumos, linaje de gold y Great Expectations verificados", flush=True)
    jobs = archive.device.xgboost_settings()
    if jobs["device"] != "cpu":
        raise ValueError("Usar CPU para comparar con el archivo de confirmados")
    history, history_fits, alert, operating, alert_fits, fits = [], [], [], [], [], []
    archive_files = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        pending = {seed: pool.submit(fit_short, inputs, snapshot, seed) for seed in SEEDS}
        for i, seed in enumerate(SEEDS):
            short, fit = pending[seed].result()
            fits.append(fit)
            long = load_archive("l5a", seed).rename(columns={"probabilidad_cruda": "p_entrenamiento_largo"})
            climate = load_archive("v3", seed).rename(columns={"probabilidad_cruda": "v3"})
            for slug in ("l5a", "v3"):
                path = archive.OUTPUT / f"{slug}_s{seed}" / "predicciones.csv.gz"
                archive_files[str(path.relative_to(archive.ROOT))] = archive.sha256(path)
            pd.testing.assert_frame_equal(long[OBS], climate[OBS])
            if i == 0:
                audit_observations(long, inputs["etiquetas"], inputs["casos"])
                shared_rows = long[OBS]
            else:
                pd.testing.assert_frame_equal(shared_rows, long[OBS])
            paired = long.merge(short, on=KEY, how="inner", suffixes=("", "_corto"), validate="one_to_one")
            if len(paired) != len(short) or paired.bloque.min() != "temporada_2018":
                raise ValueError("Cobertura corta y larga desigual")
            for column in set(OBS) - set(KEY):
                pd.testing.assert_series_equal(paired[column], paired[f"{column}_corto"], check_names=False,
                                               check_dtype=False, rtol=0, atol=1e-10)
            h, hfit = history_metrics(paired, seed)
            a, o, afit, forecasts = alert_metrics(
                long.rename(columns={"p_entrenamiento_largo": "sin_clima"}).assign(v3=climate.v3),
                inputs["serie"], seed,
            )
            history.extend(h)
            history_fits.append(hfit)
            alert.extend(a)
            operating.extend(o)
            alert_fits.append(afit)
            short.to_csv(OUTPUT / f"historia_corta_s{seed}.csv.gz", index=False)
            forecasts.to_csv(OUTPUT / f"alertas_s{seed}.csv.gz", index=False)
            print(f"Contrastes verificados, semilla {seed}", flush=True)

    frames = {
        "historia_metricas": pd.DataFrame(history), "alertas_metricas": pd.DataFrame(alert),
        "puntos_operativos": pd.DataFrame(operating),
        "historia_ajustes": pd.concat(fits, ignore_index=True),
        "historia_calibracion": pd.concat(history_fits, ignore_index=True),
        "alertas_calibracion": pd.concat(alert_fits, ignore_index=True),
    }
    for name, frame in frames.items():
        frame.to_csv(OUTPUT / f"{name}.csv", index=False)
    fingerprints = {
        "insumos": snapshot["configuracion"]["insumos"], "predicciones_archivadas": archive_files,
        "configuracion_archivada": snapshot["configuracion"], "codigo": archive.sha256(Path(__file__)),
        "protocolo": archive.sha256(Path(__file__).resolve().parents[1] / "protocolo_contribucion.md"),
        "entorno": jobs, "software": archive.tracking.environment_tags(),
    }
    manifest = {
        "experimento": STUDY, "semillas": list(SEEDS), "huellas": fingerprints,
        "calidad": quality, "gold_filas": handoff["horizontes"]["2"]["filas"],
        "filas_por_tabla": {name: len(frame) for name, frame in frames.items()},
    }
    path = OUTPUT / "manifiesto.json"
    archive.write_json(path, manifest)
    report = {"experimento": STUDY, "parametros": snapshot["configuracion"]["parametros"], "horizontes": {}}
    for h in archive.HORIZONS:
        per_horizon = frames["alertas_metricas"].loc[lambda d: d.horizonte.eq(h)]
        summary = per_horizon.groupby(["metodo", "bloque"])[["brier", "ap"]].median().groupby("metodo").mean()
        report["horizontes"][str(h)] = {
            "variantes": {method: {"metricas": metrics} for method, metrics in summary.to_dict("index").items()}
        }
    manifest["mlflow_run"] = archive.tracking.log_report(
        STUDY, report, metrics_path=path, output_dir=OUTPUT, gold_dir=archive.GOLD,
        data_quality=quality, log_datasets=False, tracking_uri=f"sqlite:///{archive.MLFLOW_DB.as_posix()}",
        fingerprint=hashlib.sha256(json.dumps(fingerprints, sort_keys=True).encode()).hexdigest(),
        description="Análisis retrospectivo de ventanas de entrenamiento, calibración y alertas con confirmados.",
    )
    archive.write_json(path, manifest)
    print(f"Resultados: {OUTPUT} | MLflow {manifest['mlflow_run']}", flush=True)


if __name__ == "__main__":
    main()
