"""Choose where XGBoost trains: an NVIDIA GPU (CUDA) if there is one, otherwise the CPU.

The setting lives in ``configs/config.yaml`` (``xgboost`` section) and can be
overridden with environment variables, handy for a single run:

- ``DENGUEKAY_XGB_DEVICE``: ``auto`` (default), ``cuda`` or ``cpu``.
- ``DENGUEKAY_XGB_NJOBS``: ``auto`` (every core) or a number.

``auto`` trains a tiny model on ``cuda`` and reads which device XGBoost
actually used: without a visible NVIDIA GPU (for example on an Apple Silicon
Mac, or with an AMD card) it falls back to the CPU without error. XGBoost
does not support Mac GPUs (Metal), so there it is always the CPU.

On the CPU the number of threads may change the last bits of the results
(see ``REFERENCE_FINGERPRINTS`` in ``frozen_configs``), and training on the GPU
can change decimals with respect to the CPU; that is why the device is recorded
in the report parameters and in MLflow (``xgb.device``).

To see what your machine detects and compare times::

    python -m denguekay.model.device
    python -m denguekay.model.device --comparar
"""

import argparse
import json
import os
import time
import warnings
from functools import lru_cache

import numpy as np
import xgboost as xgb

from denguekay.config.paths import CONFIG

VALID_DEVICES = {"auto", "cuda", "cpu"}

# With data on the CPU and the model on the GPU, XGBoost warns on every prediction that
# it converts the data. That is expected and does not affect the result.
warnings.filterwarnings("ignore", message=".*mismatched devices.*")


def _read_config() -> dict:
    """Read the ``xgboost`` section of config.yaml (empty if it does not exist)."""
    try:
        import yaml

        with open(CONFIG, encoding="utf-8") as file:
            return (yaml.safe_load(file) or {}).get("xgboost") or {}
    except FileNotFoundError:
        return {}


def cuda_available() -> bool:
    """True if this XGBoost has CUDA and really trains on an NVIDIA GPU."""
    if not xgb.build_info().get("USE_CUDA", False):
        return False
    x = np.random.default_rng(0).random((64, 3))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            model = xgb.train({"device": "cuda", "tree_method": "hist", "verbosity": 0},
                               xgb.DMatrix(x, label=x[:, 0]), num_boost_round=1)
        except xgb.core.XGBoostError:
            return False
    used = json.loads(model.save_config())["learner"]["generic_param"].get("device", "cpu")
    return used.startswith("cuda")


@lru_cache(maxsize=1)
def xgboost_settings() -> dict:
    """Return ``{"device": ..., "n_jobs": ...}`` to pass to XGBoost."""
    config = _read_config()
    requested = str(os.environ.get("DENGUEKAY_XGB_DEVICE") or config.get("device") or "auto").lower()
    if requested not in VALID_DEVICES:
        raise ValueError(f"device debe ser auto, cuda o cpu; se recibió {requested!r}")
    if requested == "cpu":
        device = "cpu"
    else:
        has_gpu = cuda_available()
        if requested == "cuda" and not has_gpu:
            raise RuntimeError(
                "Se pidió device=cuda pero XGBoost no encuentra una GPU NVIDIA utilizable. "
                "Usa device: auto o cpu en configs/config.yaml.")
        device = "cuda" if has_gpu else "cpu"
    threads = str(os.environ.get("DENGUEKAY_XGB_NJOBS") or config.get("n_jobs") or "auto").lower()
    n_jobs = (os.cpu_count() or 1) if threads == "auto" else int(threads)
    return {"device": device, "n_jobs": n_jobs}


def _compare_times() -> None:
    """Train the first real fold (h=4, base_6) on CPU and on GPU and time both."""
    import pandas as pd

    from denguekay.model import train
    from denguekay.config.paths import GOLD, SILVER_INTEGRATED

    gold = pd.read_csv(GOLD / f"{SILVER_INTEGRATED.stem}_h4_gold.csv", dtype={"ubigeo": "string"},
                       parse_dates=["semana_inicio", "origen_inicio", "origen_cierre"])
    data, _ = train.prepare_gold(gold, 4)
    training, _, _ = train.split_season(data, 2024)
    columns = train.variant_columns(4)["historia_4_mas_2"]
    base = {k: v for k, v in train.BASE_PARAMS.items() if k != "device"}
    options = ["cpu"] + (["cuda"] if cuda_available() else [])
    print(f"Fold de prueba: {len(training)} filas, {len(columns)} columnas, 2 modelos")
    for device in options:
        times = []
        for _ in range(3):
            start = time.perf_counter()
            for target, y in (("reg:squarederror", np.log1p(training.casos_Dengue)),
                                ("binary:logistic", training.brote)):
                model_class = xgb.XGBRegressor if target.startswith("reg") else xgb.XGBClassifier
                model_class(objective=target, **base, device=device).fit(training[columns], y)
            times.append(time.perf_counter() - start)
        print(f"  {device:4s}: {min(times):.2f} s por fold (mejor de 3)")


def main() -> None:
    """CLI: show the chosen device and, optionally, compare times."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--comparar", action="store_true", help="Mide CPU vs GPU con un fold real")
    args = parser.parse_args()
    info = xgb.build_info()
    print(f"XGBoost {xgb.__version__} | compilado con CUDA: {info.get('USE_CUDA', False)}")
    print(f"GPU NVIDIA utilizable: {cuda_available()}")
    print(f"Configuración que usarán los experimentos: {xgboost_settings()}")
    if args.comparar:
        _compare_times()


if __name__ == "__main__":
    main()
