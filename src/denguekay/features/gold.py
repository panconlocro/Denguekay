"""Integration of the candidates for the weekly 2- and 4-week forecast.

Gold keeps one row per target week. Learned statistics (climatology, PCA,
alert threshold) are fitted later inside each fold.
"""

import hashlib
import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from denguekay.data.loading import load_integrated
from denguekay.features.climate import build_observed_climate
from denguekay.features.outbreak_label import SeasonalOutbreakConfig, label_seasonal_outbreak
from denguekay.features.history_calendar import build_history_calendar
from denguekay.features.sociodemographics import (
    DIRECT, build_sociodemography, build_raw_annual_sociodemography,
    reference_2017,
)
from denguekay.features.neighbors import build_neighbors_hierarchy
from denguekay.data.processing.socio_interpolation import SOCIO_COLUMNS
from denguekay.config.paths import GOLD, SILVER_EPI_HISTORICAL, SILVER_INTEGRATED, UBIGEO_CATALOG
from denguekay.data.validation.forecast_contract import KEY, EXPERIMENTAL_HORIZONS, audit_origin
from denguekay.data.validation.integrated_expectations import (
    coverage_path, load_case_coverage, validate_complete, validate_geography,
)

# Persisted gold: only h=2 and h=4. The other EXPERIMENTAL_HORIZONS
# are built in memory with build_gold and are never written to data/.
HORIZONS = (2, 4)
SOCIO_2017_DATE = "2019-01-01"  # conservative barrier, not a verified date of the Excel file
BASE = ["provincia", "distrito", "distrito_key", *KEY, "semana_inicio", "casos_Dengue"]


def gold_columns(horizon: int, *, with_outbreak: bool = False) -> list[str]:
    """Contract of candidate columns and metadata for one horizon."""
    if horizon not in EXPERIMENTAL_HORIZONS:
        raise ValueError("El horizonte debe estar entre 1 y 6 semanas")
    columns = [
        *BASE, "origen_inicio", "origen_cierre",
        f"casos_lag_{horizon}", f"casos_lag_{horizon + 1}",
        f"casos_media_4_h{horizon}", f"casos_semanas_positivas_4_h{horizon}",
        "semana_epi_seno", "semana_epi_coseno",
        f"vecinos_media_casos_knn5_h{horizon}",
        f"vecinos_frac_con_casos_knn5_h{horizon}",
        f"provincia_otros_casos_h{horizon}",
        f"provincia_otros_frac_con_casos_h{horizon}",
        f"region_otros_casos_h{horizon}",
        f"region_otros_frac_con_casos_h{horizon}",
        f"hum_rel_media_media5_h{horizon}",
        f"precip_total_mm_media5_h{horizon}",
        *(f"{c}_2017" for c in DIRECT), "log_poblacion_censo_2017",
        *(f"{c}_anual" for c in SOCIO_COLUMNS if c != "poblacion"),
        "log_poblacion_anual", "socio_2017_disponible_al_origen",
        "socio_fracciones_interpoladas_con_2025",
    ]
    if with_outbreak:
        columns += ["umbral_brote_casos", "brote"]
    return columns


def _append(base: pd.DataFrame, fragment: pd.DataFrame) -> pd.DataFrame:
    """Join a family without changing grain, date, order or existing names."""
    if fragment.duplicated(KEY).any() or len(fragment) != len(base):
        raise ValueError("Una familia tiene llaves duplicadas o perdió filas")
    origin_dates = [c for c in ("origen_inicio", "origen_cierre") if c in base and c in fragment]
    if origin_dates:
        check = base[KEY + origin_dates].merge(
            fragment[KEY + origin_dates], on=KEY, validate="one_to_one",
            suffixes=("", "_familia"), sort=False)
        if len(check) != len(base):
            raise ValueError("Las fechas de origen de la familia tienen llaves distintas")
        for column in origin_dates:
            if not pd.to_datetime(check[column]).equals(pd.to_datetime(check[f"{column}_familia"])):
                raise ValueError(f"La familia tiene {column} distinto")
        fragment = fragment.drop(columns=origin_dates)
    extras = set(fragment) - set(KEY + ["semana_inicio"])
    if extras & set(base):
        raise ValueError(f"Columnas de features repetidas: {sorted(extras & set(base))}")
    output = base.merge(fragment, on=KEY, how="left", validate="one_to_one", sort=False,
                        suffixes=("", "_familia"))
    if len(output) != len(base) or output[KEY].ne(base[KEY]).any().any():
        raise ValueError("El cruce de features alteró filas o su orden")
    if not output.semana_inicio.eq(output.pop("semana_inicio_familia")).all():
        raise ValueError("La fecha de la familia difiere de la semana objetivo")
    return output


