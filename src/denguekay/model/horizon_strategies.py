"""Estrategias multi-horizonte comparadas en la fase 3 del encargo.

Todas usan las matrices congeladas (``base_6`` para regresión de
``log1p(casos)`` y ``base_6_poblacion_2017`` para clasificación), los mismos
bloques temporales y los mismos hiperparámetros fijos; solo cambia cómo se
organiza el aprendizaje entre horizontes:

- **E1, directa por horizonte:** un regresor y un clasificador por h.
- **E2, directa agrupada:** un regresor y un clasificador para h ∈ {2,3,4},
  con filas apiladas, nombres genéricos de columnas y ``h`` como variable.
- **E3, multi-salida (MIMO):** desde cada origen, un modelo predice el vector
  (t+2, t+3, t+4) con ``multi_strategy="multi_output_tree"``.

Las matrices de horizontes ausentes en gold se construyen **en memoria** con
``features.construir_gold``; nada se escribe en ``data/``. E2 y E3 comparten
un único modelo por bloque para los tres horizontes, así que se entrenan con
las etiquetas cerradas antes del primer origen **más temprano** (el de h=4).
"""

import numpy as np
import pandas as pd
from xgboost import XGBClassifier, XGBRegressor

from src.modeling.features import construir_gold
from denguekay.model.train import (
    ANIO_PRUEBA_SENSIBILIDAD, MINIMO_CASOS_BROTE, PARAMETROS_BASE, conteos_desde_log1p,
    preparar_gold, separar_anio_calendario, separar_temporada,
)
from src.modeling.validacion_temporal_compacta import TEMPORADAS, variantes_compactas
from denguekay.data.validation.forecast_contract import CLAVE

HORIZONTES_ESTRATEGIA = (2, 3, 4)
HORIZONTES_CURVA = (1, 2, 3, 4, 5, 6)
REZAGO_ESTACIONAL = 52
GENERICAS = ["hist_lag_a", "hist_lag_b", "hist_media_4", "hist_semanas_pos_4",
             "semana_epi_seno", "semana_epi_coseno"]
POBLACION = "log_poblacion_censo_2017"
SALIDA = [*CLAVE, "semana_inicio", "origen_cierre", "horizonte", "bloque", "casos_Dengue",
          "brote", "umbral_brote_casos", "persistencia", "estacional"]
MODELOS_POR_ESTRATEGIA = {"E1": 2 * len(HORIZONTES_ESTRATEGIA), "E2": 2, "E3": 2}


# ---------------------------------------------------------------------------
# Matrices en memoria
# ---------------------------------------------------------------------------

def matriz_horizonte(panel: pd.DataFrame, etiquetas: pd.DataFrame, horizonte: int) -> pd.DataFrame:
    """Matriz modelable de un horizonte, construida en memoria y auditada.

    Usa ``construir_gold`` (mismo código que gold h=2/h=4) y ``preparar_gold``
    (mismas exclusiones de arranque y validación de origen). Agrega el
    ingenuo estacional: casos de la semana ``t − 52``, conocidos al origen.
    """
    gold = construir_gold(panel, horizonte, etiquetas, minimo_casos_brote=MINIMO_CASOS_BROTE)
    datos, _ = preparar_gold(gold, horizonte)
    if not datos.origen_cierre.lt(datos.semana_inicio).all():
        raise ValueError(f"Fuga temporal en la matriz h={horizonte}")
    serie = panel[CLAVE + ["semana_inicio", "casos_Dengue"]].copy()
    serie["semana_inicio"] = pd.to_datetime(serie.semana_inicio)
    serie = serie.sort_values(["ubigeo", "semana_inicio"])
    serie["estacional"] = serie.groupby("ubigeo").casos_Dengue.shift(REZAGO_ESTACIONAL)
    datos = datos.merge(serie[CLAVE + ["estacional"]], on=CLAVE, how="left", validate="one_to_one")
    datos["persistencia"] = datos[f"casos_lag_{horizonte}"]
    datos["horizonte"] = horizonte
    return datos


