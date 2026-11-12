"""Repeat the frozen V3 paired evaluation on confirmed-only observations."""

from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from time import perf_counter

import pandas as pd

from denguekay.config.paths import (
    GOLD, MLFLOW_DB, MODELS, RESEARCH, ROOT, SILVER, SILVER_EPI_HISTORICAL, SILVER_INTEGRATED,
    SILVER_METEO_ERA5_LAND_2000_2026, SILVER_SALA,
)
from denguekay.data.loading import load_integrated
from denguekay.data.validation.gx_quality import validate_modeling_inputs
from denguekay.data.validation.integrated_expectations import coverage_path
from denguekay.evaluation import protocol as evaluation
from denguekay.features.long_history import long_inputs
from denguekay.features.model_input_contract import audit_handoff
from denguekay.model import device, frozen_configs, tracking

sys.path.insert(0, str(RESEARCH / "06_model_improvement" / "code"))
import phase_2026 as original
import phase_v3_close as closure
import preregistration as rules

CONFIRMED = SILVER / "confirmados"
PANEL = CONFIRMED / SILVER_INTEGRATED.name
HISTORY = CONFIRMED / SILVER_EPI_HISTORICAL.name
SALA = CONFIRMED / SILVER_SALA.name
ERA5 = SILVER_METEO_ERA5_LAND_2000_2026
OUTPUT = MODELS / "experimentos" / "mejora_modelo" / "v3_confirmados"
HORIZONS = (2, 3, 4)
BLOCK_KEY = ["bloque", "horizonte"]
OBSERVATIONS = closure.KEY + ["origen_cierre", "casos_Dengue", "brote", "umbral_brote_casos", "persistencia"]
PREDICTIONS = {"V3": "v3", "L + 5a": "l5a"}
METRICS = ("brier", "auprc", "f1_050", "precision_050", "recall_050", "mae", "rmse", "razon_mae", "razon_rmse")


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def records(frame):
    return json.loads(frame.to_json(orient="records", date_format="iso", double_precision=15))


def write_json(path, payload):
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def verify_reference_features(columns):
    """On original inputs, compare the reusable feature path with the archived implementation."""
    old = original.inputs_2026()
    old_origins, _ = original.add_climate(old)
    reusable = long_inputs(load_integrated(SILVER_INTEGRATED), ERA5)
    key = ["ubigeo", "origen_cierre"]
    for field, cols in (
        ("casos", ["ubigeo", "semana_inicio", "casos_Dengue"]),
        ("etiquetas", ["ubigeo", "semana_inicio", "brote", "umbral_brote_casos"]),
    ):
        pd.testing.assert_frame_equal(
            old[field][cols].reset_index(drop=True), reusable[field][cols].reset_index(drop=True),
            check_dtype=False, rtol=0, atol=1e-12,
        )
    fields = key + columns + [f"semana_inicio_h{h}" for h in HORIZONS]
    pd.testing.assert_frame_equal(
        old_origins[fields].reset_index(drop=True), reusable["origenes"][fields].reset_index(drop=True),
        check_dtype=False, rtol=0, atol=1e-12,
    )
    return old["casos"]


def fit_one(inputs, variant, seed, columns, hp, config_id):
    destination = OUTPUT / f"{PREDICTIONS[variant]}_s{seed}"
    if destination.exists():
        existing = json.loads((destination / "evaluacion.json").read_text())
        if existing["corrida"] != config_id:
            raise ValueError(f"El checkpoint {destination.name} corresponde a otros insumos o código")
        print(f"Reusando checkpoint {variant}, semilla {seed}", flush=True)
        return
    start = perf_counter()
    print(f"Iniciando {variant}, semilla {seed}", flush=True)
    result = original.run_variant(inputs, inputs["origenes"], columns, hp, seeds=(seed,))
    evaluated = result["evaluaciones"][seed]
    table = closure.full_table(result["predicciones"][seed], result["ajustes"], variant, seed)
    checks = closure.check_table(table)
    if (table.duplicated(closure.KEY).any() or checks["alpha_nulos"] or checks["calibrada_sin_platt"]
            or checks["platt_diferencia_maxima"] > 1e-12 or checks["conteo_diferencia_maxima"] > 1e-12):
        raise ValueError(f"Predicciones inválidas para {variant}, semilla {seed}: {checks}")
    with TemporaryDirectory(prefix=f"{destination.name}-", dir=OUTPUT) as directory:
        pending = Path(directory)
        table.to_csv(pending / "predicciones.csv.gz", index=False)
        result["ajustes"].to_csv(pending / "ajustes.csv", index=False)
        write_json(pending / "evaluacion.json", {
            "corrida": config_id, "segundos": round(perf_counter() - start, 2), "filas": len(table),
            "comprobaciones": checks, "metricas": records(evaluated["metricas"]),
            "antelacion": records(evaluated["antelacion"]),
        })
        pending.rename(destination)
    print(f"Terminó {variant}, semilla {seed}: {len(table):,} predicciones", flush=True)


