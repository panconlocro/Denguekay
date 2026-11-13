"""Complete the 2 × 2 crossing of geographic controls and climate timing."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path

import pandas as pd

import run_spatial_controls as spatial


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("geografia", type=Path)
    args = parser.parse_args()
    root = spatial.OUTPUT
    fixed = json.loads((root / "resultados.json").read_text())
    archived, _, quality, inputs = spatial.training_data()
    origins, arms, hp, _ = spatial.prepare(inputs, args.geografia)
    archive = spatial.archive
    if (fixed["variantes"] != arms or fixed["hiperparametros"] != hp
            or fixed["geografia"] != archive.sha256(args.geografia)
            or fixed["entorno"] != archive.device.xgboost_settings()
            or fixed["epidemiologia"] != archived["configuracion"]["insumos"]
            or fixed["codigo"] != archive.sha256(Path(spatial.__file__))
            or any(fixed["fuentes"][p.name] != archive.sha256(p)
                   for p in (spatial.SILVER_CHIRPS_PRECIP, spatial.SILVER_ENSO))):
        raise ValueError("El puente no coincide con los controles espaciales existentes")
    combinations = {
        "b3_hist_geo": [*arms["historia_geo"], *(f"{c}_hist" for c in spatial.B3)],
        "b3_obs_sin_geo": [*arms["historia"], *(f"{c}_obs" for c in spatial.B3)],
    }
    spatial.OUTPUT = root / "puente_geografia_disponibilidad"
    out = spatial.OUTPUT
    out.mkdir(exist_ok=True)
    info = {"controles": fixed["huella"], "combinaciones": combinations,
            "codigo": archive.sha256(Path(__file__)), "protocolo": archive.sha256(
                Path(__file__).resolve().parents[1] / "protocolo_puente_geografia_disponibilidad.md")}
    fingerprint = hashlib.sha256(json.dumps(info, sort_keys=True).encode()).hexdigest()
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(spatial.save_fit, inputs, origins, arm, cols, hp, seed, fingerprint)
                for arm, cols in combinations.items() for seed in spatial.pa.SEEDS]
        paths = []
        for future in as_completed(jobs):
            paths.append(future.result())
            print(f"Puente {len(paths)}/{len(jobs)} {paths[-1].name}", flush=True)
    old_paths = [root / f"{arm}_s{seed}" for arm in ("historia", "b3_historico", "b3_obs")
                 for seed in spatial.pa.SEEDS]
    geo_paths = spatial.compatible_geo(arms, args.geografia, archived, hp)
    metrics = spatial.assemble([*paths, *old_paths, *geo_paths], inputs)
    cells = metrics.pivot(index=["bloque", "horizonte", "semilla"], columns="variante", values="brier")
    details = []
    for clock, geo, variant, reference in (
        ("historico", False, "b3_historico", "historia"),
        ("historico", True, "b3_hist_geo", "historia_geo"),
        ("al_cierre", False, "b3_obs_sin_geo", "historia"),
        ("al_cierre", True, "b3_obs", "historia_geo"),
    ):
        change = cells[variant] - cells[reference]
        result = pd.DataFrame({"delta": change, "relativo": change / cells[reference]})
        details.append(result.groupby(level=["bloque", "horizonte"]).median().reset_index().assign(
            reloj=clock, geografia=geo, variante=variant, referencia=reference))
    detail = pd.concat(details, ignore_index=True)
    detail.to_csv(out / "contrastes_por_temporada.csv", index=False)
    decisive = detail.loc[detail.bloque.isin([f"temporada_{s}" for s in spatial.DECIDING])]
    summary = (pd.concat([decisive.assign(sin_2026=False),
                          decisive.loc[decisive.bloque.ne("temporada_2026")].assign(sin_2026=True)])
               .groupby(["reloj", "geografia", "horizonte", "sin_2026"], as_index=False)
               .agg(delta=("delta", "mean"), relativo=("relativo", "mean"), temporadas=("delta", "size")))
    summary.to_csv(out / "resumen.csv", index=False)
    full = out / "resultados.json"
    archive.write_json(full, {"huella": fingerprint, **info})
    variants = {}
    for h, block in metrics.loc[metrics.bloque.isin(decisive.bloque)].groupby("horizonte"):
        vals = block.groupby(["variante", "bloque"])[["brier", "auprc"]].median().groupby("variante").mean()
        variants[str(h)] = {"variantes": {a: {"metricas": v} for a, v in vals.to_dict("index").items()}}
    run = archive.tracking.log_report(
        "v3_confirmados_puente_geografia_disponibilidad", {"horizontes": variants},
        metrics_path=full, output_dir=out, gold_dir=archive.GOLD, data_quality=quality,
        log_datasets=False, tracking_uri=f"sqlite:///{archive.MLFLOW_DB.as_posix()}",
        fingerprint=fingerprint, description="Contraste factorial retrospectivo de geografía y disponibilidad.",
    )
    archive.write_json(full, {"huella": fingerprint, **info, "mlflow_run": run})
    print("MLflow", run, flush=True)


if __name__ == "__main__":
    main()