def columnas_modelo(horizonte: int) -> tuple[list[str], list[str]]:
    """Columnas congeladas de regresión y clasificación para un horizonte."""
    variantes = variantes_compactas(horizonte)
    return variantes["base_6"], variantes["base_6_poblacion_2017"]


def a_genericas(datos: pd.DataFrame, horizonte: int) -> pd.DataFrame:
    """Renombra las columnas de historia de un horizonte a nombres comunes."""
    reg, _ = columnas_modelo(horizonte)
    return datos.rename(columns=dict(zip(reg, GENERICAS)))


def bloques() -> list[tuple[str, str, int]]:
    """Bloques del protocolo: temporadas 2021–2024 y calendario 2025."""
    return [*((f"temporada_{t}", "temporada", t) for t in TEMPORADAS),
            (f"calendario_{ANIO_PRUEBA_SENSIBILIDAD}", "calendario", ANIO_PRUEBA_SENSIBILIDAD)]


def separar(datos: pd.DataFrame, tipo: str, periodo: int):
    """Corte temporal compartido con ``train.py``."""
    if tipo == "temporada":
        return separar_temporada(datos, periodo)
    return separar_anio_calendario(datos, periodo)


def parametros(semilla: int, **extra) -> dict:
    """Hiperparámetros fijos del encargo con la semilla indicada."""
    return {**PARAMETROS_BASE, "random_state": semilla, **extra}


def _salida(prueba: pd.DataFrame, bloque: str, conteos, probabilidad) -> pd.DataFrame:
    salida = prueba[[c for c in SALIDA if c != "bloque"]].copy()
    salida["bloque"] = bloque
    salida["casos_predichos"] = np.asarray(conteos, float)
    salida["probabilidad_brote"] = np.asarray(probabilidad, float)
    if not np.isfinite(salida[["casos_predichos", "probabilidad_brote"]].to_numpy()).all():
        raise ValueError("Predicciones no finitas")
    return salida[SALIDA + ["casos_predichos", "probabilidad_brote"]]


def _ajustar(x_reg, x_cls, y_casos, y_brote, semilla: int, **extra):
    reg = XGBRegressor(objective="reg:squarederror", **parametros(semilla, **extra))
    cls = XGBClassifier(objective="binary:logistic", eval_metric="logloss", **parametros(semilla, **extra))
    reg.fit(x_reg, np.log1p(np.asarray(y_casos, float)))
    cls.fit(x_cls, np.asarray(y_brote, int))
    return reg, cls


# ---------------------------------------------------------------------------
# E1: directa por horizonte
# ---------------------------------------------------------------------------

def predecir_e1(matrices: dict[int, pd.DataFrame], semilla: int,
                horizontes: tuple[int, ...] | None = None) -> pd.DataFrame:
    """Un regresor y un clasificador por horizonte y bloque."""
    partes = []
    for h in horizontes or sorted(matrices):
        datos = matrices[h]
        col_reg, col_cls = columnas_modelo(h)
        for bloque, tipo, periodo in bloques():
            train, test, _ = separar(datos, tipo, periodo)
            reg, cls = _ajustar(train[col_reg], train[col_cls], train.casos_Dengue, train.brote, semilla)
            partes.append(_salida(test, bloque, conteos_desde_log1p(reg.predict(test[col_reg])),
                                  cls.predict_proba(test[col_cls])[:, 1]))
    return pd.concat(partes, ignore_index=True).assign(estrategia="E1", semilla=semilla)


# ---------------------------------------------------------------------------
# E2: directa agrupada (filas apiladas con h como variable)
# ---------------------------------------------------------------------------

