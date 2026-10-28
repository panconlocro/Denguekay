"""
Estilo de gráficos y guardado reproducible de figuras/métricas del EDA.

Las figuras van a docs/eda/figuras/<fase>/ y las métricas clave a
docs/eda/metricas/<fase>.json. Nada del EDA se escribe en data/.
"""

import json
import re
from pathlib import Path

from src.utils.paths import EDA_FIGURAS, EDA_METRICAS

# Paleta apta para daltonismo (Okabe-Ito). Un color = un significado en todo el EDA.
COLORES = {
    "casos": "#D55E00",
    "clima": "#0072B2",
    "socio": "#009E73",
    "referencia": "#666666",
    "resalte": "#CC79A7",
}


def aplicar_estilo() -> None:
    """Configura matplotlib con un estilo sobrio y legible para la tesis."""
    import matplotlib as mpl

    mpl.rcParams.update({
        "figure.figsize": (10, 5),
        "figure.dpi": 100,
        "savefig.dpi": 150,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.alpha": 0.25,
        "axes.titlesize": 12,
        "axes.titleweight": "bold",
        "axes.labelsize": 10,
        "legend.frameon": False,
    })


def _slug(texto: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", texto.lower()).strip("_")


def guardar_figura(fig, fase: str, nombre: str) -> Path:
    """Guarda fig en docs/eda/figuras/<fase>/<nombre>.png y devuelve la ruta."""
    carpeta = EDA_FIGURAS / _slug(fase)
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f"{_slug(nombre)}.png"
    fig.savefig(ruta, bbox_inches="tight")
    return ruta


def guardar_metricas(fase: str, metricas: dict) -> Path:
    """
    Fusiona `metricas` en docs/eda/metricas/<fase>.json. Cada cifra citada en
    docs/eda/hallazgos.md debe salir de acá para que pueda verificarse.
    """
    EDA_METRICAS.mkdir(parents=True, exist_ok=True)
    ruta = EDA_METRICAS / f"{_slug(fase)}.json"
    actuales = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}
    actuales.update(metricas)
    ruta.write_text(json.dumps(actuales, indent=2, ensure_ascii=False, default=float) + "\n", encoding="utf-8")
    return ruta
