"""Auditable input contract for the XGBoost experiments.

Phase 7 lists candidates and checks gold; it neither fits models nor decides
the final training and test cutoff.
"""

import hashlib
import json
from pathlib import Path

import pandas as pd

from denguekay.data.loading import load_integrated
from denguekay.features.gold import HORIZONS, gold_columns, validate_gold
from denguekay.data.validation.forecast_contract import EXPERIMENTAL_HORIZONS
from denguekay.features.sociodemographics import DIRECT
from denguekay.data.processing.socio_interpolation import SOCIO_COLUMNS
from denguekay.config.paths import (
    GOLD, RESEARCH, SILVER_EPI_HISTORICAL, SILVER_INTEGRATED, UBIGEO_CATALOG,
)
from denguekay.data.validation.forecast_contract import KEY
from denguekay.data.validation.integrated_expectations import (
    coverage_path, load_case_coverage, validate_complete, validate_geography,
)

NON_PREDICTORS = (
    "casos_Dengue", "brote", "umbral_brote_casos", "ubigeo", "anio",
    "semana", "provincia", "distrito", "distrito_key", "semana_inicio",
    "origen_inicio", "origen_cierre", "socio_2017_disponible_al_origen",
    "socio_fracciones_interpoladas_con_2025",
)


def predictor_families(horizon: int) -> dict[str, list[str]]:
    """Return candidates per family for a horizon of 1 to 6 weeks.

    The optional families are tried through ablations; returning them here does
    not mean training them all together nor validating their operational
    availability.
    """
    if horizon not in EXPERIMENTAL_HORIZONS:
        raise ValueError("El horizonte debe estar entre 1 y 6 semanas")
    h = horizon
    return {
        "historia": [f"casos_lag_{h}", f"casos_lag_{h + 1}",
                     f"casos_media_4_h{h}", f"casos_semanas_positivas_4_h{h}"],
        "calendario": ["semana_epi_seno", "semana_epi_coseno"],
        "vecinos": [f"vecinos_media_casos_knn5_h{h}",
                     f"vecinos_frac_con_casos_knn5_h{h}"],
        "jerarquia": [f"provincia_otros_casos_h{h}",
                      f"provincia_otros_frac_con_casos_h{h}",
                      f"region_otros_casos_h{h}",
                      f"region_otros_frac_con_casos_h{h}"],
        "clima": [f"hum_rel_media_media5_h{h}",
                  f"precip_total_mm_media5_h{h}"],
        "socio_2017": [*(f"{c}_2017" for c in DIRECT),
                       "log_poblacion_censo_2017"],
        "socio_anual_reconstruida": [
            *(f"{c}_anual" for c in SOCIO_COLUMNS if c != "poblacion"),
            "log_poblacion_anual",
        ],
    }