def _cortes_comunes(matrices: dict[int, pd.DataFrame], tipo: str, periodo: int):
    """Pruebas por horizonte y el corte más temprano entre ellos."""
    pruebas, cortes = {}, []
    for h in HORIZONTES_ESTRATEGIA:
        _, test, corte = separar(matrices[h], tipo, periodo)
        pruebas[h] = test
        cortes.append(corte)
    return pruebas, min(cortes)


def apilar_entrenamiento(matrices: dict[int, pd.DataFrame], corte: pd.Timestamp) -> pd.DataFrame:
    """Filas de los tres horizontes con etiqueta cerrada al corte, en nombres genéricos."""
    partes = []
    for h in HORIZONTES_ESTRATEGIA:
        datos = matrices[h]
        cerradas = datos[(datos.semana_inicio + pd.Timedelta(days=6)).le(corte)]
        if not cerradas.origen_cierre.lt(cerradas.semana_inicio).all():
            raise ValueError("Fuga temporal en filas apiladas")
        partes.append(a_genericas(cerradas, h))
    apiladas = pd.concat(partes, ignore_index=True)
    if apiladas.brote.nunique() < 2:
        raise ValueError("Entrenamiento apilado sin dos clases")
    return apiladas


def predecir_e2(matrices: dict[int, pd.DataFrame], semilla: int) -> pd.DataFrame:
    """Un regresor y un clasificador por bloque para h=2, 3 y 4 juntos."""
    col_reg, col_cls = [*GENERICAS, "horizonte"], [*GENERICAS, POBLACION, "horizonte"]
    partes = []
    for bloque, tipo, periodo in bloques():
        pruebas, corte = _cortes_comunes(matrices, tipo, periodo)
        train = apilar_entrenamiento(matrices, corte)
        if train.semana_inicio.max() >= min(t.semana_inicio.min() for t in pruebas.values()):
            raise ValueError("El entrenamiento apilado alcanza semanas de prueba")
        reg, cls = _ajustar(train[col_reg], train[col_cls], train.casos_Dengue, train.brote, semilla)
        for h, test in pruebas.items():
            g = a_genericas(test, h)
            partes.append(_salida(test, bloque, conteos_desde_log1p(reg.predict(g[col_reg])),
                                  cls.predict_proba(g[col_cls])[:, 1]))
    return pd.concat(partes, ignore_index=True).assign(estrategia="E2", semilla=semilla)


# ---------------------------------------------------------------------------
# E3: multi-salida desde el mismo origen
# ---------------------------------------------------------------------------

def tabla_origenes(matriz_h2: pd.DataFrame) -> pd.DataFrame:
    """Una fila por origen con predictores de h=2 y objetivos t+2, t+3 y t+4.

    La fila de h=2 con objetivo ``t`` tiene origen ``o = t − 2``; los
    objetivos de h=3 y h=4 son las semanas siguientes del mismo distrito.
    """
    datos = a_genericas(matriz_h2, 2).sort_values(["ubigeo", "semana_inicio"]).reset_index(drop=True)
    if not datos.groupby("ubigeo").semana_inicio.diff().dropna().dt.days.eq(7).all():
        raise ValueError("La matriz h=2 tiene semanas faltantes")
    grupo = datos.groupby("ubigeo")
    for paso, h in enumerate(HORIZONTES_ESTRATEGIA):
        for col in ("casos_Dengue", "brote", "semana_inicio"):
            datos[f"{col}_h{h}"] = grupo[col].shift(-paso)
    return datos