def build_gold(
    panel: pd.DataFrame, horizon: int, labels: pd.DataFrame | None = None,
    *, min_outbreak_cases: int = 1,
) -> pd.DataFrame:
    """Integrate candidates without fitting statistics on test data.

    It keeps the first rows with the expected NaN lags. The silver yearly
    population and fractions are a retrospective reconstruction that includes
    the 2025 end point; their use must be evaluated separately.
    """
    if horizon not in EXPERIMENTAL_HORIZONS:
        raise ValueError("El horizonte debe estar entre 1 y 6 semanas")
    missing = set(BASE) - set(panel)
    if missing:
        raise ValueError(f"Faltan columnas del integrado: {sorted(missing)}")
    audit_origin(panel, horizon)
    reference = reference_2017(panel)
    output = panel[BASE].sort_values(["ubigeo", "semana_inicio"]).reset_index(drop=True).copy()
    output["semana_inicio"] = pd.to_datetime(output["semana_inicio"])
    families = (
        build_history_calendar(panel, horizon),
        build_neighbors_hierarchy(panel, horizon),
        build_observed_climate(panel, horizon),
        build_sociodemography(
            panel, horizon, reference, SOCIO_2017_DATE,
            mask_before_availability=False,
        ),
        build_raw_annual_sociodemography(panel),
    )
    for family in families:
        output = _append(output, family)
    output["socio_2017_disponible_al_origen"] = output.origen_cierre.ge(pd.Timestamp(SOCIO_2017_DATE))
    output["socio_fracciones_interpoladas_con_2025"] = output.anio.between(2018, 2024)
    if labels is not None:
        if set(labels) != set(KEY + ["umbral_brote_casos", "brote"]):
            raise ValueError("Las etiquetas de brote tienen un esquema inesperado")
        if labels.duplicated(KEY).any() or len(labels) != len(panel):
            raise ValueError("Las etiquetas de brote alteran el grano del panel")
        output = output.merge(labels, on=KEY, how="left", validate="one_to_one", sort=False)
    validate_gold(output, panel, horizon, with_outbreak=labels is not None,
                 min_outbreak_cases=min_outbreak_cases)
    return output


