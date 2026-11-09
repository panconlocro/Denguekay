"""Evaluate alternative V3 outbreak labels using the frozen Release predictions."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile

import numpy as np
import pandas as pd

from denguekay.config.paths import ROOT, SILVER_EPI_HISTORICAL, SILVER_INTEGRATED, SILVER_SALA, UBIGEO_CATALOG
from denguekay.data.ingestion.release_bundles import load_manifest, sha256_file
from denguekay.data.validation.gx_quality import validate_integrated_gx
from denguekay.evaluation import protocol as pa
from denguekay.evaluation.episodes import lead_time_summary
from denguekay.features.outbreak_label import future_outbreak_threshold
from denguekay.model import horizon_strategies, probabilistic_output, tracking

# Archived research is used only by this study, never by the package.
sys.path.insert(0, str(ROOT / "research/06_model_improvement/code"))
import phase0_diagnosis as history
import phase_2026 as season_2026
import phase_v3_close as v3
import preregistration as rules

STUDY = Path(__file__).resolve().parents[1]
OUTPUT = STUDY / "docs/metricas"
SCENARIOS = {"principal": (1.5, 5), "A": (2.0, 5), "B": (1.5, 3)}
VARIANTS = tuple(v3.FILES)
ROW_KEY = ["semilla", *v3.KEY]
CELL = ["horizonte", "bloque"]
CALIBRATION_COUNTS = ["filas_calibracion", "positivos_calibracion"]
COUNT_METRICS = ["mae", "rmse", "razon_mae", "razon_rmse"]
REPORTED = ["n", "positivos", "brier", "auprc", "f1_050", "precision_050", "recall_050",
            "vp_050", "fp_050", "fn_050", "f1_persistencia", "precision_persistencia", "recall_persistencia",
            *COUNT_METRICS]


def records(table: pd.DataFrame) -> list[dict]:
    return json.loads(table.to_json(orient="records", date_format="iso", double_precision=15))


def write_report(name: str, payload: dict) -> Path:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    destination = OUTPUT / name
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=OUTPUT, suffix=".tmp", delete=False) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    Path(handle.name).replace(destination)
    return destination


def release_inputs() -> dict[str, str]:
    manifest = load_manifest()
    expected = {item["ruta"]: item["sha256"] for bundle in manifest["paquetes"] for item in bundle["archivos"]}
    files = [SILVER_INTEGRATED, SILVER_EPI_HISTORICAL, SILVER_SALA, UBIGEO_CATALOG,
             *(v3.OUT / name for name in v3.FILES.values())]
    hashes = {}
    for path in files:
        relative = path.relative_to(ROOT).as_posix()
        hashes[relative] = sha256_file(path)
        if hashes[relative] != expected[relative]:
            raise ValueError(f"El insumo no coincide con el Release V3: {relative}")
    return hashes


def case_series() -> pd.DataFrame:
    panel = history.load_integrated()
    sala, _ = season_2026.sala_2026()
    added_2025 = season_2026.sala_missing_2025(panel)
    columns = ["ubigeo", "anio", "semana", "semana_inicio", "casos_Dengue"]
    cases, _ = history.long_case_series(pd.concat([panel[columns], added_2025, sala], ignore_index=True))
    return cases


def scenario_labels(cases: pd.DataFrame, multiplier: float, years: int) -> pd.DataFrame:
    targets = cases[cases.anio.ge(2005)].reset_index(drop=True)
    threshold = future_outbreak_threshold(cases, None, targets, multiplicador=multiplier, anios_previos=years)
    labels = targets.assign(umbral_brote_casos=threshold.to_numpy())
    labels["brote"] = ((labels.casos_Dengue > labels.umbral_brote_casos) & labels.casos_Dengue.ge(2)).astype("int8")
    return labels


def load_predictions() -> dict[str, pd.DataFrame]:
    tables = {}
    for variant, file in v3.FILES.items():
        data = v3.read_table(v3.OUT / file)
        data["semana_inicio"] = pd.to_datetime(data.semana_inicio)
        data["origen_cierre"] = pd.to_datetime(data.origen_cierre)
        if set(data.variante) != {variant} or data.duplicated(ROW_KEY).any():
            raise ValueError(f"Variante o llave inválida en {file}")
        tables[variant] = data
    columns = ROW_KEY + ["anio", "semana", "origen_cierre", "casos_Dengue", "persistencia"]
    pd.testing.assert_frame_equal(*(t[columns].sort_values(ROW_KEY).reset_index(drop=True) for t in tables.values()))
    return tables


def align_labels(table: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    keys = ["ubigeo", "semana_inicio"]
    aligned = labels.set_index(keys).reindex(pd.MultiIndex.from_frame(table[keys])).reset_index(drop=True)
    if aligned.brote.isna().any() or not np.array_equal(aligned.casos_Dengue, table.casos_Dengue):
        raise ValueError("Etiquetas sin pareja o conteos distintos a las predicciones del Release")
    return aligned


def numerical_check(actual, expected, tolerance: float) -> dict:
    actual, expected = np.asarray(actual, float), np.asarray(expected, float)
    same_missing = bool(np.array_equal(np.isnan(actual), np.isnan(expected)))
    valid = np.isfinite(actual) & np.isfinite(expected)
    delta = float(np.abs(actual[valid] - expected[valid]).max(initial=0.0))
    finite_or_missing = np.isfinite(actual) | np.isnan(actual)
    return {"maximo": delta, "tolerancia": tolerance, "misma_mascara_na": same_missing,
            "pasa": bool(same_missing and finite_or_missing.all() and not np.isinf(expected).any() and delta <= tolerance)}


def checks_against_reference(metrics: pd.DataFrame, tolerance: float) -> dict:
    archived = pd.DataFrame(json.loads(v3.METRICS_JSON.read_text())["metricas_por_bloque"])
    key = ["variante", "semilla", *CELL]
    pairs = metrics.merge(archived, on=key, how="outer", validate="one_to_one", indicator=True,
                          suffixes=("", "_v3"))
    unmatched = int(pairs._merge.ne("both").sum())
    exact_counts = all(pairs[c].eq(pairs[f"{c}_v3"]).all() for c in ("n", "positivos"))
    checks = {m: numerical_check(pairs[m], pairs[f"{m}_v3"], tolerance) for m in ("brier", "auprc")}
    return {"celdas": len(pairs), "sin_par": unmatched, "conteos_exactos": bool(exact_counts), **checks,
            "pasa": unmatched == 0 and bool(exact_counts) and all(c["pasa"] for c in checks.values())}


def calibrate_seed(group: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run the archived chronological calibration in the expected column format."""
    columns = pa.PREDICTION_COLUMNS + ["estacional", "conteo_publicado", "probabilidad_cruda"]
    data = group[columns].rename(columns={"conteo_publicado": "casos_predichos",
                                           "probabilidad_cruda": "probabilidad_brote"})
    return pa.calibrate_chronologically(data)


