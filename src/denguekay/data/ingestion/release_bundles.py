"""Data bundles of a frozen model version or a closed study, published as assets of the GitHub Release of its tag.

``data/`` is not versioned, so a clone cannot retrain a model by itself. For a frozen version the needed files
are packed in zips (``datos_v3.zip`` with the inputs under ``data/``, ``predicciones_v3.zip`` with the reference
predictions under ``models/experimentos/``) and attached to the Release of its tag. A manifest versioned in the
repository (``models/registry/<version>/manifiesto_datos.json``) lists each zip and each file with its rows and
SHA-256. This module downloads the zips, checks every hash against the manifest and extracts them at the
repository root. It refuses entries outside their declared folder and never overwrites a different file unless
asked to.

Each version has ``models/registry/<version>/manifiesto_datos.json`` and each study that needs files of its own has
``research/<study>/manifiesto_datos.json``; the manifest names its tag, so the zips are downloaded from that tag's
Release. ``--raiz`` extracts into another checkout (e.g. a worktree of a study tag).

Usage (from the repository root)::

    python -m denguekay.data.ingestion.release_bundles                    # v3 (default)
    python -m denguekay.data.ingestion.release_bundles --version v2
    python -m denguekay.data.ingestion.release_bundles --estudio 05_fe_hyperparameters --raiz ../wt-05
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

from denguekay.config.paths import MODEL_REGISTRY, RESEARCH, ROOT, V3_DATA_MANIFEST

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


MANIFEST_NAME = "manifiesto_datos.json"


def manifest_path(version: str | None = None, study: str | None = None) -> Path:
    """Manifest of a model version (``models/registry/<version>/``) or of a study (``research/<study>/``)."""
    if version and study:
        raise ValueError("Indique una versión o un estudio, no ambos")
    if study:
        path = RESEARCH / study / MANIFEST_NAME
    else:
        path = MODEL_REGISTRY / (version or "v3") / MANIFEST_NAME
    if not path.exists():
        raise FileNotFoundError(f"No hay manifiesto de datos en {path.relative_to(ROOT).as_posix()}")
    return path


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
    parser = argparse.ArgumentParser(description="Descarga y verifica los paquetes de datos de una versión o un estudio.")
    parser.add_argument("--version", help="versión del modelo (v0, v1, v2, v3); por defecto v3")
    parser.add_argument("--estudio", help="carpeta del estudio en research/ (p. ej. 05_fe_hyperparameters)")
    parser.add_argument("--manifiesto", type=Path, help="ruta de un manifiesto (en lugar de --version o --estudio)")
    parser.add_argument("--raiz", type=Path, default=ROOT, help="carpeta donde extraer (por defecto, este repo)")
    parser.add_argument("--solo", nargs="*", help="nombres de los zips a descargar (por defecto, todos)")
    parser.add_argument("--carpeta", type=Path, help="carpeta donde guardar los zips descargados")
    parser.add_argument("--sobrescribir", action="store_true", help="reemplaza archivos existentes distintos")
    args = parser.parse_args(argv)
    path = args.manifiesto or manifest_path(args.version, args.estudio)
    reports = fetch(path, root=args.raiz, only=args.solo, overwrite=args.sobrescribir, folder=args.carpeta)
    for name, report in reports.items():
        print(f"{name}: verificado; {report}")


if __name__ == "__main__":
    main()
