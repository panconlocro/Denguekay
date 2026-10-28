"""Puerto de almacenamiento de artefactos y adaptador local (TB1).

El documento OE2 define buckets de Supabase Storage (``modelos``, ``geodatos``,
``reportes``). En TB1 se usan carpetas locales con la misma ruta lógica
``<bucket>/<nombre>``; un adaptador Supabase podrá implementar el mismo puerto.
"""

from pathlib import Path, PurePosixPath
from typing import Protocol

from src.utils.paths import STORAGE

BUCKETS = ("modelos", "geodatos", "reportes")


class Almacenamiento(Protocol):
    def guardar(self, ruta: str, contenido: bytes) -> None: ...
    def leer(self, ruta: str) -> bytes: ...
    def existe(self, ruta: str) -> bool: ...


def validar_ruta(ruta):
    """Ruta lógica ``bucket/archivo`` sin escapes de directorio."""
    partes = PurePosixPath(ruta).parts
    if (len(partes) < 2 or partes[0] not in BUCKETS or any(p in ("..", ".") for p in partes)
            or "\\" in ruta or "//" in ruta or ruta.startswith("/")):
        raise ValueError(f"Ruta de artefacto inválida: {ruta}")
    return partes


class AlmacenamientoLocal:
    """Guarda en ``models/storage/<bucket>/`` (ignorado por Git)."""

    def __init__(self, raiz=STORAGE):
        self.raiz = Path(raiz)

    def _archivo(self, ruta):
        return self.raiz.joinpath(*validar_ruta(ruta))

    def guardar(self, ruta, contenido):
        archivo = self._archivo(ruta)
        archivo.parent.mkdir(parents=True, exist_ok=True)
        temporal = archivo.with_suffix(archivo.suffix + ".tmp")
        temporal.write_bytes(contenido)
        temporal.replace(archivo)  # escritura atómica: nunca queda un artefacto a medias

    def leer(self, ruta):
        archivo = self._archivo(ruta)
        if not archivo.is_file():
            raise FileNotFoundError(f"No existe el artefacto {ruta}")
        return archivo.read_bytes()

    def existe(self, ruta):
        return self._archivo(ruta).is_file()
