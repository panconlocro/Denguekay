"""Fits of experiments that need their own path (cached):
``python run_extra.py cuatro_brazos|nb2|confirmados_probables|horizontes_largos|retrasos|clasificador``.

- ``cuatro_brazos`` (E5): the four arms of ``evaluate_climate_without_history`` (formulation S4_s2, no offset).
- ``nb2`` (E7): NB2 regression with case history and geography, with and without exactly the b3 climate block.
- ``confirmados_probables`` (E6b): the primary pair refitted on confirmed + probable cases (protocol D5).
- ``horizontes_largos`` (E8): a separate two-output model for 8 and 12 weeks (``protocolo_e8.md``).
- ``retrasos`` (E12): the primary pair under two simulated reporting-delay scenarios (``protocolo_revision.md``).
- ``clasificador`` (E13): the primary pair with a direct classifier of elevated weeks (``protocolo_revision.md``).
"""

import argparse
import hashlib
import inspect
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd

import common as c

FOUR_ARMS_DIR = c.ARMS_DIR / "sin_margen"
NB2_DIR = c.ARMS_DIR / "nb2"
CP_DIR = c.ARMS_DIR / "confirmados_probables"
CP_HISTORY = c.OUTPUT / "insumos" / "epi_piura_semanal_confirmados_probables.csv"
NATIONAL = c.ROOT / "data" / "bronze" / "epi" / "DatosDengueV2.csv"
REVISION = c.STUDY / "protocolo_revision.md"


def code_hash(*functions) -> str:
    return hashlib.sha256("".join(inspect.getsource(f) for f in functions).encode()).hexdigest()


def four_arms(inputs, origins, arms, hp, workers):
    import evaluate_climate_without_history as ecwh

    climate = [f"{x}_obs" for x in c.spatial.B3]
    geo = ["semana_epi_seno", "semana_epi_coseno", *c.spatial.GEO]
    history = arms["historia_geo"]
    design = {"geografia": geo, "clima_geografia": [*geo, *climate], "historia_geografia": history,
              "clima_historia_geografia": [*history, *climate]}

    def job(arm, columns, seed):
        dest = FOUR_ARMS_DIR / f"{arm}_s{seed}"
        expected = c.fingerprint(arm, columns, hp, {"formulacion": ecwh.FORMULATION, "codigo_e5": code_hash(ecwh.fit_arm)})
        if (dest / "control.json").exists():
            if json.loads((dest / "control.json").read_text())["huella"] != expected:
                raise ValueError(f"Cached fit from another configuration: {dest}")
            return dest
        forecasts, cuts = ecwh.fit_arm(inputs, origins, columns, hp, seed)
        forecasts = forecasts.assign(variante=arm, semilla=seed)
        return c.save_table(dest, forecasts, cuts, expected)

    run(job, [(arm, cols, seed) for arm, cols in design.items() for seed in c.SEEDS], workers)
    (FOUR_ARMS_DIR / "diseno.json").write_text(json.dumps(design, indent=1), encoding="utf-8")


def nb2(inputs, origins, arms, hp, workers):
    import run_statistical_benchmarks as rsb

    history = arms["historia_geo"]
    design = {"nb_historia_geo": history, "nb_b3": [*history, *(f"{x}_obs" for x in c.spatial.B3)]}

    def job(arm, columns, seed):
        dest = NB2_DIR / f"{arm}_s{seed}"
        expected = c.fingerprint(arm, columns, hp, {"familia": "nb2", "codigo_e7": code_hash(rsb.fit_nb, rsb.nb_predictions)})
        if (dest / "control.json").exists():
            if json.loads((dest / "control.json").read_text())["huella"] != expected:
                raise ValueError(f"Cached fit from another configuration: {dest}")
            return dest
        pred, fits = rsb.nb_predictions(inputs, origins, columns, seed)
        table = c.archive.closure.full_table(pred, fits.assign(semilla=seed, regimen=None), arm, seed)
        guard = c.archive.closure.check_table(table)
        if guard["platt_diferencia_maxima"] > 1e-12 or guard["conteo_diferencia_maxima"] > 1e-12:
            raise ValueError(f"Invalid NB2 predictions: {arm}")
        return c.save_table(dest, table, fits, expected, guard)

    # The NB2 GLM has no randomness: one seed, as in study 08.
    run(job, [(arm, cols, 17) for arm, cols in design.items()], workers)
    (NB2_DIR / "diseno.json").write_text(json.dumps(design, indent=1), encoding="utf-8")


def confirmed_probable_counts() -> pd.DataFrame:
    """Weekly Piura counts of diagnoses C and P from the national file (``epi_cases`` rules, both codes)."""
    raw = pd.read_csv(NATIONAL, usecols=["departamento", "tipo_dx", "ubigeo", "ano", "semana"], dtype=str)
    keep = raw.departamento.str.strip().str.upper().eq("PIURA") & raw.tipo_dx.str.strip().str.upper().isin(["C", "P"])
    cases = raw.loc[keep, ["ubigeo", "ano", "semana", "tipo_dx"]].copy()
    cases["ubigeo"] = cases.ubigeo.str.strip().str.zfill(6)
    cases["anio"], cases["semana"] = cases.ano.astype(int), cases.semana.astype(int)
    if not cases.semana.between(1, 53).all():
        raise ValueError("Invalid weeks in the national file")
    return cases.groupby(["ubigeo", "anio", "semana"]).size().rename("casos_Dengue").reset_index()


