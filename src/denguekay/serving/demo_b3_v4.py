"""Publish a previously fitted B3 package on an isolated demo database."""

from datetime import date
import hashlib
import json
from pathlib import Path
import time

import pandas as pd

from denguekay.config.paths import DISTRICT_COORDS, UBIGEO_CATALOG
from denguekay.data.calendar import mmwr_epi_week
from denguekay.data.processing.epi_sala import load_ubigeo_catalog
from denguekay.db.session import transaction
from denguekay.evaluation.metrics import alert_metrics, count_metrics
from denguekay.model.tracking import log_report
from denguekay.serving.geometries import read_boundaries
from denguekay.serving.load_data import LoadBatch, persist_load, prepare_districts, prepare_weeks, week_id
from denguekay.serving.package import package_code
from denguekay.serving.predictors import v4_b3_obs as v4
from denguekay.serving.predictors.base import BuiltPackage, OOS_COLUMNS, VersionSpec
from denguekay.serving.publish import publish_to_db

FIRST_WEEK = pd.Timestamp("2024-12-29")  # week 1 of MMWR 2025, covered by the Sala
TASKS = {"clasificacion": "clf", "regresion": "reg"}
ALGORITHM = "xgboost_multisalida_bn"
SEASON_BLOCKS = tuple(f"temporada_{year}" for year in range(2018, 2041))   # later seasons only exist in a refit package
ACCEPTANCE_SEASONS = tuple(f"temporada_{year}" for year in range(2022, 2027))
ACCEPTANCE_BLOCK = "temporadas_2022_2026"


def digest(content):
    return hashlib.sha256(content).hexdigest()


def read_bundle(folder):
    raw = (folder / "paquete.json").read_bytes()
    config = json.loads(raw)
    if config["version"] != "v4-b3" or config["horizontes"] != [2, 3, 4] or config["corte_alerta"] != 0.5:
        raise ValueError("El directorio debe contener el paquete b3 congelado para el paper")
    for name, expected in config["archivos"].items():
        if Path(name).name != name or digest((folder / name).read_bytes()) != expected:
            raise ValueError(f"Artefacto V4 distinto al manifiesto: {name}")
    return config, digest(raw)


def prepare_observations(folder, config, manifest_hash):
    data = pd.read_csv(folder / "observaciones.csv.gz", dtype={"ubigeo": str}, parse_dates=["semana_inicio"])
    cutoff = pd.Timestamp(config["corte"])
    visible = data.loc[data.semana_inicio.ge(FIRST_WEEK)].copy()
    keys = ["ubigeo", "semana_inicio"]
    calendar = mmwr_epi_week(visible.semana_inicio)
    districts = load_ubigeo_catalog(UBIGEO_CATALOG)
    expected_dates = pd.date_range(FIRST_WEEK, cutoff, freq="W-SUN")
    if (visible.duplicated(keys).any() or set(visible.ubigeo) != set(districts.ubigeo)
            or not visible.groupby("ubigeo").size().eq(len(expected_dates)).all()
            or set(visible.semana_inicio) != set(expected_dates)
            or not calendar.anio_epi.eq(visible.anio).all() or not calendar.semana_epi.eq(visible.semana).all()
            or not visible.brote.isin((0, 1)).all()
            or not visible.casos_Dengue.ge(0).all() or not visible.umbral_brote_casos.ge(0).all()):
        raise ValueError("El panel confirmado de la demo V4 no cubre todas las semanas distritales")
    provinces, district_records = prepare_districts(districts, pd.read_csv(DISTRICT_COORDS), {}, read_boundaries())
    weeks = prepare_weeks(date(2017, 1, 1), cutoff + pd.Timedelta(weeks=52))
    rows = [{
        "ubigeo": row.ubigeo, "id_semana": week_id(row.anio, row.semana), "casos_dengue": int(row.casos_Dengue),
        "brote": bool(row.brote), "umbral_brote_casos": round(float(row.umbral_brote_casos), 2),
        "fuente_casos": "sala_situacional", "estado_cobertura": "verificado",
    } for row in visible.itertuples()]
    quality = {"exito": True, "suites": {
        name: {"evaluadas": n, "exitosas": n, "fallidas_n": 0, "porcentaje_exito": 100.0}
        for name, n in config["validaciones"].items()
    }}
    load = LoadBatch(provinces, district_records, weeks, rows, {"paquete_v4": manifest_hash}, quality, cutoff.date())
    return load, data


