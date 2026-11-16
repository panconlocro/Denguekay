"""Compare a regenerated V4 training table against an independent, frozen reference."""

from hashlib import sha256
import json

import numpy as np
import pandas as pd

from denguekay.config.paths import V4_GOLD_REFERENCE


def column_digest(values):
    return sha256(("\n".join(values) + "\n").encode("utf-8")).hexdigest()


def compare_gold_reference(path):
    reference = json.loads((V4_GOLD_REFERENCE / "referencia.json").read_bytes())
    floating = pd.read_csv(V4_GOLD_REFERENCE / "flotantes.csv.xz", float_precision="round_trip")
    frame = pd.read_csv(path, dtype="string", keep_default_na=False)
    expected_columns = list(reference["sha256_columnas"]["macOS ARM64"])
    if list(frame) != expected_columns or len(frame) != reference["filas"]:
        return {"estado": "difiere", "filas": len(frame), "columnas": list(frame),
                "motivo": "El esquema, el orden de columnas o el número de filas difiere de la referencia"}
    observed = {}
    for name, expected in reference["sha256_columnas"]["macOS ARM64"].items():
        digest = column_digest(frame[name])
        result = {"estado": "coincide" if digest == expected else "difiere", "sha256_obtenido": digest}
        if name in floating:
            values = frame[name].replace("", "nan").to_numpy(dtype=float)
            delta = np.abs(values - floating[name].to_numpy())
            finite = np.isfinite(delta).all()
            maximum = float(delta.max()) if finite else None
            result.update(diferencia_max_abs=maximum,
                          celdas_fuera_tolerancia=int((~np.isfinite(delta) | (delta > reference["atol"])).sum()))
            if finite and maximum <= reference["atol"]:
                result["estado"] = "coincide" if maximum == 0 else "dentro_tolerancia"
            else:
                result["estado"] = "difiere"
        observed[name] = result
    states = {item["estado"] for item in observed.values()}
    state = next(status for status in ("difiere", "dentro_tolerancia", "coincide") if status in states)
    return {"estado": state, "filas": len(frame), "atol": reference["atol"], "columnas": observed}
