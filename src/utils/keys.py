"""
Helpers chicos usados por más de un módulo (ingestion, processing).
No tienen dueño claro por eso viven en utils/ y no en processing/.
"""

import re
import unicodedata


def normalizar(s) -> str:
    """
    Llave normalizada para cruzar distritos entre fuentes distintas
    (meteo, socio, epi): sin tildes, sin espacios repetidos, en mayúsculas.

    Ej: "Santa Catalina de Mossa" -> "SANTA CATALINA DE MOSSA"
    """
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().upper()


def separar_camel(s: str) -> str:
    """
    GADM devuelve nombres de distrito en camelCase pegado (ej. "ElTallan").
    Esto separa "ElTallan" -> "El Tallan" insertando un espacio antes de
    cada mayúscula que sigue a una minúscula.
    """
    return re.sub(r"(?<=[a-záéíóú])(?=[A-ZÁÉÍÓÚ])", " ", s)