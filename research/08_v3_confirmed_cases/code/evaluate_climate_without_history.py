"""Estimate the incremental climate signal with and without recent case predictors."""

from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

from denguekay.evaluation.metrics import count_metrics
from run_contribution import training_data
import run_spatial_controls as spatial


archive = spatial.archive
OUTPUT = archive.OUTPUT / "clima_sin_historia"
STUDY = "v3_confirmados_clima_sin_historia"
GEOGRAPHY = spatial.RESOLUTION.parent / "insumos" / "geografia_distritos.csv"
FORMULATION = "S4_s2"
BLOCKS = spatial.BLOCK_LIST[:-1]
DECISIVE = [f"temporada_{season}" for season in spatial.DECIDING]


def fit_arm(inputs, origins, columns, hp, seed):
    parts, fits = [], []
    params = spatial.sp.e3_parameters(hp)
    for block, kind, season in BLOCKS:
        tests, cutoff = spatial.eh._common_cutoffs(inputs["matrices"], kind, season)
        fit = spatial.sp.fit_e3(origins, cutoff, seed, FORMULATION, columns, [], params, None)
        latest_label = fit.train.semana_inicio_h4.max() + pd.Timedelta(days=6)
        if latest_label > cutoff:
            raise ValueError(f"Etiqueta de entrenamiento posterior al corte: {block}")
        for j, h in enumerate(archive.HORIZONS):
            test = tests[h]
            features = test[["ubigeo", "origen_cierre"]].merge(
                origins[["ubigeo", "origen_cierre", *columns]], on=["ubigeo", "origen_cierre"], how="left",
                validate="one_to_one")
            if features[columns].isna().any().any():
                raise ValueError(f"Predictores incompletos: {block}, h{h}")
            # Predict the three counts for all origins of the horizon, then retain its column.
            counts = spatial.sp.predict_count(fit.regressor, features[columns], "poisson")[:, j]
            p = spatial.sp.negative_binomial_probability(counts, fit.alphas[j], test.umbral_brote_casos)
            parts.append(spatial.eh._output(test, block, counts, p))
            fits.append({"bloque": block, "horizonte": h, "corte": cutoff, "ultimo_cierre": latest_label,
                         "filas_entrenamiento": len(fit.train), "alpha_usada": fit.alphas[j]})
    pred = pd.concat(parts, ignore_index=True)
    calibrated, calibration = spatial.pa.calibrate_chronologically(pred)
    fitted = pd.DataFrame(fits).merge(calibration, on=["bloque", "horizonte"], validate="one_to_one",
                                      suffixes=("_entrenamiento", "_calibracion"))
    if not fitted.ultima_etiqueta_usada.dropna().le(fitted.loc[fitted.ultima_etiqueta_usada.notna(), "corte_calibracion"]).all():
        raise ValueError("Etiqueta de calibración posterior al corte")
    return calibrated, fitted


def save_arm(inputs, origins, arm, columns, hp, seed, fingerprint):
    path = OUTPUT / f"{arm}_s{seed}"
    if path.exists():
        if json.loads((path / "control.json").read_text())["huella"] != fingerprint:
            raise ValueError(f"Predicciones incompatibles en {path}")
        return path
    forecasts, cuts = fit_arm(inputs, origins, columns, hp, seed)
    forecasts = forecasts.assign(variante=arm, semilla=seed)
    probability = archive.closure.block_metrics(forecasts)
    counts = []
    for (block, h), group in forecasts.groupby(["bloque", "horizonte"]):
        counts.append({"bloque": block, "horizonte": h,
                       **count_metrics(group.casos_Dengue, group.casos_predichos)})
    metrics = pd.DataFrame(counts).merge(probability, on=["bloque", "horizonte"], how="left",
                                         validate="one_to_one").assign(variante=arm, semilla=seed)
    if len(forecasts) != 193440 or len(metrics) != 57 or metrics.brier.notna().sum() != 54:
        raise ValueError(f"Soporte inesperado para {arm}, semilla {seed}")
    with TemporaryDirectory(dir=OUTPUT) as tmp:
        temp = Path(tmp)
        forecasts.to_csv(temp / "predicciones.csv.gz", index=False)
        metrics.to_csv(temp / "metricas.csv", index=False)
        cuts.to_csv(temp / "cortes.csv", index=False)
        archive.write_json(temp / "control.json", {"huella": fingerprint, "filas": len(forecasts)})
        temp.rename(path)
    print(f"{arm}, semilla {seed}: {len(cuts) // 3} cortes ajustados.", flush=True)
    return path


