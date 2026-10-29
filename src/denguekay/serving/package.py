"""Model package (decision M2): ``modelos/<codigo>/manifest.json`` and its files in Storage.

The manifest names the predictor type that runs the package, its horizons, variables and interval
level, and the SHA-256 of every file. ``version_modelo.ruta_artefacto`` points to the manifest and
``sha256_artefacto`` is the manifest's hash; loading a package checks the manifest and every file
against those hashes (409 ``artefacto_invalido``).
"""

from dataclasses import dataclass
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json

from denguekay.serving.artifacts import InvalidArtifact, sha256_bytes

MANIFEST_VERSION = 1
MANIFEST_NAME = "manifest.json"
BUCKET = "modelos"


def denguekay_version():
    try:
        return version("denguekay")
    except PackageNotFoundError:  # running from a checkout without ``pip install -e .``
        return "0.0.0"


def _version_tuple(text):
    return tuple(int(part) for part in str(text).split(".")[:3])


def package_code(prefix, files):
    """Content-addressed code: the same files always give the same package."""
    digest = hashlib.sha256()
    for name in sorted(files):
        digest.update(name.encode("utf-8") + b"\0" + hashlib.sha256(files[name]).digest())
    return f"{prefix}-{digest.hexdigest()[:12]}"


def file_path(code, name):
    return f"{BUCKET}/{code}/{name}"


def build_manifest(built, thresholds):
    """Manifest of a ``BuiltPackage``; ``thresholds`` = {(horizon, task): cumple_umbrales}."""
    return {
        "version_manifiesto": MANIFEST_VERSION,
        "codigo_paquete": built.code,
        "tipo_predictor": built.kind,
        "version_minima_denguekay": denguekay_version(),
        "horizontes": list(built.horizons),
        "nivel_intervalo": built.interval_level,
        "variables": built.variables,
        "opciones": built.options,
        "archivos": {name: {"ruta": file_path(built.code, name), "sha256": sha256_bytes(content)}
                     for name, content in sorted(built.files.items())},
        "metricas": {f"{spec.horizonte}_{spec.tarea}": spec.data["metricas"] for spec in built.versions},
        "cumple_umbrales": {f"{h}_{task}": bool(value) for (h, task), value in sorted(thresholds.items())},
        "huella": built.fingerprint,
    }


def manifest_bytes(manifest):
    return (json.dumps(manifest, sort_keys=True, indent=1, ensure_ascii=False, allow_nan=False, default=str)
            + "\n").encode("utf-8")


def save_package(storage, built, thresholds):
    """Write the files and the manifest; never overwrite different content. Returns (path, sha256)."""
    manifest = build_manifest(built, thresholds)
    for name, content in built.files.items():
        path = file_path(built.code, name)
        if storage.exists(path):
            if sha256_bytes(storage.read(path)) != sha256_bytes(content):
                raise InvalidArtifact(f"La ruta {path} ya guarda otro contenido; el paquete no se sobrescribe")
        else:
            storage.save(path, content)
    content = manifest_bytes(manifest)
    sha = sha256_bytes(content)
    path = file_path(built.code, MANIFEST_NAME)
    # Another database (other acceptance thresholds) may have written a different manifest for the same files.
    if storage.exists(path) and sha256_bytes(storage.read(path)) != sha:
        path = file_path(built.code, f"manifest-{sha[:12]}.json")
    if not storage.exists(path):
        storage.save(path, content)
    return path, sha


@dataclass(frozen=True)
class Package:
    path: str
    sha256: str
    manifest: dict
    files: dict

    @property
    def kind(self):
        return self.manifest["tipo_predictor"]

    @property
    def code(self):
        return self.manifest["codigo_paquete"]

    @property
    def horizons(self):
        return tuple(self.manifest["horizontes"])

    @property
    def interval_level(self):
        return self.manifest.get("nivel_intervalo")


def _read(storage, path, what):
    try:
        return storage.read(path)
    except (FileNotFoundError, ValueError) as error:
        raise InvalidArtifact(f"No se encontró el artefacto {what} ({path})") from error


def load_package(storage, path, sha256):
    """Read the manifest and every file, checking each SHA-256 on every load."""
    content = _read(storage, path, "del paquete")
    if sha256_bytes(content) != sha256:
        raise InvalidArtifact(f"El manifiesto {path} no coincide con su SHA-256 registrado")
    try:
        manifest = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InvalidArtifact(f"El manifiesto {path} no es JSON válido") from error
    if manifest.get("version_manifiesto") != MANIFEST_VERSION:
        raise InvalidArtifact(f"Versión de manifiesto no soportada en {path}")
    if _version_tuple(manifest.get("version_minima_denguekay", "0")) > _version_tuple(denguekay_version()):
        raise InvalidArtifact(f"El paquete {path} exige denguekay >= {manifest['version_minima_denguekay']}")
    files = {}
    for name, entry in manifest.get("archivos", {}).items():
        data = _read(storage, entry["ruta"], f"{name} del paquete")
        if sha256_bytes(data) != entry["sha256"]:
            raise InvalidArtifact(f"El archivo {name} del paquete {manifest.get('codigo_paquete')} "
                                  "no coincide con su SHA-256 registrado")
        files[name] = data
    return Package(path, sha256, manifest, files)
