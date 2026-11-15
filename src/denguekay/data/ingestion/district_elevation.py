"""Archive GLO-90 elevation responses for the existing Piura district points."""

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

import pandas as pd
import requests

from denguekay.config.paths import (
    DISTRICT_COORDS, ROOT, UBIGEO_CATALOG, V4_DATA_MANIFEST, V4_ELEVATION_RAW, V4_GEOGRAPHY, V4_LIVE_GEOGRAPHY,
)
from denguekay.data.ingestion import release_bundles
from denguekay.data.keys import normalize
from denguekay.features.b3 import GEO

ELEVATION_URL = "https://api.open-meteo.com/v1/elevation"


def ensure_frozen_geography(*, offline=False):
    """Extract only the geography member verified against the release manifest."""
    manifest = release_bundles.load_manifest(V4_DATA_MANIFEST)
    archive = next(item for item in manifest["paquetes"] if item["nombre"] == "datos_v4.zip")
    member = V4_GEOGRAPHY.relative_to(ROOT).as_posix()
    expected = next(item["sha256"] for item in archive["archivos"] if item["ruta"] == member)
    if not V4_GEOGRAPHY.exists():
        if offline:
            raise FileNotFoundError("Extract the frozen V4 geography from datos_v4.zip before an offline run")
        V4_GEOGRAPHY.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=V4_GEOGRAPHY.parent) as folder:
            archive_path = Path(folder) / archive["nombre"]
            release_bundles.download(release_bundles.release_url(manifest["repositorio"], manifest["tag"],
                                                               archive["nombre"]), archive_path)
            release_bundles.verify_bundle(archive_path, archive)
            with ZipFile(archive_path) as bundle:
                payload = bundle.read(member)
            if sha256(payload).hexdigest() != expected:
                raise ValueError("V4 geography differs from its release checksum")
            candidate = Path(folder) / V4_GEOGRAPHY.name
            candidate.write_bytes(payload)
            candidate.replace(V4_GEOGRAPHY)
    if release_bundles.sha256_file(V4_GEOGRAPHY) != expected:
        raise ValueError("Local V4 geography differs from its release checksum")
    return V4_GEOGRAPHY


def district_points(coords=DISTRICT_COORDS, catalog=UBIGEO_CATALOG):
    points = pd.read_csv(coords, float_precision="round_trip")
    codes = pd.read_csv(catalog, dtype={"ubigeo": "string"})
    keys = ["provincia", "distrito"]
    for frame in (points, codes):
        frame["provincia"] = frame.provincia.map(normalize)
        frame["distrito"] = (frame.distrito.map(normalize).str.removesuffix("_S").str.replace(" ", "", regex=False))
    joined = codes[keys + ["ubigeo"]].merge(points[keys + ["lat", "lon"]], on=keys, how="left",
                                            validate="one_to_one")
    if joined[["lat", "lon"]].isna().any().any() or not joined.ubigeo.str.fullmatch(r"\d{6}").all():
        raise ValueError("District coordinates do not reconcile to the UBIGEO catalogue")
    return joined[["lat", "lon", "ubigeo"]].sort_values("ubigeo").reset_index(drop=True)


def elevation_reference(*, offline=False, points_path=DISTRICT_COORDS, catalog_path=UBIGEO_CATALOG,
                        folder=V4_ELEVATION_RAW, output=V4_LIVE_GEOGRAPHY):
    points = district_points(points_path, catalog_path)
    params = {"latitude": ",".join(map(str, points.lat)), "longitude": ",".join(map(str, points.lon))}
    point_hash = sha256(points.to_csv(index=False, lineterminator="\n").encode()).hexdigest()
    folder.mkdir(parents=True, exist_ok=True)
    if offline:
        requests_for_points = sorted(folder.glob(f"*_{point_hash}.request.json"))
        if not requests_for_points:
            raise FileNotFoundError("No archived elevation response for these district coordinates")
        note = requests_for_points[-1]
        raw = note.with_name(note.name.removesuffix(".request.json") + ".json")
        metadata = json.loads(note.read_bytes())
        if metadata["sha256_respuesta"] != sha256(raw.read_bytes()).hexdigest():
            raise ValueError("Archived elevation response does not match its recorded SHA-256")
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        stem = f"{stamp}_{point_hash}"
        response = requests.get(ELEVATION_URL, params=params, timeout=60)
        response.raise_for_status()
        raw = folder / f"{stem}.json"
        with raw.open("xb") as stream:
            stream.write(response.content)
        metadata = {"fuente": ELEVATION_URL, "consulta_utc": stamp, "parametros": params,
                    "ubigeos": points.ubigeo.tolist(), "sha256_respuesta": sha256(response.content).hexdigest()}
        (folder / f"{stem}.request.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    samples = json.loads(raw.read_bytes()).get("elevation")
    if (metadata["ubigeos"] != points.ubigeo.tolist() or metadata["parametros"] != params
            or not isinstance(samples, list) or len(samples) != len(points)):
        raise ValueError("Elevation response does not align with the ordered district points")
    values = pd.to_numeric(pd.Series(samples), errors="raise")
    if not values.between(-12000, 9000).all():
        raise ValueError("Missing or invalid GLO-90 elevations")
    points[GEO[-1]] = values.astype(float)
    output.parent.mkdir(parents=True, exist_ok=True)
    points.to_csv(output, index=False, lineterminator="\n")
    return points