def summaries(paths):
    baseline = archive.OUTPUT / "comparadores_revision"
    reference = pd.read_csv(baseline / "predicciones_baselines.csv.gz", dtype={"ubigeo": str},
                            parse_dates=["semana_inicio", "origen_cierre"], usecols=archive.OBSERVATIONS)
    reference = reference.loc[reference.bloque.str.startswith("temporada_")].reset_index(drop=True)
    metrics = []
    for path in sorted(paths):
        forecast = pd.read_csv(path / "predicciones.csv.gz", dtype={"ubigeo": str},
                               parse_dates=["semana_inicio", "origen_cierre"], usecols=archive.OBSERVATIONS)
        pd.testing.assert_frame_equal(forecast[archive.OBSERVATIONS], reference[archive.OBSERVATIONS])
        metrics.append(pd.read_csv(path / "metricas.csv"))
    metrics = pd.concat(metrics, ignore_index=True)
    ref = pd.read_csv(baseline / "metricas_por_bloque.csv")
    ref = ref.loc[ref.variante.isin(["persistencia_prob", "climatologia"])]
    ref = ref.pivot(index=["bloque", "horizonte"], columns="variante", values="brier").reset_index()
    metrics = metrics.merge(ref, on=["bloque", "horizonte"], how="left", validate="many_to_one")
    metrics = metrics.assign(bss_climatologia=1 - metrics.brier / metrics.climatologia,
                             bss_persistencia=1 - metrics.brier / metrics.persistencia_prob)
    metrics.to_csv(OUTPUT / "metricas_por_bloque_y_semilla.csv", index=False)
    fields = ["brier", "auprc", "mae", "rmse", "mae_log1p", "bss_climatologia", "bss_persistencia"]
    wide = metrics.pivot(index=["bloque", "horizonte", "semilla"], columns="variante", values=fields)
    pairs = [("clima_sin_historia", "clima_geografia", "geografia"),
             ("clima_con_historia", "clima_historia_geografia", "historia_geografia"),
             ("historia_sin_clima", "historia_geografia", "geografia"),
             ("historia_con_clima", "clima_historia_geografia", "clima_geografia")]
    contrasts = []
    for name, a, b in pairs:
        delta = wide.xs(a, level="variante", axis=1) - wide.xs(b, level="variante", axis=1)
        delta["brier_relativo"] = delta.brier / wide[("brier", b)]
        contrasts.append(delta.reset_index().assign(contraste=name))
    interaction = (contrasts[1].set_index(["bloque", "horizonte", "semilla"])[fields]
                   - contrasts[0].set_index(["bloque", "horizonte", "semilla"])[fields])
    contrasts.append(interaction.reset_index().assign(contraste="interaccion_clima_historia"))
    detail = pd.concat(contrasts, ignore_index=True)
    detail.to_csv(OUTPUT / "contrastes_por_semilla.csv", index=False)
    medians = detail.groupby(["bloque", "horizonte", "contraste"], as_index=False)[
        [*fields, "brier_relativo"]].median()
    medians.to_csv(OUTPUT / "contrastes_por_temporada.csv", index=False)
    test = medians.loc[medians.bloque.isin(DECISIVE)]
    variants = []
    for name, subset in (("principal", test), ("sin_2026", test.loc[test.bloque.ne("temporada_2026")])):
        stats = subset.groupby(["horizonte", "contraste"], as_index=False).agg(
            **{f: (f, "mean") for f in [*fields, "brier_relativo"]},
            temporadas=("brier", "size"), mejora_brier=("brier", lambda p: int(p.lt(0).sum())))
        variants.append(stats.assign(conjunto=name))
    pd.concat(variants, ignore_index=True).to_csv(OUTPUT / "resumen_contrastes.csv", index=False)
    return (metrics.loc[metrics.bloque.isin(DECISIVE)].groupby(["horizonte", "variante", "bloque"])[fields].median()
            .groupby(["horizonte", "variante"]).mean())


def main():
    archived, _, quality, inputs = training_data()
    evidence = json.loads((spatial.OUTPUT / "resultados.json").read_text())
    origins, original_arms, hp, _ = spatial.prepare(inputs, GEOGRAPHY)
    climate = [f"{c}_obs" for c in spatial.B3]
    geo = ["semana_epi_seno", "semana_epi_coseno", *spatial.GEO]
    case_history = original_arms["historia_geo"]
    if (evidence["geografia"] != archive.sha256(GEOGRAPHY) or evidence["hiperparametros"] != hp
            or evidence["epidemiologia"] != archived["configuracion"]["insumos"]
            or evidence["variantes"]["b3_obs"] != [*case_history, *climate]
            or evidence["entorno"] != archive.device.xgboost_settings()
            or evidence["codigo"] != archive.sha256(Path(spatial.__file__))
            or any(evidence["fuentes"][p.name] != archive.sha256(p)
                   for p in (spatial.SILVER_CHIRPS_PRECIP, spatial.SILVER_ENSO))):
        raise ValueError("Insumos diferentes del control espacial archivado")
    arms = {"geografia": geo, "clima_geografia": [*geo, *climate],
            "historia_geografia": case_history, "clima_historia_geografia": [*case_history, *climate]}
    info = {"controles_espaciales": evidence["huella"], "columnas": arms, "parametros": hp,
            "formulacion": FORMULATION, "semillas": spatial.pa.SEEDS, "temporadas_decisivas": DECISIVE,
            "codigo": archive.sha256(Path(__file__)),
            "protocolo": archive.sha256(Path(__file__).resolve().parents[1] / "protocolo_clima_sin_historia.md")}
    fingerprint = hashlib.sha256(json.dumps(info, sort_keys=True).encode()).hexdigest()
    OUTPUT.mkdir(exist_ok=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = [pool.submit(save_arm, inputs, origins, arm, cols, hp, seed, fingerprint)
                for arm, cols in arms.items() for seed in spatial.pa.SEEDS]
        paths = [future.result() for future in as_completed(jobs)]
    summary = summaries(paths)
    summary.reset_index().to_csv(OUTPUT / "resumen_metricas.csv", index=False)
    report = {"experimento": STUDY, "parametros": hp, "horizontes": {
        str(h): {"variantes": {arm: {"metricas": v} for arm, v in rows.droplevel("horizonte").to_dict("index").items()}}
        for h, rows in summary.groupby(level="horizonte")}}
    path = OUTPUT / "manifiesto.json"
    archive.write_json(path, {"huella": fingerprint, **info})
    run = archive.tracking.log_report(
        STUDY, report, metrics_path=path, output_dir=OUTPUT, gold_dir=archive.GOLD, data_quality=quality,
        log_datasets=False, tracking_uri=f"sqlite:///{archive.MLFLOW_DB.as_posix()}",
        fingerprint=fingerprint, description="Contraste factorial de clima y predictores de casos con Poisson común.",
    )
    archive.write_json(path, {"huella": fingerprint, "mlflow_run": run, **info})


if __name__ == "__main__":
    main()
