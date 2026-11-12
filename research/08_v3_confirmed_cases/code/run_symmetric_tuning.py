"""Give b3, d3 and epidemiology with geography the same development search."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
import time

import numpy as np
import pandas as pd
from scipy.stats import qmc

import run_spatial_controls as spatial
import phase_hp_tuning as hp_study

archive = spatial.archive
ARMS = ("historia_geo", "b3_obs", "d3_obs")
OUTPUT = archive.OUTPUT / "ajuste_simetrico"
STUDY = "v3_confirmados_ajuste_simetrico"
SEED = 17
DESIGN_SEED = 20261110
STAGES = {
    "cribado": ((2008, 2009, 2012, 2013), (2009, 2012, 2013)),
    "finalistas": (archive.rules.HP_TUNING_TRAIN_SEASONS, archive.rules.HP_TUNING_OBJECTIVE_SEASONS),
}
SPACE = {
    **archive.rules.HP_TUNING_SPACE,
    "max_depth": ("int", 2, 6, False),
    "n_estimators": ("int", 100, 700, False),
}


def configurations(inherited):
    design = qmc.Sobol(d=len(SPACE), scramble=True, seed=DESIGN_SEED).random_base2(m=4)
    configs = {"heredados": dict(inherited)}
    for i, point in enumerate(design, 1):
        hp = {}
        for (name, (kind, low, high, log)), u in zip(SPACE.items(), point, strict=True):
            if kind == "int":
                hp[name] = low + math.floor(u * (high - low + 1))
            else:
                hp[name] = float(np.exp(np.log(low) + u * np.log(high / low))) if log else low + float(u) * (high - low)
        configs[f"sobol_{i:02}"] = hp
    return configs


def stage_definition(stage):
    development, scored = STAGES[stage]
    if set(development) & set(spatial.DECIDING) or not set(scored) <= set(development):
        raise ValueError(f"Temporadas de ajuste incompatibles: {stage}")
    blocks = [b for b in spatial.BLOCK_LIST if b[1] == "temporada" and b[2] in development]
    if len(blocks) != len(development):
        raise ValueError(f"Bloques de desarrollo faltantes: {stage}")
    return blocks, [f"temporada_{s}" for s in scored]


def evaluate_candidate(inputs, origins, columns, hp, stage, arm, candidate, fingerprint):
    dest = OUTPUT / stage / f"{arm}_{candidate}.csv"
    if dest.exists():
        cached = pd.read_csv(dest)
        if not cached.huella.eq(fingerprint).all() or cached.empty:
            raise ValueError(f"Checkpoint incompatible: {dest}")
        return cached
    blocks, scored = stage_definition(stage)
    start = time.perf_counter()
    pred, _ = spatial.predict(inputs, origins, blocks, columns, hp, SEED)
    cells = hp_study.cell_scores(pred, blocks=scored)
    if len(cells) != len(scored) * len(archive.HORIZONS) or not np.isfinite(cells.brier).all():
        raise ValueError(f"Brier incompleto: {stage}, {arm}, {candidate}")
    cells = cells.assign(variante=arm, candidato=candidate, huella=fingerprint,
                         segundos=time.perf_counter() - start)
    with TemporaryDirectory(dir=dest.parent) as tmp:
        path = Path(tmp) / dest.name
        cells.to_csv(path, index=False, float_format="%.17g")
        path.rename(dest)
    return cells


def evaluate_stage(inputs, origins, arms, configs, selection, stage, fingerprint, workers):
    (OUTPUT / stage).mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        jobs = {
            pool.submit(evaluate_candidate, inputs, origins, arms[arm], configs[c], stage, arm, c, fingerprint): (arm, c)
            for arm, candidates in selection.items() for c in candidates
        }
        tables = []
        for future in as_completed(jobs):
            tables.append(future.result())
            print(f"{stage} {len(tables)}/{len(jobs)}", *jobs[future], flush=True)
    cells = pd.concat(tables, ignore_index=True)
    keys = ["variante", "bloque", "horizonte"]
    refs = cells.loc[cells.candidato.eq("heredados"), [*keys, "brier"]].rename(columns={"brier": "brier_heredado"})
    relative = cells.merge(refs, on=keys, how="left", validate="many_to_one")
    if not relative.brier_heredado.gt(0).all():
        raise ValueError("Falta una referencia de Brier positiva")
    ranking = (relative.assign(razon=lambda d: d.brier / d.brier_heredado)
               .groupby(["variante", "candidato"], as_index=False)
               .agg(objetivo=("razon", "mean"), segundos=("segundos", "max"))
               .sort_values(["variante", "objetivo", "candidato"]))
    relative.sort_values([*keys, "candidato"]).to_csv(OUTPUT / f"{stage}_celdas.csv", index=False)
    ranking.to_csv(OUTPUT / f"{stage}_ranking.csv", index=False)
    return ranking


def validate_final(paths, inputs):
    check, metrics = None, []
    for path in sorted(paths):
        frame = pd.read_csv(path / "predicciones.csv.gz", usecols=archive.OBSERVATIONS + ["filas_calibracion"],
                            dtype={"ubigeo": str}, parse_dates=["semana_inicio", "origen_cierre"])
        if check is None:
            check = frame
        else:
            pd.testing.assert_frame_equal(check, frame)
        metrics.append(pd.read_csv(path / "metricas.csv"))
    cut, _ = spatial.cut_table(inputs)
    actual = check.groupby(["bloque", "horizonte"], as_index=False).agg(
        filas_calibracion=("filas_calibracion", "first"),
        n_calibracion=("filas_calibracion", "nunique"))
    audit = cut.merge(actual, on=["bloque", "horizonte"], how="outer", validate="one_to_one")
    if (len(check) != 194805 or not audit.n_calibracion.eq(1).all()
            or not audit.filas_calibracion.eq(audit.filas_elegibles_calibracion).all()):
        raise ValueError("Predicciones incompatibles con el calendario común")
    return pd.concat(metrics, ignore_index=True)


def report_comparisons(metrics):
    cells = metrics.pivot(index=["bloque", "horizonte", "semilla"], columns="variante", values="brier")
    pairs = (("b3_obs", "historia_geo"), ("d3_obs", "historia_geo"), ("b3_obs", "d3_obs"))
    rows = []
    for arm, reference in pairs:
        delta = cells[arm] - cells[reference]
        values = pd.DataFrame({"delta": delta, "relativo": delta / cells[reference]})
        rows.append(values.groupby(level=["bloque", "horizonte"]).median().reset_index().assign(
            variante=arm, referencia=reference))
    detail = pd.concat(rows, ignore_index=True)
    detail.to_csv(OUTPUT / "contrastes_por_temporada.csv", index=False)
    chosen = detail.loc[detail.bloque.isin([f"temporada_{s}" for s in spatial.DECIDING])]
    variants = [chosen.assign(omitida="ninguna")]
    for season in spatial.DECIDING:
        variants.append(chosen.loc[chosen.bloque.ne(f"temporada_{season}")].assign(omitida=str(season)))
    sensitivity = (pd.concat(variants, ignore_index=True).groupby(
        ["variante", "referencia", "horizonte", "omitida"], as_index=False).agg(
            delta=("delta", "mean"), relativo=("relativo", "mean"),
            temporadas=("delta", "size"), temporadas_mejor=("delta", lambda x: int(x.lt(0).sum()))))
    sensitivity.to_csv(OUTPUT / "resumen_y_sensibilidad.csv", index=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("geografia", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    archived, _, quality, inputs = spatial.training_data()
    origins, arms, inherited, _ = spatial.prepare(inputs, args.geografia)
    configs = configurations(inherited)
    protocol_path = Path(__file__).resolve().parents[1] / "protocolo_ajuste_simetrico.md"
    info = {
        "candidatos": configs, "etapas": STAGES, "variantes": {a: arms[a] for a in ARMS},
        "semilla_desarrollo": SEED, "semillas_evaluacion": list(spatial.pa.SEEDS),
        "protocolo": archive.sha256(protocol_path), "codigo": archive.sha256(Path(__file__)),
        "control_espacial": archive.sha256(Path(spatial.__file__)),
        "entorno": archive.device.xgboost_settings(), "geografia": archive.sha256(args.geografia),
        "epidemiologia": archived["configuracion"]["insumos"],
        "clima": {p.name: archive.sha256(p) for p in (spatial.SILVER_CHIRPS_PRECIP, spatial.SILVER_ENSO)},
    }
    fingerprint = hashlib.sha256(json.dumps(info, sort_keys=True).encode()).hexdigest()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    archive.write_json(OUTPUT / "diseno.json", {"huella": fingerprint, **info})
    screen = evaluate_stage(inputs, origins, arms, configs, dict.fromkeys(ARMS, tuple(configs)),
                            "cribado", fingerprint, args.workers)
    promoted = {arm: ("heredados", *g.loc[g.candidato.ne("heredados"), "candidato"].head(4))
                for arm, g in screen.groupby("variante")}
    final = evaluate_stage(inputs, origins, arms, configs, promoted, "finalistas", fingerprint, args.workers)
    winners = final.groupby("variante").first().candidato.to_dict()
    archive.write_json(OUTPUT / "ganadores_desarrollo.json", winners)
    print("Ganadores de desarrollo", winners, flush=True)
    destinations = OUTPUT / "evaluacion"
    destinations.mkdir(exist_ok=True)
    # Reuse the spatial archive format but isolate output paths and fingerprints.
    spatial.OUTPUT = destinations
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        jobs = [pool.submit(spatial.save_fit, inputs, origins, arm, arms[arm], configs[c], seed, fingerprint)
                for arm, c in winners.items() for seed in spatial.pa.SEEDS]
        paths = []
        for future in as_completed(jobs):
            paths.append(future.result())
            print(f"evaluación {len(paths)}/{len(jobs)} {paths[-1].name}", flush=True)
    metrics = validate_final(paths, inputs)
    metrics.to_csv(OUTPUT / "metricas_por_bloque.csv", index=False)
    report_comparisons(metrics)
    chosen = metrics.loc[metrics.bloque.isin([f"temporada_{s}" for s in spatial.DECIDING])]
    horizons = {}
    for h, rows in chosen.groupby("horizonte"):
        vals = rows.groupby(["variante", "bloque"])[["brier", "auprc"]].median().groupby("variante").mean()
        horizons[str(h)] = {"variantes": {arm: {"metricas": v} for arm, v in vals.to_dict("index").items()}}
    report = {"experimento": STUDY, "parametros": {a: configs[c] for a, c in winners.items()}, "horizontes": horizons}
    results = {"huella": fingerprint, "ganadores": winners, "hiperparametros": report["parametros"], "calidad": quality}
    path = OUTPUT / "resultados.json"
    archive.write_json(path, results)
    results["mlflow_run"] = archive.tracking.log_report(
        STUDY, report, metrics_path=path, output_dir=OUTPUT, gold_dir=archive.GOLD, data_quality=quality,
        log_datasets=False, tracking_uri=f"sqlite:///{archive.MLFLOW_DB.as_posix()}", fingerprint=fingerprint,
        description="Ajuste por brazo con el mismo espacio, candidatos, semillas y temporadas de desarrollo.",
    )
    archive.write_json(path, results)
    print("MLflow", results["mlflow_run"], flush=True)


if __name__ == "__main__":
    main()
