"""Configuración final congelada para la evaluación prospectiva de 2026 (encargo de FE).

**No se cambia después de ver datos de 2026**: cualquier cambio es un encargo
nuevo con su propio preregistro. Versiones:

- ``CONFIGURACION_2026_V1`` (histórica): resultado de las fases 0–4, congelada
  en el commit ``d6bd0be`` (2026-10-27). Reemplazada por la V2.
- ``CONFIGURACION_2026`` (vigente, V2): V1 + clima de gold (A3), adoptada por el
  complemento de clima (comparación 20, ``complemento_clima``). Su fecha de
  congelamiento es la del commit que la introduce.
"""

import hashlib
import json

import numpy as np
import pandas as pd

from src.modeling import complemento_clima as cc
from denguekay.model import horizon_strategies as eh
from src.modeling import features_inicio as fi
from src.modeling import hiperparametros as hp
from src.modeling import protocolo_arquitectura as pa
from denguekay.model import probabilistic_output as sp

FECHA_CONGELAMIENTO_V1 = "2026-10-27"
FECHA_CONGELAMIENTO = "2026-10-27"  # V2: fecha del commit que introduce CONFIGURACION_2026 con A3
SEMILLA_DESPLIEGUE = 17
COLUMNAS_A3 = cc.COLUMNAS_A3
# B3 no depende del corte (no tiene ajuste por bloque); este valor solo cumple la firma, como en los notebooks 33–34.
CORTE_REFERENCIA_B3 = pd.Timestamp("2021-08-28")

CONFIGURACION_2026_V1 = {
    "fecha_congelamiento": FECHA_CONGELAMIENTO_V1,
    "matriz": "C3 = base_6 + B3",
    "columnas": [*eh.GENERICAS, *fi.COLUMNAS["B3"]],
    "estrategia": "E3 (un regresor multi-salida, multi_output_tree, t+2/t+3/t+4 desde el origen o = t − 2)",
    "formulacion": "S4_s3",
    "conteo": "count:poisson con base_margin = log(casos del origen + 0,5) en las tres salidas",
    "probabilidad": "P(casos ≥ k) binomial negativa NB2, k = max(⌊umbral⌋ + 1, 2)",
    "dispersion": "dentro_muestra",
    "hiperparametros": {k: v for k, v in hp.BASE.items()},
    "calibracion": "Platt cronológico (predicciones fuera de muestra de las temporadas previas cerradas)",
    "umbral_alerta": pa.UMBRAL_ALERTA,
    "semilla_despliegue": SEMILLA_DESPLIEGUE,
    "decisiones": {"fase2c": "C3 elegida (gana a B; C empata con C3 y tiene más columnas)",
                   "fase3": "empate: se quedan los hiperparámetros heredados",
                   "fase4.2": "empate forzado por el respaldo: α dentro de la muestra",
                   "fase4.3": "S4_s3 gana a S4_s2 en h=4 por antelación"},
}

CONFIGURACION_2026 = {
    **CONFIGURACION_2026_V1,
    "version": 2,
    "fecha_congelamiento": FECHA_CONGELAMIENTO,
    "matriz": "C3 + A3 = base_6 + B3 + clima de gold (humedad y precipitación, media de 5 semanas hasta o)",
    "columnas": [*CONFIGURACION_2026_V1["columnas"], *COLUMNAS_A3],
    "filas_excluidas": "orígenes con nulos de arranque de A3 (primera semana de 2017, 65 filas)",
    "decisiones": {**CONFIGURACION_2026_V1["decisiones"],
                   "complemento_clima": "F+A3 mejora el conteo en h=2, 3 y 4 y la alerta no pierde en ninguno"},
}

# Estado de cada versión (fuera de las constantes para no cambiar sus huellas).
HISTORIAL = {
    "V1": {"constante": "CONFIGURACION_2026_V1", "commit": "d6bd0be", "fecha": FECHA_CONGELAMIENTO_V1,
           "estado": "reemplazada por la V2 (complemento de clima, comparación 20)"},
    "V2": {"constante": "CONFIGURACION_2026", "commit": "el que introduce esta constante", "fecha": FECHA_CONGELAMIENTO,
           "estado": "vigente"},
}