def validate_model_columns(
    gold: pd.DataFrame, manifest: dict, horizon: int,
) -> dict[str, list[str]]:
    """Reject unexpected columns, predictor labels and inconsistent lineage."""
    if gold.columns.duplicated().any() or set(gold) != set(gold_columns(horizon, with_outbreak=True)):
        raise ValueError("El esquema gold no coincide con el horizonte etiquetado")
    families = predictor_families(horizon)
    candidates = [col for cols in families.values() for col in cols]
    if len(candidates) != len(set(candidates)):
        raise ValueError("Una candidata aparece en más de una familia")
    if set(manifest.get("columnas_no_predictoras", [])) != set(NON_PREDICTORS):
        raise ValueError("El manifiesto no enumera todas las exclusiones del modelo")
    if set(candidates) & set(NON_PREDICTORS) or set(candidates) | set(NON_PREDICTORS) != set(gold):
        raise ValueError("Las candidatas y exclusiones no particionan gold")
    return families


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit_handoff(
    silver_path: Path = SILVER_INTEGRATED, gold_dir: Path = GOLD,
    catalog_path: Path = UBIGEO_CATALOG,
    history_path: Path = SILVER_EPI_HISTORICAL,
) -> dict:
    """Validate the persisted files, lineage and coverage before modelling.

    It only reads silver and gold. Returns reproducible figures for notebook 23.
    """
    silver_path, gold_dir, catalog_path, history_path = map(
        Path, (silver_path, gold_dir, catalog_path, history_path),
    )
    panel = load_integrated(silver_path)
    cobertura_path = coverage_path(silver_path)
    coverage = load_case_coverage(cobertura_path)
    if coverage is None:
        raise ValueError("Falta la cobertura epidemiológica de silver")
    validate_complete(panel, coverage)
    validate_geography(panel, catalog_path)
    manifest = json.loads((gold_dir / "manifest_fase6.json").read_text(encoding="utf-8"))
    if (manifest.get("fuente") != silver_path.name
            or manifest.get("sha256_fuente") != _sha256(silver_path)
            or manifest.get("sha256_cobertura") != _sha256(cobertura_path)
            or manifest.get("sha256_catalogo_geografico") != _sha256(catalog_path)):
        raise ValueError("El linaje de silver/cobertura/geografía no coincide con gold")
    rule = manifest.get("regla_brote")
    if not isinstance(rule, dict) or int(rule.get("minimo_casos", 0)) < 1:
        raise ValueError("Gold no tiene una regla de brote documentada")
    if (rule.get("fuente_historia") != history_path.name
            or rule.get("sha256_fuente_historia") != _sha256(history_path)):
        raise ValueError("La historia usada para etiquetar brote difiere del manifiesto")
    summary = {"fuente": silver_path.name, "sha256_fuente": _sha256(silver_path),
               "regla_brote": rule, "horizontes": {}}
    labels = []
    for h in HORIZONS:
        record = manifest.get("horizontes", {}).get(str(h), {})
        file = gold_dir / f"{silver_path.stem}_h{h}_gold.csv"
        if record.get("archivo") != file.name or record.get("sha256") != _sha256(file):
            raise ValueError(f"El hash o nombre de gold h={h} no coincide con el manifiesto")
        gold = pd.read_csv(file, dtype={"ubigeo": "string"},
                           parse_dates=["semana_inicio", "origen_inicio", "origen_cierre"])
        validation = validate_gold(gold, panel, h, with_outbreak=True,
                                 min_outbreak_cases=rule["minimo_casos"])
        families = validate_model_columns(gold, manifest, h)
        candidates = [col for cols in families.values() for col in cols]
        summary["horizontes"][str(h)] = {
            **validation,
            "columnas": len(gold.columns),
            "candidatas": len(candidates),
            "filas_candidatas_completas": int(gold[candidates].notna().all(axis=1).sum()),
            "familias": families,
            "nulos_por_familia": {
                name: int(gold[cols].isna().any(axis=1).sum())
                for name, cols in families.items()
            },
            "positivos_brote": int(gold.brote.sum()),
            "positivos_por_anio": {
                str(y): int(n) for y, n in gold.groupby("anio").brote.sum().items()
            },
        }
        labels.append(gold[KEY + ["brote", "umbral_brote_casos"]].sort_values(KEY).reset_index(drop=True))
    if not labels[0].equals(labels[1]):
        raise ValueError("Las etiquetas difieren entre horizontes")
    if summary["horizontes"]["2"]["positivos_por_anio"] != manifest.get("positivos_brote_por_anio"):
        raise ValueError("Los conteos de brote difieren del manifiesto")
    return summary


def summarize_ablations(metrics_dir: Path = RESEARCH / "02_feature_engineering" / "docs" / "metricas") -> dict:
    """Summarise the ridge count comparisons of phases 4 and 5 per horizon.

    Delta MAE = candidate model minus its reference; a negative value favours
    the candidate. It only uses results already measured on the same time cutoffs.
    """
    metrics_dir = Path(metrics_dir)
    outputs = {}
    for phase, file in (("clima", "fase4_clima.json"),
                          ("sociodemografia", "fase5_sociodemografia.json")):
        results = json.loads((metrics_dir / file).read_text(encoding="utf-8"))["resultados"]
        by_model = {(int(r["horizonte"]), int(r["temporada"]), r["modelo"]): r
                      for r in results}
        if len(by_model) != len(results):
            raise ValueError(f"{file} tiene filas de ablación duplicadas")
        phase_summary = {}
        for h in HORIZONS:
            models = sorted({m for h0, _, m in by_model if h0 == h}
                            - {"persistencia", "historia_calendario"})
            summary_h = {}
            for model in models:
                reference = "mas_clima" if model.startswith("mas_clima_") else "historia_calendario"
                seasons = sorted(y for h0, y, m in by_model if h0 == h and m == model)
                deltas = {}
                for y in seasons:
                    base = by_model.get((h, y, reference))
                    if base is None:
                        raise ValueError(f"{file}: falta referencia {reference} para {h=}, {y=}")
                    candidate = by_model[(h, y, model)]
                    if any(candidate[c] != base[c] for c in (
                        "n_entrenamiento", "n_prueba", "primera_semana_prueba", "corte_ajuste"
                    )):
                        raise ValueError(f"{file}: {model} y {reference} usan cortes/filas distintos")
                    deltas[str(y)] = candidate["mae_casos"] - base["mae_casos"]
                summary_h[model] = {
                    "referencia": reference,
                    "temporadas": seasons,
                    "cortes_con_menor_mae": sum(delta < 0 for delta in deltas.values()),
                    "delta_mae_casos_por_temporada": {
                        y: round(delta, 6) for y, delta in deltas.items()
                    },
                }
            phase_summary[str(h)] = summary_h
        outputs[phase] = phase_summary
    return outputs
