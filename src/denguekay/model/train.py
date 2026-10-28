"""First XGBoost experiment: case forecast and direct alert.

Each row is a target week. Each season's model is fitted once before its
first origin and stays fixed during that season. The lags of weeks already
observed inside the test are available for its later origins; no test
label is used for fitting.
"""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from xgboost import XGBClassifier, XGBRegressor, __version__ as XGBOOST_VERSION

from denguekay.data.seasons import assign_season
from denguekay.features.model_input_contract import auditar_traspaso, familias_predictoras
from denguekay.model.device import xgboost_settings
from src.modeling.evaluate import (
    alertas_desde_conteos, metricas_alerta, metricas_conteos,
    seleccionar_umbral_f1,
)
from denguekay.model.tracking import log_or_warn
from denguekay.config.paths import GOLD, MODELS, RESEARCH_FIRST_MODELS, SILVER_INTEGRATED
from denguekay.data.calendar import mmwr_epi_week
from denguekay.data.validation.forecast_contract import KEY
from denguekay.data.validation.gx_quality import validate_modeling_inputs

VALIDATION_SEASONS = (2021, 2022, 2023)
MAIN_TEST_SEASON = 2024
SENSITIVITY_TEST_YEAR = 2025
MIN_OUTBREAK_CASES = 2
SEASON_START_WEEK = 35
SEED = 17
BASE_PARAMS = {
    "n_estimators": 160,
    "max_depth": 3,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.9,
    "min_child_weight": 5,
    "reg_lambda": 5.0,
    "tree_method": "hist",
    "random_state": SEED,
    # NVIDIA GPU if there is one, otherwise the CPU with every core (configs/config.yaml,
    # xgboost section). On the GPU the decimals may change,
    # so "device" is recorded in the report parameters.
    **xgboost_settings(),
}


def variant_columns(horizon: int) -> dict[str, list[str]]:
    """Return the predefined bases of four and six available variables."""
    families = familias_predictoras(horizon)
    history = families["historia"]
    return {
        "historia_4": [history[0], history[2], *families["calendario"]],
        "historia_4_mas_2": [*history, *families["calendario"]],
    }


def prepare_gold(gold: pd.DataFrame, horizon: int) -> tuple[pd.DataFrame, int]:
    """Validate the minimum contract and set aside only structural start-up nulls.

    Both variants share the complete rows of the six-variable base. The
    canonical gold output is neither modified nor filled with artificial zeros.
    """
    variants = variant_columns(horizon)
    base_six = variants["historia_4_mas_2"]
    required = set(KEY + [
        "semana_inicio", "origen_inicio", "origen_cierre", "casos_Dengue",
        "brote", "umbral_brote_casos", *base_six,
    ])
    missing = required - set(gold)
    if missing or gold.empty or gold.duplicated(KEY).any() or gold[KEY].isna().any().any():
        raise ValueError(f"Gold vacío, con llaves duplicadas/incompletas o columnas ausentes: {sorted(missing)}")
    data = gold.copy()
    if not data.ubigeo.astype("string").str.fullmatch(r"\d{6}").all():
        raise ValueError("ubigeo debe tener seis dígitos y ser texto")
    for col in ("semana_inicio", "origen_inicio", "origen_cierre"):
        data[col] = pd.to_datetime(data[col], errors="raise")
    for col in ("casos_Dengue", "brote", "umbral_brote_casos", *base_six):
        data[col] = pd.to_numeric(data[col], errors="raise")
    if (data[["casos_Dengue", "brote", "umbral_brote_casos"]].isna().any().any()
            or (data.casos_Dengue < 0).any() or (data.umbral_brote_casos < 0).any()
            or not np.isfinite(data[["casos_Dengue", "brote", "umbral_brote_casos"]].to_numpy(float)).all()
            or not np.isin(data.brote, [0, 1]).all()
            or (data.casos_Dengue % 1 != 0).any()):
        raise ValueError("Objetivos o umbrales de gold inválidos")
    expected = alertas_desde_conteos(
        data.casos_Dengue.to_numpy(float),
        data.umbral_brote_casos.to_numpy(float), MIN_OUTBREAK_CASES,
    )
    if not np.array_equal(expected, data.brote.to_numpy(bool)):
        raise ValueError("La etiqueta brote no coincide con la regla de gold")
    if (data.semana_inicio.dt.weekday != 6).any():
        raise ValueError("semana_inicio debe ser domingo")
    calendar = mmwr_epi_week(data.semana_inicio)
    if (pd.to_numeric(data.anio, errors="raise").ne(calendar.anio_epi)
            | pd.to_numeric(data.semana, errors="raise").ne(calendar.semana_epi)).any():
        raise ValueError("anio/semana de gold no coinciden con el calendario epidemiológico MMWR")
    without_window = data[base_six].isna().any(axis=1)
    ordered = data.sort_values(["ubigeo", "semana_inicio"])
    gaps = ordered.groupby("ubigeo").semana_inicio.diff().dt.days.dropna()
    if not gaps.eq(7).all():
        raise ValueError("Gold tiene semanas faltantes o repetidas por distrito")
    positions = ordered.groupby("ubigeo").cumcount()
    if not without_window.loc[ordered.index].reset_index(drop=True).equals(
        positions.lt(horizon + 3).reset_index(drop=True)
    ):
        raise ValueError("Hay predictores faltantes fuera del arranque estructural")
    if data.loc[~without_window, ["origen_inicio", "origen_cierre"]].isna().any().any():
        raise ValueError("Hay predictores poblados sin origen temporal")
    if data.loc[~without_window, base_six].isna().any().any():
        raise ValueError("Hay predictores incompletos fuera del arranque")
    if not np.isfinite(data.loc[~without_window, base_six].to_numpy(float)).all():
        raise ValueError("Hay predictores no finitos")
    complete = data.loc[~without_window].copy()
    distance = (complete.semana_inicio - complete.origen_inicio).dt.days
    if not distance.eq(7 * horizon).all() or not complete.origen_cierre.eq(complete.origen_inicio + pd.Timedelta(days=6)).all():
        raise ValueError("El origen no respeta el horizonte solicitado")
    complete["temporada"] = assign_season(
        complete.anio, complete.semana, SEASON_START_WEEK,
    )
    complete = complete.sort_values(["semana_inicio", "ubigeo"]).reset_index(drop=True)
    return complete, int(without_window.sum())