def predecir_e3(matrices: dict[int, pd.DataFrame], semilla: int) -> pd.DataFrame:
    """Un modelo multi-salida por tarea y bloque para el vector (h=2, 3, 4)."""
    origenes = tabla_origenes(matrices[2])
    col_reg, col_cls = list(GENERICAS), [*GENERICAS, POBLACION]
    objetivos = [f"semana_inicio_h{h}" for h in HORIZONTES_ESTRATEGIA]
    extra = {"multi_strategy": "multi_output_tree"}
    partes = []
    for bloque, tipo, periodo in bloques():
        pruebas, corte = _cortes_comunes(matrices, tipo, periodo)
        completas = origenes.dropna(subset=objetivos)
        ultima = completas[f"semana_inicio_h{HORIZONTES_ESTRATEGIA[-1]}"]
        train = completas[(ultima + pd.Timedelta(days=6)).le(corte)]
        if not train.origen_cierre.lt(train.semana_inicio).all() or train.empty:
            raise ValueError("Entrenamiento multi-salida vacío o con fuga")
        y_casos = np.column_stack([train[f"casos_Dengue_h{h}"] for h in HORIZONTES_ESTRATEGIA])
        y_brote = np.column_stack([train[f"brote_h{h}"] for h in HORIZONTES_ESTRATEGIA]).astype(int)
        reg, cls = _ajustar(train[col_reg], train[col_cls], y_casos, y_brote, semilla, **extra)
        conteos = conteos_desde_log1p(reg.predict(origenes[col_reg]))
        prob = cls.predict_proba(origenes[col_cls])
        for paso, h in enumerate(HORIZONTES_ESTRATEGIA):
            pred = pd.DataFrame({"ubigeo": origenes.ubigeo, "semana_inicio": origenes[f"semana_inicio_h{h}"],
                                 "origen_cierre_mimo": origenes.origen_cierre,
                                 "casos_predichos": conteos[:, paso], "probabilidad_brote": prob[:, paso]})
            test = pruebas[h].merge(pred.dropna(subset=["semana_inicio"]), on=["ubigeo", "semana_inicio"],
                                    how="left", validate="one_to_one")
            if test.casos_predichos.isna().any() or len(test) != len(pruebas[h]):
                raise ValueError(f"Faltan predicciones multi-salida para h={h}")
            if not test.origen_cierre_mimo.eq(test.origen_cierre).all():
                raise ValueError("El origen multi-salida no coincide con el horizonte")
            partes.append(_salida(test, bloque, test.casos_predichos, test.probabilidad_brote))
    return pd.concat(partes, ignore_index=True).assign(estrategia="E3", semilla=semilla)


ESTRATEGIAS = {"E1": predecir_e1, "E2": predecir_e2, "E3": predecir_e3}


# ---------------------------------------------------------------------------
# Coherencia entre horizontes
# ---------------------------------------------------------------------------

def coherencia_horizontes(datos: pd.DataFrame, serie: pd.DataFrame,
                          alerta: str = "alerta_050") -> pd.DataFrame:
    """Contradicciones de alerta entre h=4, h=3 y h=2 para la misma semana objetivo.

    Al pasar de h=k a h=k−1 se agrega un único dato nuevo: los casos de la
    semana ``w − k + 1``. Un cambio de alerta está **explicado** si ese dato
    se movió en el mismo sentido respecto de la semana anterior (sube → la
    alerta aparece; baja → desaparece). **Parpadeo**: la alerta cambia dos
    veces (sí–no–sí o no–sí–no) entre h=4, h=3 y h=2.
    """
    casos = serie[["ubigeo", "semana_inicio", "casos_Dengue"]].copy()
    casos["semana_inicio"] = pd.to_datetime(casos.semana_inicio)
    casos = casos.set_index(["ubigeo", "semana_inicio"]).casos_Dengue
    evaluables = datos[datos.horizonte.isin(HORIZONTES_ESTRATEGIA) & datos.probabilidad_calibrada.notna()]
    tabla = evaluables.pivot_table(
        index=["bloque", "ubigeo", "semana_inicio"], columns="horizonte", values=alerta, aggfunc="first")
    tabla = tabla.dropna().astype(bool).reset_index()
    filas = []
    for bloque, g in tabla.groupby("bloque"):
        cambios = np.zeros(len(g), int)
        sin_explicar = np.zeros(len(g), bool)
        for k in (4, 3):
            nuevo = g.semana_inicio - pd.to_timedelta(7 * (k - 1), unit="D")
            previo = nuevo - pd.Timedelta(days=7)
            delta = (casos.reindex(list(zip(g.ubigeo, nuevo))).to_numpy()
                     - casos.reindex(list(zip(g.ubigeo, previo))).to_numpy())
            antes, despues = g[k].to_numpy(), g[k - 1].to_numpy()
            aparece, desaparece = ~antes & despues, antes & ~despues
            cambios += aparece | desaparece
            sin_explicar |= (aparece & ~(delta > 0)) | (desaparece & ~(delta < 0))
        parpadeo = (g[4].to_numpy() != g[3].to_numpy()) & (g[3].to_numpy() != g[2].to_numpy())
        filas.append({"bloque": bloque, "semanas_objetivo": len(g),
                      "con_cambio": float((cambios > 0).mean()),
                      "cambio_sin_explicar": float(sin_explicar.mean()),
                      "parpadeo": float(parpadeo.mean()),
                      "alerta_h4_que_desaparece_en_h2": float((g[4] & ~g[2]).mean())})
    return pd.DataFrame(filas)


