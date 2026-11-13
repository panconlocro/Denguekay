"""Freeze the confirmed-case B3 paper specification and its matched comparator."""

from argparse import ArgumentParser
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import json
import subprocess

import numpy as np
import pandas as pd
from xgboost import XGBRegressor

import run_experiment as archive
import run_spatial_controls as spatial
from denguekay.config.paths import SILVER_CHIRPS_PRECIP
from denguekay.data.calendar import mmwr_epi_week
from denguekay.data.validation.gx_quality import validate_modeling_inputs
from denguekay.evaluation import protocol as pa
from denguekay.features.long_history import long_inputs, OUTBREAK_RULE
from denguekay.model import probabilistic_output as sp
from denguekay.serving.predictors import v2_e3_s4 as v2, v3_l5a_d3 as v3

DAY = pd.Timedelta(days=1)
ARMS = ("b3_obs", "historia_geo")
HORIZONS = (2, 3, 4)
DEMO_SEED = 17


def read(path, dates=()):
    return pd.read_csv(path, dtype={"ubigeo": str}, parse_dates=list(dates), float_precision="round_trip")


def calibrate(data, p):
    fit = pa.fit_platt(p, data.brote.to_numpy(int))
    return {"a": float(fit.coef_[0, 0]), "b": float(fit.intercept_[0]), "filas": len(data),
            "ultimo_cierre": str((data.semana_inicio.max() + 6 * DAY).date())}


def prior_rows(path, cutoff):
    pred = read(path / "predicciones.csv.gz", ("semana_inicio", "origen_cierre"))
    pred = pred.loc[(pred.semana_inicio + 6 * DAY).le(cutoff)].copy()
    fits = read(path / "ajustes.csv", ("corte",))
    pred = pred.merge(fits[["bloque", "corte"]], on="bloque", validate="many_to_one")
    if pred.empty or pred.corte.gt(pred.origen_cierre).any() or pred.duplicated(["ubigeo","semana_inicio","horizonte"]).any():
        raise ValueError("Invalid out-of-sample calibration history")
    return pred


