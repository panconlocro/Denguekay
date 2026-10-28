"""Logging of the XGBoost experiments in MLflow.

Every experiment module (``train``, ``ablacion_*`` and
``validacion_temporal_compacta``) produces a report with the same shape::

    report["horizontes"][h]["variantes"][variant] -> evaluated folds

This module walks that report **after** the experiment ended and logs it
without altering the statistical protocol or the versioned files:

- one **MLflow experiment** per module (``denguekay/ablacion_clima``, ...);
- one **parent run** per execution, with XGBoost parameters, lineage (hashes
  of gold/silver/manifest, Git commit), library versions, the Great
  Expectations result and the output files;
- one **child run** per horizon x variant, with metrics per block
  (``temporada_2024.cls_f1``) and the validation mean (``validacion_media.cls_f1``);
- one **grandchild run** per fold (horizon x variant x block), with every metric
  of the fold and the fold's XGBoost models when they were saved.

Metric prefixes: ``reg_`` = case regression + alert rule,
``cls_`` = direct classification of ``brote``, ``pers_`` = persistence,
``cal_`` = progressive threshold calibration.

By default the store is local: ``mlflow.db`` (SQLite) and ``mlartifacts/`` at
the repository root. Defining ``MLFLOW_TRACKING_URI`` is enough to use another
server. Open the UI with::

    mlflow ui --backend-store-uri sqlite:///mlflow.db --workers 1
"""

import json
import os
import platform
import subprocess
from pathlib import Path

import numpy as np

from denguekay.config.paths import MLFLOW_ARTIFACTS, MLFLOW_DB, ROOT

# MLflow 3 prints hints for AI agents when imported; they add nothing here.
os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")

EXPERIMENT_PREFIX = "denguekay"
SECTIONS = {"regresion": "reg", "clasificacion": "cls", "persistencia": "pers"}
VALIDATION_TYPES = {"validacion", "seleccion"}
FOLD_KEYS = {"horizonte", "variante", "bloque", "regresion", "clasificacion"}
MAX_PARAM_LENGTH = 6000
FINGERPRINT_TAG = "huella_cache"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def default_tracking_uri() -> str:
    """Tracking store URI: ``MLFLOW_TRACKING_URI`` or the local SQLite in the repository."""
    return os.environ.get("MLFLOW_TRACKING_URI") or f"sqlite:///{MLFLOW_DB.as_posix()}"


def set_experiment(name: str, tracking_uri: str | None = None) -> str:
    """Set the tracking URI and return the experiment id (it is created if missing).

    With the local store, artifacts go to ``mlartifacts/<experiment>`` with an
    absolute path, so a notebook (cwd ``pipelines/notebooks/``) and the CLI (cwd at the
    root) write to the same place.
    """
    import mlflow

    uri = tracking_uri or default_tracking_uri()
    mlflow.set_tracking_uri(uri)
    existing = mlflow.get_experiment_by_name(name)
    if existing is not None:
        return existing.experiment_id
    location = None
    if uri.startswith("sqlite:///"):
        base = Path(uri[len("sqlite:///"):]).resolve()
        root = MLFLOW_ARTIFACTS if base == MLFLOW_DB.resolve() else base.parent / "mlartifacts"
        location = (root / name.replace("/", "_")).as_uri()
    return mlflow.create_experiment(name, artifact_location=location)


# ---------------------------------------------------------------------------
# Flattening of reports (pure functions, testable without MLflow)
# ---------------------------------------------------------------------------

def _is_fold(obj) -> bool:
    return isinstance(obj, dict) and FOLD_KEYS <= set(obj)


def _number(value) -> float | None:
    """Convert to float if it is a finite number; ``None`` otherwise."""
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float, np.integer, np.floating)):
        value = float(value)
        return value if np.isfinite(value) else None
    return None


def _leaves(obj, prefix: str = "") -> dict:
    """Flatten a nested dict using only the leaf name with a prefix."""
    output = {}
    for key, value in obj.items():
        if isinstance(value, dict):
            output.update(_leaves(value, prefix))
        else:
            output[f"{prefix}{key}"] = value
    return output


def fold_metrics(fold: dict) -> tuple[dict[str, float], dict[str, str]]:
    """Split a fold into numeric metrics and descriptive parameters.

    ``regresion.conteos.mae`` -> ``reg_mae``; ``clasificacion.alerta_directa.f1``
    -> ``cls_f1``; ``calibracion.seleccion_umbral.umbral`` -> ``cal_umbral``.
    """
    metrics, params = {}, {}
    for section, prefix in SECTIONS.items():
        for key, value in _leaves(fold.get(section) or {}, f"{prefix}_").items():
            number = _number(value)
            if number is not None:
                metrics[key] = number
    for key, value in _leaves(fold.get("calibracion") or {}, "cal_").items():
        number = _number(value)
        if number is not None:
            metrics[key] = number
        elif value is not None:
            params[key] = str(value)
    for key, value in fold.items():
        if key in SECTIONS or key == "calibracion" or isinstance(value, (dict, list)):
            continue
        if value is not None:
            params[key] = str(value)
    return metrics, params


