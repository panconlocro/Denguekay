"""Archive an observed V4 CHIRPS silver and select an evidenced snapshot at a cutoff."""

import argparse
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile
from zoneinfo import ZoneInfo

import pandas as pd

from denguekay.config.paths import ROOT, V4_CHIRPS, V4_CHIRPS_CUTOFFS, V4_CHIRPS_SNAPSHOTS
from denguekay.data.processing.chirps_precipitation import SILVER_COLUMNS

STAMP = "%Y%m%dT%H%M%S%fZ"
STAMP_NAME = re.compile(r"[0-9]{8}T[0-9]{12}Z")
MANIFEST = "manifest.json"


def _utc(instant):
    if instant.utcoffset() is None:
        raise ValueError("A CHIRPS cutoff requires an explicit UTC offset")
    return instant.astimezone(timezone.utc)


def archive_snapshot(weekly, *, observed_at, folder=V4_CHIRPS_SNAPSHOTS):
    """Keep the exact silver bytes observed at the end of an online capture."""
    observed = _utc(observed_at)
    payload = weekly.to_csv(index=False, lineterminator="\r\n").encode("utf-8")
    metadata = {"observada_utc": observed.isoformat(), "archivo": V4_CHIRPS.name,
                "sha256": sha256(payload).hexdigest()}
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{observed:{STAMP}}.zip"
    target = folder / name
    if target.exists():
        raise FileExistsError(target)
    with TemporaryDirectory(dir=folder) as scratch:
        candidate = Path(scratch) / name
        with ZipFile(candidate, "w", compression=ZIP_DEFLATED) as archive:
            archive.writestr(MANIFEST, json.dumps(metadata, indent=2))
            archive.writestr(V4_CHIRPS.name, payload)
        candidate.replace(target)
    return target


def snapshot_at(cutoff, *, folder=V4_CHIRPS_SNAPSHOTS):
    """Read the last capture observed by the cutoff, with the weekly availability gate applied."""
    instant = _utc(cutoff)
    limit = instant.strftime(STAMP)
    candidates = [path for path in folder.glob("*.zip") if STAMP_NAME.fullmatch(path.stem) and path.stem <= limit]
    if not candidates:
        raise FileNotFoundError(f"No archived CHIRPS capture on or before {instant.isoformat()}")
    selected = max(candidates)
    try:
        with ZipFile(selected) as archive:
            metadata = json.loads(archive.read(MANIFEST))
            payload = archive.read(V4_CHIRPS.name)
    except (BadZipFile, KeyError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid CHIRPS snapshot archive: {selected.name}") from error
    observed = _utc(datetime.fromisoformat(metadata["observada_utc"]))
    if (observed.strftime(STAMP) != selected.stem or metadata["archivo"] != V4_CHIRPS.name
            or sha256(payload).hexdigest() != metadata["sha256"]):
        raise ValueError(f"Invalid CHIRPS snapshot lineage: {selected.name}")
    weekly = pd.read_csv(BytesIO(payload), dtype={"ubigeo": "string"}, float_precision="round_trip")
    if (list(weekly) != SILVER_COLUMNS or weekly.duplicated(["ubigeo", "semana_inicio"]).any()
            or not weekly.ubigeo.str.fullmatch(r"[0-9]{6}", na=False).all()):
        raise ValueError(f"Invalid CHIRPS weekly schema: {selected.name}")
    available = pd.to_datetime(weekly.fecha_disponible, format="%Y-%m-%d", errors="raise")
    day = pd.Timestamp(instant.astimezone(ZoneInfo("America/Lima")).date())
    return weekly.loc[available.le(day)].copy(), {**metadata, "captura": selected.name}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corte", required=True, type=datetime.fromisoformat, help="fecha y hora ISO con desfase UTC")
    args = parser.parse_args(argv)
    try:
        cutoff = _utc(args.corte)
        weekly, lineage = snapshot_at(cutoff, folder=V4_CHIRPS_SNAPSHOTS)
    except (FileNotFoundError, ValueError) as error:
        parser.exit(1, f"{error}\n")
    if weekly.empty:
        parser.exit(1, "La captura seleccionada no contiene semanas disponibles al corte.\n")
    output = V4_CHIRPS_CUTOFFS / f"{cutoff:{STAMP}}.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as scratch:
        candidate = Path(scratch) / output.name
        weekly.to_csv(candidate, index=False, lineterminator="\r\n")
        digest = sha256(candidate.read_bytes()).hexdigest()
        candidate.replace(output)
    print(json.dumps({**lineage, "corte_utc": cutoff.isoformat(), "filas": len(weekly),
                      "ultima_semana": weekly.semana_inicio.max(), "sha256_salida": digest,
                      "salida": output.relative_to(ROOT).as_posix()},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