# ---------------------------------------------------------------------------
# Decisión preregistrada con desempate
# ---------------------------------------------------------------------------

def restringir_horizontes(evaluacion: dict, horizontes: tuple[int, ...] = HORIZONTES_ESTRATEGIA) -> dict:
    """Copia de una evaluación del protocolo con solo los horizontes indicados."""
    return {k: (v[v.horizonte.isin(horizontes)].reset_index(drop=True)
                if isinstance(v, pd.DataFrame) and "horizonte" in v else v)
            for k, v in evaluacion.items()}


def decidir_frente_a_referencia(evaluaciones: dict[str, dict[int, dict]], candidata: str,
                                referencia: str = "E1") -> pd.DataFrame:
    """Aplica ``protocolo_arquitectura.decidir`` con medianas y rangos de semillas.

    ``evaluaciones[estrategia][semilla]`` es la salida de ``protocolo.evaluar``.
    La antelación usa la diferencia pareada de la semilla de referencia y,
    además, exige que la diferencia de medianas entre semillas tenga el
    mismo signo; si no, se anula la mejora o el empeoramiento.
    """
    from src.modeling import protocolo_arquitectura as pa

    met = {e: [evaluaciones[e][s]["metricas"] for s in evaluaciones[e]] for e in (candidata, referencia)}
    rangos = pa.umbral_empate(pa.rangos_semillas(met[candidata]), pa.rangos_semillas(met[referencia]))
    semilla = pa.SEMILLAS[0]
    dif = pa.diferencia_antelacion(evaluaciones[candidata][semilla]["antelacion"],
                                   evaluaciones[referencia][semilla]["antelacion"], "alerta_050")
    medianas = {}
    for e in (candidata, referencia):
        tabla = pd.concat([evaluaciones[e][s]["antelacion_ic"].query(
            "alerta == 'alerta_050' and bloque == 'seleccion_2022_2023'") for s in evaluaciones[e]])
        medianas[e] = tabla.groupby("horizonte").avisados_2_o_mas.median()
    signo = np.sign(medianas[candidata] - medianas[referencia]).rename("signo_mediana_antelacion")
    dif = dif.merge(signo, left_on="horizonte", right_index=True)
    # Si la mediana de semillas no acompaña, el IC de la semilla de referencia no cuenta.
    contradice_mejora = dif.signo_mediana_antelacion <= 0
    dif.loc[contradice_mejora, "ic95_inferior"] = np.minimum(dif.loc[contradice_mejora, "ic95_inferior"], 0)
    contradice_caida = dif.signo_mediana_antelacion >= 0
    dif.loc[contradice_caida, "ic95_superior"] = np.maximum(dif.loc[contradice_caida, "ic95_superior"], 0)
    veredicto = pa.decidir(pa.mediana_semillas(met[candidata]), pa.mediana_semillas(met[referencia]),
                           rangos, dif)
    return veredicto.assign(candidata=candidata, referencia=referencia).merge(
        dif[["horizonte", "diferencia", "ic95_inferior", "ic95_superior", "signo_mediana_antelacion"]]
        .rename(columns=lambda c: c if c == "horizonte" else f"antelacion_{c}"), on="horizonte")