def variant_folds(result: dict) -> list[dict]:
    """Find the folds of a variant whatever the module named them."""
    folds = []
    for value in result.values():
        if _is_fold(value):
            folds.append(value)
        elif isinstance(value, list):
            folds.extend(x for x in value if _is_fold(x))
    return folds


def variant_summary(folds: list[dict]) -> dict[str, float]:
    """Metrics per block and validation mean (it never averages tests)."""
    metrics = {}
    by_validation_type = []
    for fold in folds:
        values, _ = fold_metrics(fold)
        metrics.update({f"{fold['bloque']}.{k}": v for k, v in values.items()})
        if fold.get("tipo") in VALIDATION_TYPES:
            by_validation_type.append(values)
    if by_validation_type:
        keys = set().union(*by_validation_type)
        for key in sorted(keys):
            values = [m[key] for m in by_validation_type if key in m]
            if len(values) == len(by_validation_type):
                metrics[f"validacion_media.{key}"] = float(np.mean(values))
        metrics["validacion_media.n_bloques"] = float(len(by_validation_type))
    return metrics


def selected_by_horizon(block_h: dict) -> dict[str, list[str]]:
    """Variant -> approaches in which it was chosen (``elegidas_solo_validacion`` and similar).

    It recognises ``{"regresion": variant, "clasificacion": variant}`` and the
    per-family shape ``{"fija": {"regresion": ...}}``; then the tag is
    ``fija:regresion``. Winners per season (one level deeper) do not count.
    """
    variants = set(block_h.get("variantes", {}))
    chosen: dict[str, list[str]] = {}

    def is_selection(value) -> bool:
        return (isinstance(value, dict) and bool(value) and set(value) <= set(SECTIONS)
                and all(isinstance(v, str) and v in variants for v in value.values()))

    def annotate(selection: dict, prefix: str = "") -> None:
        for approach, variant in selection.items():
            label = f"{prefix}{approach}"
            chosen.setdefault(variant, [])
            if label not in chosen[variant]:
                chosen[variant].append(label)

    for key, value in block_h.items():
        if key == "variantes" or not isinstance(value, dict):
            continue
        if is_selection(value):
            annotate(value)
        else:
            for family, sub in value.items():
                if is_selection(sub):
                    annotate(sub, f"{family}:")
    return chosen


def _param_text(value) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text[:MAX_PARAM_LENGTH]


def variant_params(result: dict) -> tuple[dict[str, str], dict[str, float]]:
    """Columns, threshold selection and other non-fold data of a variant."""
    params, metrics = {}, {}
    for key, value in result.items():
        if _is_fold(value) or (isinstance(value, list) and any(_is_fold(x) for x in value)):
            continue
        if key == "columnas":
            params["columnas"] = _param_text(value)
            params["n_columnas"] = str(len(value))
        elif isinstance(value, dict):
            for leaf, item in _leaves(value, f"{key}.").items():
                number = _number(item)
                if number is not None:
                    metrics[leaf] = number
                elif item is not None:
                    params[leaf] = _param_text(item)
        elif value is not None:
            number = _number(value)
            if number is not None:
                metrics[key] = number
            else:
                params[key] = _param_text(value)
    return params, metrics


# ---------------------------------------------------------------------------
# Execution context
# ---------------------------------------------------------------------------

def _git(*args: str) -> str | None:
    try:
        output = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return output.stdout.strip() if output.returncode == 0 else None


def environment_tags() -> dict[str, str]:
    """Git commit, platform and the versions that affect reproducibility."""
    import importlib.metadata as md

    labels = {
        "plataforma": f"{platform.system()} {platform.release()} {platform.machine()}",
        "python": platform.python_version(),
    }
    for package in ("xgboost", "scikit-learn", "pandas", "numpy", "great_expectations", "mlflow"):
        try:
            labels[f"version.{package}"] = md.version(package)
        except md.PackageNotFoundError:
            pass
    commit = _git("rev-parse", "HEAD")
    if commit:
        labels["mlflow.source.git.commit"] = commit
        status = _git("status", "--porcelain")
        labels["git_cambios_sin_commit"] = "si" if status else "no"
    return labels


