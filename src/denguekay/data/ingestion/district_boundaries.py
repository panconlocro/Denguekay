"""
District boundaries of Piura from the Peru COD-AB published on HDX (study 06, step b-I).

Source: "Peru - Subnational Administrative Boundaries" (https://data.humdata.org/dataset/cod-ab-per),
produced by the Instituto Geografico Nacional (IGN) and published by OCHA on HDX under CC BY-IGO 3.0
(http://creativecommons.org/licenses/by/3.0/igo/legalcode). The downloaded archive is kept in bronze as is,
with a manifest; the Piura districts (ubigeo as a 6-digit string) go to data/reference/ as GeoJSON, which is
versioned with its attribution. These polygons feed the area-weighted rainfall mean of CHIRPS v3.

GADM (gadm_districts.py) is not used here: its licence forbids redistribution and it lacks a district.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from denguekay.config.paths import BRONZE_BOUNDARIES, DISTRICT_BOUNDARIES

HDX_DATASET = "cod-ab-per"
HDX_PACKAGE_URL = f"https://data.humdata.org/api/3/action/package_show?id={HDX_DATASET}"
RESOURCE_NAME = "per_admin_boundaries.geojson.zip"
EXPECTED_LICENSE = "cc-by-igo"
ATTRIBUTION = ("Límites distritales: Instituto Geográfico Nacional (IGN), publicados por OCHA en HDX "
               "(COD-AB de Perú, https://data.humdata.org/dataset/cod-ab-per), licencia CC BY-IGO 3.0.")
USER_AGENT = "Denguekay-UPC-tesis/0.1 (+https://github.com/panconlocro/Denguekay)"
ADM3_LAYER = "per_admin3.geojson"
PIURA_ADM1_PCODE = "PE20"
EXPECTED_DISTRICTS = 65
# Equal-area projection to recompute the surfaces (South America Albers Equal Area Conic)
EQUAL_AREA_CRS = "ESRI:102033"
REFERENCE_COLUMNS = ["ubigeo", "provincia", "distrito", "adm3_pcode", "geometry"]


def resource_info(package: dict) -> dict:
    """Pick the GeoJSON resource of the HDX package and check the licence (stops if it changed)."""
    if package.get("license_id") != EXPECTED_LICENSE:
        raise RuntimeError(f"La licencia del COD-AB cambió: {package.get('license_id')!r} "
                           f"(se esperaba {EXPECTED_LICENSE!r}). Revisar antes de usarlo.")
    matches = [r for r in package.get("resources", []) if r.get("name") == RESOURCE_NAME]
    if len(matches) != 1:
        raise RuntimeError(f"No se encontró un único recurso {RESOURCE_NAME} en {HDX_DATASET}.")
    res = matches[0]
    return {
        "dataset": HDX_DATASET,
        "recurso": RESOURCE_NAME,
        "url": res["url"],
        "recurso_modificado": res.get("last_modified"),
        "licencia_id": package.get("license_id"),
        "licencia": package.get("license_title"),
        "licencia_url": package.get("license_url"),
        "fuente": package.get("dataset_source"),
        "fechas_dataset": package.get("dataset_date"),
    }


def download(folder: Path = BRONZE_BOUNDARIES) -> tuple[Path, Path]:
    """Download the COD-AB GeoJSON archive as is (never overwrites) and write its manifest next to it."""
    import requests

    headers = {"User-Agent": USER_AGENT}
    r = requests.get(HDX_PACKAGE_URL, headers=headers, timeout=60)
    r.raise_for_status()
    info = resource_info(r.json()["result"])
    path = folder / RESOURCE_NAME
    if path.exists():
        raise FileExistsError(f"Ya existe {path}: bronze no se sobrescribe.")
    resp = requests.get(info["url"], headers=headers, timeout=300)
    check_archive_response(resp.status_code, resp.headers, resp.content)
    return _save(resp.content, info, folder, {"origen": "descarga directa", "user_agent": USER_AGENT})


def check_archive_response(status: int, headers, content: bytes) -> None:
    """Refuse anything that is not the zip itself. HDX sits behind an AWS WAF that answers automated clients
    with HTTP 202, an empty body and ``x-amzn-waf-action: challenge``; that challenge is not bypassed."""
    if headers.get("x-amzn-waf-action"):
        raise RuntimeError("HDX respondió con un desafío anti-bots (AWS WAF); no se elude. Bajar el archivo a "
                           "mano en el navegador y registrarlo con register_local_copy().")
    if status != 200 or not content.startswith(b"PK"):
        raise RuntimeError(f"Respuesta inesperada de HDX: HTTP {status}, {len(content)} bytes, no es un zip.")


def register_local_copy(source: Path, info: dict, folder: Path = BRONZE_BOUNDARIES,
                        downloaded_by: str = "Rosa, a mano en el navegador") -> tuple[Path, Path]:
    """Copy into bronze, byte for byte, the archive downloaded by hand from HDX, with the same manifest."""
    content = Path(source).read_bytes()
    if Path(source).name != RESOURCE_NAME or not content.startswith(b"PK"):
        raise RuntimeError(f"{source} no es {RESOURCE_NAME} (zip).")
    return _save(content, info, folder, {"origen": "descarga manual", "descargado_por": downloaded_by})


def _save(content: bytes, info: dict, folder: Path, extra: dict) -> tuple[Path, Path]:
    path = folder / RESOURCE_NAME
    manifest_path = folder / "manifiesto.json"
    for p in (path, manifest_path):
        if p.exists():
            raise FileExistsError(f"Ya existe {p}: bronze no se sobrescribe.")
    folder.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(content)
    os.replace(tmp, path)
    manifest = {
        **info,
        **extra,
        "archivo": path.name,
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "registrado_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "atribucion": ATTRIBUTION,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return path, manifest_path


def pcode_to_ubigeo(pcode: pd.Series) -> pd.Series:
    """COD-AB ADM3 pcode ("PE" + the 6-digit INEI ubigeo) -> ubigeo as a 6-digit string. Stops on anything else."""
    pcode = pcode.astype(str)
    ok = pcode.str.fullmatch(r"PE\d{6}")
    if not ok.all():
        raise ValueError(f"pcode con formato inesperado: {sorted(pcode[~ok])}")
    return pcode.str[2:]


def read_piura_districts(archive: Path = BRONZE_BOUNDARIES / RESOURCE_NAME):
    """Level-3 polygons of the Piura department from the bronze archive, with ubigeo (string) from the pcode."""
    import geopandas as gpd

    gdf = gpd.read_file(f"zip://{Path(archive).as_posix()}!{ADM3_LAYER}")
    piura = gdf[gdf["adm1_pcode"] == PIURA_ADM1_PCODE].copy()
    piura["ubigeo"] = pcode_to_ubigeo(piura["adm3_pcode"])
    return piura.sort_values("ubigeo").reset_index(drop=True)


def compact_key(name) -> str:
    """Name key that ignores accents, case, spaces and the catalogue's "_s" suffix (Salitral of Sullana), so that
    "El Carmendela Frontera" (centroid file) matches "El Carmen de la Frontera"."""
    from denguekay.data.keys import normalize

    key = normalize(name).replace(" ", "")
    return key[:-2] if key.endswith("_S") else key


def verify_districts(piura, catalog: pd.DataFrame, coords: pd.DataFrame | None = None) -> pd.DataFrame:
    """Check the polygons against the ubigeo catalogue and return one row per district for the report.

    Stops (ValueError) if the count is not 65, an ubigeo is missing, extra or repeated, or a geometry is empty or
    invalid. The surfaces are recomputed in an equal-area projection and set next to the COD-AB area_sqkm;
    with ``coords`` (the V2 centroids), it also reports whether each centroid falls inside its polygon.
    """
    catalog = catalog.astype({"ubigeo": str})
    problems = []
    if len(piura) != EXPECTED_DISTRICTS:
        problems.append(f"{len(piura)} polígonos (se esperaban {EXPECTED_DISTRICTS})")
    if piura["ubigeo"].duplicated().any():
        problems.append(f"ubigeo repetidos: {sorted(piura.loc[piura['ubigeo'].duplicated(), 'ubigeo'])}")
    missing = sorted(set(catalog["ubigeo"]) - set(piura["ubigeo"]))
    extra = sorted(set(piura["ubigeo"]) - set(catalog["ubigeo"]))
    if missing or extra:
        problems.append(f"faltan {missing}; sobran {extra}")
    bad = piura.geometry.is_empty | ~piura.geometry.is_valid
    if bad.any():
        problems.append(f"geometrías vacías o inválidas: {sorted(piura.loc[bad, 'ubigeo'])}")
    if problems:
        raise ValueError("; ".join(problems))

    report = piura.merge(catalog, on="ubigeo", how="left")
    report["nombre_coincide"] = report["adm3_name"].map(compact_key) == report["distrito"].map(compact_key)
    report["area_km2"] = report.to_crs(EQUAL_AREA_CRS).geometry.area / 1e6
    report["area_dif_pct"] = 100 * (report["area_km2"] / report["area_sqkm"] - 1)
    if coords is not None:
        import geopandas as gpd

        keys = ["prov_key", "dist_key"]
        keyed = (coords.assign(prov_key=coords["provincia"].map(compact_key), dist_key=coords["distrito"].map(compact_key))
                 .merge(catalog.assign(prov_key=catalog["provincia"].map(compact_key),
                                       dist_key=catalog["distrito"].map(compact_key))[keys + ["ubigeo"]],
                        on=keys, how="inner"))
        points = gpd.GeoSeries(gpd.points_from_xy(keyed["lon"], keyed["lat"]), crs="EPSG:4326",
                               index=keyed["ubigeo"].values)
        poly = report.set_index("ubigeo").geometry
        report["centroide_v2_dentro"] = report["ubigeo"].map(
            lambda u: bool(poly[u].contains(points[u])) if u in points.index else None)
    return report


def write_reference(piura, path: Path = DISTRICT_BOUNDARIES) -> Path:
    """Write the Piura polygons (EPSG:4326, ubigeo as string) as GeoJSON in data/reference/. Never overwrites."""
    if path.exists():
        raise FileExistsError(f"Ya existe {path}: no se sobrescribe.")
    out = piura[REFERENCE_COLUMNS].copy()
    out["ubigeo"] = out["ubigeo"].astype(str)
    tmp = path.with_suffix(".tmp")
    out.to_file(tmp, driver="GeoJSON")
    os.replace(tmp, path)
    return path
