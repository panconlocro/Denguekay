"""Evaluate the CHIRTS midpoint and diurnal range on the archived common folds."""

from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

import run_chirts_resolution as chirts
from run_symmetric_tuning import validate_final


archive = chirts.archive
REFERENCE = chirts.OUTPUT
OUTPUT = chirts.WEATHER_OUTPUT / "sensibilidad_rango_diurno"
GEOGRAPHY = chirts.WEATHER_OUTPUT / "insumos" / "geografia_distritos.csv"
PROTOCOL = Path(__file__).resolve().parents[1] / "protocolo_rango_diurno_chirts.md"
STUDY = "v3_confirmados_rango_diurno_chirts"
PAIRS = (
    ("chirts_medio_rango", "chirts_medio"),
    ("chirts_medio_rango", "chirts_005"),
    ("chirts_medio", "clima_sin_temperatura"),
)


def fit_one(inputs, origins, name, columns, hp, seed, fingerprint):
    dest = OUTPUT / f"{name}_s{seed}"
    if dest.exists():
        if json.loads((dest / "control.json").read_text())["huella"] != fingerprint:
            raise ValueError(f"Checkpoint incompatible: {dest}")
        return dest
    pred = archive.original.p3.predict_blocks_weighted(
        inputs["matrices"], origins, chirts.BLOCK_LIST, seed, columns, hp)
    fits = pred.attrs.pop("ajustes").assign(semilla=seed)
    table = archive.closure.full_table(pred, fits, name, seed)
    check = archive.closure.check_table(table)
    if (table.duplicated(archive.closure.KEY).any() or check["calibrada_sin_platt"]
            or check["alpha_nulos"] or check["platt_diferencia_maxima"] > 1e-12
            or check["conteo_diferencia_maxima"] > 1e-12):
        raise ValueError(f"Pronósticos inválidos: {name}, semilla {seed}")
    with TemporaryDirectory(dir=OUTPUT) as directory:
        path = Path(directory)
        table.to_csv(path / "predicciones.csv.gz", index=False)
        fits.to_csv(path / "ajustes.csv", index=False)
        archive.closure.block_metrics(table).to_csv(path / "metricas.csv", index=False)
        archive.write_json(path / "control.json", {"huella": fingerprint, "filas": len(table), **check})
        path.rename(dest)
    return dest


def summarize(metrics):
    scores = metrics.pivot(index=["bloque", "horizonte", "semilla"],
                           columns="variante", values=["brier", "auprc"])
    comparisons = []
    for candidate, reference in PAIRS:
        delta = scores["brier", candidate] - scores["brier", reference]
        comparisons.append(pd.DataFrame({
            "delta_brier": delta,
            "delta_brier_relativo": delta / scores["brier", reference],
            "delta_ap": scores["auprc", candidate] - scores["auprc", reference],
        }).reset_index().assign(candidata=candidate, referencia=reference))
    by_seed = pd.concat(comparisons, ignore_index=True)
    keys = ["candidata", "referencia", "horizonte"]
    by_season = by_seed.groupby([*keys, "bloque"], as_index=False)[
        ["delta_brier", "delta_brier_relativo", "delta_ap"]].median()
    test = by_season.loc[by_season.bloque.isin([f"temporada_{s}" for s in chirts.SEASONS])]
    subset = [test.assign(temporada_omitida="ninguna")]
    for season in chirts.SEASONS:
        subset.append(test.loc[test.bloque.ne(f"temporada_{season}")].assign(temporada_omitida=str(season)))
    summary = pd.concat(subset).groupby([*keys, "temporada_omitida"], as_index=False).agg(
        delta_brier=("delta_brier", "mean"), delta_brier_relativo=("delta_brier_relativo", "mean"),
        delta_ap=("delta_ap", "mean"), temporadas=("delta_brier", "count"),
        favorables=("delta_brier", lambda x: int(x.lt(0).sum())),
    )
    by_seed.to_csv(OUTPUT / "contrastes_por_semilla.csv", index=False)
    by_season.to_csv(OUTPUT / "contrastes_por_temporada.csv", index=False)
    summary.to_csv(OUTPUT / "resumen_y_sensibilidad.csv", index=False)


