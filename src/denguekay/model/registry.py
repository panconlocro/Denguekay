"""Model registry: the version cards in ``models/registry/`` and the configurations they point to.

Each version has ``models/registry/<version>/ficha.json`` (machine-readable) and ``ficha.md`` (for
people). The configuration of a frozen version is not copied into its card: it is loaded from the
package (``denguekay.model.frozen_configs``), and the card names the constant it comes from.
"""

import json

from denguekay.config.paths import MODEL_REGISTRY
from denguekay.model import frozen_configs

VERSIONS = ("v0", "v1", "v2")
CURRENT = "v2"  # frozen configuration in force; v0 is the one served today (see its card)
SERVED = "v0"


def card_path(version: str):
    """Path of the machine-readable card of a version."""
    if version not in VERSIONS:
        raise ValueError(f"Versión de modelo desconocida: {version}")
    return MODEL_REGISTRY / version / "ficha.json"


def card(version: str) -> dict:
    """The card of a version, as stored in the registry."""
    return json.loads(card_path(version).read_text(encoding="utf-8"))


def configuration(version: str) -> dict:
    """Frozen configuration of a version, loaded from the package constant its card names.

    V0 has no frozen configuration constant: its variants live in ``configs/config.yaml``
    (``serving.variantes``), so this raises for it.
    """
    source = card(version)["configuracion"]
    if source.get("constante") is None:
        raise ValueError(f"La versión {version} no tiene una configuración congelada en el paquete")
    return getattr(frozen_configs, source["constante"])