def adopcion(veredictos: pd.DataFrame) -> pd.DataFrame:
    """Una candidata se adopta si gana en algún horizonte y no pierde en ninguno."""
    filas = []
    for candidata, g in veredictos.groupby("candidata"):
        gana = g.veredicto.eq("gana").any()
        pierde = g.veredicto.eq("pierde").any()
        filas.append({"candidata": candidata, "gana_en": ", ".join(f"h={h}" for h in g.horizonte[g.veredicto.eq("gana")]) or None,
                      "pierde_en": ", ".join(f"h={h}" for h in g.horizonte[g.veredicto.eq("pierde")]) or None,
                      "resultado": "adoptable" if gana and not pierde else ("descartada" if pierde else "empate")})
    return pd.DataFrame(filas)


def resumen_coherencia(coherencias: dict[str, list[pd.DataFrame]]) -> pd.DataFrame:
    """Mediana y rango entre semillas de los cambios sin explicar por estrategia y bloque."""
    filas = []
    for estrategia, tablas in coherencias.items():
        todas = pd.concat(tablas, ignore_index=True)
        for bloque, g in todas.groupby("bloque"):
            fila = {"estrategia": estrategia, "bloque": bloque}
            for col in ("con_cambio", "cambio_sin_explicar", "parpadeo", "alerta_h4_que_desaparece_en_h2"):
                fila[col] = float(g[col].median())
                fila[f"rango_{col}"] = float(g[col].max() - g[col].min())
            filas.append(fila)
    return pd.DataFrame(filas)


def desempatar(empatadas: list[str], coherencia: pd.DataFrame,
               bloques_seleccion: tuple[str, ...] = ("temporada_2022", "temporada_2023"),
               modelos: dict | None = None) -> dict:
    """Desempate preregistrado: (a) coherencia entre horizontes; (b) simplicidad operativa.

    (a) Gana la estrategia con menos cambios de alerta sin explicar **en ambas**
    temporadas de selección, por más que el mayor rango de semillas de las dos.
    (b) Si (a) no separa, gana la que entrena y despliega menos modelos.
    """
    if len(empatadas) == 1:
        return {"elegida": empatadas[0], "criterio": "única no descartada (no hubo desempate)"}
    c = coherencia.set_index(["estrategia", "bloque"])
    mejores = []
    for e in empatadas:
        domina_a_todas = all(
            all(c.at[(o, b), "cambio_sin_explicar"] - c.at[(e, b), "cambio_sin_explicar"]
                > max(c.at[(o, b), "rango_cambio_sin_explicar"], c.at[(e, b), "rango_cambio_sin_explicar"])
                for b in bloques_seleccion)
            for o in empatadas if o != e)
        if domina_a_todas:
            mejores.append(e)
    if len(mejores) == 1:
        return {"elegida": mejores[0], "criterio": "coherencia entre horizontes"}
    modelos = modelos or MODELOS_POR_ESTRATEGIA
    menos = min(modelos[e] for e in empatadas)
    simples = [e for e in empatadas if modelos[e] == menos]
    return {"elegida": simples[0] if len(simples) == 1 else simples,
            "criterio": "simplicidad operativa" if len(simples) == 1 else "empate sin resolver por simplicidad"}


# ---------------------------------------------------------------------------
# Registro en MLflow (forma horizontes → variantes → folds)
# ---------------------------------------------------------------------------

TIPO_BLOQUE = {"temporada_2021": "calibracion", "temporada_2022": "seleccion",
               "temporada_2023": "seleccion", "temporada_2024": "contraste",
               "calendario_2025": "sensibilidad"}


