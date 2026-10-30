"""Service options: config.yaml gives the defaults and the environment replaces them.

``serving.paquete`` names the predictor type that publication builds (``tipo``), its horizons and the
type's own options; each type validates its options (``denguekay.serving.predictors``). The risk cutoffs,
the acceptance thresholds, the outbreak rule and the interval level are not here: they live in
``parametro_sistema`` (seeded by the migrations).

Deployment options that the environment can replace (``.env`` locally, the service's variables in
Render): ``CORS_ORIGINS`` (comma-separated origins), ``SERVIR_NO_VALIDADAS`` (true | false) and
``STORAGE_BACKEND`` (local | supabase). ``DATABASE_URL`` and ``API_KEY`` are read only from the
environment (``denguekay.db.settings`` and ``apps.api.main``), and so are the Storage credentials
(``denguekay.serving.storage``).
"""

from dataclasses import dataclass
import os
import re

from dotenv import load_dotenv
import yaml

from denguekay.config.paths import CONFIG, ENV_FILE
from denguekay.serving.predictors import PREDICTORS

HORIZONS = (2, 3, 4)  # admitted by the DDL CHECK
STORAGE_BACKENDS = ("local", "supabase")
ORIGIN = re.compile(r"^https?://[^/\s,*]+$")  # scheme://host[:port], without a path or a trailing slash
BOOLEANS = {"true": True, "1": True, "false": False, "0": False}


@dataclass(frozen=True)
class ServiceSettings:
    paquete: dict
    servir_no_validadas: bool
    cors_origenes: list
    almacenamiento: str = "local"

    @property
    def tipo_paquete(self):
        return self.paquete["tipo"]

    @property
    def horizontes(self):
        return tuple(self.paquete["horizontes"])

    @property
    def opciones(self):
        return self.paquete.get("opciones") or {}

    def publication_options(self):
        """What a publication depends on; CORS and the storage backend are deployment details."""
        return {"paquete": self.paquete, "servir_no_validadas": self.servir_no_validadas}


def parse_origins(value):
    """Comma-separated origins (``CORS_ORIGINS``) or a list from config.yaml."""
    items = value.split(",") if isinstance(value, str) else value
    if not isinstance(items, (list, tuple)):
        raise ValueError("cors_origenes debe ser una lista de orígenes")
    origins = list(dict.fromkeys(str(item).strip() for item in items if str(item).strip()))
    if not origins:
        raise ValueError("cors_origenes debe tener al menos un origen")
    invalid = [o for o in origins if not ORIGIN.match(o)]
    if invalid:
        raise ValueError(f"Orígenes CORS inválidos (esquema://servidor[:puerto], sin ruta ni *): {invalid}")
    return origins


def parse_boolean(name, value):
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text not in BOOLEANS:
        raise ValueError(f"{name} debe ser true o false")
    return BOOLEANS[text]


def environment_overrides(environ):
    """Options of the ``serving`` section that the environment replaces (empty variables are ignored)."""
    overrides = {}
    for variable, key, parse in (("CORS_ORIGINS", "cors_origenes", str),
                                 ("SERVIR_NO_VALIDADAS", "servir_no_validadas", lambda v: parse_boolean(variable, v)),
                                 ("STORAGE_BACKEND", "almacenamiento", str.lower)):
        value = (environ.get(variable) or "").strip()
        if value:
            overrides[key] = parse(value)
    return overrides


def service_settings(path=CONFIG, environ=None):
    """Fail on an unknown predictor type, horizons outside the DDL, invalid origins or an unknown backend."""
    if environ is None:
        load_dotenv(ENV_FILE, override=False)
        environ = os.environ
    with open(path, encoding="utf-8") as file:
        value = (yaml.safe_load(file) or {}).get("serving")
    if not isinstance(value, dict):
        raise ValueError("Falta la sección serving en config.yaml")
    value = {**value, **environment_overrides(environ)}
    value["cors_origenes"] = parse_origins(value.get("cors_origenes", ()))
    options = ServiceSettings(**value)
    package = options.paquete
    if not isinstance(package, dict) or package.get("tipo") not in PREDICTORS:
        raise ValueError(f"serving.paquete.tipo debe ser uno de {sorted(PREDICTORS)}")
    horizons = package.get("horizontes")
    if (not isinstance(horizons, list) or not horizons or len(set(horizons)) != len(horizons)
            or any(h not in HORIZONS or isinstance(h, bool) for h in horizons)):
        raise ValueError("serving.paquete.horizontes debe listar horizontes únicos entre 2 y 4")
    if not isinstance(package.get("opciones", {}), dict):
        raise ValueError("serving.paquete.opciones debe ser un diccionario")
    if not isinstance(options.servir_no_validadas, bool):
        raise ValueError("servir_no_validadas debe ser un booleano")
    if options.almacenamiento not in STORAGE_BACKENDS:
        raise ValueError(f"almacenamiento (STORAGE_BACKEND) debe ser uno de {list(STORAGE_BACKENDS)}")
    return options