def evaluate_scenario(name: str, labels: pd.DataFrame, tables: dict[str, pd.DataFrame]) -> dict:
    metrics, calibrated_cells, calibration, lead_summary, seed17, changes = [], [], [], [], {}, []
    checks = {}
    for variant, saved in tables.items():
        aligned = align_labels(saved, labels)
        raw = probabilistic_output.negative_binomial_probability(saved.mu_modelo, saved.alpha_usada,
                                                                 aligned.umbral_brote_casos)
        if name == "principal":
            checks[variant] = {
                "etiquetas_exactas": bool(np.array_equal(aligned.brote, saved.brote)),
                "umbral": numerical_check(aligned.umbral_brote_casos, saved.umbral_brote_casos, 1e-9),
                "probabilidad_cruda": numerical_check(raw, saved.probabilidad_cruda, 1e-9),
                "platt_por_semilla": {},
            }
        data = saved.assign(brote=aligned.brote.to_numpy(), umbral_brote_casos=aligned.umbral_brote_casos.to_numpy(),
                            probabilidad_cruda=raw, etiqueta_principal=saved.brote)
        for seed, group in data.groupby("semilla"):
            calibrated, fits = calibrate_seed(group)
            tags = {"escenario": name, "variante": variant, "semilla": int(seed)}
            calibration.append(fits.assign(**tags))
            if name == "principal":
                expected = group[CELL + CALIBRATION_COUNTS].drop_duplicates()
                counts = fits.merge(expected, on=CELL, how="outer", suffixes=("", "_v3"), validate="one_to_one")
                checks[variant]["platt_por_semilla"][str(seed)] = {
                    "conteos_exactos": all(bool(counts[c].eq(counts[f"{c}_v3"]).all()) for c in CALIBRATION_COUNTS),
                    "probabilidad": numerical_check(calibrated.probabilidad_calibrada,
                                                     group.probabilidad_calibrada, 1e-6),
                }
                calibrated_cells.append(v3.block_metrics(calibrated.assign(**tags)))
            alerts = pa.add_protocol_alerts(calibrated)
            metrics.append(pa.metrics_by_block(alerts).reindex(columns=CELL + REPORTED).assign(**tags))
            # Match the V3 protocol's onset pairing and block exclusions.
            evaluable_alerts = alerts.dropna(subset=["probabilidad_calibrada"])
            lead = pa.clean_lead_time(evaluable_alerts, labels, ["alerta_050", "alerta_persistencia"])
            lead_summary.append(lead_time_summary(lead, ["alerta_050", "alerta_persistencia"]).assign(**tags))
            if seed == rules.SEEDS[0]:
                seed17[variant] = lead
            if variant == VARIANTS[0] and seed == rules.SEEDS[0]:
                changes.append(group.assign(cambia=group.brote.ne(group.etiqueta_principal),
                                            a_positiva=group.brote.gt(group.etiqueta_principal),
                                            a_negativa=group.brote.lt(group.etiqueta_principal))
                               .groupby(CELL)[["cambia", "a_positiva", "a_negativa"]].sum().reset_index().assign(escenario=name))
        print(f"{name} · {variant}: evaluadas las cinco semillas", flush=True)
    return {"metricas": pd.concat(metrics, ignore_index=True), "calibracion": pd.concat(calibration, ignore_index=True),
            "antelacion": pd.concat(lead_summary, ignore_index=True), "antelacion_17": seed17,
            "cambios": pd.concat(changes, ignore_index=True), "control": checks,
            "celdas_reajuste": pd.concat(calibrated_cells, ignore_index=True) if calibrated_cells else None}


