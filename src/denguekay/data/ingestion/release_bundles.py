"""Data bundles of a frozen model version, published as assets of its GitHub Release.

``data/`` is not versioned, so a clone cannot retrain a model by itself. For a frozen version the needed files
are packed in zips (``datos_v3.zip`` with the inputs under ``data/``, ``predicciones_v3.zip`` with the reference
predictions under ``models/experimentos/``) and attached to the Release of its tag. A manifest versioned in the
repository (``models/registry/<version>/manifiesto_datos.json``) lists each zip and each file with its rows and
SHA-256. This module downloads the zips, checks every hash against the manifest and extracts them at the
repository root. It refuses entries outside their declared folder and never overwrites a different file unless
asked to.

Usage (from the repository root)::

    python -m denguekay.data.ingestion.release_bundles            # V3 manifest
    python -m denguekay.data.ingestion.release_bundles --solo predicciones_v3.zip
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

from denguekay.config.paths import ROOT, V3_DATA_MANIFEST

CHUNK = 1 << 20


class BundleError(RuntimeError):
    """A bundle or one of its files does not match the manifest."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def count_rows(path: Path) -> int | None:
    """Data rows of a CSV (plain or .gz; header excluded) or a Parquet file; ``None`` for other files."""
    name = path.name.lower()
    if name.endswith(".parquet"):
        import pyarrow.parquet as pq

        return int(pq.ParquetFile(path).metadata.num_rows)
    if name.endswith(".csv") or name.endswith(".csv.gz"):
        opener = gzip.open if name.endswith(".gz") else open
        with opener(path, "rb") as f:
            lines = sum(1 for _ in f)
        return max(lines - 1, 0)
    return None


def _prefixes(prefix: str | list[str]) -> list[str]:
    return [prefix] if isinstance(prefix, str) else list(prefix)


def _safe_member(name: str, prefix: str | list[str]) -> PurePosixPath:
    """The member's relative path, if it lies inside one of the ``prefix`` folders (no absolute paths, no ``..``)."""
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or ":" in path.parts[0]:
        raise BundleError(f"Ruta no permitida en el paquete: {name}")
    if not any(path.parts[: len(PurePosixPath(p).parts)] == PurePosixPath(p).parts for p in _prefixes(prefix)):
        raise BundleError(f"{name} está fuera de {_prefixes(prefix)}")
    return path


def build_bundle(files: list[Path], zip_path: Path, prefix: str | list[str], root: Path = ROOT) -> dict:
    """Zip ``files`` (paths under ``root/prefix``; ``prefix`` may list several folders) keeping their path relative to ``root``; return the manifest
    entry of the zip (name, bytes, SHA-256, destination folder and every file with its rows and SHA-256)."""
    entries = []
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for path in sorted(files):
            relative = path.resolve().relative_to(root.resolve()).as_posix()
            _safe_member(relative, prefix)
            z.write(path, relative)
            entries.append({"ruta": relative, "filas": count_rows(path), "bytes": path.stat().st_size,
                            "sha256": sha256_file(path)})
    return {"nombre": zip_path.name, "bytes": zip_path.stat().st_size, "sha256": sha256_file(zip_path),
            "destino": prefix, "archivos": entries}


def verify_bundle(zip_path: Path, entry: dict) -> None:
    """The zip has the manifest's SHA-256 and exactly the manifest's files, all inside its destination."""
    actual = sha256_file(zip_path)
    if actual != entry["sha256"]:
        raise BundleError(f"{entry['nombre']}: SHA-256 {actual} distinto del manifiesto ({entry['sha256']})")
    with zipfile.ZipFile(zip_path) as z:
        members = [m for m in z.namelist() if not m.endswith("/")]
    for m in members:
        _safe_member(m, entry["destino"])
    expected = {f["ruta"] for f in entry["archivos"]}
    if set(members) != expected:
        raise BundleError(f"{entry['nombre']}: archivos distintos del manifiesto "
                          f"(sobran {sorted(set(members) - expected)}, faltan {sorted(expected - set(members))})")


def extract_bundle(zip_path: Path, entry: dict, root: Path = ROOT, overwrite: bool = False) -> dict:
    """Verify the zip and extract it under ``root``, checking each extracted file's SHA-256.

    A file already present with the same SHA-256 is left alone; with a different one it is an error unless
    ``overwrite``.
    """
    verify_bundle(zip_path, entry)
    report = {"extraidos": 0, "ya_estaban": 0, "sobrescritos": 0}
    with zipfile.ZipFile(zip_path) as z:
        for f in entry["archivos"]:
            target = root / Path(*PurePosixPath(f["ruta"]).parts)
            if target.exists():
                if sha256_file(target) == f["sha256"]:
                    report["ya_estaban"] += 1
                    continue
                if not overwrite:
                    raise BundleError(f"{f['ruta']} ya existe con otro contenido (usa --sobrescribir)")
                report["sobrescritos"] += 1
            target.parent.mkdir(parents=True, exist_ok=True)
            partial = target.with_name(target.name + ".parcial")
            with z.open(f["ruta"]) as src, open(partial, "wb") as dst:
                shutil.copyfileobj(src, dst, CHUNK)
            if sha256_file(partial) != f["sha256"]:
                partial.unlink()
                raise BundleError(f"{f['ruta']}: SHA-256 distinto del manifiesto al extraer")
            partial.replace(target)
            report["extraidos"] += 1
    return report


def release_url(repository: str, tag: str, name: str) -> str:
    return f"https://github.com/{repository}/releases/download/{tag}/{name}"


def download(url: str, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".parcial")
    with urllib.request.urlopen(url, timeout=120) as response, open(partial, "wb") as f:
        shutil.copyfileobj(response, f, CHUNK)
    partial.replace(destination)
    return destination


def load_manifest(path: Path = V3_DATA_MANIFEST) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def fetch(manifest_path: Path = V3_DATA_MANIFEST, root: Path = ROOT, only: list[str] | None = None,
          overwrite: bool = False, folder: Path | None = None) -> dict:
    """Download the manifest's zips from its Release, verify them and extract them under ``root``.

    ``folder`` keeps the downloaded zips (and reuses a zip already there if its SHA-256 matches); without it they
    go to a temporary folder that is removed afterwards.
    """
    manifest = load_manifest(manifest_path)
    reports = {}
    with tempfile.TemporaryDirectory() as tmp:
        where = Path(folder) if folder is not None else Path(tmp)
        for entry in manifest["paquetes"]:
            if only and entry["nombre"] not in only:
                continue
            zip_path = where / entry["nombre"]
            if not (zip_path.exists() and sha256_file(zip_path) == entry["sha256"]):
                download(release_url(manifest["repositorio"], manifest["tag"], entry["nombre"]), zip_path)
            reports[entry["nombre"]] = extract_bundle(zip_path, entry, root, overwrite)
    return reports


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Descarga y verifica los paquetes de datos de una versión congelada.")
    parser.add_argument("--manifiesto", type=Path, default=V3_DATA_MANIFEST)
    parser.add_argument("--solo", nargs="*", help="nombres de los zips a descargar (por defecto, todos)")
    parser.add_argument("--carpeta", type=Path, help="carpeta donde guardar los zips descargados")
    parser.add_argument("--sobrescribir", action="store_true", help="reemplaza archivos existentes distintos")
    args = parser.parse_args(argv)
    reports = fetch(args.manifiesto, only=args.solo, overwrite=args.sobrescribir, folder=args.carpeta)
    for name, report in reports.items():
        print(f"{name}: verificado; {report}")


if __name__ == "__main__":
    main()
