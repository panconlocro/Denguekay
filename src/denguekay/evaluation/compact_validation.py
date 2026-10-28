"""Progressive evaluation of three compact matrices for both targets.

Each alert threshold is calibrated with predictions of earlier seasons whose
labels had already closed at the first origin of the evaluated block.
"""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from xgboost import __version__ as XGBOOST_VERSION

from denguekay.features.model_input_contract import audit_handoff
from denguekay.evaluation.metrics import select_f1_threshold
from denguekay.features.gold import SOCIO_2017_DATE
from denguekay.model.train import (
    SENSITIVITY_TEST_YEAR, MIN_OUTBREAK_CASES, BASE_PARAMS,
    SEASON_START_WEEK, variant_columns, evaluate_fold, predict_fold,
    prepare_gold, split_calendar_year, split_season,
)
from denguekay.model.tracking import log_or_warn
from denguekay.config.paths import COMPACT_METRICS, GOLD, MODELS, SILVER_INTEGRATED
from denguekay.data.validation.forecast_contract import KEY
from denguekay.data.validation.gx_quality import validate_modeling_inputs


SEASONS = (2021, 2022, 2023, 2024)
SELECTION_SEASONS = (2022, 2023)
POPULATION = "log_poblacion_censo_2017"


def compact_variants(horizon: int) -> dict[str, list[str]]:
    """Define the small matrices before looking at the new results."""
    bases = variant_columns(horizon)
    return {
        "base_4": bases["historia_4"],
        "base_6": bases["historia_4_mas_2"],
        "base_6_poblacion_2017": [*bases["historia_4_mas_2"], POPULATION],
    }


def validate_matrix(data: pd.DataFrame, horizon: int) -> None:
    """Check complete predictors and a fixed population per UBIGEO."""
    variants = compact_variants(horizon)
    columns = sorted({c for cols in variants.values() for c in cols})
    missing = set(columns) - set(data)
    if missing:
        raise ValueError(f"Faltan columnas de la matriz compacta: {sorted(missing)}")
    if any(len(v) != len(set(v)) for v in variants.values()):
        raise ValueError("La matriz compacta repite predictores")
    if set(columns) & {"ubigeo", "casos_Dengue", "brote", "umbral_brote_casos"}:
        raise ValueError("La matriz compacta incluye identificador u objetivo")
    if data[columns].isna().any().any() or not np.isfinite(data[columns].to_numpy(float)).all():
        raise ValueError("Predictores compactos incompletos o no finitos")
    if data[POPULATION].le(0).any() or data.groupby("ubigeo")[POPULATION].nunique().ne(1).any():
        raise ValueError("La población censal de 2017 debe ser positiva y fija por UBIGEO")
    if data.duplicated(KEY).any():
        raise ValueError("Distrito-semanas duplicadas")


def available_calibration(
    earlier_predictions: list[pd.DataFrame], cutoff: pd.Timestamp,
) -> tuple[pd.DataFrame, int]:
    """Use only labels closed before the first origin of the new block."""
    if not earlier_predictions:
        raise ValueError("Se necesita una temporada anterior para calibrar")
    earlier = pd.concat(earlier_predictions, ignore_index=True)
    label_close = earlier.semana_inicio + pd.Timedelta(days=6)
    available = earlier.loc[label_close.le(cutoff)].copy()
    if available.empty or available.brote.nunique() < 2:
        raise ValueError("Calibración sin dos clases disponibles al origen")
    if available.duplicated(KEY).any():
        raise ValueError("Observaciones duplicadas para calibrar")
    if not (available.semana_inicio + pd.Timedelta(days=6)).le(cutoff).all():
        raise ValueError("La calibración incluye etiquetas futuras")
    return available, len(earlier) - len(available)


def choose_in_validation(
    results: dict[str, dict], approach: str, variants: dict[str, list[str]],
) -> str:
    """Select by mean F1 of 2022-2023; on a tie, fewer columns."""
    if approach not in {"regresion", "clasificacion"}:
        raise ValueError("Enfoque inválido")
    path = "alerta_derivada" if approach == "regresion" else "alerta_directa"

    def score(name: str) -> tuple[float, int, str]:
        folds = results[name]["folds"]
        used = [f for f in folds if f["bloque"] in {f"temporada_{x}" for x in SELECTION_SEASONS}]
        if len(used) != len(SELECTION_SEASONS):
            raise ValueError("Faltan folds progresivos para selección")
        return float(np.mean([f[approach][path]["f1"] for f in used])), -len(variants[name]), name

    return max(variants, key=score)


