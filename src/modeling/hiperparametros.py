"""Optimización de hiperparámetros de E3·S4_s2 sobre la matriz C3 (fase 3, HU0007-3).

``PREREGISTRO_FASE3`` fija, antes del estudio, la base, el objetivo, el
espacio, el muestreador, la selección de la candidata, la regla de adopción y
la robustez. El protocolo (``protocolo_arquitectura``) no cambia: cada
configuración se evalúa con ``salida_probabilistica.predecir_e3`` (S4_s2) y
``protocolo_arquitectura.evaluar`` (Platt cronológico).
"""

import json
import math
import time

import numpy as np
import pandas as pd

from denguekay.model import horizon_strategies as eh
from src.modeling import protocolo_arquitectura as pa
from denguekay.model import probabilistic_output as sp
from denguekay.model.train import PARAMETROS_BASE

FORMULACION = "S4_s2"
SEMILLA_XGB = 17
SEMILLA_TPE = 20261027
N_TRIALS = 100
TOP_K = 5
MAX_DELTA_STEP_POISSON = 0.7  # valor por defecto de XGBoost con count:poisson

# Hiperparámetros optimizables de la base (C3 con los valores fijos heredados), todos explícitos.
BASE = {"n_estimators": PARAMETROS_BASE["n_estimators"], "max_depth": PARAMETROS_BASE["max_depth"],
        "learning_rate": PARAMETROS_BASE["learning_rate"], "min_child_weight": PARAMETROS_BASE["min_child_weight"],
        "subsample": PARAMETROS_BASE["subsample"], "colsample_bytree": PARAMETROS_BASE["colsample_bytree"],
        "reg_lambda": PARAMETROS_BASE["reg_lambda"], "reg_alpha": 0.0, "gamma": 0.0,
        "max_delta_step": MAX_DELTA_STEP_POISSON}
# Trial 0 del estudio: la base con reg_alpha en el mínimo del espacio log (Optuna no admite 0 en escala log).
TRIAL_0 = {**BASE, "reg_alpha": 1e-3}

# (tipo, mínimo, máximo, log)
ESPACIO = {
    "max_depth": ("int", 2, 8, False),
    "min_child_weight": ("float", 1.0, 50.0, True),
    "learning_rate": ("float", 0.01, 0.3, True),
    "n_estimators": ("int", 100, 1500, False),
    "subsample": ("float", 0.5, 1.0, False),
    "colsample_bytree": ("float", 0.5, 1.0, False),
    "reg_lambda": ("float", 1e-3, 10.0, True),
    "reg_alpha": ("float", 1e-3, 10.0, True),
    "gamma": ("float", 0.0, 5.0, False),
    "max_delta_step": ("float", 0.3, 2.0, False),
}

PREREGISTRO_FASE3 = {
    "fecha": "2026-10-27, antes del estudio (aprobado por Rosa)",
    "matriz": "C3 = base_6 + B3 (elegida en la fase 2c)",
    "base": {"parametros": BASE, "nota": "PARAMETROS_BASE heredados; reg_alpha y gamma en 0 y max_delta_step 0,7 "
                                         "(los valores por defecto de XGBoost con count:poisson), explícitos"},
    "objetivo": "log-loss de probabilidad_calibrada (Poisson → binomial negativa con α dentro de la muestra → "
                "Platt cronológico), media sobre h=2/3/4 × temporadas 2022 y 2023; F1 a 0,50 y AUPRC se registran "
                "por trial, no se optimizan",
    "espacio": {k: {"tipo": t, "min": lo, "max": hi, "log": lg} for k, (t, lo, hi, lg) in ESPACIO.items()},
    "nota_max_delta_step": "rango 0,3–2 (lineal) en lugar de 0–2: con count:poisson, 0 significa sin límite y puede "
                           "volver inestable la optimización; el rango incluye el 0,7 de la base",
    "trial_0": {"parametros": TRIAL_0,
                "nota": "la base exacta usa reg_alpha = 0, que Optuna no admite en escala log; el trial 0 es la base con "
                        "reg_alpha = 1e-3, el punto más cercano del espacio. Medido antes del estudio (semilla 17): "
                        "objetivo 0,220007 igual al sexto decimal, F1 y AUPRC idénticos en las 6 celdas, diferencia "
                        "máxima de casos predichos 0,0024. La regla compara contra la base exacta (C3 de la 2c, "
                        "reg_alpha = 0); el trial 0 solo sitúa el arranque de la curva"},
    "estudio": {"muestreador": "TPE", "semilla_tpe": SEMILLA_TPE, "semilla_xgboost": SEMILLA_XGB,
                "n_trials": N_TRIALS, "trial_0": "TRIAL_0, encolado con enqueue_trial", "pruning": False,
                "early_stopping": False,
                "fallidos": "un trial que falla o da objetivo no finito queda como FAIL en Optuna y en MLflow y se reporta"},
    "seleccion": f"las {TOP_K} mejores por el objetivo se reentrenan con las 5 semillas; se elige la de mejor mediana "
                 "del objetivo; solo esa se compara con la regla simétrica contra la base (+1 comparación, 17 en total)",
    "adopcion": "gana → se adopta; empata → se queda la base salvo que la candidata sea igual o más simple "
                "(n_estimators × max_depth); pierde → se queda la base",
    "robustez_solo_lectura": "candidata final frente a la base sin las 8 primeras semanas de orígenes de 2017; signos "
                             "de F1 y antelación en 2022 y 2023",
    "limite": "la búsqueda usa las mismas temporadas de selección (2022–2023): las métricas de la candidata son "
              "optimistas; 2024 solo de contraste",
}