def _split_block(
    data: pd.DataFrame, mask: pd.Series, name: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Timestamp]:
    """Split a time block and require train labels that were already available."""
    test_set = data.loc[mask].copy()
    if test_set.empty or test_set.origen_cierre.isna().any():
        raise ValueError(f"{name} vacío o sin origen")
    first = test_set.semana_inicio.min()
    cutoff = test_set.loc[test_set.semana_inicio.eq(first), "origen_cierre"].min()
    if not test_set.loc[test_set.semana_inicio.eq(first), "origen_cierre"].eq(cutoff).all():
        raise ValueError("Los distritos tienen distinto primer origen de prueba")
    training = data.loc[(data.semana_inicio + pd.Timedelta(days=6)).le(cutoff)].copy()
    if training.empty or training.brote.nunique() < 2:
        raise ValueError(f"Entrenamiento sin dos clases para {name}")
    if training.semana_inicio.max() >= first or not training.origen_cierre.lt(training.semana_inicio).all():
        raise ValueError("Solapamiento o fuga temporal en el corte")
    if set(map(tuple, training[KEY].to_numpy())) & set(map(tuple, test_set[KEY].to_numpy())):
        raise ValueError("El entrenamiento contiene observaciones de prueba")
    return training, test_set, cutoff


def split_season(
    data: pd.DataFrame, season: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Timestamp]:
    """Build a fold of an epidemiological season common to every district."""
    return _split_block(data, data.temporada.eq(season), f"temporada {season}")


def split_calendar_year(
    data: pd.DataFrame, year: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Timestamp]:
    """Build a yearly test to measure the 2025 change separately."""
    return _split_block(data, data.anio.eq(year), f"año calendario {year}")


def fit_models(
    training: pd.DataFrame, columns: list[str],
) -> tuple[XGBRegressor, XGBClassifier]:
    """Fit the XGBoost models of log1p(cases) and of brote, with fixed hyperparameters."""
    x = training[columns]
    if x.isna().any().any() or not np.isfinite(x.to_numpy(float)).all():
        raise ValueError("Matriz de entrenamiento incompleta")
    regressor = XGBRegressor(objective="reg:squarederror", **BASE_PARAMS)
    classifier = XGBClassifier(objective="binary:logistic", eval_metric="logloss", **BASE_PARAMS)
    regressor.fit(x, np.log1p(training.casos_Dengue.to_numpy(float)))
    classifier.fit(x, training.brote.to_numpy(int))
    return regressor, classifier


def counts_from_log1p(predictions: np.ndarray) -> np.ndarray:
    """Invert the regressor output with the original bounds of the protocol."""
    counts = np.expm1(np.clip(predictions, 0, 30)).clip(min=0)
    if not np.isfinite(counts).all():
        raise ValueError("El modelo produjo conteos no finitos")
    return counts