def _fold_models(output_dir: Path, horizon, variant: str, block: str) -> list[Path]:
    """``xgb_h{h}_{variant}_{approach}_{block}.json`` files saved by the module."""
    return [p for approach in ("regresion", "clasificacion")
            if (p := output_dir / f"xgb_h{horizon}_{variant}_{approach}_{block}.json").exists()]


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def run_with_fingerprint(experiment_id: str, fingerprint: str) -> str | None:
    """Id of the parent run already logged with that cache fingerprint (``None`` if there is none)."""
    import mlflow

    runs = mlflow.search_runs(
        experiment_ids=[experiment_id], output_format="list",
        filter_string=f"tags.{FINGERPRINT_TAG} = '{fingerprint}'")
    parents = [r for r in runs if "mlflow.parentRunId" not in r.data.tags and r.data.tags.get("duplicada") != "true"]
    return min(parents, key=lambda r: r.info.start_time).info.run_id if parents else None


def log_report(
    experiment: str, report: dict, *, metrics_path: Path, output_dir: Path,
    gold_dir: Path | None = None, data_quality: dict | None = None,
    description: str | None = None, tracking_uri: str | None = None,
    log_datasets: bool = True, fingerprint: str | None = None,
) -> str:
    """Log an already computed report in MLflow and return the parent run id.

    With ``fingerprint`` (the one from ``cache_experimentos``), if the experiment
    already has a parent run with that fingerprint no new one is logged: the
    existing one is returned. That way, rerunning a notebook without changes in
    data or code does not duplicate runs.
    """
    import mlflow

    metrics_path, output_dir = Path(metrics_path), Path(output_dir)
    experiment_name = f"{EXPERIMENT_PREFIX}/{experiment}"
    experiment_id = set_experiment(experiment_name, tracking_uri)
    if fingerprint is not None:
        existing = run_with_fingerprint(experiment_id, fingerprint)
        if existing is not None:
            print(f"MLflow: ya existe el run {existing} con huella {fingerprint[:12]} en '{experiment_name}'; "
                  "no se registra otro")
            return existing

    parent_params = {}
    parent_tags = {"experimento": experiment, **environment_tags()}
    if fingerprint is not None:
        parent_tags[FINGERPRINT_TAG] = fingerprint
    for key, value in report.items():
        if key in {"horizontes", "parametros"}:
            continue
        if isinstance(value, str) and key.startswith("sha256"):
            parent_tags[key] = value
        elif not isinstance(value, dict):
            parent_params[key] = _param_text(value)
    parent_params.update({f"xgb.{k}": _param_text(v) for k, v in report.get("parametros", {}).items()})
    for h, block_h in report["horizontes"].items():
        for key, value in block_h.items():
            if key == "variantes" or isinstance(value, (dict, list)):
                continue
            if key.startswith("sha256"):
                parent_tags[f"h{h}.{key}"] = str(value)
            else:
                parent_params[f"h{h}.{key}"] = _param_text(value)
    if data_quality is not None:
        parent_tags["calidad_datos.exito"] = "si" if data_quality.get("exito") else "no"
    if description:
        parent_tags["mlflow.note.content"] = description

    with mlflow.start_run(experiment_id=experiment_id, run_name=f"{experiment}",
                          tags=parent_tags) as parent:
        mlflow.log_params(parent_params)
        if data_quality is not None:
            mlflow.log_dict(data_quality, "calidad_datos/great_expectations.json")
            for name, suite in data_quality.get("suites", {}).items():
                mlflow.log_metric(f"gx.{name}.porcentaje_exito", suite["porcentaje_exito"])
                mlflow.log_metric(f"gx.{name}.fallidas", suite["fallidas_n"])
        if metrics_path.exists():
            mlflow.log_artifact(str(metrics_path), "reporte")
        if gold_dir is not None:
            manifest = Path(gold_dir) / "manifest_fase6.json"
            if manifest.exists():
                mlflow.log_artifact(str(manifest), "linaje")
            if log_datasets:
                _log_datasets(report, Path(gold_dir))
        if output_dir.exists():
            for file in sorted(output_dir.iterdir()):
                if file.is_file() and not file.name.startswith("xgb_"):
                    mlflow.log_artifact(str(file), "salidas")

        for h, block_h in report["horizontes"].items():
            chosen = selected_by_horizon(block_h)
            for variant, result in block_h.get("variantes", {}).items():
                folds = variant_folds(result)
                params_v, metrics_v = variant_params(result)
                tags_v = {"horizonte": str(h), "variante": variant, "nivel": "variante"}
                if variant in chosen:
                    tags_v["seleccionada_en_validacion"] = ",".join(chosen[variant])
                with mlflow.start_run(experiment_id=experiment_id, run_name=f"h{h} · {variant}",
                                      nested=True, tags=tags_v):
                    mlflow.log_params({"horizonte": str(h), "variante": variant, **params_v})
                    mlflow.log_metrics({**metrics_v, **variant_summary(folds)})
                    for fold in folds:
                        metrics_f, params_f = fold_metrics(fold)
                        tags_f = {"horizonte": str(h), "variante": variant,
                                       "bloque": fold["bloque"], "tipo": str(fold.get("tipo")),
                                       "nivel": "fold"}
                        with mlflow.start_run(experiment_id=experiment_id,
                                              run_name=f"h{h} · {variant} · {fold['bloque']}",
                                              nested=True, tags=tags_f):
                            mlflow.log_params(params_f)
                            mlflow.log_metrics(metrics_f)
                            for model in _fold_models(output_dir, h, variant, fold["bloque"]):
                                mlflow.log_artifact(str(model), "modelos")
        run_id = parent.info.run_id
    print(f"MLflow: run {run_id} en '{experiment_name}' ({default_tracking_uri()})")
    return run_id