def sugerir(trial) -> dict:
    """Muestrea una configuración del espacio preregistrado."""
    params = {}
    for nombre, (tipo, lo, hi, log) in ESPACIO.items():
        if tipo == "int":
            params[nombre] = trial.suggest_int(nombre, lo, hi, log=log)
        else:
            params[nombre] = trial.suggest_float(nombre, lo, hi, log=log)
    return params


def logloss(y, p, eps: float = pa.EPS) -> float:
    y = np.asarray(y, float)
    p = np.clip(np.asarray(p, float), eps, 1 - eps)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def objetivo(evaluacion: dict, bloques: tuple[str, ...] = pa.BLOQUES_SELECCION) -> tuple[float, pd.DataFrame]:
    """Media del log-loss calibrado sobre h × temporadas de selección y la tabla por celda."""
    datos = evaluacion["datos"]
    datos = datos[datos.bloque.isin(bloques) & datos.probabilidad_calibrada.notna()]
    celdas = (datos.groupby(["horizonte", "bloque"])
              .apply(lambda g: logloss(g.brote, g.probabilidad_calibrada), include_groups=False)
              .rename("logloss").reset_index())
    esperadas = len(eh.HORIZONTES_ESTRATEGIA) * len(bloques)
    if len(celdas) != esperadas:
        return float("nan"), celdas
    return float(celdas.logloss.mean()), celdas


def evaluar_configuracion(matrices, serie, origenes, columnas, params: dict, semilla: int = SEMILLA_XGB) -> dict:
    """Predicción E3·S4_s2 con ``params`` y evaluación completa del protocolo."""
    pred = sp.predecir_e3(matrices, semilla, FORMULACION, columnas=columnas, origenes=origenes, hiperparametros=params)
    return pa.evaluar(pred, serie, sp.FORMULACIONES[FORMULACION]["calibracion"]) | {"predicciones": pred}


def resumen_trial(evaluacion: dict) -> dict:
    """Objetivo y métricas por celda que se guardan en cada trial."""
    valor, celdas = objetivo(evaluacion)
    met = evaluacion["metricas"].set_index(["horizonte", "bloque"])
    salida = {"objetivo": valor}
    for _, c in celdas.iterrows():
        sufijo = f"h{int(c.horizonte)}_{c.bloque.replace('temporada_', '')}"
        salida[f"logloss_{sufijo}"] = float(c.logloss)
    for (h, b), fila in met.iterrows():
        if b in (*pa.BLOQUES_SELECCION, pa.BLOQUE_CONTRASTE):
            sufijo = f"h{int(h)}_{b.replace('temporada_', '')}"
            salida[f"f1_050_{sufijo}"] = float(fila.f1_050)
            salida[f"auprc_{sufijo}"] = float(fila.auprc)
    return salida


def estudio(matrices, serie, origenes, columnas, storage: str, nombre: str = "fase3_c3",
            n_trials: int = N_TRIALS):
    """Corre (o reanuda) el estudio TPE preregistrado hasta ``n_trials`` trials en total."""
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    st = optuna.create_study(study_name=nombre, storage=storage, direction="minimize", load_if_exists=True,
                             sampler=optuna.samplers.TPESampler(seed=SEMILLA_TPE))
    if not st.trials:
        st.enqueue_trial(TRIAL_0, user_attrs={"es_base": True})

    def funcion(trial):
        params = sugerir(trial)
        inicio = time.perf_counter()
        r = resumen_trial(evaluar_configuracion(matrices, serie, origenes, columnas, params))
        trial.set_user_attr("segundos", time.perf_counter() - inicio)
        for k, v in r.items():
            if k != "objetivo":
                trial.set_user_attr(k, v)
        return r["objetivo"] if math.isfinite(r["objetivo"]) else float("nan")

    # El trial encolado (WAITING) no cuenta como hecho hasta que se ejecuta.
    hechos = sum(t.state != optuna.trial.TrialState.WAITING for t in st.trials)
    restantes = n_trials - hechos
    if restantes > 0:
        st.optimize(funcion, n_trials=restantes, catch=(Exception,))
    return st