def validate_gold(
    gold: pd.DataFrame, silver: pd.DataFrame, horizon: int, *,
    with_outbreak: bool = False, min_outbreak_cases: int = 1,
) -> dict[str, int]:
    """Check keys, label, origin, start-up nulls and finiteness."""
    if horizon not in EXPERIMENTAL_HORIZONS:
        raise ValueError("Horizonte inválido")
    if len(gold) != len(silver) or gold.duplicated(KEY).any() or silver.duplicated(KEY).any():
        raise ValueError("Gold debe conservar las llaves únicas y el número de filas de silver")
    expected = set(gold_columns(horizon, with_outbreak=with_outbreak))
    if set(gold) != expected:
        raise ValueError(f"Esquema gold inesperado: faltan {sorted(expected - set(gold))}; sobran {sorted(set(gold) - expected)}")
    if gold.columns.duplicated().any() or any(c.endswith(("_x", "_y", "_familia")) for c in gold):
        raise ValueError("Gold contiene columnas duplicadas o sufijos de merge")
    base = silver[KEY + ["semana_inicio", "casos_Dengue"]].copy()
    base["semana_inicio"] = pd.to_datetime(base.semana_inicio)
    join = gold[KEY + ["semana_inicio", "casos_Dengue"]].merge(
        base, on=KEY, validate="one_to_one", suffixes=("", "_silver"))
    if len(join) != len(silver) or not join.semana_inicio.eq(join.semana_inicio_silver).all() or not join.casos_Dengue.eq(join.casos_Dengue_silver).all():
        raise ValueError("Gold cambió las semanas objetivo o las etiquetas de silver")
    audit = audit_origin(gold, horizon)
    origin = gold[KEY + ["origen_inicio", "origen_cierre"]].merge(
        audit[KEY + ["origen_inicio", "origen_cierre"]], on=KEY,
        suffixes=("", "_esperado"), validate="one_to_one")
    for field in ("origen_inicio", "origen_cierre"):
        actual = pd.to_datetime(origin[field])
        expected_value = pd.to_datetime(origin[f"{field}_esperado"])
        if not actual.equals(expected_value):
            raise ValueError(f"Gold tiene {field} fuera del horizonte")
    if not gold.socio_2017_disponible_al_origen.eq(
        pd.to_datetime(gold.origen_cierre).ge(pd.Timestamp(SOCIO_2017_DATE))).all():
        raise ValueError("La marca de disponibilidad censal no coincide con el origen")
    if not gold.socio_fracciones_interpoladas_con_2025.eq(gold.anio.between(2018, 2024)).all():
        raise ValueError("La marca de fracciones interpoladas no coincide con el año")
    if with_outbreak:
        if not gold.brote.isin([0, 1]).all() or not pd.to_numeric(gold.umbral_brote_casos, errors="coerce").ge(0).all():
            raise ValueError("La etiqueta o el umbral de brote son inválidos")
        expected_value = (gold.casos_Dengue.gt(gold.umbral_brote_casos)
                    & gold.casos_Dengue.ge(min_outbreak_cases)).astype("int8")
        if not gold.brote.eq(expected_value).all():
            raise ValueError("La etiqueta de brote no coincide con sus casos y umbral")
    order = gold.sort_values(["ubigeo", "semana_inicio"])
    position = order.groupby("ubigeo", sort=False).cumcount()
    startup = {
        f"casos_lag_{horizon}": horizon,
        f"casos_lag_{horizon + 1}": horizon + 1,
        f"casos_media_4_h{horizon}": horizon + 3,
        f"casos_semanas_positivas_4_h{horizon}": horizon + 3,
    }
    startup.update({c: horizon for c in gold if c.startswith(("vecinos_", "provincia_otros_", "region_otros_"))})
    startup.update({c: horizon + 4 for c in gold if c.endswith(f"_media5_h{horizon}")})
    for column, start in startup.items():
        if column not in order or not order[column].isna().eq(position.lt(start)).all():
            raise ValueError(f"Nulos o cobertura temporal inesperados en {column}")
    always = [c for c in gold if c not in set(KEY + ["semana_inicio", "origen_inicio", "origen_cierre", *startup])
              and pd.api.types.is_numeric_dtype(gold[c])]
    if gold[always].isna().any().any():
        raise ValueError("Hay nulos no esperados en columnas completas de gold")
    numeric = gold.select_dtypes(include="number")
    if not np.isfinite(numeric.to_numpy(float)[~numeric.isna().to_numpy()]).all():
        raise ValueError("Gold contiene valores numéricos no finitos")
    return {"filas": len(gold), "distritos": int(gold.ubigeo.nunique()),
            "semanas_por_distrito": int(gold.groupby("ubigeo").size().min()),
            "filas_con_ventanas_completas": int(position.ge(horizon + 4).sum()),
            "filas_sin_ventanas_completas": int(position.lt(horizon + 4).sum())}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_labels(
    panel: pd.DataFrame, outbreak: SeasonalOutbreakConfig,
    history_path: Path = SILVER_EPI_HISTORICAL,
) -> pd.DataFrame:
    """Label brote with the history before the panel, exactly like ``generate_gold``."""
    history = pd.read_csv(Path(history_path), dtype={"ubigeo": "string"})
    first = int(panel.anio.min())
    history = history.loc[history.anio.between(first - outbreak.anios_previos, first - 1)]
    return label_seasonal_outbreak(
        panel, history, multiplicador=outbreak.multiplicador,
        anios_previos=outbreak.anios_previos, minimo_casos=outbreak.minimo_casos,
    )