def block_metrics(block, group):
    """Metrics of one block of archived predictions: the same calculation for a season and for the pooled block."""
    y, p = group.brote, group.probabilidad_brote
    scores = alert_metrics(y, p.ge(0.5), score=p)
    return {
        "bloque": block, "n": len(group), "positivos": int(y.sum()),
        "clasificacion": {"umbral_probabilidad": 0.5, "alerta_directa": {
            metric: scores[metric] for metric in ("precision", "recall", "f1")},
            "auprc": scores["auprc"], "brier": float((p-y).pow(2).mean())},
        "regresion": {"conteos": count_metrics(group.casos_Dengue, group.casos_estimados)},
        "persistencia": {"conteos": count_metrics(group.casos_Dengue, group.persistencia)},
    }


def joined_predictions(folder, data, seed):
    """The archived out-of-sample file (as read) and its calibrated rows joined to the observed panel and to the
    persistence of their origin week: the table every block metric and the temporal partition are computed from."""
    archive = pd.read_csv(folder / f"oos_b3_s{seed}.csv.gz", dtype={"ubigeo": str},
                          parse_dates=["semana_inicio", "origen_cierre"])
    prior = archive.dropna(subset=["probabilidad_calibrada"]).rename(
        columns={"probabilidad_calibrada": "probabilidad_brote", "conteo_publicado": "casos_estimados"})
    table = prior.merge(data, on=["ubigeo", "semana_inicio"], validate="many_to_one")
    origin = data[["ubigeo", "semana_inicio", "casos_Dengue"]].assign(
        origen_cierre=lambda d: d.semana_inicio + pd.Timedelta(days=6))
    table = table.merge(origin[["ubigeo", "origen_cierre", "casos_Dengue"]].rename(
        columns={"casos_Dengue": "persistencia"}), on=["ubigeo", "origen_cierre"], validate="many_to_one")
    return archive, table


def temporal_partition(archive, table):
    """Per horizon and block of ``archived_predictions``: target weeks, test rows and the cutoff of the fit.

    The protocol fits each season once, at its first origin (``refit_v4.block_predictions``: the earliest origin among
    the three horizons, ``horizon_strategies._common_cutoffs``), so that cutoff is the earliest ``origen_cierre`` of
    the block in the archived file. Against the ``ajustes.csv`` of the V4 archive it matches in every block (the seasons
    2008 to 2026 and the partial one after them). The pooled acceptance block has no single fit: it publishes the rule and each season's cutoff."""
    seasons = table[table.bloque.isin(SEASON_BLOCKS)]
    cutoffs = archive[archive.bloque.isin(SEASON_BLOCKS)].groupby("bloque").origen_cierre.min()
    day = lambda value: str(pd.Timestamp(value).date())
    summary = lambda group: {"primera_semana_objetivo": day(group.semana_inicio.min()),
                             "ultima_semana_objetivo": day(group.semana_inicio.max()), "n_prueba": int(len(group))}
    result = {}
    for (h, block), group in seasons.groupby(["horizonte", "bloque"]):
        result.setdefault(int(h), {})[block] = {"bloque": block, "tipo": "temporada", **summary(group),
                                                "corte_ajuste": day(cutoffs[block])}
    for h, group in seasons[seasons.bloque.isin(ACCEPTANCE_SEASONS)].groupby("horizonte"):
        used = sorted(group.bloque.unique())
        result[int(h)][ACCEPTANCE_BLOCK] = {
            "bloque": ACCEPTANCE_BLOCK, "tipo": "agregado", **summary(group), "corte_ajuste": None,
            "regla_ajuste": "Sin un único ajuste: cada temporada se ajusta una vez, en su primer origen, con las "
                            "etiquetas cerradas a esa fecha; el bloque junta las semanas de prueba de "
                            f"{', '.join(b.removeprefix('temporada_') for b in used)}",
            "cortes_por_temporada": {b.removeprefix("temporada_"): day(cutoffs[b]) for b in used}}
    return result


def archived_predictions(folder, data, seed):
    _, table = joined_predictions(folder, data, seed)
    results = {}
    # Use the archived seasonal blocks within the validated observed panel.
    seasons = table[table.bloque.isin(SEASON_BLOCKS)]
    for (h, block), group in seasons.groupby(["horizonte", "bloque"]):
        results.setdefault(int(h), {})[block] = block_metrics(block, group)
    # HU0007-4 (US v1.4): out-of-sample district-weeks of the seasons 2022 to 2026 pooled in one block.
    pooled = seasons[seasons.bloque.isin(ACCEPTANCE_SEASONS)]
    for h, group in pooled.groupby("horizonte"):
        results[int(h)][ACCEPTANCE_BLOCK] = block_metrics(ACCEPTANCE_BLOCK, group)
    return table.loc[table.semana_inicio.ge(FIRST_WEEK), OOS_COLUMNS], results


