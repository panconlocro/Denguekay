"""Persistence baseline of the V4 on the acceptance block ``temporadas_2022_2026`` (HU0007-1, RQ5).

The V4 is judged against persistence: the forecast of the target week ``t`` is the cases observed at the cutoff week
``t - h``. This module computes that comparator for each horizon on the SAME district-weeks as the V4 (the out-of-sample
rows of the seasons 2022 to 2026 of the archived file of the seed 17, with their observed cases and thresholds):

- classification: alert = 1 when ``casos(t - h) > umbral de brote de t`` and ``casos(t - h) >= 2`` (the rule that labels
  the outbreaks, ``metrics.alerts_from_counts``), scored with Precision, Recall and F1 against ``brote``;
- regression: the forecast is ``casos(t - h)``, scored with MAE and RMSE in cases.

It checks, before saying anything, that the V4 ratios against this persistence reproduce the ones the card of the V4
publishes (0.001 of tolerance) and that every horizon has the 16 965 rows and 2 478 positives of the block; if not, it
stops. It reads the files of the frozen package, writes nothing to ``data/`` and touches no MLflow store unless
``--registrar`` is given (the run is then named ``persistencia · V4 · temporadas_2022_2026``).

The persistence of the paper is another comparator: a calibrated probabilistic persistence. This one is the deterministic
rule of the protocol (the last count against the threshold of the target week).
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys

import pandas as pd

from denguekay.config.paths import MODEL_REGISTRY, V4_FROZEN
from denguekay.evaluation.metrics import alert_metrics, alerts_from_counts, count_metrics

BLOCK = "temporadas_2022_2026"
EXPECTED_ROWS = 16_965
EXPECTED_POSITIVES = 2_478
TOLERANCE = 0.001
MINIMUM_CASES = 2          # ``OUTBREAK_RULE["minimo_casos"]`` of the label of the V4
RUN_NAME = f"persistencia · V4 · {BLOCK}"
EXPERIMENT = "denguekay/persistencia_v4"
METRICS = ("precision", "recall", "f1", "mae", "rmse")
INPUTS = ("observaciones.csv.gz", "oos_b3_s{seed}.csv.gz", "paquete.json")


class BaselineMismatch(ValueError):
    """The comparator does not reproduce what the card of the V4 publishes, or the block is not the published one."""


def read_inputs(folder=V4_FROZEN):
    """The package config, its observations and the joined out-of-sample table of the acceptance block."""
    from denguekay.serving.demo_b3_v4 import ACCEPTANCE_SEASONS, SEASON_BLOCKS, joined_predictions, read_bundle

    folder = Path(folder)
    config, _ = read_bundle(folder)   # every file is checked against the package's own manifest
    data = pd.read_csv(folder / "observaciones.csv.gz", dtype={"ubigeo": str}, parse_dates=["semana_inicio"])
    _, table = joined_predictions(folder, data, config["semilla_demo"])
    seasons = table[table.bloque.isin(SEASON_BLOCKS)]
    return config, seasons[seasons.bloque.isin(ACCEPTANCE_SEASONS)]


def ratio(value, reference):
    """``value / reference``, or ``None`` when the reference is 0 (the ratio is then undefined)."""
    return None if reference == 0 else value / reference


def evaluate(table):
    """Per horizon: ``n``, ``positivos``, the five persistence metrics and the V4 ratios against its MAE and RMSE."""
    result = {}
    for horizon, group in table.groupby("horizonte"):
        alerts = alerts_from_counts(group.persistencia.to_numpy(), group.umbral_brote_casos.to_numpy(), MINIMUM_CASES)
        scores = alert_metrics(group.brote.astype(int).to_numpy(), alerts.astype(int))
        persistence = count_metrics(group.casos_Dengue, group.persistencia)
        v4 = count_metrics(group.casos_Dengue, group.casos_estimados)
        result[int(horizon)] = {
            "n": int(len(group)), "positivos": int(group.brote.sum()), "alertas": int(alerts.sum()),
            "precision": scores["precision"], "recall": scores["recall"], "f1": scores["f1"],
            "mae": persistence["mae"], "rmse": persistence["rmse"],
            "mae_v4": v4["mae"], "rmse_v4": v4["rmse"],
            "razon_mae_v4": ratio(v4["mae"], persistence["mae"]), "razon_rmse_v4": ratio(v4["rmse"], persistence["rmse"]),
        }
    return result


def published_ratios(registry=MODEL_REGISTRY):
    card = json.loads((Path(registry) / "v4" / "ficha.json").read_text(encoding="utf-8"))["aceptacion"]
    return {int(h): {"mae": values["mae_sobre_persistencia"], "rmse": values["rmse_sobre_persistencia"]}
            for h, values in card["por_horizonte"].items()}


def verify(result, published):
    """Raise ``BaselineMismatch`` unless the block and the ratios are the published ones; return the differences."""
    if sorted(result) != sorted(published):
        raise BaselineMismatch(f"Horizontes distintos: {sorted(result)} frente a {sorted(published)}")
    differences = {}
    for horizon, values in result.items():
        if (values["n"], values["positivos"]) != (EXPECTED_ROWS, EXPECTED_POSITIVES):
            raise BaselineMismatch(f"h = {horizon}: {values['n']} filas y {values['positivos']} positivos; el bloque "
                                   f"publicado tiene {EXPECTED_ROWS} y {EXPECTED_POSITIVES}")
        if values["razon_mae_v4"] is None or values["razon_rmse_v4"] is None:
            raise BaselineMismatch(f"h = {horizon}: el error de la persistencia es 0 y la razón no se define")
        differences[horizon] = {
            "mae": round(values["razon_mae_v4"] - published[horizon]["mae"], 6),
            "rmse": round(values["razon_rmse_v4"] - published[horizon]["rmse"], 6)}
        for name, difference in differences[horizon].items():
            if abs(difference) > TOLERANCE:
                raise BaselineMismatch(
                    f"h = {horizon}: la razón {name.upper()} de la V4 frente a esta persistencia es "
                    f"{values['razon_' + name + '_v4']:.4f} y la ficha publica {published[horizon][name]} "
                    f"(diferencia {difference:+.4f}, más de {TOLERANCE})")
    return differences


def input_hashes(config, folder=V4_FROZEN):
    folder = Path(folder)
    names = [name.format(seed=config["semilla_demo"]) for name in INPUTS]
    return {name: hashlib.sha256((folder / name).read_bytes()).hexdigest() for name in names}


def build_report(folder=V4_FROZEN, registry=MODEL_REGISTRY):
    config, table = read_inputs(folder)
    result = evaluate(table)
    differences = verify(result, published_ratios(registry))
    return {"bloque": BLOCK, "semilla": config["semilla_demo"], "umbral_probabilidad_v4": 0.5,
            "regla_alerta": f"casos(t-h) > umbral de brote de t y casos(t-h) >= {MINIMUM_CASES}",
            "horizontes": result, "diferencia_con_la_ficha": differences, "insumos_sha256": input_hashes(config, folder)}


def log_to_mlflow(report, *, tracking_uri=None):
    """One parent run, ``persistencia · V4 · temporadas_2022_2026``, with the five metrics of each horizon, the seed and the
    hashes of the inputs; one child run per horizon. Returns the parent run id."""
    import mlflow

    from denguekay.model.tracking import environment_tags, set_experiment

    experiment_id = set_experiment(EXPERIMENT, tracking_uri)
    tags = {"experimento": "persistencia_v4", "bloque": BLOCK, **environment_tags(),
            **{f"sha256.{name}": digest for name, digest in report["insumos_sha256"].items()}}
    with mlflow.start_run(experiment_id=experiment_id, run_name=RUN_NAME, tags=tags) as parent:
        mlflow.log_params({"semilla": report["semilla"], "bloque": BLOCK, "regla_alerta": report["regla_alerta"],
                           "comparador": "persistencia determinista (último conteo al corte)"})
        mlflow.log_dict(report, "reporte/persistencia_v4.json")
        for horizon, values in report["horizontes"].items():
            metrics = {name: values[name] for name in METRICS if values[name] is not None}
            mlflow.log_metrics({f"h{horizon}.{name}": value for name, value in metrics.items()})
            mlflow.log_metrics({f"h{horizon}.razon_mae_v4": values["razon_mae_v4"],
                                f"h{horizon}.razon_rmse_v4": values["razon_rmse_v4"]})
            with mlflow.start_run(experiment_id=experiment_id, run_name=f"h{horizon} · persistencia", nested=True,
                                  tags={"horizonte": str(horizon), "nivel": "variante", "bloque": BLOCK}):
                mlflow.log_params({"horizonte": horizon, "semilla": report["semilla"], "n": values["n"],
                                   "positivos": values["positivos"]})
                mlflow.log_metrics(metrics)
        return parent.info.run_id


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registrar", action="store_true",
                        help="Registra una corrida en MLflow (MLFLOW_TRACKING_URI, o mlflow.db en la raíz si no está definida)")
    args = parser.parse_args(argv)
    try:
        report = build_report()
    except BaselineMismatch as error:
        print(f"La persistencia no reproduce la ficha de la V4: {error}", file=sys.stderr)
        return 2
    if args.registrar:
        report["mlflow_run_id"] = log_to_mlflow(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
