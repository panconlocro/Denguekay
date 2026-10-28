"""Data quality validation with Great Expectations (GX Core 1.x).

The suites are defined in code (``gold_expectations.py`` and
``integrated_expectations.py``) and this module runs them on the project's
CSV files. The GX context lives in ``great_expectations/gx/``: it keeps the
suites, the result of each validation and the Data Docs (HTML) in
``great_expectations/gx/uncommitted/data_docs/local_site/index.html``.

These suites **do not replace** the strict checks that already exist
(``preparar_gold``, ``auditar_traspaso``, ``validate_complete``): they
complement them with a declarative, readable and auditable report that is
also attached to every MLflow run. They only read ``data/``; they never write to it.

Usage from the repository root::

    python -m denguekay.data.validation.gx_quality            # integrated silver + gold h2/h4
    python -m denguekay.data.validation.gx_quality --sin-gold # integrated silver only
"""

import argparse
import copy
import json
import logging
import sys
from pathlib import Path

import great_expectations as gx
import pandas as pd

from denguekay.features.gold import HORIZONTES
from denguekay.data.processing.epi_sala import load_ubigeo_catalog
from denguekay.config.paths import GOLD, GX_DIR, SILVER_INTEGRATED, UBIGEO_CATALOG
from denguekay.data.validation.gold_expectations import expectations_for_gold
from denguekay.data.validation.integrated_expectations import integrated_gx_expectations

GX_SOURCE = "denguekay_pandas"
FULL_BATCH = "dataframe_completo"
GOLD_DATE_COLUMNS = ["semana_inicio", "origen_inicio", "origen_cierre"]


class DataValidationError(ValueError):
    """A GX suite failed; ``summary`` keeps the detail per expectation."""

    def __init__(self, message: str, summary: dict):
        super().__init__(message)
        self.summary = summary