def summarize(inputs, seeds):
    evaluations, medians, cells, lead_rows, checks = {}, {}, [], [], {}
    reference = pd.read_csv(closure.OUT / closure.FILES["V3"], usecols=["semilla", *closure.KEY],
                            dtype={"ubigeo": "string"}, parse_dates=["semana_inicio"])
    first_pair = None
    for variant, slug in PREDICTIONS.items():
        evaluations[variant], checks[variant] = {}, {}
        for seed in seeds:
            folder = OUTPUT / f"{slug}_s{seed}"
            row = json.loads((folder / "evaluacion.json").read_text())
            checks[variant][seed] = {k: row[k] for k in ("segundos", "filas", "comprobaciones")}
            table = pd.read_csv(folder / "predicciones.csv.gz", usecols=OBSERVATIONS + ["filas_calibracion", "positivos_calibracion"],
                                dtype={"ubigeo": "string"}, parse_dates=["semana_inicio", "origen_cierre"])
            archived = reference.loc[reference.semilla.eq(seed), closure.KEY]
            pd.testing.assert_frame_equal(table[closure.KEY], archived.reset_index(drop=True))
            obs = table[OBSERVATIONS].reset_index(drop=True)
            if first_pair is None:
                first_pair = obs
                cuts = closure.cutoff_table(inputs, inputs["origenes"], table)
                fields = ["filas_calibracion", "positivos_calibracion"]
                aligned = table.merge(cuts[BLOCK_KEY + fields], on=BLOCK_KEY, suffixes=("", "_corte"), validate="many_to_one")
                if any(not aligned[field].eq(aligned[f"{field}_corte"]).all() for field in fields):
                    raise ValueError("Las filas de calibración no coinciden con los cortes cronológicos")
            else:
                pd.testing.assert_frame_equal(obs, first_pair)
            metrics = pd.DataFrame(row["metricas"])
            lead = pd.DataFrame(row["antelacion"])
            evaluations[variant][seed] = {"metricas": metrics, "antelacion": lead}
            cells.append(metrics.assign(variante=variant, semilla=seed))
            lead_rows.append(lead.assign(variante=variant, semilla=seed))
        medians[variant] = evaluation.seed_median([e["metricas"] for e in evaluations[variant].values()])
    outbreaks = original.outbreak_weeks(inputs["serie"])
    verdict = original.compare_2026(
        {"evaluaciones": evaluations["V3"]}, {"evaluaciones": evaluations["L + 5a"]}, outbreaks,
    )
    pd.concat(lead_rows, ignore_index=True).to_csv(OUTPUT / "antelacion_por_episodio.csv.gz", index=False)
    return {
        "comprobaciones": checks, "cortes": records(cuts),
        "metricas_por_bloque_y_semilla": records(pd.concat(cells, ignore_index=True)),
        "medianas_por_bloque": {variant: records(rows) for variant, rows in medians.items()},
        "semanas_elevadas_temporada_2026": outbreaks,
        "comparacion_pareada": {name: records(value) if isinstance(value, pd.DataFrame) else bool(value)
                               for name, value in verdict.items()},
    }, medians