# Evaluación prospectiva de 2026 (fijada antes de ver datos; no se aplica a nada todavía).
EVALUACION_2026 = {
    "test_independiente": f"semanas objetivo publicadas por MINSA después del congelamiento de la V2 "
                          f"({FECHA_CONGELAMIENTO}, commit que introduce CONFIGURACION_2026 con A3)",
    "no_independientes": "las semanas 35–53 de 2025 ya están en el panel y se miraron como sensibilidad de "
                         "conteos (bloque calendario_2025); no cuentan como test independiente",
    "precision_a_la_hu0007_4": "la HU habla de «temporada 2025-2026»; el test independiente es solo la parte de "
                               "esa temporada publicada después del congelamiento",
    "reporte": "cada métrica con su número de positivos (semanas brote o inicios limpios) y un IC bootstrap",
    "minimos": {"semanas_brote_por_horizonte": 30, "inicios_limpios_por_horizonte": 20},
    "regla_minimos": "por debajo del mínimo, la celda se declara «no evaluable» en lugar de «cumple / no cumple»; "
                     "clasificación y regresión usan el mínimo de semanas brote; la antelación, el de inicios limpios",
    "justificacion_minimos": "calendario_2025 tuvo 3 semanas brote por horizonte (2 de inicio): F1 a 0,50 dio 0 en "
                             "h2 y h4 y 0,14 en h3, con 0,12 de rango entre semillas, así que una sola semana cambia "
                             "el veredicto. Con 30 semanas brote una semana mueve el recall 0,033; con 20 inicios, "
                             "una alerta mueve la antelación 0,05. 20 está por debajo del bloque evaluado más chico "
                             "(temporada_2024: 23 inicios, 857 semanas brote) y 30 por debajo del bloque de "
                             "calibración (temporada_2021: 90 semanas brote)",
}


def evaluable(positivos: int, tipo: str) -> bool:
    """``True`` si la celda alcanza el mínimo preregistrado (``tipo``: ``"brote"`` o ``"inicios"``)."""
    clave = {"brote": "semanas_brote_por_horizonte", "inicios": "inicios_limpios_por_horizonte"}[tipo]
    return int(positivos) >= EVALUACION_2026["minimos"][clave]


def origenes(panel: pd.DataFrame, insumos: dict, regla: dict, historia: pd.DataFrame | None = None,
             configuracion: dict | None = None) -> pd.DataFrame:
    """Tabla de orígenes de una configuración (por defecto la vigente), en memoria.

    ``base_6`` + B3 siempre; si la configuración usa A3, se quitan los orígenes
    con nulos de arranque de A3 (las columnas ya vienen de gold h=2).
    """
    from denguekay.config.paths import SILVER_EPI_HISTORICAL

    configuracion = CONFIGURACION_2026 if configuracion is None else configuracion
    if historia is None:
        historia = pd.read_csv(SILVER_EPI_HISTORICAL, dtype={"ubigeo": "string"})
    vi = fi.VariablesInicio(panel, insumos["serie"], historia, regla)
    salida = vi.origenes(eh.tabla_origenes(insumos["matrices"][2]), ["B3"], CORTE_REFERENCIA_B3)
    clima = [c for c in COLUMNAS_A3 if c in configuracion["columnas"]]
    if clima:
        salida = salida.loc[salida[clima].notna().all(axis=1)].reset_index(drop=True)
    return salida


def predecir(matrices: dict[int, pd.DataFrame], origenes_c3: pd.DataFrame,
             semilla: int = SEMILLA_DESPLIEGUE, configuracion: dict | None = None) -> pd.DataFrame:
    """Predicciones fuera de muestra de una configuración congelada (protocolo de bloques)."""
    c = CONFIGURACION_2026 if configuracion is None else configuracion
    return sp.predecir_e3(matrices, semilla, c["formulacion"], columnas=c["columnas"], origenes=origenes_c3,
                          hiperparametros=c["hiperparametros"], dispersion=c["dispersion"])