def mlflow_horizons(by_horizon, seed):
    """The ``horizontes`` of the report that ``tracking.log_report`` walks: per horizon, the variant ``b3_obs_s<seed>`` with
    one fold per block (each season and the pooled acceptance block).

    ``log_report`` logs one child run per horizon x variant and one per fold; a report without ``variantes`` leaves the
    horizons empty in MLflow. The folds are the block metrics already computed (nothing is recalculated); the persistence
    block keeps its ``persistencia`` section, which MLflow logs with the ``pers_`` prefix."""
    variant = f"b3_obs_s{seed}"
    horizons = {}
    for horizon, blocks in by_horizon.items():
        folds = [{**metrics, "horizonte": int(horizon), "variante": variant, "bloque": block,
                  "tipo": "agregado" if block == ACCEPTANCE_BLOCK else "prueba", "n_prueba": metrics["n"]}
                 for block, metrics in blocks.items()]
        horizons[str(horizon)] = {"variantes": {variant: {"folds": folds}}}
    return horizons


def build_package(folder, config, manifest_hash, data):
    seed = config["semilla_demo"]
    model_name = f"b3_obs_s{seed}"
    model = config["modelos"][model_name]
    horizons = tuple(config["horizontes"])
    columns = config["columnas"]["b3_obs"]
    records = model["por_horizonte"]
    parameters = {
        "corte": config["corte"], "columnas": columns,
        "dispersion": dict(zip(map(str, horizons), model["alphas"], strict=True)),
        "platt": {h: [r["platt"]["a"], r["platt"]["b"]] for h, r in records.items()},
        "mezcla": {h: r["peso_modelo"] for h, r in records.items()},
    }
    files = {v4.BOOSTER: (folder / f"{model_name}.ubj").read_bytes(),
             v4.SNAPSHOT: (folder / v4.SNAPSHOT).read_bytes(),
             v4.PARAMETERS: json.dumps(parameters, sort_keys=True, allow_nan=False).encode()}
    forecasts, by_horizon = archived_predictions(folder, data, seed)
    origin = {"configuracion": "v4-b3", "entrenamiento_corte": config["corte"], "semilla": seed,
              "congelado_utc": config["congelado_utc"], "sha256_paquete_paper": manifest_hash,
              "alcance": "Demo retrospectiva de casos confirmados de Piura"}
    versions = []
    for h in horizons:
        metrics = {"bloques": by_horizon[h], "procedencia": f"Predicciones retrospectivas de b3 por temporada y semilla {seed}."}
        for task, prefix in TASKS.items():
            versions.append(VersionSpec(task, h, f"v4-{prefix}-h{h}-", {
                "algoritmo": ALGORITHM, "variables": columns, "hiperparametros": config["hiperparametros"],
                "metricas": metrics, "umbral_probabilidad": 0.50 if task == "clasificacion" else None,
                "sha256_dataset": config["archivos"]["observaciones.csv.gz"], "reproducibilidad": origin,
            }))
    return BuiltPackage(
        kind=v4.KIND, code=package_code("v4", files), horizons=horizons, files=files,
        variables={str(h): {task: columns for task in TASKS} for h in horizons}, interval_level=None,
        options={"configuracion": "v4-b3", "formulacion": config["formulacion"]}, versions=versions, oos=forecasts,
        oos_detail=origin, fingerprint=manifest_hash,
        report={"experimento": "demo_v4_b3", "parametros": config["hiperparametros"], **origin,
                "horizontes": mlflow_horizons({h: by_horizon[h] for h in horizons}, seed)},
    )


def publish_frozen_demo(engine, folder, storage, demo_dir):
    start = time.perf_counter()
    config, sha = read_bundle(folder)
    load, data = prepare_observations(folder, config, sha)
    built = build_package(folder, config, sha, data)
    path = demo_dir / "reporte_v4.json"
    path.write_text(json.dumps(built.report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    run_id = log_report("demo_v4_b3", built.report, metrics_path=path, output_dir=demo_dir,
                        data_quality=load.validacion_gx, log_datasets=False, fingerprint=sha)
    with transaction(engine) as session:
        persist_load(session, load)
    return publish_to_db(engine, load, built, run_id, sha, storage, start,
                         run_inference=True, select_experimental=True)