def main():
    start = perf_counter()
    seeds = tuple(rules.SEEDS)
    if device.xgboost_settings()["device"] != "cpu":
        raise ValueError("Esta corrida local usa XGBoost en CPU")
    config = frozen_configs.CONFIG_V3
    columns = closure.variant_columns()
    hp = closure.hyperparameters()
    if columns["V3"] != config["columnas"] or any(hp[k] != v for k, v in frozen_configs.V3_HYPERPARAMETERS.items()):
        raise ValueError("La configuración del cierre difiere de la V3 congelada")
    inputs_hashes = {p.relative_to(ROOT).as_posix(): sha256(p) for p in (
        PANEL, HISTORY, SALA, coverage_path(PANEL), ERA5, GOLD / "manifest_fase6.json",
        ROOT / "data/reference/catalogo_ubigeos_piura.csv",
    )}
    gold = audit_handoff(silver_path=PANEL, history_path=HISTORY)
    quality = validate_modeling_inputs(silver_path=PANEL)
    print("Gold y silver confirmados validados", flush=True)
    baseline_cases = verify_reference_features(columns["V3"])
    print("Ruta de variables idéntica al cierre original al usar sus insumos", flush=True)

    sala = pd.read_csv(SALA, dtype={"ubigeo": "string"})
    if not sala.tipo_dx.eq("C").all():
        raise ValueError("La Sala debe contener solo casos confirmados")
    inputs = long_inputs(load_integrated(PANEL), ERA5, sala=sala, history_path=HISTORY)
    newest = inputs["casos"]
    compared = baseline_cases.merge(newest, on=["ubigeo", "anio", "semana", "semana_inicio"],
                                    how="outer", indicator=True, suffixes=("_original", "_confirmados"),
                                    validate="one_to_one")
    if not compared._merge.eq("both").all():
        raise ValueError("El cambio de fuente alteró la grilla temporal de la evaluación")
    years = compared.assign(cambios=compared.casos_Dengue_original.ne(compared.casos_Dengue_confirmados))
    counts = years.groupby("anio")[["casos_Dengue_original", "casos_Dengue_confirmados", "cambios"]].sum().reset_index()
    climate = original.guard_coverage(inputs["origenes"], columns["V3"], inputs["ultima_semana"])
    if not climate["pasa"]:
        raise ValueError(f"Hay orígenes incompletos: {climate}")
    fingerprints = {
        "insumos": inputs_hashes, "script": sha256(Path(__file__)), "parametros": hp,
        "entorno": device.xgboost_settings(), "software": tracking.environment_tags(),
        "codigo_cierre": sha256(Path(closure.__file__)),
    }
    config_id = hashlib.sha256(json.dumps(fingerprints, sort_keys=True).encode()).hexdigest()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    print(f"Entradas verificadas: {len(newest):,} distrito-semanas, {len(original.blocks())} bloques, "
          f"provisionales {inputs['semanas_provisionales']}", flush=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        tasks = [
            pool.submit(fit_one, inputs, variant, seed, features, hp, config_id)
            for seed in seeds for variant, features in columns.items()
        ]
        for task in as_completed(tasks):
            task.result()

    result, medians = summarize(inputs, seeds)
    result.update({
        "experimento": "v3_confirmados", "semillas": list(seeds), "configuracion": fingerprints,
        "variables": columns, "calidad_datos": quality, "gold_filas": gold["horizontes"]["2"]["filas"],
        "semanas_provisionales": inputs["semanas_provisionales"], "cobertura_origenes": climate,
        "casos_por_anio": records(counts), "segundos": round(perf_counter() - start, 2),
    })
    path = OUTPUT / "resultados.json"
    write_json(path, result)
    blocks = original.block_names(rules.SEASON_2026_DECIDING)
    report = {"experimento": "v3_confirmados", "parametros": hp, "horizontes": {}}
    for horizon in HORIZONS:
        report["horizontes"][str(horizon)] = {"variantes": {
            variant: {"metricas": frame.loc[frame.horizonte.eq(horizon) & frame.bloque.isin(blocks),
                                            list(METRICS)].median().dropna().to_dict()}
            for variant, frame in medians.items()
        }}
    run_id = tracking.log_report(
        "v3_confirmados", report, metrics_path=path, output_dir=OUTPUT, gold_dir=GOLD,
        data_quality=quality, fingerprint=config_id, log_datasets=False,
        tracking_uri=f"sqlite:///{MLFLOW_DB.as_posix()}",
        description="Repetición pareada del cierre V3 con casos confirmados y el trial 191 fijo.",
    )
    result["mlflow_run"] = run_id
    write_json(path, result)
    print(f"Resultados completos: {path} | MLflow {run_id}", flush=True)


if __name__ == "__main__":
    main()