def generate_gold(
    input_path: Path = SILVER_INTEGRATED, output_dir: Path = GOLD,
    catalog_path: Path = UBIGEO_CATALOG,
    *, outbreak: SeasonalOutbreakConfig | None = None,
    history_path: Path = SILVER_EPI_HISTORICAL,
) -> dict[int, dict[str, object]]:
    """Validate silver, build both horizons and write reproducible CSV/lineage files."""
    input_path, output_dir = Path(input_path), Path(output_dir)
    panel = load_integrated(input_path)
    coverage = load_case_coverage(coverage_path(input_path))
    if coverage is None:
        raise ValueError("Falta el archivo de cobertura epidemiológica del integrado")
    validate_complete(panel, coverage)
    validate_geography(panel, catalog_path)
    labels = None
    if outbreak is not None:
        history_path = Path(history_path)
        labels = build_labels(panel, outbreak, history_path)
    outputs = {h: build_gold(panel, h, labels,
                                min_outbreak_cases=outbreak.minimo_casos if outbreak else 1)
               for h in HORIZONS}
    summary = {h: validate_gold(outputs[h], panel, h, with_outbreak=outbreak is not None,
                              min_outbreak_cases=outbreak.minimo_casos if outbreak else 1) for h in HORIZONS}
    output_dir.mkdir(parents=True, exist_ok=True)
    tmp_files: list[tuple[Path, Path]] = []
    try:
        for h in HORIZONS:
            destination = output_dir / f"{input_path.stem}_h{h}_gold.csv"
            with tempfile.NamedTemporaryFile(dir=output_dir, suffix=".csv.tmp", delete=False) as temp:
                tmp = Path(temp.name)
            tmp_files.append((tmp, destination))
            outputs[h].to_csv(tmp, index=False, date_format="%Y-%m-%d", float_format="%.17g")
            persisted = pd.read_csv(
                tmp, dtype={"ubigeo": "string"},
                parse_dates=["semana_inicio", "origen_inicio", "origen_cierre"],
            )
            validate_gold(persisted, panel, h, with_outbreak=outbreak is not None,
                         min_outbreak_cases=outbreak.minimo_casos if outbreak else 1)
            summary[h]["archivo"] = destination.name
            summary[h]["sha256"] = _sha256(tmp)
            summary[h]["columnas"] = len(outputs[h].columns)
        manifest = {
            "fuente": input_path.name,
            "sha256_fuente": _sha256(input_path),
            "sha256_cobertura": _sha256(coverage_path(input_path)),
            "catalogo_geografico": Path(catalog_path).name,
            "sha256_catalogo_geografico": _sha256(Path(catalog_path)),
            "grano": KEY,
            "etiqueta": "casos_Dengue (conteo observado)" if outbreak is None else "brote (semana elevada; 0/1)",
            "columnas_no_predictoras": [
                "casos_Dengue", "brote", "umbral_brote_casos", "ubigeo", "anio", "semana",
                "provincia", "distrito", "distrito_key", "semana_inicio",
                "origen_inicio", "origen_cierre", "socio_2017_disponible_al_origen",
                "socio_fracciones_interpoladas_con_2025",
            ] if outbreak is not None else [
                "casos_Dengue", "ubigeo", "anio", "semana", "provincia", "distrito", "distrito_key",
                "semana_inicio", "origen_inicio", "origen_cierre",
                "socio_2017_disponible_al_origen", "socio_fracciones_interpoladas_con_2025",
            ],
            "regla_brote": None if outbreak is None else {
                "metodo": "misma semana epidemiológica de años previos; media + multiplicador * DE muestral; desigualdad estricta",
                **asdict(outbreak), "fuente_historia": history_path.name,
                "sha256_fuente_historia": _sha256(history_path),
                "ausencia_historica": "sin registro tratado como cero, no cero notificado",
                "semana_53": "se suma a semana 52 para la referencia",
            },
            "fecha_disponibilidad_socio_2017_supuesta": SOCIO_2017_DATE,
            "limitaciones": [
                "Fracciones 2018-2024 interpoladas con 2025: reconstrucción retrospectiva.",
                "Población anual proyectada: fecha/version de publicación no comprobada.",
                "Casos y clima semanal suponen disponibilidad al cierre de su semana; latencia no verificada.",
                "No incluye anomalías climáticas ni PCA globales: ajustar por fold de entrenamiento.",
                "No hay partición train/test final; brote y umbral son etiquetas/metadatos, no predictores.",
            ],
            "horizontes": {str(h): summary[h] for h in HORIZONS},
        }
        if labels is not None:
            manifest["positivos_brote_por_anio"] = {
                str(y): int(n) for y, n in labels.groupby("anio").brote.sum().items()
            }
        manifest_destination = output_dir / "manifest_fase6.json"
        with tempfile.NamedTemporaryFile(dir=output_dir, suffix=".json.tmp", delete=False) as temp:
            tmp_manifest = Path(temp.name)
        tmp_files.append((tmp_manifest, manifest_destination))
        tmp_manifest.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        for tmp, destination in tmp_files:
            os.replace(tmp, destination)
    finally:
        for tmp, _ in tmp_files:
            tmp.unlink(missing_ok=True)
    return summary