def _log_datasets(report: dict, gold_dir: Path) -> None:
    """Attach each gold dataset used to the parent run (MLflow *Datasets* tab)."""
    import warnings

    import mlflow
    import pandas as pd

    for h, block_h in report["horizontes"].items():
        file = gold_dir / str(block_h.get("archivo_gold", ""))
        if not file.is_file():
            continue
        data = pd.read_csv(file, dtype={"ubigeo": "string"})
        with warnings.catch_warnings():
            # MLflow warnings about schema inference that do not apply here.
            warnings.simplefilter("ignore", UserWarning)
            dataset = mlflow.data.from_pandas(
                data, source=file.resolve().as_uri(), name=file.name, targets="brote")
            mlflow.log_input(dataset, context=f"gold_h{h}")


def log_study(
    experiment: str, trials, *, parent: dict, artifacts: list[Path] = (), tables: dict | None = None,
    fingerprint: str | None = None, description: str | None = None, tracking_uri: str | None = None,
) -> str:
    """Log a hyperparameter study: one parent run and one child run per trial.

    ``trials`` is a table with ``numero``, ``estado``, ``objetivo``, ``param_*``
    columns and numeric metrics per trial. Trials that did not complete are
    logged with ``estado`` as a tag and no objective, so they are not lost
    silently. ``parent`` holds the study's ``params`` and ``metricas`` (best
    parameters, base value, number of failures...). With ``fingerprint``, an
    already logged study is not duplicated.
    """
    import mlflow

    experiment_name = f"{EXPERIMENT_PREFIX}/{experiment}"
    experiment_id = set_experiment(experiment_name, tracking_uri)
    if fingerprint is not None:
        existing = run_with_fingerprint(experiment_id, fingerprint)
        if existing is not None:
            print(f"MLflow: ya existe el run {existing} con huella {fingerprint[:12]} en '{experiment_name}'; "
                  "no se registra otro")
            return existing
    labels = {"experimento": experiment, "nivel": "estudio", **environment_tags()}
    if fingerprint is not None:
        labels[FINGERPRINT_TAG] = fingerprint
    if description:
        labels["mlflow.note.content"] = description
    with mlflow.start_run(experiment_id=experiment_id, run_name=experiment, tags=labels) as run_padre:
        mlflow.log_params({k: _param_text(v) for k, v in parent.get("params", {}).items()})
        mlflow.log_metrics({k: float(v) for k, v in parent.get("metricas", {}).items()
                            if _number(v) is not None})
        for path in artifacts:
            if Path(path).exists():
                mlflow.log_artifact(str(path), "estudio")
        for name, table in (tables or {}).items():
            mlflow.log_dict(json.loads(table.to_json(orient="records", force_ascii=False)), f"tablas/{name}.json")
        for row in trials.sort_values("numero").to_dict("records"):
            status = str(row["estado"])
            with mlflow.start_run(experiment_id=experiment_id, run_name=f"trial {int(row['numero'])}", nested=True,
                                  tags={"nivel": "trial", "estado": status, "es_base": str(bool(row.get("es_base")))}):
                mlflow.log_params({k[len("param_"):]: _param_text(v) for k, v in row.items()
                                   if k.startswith("param_") and v is not None and not (isinstance(v, float) and v != v)})
                metrics = {k: _number(v) for k, v in row.items()
                            if k not in ("numero", "estado", "es_base") and not k.startswith("param_")}
                mlflow.log_metrics({k: v for k, v in metrics.items() if v is not None})
        run_id = run_padre.info.run_id
    print(f"MLflow: estudio {run_id} en '{experiment_name}' ({default_tracking_uri()})")
    return run_id


def log_or_warn(experiment: str, report: dict, **kwargs) -> str | None:
    """Log in MLflow; if it fails, warn without losing the outputs already written.

    The experiment already saved its JSON, predictions and models before
    calling this, so an MLflow problem does not invalidate the run.
    """
    try:
        return log_report(experiment, report, **kwargs)
    except Exception as error:  # noqa: BLE001 - reported and we carry on
        print(f"AVISO: no se pudo registrar '{experiment}' en MLflow: {error!r}. "
              "Las métricas y modelos se guardaron igual en docs/ y models/.")
        return None