def get_context(directory: Path = GX_DIR):
    """Open (or create) the GX file context and silence its progress bars."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    logging.getLogger("great_expectations").setLevel(logging.WARNING)
    context = gx.get_context(mode="file", project_root_dir=directory)
    try:
        from great_expectations.data_context.types.base import ProgressBarsConfig

        bars = context.variables.progress_bars
        if bars is None or bars.globally is not False:
            context.variables.progress_bars = ProgressBarsConfig(globally=False)
            context.variables.save()
    except Exception:  # pragma: no cover - cosmetic only
        pass
    return context


def data_docs_path(context) -> Path:
    """Return the local HTML index of the Data Docs."""
    return Path(context.root_directory) / "uncommitted" / "data_docs" / "local_site" / "index.html"


def _batch_definition(context, asset_name: str):
    """Get or create the pandas source, the asset and the 'whole dataframe' batch."""
    try:
        source = context.data_sources.get(GX_SOURCE)
    except (KeyError, ValueError, LookupError):
        source = context.data_sources.add_pandas(name=GX_SOURCE)
    try:
        asset = source.get_asset(asset_name)
    except LookupError:
        asset = source.add_dataframe_asset(name=asset_name)
    try:
        return asset.get_batch_definition(FULL_BATCH)
    except (KeyError, ValueError, LookupError):
        return asset.add_batch_definition_whole_dataframe(FULL_BATCH)


def _summarize(result, *, suite_name: str, asset_name: str, rows: int, docs: Path) -> dict:
    """Turn the checkpoint result into a serializable dict."""
    validations = list(result.run_results.values())
    if len(validations) != 1:
        raise RuntimeError("Se esperaba una sola validación por checkpoint")
    validation = validations[0]
    statistics = validation.statistics
    failed = []
    for item in validation.results:
        if item.success:
            continue
        config = item.expectation_config
        kwargs = {k: v for k, v in config.kwargs.items() if k in {"column", "column_list", "column_A", "column_B"}}
        detail = item.result or {}
        failed.append({
            "expectativa": config.type,
            **kwargs,
            "inesperados": detail.get("unexpected_count"),
            "porcentaje_inesperado": detail.get("unexpected_percent"),
            "muestra": [str(x) for x in (detail.get("partial_unexpected_list") or [])[:10]],
            "valor_observado": None if "observed_value" not in detail else str(detail["observed_value"])[:500],
            "excepcion": (item.exception_info or {}).get("exception_message") if item.exception_info else None,
        })
    return {
        "suite": suite_name,
        "activo": asset_name,
        "filas": int(rows),
        "exito": bool(validation.success),
        "evaluadas": int(statistics["evaluated_expectations"]),
        "exitosas": int(statistics["successful_expectations"]),
        "fallidas_n": int(statistics["unsuccessful_expectations"]),
        "porcentaje_exito": float(statistics["success_percent"] or 0.0),
        "fallidas": failed,
        "data_docs": str(docs),
    }


def validate_dataframe(
    data: pd.DataFrame, *, suite_name: str, expectations: list,
    asset_name: str, context=None, raise_on_failure: bool = True,
    update_docs: bool = True,
) -> dict:
    """Register the suite (the code is the source of truth) and validate ``data``.

    If ``raise_on_failure`` is true and an expectation fails, raise
    ``DataValidationError`` with the full summary.
    """
    context = context or get_context()
    suite = context.suites.add_or_update(
        gx.ExpectationSuite(name=suite_name, expectations=[copy.copy(e) for e in expectations]))
    definition = context.validation_definitions.add_or_update(
        gx.ValidationDefinition(name=suite_name, data=_batch_definition(context, asset_name), suite=suite))
    actions = [gx.checkpoint.UpdateDataDocsAction(name="actualizar_data_docs")] if update_docs else []
    checkpoint = context.checkpoints.add_or_update(gx.Checkpoint(
        name=f"checkpoint_{suite_name}", validation_definitions=[definition],
        actions=actions, result_format={"result_format": "SUMMARY"}))
    result = checkpoint.run(batch_parameters={"dataframe": data})
    summary = _summarize(result, suite_name=suite_name, asset_name=asset_name,
                       rows=len(data), docs=data_docs_path(context))
    if raise_on_failure and not summary["exito"]:
        detail = "; ".join(
            f"{f['expectativa']}({f.get('column') or f.get('column_list') or ''}): {f['inesperados']}"
            for f in summary["fallidas"][:8])
        raise DataValidationError(
            f"La suite GX '{suite_name}' falló {summary['fallidas_n']} de "
            f"{summary['evaluadas']} expectativas: {detail}. Ver {summary['data_docs']}", summary)
    return summary


def catalog_ubigeos(catalog_path: Path = UBIGEO_CATALOG) -> list[str]:
    """List of six-digit UBIGEO codes of the versioned Piura catalogue."""
    return sorted(load_ubigeo_catalog(Path(catalog_path))["ubigeo"].astype(str))


def read_gold(gold_dir: Path, horizon: int, stem: str = SILVER_INTEGRATED.stem) -> tuple[pd.DataFrame, Path]:
    """Read gold the same way the training modules do (ubigeo as text)."""
    file = Path(gold_dir) / f"{stem}_h{horizon}_gold.csv"
    gold = pd.read_csv(file, dtype={"ubigeo": "string"}, parse_dates=GOLD_DATE_COLUMNS)
    return gold, file


def validate_gold_gx(
    gold_dir: Path = GOLD, *, horizons=HORIZONTES, context=None,
    catalog_path: Path = UBIGEO_CATALOG, raise_on_failure: bool = True,
) -> dict[str, dict]:
    """Validate each gold per horizon with its ``gold_h{h}`` suite."""
    context = context or get_context()
    ubigeos = catalog_ubigeos(catalog_path)
    output = {}
    for h in horizons:
        gold, file = read_gold(gold_dir, h)
        summary = validate_dataframe(
            gold, suite_name=f"gold_h{h}", expectations=expectations_for_gold(h, ubigeos),
            asset_name=f"gold_h{h}", context=context, raise_on_failure=raise_on_failure)
        summary["archivo"] = file.name
        output[f"gold_h{h}"] = summary
    return output


def validate_integrated_gx(
    silver_path: Path = SILVER_INTEGRATED, *, context=None,
    catalog_path: Path = UBIGEO_CATALOG, raise_on_failure: bool = True,
) -> dict:
    """Validate the integrated silver panel (no features) with its suite."""
    context = context or get_context()
    silver_path = Path(silver_path)
    data = pd.read_csv(silver_path, dtype={"ubigeo": "string"}, parse_dates=["semana_inicio"])
    summary = validate_dataframe(
        data, suite_name="silver_integrado",
        expectations=integrated_gx_expectations(catalog_ubigeos(catalog_path)),
        asset_name="silver_integrado", context=context, raise_on_failure=raise_on_failure)
    summary["archivo"] = silver_path.name
    return summary


def validate_modeling_inputs(
    *, gold_dir: Path = GOLD, silver_path: Path | None = None,
    gx_directory: Path = GX_DIR, raise_on_failure: bool = True,
) -> dict:
    """Validate the inputs of an experiment before training.

    It always validates gold h2 and h4, and also integrated silver when the
    experiment reads it (``silver_path``). Returns a summary that can be
    attached to MLflow.
    """
    context = get_context(gx_directory)
    suites = {}
    if silver_path is not None:
        suites["silver_integrado"] = validate_integrated_gx(silver_path, context=context, raise_on_failure=raise_on_failure)
    suites.update(validate_gold_gx(gold_dir, context=context, raise_on_failure=raise_on_failure))
    return {
        "herramienta": f"great_expectations {gx.__version__}",
        "exito": all(s["exito"] for s in suites.values()),
        "suites": suites,
        "data_docs": str(data_docs_path(context)),
    }


def main() -> None:
    """CLI: ``python -m denguekay.data.validation.gx_quality``. Exits with code 1 if anything fails."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--silver", type=Path, default=SILVER_INTEGRATED)
    parser.add_argument("--gold-dir", type=Path, default=GOLD)
    parser.add_argument("--sin-gold", action="store_true", help="Valida solo silver integrado")
    parser.add_argument("--json", type=Path, default=None, help="Ruta opcional para guardar el resumen")
    args = parser.parse_args()
    context = get_context()
    suites = {"silver_integrado": validate_integrated_gx(args.silver, context=context, raise_on_failure=False)}
    if not args.sin_gold:
        suites.update(validate_gold_gx(args.gold_dir, context=context, raise_on_failure=False))
    for name, r in suites.items():
        status = "OK   " if r["exito"] else "FALLA"
        print(f"[{status}] {name}: {r['exitosas']}/{r['evaluadas']} expectativas ({r['filas']} filas)")
        for f in r["fallidas"]:
            print(f"         - {f['expectativa']} {f.get('column') or f.get('column_list') or ''}: "
                  f"{f['inesperados']} inesperados, muestra={f['muestra'][:5]}")
    print(f"Data Docs: {data_docs_path(context)}")
    if args.json:
        args.json.write_text(json.dumps(suites, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sys.exit(0 if all(r["exito"] for r in suites.values()) else 1)


if __name__ == "__main__":
    main()