def baseline_control(result: dict, saved_metrics: dict) -> dict:
    comparisons = result["control"]
    refit_metrics = checks_against_reference(result["celdas_reajuste"], 1e-6)
    passed = saved_metrics["pasa"] and refit_metrics["pasa"] and all(
        c["etiquetas_exactas"] and c["umbral"]["pasa"] and c["probabilidad_cruda"]["pasa"] and all(
            fit["conteos_exactos"] and fit["probabilidad"]["pasa"] for fit in c["platt_por_semilla"].values())
        for c in comparisons.values())
    return {"pasa": bool(passed), "metricas_guardadas": saved_metrics, "metricas_reajustadas": refit_metrics,
            "por_variante": comparisons}


def compare_scenario(name: str, result: dict) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    metrics = result["metricas"]
    medians = metrics.groupby(["variante", *CELL])[REPORTED].median().reset_index()
    candidate, reference = (medians[medians.variante.eq(v)] for v in VARIANTS)
    ranges = []
    for variant in VARIANTS:
        per_seed = [g for _, g in metrics[metrics.variante.eq(variant)].groupby("semilla")]
        ranges.append(pa.seed_ranges(per_seed))
    tolerance = pa.tie_threshold(*ranges)
    cells = candidate.merge(reference, on=CELL, suffixes=("_v3", "_sin_clima"), validate="one_to_one")
    cells = cells.merge(tolerance[CELL + ["brier"]].rename(columns={"brier": "tolerancia_brier"}),
                        on=CELL, validate="one_to_one")
    cells["delta_brier"] = cells.brier_v3 - cells.brier_sin_clima
    cells["lectura_brier"] = np.select(
        [cells.delta_brier.lt(-cells.tolerancia_brier), cells.delta_brier.gt(cells.tolerancia_brier),
         cells.delta_brier.notna()], ["favorable", "desfavorable", "empate"], default="sin_calibrar")
    episodes = result["antelacion_17"]
    lead = rules.lead_time_difference_multi(episodes[VARIANTS[0]], episodes[VARIANTS[1]],
                                           "alerta_050", rules.SEASON_2026_DECIDING)
    counts_2026 = candidate[candidate.bloque.eq("temporada_2026")].set_index("horizonte").positivos.to_dict()
    verdicts = rules.decide_season_2026(candidate, reference, tolerance, lead, counts_2026)
    return cells.assign(escenario=name), verdicts.assign(escenario=name), lead.assign(escenario=name)