def freeze(output, geography, cutoff, created):
    source = archive.OUTPUT / "controles_espaciales"
    report = json.loads((source / "resultados.json").read_text())
    if archive.sha256(geography) != report["geografia"]:
        raise ValueError("Geography differs from the paper archive")
    for rel, sha in report["epidemiologia"].items():
        if archive.sha256(archive.ROOT / rel) != sha:
            raise ValueError(f"Changed epidemiological input: {rel}")
    for path in (SILVER_CHIRPS_PRECIP, spatial.SILVER_ENSO):
        if archive.sha256(path) != report["fuentes"][path.name]:
            raise ValueError(f"Changed climate input: {path.name}")
    with TemporaryDirectory() as folder:
        quality = validate_modeling_inputs(silver_path=archive.PANEL, gx_directory=Path(folder))
    panel = archive.load_integrated(archive.PANEL)
    sala = read(archive.SALA)
    if not sala.tipo_dx.eq("C").all():
        raise ValueError("Unexpected diagnosis in the Sala")
    inputs = long_inputs(panel, archive.ERA5, sala=sala, history_path=archive.HISTORY)
    if cutoff != pd.Timestamp(inputs["ultima_semana"]) + 6 * DAY:
        raise ValueError("The cutoff must match the last validated confirmed-case week in the paper archive")
    geo = read(geography)
    rain = read(SILVER_CHIRPS_PRECIP, ("semana_inicio", "fecha_disponible"))
    era = archive.original.era5_2026(panel).assign(fecha_disponible=lambda d: d.semana_inicio + 13 * DAY)
    weather = spatial.weekly_fields(rain, era, lag=2)
    origin_start = cutoff - 6 * DAY
    original_columns = {arm: report["variantes"][arm] for arm in ARMS}
    climate_columns = {col: f"{col}_obs" for col in spatial.B3}
    origins = (inputs["origenes"].assign(semana_origen=lambda d: d.origen_cierre - 6 * DAY)
               .merge(geo[["ubigeo", *spatial.GEO]], on="ubigeo", validate="many_to_one")
               .merge(weather[["ubigeo","semana_origen",*spatial.B3]].rename(columns=climate_columns),
                      on=["ubigeo","semana_origen"], how="left", validate="many_to_one"))
    train = origins[(origins.semana_inicio_h4 + 6 * DAY).le(cutoff)]
    if train.empty or not np.isfinite(train[original_columns["b3_obs"]].to_numpy(float)).all():
        raise ValueError("Incomplete training features")
    cases = inputs["casos"].loc[inputs["casos"].semana_inicio.le(origin_start)].copy()
    now, reasons = v2._base_6(cases, SimpleNamespace(fecha_fin=cutoff.date()))
    if reasons:
        raise ValueError(f"Incomplete demo histories: {reasons}")
    current = (now.join(v2._b3(cases, origin_start)).join(geo.set_index("ubigeo")[spatial.GEO])
               .join(weather.loc[weather.semana_origen.eq(origin_start)].set_index("ubigeo")[spatial.B3].rename(columns=climate_columns)))
    columns = original_columns["b3_obs"]
    if len(current) != 65 or not np.isfinite(current[columns].to_numpy(float)).all():
        raise ValueError("Incomplete latest-origin B3 features")
    for start in (origin_start - pd.Timedelta(weeks=4), origin_start - pd.Timedelta(weeks=2)):
        at = start + 6 * DAY
        past = cases[cases.semana_inicio.le(start)]
        base, missing = v2._base_6(past, SimpleNamespace(fecha_fin=at.date()))
        same = (base.join(v2._b3(past, start)).join(geo.set_index("ubigeo")[spatial.GEO])
                .join(weather.loc[weather.semana_origen.eq(start)].set_index("ubigeo")[spatial.B3].rename(columns=climate_columns)))
        reference = origins.loc[origins.origen_cierre.eq(at)].set_index("ubigeo")[columns]
        if missing or set(same.index) != set(reference.index):
            raise ValueError("Origin-vector support differs from training")
        pd.testing.assert_frame_equal(same[columns].sort_index(), reference.sort_index(), check_dtype=False, rtol=0, atol=1e-12)
    rule = {"minimo_casos": OUTBREAK_RULE["minimo_casos"], "anios_previos": OUTBREAK_RULE["anios_previos"],
            "k_desviaciones": OUTBREAK_RULE["multiplicador"]}
    thresholds = v3.target_thresholds(cases, origin_start, list(current.index), rule)
    snapshot = current[columns].join(thresholds.rename(columns={h:f"umbral_h{h}" for h in HORIZONS}))
    snapshot.to_csv(output / "origen.csv", float_format="%.17g")
    observations = cases.merge(inputs["etiquetas"][["ubigeo","semana_inicio","brote","umbral_brote_casos"]],
                              on=["ubigeo","semana_inicio"], how="left", validate="one_to_one")
    observations.loc[observations.anio.ge(2017)].to_csv(output / "observaciones.csv.gz", index=False,
                                                        compression={"method":"gzip","mtime":0})
    config = {"version": "v4-b3", "corte": str(cutoff.date()), "congelado_utc": created,
              "formulacion": spatial.FORM, "columnas": original_columns, "hiperparametros":report["hiperparametros"],
              "semillas": report["semillas"], "semilla_demo": DEMO_SEED, "corte_alerta": 0.50,
              "regla_brote": rule, "horizontes": list(HORIZONS), "modelos": {},
              "validaciones": {k:v["evaluadas"] for k,v in quality["suites"].items()},
              "fuentes": report["epidemiologia"] | report["fuentes"] | {"geografia":report["geografia"]},
              "commit_piura":subprocess.check_output(["git","rev-parse","HEAD"],cwd=archive.ROOT,text=True).strip()}
    epi = json.loads((archive.OUTPUT / "resultados.json").read_text())
    baseline = dict(zip(pa.SEEDS, spatial.compatible_geo(original_columns, geography, epi, report["hiperparametros"]), strict=True))
    margin = sp.e3_margin(origins, spatial.FORM)
    for arm in ARMS:
        for seed in config["semillas"]:
            name = f"{arm}_s{seed}"
            prior_path = baseline[seed] if arm == "historia_geo" else source / name
            previous = prior_rows(prior_path, cutoff)
            f = sp.fit_e3(origins, cutoff, seed, spatial.FORM, original_columns[arm], [],
                          sp.e3_parameters(report["hiperparametros"]), margin)
            if f.train.semana_inicio_h4.max() + 6 * DAY > cutoff:
                raise ValueError("Training label closes after the frozen cutoff")
            model_file = output / f"{name}.ubj"
            f.regressor.save_model(model_file)
            restored = XGBRegressor()
            restored.load_model(model_file)
            kind = sp.FORMULATIONS[spatial.FORM]["conteo"]
            m = sp.e3_margin(snapshot.reset_index(), spatial.FORM)
            np.testing.assert_array_equal(sp.predict_count(f.regressor,snapshot[original_columns[arm]],kind,m),
                                          sp.predict_count(restored,snapshot[original_columns[arm]],kind,m))
            record = {"brazo":arm,"semilla":seed,"sha256":archive.sha256(model_file),"alphas":f.alphas,
                      "filas_entrenamiento":len(f.train),
                      "ultimo_cierre_h4":str((f.train.semana_inicio_h4.max()+6*DAY).date()),
                      "archivo_calibracion_sha256":archive.sha256(prior_path/"predicciones.csv.gz"),
                      "por_horizonte":{}}
            for h, history in previous.groupby("horizonte"):
                record["por_horizonte"][str(h)] = {
                    "platt":calibrate(history,history.probabilidad_cruda),
                    "peso_modelo":archive.closure.p5.fit_w(history.mu_modelo.to_numpy(),history.persistencia.to_numpy(),
                                                           history.casos_Dengue.to_numpy())}
            config["modelos"][name] = record
            if arm == "b3_obs" and seed == DEMO_SEED:
                previous[["ubigeo","semana_inicio","horizonte","bloque","origen_cierre","probabilidad_calibrada",
                          "conteo_publicado"]].to_csv(output / "oos_b3_s17.csv.gz", index=False,
                                                     compression={"method":"gzip","mtime":0})
            print(name,len(f.train), flush=True)
    config["persistencia_prob"] = {}
    for h, history in prior_rows(baseline[DEMO_SEED], cutoff).groupby("horizonte"):
        odds = (history.persistencia + 0.5) / (sp.count_threshold(history.umbral_brote_casos) + 0.5)
        config["persistencia_prob"][str(h)] = calibrate(history,odds/(1+odds))
    config["archivos"] = {p.name:archive.sha256(p) for p in sorted(output.iterdir())}
    archive.write_json(output / "paquete.json", config)


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--salida", type=Path, required=True)
    parser.add_argument("--geografia", type=Path, required=True)
    parser.add_argument("--corte", required=True)
    args = parser.parse_args()
    path = args.salida.resolve()
    if path.exists():
        parser.error("Elija una carpeta nueva para preservar el paquete anterior")
    path.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=path.parent) as parent:
        temp = Path(parent) / path.name
        temp.mkdir()
        freeze(temp, args.geografia, pd.Timestamp(args.corte), datetime.now(timezone.utc).isoformat(timespec="seconds"))
        temp.rename(path)


if __name__ == "__main__":
    main()
