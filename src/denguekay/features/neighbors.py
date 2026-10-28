"""Spatial and hierarchical context available at the forecast origin."""

import numpy as np
import pandas as pd

from denguekay.features.spatial import distances_km, inverse_distance_weights, knn_weights
from denguekay.data.validation.forecast_contract import KEY, EXPERIMENTAL_HORIZONS, audit_origin


def geographic_catalog(panel: pd.DataFrame) -> pd.DataFrame:
    """Extract a single, stable geography per UBIGEO from the integrated panel."""
    required = {"ubigeo", "provincia", "lat", "lon"}
    missing = required - set(panel)
    if missing:
        raise ValueError(f"Faltan columnas geográficas: {sorted(missing)}")
    geo = panel[list(required)].copy()
    if geo.isna().any().any():
        raise ValueError("Hay identificadores, provincias o coordenadas faltantes")
    geo["ubigeo"] = geo["ubigeo"].astype("string")
    if not geo.ubigeo.str.fullmatch(r"\d{6}").all():
        raise ValueError("UBIGEO debe tener seis dígitos")
    geo["lat"] = pd.to_numeric(geo["lat"], errors="raise")
    geo["lon"] = pd.to_numeric(geo["lon"], errors="raise")
    if (not np.isfinite(geo[["lat", "lon"]].to_numpy()).all()
            or not geo.lat.between(-90, 90).all()
            or not geo.lon.between(-180, 180).all()):
        raise ValueError("Coordenadas no finitas o fuera de rango")
    if (geo.groupby("ubigeo")[["provincia", "lat", "lon"]].nunique() > 1).any().any():
        raise ValueError("Un UBIGEO tiene geografía inconsistente entre semanas")
    geo = geo.drop_duplicates("ubigeo").sort_values("ubigeo").reset_index(drop=True)
    if geo.duplicated(["lat", "lon"]).any():
        raise ValueError("Hay centroides idénticos; los pesos por distancia serían ambiguos")
    if geo.groupby("provincia").size().lt(2).any():
        raise ValueError("Cada provincia necesita otro distrito para agregados sin sí mismo")
    return geo[["ubigeo", "provincia", "lat", "lon"]]


def neighborhood_matrix(
    catalog: pd.DataFrame, k: int = 5, method: str = "knn",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return weights without diagonal and distances, both indexed by UBIGEO.

    ``knn`` reuses the EDA's uniform k neighbours. ``knn_inversa`` uses those
    same k neighbours with inverse-distance weights. ``inversa`` uses every
    other district with inverse weights; then ``k`` is ignored.
    """
    geo = catalog.sort_values("ubigeo").reset_index(drop=True)
    if geo.empty or geo.ubigeo.duplicated().any():
        raise ValueError("El catálogo está vacío o duplica UBIGEO")
    if method not in ("knn", "knn_inversa", "inversa"):
        raise ValueError("Método de vecindad desconocido")
    if method in ("knn", "knn_inversa") and (not isinstance(k, int) or not 1 <= k < len(geo)):
        raise ValueError("k debe estar entre 1 y el número de distritos menos 1")
    dist = distances_km(geo.lat.to_numpy(), geo.lon.to_numpy())
    if (dist[np.triu_indices(len(geo), 1)] <= 0).any():
        raise ValueError("Hay centroides coincidentes")
    if method == "knn":
        weights = knn_weights(dist, k)
    elif method == "knn_inversa":
        mask = knn_weights(dist, k) > 0
        weights = inverse_distance_weights(dist) * mask
        weights = weights / weights.sum(axis=1, keepdims=True)
    else:
        weights = inverse_distance_weights(dist)
    if not np.isfinite(weights).all() or not np.allclose(weights.sum(axis=1), 1):
        raise ValueError("Pesos espaciales no finitos o sin normalizar")
    if not np.allclose(np.diag(weights), 0):
        raise ValueError("La matriz espacial incluye al distrito objetivo")
    ids = pd.Index(geo.ubigeo, name="ubigeo")
    return (pd.DataFrame(weights, index=ids, columns=ids),
            pd.DataFrame(dist, index=ids, columns=ids))


def build_neighbors_hierarchy(
    panel: pd.DataFrame, horizon: int, k: int = 5, method: str = "knn",
) -> pd.DataFrame:
    """Compute neighbours, province and region using only the cases of ``t-h``.

    Each output keeps one row per district and target week; its origin dates
    allow auditing availability. The provincial and regional aggregates exclude
    the district itself. ``frac_con_casos`` means strictly positive cases,
    without adopting the EDA's D1 outbreak definition. A complete panel is
    required on every date to avoid spatial averages silently computed with
    missing districts.
    """
    if horizon not in EXPERIMENTAL_HORIZONS:
        raise ValueError("El horizonte debe estar entre 1 y 6 semanas")
    if "casos_Dengue" not in panel:
        raise ValueError("Falta casos_Dengue")
    audit = audit_origin(panel, horizon)
    geo = geographic_catalog(panel)
    weights, _ = neighborhood_matrix(geo, k=k, method=method)
    source = audit.merge(panel[KEY + ["casos_Dengue"]], on=KEY,
                         how="left", validate="one_to_one", sort=False)
    if len(source) != len(panel):
        raise ValueError("El cruce con casos cambió el número de filas")
    cases = pd.to_numeric(source.casos_Dengue, errors="raise")
    if cases.isna().any() or not np.isfinite(cases.to_numpy(dtype=float)).all() or (cases < 0).any():
        raise ValueError("casos_Dengue debe ser numérico, finito y no negativo")

    ids = weights.index
    width = source.assign(casos_Dengue=cases).pivot(
        index="semana_inicio", columns="ubigeo", values="casos_Dengue"
    ).reindex(columns=ids)
    if width.isna().any().any() or len(width) * len(ids) != len(panel):
        raise ValueError("Faltan distrito-semanas para construir el contexto espacial")
    y = width.to_numpy(dtype=float)
    active = (y > 0).astype(float)
    provinces = geo.set_index("ubigeo").loc[ids, "provincia"].to_numpy()
    same_province = (provinces[:, None] == provinces[None, :]).astype(float)
    np.fill_diagonal(same_province, 0)
    rest_of_region = np.ones_like(same_province) - np.eye(len(ids))
    province_count = same_province.sum(axis=1)

    label = (f"knn{k}" if method == "knn" else
                f"knn{k}_inversa" if method == "knn_inversa" else "inversa")
    values = {
        f"vecinos_media_casos_{label}_h{horizon}": y @ weights.to_numpy().T,
        f"vecinos_frac_con_casos_{label}_h{horizon}": active @ weights.to_numpy().T,
        f"provincia_otros_casos_h{horizon}": y @ same_province.T,
        f"provincia_otros_frac_con_casos_h{horizon}":
            (active @ same_province.T) / province_count[None, :],
        f"region_otros_casos_h{horizon}": y @ rest_of_region.T,
        f"region_otros_frac_con_casos_h{horizon}":
            (active @ rest_of_region.T) / (len(ids) - 1),
    }
    output = audit.copy()
    rows = width.index.get_indexer(audit.semana_inicio)
    columns = ids.get_indexer(audit.ubigeo.astype("string"))
    if (rows < 0).any() or (columns < 0).any():
        raise ValueError("Un distrito o una semana no se pudo alinear")
    for name, matrix in values.items():
        # Target row t takes the aggregate that existed at t-h.
        lagged = pd.DataFrame(matrix, index=width.index, columns=ids).shift(horizon).to_numpy()
        output[name] = lagged[rows, columns]
    return output