def fold_mlflow(fila: pd.Series, variante: str) -> dict:
    """Convierte una fila de ``protocolo.metricas_por_bloque`` en un fold registrable."""
    valor = lambda c: None if c not in fila or pd.isna(fila[c]) else float(fila[c])
    return {
        "horizonte": int(fila.horizonte), "variante": variante, "bloque": fila.bloque,
        "tipo": TIPO_BLOQUE.get(fila.bloque, "otro"), "n_prueba": int(fila.n),
        "regresion": {"conteos": {"mae": valor("mae"), "rmse": valor("rmse"), "razon_mae": valor("razon_mae"),
                                  "razon_rmse": valor("razon_rmse")},
                      "alerta_derivada": {"f1": valor("f1_regresion")}},
        "clasificacion": {"alerta_directa": {k: valor(f"{k}_050") for k in ("precision", "recall", "f1")}
                          | {"auprc": valor("auprc")}, "brier": valor("brier")},
        "persistencia": {"conteos": {"mae": valor("mae_persistencia"), "rmse": valor("rmse_persistencia")},
                         "alerta_derivada": {"f1": valor("f1_persistencia"), "auprc": valor("auprc_persistencia")}},
    }


def reporte_mlflow(experimento: str, metricas: dict[str, pd.DataFrame], semillas: tuple[int, ...]) -> dict:
    """Reporte con la forma estándar a partir de métricas por variante."""
    reporte = {"experimento": experimento, "semillas": list(semillas),
               "parametros": {k: v for k, v in PARAMETROS_BASE.items() if k != "random_state"},
               "horizontes": {}}
    for variante, tabla in metricas.items():
        for h, g in tabla.groupby("horizonte"):
            bloque_h = reporte["horizontes"].setdefault(str(int(h)), {"variantes": {}})
            bloque_h["variantes"][variante] = {"folds": [fold_mlflow(f, variante) for _, f in g.iterrows()]}
    return reporte


# ---------------------------------------------------------------------------
# Figuras
# ---------------------------------------------------------------------------

def figura_curva_habilidad(metricas: pd.DataFrame):
    """F1, AUPRC y MAE relativo frente a h, por temporada de selección."""
    import matplotlib.pyplot as plt

    fig, ejes = plt.subplots(1, 3, figsize=(16, 4.5))
    for bloque, g in metricas.groupby("bloque"):
        g = g.sort_values("horizonte")
        etiqueta = bloque.replace("temporada_", "")
        ejes[0].plot(g.horizonte, g.f1_050, marker="o", label=f"XGBoost {etiqueta}")
        ejes[0].plot(g.horizonte, g.f1_persistencia, marker="x", linestyle="--", label=f"Persistencia {etiqueta}")
        ejes[0].plot(g.horizonte, g.f1_estacional, marker="s", linestyle=":", label=f"Estacional {etiqueta}")
        ejes[1].plot(g.horizonte, g.auprc, marker="o", label=f"XGBoost {etiqueta}")
        ejes[1].plot(g.horizonte, g.auprc_persistencia, marker="x", linestyle="--", label=f"Persistencia {etiqueta}")
        ejes[2].plot(g.horizonte, g.razon_mae, marker="o", label=f"XGBoost {etiqueta}")
        ejes[2].plot(g.horizonte, g.razon_mae_estacional, marker="s", linestyle=":", label=f"Estacional {etiqueta}")
    ejes[2].axhline(1, color="grey", linewidth=0.8)
    ejes[2].axhline(0.85, color="black", linewidth=0.8, linestyle="--")
    for ax, titulo in zip(ejes, ("F1 de alerta (p ≥ 0,50 calibrada; reglas de casos)",
                                 "AUPRC", "MAE relativo a la persistencia")):
        ax.set_xlabel("Horizonte h (semanas)")
        ax.set_title(titulo)
        ax.legend(fontsize=7)
    fig.tight_layout()
    return fig