# Fingerprints under the original definition: SHA-256 of the configuration JSON plus the source text of
# estrategias_horizonte, features_inicio, hiperparametros, protocolo_arquitectura and salida_probabilistica.
# Moving or translating those modules changes that value without changing the model, so the restructure
# (docs/decisions/0001-repo-restructure.md, decision D1) keeps them as history and replaces the definition.
HISTORICAL_FINGERPRINTS = {
    "V1": {"sha256": "88ed2a43b0171a0878b99122b70109be61b27d5d4d29a2b93eae55066fd8f945", "commit": "d6bd0be",
           "constant": "CONFIGURACION_2026_V1"},
    "V2": {"sha256": "c36d7a80d1896a203874bf271bd78f1078850e1faa381e2b17e9ba04b07d5569", "commit": "424a148",
           "constant": "CONFIGURACION_2026"},
}
HISTORICAL_FINGERPRINT_DEFINITION = "SHA-256(configuration JSON + source of eh, fi, hp, pa and sp)"
FINGERPRINT_DEFINITION = "SHA-256(SHA-256(configuration JSON) + ':' + predictions_digest(reference predictions))"

PREDICTION_KEY = ["ubigeo", "semana_inicio", "horizonte", "bloque"]
PREDICTION_VALUES = ["casos_predichos", "probabilidad_brote"]

# Behavioural fingerprints of the reference predictions (seed 17, protocol blocks). XGBoost gives identical
# bits for a fixed device and thread count, but CPU and CUDA (and a different n_jobs on CPU) do not, so each
# value is keyed by the training setup (see setup_key).
REFERENCE_FINGERPRINTS = {
    "device=cpu,n_jobs=2": {"V1": "be86664973cf5e7ac3af4a29ae0f8887a5191ed1007a0c097aacba3c7190bff5",
                            "V2": "0fe5d10712d4127e9e2728d7de230b8db6bfbae364b018f2b449ccd10818e2b3"},
    "device=cuda": {"V1": "1534b535bd19d6945c852c10f64294c1d2b16cd9e4359d074fcac11a9ed3806e",
                    "V2": "b302d838aa402017dbcf70320cd8c061ef854e0eda50460b801d557cd709a936"},
}


def setup_key(setup: dict) -> str:
    """Key of REFERENCE_FINGERPRINTS for a ``configuracion_xgboost()`` result."""
    return f"device=cpu,n_jobs={setup['n_jobs']}" if setup["device"] == "cpu" else "device=cuda"


def predictions_digest(predictions: pd.DataFrame) -> str:
    """SHA-256 of the prediction keys and exact float64 values, in canonical key order."""
    ordered = predictions.sort_values(PREDICTION_KEY, kind="mergesort").reset_index(drop=True)
    digest = hashlib.sha256()
    # Column by column: the predictions carry DataFrames in ``attrs``, which frame-level astype rejects.
    keys = [ordered[c].astype(str).tolist() for c in PREDICTION_KEY]
    digest.update("|".join(",".join(row) for row in zip(*keys)).encode("utf-8"))
    for column in PREDICTION_VALUES:
        digest.update(np.ascontiguousarray(ordered[column].to_numpy(dtype="float64")).tobytes())
    return digest.hexdigest()


def fingerprint(predictions: pd.DataFrame, configuracion: dict | None = None) -> str:
    """Behavioural fingerprint of a frozen configuration: its JSON and its reference predictions.

    It does not depend on where the code lives or how it is written: two runs agree only if they use the
    same configuration and produce bit-for-bit identical predictions.
    """
    configuracion = CONFIGURACION_2026 if configuracion is None else configuracion
    config_digest = hashlib.sha256(
        json.dumps(configuracion, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")).hexdigest()
    return hashlib.sha256(f"{config_digest}:{predictions_digest(predictions)}".encode("utf-8")).hexdigest()


def coincide_con_guardadas(pred: pd.DataFrame, guardadas: pd.DataFrame, tolerancia: float = 1e-9) -> dict:
    """Compara predicciones nuevas con las guardadas (misma semilla) por llave."""
    clave = ["ubigeo", "semana_inicio", "horizonte", "bloque"]
    a = pred.assign(semana_inicio=pd.to_datetime(pred.semana_inicio).dt.strftime("%Y-%m-%d"))
    b = guardadas.assign(semana_inicio=pd.to_datetime(guardadas.semana_inicio).dt.strftime("%Y-%m-%d"))
    m = a.merge(b, on=clave, suffixes=("", "_guardada"), validate="one_to_one")
    dif = {c: float(np.abs(m[c] - m[f"{c}_guardada"]).max()) for c in ("casos_predichos", "probabilidad_brote")}
    return {"filas": len(a), "filas_guardadas": len(b), "cruzadas": len(m), **dif,
            "coincide": len(m) == len(a) == len(b) and all(v <= tolerancia for v in dif.values())}