def main():
    source = json.loads((REFERENCE / "resultados.json").read_text())
    archived, _, quality, inputs = chirts.training_data()
    origins, original, hp = chirts.prepare(inputs, GEOGRAPHY)
    climate = {p.name: archive.sha256(p) for p in
               (chirts.WEEKLY, chirts.ERA5, chirts.SILVER_CHIRPS_PRECIP, chirts.SILVER_ENSO)}
    device = archive.device.xgboost_settings()
    if (source["insumos_climaticos"] != climate or source["geografia"] != archive.sha256(GEOGRAPHY)
            or source["insumos_epidemiologicos"] != archived["configuracion"]["insumos"]
            or source["hiperparametros"] != hp or source["variantes"] != original
            or source["semillas"] != list(chirts.protocol.SEEDS) or source["entorno"] != device):
        raise ValueError("La configuración actual difiere del contraste de resolución archivado")
    high, low = origins.tmax_fina, origins.tmin_fina
    np.testing.assert_array_equal(high.isna(), low.isna())
    origins = origins.assign(temperatura_punto_medio=(high + low) / 2, temperatura_rango=high - low)
    observed = origins.temperatura_rango.notna()
    if not observed.any() or origins.loc[observed, "temperatura_rango"].lt(0).any():
        raise ValueError("Rango diurno inválido")
    np.testing.assert_allclose(
        (origins.temperatura_punto_medio + origins.temperatura_rango / 2)[observed],
        high[observed], atol=1e-12, rtol=0)
    np.testing.assert_allclose(
        (origins.temperatura_punto_medio - origins.temperatura_rango / 2)[observed],
        low[observed], atol=1e-12, rtol=0)

    base = [*original["clima_sin_temperatura"], "temperatura_punto_medio"]
    arms = {"chirts_medio": base, "chirts_medio_rango": [*base, "temperatura_rango"]}
    reference_paths = [REFERENCE / f"{name}_s{seed}"
                       for name in ("chirts_005", "clima_sin_temperatura") for seed in chirts.protocol.SEEDS]
    for path in reference_paths:
        if json.loads((path / "control.json").read_text())["huella"] != source["huella"]:
            raise ValueError(f"Referencia incompatible: {path}")
    details = {
        "codigo": archive.sha256(Path(__file__)), "codigo_resolucion": archive.sha256(Path(chirts.__file__)),
        "protocolo": archive.sha256(PROTOCOL), "manifest_referencia": archive.sha256(REFERENCE / "resultados.json"),
        "huella_referencia": source["huella"], "semillas": source["semillas"], "entorno": device,
        "variantes": arms, "hiperparametros": hp, "origenes": len(origins),
        "origenes_con_rango": int(observed.sum()), "insumos_climaticos": climate,
        "insumos_epidemiologicos": source["insumos_epidemiologicos"],
        "geografia": source["geografia"],
        "predicciones_referencia": {path.name: archive.sha256(path / "predicciones.csv.gz")
                                    for path in reference_paths},
    }
    fingerprint = hashlib.sha256(json.dumps(details, sort_keys=True).encode()).hexdigest()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    print(f"GE, procedencia y disponibilidad verificadas. {observed.sum()} orígenes con rango.", flush=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = [pool.submit(fit_one, inputs, origins, name, columns, hp, seed, fingerprint)
                for seed in chirts.protocol.SEEDS for name, columns in arms.items()]
        new_paths = []
        for task in as_completed(jobs):
            path = task.result()
            new_paths.append(path)
            print(f"Ajustado {path.name} ({len(new_paths)}/{len(jobs)})", flush=True)

    metrics = validate_final([*new_paths, *reference_paths], inputs)
    metrics.to_csv(OUTPUT / "metricas_por_bloque.csv", index=False)
    summarize(metrics)
    test = metrics.loc[metrics.bloque.isin([f"temporada_{s}" for s in chirts.SEASONS])]
    report = {"experimento": STUDY, "parametros": hp, "horizontes": {}}
    for h in archive.HORIZONS:
        scores = test.loc[test.horizonte.eq(h)].groupby(["variante", "bloque"])[["brier", "auprc"]]
        by_arm = scores.median().groupby("variante").mean().to_dict("index")
        report["horizontes"][str(h)] = {"variantes": {a: {"metricas": m} for a, m in by_arm.items()}}
    manifest = OUTPUT / "resultados.json"
    details.update(huella=fingerprint, calidad_datos=quality)
    archive.write_json(manifest, details)
    details["mlflow_run"] = archive.tracking.log_report(
        STUDY, report, metrics_path=manifest, output_dir=OUTPUT, gold_dir=archive.GOLD, data_quality=quality,
        log_datasets=False, tracking_uri=f"sqlite:///{archive.MLFLOW_DB.as_posix()}", fingerprint=fingerprint,
        description="Sensibilidad pareada al rango diurno de CHIRTS con el calendario común de confirmados.",
    )
    archive.write_json(manifest, details)
    print(f"Resultados: {OUTPUT} | MLflow {details['mlflow_run']}", flush=True)


if __name__ == "__main__":
    main()
