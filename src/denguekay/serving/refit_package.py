"""The refit package that ``serving.paquete.opciones.paquete_dir`` names, between the PC and the Storage.

A refit package (``denguekay.model.refit_v4``) is a folder outside Git whose ``paquete.json`` lists, under ``archivos``,
the SHA-256 of every other file in it. The weekly update of GitHub Actions starts on an empty machine, so before its
preflight it downloads that folder from the Storage (``modelos/reajustes/<carpeta>/<archivo>``) and checks every file against
the manifest: a file that was altered or truncated is rejected and nothing is left in the destination folder.

- ``python -m denguekay.serving.refit_package --subir``: copies the folder the configuration names to the Storage
  (after a refit, before or with ``publish``).
- ``python -m denguekay.serving.refit_package --descargar``: downloads it when it is configured and not on the machine
  (what the workflow runs; it does nothing when the frozen package of the Release is served).
"""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory

from denguekay.config.paths import ROOT

PREFIX = "modelos/reajustes"   # the bucket ``modelos``; the packages of M2 live at ``modelos/<codigo>/``
MANIFEST = "paquete.json"


class RefitPackageError(ValueError):
    """The package in the Storage is incomplete or does not match its manifest."""


def storage_path(folder, name):
    return f"{PREFIX}/{Path(folder).name}/{name}"


def sha256_bytes(content):
    return hashlib.sha256(content).hexdigest()


def upload(storage, folder):
    """Copy every file of the refit folder (and its manifest) to the Storage and return the logical paths."""
    folder = Path(folder)
    config = json.loads((folder / MANIFEST).read_text(encoding="utf-8"))
    names = [*config["archivos"], MANIFEST]
    missing = [name for name in names if not (folder / name).is_file()]
    if missing:
        raise RefitPackageError(f"Faltan archivos del paquete en {folder}: {', '.join(missing)}")
    contents = {name: (folder / name).read_bytes() for name in names}
    for name, digest in config["archivos"].items():   # everything is checked before anything goes up
        if sha256_bytes(contents[name]) != digest:
            raise RefitPackageError(f"{name} no coincide con el SHA-256 de su paquete; no se sube")
    for name in [*config["archivos"], MANIFEST]:   # the manifest goes last: its presence marks a complete package
        storage.save(storage_path(folder, name), contents[name])
    return [storage_path(folder, name) for name in names]


def download(storage, destination):
    """Download the package into ``destination`` (a folder that must not hold a ``paquete.json`` yet).

    Every file is checked against the ``archivos`` of the manifest before anything is written to ``destination``;
    a mismatch raises ``RefitPackageError``. Returns the names written."""
    destination = Path(destination)
    try:
        manifest = storage.read(storage_path(destination, MANIFEST))
    except FileNotFoundError as error:
        raise FileNotFoundError(f"El paquete reajustado {destination.name} no está en el Storage "
                                f"({storage_path(destination, MANIFEST)}); súbalo con "
                                "python -m denguekay.serving.refit_package --subir") from error
    expected = json.loads(manifest.decode("utf-8"))["archivos"]
    with TemporaryDirectory(prefix="denguekay-reajuste-") as scratch:
        staged = Path(scratch)
        for name, digest in expected.items():
            try:
                content = storage.read(storage_path(destination, name), digest)
            except FileNotFoundError as error:
                raise RefitPackageError(f"Falta {name} del paquete reajustado en el Storage") from error
            except ValueError as error:   # a name of the manifest that is not a valid Storage path
                raise RefitPackageError(f"Nombre inválido en el manifiesto del paquete reajustado: {name}") from error
            if sha256_bytes(content) != digest:
                raise RefitPackageError(f"{name} del Storage no coincide con el SHA-256 de su manifiesto: se rechaza")
            (staged / name).write_bytes(content)
        (staged / MANIFEST).write_bytes(manifest)
        destination.mkdir(parents=True, exist_ok=True)
        for item in staged.iterdir():   # the manifest goes last: its presence marks a complete package
            if item.name != MANIFEST:
                shutil.copyfile(item, destination / item.name)
        shutil.copyfile(staged / MANIFEST, destination / MANIFEST)
    return [*expected, MANIFEST]


def ensure(storage, options, *, root=ROOT):
    """Make the folder of ``paquete_dir`` exist on this machine. It returns what it did, for the report.

    Nothing to do without ``paquete_dir`` or when the folder is already there. A package that is not in the Storage is
    not an error here: the preflight then says, as before, that the folder is missing."""
    relative = options.get("paquete_dir")
    if not relative:
        return {"estado": "no_aplica"}
    folder = Path(root) / relative
    if (folder / MANIFEST).is_file():
        return {"estado": "ya_estaba", "carpeta": relative}
    try:
        names = download(storage, folder)
    except FileNotFoundError as error:
        return {"estado": "no_esta_en_el_storage", "carpeta": relative, "detalle": str(error)}
    return {"estado": "descargado", "carpeta": relative, "archivos": names}


def main(argv=None):
    from denguekay.serving.settings import service_settings
    from denguekay.serving.storage import storage_from_environment

    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--subir", action="store_true", help="Copia la carpeta configurada al Storage")
    action.add_argument("--descargar", action="store_true", help="Trae la carpeta configurada si falta en esta máquina")
    args = parser.parse_args(argv)
    cfg = service_settings()
    options = cfg.opciones
    if not options.get("paquete_dir"):
        print(json.dumps({"estado": "no_aplica", "nota": "config.yaml sirve el paquete congelado del Release"}))
        return 0
    storage = storage_from_environment(cfg.almacenamiento)
    try:
        if args.subir:
            result = {"estado": "subido", "archivos": upload(storage, ROOT / options["paquete_dir"])}
        else:
            result = ensure(storage, options, root=ROOT)
    except (RefitPackageError, OSError) as error:
        print(f"Paquete reajustado rechazado: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    finally:
        close = getattr(storage, "close", None)
        if close:
            close()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["estado"] == "no_esta_en_el_storage" else 0


if __name__ == "__main__":
    sys.exit(main())
