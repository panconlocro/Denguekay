"""Reconcile stable weather-cache IDs with the Piura UBIGEO catalogue."""

import pandas as pd

from denguekay.config.paths import DISTRICT_COORDS, UBIGEO_CATALOG
from denguekay.data.keys import normalize


def _district_key(values):
    return values.map(normalize).str.removesuffix("_S").str.replace(" ", "", regex=False)


def district_locations(coords=DISTRICT_COORDS, catalog=UBIGEO_CATALOG):
    """Return one location and weather ID per district using the versioned lookups."""
    points = pd.read_csv(coords, float_precision="round_trip")
    codes = pd.read_csv(catalog, dtype={"ubigeo": "string"})
    keys = ["provincia", "distrito"]
    for frame in (points, codes):
        frame["provincia"] = frame.provincia.map(normalize)
        frame["distrito"] = _district_key(frame.distrito)
    joined = codes.merge(points[keys + ["lat", "lon", "id_distrito"]], on=keys, how="left", validate="one_to_one")
    if (joined[["lat", "lon", "id_distrito"]].isna().any().any()
            or joined.id_distrito.duplicated().any() or joined.ubigeo.duplicated().any()
            or not joined.ubigeo.str.fullmatch(r"\d{6}").all()):
        raise ValueError("District coordinates do not reconcile to the UBIGEO catalogue")
    return joined.sort_values("ubigeo").reset_index(drop=True)


def district_points(coords=DISTRICT_COORDS, catalog=UBIGEO_CATALOG):
    """Return the ordered points used for the GLO-90 elevation request."""
    return district_locations(coords, catalog)[["lat", "lon", "ubigeo"]]


def read_v4_era5(path):
    """Read archived or rebuilt weekly ERA5-Land and resolve UBIGEO without comparing floats."""
    era = pd.read_csv(path, parse_dates=["semana_inicio"], float_precision="round_trip")
    ids = district_locations().rename(columns={"provincia": "expected_prov", "distrito": "expected_dist"})
    out = era.merge(ids[["id_distrito", "ubigeo", "expected_prov", "expected_dist"]],
                    on="id_distrito", how="left", validate="many_to_one")
    if (out.empty or out.ubigeo.isna().any() or not out.provincia.map(normalize).eq(out.expected_prov).all()
            or not _district_key(out.distrito).eq(out.expected_dist).all()
            or out.duplicated(["ubigeo", "semana_inicio"]).any()):
        raise ValueError("ERA5-Land district IDs or names do not match the versioned catalogue")
    if "fecha_disponible" in out:
        out["fecha_disponible"] = pd.to_datetime(out.fecha_disponible, errors="raise")
    else:
        out["fecha_disponible"] = out.semana_inicio + pd.Timedelta(days=13)
    return out.drop(columns=["expected_prov", "expected_dist"])