def material_changes(cells: pd.DataFrame, verdicts: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    deciding = [rules.block_name(year) for year in rules.SEASON_2026_DECIDING]
    base = cells[cells.escenario.eq("principal")][CELL + ["lectura_brier"]]
    alt = cells[~cells.escenario.eq("principal") & cells.bloque.isin(deciding)]
    transitions = alt.merge(base.rename(columns={"lectura_brier": "lectura_principal"}), on=CELL, validate="many_to_one")
    transitions = transitions[transitions.lectura_brier.ne(transitions.lectura_principal)].copy()
    transitions["inversion"] = (transitions.lectura_brier.isin(["favorable", "desfavorable"])
                                 & transitions.lectura_principal.isin(["favorable", "desfavorable"]))
    base_verdicts = verdicts[verdicts.escenario.eq("principal")][["horizonte", "veredicto"]]
    verdict_changes = verdicts[~verdicts.escenario.eq("principal")].merge(
        base_verdicts.rename(columns={"veredicto": "veredicto_principal"}), on="horizonte", validate="many_to_one")
    return transitions, verdict_changes[verdict_changes.veredicto.ne(verdict_changes.veredicto_principal)]


def main() -> int:
    hashes = release_inputs()
    quality = validate_integrated_gx()
    print(f"Silver integrado: GX {quality['evaluadas']} expectativas, {quality['fallidas_n']} fallidas", flush=True)
    cases = case_series()
    tables = load_predictions()
    archived = v3.verify_metrics()
    if not archived["pasa"]:
        write_report("reproduccion_principal.json", {"pasa": False, "metricas_guardadas": archived})
        return 2
    main_labels = scenario_labels(cases, *SCENARIOS["principal"])
    results = {"principal": evaluate_scenario("principal", main_labels, tables)}
    control = baseline_control(results["principal"], archived)
    write_report("reproduccion_principal.json", control)
    print(f"Reproducción del principal: {'PASA' if control['pasa'] else 'FALLA'}", flush=True)
    if not control["pasa"]:
        return 2
    for name in ("A", "B"):
        results[name] = evaluate_scenario(name, scenario_labels(cases, *SCENARIOS[name]), tables)
    comparisons = [compare_scenario(name, result) for name, result in results.items()]
    cells, verdicts, lead = (pd.concat(parts, ignore_index=True) for parts in zip(*comparisons))
    transitions, verdict_changes = material_changes(cells, verdicts)
    metrics = pd.concat([r["metricas"] for r in results.values()], ignore_index=True)
    key = ["variante", "semilla", *CELL]
    original_counts = metrics[metrics.escenario.eq("principal")].set_index(key)[COUNT_METRICS].sort_index()
    for name in ("A", "B"):
        counts = metrics[metrics.escenario.eq(name)].set_index(key)[COUNT_METRICS].sort_index()
        pd.testing.assert_frame_equal(original_counts, counts, check_exact=True)
    output = write_report("r09.json", {"escenarios": SCENARIOS, "sha256_insumos": hashes,
        "sha256_protocolo": sha256_file(STUDY / "docs/protocolo.md"), "sha256_codigo": sha256_file(Path(__file__)),
        "reproduccion_principal": control, "calidad_silver": quality,
        "conteos_invariantes": True, "metricas_por_semilla": records(metrics), "comparacion_por_celda": records(cells),
        "cambios_etiqueta": records(pd.concat([r["cambios"] for r in results.values()])),
        "calibracion": records(pd.concat([r["calibracion"] for r in results.values()])),
        "antelacion_por_semilla": records(pd.concat([r["antelacion"] for r in results.values()])),
        "antelacion_pareada_semilla_17": records(lead), "veredictos_brier": records(verdicts),
        "transiciones_celdas_decision": records(transitions), "cambios_veredicto": records(verdict_changes)})
    print(f"Resultados: {output}", flush=True)
    by_variant = {f"{name} / {variant}": table.groupby(CELL)[REPORTED].median().reset_index()
                  for (name, variant), table in metrics.groupby(["escenario", "variante"])}
    report = horizon_strategies.mlflow_report("r09_sensibilidad_etiqueta_v3", by_variant, rules.SEEDS)
    report["parametros"] = v3.hyperparameters()
    report["tag_referencia"] = "model/v3"
    report["escenarios"] = SCENARIOS
    run = tracking.log_or_warn("r09_sensibilidad_etiqueta_v3", report, metrics_path=output, output_dir=OUTPUT,
                              data_quality={"exito": quality["exito"], "suites": {"silver_integrado": quality}},
                              tracking_uri=f"sqlite:///{ROOT / 'mlflow.db'}", log_datasets=False,
                              fingerprint=sha256_file(output))
    write_report("ejecucion.json", {"resultados": output.name, "sha256": sha256_file(output), "mlflow_run": run})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
