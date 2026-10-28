"""On-disk cache of the expensive computations of a modelling notebook.

Notebook 31 retrains hundreds of models on every run. The cache keeps the
results (predictions and evaluations) together with a **fingerprint** of
everything that determines them and reuses them only if the fingerprint matches.
The fingerprint covers:

- the input data (integrated silver, epidemiological history, gold h=2 and
  h=4 and its manifest);
- the configuration (``configs/config.yaml``);
- the code of the denguekay package (``src/denguekay/**/*.py``).

Any change in those files invalidates the cache by itself. ``force=True``
always recomputes. Project policy: the **closing** run of each stage starts from
scratch (forced); the cache is only for iterating on tables and documents. The
files live in ``models/experimentos/`` (not versioned) and never in ``data/``.
"""

import hashlib
import json
import os
import pickle
import tempfile
from pathlib import Path

from denguekay.config.paths import (
    CONFIG, ARCHITECTURE_EXPERIMENTS, GOLD, GOLD_MANIFEST, ROOT, SILVER_EPI_HISTORICAL, SILVER_INTEGRATED,
)

CACHE_DIR = ARCHITECTURE_EXPERIMENTS / "cache"
FORCE_VARIABLE = "DENGUEKAY_FORZAR_REENTRENO"


def files_fingerprint(files: list[Path]) -> str:
    """SHA-256 of the content and relative path of a list of files (stable order)."""
    total = hashlib.sha256()
    for path in sorted(Path(a) for a in files):
        if not path.exists():
            raise FileNotFoundError(f"No existe un insumo de la caché: {path}")
        try:
            name = path.resolve().relative_to(ROOT.resolve()).as_posix()
        except ValueError:
            name = path.name
        total.update(name.encode("utf-8"))
        total.update(hashlib.sha256(path.read_bytes()).digest())
    return total.hexdigest()


def study_inputs() -> list[Path]:
    """Data, configuration and code that determine the results of the study."""
    data = [SILVER_INTEGRATED, SILVER_EPI_HISTORICAL, GOLD_MANIFEST,
             *sorted(GOLD.glob(f"{SILVER_INTEGRATED.stem}_h*_gold.csv"))]
    code = sorted((ROOT / "src" / "denguekay").rglob("*.py"))
    return [*data, CONFIG, *code]


def study_fingerprint() -> str:
    """Fingerprint of every input of the multi-horizon architecture study."""
    return files_fingerprint(study_inputs())


def force_from_env() -> bool:
    """``True`` if the ``DENGUEKAY_FORZAR_REENTRENO`` variable is 1 (closing run)."""
    return os.environ.get(FORCE_VARIABLE, "0").strip() == "1"


def load_or_compute(name: str, compute, *, fingerprint: str, directory: Path = CACHE_DIR,
                      force: bool = False):
    """Return the saved result if its fingerprint matches; otherwise compute and save it.

    ``compute`` is a function without arguments. The result is saved with
    ``pickle`` plus a metadata JSON (fingerprint and name); the write is atomic so
    an interrupted run never leaves a half-written cache.
    """
    directory = Path(directory)
    data, meta = directory / f"{name}.pkl", directory / f"{name}.json"
    if not force and data.exists() and meta.exists():
        saved = json.loads(meta.read_text(encoding="utf-8"))
        if saved.get("huella") == fingerprint:
            with data.open("rb") as file:
                print(f"caché: '{name}' reutilizada (huella {fingerprint[:12]})")
                return pickle.load(file)
    result = compute()
    directory.mkdir(parents=True, exist_ok=True)
    for destination, content in ((data, pickle.dumps(result, protocol=pickle.HIGHEST_PROTOCOL)),
                               (meta, json.dumps({"nombre": name, "huella": fingerprint}).encode("utf-8"))):
        with tempfile.NamedTemporaryFile(dir=directory, delete=False, suffix=".tmp") as tmp:
            tmp.write(content)
        os.replace(tmp.name, destination)
    print(f"caché: '{name}' {'recalculada (forzada)' if force else 'calculada'} (huella {fingerprint[:12]})")
    return result
