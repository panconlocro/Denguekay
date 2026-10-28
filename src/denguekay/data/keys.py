"""
Small helpers used by more than one module (ingestion, processing).
They have no clear owner, so they live here and not in processing/.
"""

import re
import unicodedata


def normalize(s) -> str:
    """
    Normalized key to join districts across sources
    (meteo, socio, epi): no accents, no repeated spaces, upper case.

    E.g. "Santa Catalina de Mossa" -> "SANTA CATALINA DE MOSSA"
    """
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().upper()


def split_camel(s: str) -> str:
    """
    GADM returns district names in glued camelCase (e.g. "ElTallan").
    This splits "ElTallan" -> "El Tallan" by inserting a space before
    every capital letter that follows a lower-case one.
    """
    return re.sub(r"(?<=[a-záéíóú])(?=[A-ZÁÉÍÓÚ])", " ", s)


def normalize_sala(s: str) -> str:
    """Normalize Sala labels, including its PARIÐAS spelling."""
    return normalize(str(s).replace("Ð", "Ñ"))
