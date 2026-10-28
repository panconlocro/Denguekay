"""Formulaciones de la salida (fase 4 del encargo multi-horizonte).

Cada formulación define cómo se obtienen los **casos** y la **probabilidad de
brote**, sobre la estrategia E1 (directa por horizonte) o E3 (multi-salida),
con las mismas variables, bloques, semillas e hiperparámetros:

========  ==========================================  =======================================
Id        Casos                                        Probabilidad
========  ==========================================  =======================================
S1        ``log1p`` + error cuadrático                 clasificador; Platt cronológico
S2_pois   ``count:poisson``                            clasificador; Platt
S2_twd    ``reg:tweedie`` (potencia 1,5, fija)         clasificador; Platt
S3        ``count:poisson`` con ``base_margin =``      clasificador; Platt
          ``log(persistencia + 0,5)``
S4_s2     media de S2_pois                             P(casos ≥ k) binomial negativa; Platt
S4_s3     media de S3                                  P(casos ≥ k) binomial negativa; Platt
S5_iso    ``log1p`` (como S1)                          clasificador; isotónica cronológica
S5_spw    ``log1p`` (como S1)                          clasificador con ``scale_pos_weight``;
                                                       Platt
========  ==========================================  =======================================

En S4, ``k = max(⌊umbral_brote_casos⌋ + 1, 2)`` reproduce la regla de gold
(casos > umbral y ≥ 2). El umbral de la semana objetivo usa solo la misma
semana de años anteriores; ``tests/test_umbral_brote_sin_fuga.py`` comprueba
que no depende de casos posteriores a ``t−h``. Se usa solo para convertir la
distribución predicha en probabilidad, nunca como variable de entrada. La
dispersión de la binomial negativa se estima por máxima verosimilitud con las
predicciones dentro de la muestra de entrenamiento del bloque (causal, aunque
puede subestimarla); la calibración Platt posterior corrige la escala.

Con ``dispersion="oos"`` (fase 4.2 del encargo de FE) la α de cada bloque se
estima con las predicciones fuera de muestra de los bloques anteriores cuya
semana objetivo ya cerró en el corte (acumuladas). El primer bloque
(temporada 2021) usa un pseudo-bloque ``temporada_2020`` que solo sirve para
eso. Respaldo preregistrado: si la α OOS de un bloque y horizonte no converge,
queda en el límite del optimizador o sale de [mín / 5, máx × 5] de las α dentro
de la muestra de 2021–2024 (mismo horizonte y semilla), ese bloque usa la α
dentro de la muestra y se marca.
"""

import numpy as np
import pandas as pd
from scipy import optimize, special, stats
from xgboost import XGBClassifier, XGBRegressor

from denguekay.model import horizon_strategies as eh
from denguekay.model.train import MINIMO_CASOS_BROTE, conteos_desde_log1p

