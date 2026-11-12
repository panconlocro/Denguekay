"""Evaluate persistence, climatology and statistical count models on the common support."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score
import statsmodels.api as sm

import run_spatial_controls as spatial
import phase6_other_families as families

archive = spatial.archive
OUTPUT = archive.OUTPUT / "comparadores_revision"
TEMP_WINDOWS = [f"{c}_obs" for c in spatial.D3]


def fit_nb(train, columns, margin, seed):
    raw = train[columns].astype(float).copy()
    log1p = tuple(c for c in archive.rules.PHASE6_GLM_LOG1P if c in columns)
    raw[list(log1p)] = np.log1p(raw[list(log1p)])
    center, scale = raw.mean(), raw.std(ddof=0).replace(0.0, 1.0)
    x = families._glm_design(train[columns], center, scale, log1p)
    for c in (c for c in TEMP_WINDOWS if c in columns):
        x = np.column_stack([x, ((raw[c] - center[c]) / scale[c]).to_numpy() ** 2])
    poisson = families.fit_glm_poisson(train, columns, margin, seed)
    mu_poisson = families.predict_glm(poisson, train, margin)
    penalties = np.r_[0.0, np.full(x.shape[1] - 1, archive.rules.PHASE6_RIDGE_ALPHA)]
    params, alphas, converged = [], [], []
    for i, h in enumerate(archive.HORIZONS):
        y = train[f"casos_Dengue_h{h}"].to_numpy(float)
        dispersion = spatial.sp.negative_binomial_dispersion_detail(mu_poisson[:, i], y)
        if not dispersion["convergio"]:
            raise ValueError("La dispersión NB2 no convergió")
        alpha = dispersion["alpha"]
        model = sm.GLM(y, x, family=sm.families.NegativeBinomial(alpha=alpha), offset=margin[:, i])
        result = model.fit(maxiter=archive.rules.PHASE6_GLM_MAXITER)
        ok = bool(result.converged) and np.isfinite(result.params).all()
        if not ok:
            result = model.fit_regularized(alpha=penalties, L1_wt=0, maxiter=archive.rules.PHASE6_GLM_MAXITER)
        if not np.isfinite(result.params).all() or not getattr(result, "converged", True):
            raise ValueError("El GLM NB2 no convergió con el respaldo")
        converged.append(ok)
        params.append(result.params)
        alphas.append(alpha)
    return {"columns": columns, "center": center, "scale": scale, "log1p": log1p,
            "beta": np.asarray(params).T, "alpha": alphas, "convergio": converged,
            "penalizado": [not v for v in converged]}


def predict_nb(fit, frame, margin):
    x = families._glm_design(frame[fit["columns"]], fit["center"], fit["scale"], fit["log1p"])
    for c in (c for c in TEMP_WINDOWS if c in fit["columns"]):
        x = np.column_stack([x, ((frame[c] - fit["center"][c]) / fit["scale"][c]).to_numpy() ** 2])
    return np.exp(x @ fit["beta"] + margin)


def nb_predictions(inputs, origins, columns, seed):
    parts, fits = [], []
    margin = spatial.sp.e3_margin(origins, spatial.FORM)
    for block, kind, period in spatial.BLOCK_LIST:
        tests, cutoff = spatial.eh._common_cutoffs(inputs["matrices"], kind, period)
        train = archive.original.p3._training(origins, cutoff)
        fitted = fit_nb(train, columns, margin[train.index], seed)
        dates = origins.origen_cierre
        support = np.flatnonzero(dates.between(min(t.origen_cierre.min() for t in tests.values()),
                                              max(t.origen_cierre.max() for t in tests.values())))
        target = origins.iloc[support][["ubigeo", "origen_cierre"]]
        mu = predict_nb(fitted, origins.iloc[support], margin[support])
        for i, h in enumerate(archive.HORIZONS):
            test = tests[h].merge(target.assign(mu=mu[:, i]), on=["ubigeo", "origen_cierre"], validate="one_to_one")
            if len(test) != len(tests[h]):
                raise ValueError(f"Se perdieron observaciones en {block}, h{h}")
            p = spatial.sp.negative_binomial_probability(test.mu, fitted["alpha"][i], test.umbral_brote_casos)
            parts.append(spatial.eh._output(test, block, test.mu, p))
        fits.append({"bloque": block, "corte": cutoff, "filas_entrenamiento": len(train),
                     **{f"alpha_h{h}": fitted["alpha"][i] for i, h in enumerate(archive.HORIZONS)},
                     **{f"convergio_h{h}": fitted["convergio"][i] for i, h in enumerate(archive.HORIZONS)}})
    return pd.concat(parts, ignore_index=True), pd.DataFrame(fits)


def count_model(inputs, origins, columns, arm, family, seed, fingerprint):
    path = OUTPUT / f"{arm}_s{seed}"
    if path.exists():
        import json
        if json.loads((path / "control.json").read_text())["huella"] != fingerprint:
            raise ValueError(f"Checkpoint incompatible: {path}")
        return path
    if family == "nb":
        pred, fits = nb_predictions(inputs, origins, columns, seed)
    else:
        pred = families.predict_blocks_family(inputs["matrices"], origins, spatial.BLOCK_LIST, seed, columns, family)
        fits = pred.attrs.pop("ajustes")
    table = archive.closure.full_table(pred, fits.assign(semilla=seed, regimen=None), arm, seed)
    guard = archive.closure.check_table(table)
    if (len(table) != 194805 or table.duplicated(archive.closure.KEY).any() or guard["alpha_nulos"]
            or guard["calibrada_sin_platt"] or guard["platt_diferencia_maxima"] > 1e-12
            or guard["conteo_diferencia_maxima"] > 1e-12):
        raise ValueError(f"Predicciones inválidas: {arm}, {seed}")
    from tempfile import TemporaryDirectory
    with TemporaryDirectory(dir=OUTPUT) as tmp:
        temp = Path(tmp)
        table.to_csv(temp / "predicciones.csv.gz", index=False)
        fits.to_csv(temp / "ajustes.csv", index=False)
        archive.closure.block_metrics(table).to_csv(temp / "metricas.csv", index=False)
        archive.write_json(temp / "control.json", {"huella": fingerprint, "filas": len(table), **guard})
        temp.rename(path)
    return path


def reference_scores(support, labels):
    k = spatial.sp.count_threshold(support.umbral_brote_casos)
    ratio = (support.persistencia + 0.5) / (k + 0.5)
    calendar = spatial.mmwr_epi_week(support.semana_inicio)
    pred = support.assign(anio=calendar.anio_epi, semana=calendar.semana_epi,
                          probabilidad_brote=ratio / (1 + ratio))
    prob, _ = spatial.pa.calibrate_chronologically(pred)
    baselines = support.copy()
    baselines["persistencia_prob"] = prob.probabilidad_calibrada.to_numpy()
    baselines["persistencia_det"] = baselines.persistencia.ge(k).astype(float)
    baselines["climatologia"] = archive.original.pdw.climatology(support, labels)
    baselines.to_csv(OUTPUT / "predicciones_baselines.csv.gz", index=False)
    rows = []
    for (block, h), part in baselines.groupby(["bloque", "horizonte"]):
        for arm in ("persistencia_prob", "persistencia_det", "climatologia"):
            if part[arm].isna().any():
                continue
            y, p = part.brote.to_numpy(int), part[arm].to_numpy(float)
            rows.append({"variante": arm, "semilla": 17, "bloque": block, "horizonte": h,
                         "n": len(y), "positivos": int(y.sum()), "brier": np.mean((p - y) ** 2),
                         "auprc": average_precision_score(y, p) if y.any() else np.nan})
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("geografia", type=Path)
    args = parser.parse_args()
    import lightgbm
    import statsmodels

    archived, _, quality, inputs = spatial.training_data()
    origins, arms, _, _ = spatial.prepare(inputs, args.geografia)
    history = arms["historia_geo"]
    climate = [f"{c}_obs" for c in spatial.B3 if c != spatial.TEMP]
    groups = {
        "nb_historia_geo": ("nb", history, (17,)),
        "nb_clima_rezagos": ("nb", [*history, *climate, *TEMP_WINDOWS], (17,)),
        "poisson_historia_geo": ("6a_prima_poisson_glm", history, (17,)),
        "lightgbm_historia_geo": ("6b_lightgbm", history, spatial.pa.SEEDS),
    }
    config = {"grupos": groups, "codigo": archive.sha256(Path(__file__)),
              "control_espacial": archive.sha256(Path(spatial.__file__)),
              "epidemiologia": archived["configuracion"]["insumos"], "geografia": archive.sha256(args.geografia),
              "clima": {p.name: archive.sha256(p) for p in (spatial.SILVER_CHIRPS_PRECIP, spatial.SILVER_ENSO)},
              "statsmodels": statsmodels.__version__, "lightgbm": lightgbm.__version__,
              "protocolo": archive.sha256(Path(__file__).resolve().parents[1] / "protocolo_benchmarks_confirmados.md")}
    import json
    fingerprint = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    archive.write_json(OUTPUT / "diseno.json", {"huella": fingerprint, **config})
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(count_model, inputs, origins, cols, arm, family, seed, fingerprint)
                for arm, (family, cols, seeds) in groups.items() for seed in seeds]
        paths = []
        for future in as_completed(jobs):
            paths.append(future.result())
            print(f"Comparadores {len(paths)}/{len(jobs)} {paths[-1].name}", flush=True)
    prediction = spatial.OUTPUT / "b3_obs_s17" / "predicciones.csv.gz"
    types = {"ubigeo": str}
    support = pd.read_csv(prediction, usecols=archive.OBSERVATIONS,
                          dtype=types, parse_dates=["semana_inicio", "origen_cierre"])
    for path in paths:
        data = pd.read_csv(path / "predicciones.csv.gz", usecols=archive.OBSERVATIONS,
                           dtype=types, parse_dates=["semana_inicio", "origen_cierre"])
        pd.testing.assert_frame_equal(data, support)
    metrics = pd.concat([reference_scores(support, inputs["etiquetas"]),
                         *(pd.read_csv(path / "metricas.csv") for path in paths)], ignore_index=True)
    metrics.to_csv(OUTPUT / "metricas_por_bloque.csv", index=False)
    report = {"horizontes": {}}
    decisive = metrics.loc[metrics.bloque.isin([f"temporada_{s}" for s in spatial.DECIDING])]
    for h, rows in decisive.groupby("horizonte"):
        vals = rows.groupby(["variante", "bloque"])[["brier", "auprc"]].median().groupby("variante").mean()
        report["horizontes"][str(h)] = {"variantes": {a: {"metricas": v} for a, v in vals.to_dict("index").items()}}
    path = OUTPUT / "resultados.json"
    archive.write_json(path, {"huella": fingerprint, **config})
    run = archive.tracking.log_report(
        "v3_confirmados_comparadores_revision", report, metrics_path=path, output_dir=OUTPUT, gold_dir=archive.GOLD,
        data_quality=quality, log_datasets=False, tracking_uri=f"sqlite:///{archive.MLFLOW_DB.as_posix()}",
        fingerprint=fingerprint, description="Persistencia, climatología y comparadores de conteo en soporte común.",
    )
    archive.write_json(path, {"huella": fingerprint, **config, "mlflow_run": run})
    print("MLflow", run, flush=True)


if __name__ == "__main__":
    main()
