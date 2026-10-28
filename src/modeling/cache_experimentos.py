"""Caché en disco de los cálculos costosos de un notebook de modelado.

El notebook 31 reentrena cientos de modelos en cada corrida. La caché guarda
los resultados (predicciones y evaluaciones) junto con una **huella** de todo
lo que los determina y los reutiliza solo si la huella coincide. La huella
cubre:

- los datos de entrada (silver integrado, historia epidemiológica, gold h=2 y
  h=4 y su manifiesto);
- la configuración (``configs/config.yaml``);
- el código de los módulos de modelado (``src/modeling/*.py``) y de los que
  estos usan para el contrato temporal y el calendario.

Cualquier cambio en esos archivos invalida la caché sola. ``forzar=True``
recalcula siempre. Política del proyecto: la corrida de **cierre** de cada
etapa se hace desde cero (forzada); la caché es solo para iterar sobre tablas
y documentos. Los archivos viven en ``models/experimentos/`` (no se versionan)
y nunca en ``data/``.
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

DIRECTORIO_CACHE = ARCHITECTURE_EXPERIMENTS / "cache"
CODIGO_EXTRA = ("src/validation/contrato_pronostico.py", "src/eda/temporal.py", "src/eda/carga.py",
                "src/utils/calendario.py", "src/serving/riesgo.py")
VARIABLE_FORZAR = "DENGUEKAY_FORZAR_REENTRENO"


def huella_archivos(archivos: list[Path]) -> str:
    """SHA-256 del contenido y la ruta relativa de una lista de archivos (orden estable)."""
    total = hashlib.sha256()
    for ruta in sorted(Path(a) for a in archivos):
        if not ruta.exists():
            raise FileNotFoundError(f"No existe un insumo de la caché: {ruta}")
        try:
            nombre = ruta.resolve().relative_to(ROOT.resolve()).as_posix()
        except ValueError:
            nombre = ruta.name
        total.update(nombre.encode("utf-8"))
        total.update(hashlib.sha256(ruta.read_bytes()).digest())
    return total.hexdigest()


def insumos_encargo() -> list[Path]:
    """Datos, configuración y código que determinan los resultados del encargo."""
    datos = [SILVER_INTEGRATED, SILVER_EPI_HISTORICAL, GOLD_MANIFEST,
             *sorted(GOLD.glob(f"{SILVER_INTEGRATED.stem}_h*_gold.csv"))]
    # The modelling code is moving into the denguekay package (restructure, phase 3): both trees count.
    codigo = [*sorted((ROOT / "src" / "modeling").glob("*.py")), *sorted((ROOT / "src" / "denguekay").rglob("*.py")),
              *(ROOT / c for c in CODIGO_EXTRA)]
    codigo = list(dict.fromkeys(codigo))
    return [*datos, CONFIG, *codigo]


def huella_encargo() -> str:
    """Huella de todos los insumos del encargo de arquitectura multi-horizonte."""
    return huella_archivos(insumos_encargo())


def forzar_desde_entorno() -> bool:
    """``True`` si la variable ``DENGUEKAY_FORZAR_REENTRENO`` vale 1 (corrida de cierre)."""
    return os.environ.get(VARIABLE_FORZAR, "0").strip() == "1"


def cargar_o_calcular(nombre: str, calcular, *, huella: str, directorio: Path = DIRECTORIO_CACHE,
                      forzar: bool = False):
    """Devuelve el resultado guardado si su huella coincide; si no, lo calcula y lo guarda.

    ``calcular`` es una función sin argumentos. El resultado se guarda con
    ``pickle`` y un JSON de metadatos (huella y nombre); la escritura es
    atómica para no dejar una caché a medias si la corrida se interrumpe.
    """
    directorio = Path(directorio)
    datos, meta = directorio / f"{nombre}.pkl", directorio / f"{nombre}.json"
    if not forzar and datos.exists() and meta.exists():
        guardada = json.loads(meta.read_text(encoding="utf-8"))
        if guardada.get("huella") == huella:
            with datos.open("rb") as archivo:
                print(f"caché: '{nombre}' reutilizada (huella {huella[:12]})")
                return pickle.load(archivo)
    resultado = calcular()
    directorio.mkdir(parents=True, exist_ok=True)
    for destino, contenido in ((datos, pickle.dumps(resultado, protocol=pickle.HIGHEST_PROTOCOL)),
                               (meta, json.dumps({"nombre": nombre, "huella": huella}).encode("utf-8"))):
        with tempfile.NamedTemporaryFile(dir=directorio, delete=False, suffix=".tmp") as temporal:
            temporal.write(contenido)
        os.replace(temporal.name, destino)
    print(f"caché: '{nombre}' {'recalculada (forzada)' if forzar else 'calculada'} (huella {huella[:12]})")
    return resultado