def run_compact_validation(
    *, gold_dir: Path = GOLD,
    output_dir: Path = MODELS / "experimentos" / "validacion_temporal_compacta",
    metrics_path: Path = COMPACT_METRICS,
    audit: bool = True, validate_data: bool = True,
    log_mlflow: bool = True,
) -> dict:
    """Train the predefined matrices with chronological calibration per season."""
    gold_dir, output_dir, metrics_path = map(Path, (gold_dir, output_dir, metrics_path))
    if audit:
        audit_handoff(gold_dir=gold_dir)
    # Data quality (Great Expectations) before training; it fails if gold/silver
    # breaks its suite. The summary is attached to the MLflow run.
    quality = (validate_modeling_inputs(gold_dir=gold_dir, silver_path=None)
               if validate_data else None)
    manifest_path = gold_dir / "manifest_fase6.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["regla_brote"]["minimo_casos"] != MIN_OUTBREAK_CASES:
        raise ValueError("El mínimo de brote difiere del manifiesto gold")
    report = {
        "experimento": "validacion_temporal_progresiva_matrices_compactas",
        "variantes_predefinidas": ["base_4", "base_6", "base_6_poblacion_2017"],
        "temporada_calibracion_inicial": 2021,
        "temporadas_seleccion": list(SELECTION_SEASONS),
        "temporada_contraste": 2024,
        "sensibilidad_calendario": SENSITIVITY_TEST_YEAR,
        "semana_inicio_temporada": SEASON_START_WEEK,
        "regla_calibracion": "predicciones OOS de temporadas anteriores; etiqueta con cierre <= primer origen del bloque",
        "criterio_seleccion": "F1 medio no ponderado de 2022 y 2023; empate: menos columnas",
        "nota_2024": "2024 fue inspeccionado en ensayos previos; contraste exploratorio, no test virgen",
        "parametros": BASE_PARAMS,
        "version_xgboost": XGBOOST_VERSION,
        "sha256_manifest_gold": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "horizontes": {},
    }
    predictions = []
    for h in (2, 4):
        file = gold_dir / f"{SILVER_INTEGRATED.stem}_h{h}_gold.csv"
        gold = pd.read_csv(file, dtype={"ubigeo": "string"},
                           parse_dates=["semana_inicio", "origen_inicio", "origen_cierre"])
        data, excluded = prepare_gold(gold, h)
        validate_matrix(data, h)
        variants = compact_variants(h)
        block_h = {
            "archivo_gold": file.name,
            "sha256_gold": hashlib.sha256(file.read_bytes()).hexdigest(),
            "filas_gold": len(gold), "filas_excluidas_arranque": excluded,
            "filas_comparadas": len(data), "variantes": {},
        }
        print(f"h={h}: {len(data)} filas comunes; calibración progresiva")
        for name, columns in variants.items():
            previous: list[pd.DataFrame] = []
            result = {"columnas": columns, "calibracion_inicial": None, "folds": [], "sensibilidad_2025": None}
            for season in SEASONS:
                train, test, cutoff = split_season(data, season)
                if name.endswith("poblacion_2017") and test.origen_cierre.lt(pd.Timestamp(SOCIO_2017_DATE)).any():
                    raise ValueError("Referencia censal no disponible en el bloque")
                pred, _, _ = predict_fold(train, test, columns)
                pred[f"casos_lag_{h}"] = test[f"casos_lag_{h}"].to_numpy(float)
                pred["horizonte"] = h
                pred["variante"] = name
                pred["bloque"] = f"temporada_{season}"
                predictions.append(pred)
                if season == SEASONS[0]:
                    result["calibracion_inicial"] = {
                        "bloque": f"temporada_{season}", "filas": len(pred),
                        "positivos": int(pred.brote.sum()), "sin_evaluacion_clasificacion": True,
                    }
                else:
                    cal, excluded_unavailable = available_calibration(previous, cutoff)
                    threshold = select_f1_threshold(
                        cal.brote.to_numpy(int), cal.probabilidad_brote.to_numpy(float))
                    fold = evaluate_fold(
                        pred, horizon=h, variant=name, block=f"temporada_{season}",
                        kind="seleccion" if season in SELECTION_SEASONS else "contraste",
                        cutoff=cutoff, n_training=len(train),
                        classification_threshold=threshold["umbral"],
                    )
                    fold["positivos_entrenamiento"] = int(train.brote.sum())
                    fold["calibracion"] = {
                        "filas": len(cal), "positivos": int(cal.brote.sum()),
                        "etiquetas_no_disponibles": excluded_unavailable,
                        "ultima_etiqueta_cerrada": str((cal.semana_inicio.max() + pd.Timedelta(days=6)).date()),
                        "seleccion_umbral": threshold,
                    }
                    result["folds"].append(fold)
                previous.append(pred)
            # The 2025 sensitivity is computed with its own predictions;
            # it does not receive labels after its first origin either.
            train, test, cutoff = split_calendar_year(data, SENSITIVITY_TEST_YEAR)
            pred, _, _ = predict_fold(train, test, columns)
            pred[f"casos_lag_{h}"] = test[f"casos_lag_{h}"].to_numpy(float)
            pred["horizonte"] = h
            pred["variante"] = name
            pred["bloque"] = f"calendario_{SENSITIVITY_TEST_YEAR}"
            predictions.append(pred)
            cal, excluded_unavailable = available_calibration(previous, cutoff)
            threshold = select_f1_threshold(cal.brote.to_numpy(int), cal.probabilidad_brote.to_numpy(float))
            fold = evaluate_fold(
                pred, horizon=h, variant=name, block=f"calendario_{SENSITIVITY_TEST_YEAR}",
                kind="sensibilidad", cutoff=cutoff, n_training=len(train),
                classification_threshold=threshold["umbral"],
            )
            fold["positivos_entrenamiento"] = int(train.brote.sum())
            fold["calibracion"] = {
                "filas": len(cal), "positivos": int(cal.brote.sum()),
                "etiquetas_no_disponibles": excluded_unavailable,
                "ultima_etiqueta_cerrada": str((cal.semana_inicio.max() + pd.Timedelta(days=6)).date()),
                "seleccion_umbral": threshold,
            }
            result["sensibilidad_2025"] = fold
            block_h["variantes"][name] = result
        block_h["seleccion_2022_2023"] = {
            approach: choose_in_validation(block_h["variantes"], approach, variants)
            for approach in ("regresion", "clasificacion")
        }
        report["horizontes"][str(h)] = block_h
    output_dir.mkdir(parents=True, exist_ok=True)
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    pd.concat(predictions, ignore_index=True).to_csv(output_dir / "predicciones_por_bloque.csv", index=False)
    metrics_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if log_mlflow:
        log_or_warn(
            "validacion_temporal_compacta", report, metrics_path=metrics_path, output_dir=output_dir,
            gold_dir=gold_dir, data_quality=quality)
    return report


def main() -> None:
    """Run ``python -m denguekay.evaluation.compact_validation``."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold-dir", type=Path, default=GOLD)
    parser.add_argument("--salida-dir", type=Path,
                        default=MODELS / "experimentos" / "validacion_temporal_compacta")
    parser.add_argument("--metricas", type=Path,
                        default=COMPACT_METRICS)
    parser.add_argument("--sin-validacion-datos", action="store_true",
                        help="No ejecutar las suites de Great Expectations")
    parser.add_argument("--sin-mlflow", action="store_true",
                        help="No registrar la corrida en MLflow")
    args = parser.parse_args()
    report = run_compact_validation(
        validate_data=not args.sin_validacion_datos, log_mlflow=not args.sin_mlflow,
        gold_dir=args.gold_dir, output_dir=args.salida_dir, metrics_path=args.metricas)
    print(f"Métricas: {args.metricas}")
    for h, block in report["horizontes"].items():
        print(f"h={h}: {block['seleccion_2022_2023']}")


if __name__ == "__main__":
    main()