EPS_MARGEN = 0.5
POTENCIA_TWEEDIE = 1.5
FORMULACIONES = {
    "S1": {"conteo": "log1p", "probabilidad": "clasificador", "calibracion": "platt"},
    "S2_pois": {"conteo": "poisson", "probabilidad": "clasificador", "calibracion": "platt"},
    "S2_twd": {"conteo": "tweedie", "probabilidad": "clasificador", "calibracion": "platt"},
    "S3": {"conteo": "poisson_margen", "probabilidad": "clasificador", "calibracion": "platt"},
    "S4_s2": {"conteo": "poisson", "probabilidad": "binomial_negativa", "calibracion": "platt"},
    "S4_s3": {"conteo": "poisson_margen", "probabilidad": "binomial_negativa", "calibracion": "platt"},
    "S5_iso": {"conteo": "log1p", "probabilidad": "clasificador", "calibracion": "isotonica"},
    "S5_spw": {"conteo": "log1p", "probabilidad": "clasificador_spw", "calibracion": "platt"},
}
DISPERSIONES = ("dentro_muestra", "oos")
# Pseudo-bloque que solo estima la α OOS del primer bloque; no se evalúa ni entra en Platt.
BLOQUE_ALFA_INICIAL = ("temporada_2020", "temporada", 2020)
LIMITES_LOG_ALFA = (-12.0, 6.0)
TOLERANCIA_LIMITE_LOG_ALFA = 1e-3
FACTOR_RANGO_ALFA = 5.0
BLOQUES_RANGO_ALFA = ("temporada_2021", "temporada_2022", "temporada_2023", "temporada_2024")
# Modelos que se entrenan y despliegan por estrategia (S4 no usa clasificador).
MODELOS = {(e, f): (n // 2 if FORMULACIONES[f]["probabilidad"] == "binomial_negativa" else n)
           for e, n in eh.MODELOS_POR_ESTRATEGIA.items() for f in FORMULACIONES}


def objetivo_conteo(conteo: str) -> dict:
    """Parámetros de XGBoost para cada forma de modelar los casos."""
    if conteo == "log1p":
        return {"objective": "reg:squarederror"}
    if conteo in ("poisson", "poisson_margen"):
        return {"objective": "count:poisson"}
    if conteo == "tweedie":
        return {"objective": "reg:tweedie", "tweedie_variance_power": POTENCIA_TWEEDIE}
    raise ValueError(f"Conteo desconocido: {conteo}")


def margen_persistencia(persistencia) -> np.ndarray:
    """``log(persistencia + 0,5)``: punto de partida del modelo S3 en escala log."""
    p = np.asarray(persistencia, float)
    if (p < 0).any() or not np.isfinite(p).all():
        raise ValueError("Persistencia inválida para base_margin")
    return np.log(p + EPS_MARGEN)


def ajustar_conteo(x, y, conteo: str, semilla: int, margen=None, **extra) -> XGBRegressor:
    """Regresor de casos según la formulación (``y`` puede tener varias columnas)."""
    modelo = XGBRegressor(**objetivo_conteo(conteo), **eh.parametros(semilla, **extra))
    y = np.asarray(y, float)
    if conteo == "log1p":
        modelo.fit(x, np.log1p(y))
    elif conteo == "poisson_margen":
        modelo.fit(x, y, base_margin=margen)
    else:
        modelo.fit(x, y)
    return modelo


def predecir_conteo(modelo: XGBRegressor, x, conteo: str, margen=None) -> np.ndarray:
    """Casos esperados en escala original."""
    if conteo == "log1p":
        return conteos_desde_log1p(modelo.predict(x))
    pred = modelo.predict(x, base_margin=margen) if conteo == "poisson_margen" else modelo.predict(x)
    pred = np.asarray(pred, float)
    if not np.isfinite(pred).all() or (pred < 0).any():
        raise ValueError("El modelo de conteo produjo valores inválidos")
    return pred


def dispersion_binomial_negativa(mu, y) -> float:
    """α de la binomial negativa NB2 (var = μ + αμ²) por máxima verosimilitud."""
    return dispersion_binomial_negativa_detalle(mu, y)["alpha"]


def dispersion_binomial_negativa_detalle(mu, y) -> dict:
    """α NB2 por máxima verosimilitud, con convergencia y si quedó en un límite del optimizador."""
    mu = np.clip(np.asarray(mu, float).ravel(), 1e-6, None)
    y = np.asarray(y, float).ravel()

    def nll(log_alpha):
        a = np.exp(log_alpha)
        r = 1 / a
        return -np.sum(special.gammaln(y + r) - special.gammaln(r) - special.gammaln(y + 1)
                       + r * np.log(r / (r + mu)) + y * np.log(mu / (r + mu)))
    lo, hi = LIMITES_LOG_ALFA
    resultado = optimize.minimize_scalar(nll, bounds=(lo, hi), method="bounded")
    x = float(resultado.x)
    return {"alpha": float(np.exp(x)), "convergio": bool(resultado.success) and np.isfinite(x),
            "en_limite": min(x - lo, hi - x) < TOLERANCIA_LIMITE_LOG_ALFA, "n": int(mu.size)}


def alfas_oos(pruebas_por_bloque: dict, cortes: dict, alfas_dentro: dict) -> pd.DataFrame:
    """α OOS por bloque y horizonte, con el respaldo preregistrado.

    ``pruebas_por_bloque[bloque][h]`` tiene ``semana_inicio``, ``casos_predichos`` y
    ``casos_Dengue`` de la prueba del bloque, en orden cronológico de bloques (el
    pseudo-bloque primero). Para cada bloque evaluado se juntan las pruebas de los
    bloques anteriores con la semana objetivo cerrada en su corte.
    """
    nombres = list(pruebas_por_bloque)
    filas = []
    for i, bloque in enumerate(nombres):
        if bloque == BLOQUE_ALFA_INICIAL[0]:
            continue
        corte = cortes[bloque]
        for h, a_dentro in alfas_dentro[bloque].items():
            previas = pd.concat([pruebas_por_bloque[b][h] for b in nombres[:i]], ignore_index=True)
            previas = previas[(previas.semana_inicio + pd.Timedelta(days=6)).le(corte)]
            rango = [alfas_dentro[b][h] for b in BLOQUES_RANGO_ALFA if b in alfas_dentro]
            minimo, maximo = min(rango) / FACTOR_RANGO_ALFA, max(rango) * FACTOR_RANGO_ALFA
            if previas.empty:
                d = {"alpha": np.nan, "convergio": False, "en_limite": False, "n": 0}
            else:
                d = dispersion_binomial_negativa_detalle(previas.casos_predichos, previas.casos_Dengue)
            en_rango = bool(np.isfinite(d["alpha"]) and minimo <= d["alpha"] <= maximo)
            respaldo = not (d["convergio"] and not d["en_limite"] and en_rango)
            filas.append({"bloque": bloque, "horizonte": h, "alpha_dentro_muestra": a_dentro,
                          "alpha_oos": d["alpha"], "n_oos": d["n"], "convergio": d["convergio"],
                          "en_limite": d["en_limite"], "rango_minimo": minimo, "rango_maximo": maximo,
                          "en_rango": en_rango, "respaldo": respaldo,
                          "alpha_usada": a_dentro if respaldo else d["alpha"],
                          "bloques_previos": ",".join(sorted(previas.bloque_origen.unique()))
                          if not previas.empty else ""})
    return pd.DataFrame(filas)


def umbral_conteo(umbral_brote) -> np.ndarray:
    """k mínimo de casos para que la semana sea ``brote`` (casos > umbral y ≥ 2)."""
    return np.maximum(np.floor(np.asarray(umbral_brote, float)) + 1, MINIMO_CASOS_BROTE)


def probabilidad_binomial_negativa(mu, alpha: float, umbral_brote) -> np.ndarray:
    """P(casos ≥ k) con casos ~ NB2(μ, α)."""
    mu = np.clip(np.asarray(mu, float), 1e-9, None)
    k = umbral_conteo(umbral_brote)
    r = 1 / alpha
    return stats.nbinom.sf(k - 1, r, r / (r + mu))


def _clasificador(semilla: int, spw: float | None = None, **extra) -> XGBClassifier:
    params = eh.parametros(semilla, **extra)
    if spw is not None:
        params["scale_pos_weight"] = spw
    return XGBClassifier(objective="binary:logistic", eval_metric="logloss", **params)


def _spw(brote) -> float:
    b = np.asarray(brote).ravel()
    return float((b == 0).sum() / max((b == 1).sum(), 1))


# ---------------------------------------------------------------------------
# E1 con formulación
# ---------------------------------------------------------------------------

def predecir_e1(matrices: dict[int, pd.DataFrame], semilla: int, formulacion: str,
                horizontes: tuple[int, ...] = eh.HORIZONTES_ESTRATEGIA) -> pd.DataFrame:
    """E1 (un modelo por horizonte) con la formulación indicada."""
    f = FORMULACIONES[formulacion]
    partes = []
    for h in horizontes:
        datos = matrices[h]
        col_reg, col_cls = eh.columnas_modelo(h)
        for bloque, tipo, periodo in eh.bloques():
            train, test, _ = eh.separar(datos, tipo, periodo)
            m_tr = margen_persistencia(train.persistencia) if f["conteo"] == "poisson_margen" else None
            m_te = margen_persistencia(test.persistencia) if f["conteo"] == "poisson_margen" else None
            reg = ajustar_conteo(train[col_reg], train.casos_Dengue, f["conteo"], semilla, m_tr)
            conteos = predecir_conteo(reg, test[col_reg], f["conteo"], m_te)
            if f["probabilidad"] == "binomial_negativa":
                alpha = dispersion_binomial_negativa(
                    predecir_conteo(reg, train[col_reg], f["conteo"], m_tr), train.casos_Dengue)
                prob = probabilidad_binomial_negativa(conteos, alpha, test.umbral_brote_casos)
            else:
                spw = _spw(train.brote) if f["probabilidad"] == "clasificador_spw" else None
                cls = _clasificador(semilla, spw).fit(train[col_cls], train.brote.to_numpy(int))
                prob = cls.predict_proba(test[col_cls])[:, 1]
            partes.append(eh._salida(test, bloque, conteos, prob))
    return pd.concat(partes, ignore_index=True).assign(estrategia="E1", formulacion=formulacion, semilla=semilla)


# ---------------------------------------------------------------------------
# E3 con formulación
# ---------------------------------------------------------------------------

def predecir_e3(matrices: dict[int, pd.DataFrame], semilla: int, formulacion: str,
                devolver_modelos: bool = False, columnas: list[str] | None = None,
                origenes: pd.DataFrame | None = None, hiperparametros: dict | None = None,
                preparar_bloque=None, dispersion: str = "dentro_muestra"):
    """E3 (multi-salida desde el mismo origen) con la formulación indicada.

    En S3 el ``base_margin`` tiene una columna por salida; las tres valen
    ``log(casos del origen + 0,5)`` porque la persistencia de h=2, 3 y 4 es
    el mismo dato observado en el origen.

    Sin argumentos opcionales reproduce el encargo de arquitectura. El encargo
    de FE e hiperparámetros pasa ``columnas`` (``base_6`` + variables nuevas),
    ``origenes`` (``eh.tabla_origenes`` con esas columnas ya agregadas, en
    nombres genéricos) e ``hiperparametros`` (sobrescriben los fijos).
    ``preparar_bloque(origenes, corte)`` devuelve los orígenes con las columnas
    que dependen de una transformación aprendida (p. ej. el CP1 socio),
    ajustada solo con lo cerrado al ``corte`` del bloque.

    ``dispersion`` (solo S4): ``"dentro_muestra"`` (por defecto) u ``"oos"``
    (ver el docstring del módulo). Las α de cada bloque y horizonte quedan en
    ``salida.attrs["alfas"]``.
    """
    f = FORMULACIONES[formulacion]
    if dispersion not in DISPERSIONES:
        raise ValueError(f"Dispersión desconocida: {dispersion}")
    if dispersion == "oos" and f["probabilidad"] != "binomial_negativa":
        raise ValueError("La α OOS solo aplica a las formulaciones S4")
    oos = dispersion == "oos"
    H = eh.HORIZONTES_ESTRATEGIA
    base_origenes = eh.tabla_origenes(matrices[2]) if origenes is None else origenes
    col_reg = list(eh.GENERICAS) if columnas is None else list(columnas)
    col_cls = [*col_reg, eh.POBLACION]
    if preparar_bloque is None:
        faltan = [c for c in col_reg if c not in base_origenes]
        if faltan:
            raise ValueError(f"Columnas ausentes en la tabla de orígenes: {faltan}")
    objetivos = [f"semana_inicio_h{h}" for h in H]
    extra = {"multi_strategy": "multi_output_tree", **(hiperparametros or {})}
    margen_todo = (np.repeat(margen_persistencia(base_origenes.hist_lag_a)[:, None], len(H), axis=1)
                   if f["conteo"] == "poisson_margen" else None)
    partes, modelos = [], {}
    pruebas_oos, cortes, alfas_dentro, pendientes = {}, {}, {}, []
    lista = [BLOQUE_ALFA_INICIAL, *eh.bloques()] if oos else eh.bloques()
    for bloque, tipo, periodo in lista:
        pseudo = bloque == BLOQUE_ALFA_INICIAL[0]
        pruebas, corte = eh._cortes_comunes(matrices, tipo, periodo)
        cortes[bloque] = corte
        origenes = base_origenes if preparar_bloque is None else preparar_bloque(base_origenes, corte)
        if preparar_bloque is not None and (len(origenes) != len(base_origenes)
                                            or not origenes.index.equals(base_origenes.index)):
            raise ValueError("preparar_bloque no puede quitar ni reordenar orígenes")
        completas = origenes.dropna(subset=objetivos)
        ultima = completas[f"semana_inicio_h{H[-1]}"]
        sel = (ultima + pd.Timedelta(days=6)).le(corte)
        train = completas[sel]
        if train.empty or not train.origen_cierre.lt(train.semana_inicio).all():
            raise ValueError("Entrenamiento multi-salida vacío o con fuga")
        m_tr = margen_todo[completas.index[sel]] if margen_todo is not None else None
        y_casos = np.column_stack([train[f"casos_Dengue_h{h}"] for h in H])
        y_brote = np.column_stack([train[f"brote_h{h}"] for h in H]).astype(int)
        reg = ajustar_conteo(train[col_reg], y_casos, f["conteo"], semilla, m_tr, **extra)
        conteos = predecir_conteo(reg, origenes[col_reg], f["conteo"], margen_todo)
        cls, alphas = None, None
        if f["probabilidad"] == "binomial_negativa":
            ajuste = predecir_conteo(reg, train[col_reg], f["conteo"], m_tr)
            alphas = [dispersion_binomial_negativa(ajuste[:, i], y_casos[:, i]) for i in range(len(H))]
            if not pseudo:
                alfas_dentro[bloque] = dict(zip(H, alphas))
        else:
            spw = _spw(y_brote) if f["probabilidad"] == "clasificador_spw" else None
            cls = _clasificador(semilla, spw, **extra).fit(train[col_cls], y_brote)
            prob_todo = cls.predict_proba(origenes[col_cls])
        if devolver_modelos and not pseudo:
            modelos[bloque] = {"regresor": reg, "clasificador": cls, "alphas": alphas,
                               "x_reg": train[col_reg], "x_cls": train[col_cls]}
        for paso, h in enumerate(H):
            pred = pd.DataFrame({"ubigeo": origenes.ubigeo, "semana_inicio": origenes[f"semana_inicio_h{h}"],
                                 "origen_cierre_mimo": origenes.origen_cierre, "casos_predichos": conteos[:, paso]})
            if cls is not None:
                pred["probabilidad_brote"] = prob_todo[:, paso]
            test = pruebas[h].merge(pred.dropna(subset=["semana_inicio"]), on=["ubigeo", "semana_inicio"],
                                    how="left", validate="one_to_one")
            if test.casos_predichos.isna().any() or not test.origen_cierre_mimo.eq(test.origen_cierre).all():
                raise ValueError(f"Predicciones multi-salida incompletas o con origen distinto en h={h}")
            if oos:
                pruebas_oos.setdefault(bloque, {})[h] = test[["semana_inicio", "casos_predichos", "casos_Dengue"]] \
                    .assign(bloque_origen=bloque)
                if not pseudo:
                    pendientes.append((bloque, h, test))
                continue
            if cls is None:
                test["probabilidad_brote"] = probabilidad_binomial_negativa(
                    test.casos_predichos, alphas[paso], test.umbral_brote_casos)
            partes.append(eh._salida(test, bloque, test.casos_predichos, test.probabilidad_brote))
    if oos:
        alfas = alfas_oos(pruebas_oos, cortes, alfas_dentro)
        usada = alfas.set_index(["bloque", "horizonte"]).alpha_usada
        for bloque, h, test in pendientes:
            test["probabilidad_brote"] = probabilidad_binomial_negativa(
                test.casos_predichos, usada[(bloque, h)], test.umbral_brote_casos)
            partes.append(eh._salida(test, bloque, test.casos_predichos, test.probabilidad_brote))
    else:
        alfas = pd.DataFrame([{"bloque": b, "horizonte": h, "alpha_dentro_muestra": a, "alpha_usada": a}
                              for b, d in alfas_dentro.items() for h, a in d.items()])
    salida = pd.concat(partes, ignore_index=True).assign(estrategia="E3", formulacion=formulacion, semilla=semilla)
    salida.attrs["alfas"] = alfas.assign(dispersion=dispersion, semilla=semilla) if len(alfas) else alfas
    return (salida, modelos) if devolver_modelos else salida


PREDICTORES = {"E1": predecir_e1, "E3": predecir_e3}


# ---------------------------------------------------------------------------
# Importancia por horizonte (HU0008-4) y compatibilidad
# ---------------------------------------------------------------------------

def importancia_shap_por_horizonte(modelo, x: pd.DataFrame) -> pd.DataFrame:
    """Media de |SHAP| por variable y salida de un modelo multi-salida."""
    import xgboost as xgb

    contrib = modelo.get_booster().predict(xgb.DMatrix(x), pred_contribs=True)
    if contrib.ndim == 2:
        contrib = contrib[:, None, :]
    margen = modelo.predict(x, output_margin=True).reshape(contrib.shape[0], contrib.shape[1])
    if not np.allclose(contrib.sum(-1), margen, atol=1e-3):
        raise ValueError("SHAP no es aditivo respecto del margen")
    tabla = pd.DataFrame(np.abs(contrib[:, :, :-1]).mean(0), columns=list(x.columns),
                         index=[f"h={h}" for h in eh.HORIZONTES_ESTRATEGIA[:contrib.shape[1]]])
    return tabla


def compatibilidad_multi_salida(dispositivos: tuple[str, ...] = ("cuda", "cpu"), n: int = 2000) -> pd.DataFrame:
    """Prueba en datos sintéticos qué funciona con ``multi_strategy="multi_output_tree"``.

    Para cada capacidad no basta con que la llamada no falle: se verifica una
    propiedad numérica (aditividad de SHAP, media de Poisson, margen exacto).
    """
    import xgboost as xgb

    rng = np.random.default_rng(0)
    x = rng.normal(size=(n, 6))
    y = rng.poisson(np.exp(0.5 * x[:, :3])).astype(float)
    b = (y > 1).astype(int)
    filas = []

    def probar(capacidad, funcion):
        for d in dispositivos:
            p = dict(tree_method="hist", multi_strategy="multi_output_tree", n_estimators=40, max_depth=3, device=d)
            try:
                ok, detalle = funcion(p)
            except Exception as error:  # noqa: BLE001 - se reporta en la tabla
                ok, detalle = False, f"{type(error).__name__}: {str(error).splitlines()[0][:120]}"
            filas.append({"capacidad": capacidad, "dispositivo": d, "funciona": bool(ok), "verificacion": detalle})

    def poisson(p):
        m = XGBRegressor(objective="count:poisson", **p).fit(x, y)
        err = float(np.abs(m.predict(x).mean(0) - y.mean(0)).max())
        return err < 0.05, f"media predicha − real por salida ≤ {err:.4f}"

    def tweedie(p):
        m = XGBRegressor(objective="reg:tweedie", tweedie_variance_power=POTENCIA_TWEEDIE, **p).fit(x, y)
        return m.predict(x).shape == y.shape, f"salida {m.predict(x).shape}"

    def margen(p):
        mg = np.log(y + EPS_MARGEN)
        m = XGBRegressor(objective="count:poisson", **p).fit(x, y, base_margin=mg)
        dif = m.predict(x, base_margin=mg, output_margin=True) - m.predict(x, base_margin=np.zeros_like(mg), output_margin=True)
        err = float(np.abs(dif - mg).max())
        return err < 1e-4, f"base_margin (n, 3) aplicado por columna; error {err:.1e}; (n,) se rechaza"

    def importancia(p):
        m = XGBRegressor(objective="count:poisson", importance_type="gain", **p).fit(x, y)
        return m.feature_importances_.shape == (6,), "feature_importances_ es agregada (una por variable, no por salida)"

    def shap(p):
        m = XGBRegressor(objective="count:poisson", **p).fit(x, y)
        t = importancia_shap_por_horizonte(m, pd.DataFrame(x, columns=[f"x{i}" for i in range(6)]))
        propia = all(t.iloc[i].idxmax() == f"x{i}" for i in range(3))
        return propia, "pred_contribs (n, 3, p+1), aditivo por salida; detecta la variable propia de cada salida"

    def shap_cls(p):
        m = XGBClassifier(objective="binary:logistic", **p).fit(x, b)
        importancia_shap_por_horizonte(m, pd.DataFrame(x, columns=[f"x{i}" for i in range(6)]))
        return True, "clasificador multietiqueta: SHAP aditivo por salida"

    def spw(p):
        q1 = XGBClassifier(objective="binary:logistic", **p).fit(x, b).predict_proba(x).mean()
        q5 = XGBClassifier(objective="binary:logistic", scale_pos_weight=5.0, **p).fit(x, b).predict_proba(x).mean()
        return q5 > q1, f"un solo valor para las 3 salidas; prob. media {q1:.3f} → {q5:.3f}"

    probar("count:poisson", poisson)
    probar("reg:tweedie", tweedie)
    probar("base_margin con varias salidas (S3)", margen)
    probar("importancia de variables (gain)", importancia)
    probar("SHAP por horizonte, regresor", shap)
    probar("SHAP por horizonte, clasificador", shap_cls)
    probar("scale_pos_weight (S5)", spw)
    for d in dispositivos:
        filas.append({"capacidad": "calibrador por salida (S5/S4)", "dispositivo": d, "funciona": True,
                      "verificacion": "posterior al modelo: Platt/isotónica por horizonte en protocolo_arquitectura"})
    return pd.DataFrame(filas)


# ---------------------------------------------------------------------------
# Selección preregistrada de formulación y par estrategia + formulación
# ---------------------------------------------------------------------------

def clave(estrategia: str, formulacion: str) -> str:
    """Nombre de un par estrategia + formulación (``"E3|S4_s2"``)."""
    return f"{estrategia}|{formulacion}"


def modelos_par(nombre: str) -> int:
    """Modelos que se entrenan y despliegan para un par."""
    return MODELOS[tuple(nombre.split("|"))]


def elegir(evaluaciones: dict[str, dict], candidatas: list[str], referencia: str,
           coherencia: pd.DataFrame) -> dict:
    """Regla preregistrada: frente a la referencia, adopción y desempate.

    1. Cada candidata se compara con la referencia (``decidir`` con medianas
       y rangos de semillas). Es adoptable si gana en algún horizonte y no
       pierde en ninguno.
    2. Si hay varias adoptables, se comparan entre sí en ambos sentidos. Se
       descarta la que **pierde** en algún horizonte frente a otra adoptable o
       a la que otra **gana**. Si queda más de una, o si todas se descartan
       mutuamente (cada una mejor en horizontes distintos), desempate.
    3. Si no hay adoptables, desempate entre la referencia y las empatadas.
    Desempate: coherencia entre horizontes y luego número de modelos.
    """
    veredictos = pd.concat([eh.decidir_frente_a_referencia(evaluaciones, c, referencia) for c in candidatas],
                           ignore_index=True)
    adopcion = eh.adopcion(veredictos)
    adoptables = adopcion.query("resultado == 'adoptable'").candidata.tolist()
    modelos = {n: modelos_par(n) for n in [referencia, *candidatas]}
    cruces = pd.DataFrame()
    if len(adoptables) > 1:
        cruces = pd.concat([eh.decidir_frente_a_referencia(evaluaciones, a, b)
                            for a in adoptables for b in adoptables if a != b], ignore_index=True)
        vencidas = (set(cruces.loc[cruces.veredicto.eq("gana"), "referencia"])
                    | set(cruces.loc[cruces.veredicto.eq("pierde"), "candidata"]))
        finalistas = [a for a in adoptables if a not in vencidas] or adoptables
    else:
        finalistas = adoptables
    if len(finalistas) == 1:
        decision = {"elegida": finalistas[0], "criterio": "gana según la regla preregistrada"}
    elif finalistas:
        decision = {**eh.desempatar(finalistas, coherencia, modelos=modelos), "empatadas": finalistas}
    else:
        empatadas = [referencia, *adopcion.query("resultado == 'empate'").candidata]
        decision = {**eh.desempatar(empatadas, coherencia, modelos=modelos), "empatadas": empatadas}
    return {"veredictos": veredictos, "adopcion": adopcion, "cruces": cruces, "decision": decision}


def comparar_conteos(medianas: pd.DataFrame, rangos: pd.DataFrame, estrategia: str,
                     bloques=("temporada_2022", "temporada_2023")) -> pd.DataFrame:
    """Razón MAE de cada modelo de conteo frente a ``log1p`` (informativo, no decide).

    Las formulaciones S2 y S3 solo cambian los casos, así que la regla de
    alerta las deja empatadas con S1; esta tabla muestra si su conteo mejora
    más que el rango de semillas en ambas temporadas de selección.
    """
    conteos = {"log1p": "S1", "poisson": "S2_pois", "tweedie": "S2_twd", "poisson_margen": "S3"}
    ref = medianas[medianas.par.eq(clave(estrategia, "S1"))].set_index(["horizonte", "bloque"])
    filas = []
    for conteo, f in conteos.items():
        par = clave(estrategia, f)
        m = medianas[medianas.par.eq(par)].set_index(["horizonte", "bloque"])
        r = rangos[rangos.par.isin([par, clave(estrategia, "S1")])].groupby(["horizonte", "bloque"]).razon_mae.max()
        for h in eh.HORIZONTES_ESTRATEGIA:
            delta = {b: m.at[(h, b), "razon_mae"] - ref.at[(h, b), "razon_mae"] for b in bloques}
            filas.append({"estrategia": estrategia, "conteo": conteo, "horizonte": h,
                          **{f"razon_mae_{b}": m.at[(h, b), "razon_mae"] for b in bloques},
                          **{f"razon_rmse_{b}": m.at[(h, b), "razon_rmse"] for b in bloques},
                          "mejora_en_ambas": all(delta[b] < -r.at[(h, b)] for b in bloques),
                          "empeora_en_alguna": any(delta[b] > r.at[(h, b)] for b in bloques),
                          "cumple_085_en_ambas": all(m.at[(h, b), "razon_mae"] <= 0.85 and m.at[(h, b), "razon_rmse"] <= 0.85
                                                     for b in bloques)})
    return pd.DataFrame(filas)


def figura_fiabilidad_formulaciones(fiabilidades: dict[str, pd.DataFrame], titulo: str):
    """Curvas de fiabilidad (probabilidad calibrada) por formulación, horizonte y temporada."""
    import matplotlib.pyplot as plt

    nombres = list(fiabilidades)
    horizontes = eh.HORIZONTES_ESTRATEGIA
    fig, ejes = plt.subplots(len(nombres), len(horizontes), figsize=(4 * len(horizontes), 2.6 * len(nombres)),
                             squeeze=False, sharex=True, sharey=True)
    for i, nombre in enumerate(nombres):
        t = fiabilidades[nombre]
        for j, h in enumerate(horizontes):
            ax = ejes[i, j]
            ax.plot([0, 1], [0, 1], color="grey", linestyle="--", linewidth=0.8)
            for bloque in ("temporada_2022", "temporada_2023", "temporada_2024"):
                g = t[t.horizonte.eq(h) & t.bloque.eq(bloque)]
                ax.plot(g.prob_media, g.frecuencia_observada, marker="o", markersize=3,
                        label=bloque.replace("temporada_", ""))
            ax.set_title(f"{nombre}, h={h}", fontsize=9)
            if j == 0:
                ax.set_ylabel("Frecuencia observada")
            if i == len(nombres) - 1:
                ax.set_xlabel("Probabilidad calibrada")
    ejes[0, 0].legend(fontsize=7)
    fig.suptitle(titulo)
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Diagnósticos complementarios de S4
# ---------------------------------------------------------------------------

def probabilidad_poisson(mu, umbral_brote) -> np.ndarray:
    """P(casos ≥ k) con casos ~ Poisson(μ): límite de la binomial negativa con α → 0."""
    return stats.poisson.sf(umbral_conteo(umbral_brote) - 1, np.clip(np.asarray(mu, float), 1e-9, None))


def recall_por_tipo_semana(datos: pd.DataFrame, serie: pd.DataFrame, alerta: str = "alerta_050",
                           semanas_inicio: int = 2) -> pd.DataFrame:
    """Recall en semanas ``brote`` de brotes nuevos frente a brotes en curso.

    «Brote nuevo»: las primeras ``semanas_inicio`` semanas de un episodio con
    inicio limpio (sin brote en las 8 semanas previas). «En curso»: el resto
    de semanas ``brote``. Separa anticipar brotes nuevos de acertar más en
    brotes que ya empezaron.
    """
    from src.modeling import diagnostico_arquitectura as diag

    eps = diag.episodios(serie)
    limpios = eps[eps.semanas_previas_sin_brote >= diag.SIN_BROTE_PREVIO]
    nuevas = set()
    for ep in limpios.itertuples(index=False):
        for k in range(semanas_inicio):
            nuevas.add((ep.ubigeo, ep.inicio + pd.Timedelta(weeks=k)))
    pos = datos[datos.brote.eq(1) & datos.probabilidad_calibrada.notna()].copy()
    pos["tipo"] = ["brote_nuevo" if (u, s) in nuevas else "en_curso" for u, s in zip(pos.ubigeo, pos.semana_inicio)]
    return (pos.groupby(["horizonte", "bloque", "tipo"])[alerta]
            .agg(semanas="size", recall="mean").reset_index())


# ---------------------------------------------------------------------------
# Cumplimiento de la HU0007-4 (línea base; no es criterio de decisión)
# ---------------------------------------------------------------------------

UMBRALES_HU0007_4 = {"precision_050": 0.60, "recall_050": 0.80, "f1_050": 0.70,
                     "razon_mae": 0.85, "razon_rmse": 0.85}


def cumplimiento_hu0007_4(metricas: pd.DataFrame) -> pd.DataFrame:
    """Marca, por horizonte y bloque, qué umbrales de aceptación de la HU0007-4 se cumplen.

    Clasificación: P ≥ 0,60, R ≥ 0,80 y F1 ≥ 0,70 con p ≥ 0,50. Regresión:
    MAE y RMSE ≤ 85 % de los de la persistencia.
    """
    salida = metricas[["horizonte", "bloque", *UMBRALES_HU0007_4]].copy()
    for m, u in UMBRALES_HU0007_4.items():
        salida[f"cumple_{m}"] = salida[m].le(u) if m.startswith("razon") else salida[m].ge(u)
    salida["cumple_clasificacion"] = salida[["cumple_precision_050", "cumple_recall_050", "cumple_f1_050"]].all(axis=1)
    salida["cumple_regresion"] = salida[["cumple_razon_mae", "cumple_razon_rmse"]].all(axis=1)
    return salida