def confirmed_probable_inputs():
    """Long inputs with C+P counts for 2000–2024; 2025–2026 stay as the confirmed series (protocol D5)."""
    counts = confirmed_probable_counts()
    history = counts[counts.anio.le(2016)]
    CP_HISTORY.parent.mkdir(parents=True, exist_ok=True)
    history.to_csv(CP_HISTORY, index=False)
    panel = c.archive.load_integrated(c.archive.PANEL)
    keys = ["ubigeo", "anio", "semana"]
    merged = panel[keys].assign(ubigeo=lambda d: d.ubigeo.astype(str)).merge(counts, on=keys, how="left")
    replace = panel.anio.le(2024).to_numpy()
    values = panel.casos_Dengue.to_numpy().copy()
    values[replace] = merged.casos_Dengue.fillna(0).to_numpy()[replace]
    panel = panel.assign(casos_Dengue=values.astype(panel.casos_Dengue.dtype))
    sala = pd.read_csv(c.archive.SALA, dtype={"ubigeo": "string"})
    inputs = c.archive.long_inputs(panel, c.archive.ERA5, sala=sala, history_path=CP_HISTORY)
    return inputs, counts


def confirmed_probable(workers):
    c.check_sources()
    inputs, counts = confirmed_probable_inputs()
    origins, arms, hp, _ = c.prepare(inputs)
    extra = {"casos": "C+P 2000-2024", "nacional_sha256": c.sha256(NATIONAL),
             "codigo_e6b": code_hash(confirmed_probable_counts, confirmed_probable_inputs)}
    c.fit_arms(inputs, origins, arms, hp, ["historia_geo", "b3_obs"], workers=workers, out_dir=CP_DIR, extra=extra)
    labels = inputs["etiquetas"]
    labels.to_csv(CP_DIR / "etiquetas.csv.gz", index=False)


def long_horizons(inputs, origins, arms, hp, workers):
    import e8

    long_origins = e8.with_long_targets(origins, inputs["etiquetas"])
    design = {"historia_geo_largo": arms["historia_geo"], "b3_obs_largo": arms["b3_obs"]}
    extra = {"e8": code_hash(e8.with_long_targets, e8.test_set, e8.fit_predict, e8.finish),
             "adenda": c.sha256(e8.ADDENDUM)}

    def job(arm, columns, seed):
        dest = e8.OUT_DIR / f"{arm}_s{seed}"
        expected = c.fingerprint(arm, columns, hp, extra)
        if (dest / "control.json").exists():
            if json.loads((dest / "control.json").read_text())["huella"] != expected:
                raise ValueError(f"Cached fit from another configuration: {dest}")
            return dest
        pred, records = e8.fit_predict(long_origins, columns, hp, seed)
        table, calibration = e8.finish(pred)
        calibration = calibration.rename(columns={"corte": "corte_calibracion"})
        records = records.merge(calibration, on=["bloque", "horizonte"], how="left", validate="one_to_one")
        return c.save_table(dest, table.assign(variante=arm, semilla=seed), records, expected)

    run(job, [(arm, cols, seed) for arm, cols in design.items() for seed in c.SEEDS], workers)
    (e8.OUT_DIR / "diseno.json").write_text(json.dumps(design, indent=1), encoding="utf-8")


def reporting_delays(inputs, origins, arms, hp, workers):
    import reporting_delays as rd

    code = code_hash(rd.weekly, rd.reported, rd.weeks_since_case, rd.vintage_history, rd.origin_counts, rd.delayed)
    for scenario, completeness in rd.SCENARIOS.items():
        delayed_inputs, delayed_origins = rd.delayed(inputs, origins, completeness)
        extra = {"retraso": scenario, "completitud": completeness, "semilla_retraso": rd.SEED, "codigo_e12": code,
                 "adenda": c.sha256(REVISION)}
        c.fit_arms(delayed_inputs, delayed_origins, arms, hp, ["historia_geo", "b3_obs"], workers=workers,
                   out_dir=rd.OUT_DIR / scenario, extra=extra)


def direct_classifier(inputs, origins, arms, hp, workers):
    import direct_classifier as dc

    with_k = dc.with_thresholds(origins, inputs["matrices"])
    design = {"historia_geo_clasificador": arms["historia_geo"], "b3_obs_clasificador": arms["b3_obs"]}
    extra = {"formulacion": dc.FORMULATION, "umbrales": dc.THRESHOLDS, "adenda": c.sha256(REVISION),
             "codigo_e13": code_hash(dc.with_thresholds, dc.predict, dc.fit_arm)}
    run(lambda arm, columns, seed: dc.fit_arm(inputs, with_k, arm, columns, hp, seed, extra),
        [(arm, cols, seed) for arm, cols in design.items() for seed in c.SEEDS], workers)
    (dc.OUT_DIR / "diseno.json").write_text(json.dumps(design, indent=1), encoding="utf-8")


def run(job, jobs, workers):
    done = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(job, *args) for args in jobs]
        for future in as_completed(futures):
            done.append(future.result())
            print(f"{len(done)}/{len(jobs)} {done[-1].name}", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("what", choices=["cuatro_brazos", "nb2", "confirmados_probables", "horizontes_largos",
                                         "retrasos", "clasificador"])
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    start = time.time()
    if args.what == "confirmados_probables":
        confirmed_probable(args.workers)
    else:
        inputs, _ = c.load_inputs(validate=False)
        origins, arms, hp, _ = c.prepare(inputs)
        runner = {"cuatro_brazos": four_arms, "nb2": nb2, "horizontes_largos": long_horizons,
                  "retrasos": reporting_delays, "clasificador": direct_classifier}[args.what]
        runner(inputs, origins, arms, hp, args.workers)
    print(f"Done in {(time.time() - start) / 60:.1f} min", flush=True)


if __name__ == "__main__":
    main()