def predict_fold(
    training: pd.DataFrame, test_set: pd.DataFrame, columns: list[str],
) -> tuple[pd.DataFrame, XGBRegressor, XGBClassifier]:
    """Predict both targets on exactly the same district-weeks."""
    regressor, classifier = fit_models(training, columns)
    x = test_set[columns]
    counts = counts_from_log1p(regressor.predict(x))
    probabilities = classifier.predict_proba(x)[:, 1]
    if not np.isfinite(counts).all() or not np.isfinite(probabilities).all():
        raise ValueError("El modelo produjo predicciones no finitas")
    output = test_set[KEY + [
        "semana_inicio", "origen_cierre", "temporada", "casos_Dengue",
        "brote", "umbral_brote_casos",
    ]].copy()
    output["casos_predichos"] = counts
    output["probabilidad_brote"] = probabilities
    return output, regressor, classifier


def evaluate_fold(
    predictions: pd.DataFrame, *, horizon: int, variant: str,
    block: str, kind: str, cutoff: pd.Timestamp, n_training: int,
    classification_threshold: float,
) -> dict:
    """Evaluate regression, classification and persistence on the same fold."""
    y = predictions.brote.to_numpy(int)
    cases = predictions.casos_Dengue.to_numpy(float)
    limit = predictions.umbral_brote_casos.to_numpy(float)
    forecast = predictions.casos_predichos.to_numpy(float)
    persistence = predictions[f"casos_lag_{horizon}"].to_numpy(float)
    margin = forecast - np.maximum(limit, MIN_OUTBREAK_CASES)
    persistence_margin = persistence - np.maximum(limit, MIN_OUTBREAK_CASES)
    regression_alert = alertas_desde_conteos(forecast, limit, MIN_OUTBREAK_CASES)
    persistence_alert = alertas_desde_conteos(persistence, limit, MIN_OUTBREAK_CASES)
    prob = predictions.probabilidad_brote.to_numpy(float)
    return {
        "horizonte": horizon,
        "variante": variant,
        "bloque": block,
        "tipo": kind,
        "primera_semana_objetivo": str(predictions.semana_inicio.min().date()),
        "ultima_semana_objetivo": str(predictions.semana_inicio.max().date()),
        "corte_ajuste": str(cutoff.date()),
        "n_entrenamiento": n_training,
        "n_prueba": len(predictions),
        "positivos_entrenamiento": None,
        "regresion": {
            "conteos": metricas_conteos(cases, forecast),
            "alerta_derivada": metricas_alerta(y, regression_alert, puntaje=margin),
        },
        "clasificacion": {
            "umbral_probabilidad": classification_threshold,
            "alerta_directa": metricas_alerta(y, prob >= classification_threshold, puntaje=prob),
            "brier": float(np.mean((prob - y) ** 2)),
        },
        "persistencia": {
            "conteos": metricas_conteos(cases, persistence),
            "alerta_derivada": metricas_alerta(y, persistence_alert, puntaje=persistence_margin),
        },
    }


