"""Fixed 2017 district traits and reconstructed yearly estimates.

The silver holds fractions interpolated with the 2025 end point. This module
keeps the fixed 2017 alternative and allows trying the yearly series
separately. The latter do not represent a real-time backtest.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from denguekay.data.validation.forecast_contract import KEY, EXPERIMENTAL_HORIZONS, audit_origin
from denguekay.data.processing.socio_interpolation import SOCIO_COLUMNS


DIRECT = ("fraccion_rural", "fraccion_menores_15", "fraccion_desague_red")


@dataclass(frozen=True)
class UrbanAxis:
    """PCA of the 2017 fractions fitted on training districts."""

    columns: tuple[str, ...]
    media: pd.Series
    std: pd.Series
    loadings: pd.Series
    explained_variance: float
    fit_districts: frozenset[str]


def reference_2017(panel: pd.DataFrame) -> pd.DataFrame:
    """Extract one row per UBIGEO with the 2017 fractions and census population.

    It requires each value to be constant across the 2017 weeks and every
    district of the panel to have a reference. It uses no later years.
    """
    if panel.empty or "anio" not in panel or "ubigeo" not in panel:
        raise ValueError("El panel no tiene llaves demográficas")
    columns = tuple(c for c in panel if c.startswith("fraccion_"))
    if len(columns) != 15 or "poblacion" not in panel:
        raise ValueError("Se esperan las 15 fracciones y poblacion del integrado")
    data = panel.loc[panel.anio.eq(2017), ["ubigeo", "poblacion", *columns]].copy()
    if data.empty or data.ubigeo.isna().any():
        raise ValueError("No hay referencia distrital de 2017")
    present = set(data.ubigeo.astype(str))
    missing = set(panel.ubigeo.astype(str)) - present
    if missing:
        raise ValueError(f"Distritos sin referencia de 2017: {sorted(missing)}")
    numeric = ["poblacion", *columns]
    for c in numeric:
        data[c] = pd.to_numeric(data[c], errors="raise")
    if data[numeric].isna().any().any() or not np.isfinite(data[numeric].to_numpy(float)).all():
        raise ValueError("La referencia de 2017 contiene nulos o valores no finitos")
    if (data.poblacion <= 0).any() or not data[list(columns)].ge(0).all().all() or not data[list(columns)].le(1).all().all():
        raise ValueError("Población o fracciones de 2017 fuera de rango")
    dispersion = data.groupby("ubigeo")[numeric].nunique(dropna=False)
    if dispersion.gt(1).any().any():
        raise ValueError("La referencia de 2017 cambia entre semanas de un distrito")
    reference = data.drop_duplicates("ubigeo").sort_values("ubigeo").reset_index(drop=True)
    if reference.ubigeo.duplicated().any():
        raise ValueError("UBIGEO duplicado en la referencia de 2017")
    return reference


def fit_urban_axis(reference: pd.DataFrame, training_districts: set[str]) -> UrbanAxis:
    """Fit PC1 with the 2017 fractions of the training districts only."""
    columns = tuple(c for c in reference if c.startswith("fraccion_"))
    if len(columns) != 15 or reference.ubigeo.duplicated().any():
        raise ValueError("La referencia requiere 15 fracciones y UBIGEO únicos")
    district = {str(x) for x in training_districts}
    observed = set(reference.ubigeo.astype(str))
    if not district or not district.issubset(observed):
        raise ValueError("Distritos de entrenamiento vacíos o desconocidos")
    fit = reference.loc[reference.ubigeo.astype(str).isin(district), list(columns)].astype(float)
    if len(fit) < 2 or fit.isna().any().any() or not np.isfinite(fit.to_numpy()).all():
        raise ValueError("Datos insuficientes para ajustar el eje urbano")
    media = fit.mean()
    std = fit.std(ddof=1)
    if std.le(0).any():
        raise ValueError("Hay fracciones constantes en el ajuste del eje urbano")
    z = (fit - media) / std
    _, singular, vectors = np.linalg.svd(z.to_numpy(), full_matrices=False)
    loadings = pd.Series(vectors[0], index=columns)
    # EDA convention: more household equipment = positive side.
    if loadings["fraccion_hogares_refrigeradora"] < 0:
        loadings = -loadings
    variance = float(singular[0] ** 2 / np.sum(singular ** 2))
    return UrbanAxis(columns, media, std, loadings, variance, frozenset(district))


def build_sociodemography(
    panel: pd.DataFrame, horizon: int, reference: pd.DataFrame,
    available_date: str | pd.Timestamp, axis: UrbanAxis | None = None,
    *, mask_before_availability: bool = True,
) -> pd.DataFrame:
    """Attach the static 2017 traits and audit availability at the origin.

    By default, rows with an origin before ``available_date`` stay NaN because
    they would not be valid historical forecasts. To use those rows only as
    training examples at a later cutoff, the masking can be turned off. The
    evaluator must check separately that the test origins are after the
    availability. PC1 must come from a fit on the training fold.
    """
    if horizon not in EXPERIMENTAL_HORIZONS:
        raise ValueError("Use horizonte de 1 a 6 semanas")
    available = pd.Timestamp(available_date)
    if pd.isna(available):
        raise ValueError("fecha_disponible inválida")
    if reference.ubigeo.duplicated().any():
        raise ValueError("UBIGEO duplicado en referencia")
    audit = audit_origin(panel, horizon)
    columns = ["ubigeo", "poblacion", *DIRECT]
    if not set(columns).issubset(reference):
        raise ValueError("Faltan columnas censales de 2017")
    ref = reference[columns].copy()
    for column in columns[1:]:
        ref[column] = pd.to_numeric(ref[column], errors="raise")
    ref["poblacion"] = pd.to_numeric(ref["poblacion"], errors="raise")
    if ref[columns[1:]].isna().any().any() or not np.isfinite(ref[columns[1:]].to_numpy(float)).all():
        raise ValueError("Fracciones censales faltantes o no finitas")
    if not ref[list(DIRECT)].ge(0).all().all() or not ref[list(DIRECT)].le(1).all().all():
        raise ValueError("Fracciones censales fuera de rango")
    if ref.poblacion.isna().any() or not np.isfinite(ref.poblacion.to_numpy(float)).all() or (ref.poblacion <= 0).any():
        raise ValueError("Población censal faltante o no positiva")
    ref = ref.rename(columns={"poblacion": "poblacion_censo_2017", **{c: f"{c}_2017" for c in DIRECT}})
    if axis is not None:
        if not set(axis.columns).issubset(reference):
            raise ValueError("Faltan fracciones para transformar el eje urbano")
        scores = ((reference[list(axis.columns)].astype(float) - axis.media) / axis.std) @ axis.loadings
        if scores.isna().any() or not np.isfinite(scores.to_numpy(float)).all():
            raise ValueError("El eje urbano tiene puntajes faltantes o no finitos")
        ref["eje_urbano_2017"] = scores.to_numpy(float)
    output = audit[KEY + ["semana_inicio", "origen_cierre"]].merge(ref, on="ubigeo", how="left", validate="many_to_one", sort=False)
    if len(output) != len(panel):
        raise ValueError("El cruce demográfico cambió el número de filas")
    if output["poblacion_censo_2017"].isna().any():
        raise ValueError("Hay distritos sin correspondencia censal")
    output["log_poblacion_censo_2017"] = np.log(output.pop("poblacion_censo_2017"))
    features = [c for c in output if c.endswith("_2017")]
    if mask_before_availability:
        output.loc[output.origen_cierre.lt(available) | output.origen_cierre.isna(), features] = np.nan
    return output.drop(columns="origen_cierre")


def build_raw_annual_sociodemography(panel: pd.DataFrame) -> pd.DataFrame:
    """Validate and return the yearly population and fractions without fitting PCA."""
    required = set(KEY + ["semana_inicio", *SOCIO_COLUMNS])
    missing = required - set(panel)
    if missing:
        raise ValueError(f"Faltan columnas demográficas anuales: {sorted(missing)}")
    if panel.empty or panel[KEY + ["semana_inicio"]].isna().any().any():
        raise ValueError("El panel anual está vacío o tiene llaves faltantes")
    if panel.duplicated(KEY).any():
        raise ValueError("Hay llaves distrito-año-semana duplicadas")
    keys = ["ubigeo", "anio"]
    data = panel[keys + SOCIO_COLUMNS].copy()
    for column in SOCIO_COLUMNS:
        data[column] = pd.to_numeric(data[column], errors="raise")
    if data[SOCIO_COLUMNS].isna().any().any() or not np.isfinite(data[SOCIO_COLUMNS].to_numpy(float)).all():
        raise ValueError("La demografía anual contiene valores nulos o no finitos")
    fractions = [c for c in SOCIO_COLUMNS if c != "poblacion"]
    if (data.poblacion <= 0).any() or not data[fractions].ge(0).all().all() or not data[fractions].le(1).all().all():
        raise ValueError("La población o las fracciones anuales están fuera de rango")
    dispersion = data.groupby(keys)[SOCIO_COLUMNS].nunique(dropna=False)
    if dispersion.gt(1).any().any():
        raise ValueError("La demografía anual cambia entre semanas de un distrito-año")
    yearly = data.drop_duplicates(keys).copy()
    yearly["log_poblacion_anual"] = np.log(yearly.pop("poblacion"))
    yearly = yearly.rename(columns={c: f"{c}_anual" for c in fractions})
    output = panel[KEY + ["semana_inicio"]].merge(yearly, on=keys, how="left", validate="many_to_one", sort=False)
    if len(output) != len(panel) or output["log_poblacion_anual"].isna().any():
        raise ValueError("El cruce demográfico anual perdió o duplicó filas")
    return output


def build_annual_sociodemography(panel: pd.DataFrame, axis: UrbanAxis) -> pd.DataFrame:
    """Add to the yearly value an axis with the 2017 scale fitted per fold.

    The PCA is fitted outside this function, on the fold's training data. It
    applies the same 2017 scale and loadings to every year; the interpolated
    fractions of 2018-2024 include the 2025 end point of the silver.
    """
    if set(axis.columns) != set(SOCIO_COLUMNS) - {"poblacion"}:
        raise ValueError("El eje urbano no contiene las 15 fracciones esperadas")
    output = build_raw_annual_sociodemography(panel)
    columnas_anuales = [f"{c}_anual" for c in axis.columns]
    mean_scale = axis.media.rename(index=lambda c: f"{c}_anual")
    std_scale = axis.std.rename(index=lambda c: f"{c}_anual")
    loadings = axis.loadings.rename(index=lambda c: f"{c}_anual")
    scores = ((output[columnas_anuales] - mean_scale) / std_scale) @ loadings
    if scores.isna().any() or not np.isfinite(scores.to_numpy(float)).all():
        raise ValueError("El eje urbano anual contiene puntajes no finitos")
    output["eje_urbano_anual"] = scores.to_numpy(float)
    return output
