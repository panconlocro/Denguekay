"""Retrain a registered model version from the data of its Release and check it against what was recorded.

``python -m denguekay.model.reproduce v0|v1|v2`` (from the repository root, after
``python -m denguekay.data.ingestion.release_bundles --version <v>``). Nothing is written to ``data/`` nor to
``models/experimentos/``: retrained outputs go to a temporary folder.

- **v1, v2** (frozen configurations): the protocol blocks with seed 17, their behavioural fingerprint against
  ``frozen_configs.REFERENCE_FINGERPRINTS`` for this device and threads, and the largest difference with the saved
  predictions of the study (``fe_hiperparametros/fase4`` and ``complemento_clima``). The fingerprint exists for
  ``device=cpu,n_jobs=2`` and ``device=cuda``; set ``DENGUEKAY_XGB_DEVICE`` and ``DENGUEKAY_XGB_NJOBS`` to choose.
- **v0** (no fingerprint: its identity is its package): the compact temporal validation of study 03 rerun on
  ``gold/respaldo_pre_b3``, compared with the registered selection metrics
  (``models/registry/v0/validacion_temporal_compacta.json``) and the saved block predictions.
- **v3**: its reference run lives in the study (``research/06_model_improvement/code/phase_v3_close.py verificar``,
  see ``docs/modeling/reproducir_v3.md``); this module points there.

Tolerances are never relaxed here: the result reports the measured differences and whether they are zero.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd

VERSIONS = ("v0", "v1", "v2", "v3")
SAVED = {"V1": ("fase4", "predicciones_s4s3_dentro_muestra.csv.gz"),
         "V2": ("complemento_clima", "predicciones_F_A3.csv.gz")}


def _setup() -> dict:
    from denguekay.model.device import xgboost_settings

    xgboost_settings.cache_clear()
    return xgboost_settings()


def frozen(name: str) -> dict:
    """V1 or V2: retrain the protocol blocks (seed 17) and compare fingerprint and saved predictions."""
    from denguekay.config.paths import FE_HYPERPARAMETERS_EXPERIMENTS, GOLD_MANIFEST, SILVER_INTEGRATED
    from denguekay.data.loading import load_integrated
    from denguekay.evaluation import variants
    from denguekay.model import frozen_configs as fc

    config = {"V1": fc.CONFIG_2026_V1, "V2": fc.CONFIG_2026}[name]
    start = time.perf_counter()
    panel = load_integrated(SILVER_INTEGRATED)
    rule = json.loads(GOLD_MANIFEST.read_text(encoding="utf-8"))["regla_brote"]
    inputs = variants.inputs(panel, rule)
    origins = fc.origins(panel, inputs, rule, configuration=config)
    predictions = fc.predict(inputs["matrices"], origins, configuration=config)
    setup = _setup()
    key = fc.setup_key(setup)
    fingerprint = fc.fingerprint(predictions, config)
    expected = fc.REFERENCE_FINGERPRINTS.get(key, {}).get(name)
    folder, file = SAVED[name]
    saved_path = FE_HYPERPARAMETERS_EXPERIMENTS / folder / file
    comparison = None
    if saved_path.exists():
        saved = pd.read_csv(saved_path, dtype={"ubigeo": "string"}, float_precision="round_trip")
        if "semilla" in saved:
            saved = saved[saved.semilla.eq(fc.DEPLOYMENT_SEED)]
        if "variante" in saved and name == "V2":
            saved = saved[saved.variante.eq("F+A3")] if saved.variante.eq("F+A3").any() else saved
        saved = saved.assign(ubigeo=saved.ubigeo.astype(str))
        comparison = fc.matches_saved(predictions.assign(ubigeo=predictions.ubigeo.astype(str)), saved, tolerance=0.0)
    return {"version": name.lower(), "entorno": key, "segundos": round(time.perf_counter() - start, 1),
            "huella": fingerprint, "huella_esperada": expected,
            "huella_coincide": None if expected is None else fingerprint == expected,
            "predicciones_guardadas": comparison}


def compact() -> dict:
    """v0: rerun the compact temporal validation into a temporary folder and compare with the registered one."""
    from denguekay.config.paths import COMPACT_METRICS, COMPACT_PREDICTIONS
    from denguekay.evaluation.compact_validation import run_compact_validation

    start = time.perf_counter()
    registered = json.loads(COMPACT_METRICS.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        run_compact_validation(output_dir=tmp, metrics_path=tmp / "metricas.json", audit=True, validate_data=False,
                               log_mlflow=False)
        new = json.loads((tmp / "metricas.json").read_text(encoding="utf-8"))
        new_predictions = pd.read_csv(tmp / COMPACT_PREDICTIONS.name, dtype={"ubigeo": "string"})
    selection = {h: (registered["horizontes"][h]["seleccion_2022_2023"], new["horizontes"][h]["seleccion_2022_2023"])
                 for h in registered["horizontes"]}
    differences = _json_differences(registered, new)
    out = {"version": "v0", "entorno": _setup(), "segundos": round(time.perf_counter() - start, 1),
           "seleccion_igual": all(a == b for a, b in selection.values()), "seleccion": selection,
           "metricas_numericas_distintas": len(differences), "mayor_diferencia_metricas": differences[:5]}
    if COMPACT_PREDICTIONS.exists():
        saved = pd.read_csv(COMPACT_PREDICTIONS, dtype={"ubigeo": "string"})
        numeric = [c for c in saved.columns if c in new_predictions and pd.api.types.is_float_dtype(saved[c])]
        same_shape = saved.shape == new_predictions.shape and list(saved.columns) == list(new_predictions.columns)
        out["predicciones_guardadas"] = {
            "misma_forma": same_shape,
            "diferencia_maxima": ({c: float(np.nanmax(np.abs(saved[c].to_numpy(float) - new_predictions[c].to_numpy(float))))
                                   for c in numeric} if same_shape else None)}
    return out


def _json_differences(a, b, path="") -> list[tuple[str, float]]:
    """Numeric leaves of two JSON documents that differ, largest first (strings and structure compared too)."""
    found = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                found.append((f"{path}/{k}", float("inf")))
            else:
                found += _json_differences(a[k], b[k], f"{path}/{k}")
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b)):
            found += _json_differences(x, y, f"{path}[{i}]")
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        if a != b and not (np.isnan(a) and np.isnan(b)):
            found.append((path, abs(float(a) - float(b))))
    elif a != b and not _volatile(path):
        found.append((path, float("inf")))
    return sorted(found, key=lambda item: -item[1])


def _volatile(path: str) -> bool:
    """Fields that describe the run, not the result (dates, run ids, paths, device)."""
    return any(word in path for word in ("fecha", "mlflow", "ruta", "device", "duracion", "segundos", "plataforma"))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Reentrena una versión registrada con los datos de su Release y "
                                                 "la compara con lo registrado.")
    parser.add_argument("version", choices=VERSIONS)
    args = parser.parse_args(argv)
    if args.version == "v3":
        print("La v3 se verifica con: python research/06_model_improvement/code/phase_v3_close.py verificar "
              "--semilla 17 (ver docs/modeling/reproducir_v3.md)")
        return 0
    result = compact() if args.version == "v0" else frozen(args.version.upper())
    print(json.dumps(result, ensure_ascii=False, indent=1, default=str))
    if args.version == "v0":
        ok = result["seleccion_igual"] and result["metricas_numericas_distintas"] == 0
    else:
        ok = bool(result["huella_coincide"])
    print("REPRODUCE:", "SÍ" if ok else "NO (ver diferencias arriba)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