def run_experiment(
    *, gold_dir: Path = GOLD, output_dir: Path = MODELS / "experimentos",
    metrics_path: Path = RESEARCH_FIRST_MODELS / "docs" / "metricas" / "primer_xgboost.json",
    audit: bool = True, validate_data: bool = True,
    log_mlflow: bool = True,
) -> dict:
    """Train both approaches on predefined validation and time tests.

    The classification threshold is set with the out-of-sample predictions of
    seasons 2021-2023. The main test is season 2024; the full calendar year
    2025 is a separate sensitivity. Each test model is retrained only with the
    labels prior to its first origin.
    """
    gold_dir, output_dir, metrics_path = map(Path, (gold_dir, output_dir, metrics_path))
    if audit:
        auditar_traspaso(gold_dir=gold_dir)
    # Data quality (Great Expectations) before training; it fails if gold/silver
    # breaks its suite. The summary is attached to the MLflow run.
    quality = (validate_modeling_inputs(gold_dir=gold_dir, silver_path=None)
               if validate_data else None)
    manifest = json.loads((gold_dir / "manifest_fase6.json").read_text(encoding="utf-8"))
    if manifest["regla_brote"]["minimo_casos"] != MIN_OUTBREAK_CASES:
        raise ValueError("El mínimo de brote del manifiesto difiere del experimento")
    summary = {
        "objetivo": "conteos log1p y alerta binaria directa por separado",
        "validacion": list(VALIDATION_SEASONS),
        "prueba_principal": f"temporada_{MAIN_TEST_SEASON}",
        "prueba_sensibilidad": f"calendario_{SENSITIVITY_TEST_YEAR}",
        "semana_inicio_temporada": SEASON_START_WEEK,
        "minimo_casos_brote": MIN_OUTBREAK_CASES,
        "criterio_umbral_clasificacion": "máximo F1 agregado en validación 2021-2023; empate: umbral mayor",
        "parametros": BASE_PARAMS,
        "version_xgboost": XGBOOST_VERSION,
        "sha256_manifest_gold": hashlib.sha256((gold_dir / "manifest_fase6.json").read_bytes()).hexdigest(),
        "horizontes": {},
    }
    models_to_save = []
    predictions_to_save = []
    for h in (2, 4):
        file = gold_dir / f"{SILVER_INTEGRATED.stem}_h{h}_gold.csv"
        gold = pd.read_csv(file, dtype={"ubigeo": "string"},
                           parse_dates=["semana_inicio", "origen_inicio", "origen_cierre"])
        data, excluded = prepare_gold(gold, h)
        variants = variant_columns(h)
        summary_h = {
            "archivo_gold": file.name,
            "sha256_gold": hashlib.sha256(file.read_bytes()).hexdigest(),
            "filas_gold": len(gold), "filas_excluidas_arranque": excluded,
            "filas_modelables": len(data), "variantes": {},
        }
        print(f"h={h}: {len(data)} filas modelables; {excluded} de arranque fuera de la matriz")
        for name, columns in variants.items():
            runs = {}
            blocks = [
                *( (f"temporada_{t}", "validacion", t) for t in VALIDATION_SEASONS),
                (f"temporada_{MAIN_TEST_SEASON}", "prueba_principal", MAIN_TEST_SEASON),
                (f"calendario_{SENSITIVITY_TEST_YEAR}", "prueba_sensibilidad", SENSITIVITY_TEST_YEAR),
            ]
            for block, kind, period in blocks:
                if block.startswith("temporada_"):
                    train, test, cutoff = split_season(data, period)
                else:
                    train, test, cutoff = split_calendar_year(data, period)
                print(f"  {name}, {block}: train={len(train)}, test={len(test)}, corte={cutoff.date()}")
                pred, regressor, classifier = predict_fold(train, test, columns)
                pred[f"casos_lag_{h}"] = test[f"casos_lag_{h}"].to_numpy(float)
                pred["horizonte"] = h
                pred["variante"] = name
                pred["bloque"] = block
                runs[block] = (pred, cutoff, len(train), int(train.brote.sum()), kind)
                predictions_to_save.append(pred)
                if kind != "validacion":
                    models_to_save.extend([
                        (regressor, f"xgb_h{h}_{name}_regresion_{block}.json"),
                        (classifier, f"xgb_h{h}_{name}_clasificacion_{block}.json"),
                    ])
            validation = pd.concat([
                runs[f"temporada_{t}"][0] for t in VALIDATION_SEASONS
            ], ignore_index=True)
            selection = seleccionar_umbral_f1(
                validation.brote.to_numpy(int),
                validation.probabilidad_brote.to_numpy(float),
            )
            folds = []
            for block, (pred, cutoff, n_train, pos_train, kind) in runs.items():
                fold = evaluate_fold(
                    pred, horizon=h, variant=name, block=block, kind=kind,
                    cutoff=cutoff, n_training=n_train,
                    classification_threshold=selection["umbral"],
                )
                fold["positivos_entrenamiento"] = pos_train
                folds.append(fold)
            summary_h["variantes"][name] = {
                "columnas": columns,
                "seleccion_umbral": selection,
                "folds": folds,
            }
        summary["horizontes"][str(h)] = summary_h
    output_dir.mkdir(parents=True, exist_ok=True)
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    for model, name in models_to_save:
        model.save_model(output_dir / name)
    predictions = pd.concat(predictions_to_save, ignore_index=True)
    predictions.to_csv(output_dir / "predicciones_por_fold.csv", index=False)
    metrics_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if log_mlflow:
        log_or_warn(
            "primer_xgboost", summary, metrics_path=metrics_path, output_dir=output_dir,
            gold_dir=gold_dir, data_quality=quality)
    return summary


def main() -> None:
    """Run the first experiment from ``python -m denguekay.model.train``."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold-dir", type=Path, default=GOLD)
    parser.add_argument("--salida-dir", type=Path, default=MODELS / "experimentos")
    parser.add_argument("--metricas", type=Path,
                        default=RESEARCH_FIRST_MODELS / "docs" / "metricas" / "primer_xgboost.json")
    parser.add_argument("--sin-validacion-datos", action="store_true",
                        help="No ejecutar las suites de Great Expectations")
    parser.add_argument("--sin-mlflow", action="store_true",
                        help="No registrar la corrida en MLflow")
    args = parser.parse_args()
    summary = run_experiment(
        validate_data=not args.sin_validacion_datos, log_mlflow=not args.sin_mlflow,
        gold_dir=args.gold_dir, output_dir=args.salida_dir,
        metrics_path=args.metricas,
    )
    print(f"Métricas: {args.metricas}")
    for h, result in summary["horizontes"].items():
        print(f"h={h}: {list(result['variantes'])}")


if __name__ == "__main__":
    main()