def tabla_trials(st) -> pd.DataFrame:
    """Un trial por fila: número, estado, objetivo, parámetros, segundos y métricas."""
    filas = []
    for t in st.trials:
        filas.append({"numero": t.number, "estado": t.state.name, "objetivo": t.value,
                      "es_base": bool(t.user_attrs.get("es_base", False)),
                      **{f"param_{k}": v for k, v in t.params.items()}, **t.user_attrs})
    return pd.DataFrame(filas)


def top_k(st, k: int = TOP_K) -> list:
    """Las ``k`` mejores configuraciones completas por objetivo (excluye la base encolada)."""
    import optuna

    completas = [t for t in st.trials if t.state == optuna.trial.TrialState.COMPLETE
                 and math.isfinite(t.value) and not t.user_attrs.get("es_base", False)]
    return sorted(completas, key=lambda t: t.value)[:k]


def complejidad(params: dict) -> int:
    """Árboles × profundidad: criterio de simplicidad de la adopción."""
    return int(params["n_estimators"]) * int(params["max_depth"])


def adoptar(veredictos: pd.DataFrame, candidata: dict, base: dict = BASE) -> dict:
    """Regla de adopción preregistrada a partir de los veredictos por horizonte (candidata frente a base)."""
    resultado = eh.adopcion(veredictos).resultado.iloc[0]
    if resultado == "adoptable":
        return {"adoptada": "candidata", "criterio": "gana a la base"}
    if resultado == "empate" and complejidad(candidata) <= complejidad(base):
        return {"adoptada": "candidata", "criterio": "empata y es igual o más simple que la base"}
    if resultado == "empate":
        return {"adoptada": "base", "criterio": "empata y la candidata es más compleja"}
    return {"adoptada": "base", "criterio": "la candidata pierde en algún horizonte"}


def medir_configuracion(matrices, serie, origenes, columnas, params: dict, repeticiones: int = 2) -> pd.DataFrame:
    """Segundos de un trial completo (5 bloques, 1 semilla y protocolo) para una configuración."""
    filas = []
    for i in range(repeticiones):
        inicio = time.perf_counter()
        evaluar_configuracion(matrices, serie, origenes, columnas, params)
        filas.append({"repeticion": i + 1, "segundos": time.perf_counter() - inicio})
    return pd.DataFrame(filas)


def huella_trials(trials: pd.DataFrame) -> str:
    """Huella del estudio para MLflow: parámetros, estados y objetivos de todos los trials."""
    import hashlib

    columnas = ["numero", "estado", "objetivo", *sorted(c for c in trials if c.startswith("param_"))]
    texto = trials[columnas].sort_values("numero").to_json(orient="records", double_precision=15)
    return hashlib.sha256((texto + json.dumps(PREREGISTRO_FASE3, sort_keys=True, default=str)).encode()).hexdigest()


def huella_top(mejores: list) -> str:
    """Huella de las mejores configuraciones (número y parámetros): la selección se recalcula solo si cambian."""
    import hashlib

    texto = json.dumps([[t.number, t.params] for t in mejores], sort_keys=True, default=float)
    return hashlib.sha256((texto + json.dumps(PREREGISTRO_FASE3, sort_keys=True, default=str)).encode()).hexdigest()


def figura_curva(trials: pd.DataFrame, valor_base: float):
    """Objetivo por trial y mejor acumulado; el trial 0 marcado y la base exacta como línea."""
    import matplotlib.pyplot as plt

    t = trials.sort_values("numero")
    ok = t[t.estado.eq("COMPLETE")]
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.scatter(ok.numero, ok.objetivo, s=14, color="#0072B2", alpha=0.6, label="Trial")
    ax.plot(ok.numero, ok.objetivo.cummin(), color="#D55E00", label="Mejor acumulado")
    cero = ok[ok.es_base]
    ax.scatter(cero.numero, cero.objetivo, s=60, marker="D", color="#009E73", label="Trial 0 (base, reg_alpha = 1e-3)")
    ax.axhline(valor_base, color="grey", linestyle="--", linewidth=1, label="Base exacta (reg_alpha = 0, 5 semillas)")
    fallidos = t[t.estado.ne("COMPLETE")]
    if len(fallidos):
        ax.scatter(fallidos.numero, [valor_base] * len(fallidos), marker="x", color="black", label="Fallido")
    ax.set_xlabel("Trial")
    ax.set_ylabel("Log-loss calibrado (media h=2/3/4 × 2022–2023)")
    ax.set_title("Curva de optimización TPE, E3·S4_s2 con C3")
    ax.legend(fontsize=8)
    fig.tight_layout()
    return fig


def figura_importancia(importancia: dict[str, float]):
    """Importancia de hiperparámetros (fANOVA de Optuna)."""
    import matplotlib.pyplot as plt

    s = pd.Series(importancia).sort_values()
    fig, ax = plt.subplots(figsize=(7, 0.4 * len(s) + 1.5))
    ax.barh(s.index, s.values, color="#0072B2")
    ax.set_xlabel("Importancia relativa en el objetivo")
    ax.set_title("Importancia de hiperparámetros (fANOVA)")
    fig.tight_layout()
    return fig
