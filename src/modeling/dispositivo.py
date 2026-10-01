"""Elige dónde entrena XGBoost: GPU NVIDIA (CUDA) si existe, si no CPU.

La configuración vive en ``config/config.yaml`` (sección ``xgboost``) y se
puede sobrescribir con variables de entorno, útiles para una sola corrida:

- ``DENGUEKAY_XGB_DEVICE``: ``auto`` (por defecto), ``cuda`` o ``cpu``.
- ``DENGUEKAY_XGB_NJOBS``: ``auto`` (todos los núcleos) o un número.

``auto`` prueba entrenar un modelo mínimo en ``cuda`` y lee qué dispositivo
usó XGBoost de verdad: si no hay GPU NVIDIA visible (por ejemplo en una Mac
con Apple Silicon, o con una tarjeta AMD), cae a CPU sin error. XGBoost no
tiene soporte para la GPU de las Mac (Metal), así que ahí siempre es CPU.

La cantidad de hilos de CPU no cambia los resultados (se comprobó con
``n_jobs`` 1, 2 y 8). Entrenar en GPU sí puede cambiar decimales respecto de
CPU; por eso el dispositivo queda registrado en los parámetros del reporte y
en MLflow (``xgb.device``).

Para ver qué detecta tu equipo y comparar tiempos::

    python -m src.modeling.dispositivo
    python -m src.modeling.dispositivo --comparar
"""

import argparse
import json
import os
import time
import warnings
from functools import lru_cache

import numpy as np
import xgboost as xgb

from src.utils.paths import CONFIG

DISPOSITIVOS_VALIDOS = {"auto", "cuda", "cpu"}

# Con datos en CPU y modelo en GPU, XGBoost avisa en cada predicción que
# convierte los datos. Es esperado y no afecta el resultado.
warnings.filterwarnings("ignore", message=".*mismatched devices.*")


def _leer_config() -> dict:
    """Lee la sección ``xgboost`` de config.yaml (vacía si no existe)."""
    try:
        import yaml

        with open(CONFIG, encoding="utf-8") as archivo:
            return (yaml.safe_load(archivo) or {}).get("xgboost") or {}
    except FileNotFoundError:
        return {}


def cuda_disponible() -> bool:
    """True si este XGBoost tiene CUDA y entrena de verdad en una GPU NVIDIA."""
    if not xgb.build_info().get("USE_CUDA", False):
        return False
    x = np.random.default_rng(0).random((64, 3))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            modelo = xgb.train({"device": "cuda", "tree_method": "hist", "verbosity": 0},
                               xgb.DMatrix(x, label=x[:, 0]), num_boost_round=1)
        except xgb.core.XGBoostError:
            return False
    usado = json.loads(modelo.save_config())["learner"]["generic_param"].get("device", "cpu")
    return usado.startswith("cuda")


@lru_cache(maxsize=1)
def configuracion_xgboost() -> dict:
    """Devuelve ``{"device": ..., "n_jobs": ...}`` para pasar a XGBoost."""
    config = _leer_config()
    pedido = str(os.environ.get("DENGUEKAY_XGB_DEVICE") or config.get("device") or "auto").lower()
    if pedido not in DISPOSITIVOS_VALIDOS:
        raise ValueError(f"device debe ser auto, cuda o cpu; se recibió {pedido!r}")
    if pedido == "cpu":
        dispositivo = "cpu"
    else:
        hay_gpu = cuda_disponible()
        if pedido == "cuda" and not hay_gpu:
            raise RuntimeError(
                "Se pidió device=cuda pero XGBoost no encuentra una GPU NVIDIA utilizable. "
                "Usa device: auto o cpu en config/config.yaml.")
        dispositivo = "cuda" if hay_gpu else "cpu"
    hilos = str(os.environ.get("DENGUEKAY_XGB_NJOBS") or config.get("n_jobs") or "auto").lower()
    n_jobs = (os.cpu_count() or 1) if hilos == "auto" else int(hilos)
    return {"device": dispositivo, "n_jobs": n_jobs}


def _comparar_tiempos() -> None:
    """Entrena el primer fold real (h=4, base_6) en CPU y en GPU y mide tiempos."""
    import pandas as pd

    from src.modeling import train
    from src.utils.paths import GOLD, SILVER_INTEGRADO

    gold = pd.read_csv(GOLD / f"{SILVER_INTEGRADO.stem}_h4_gold.csv", dtype={"ubigeo": "string"},
                       parse_dates=["semana_inicio", "origen_inicio", "origen_cierre"])
    datos, _ = train.preparar_gold(gold, 4)
    entrenamiento, _, _ = train.separar_temporada(datos, 2024)
    columnas = train.columnas_variantes(4)["historia_4_mas_2"]
    base = {k: v for k, v in train.PARAMETROS_BASE.items() if k != "device"}
    opciones = ["cpu"] + (["cuda"] if cuda_disponible() else [])
    print(f"Fold de prueba: {len(entrenamiento)} filas, {len(columnas)} columnas, 2 modelos")
    for dispositivo in opciones:
        tiempos = []
        for _ in range(3):
            inicio = time.perf_counter()
            for objetivo, y in (("reg:squarederror", np.log1p(entrenamiento.casos_Dengue)),
                                ("binary:logistic", entrenamiento.brote)):
                clase = xgb.XGBRegressor if objetivo.startswith("reg") else xgb.XGBClassifier
                clase(objective=objetivo, **base, device=dispositivo).fit(entrenamiento[columnas], y)
            tiempos.append(time.perf_counter() - inicio)
        print(f"  {dispositivo:4s}: {min(tiempos):.2f} s por fold (mejor de 3)")


def main() -> None:
    """CLI: muestra el dispositivo elegido y, opcionalmente, compara tiempos."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--comparar", action="store_true", help="Mide CPU vs GPU con un fold real")
    args = parser.parse_args()
    info = xgb.build_info()
    print(f"XGBoost {xgb.__version__} | compilado con CUDA: {info.get('USE_CUDA', False)}")
    print(f"GPU NVIDIA utilizable: {cuda_disponible()}")
    print(f"Configuración que usarán los experimentos: {configuracion_xgboost()}")
    if args.comparar:
        _comparar_tiempos()


if __name__ == "__main__":
    main()
