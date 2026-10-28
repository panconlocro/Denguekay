"""Protocolo de evaluación preregistrado del encargo multi-horizonte (fase 2).

Recibe predicciones fuera de muestra en formato estándar (una fila por
horizonte × bloque × distrito-semana objetivo) y aplica, sin mirar la
temporada evaluada:

1. **Calibración cronológica** de la probabilidad de brote: el calibrador de
   cada bloque se ajusta con predicciones de bloques anteriores cuyas
   etiquetas cerraron antes del primer origen del bloque (2021 → 2022;
   2021–2022 → 2023; …). 2021 no tiene calibrador y no se evalúa en alerta.
2. **Regla de alerta de las HU:** alerta si la probabilidad calibrada es
   ≥ 0,50; niveles de riesgo con los cortes 0,25 / 0,50 / 0,75.
3. **Métricas:** P/R/F1 a 0,50, AUPRC, Brier y fiabilidad por temporada,
   MAE/RMSE frente a la persistencia con desglose por fase de la curva y
   antelación sobre inicios limpios con intervalo bootstrap por episodio.
4. **Regla de decisión** entre dos arquitecturas con los rangos de semillas.

El umbral que maximiza F1 solo se calcula como **diagnóstico** (con
calibración previa, nunca con el bloque evaluado) y no interviene en la
decisión.
"""

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

from denguekay.evaluation import episodes as diag
from denguekay.evaluation.metrics import (
    alertas_desde_conteos, metricas_alerta, metricas_conteos, seleccionar_umbral_f1,
)
from denguekay.model.train import MIN_OUTBREAK_CASES
from src.serving.riesgo import NIVELES
from denguekay.data.validation.forecast_contract import KEY

BLOQUE_CALIBRACION_INICIAL = "temporada_2021"
BLOQUES_SELECCION = ("temporada_2022", "temporada_2023")
BLOQUE_CONTRASTE = "temporada_2024"
BLOQUE_SENSIBILIDAD_CONTEOS = "calendario_2025"
UMBRAL_ALERTA = 0.50
CORTES_RIESGO = {"medio": 0.25, "alto": 0.50, "muy_alto": 0.75}
METODO_CALIBRACION = "platt"
SEMILLAS = (17, 29, 41, 53, 67)
ANTELACION_MINIMA = 2
N_BOOTSTRAP = 2000
SEMILLA_BOOTSTRAP = 20261020
EPS = 1e-6
COLUMNAS_PREDICCION = [*KEY, "semana_inicio", "origen_cierre", "horizonte", "bloque",
                       "casos_Dengue", "brote", "umbral_brote_casos", "persistencia"]
# Métricas en las que mayor es mejor (+1) o peor (-1). RMSE se reporta, no decide.
SENTIDO = {"f1_050": 1, "auprc": 1, "brier": -1, "razon_mae": -1}
PRIMARIAS = ("f1_050",)
GUARDAS = ("auprc", "brier", "razon_mae")


def validar_predicciones(pred: pd.DataFrame) -> pd.DataFrame:
    """Exige el formato estándar, llaves únicas y causalidad del origen."""
    faltan = set(COLUMNAS_PREDICCION) - set(pred)
    if faltan:
        raise ValueError(f"Faltan columnas de predicción: {sorted(faltan)}")
    if "probabilidad_brote" not in pred and "casos_predichos" not in pred:
        raise ValueError("Se necesita probabilidad_brote o casos_predichos")
    datos = pred.copy()
    if not datos.ubigeo.map(lambda u: isinstance(u, str)).all():
        raise ValueError("ubigeo debe ser texto de seis dígitos, no número")
    datos["ubigeo"] = datos.ubigeo.astype("string")
    if not datos.ubigeo.str.fullmatch(r"\d{6}").all():
        raise ValueError("ubigeo debe ser texto de seis dígitos")
    for col in ("semana_inicio", "origen_cierre"):
        datos[col] = pd.to_datetime(datos[col])
    if datos.duplicated(["horizonte", "bloque", *KEY]).any():
        raise ValueError("Distrito-semanas duplicadas en un bloque")
    if not datos.origen_cierre.lt(datos.semana_inicio).all():
        raise ValueError("Fuga temporal: origen_cierre debe ser anterior a semana_inicio")
    if "probabilidad_brote" in datos:
        p = datos.probabilidad_brote
        if p.isna().any() or not p.between(0, 1).all():
            raise ValueError("Probabilidades fuera de [0, 1]")
    return datos


# ---------------------------------------------------------------------------
# Calibración cronológica
# ---------------------------------------------------------------------------

def ajustar_calibrador(p: np.ndarray, y: np.ndarray, metodo: str = METODO_CALIBRACION):
    """Devuelve una función monótona p → p calibrada ajustada con (p, y)."""
    p, y = np.asarray(p, float), np.asarray(y, int)
    if len(np.unique(y)) < 2:
        raise ValueError("El calibrador necesita dos clases")
    if metodo == "platt":
        logit = np.log(np.clip(p, EPS, 1 - EPS) / (1 - np.clip(p, EPS, 1 - EPS)))
        modelo = LogisticRegression(C=1e6, max_iter=1000).fit(logit.reshape(-1, 1), y)

        def calibrar(q):
            q = np.clip(np.asarray(q, float), EPS, 1 - EPS)
            return modelo.predict_proba(np.log(q / (1 - q)).reshape(-1, 1))[:, 1]
        return calibrar
    if metodo == "isotonica":
        modelo = IsotonicRegression(y_min=0, y_max=1, out_of_bounds="clip").fit(p, y)
        return lambda q: modelo.predict(np.asarray(q, float))
    if metodo == "ninguno":
        return lambda q: np.asarray(q, float)
    raise ValueError(f"Método de calibración desconocido: {metodo}")


def corte_bloque(bloque: pd.DataFrame) -> pd.Timestamp:
    """Primer origen del bloque: cierre del origen de su primera semana objetivo."""
    primera = bloque.semana_inicio.min()
    return bloque.loc[bloque.semana_inicio.eq(primera), "origen_cierre"].min()


def calibrar_cronologicamente(pred: pd.DataFrame, metodo: str = METODO_CALIBRACION
                              ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Agrega ``probabilidad_calibrada`` y el umbral F1 diagnóstico por bloque.

    Para cada horizonte y bloque, el calibrador usa filas de bloques que
    empiezan antes, con etiqueta cerrada (``semana_inicio + 6 días``) hasta
    el primer origen del bloque. Sin dos clases disponibles el bloque queda
    sin probabilidad calibrada (temporada 2021).
    """
    datos = validar_predicciones(pred)
    datos["probabilidad_calibrada"] = np.nan
    datos["umbral_diagnostico_f1"] = np.nan
    registro = []
    for h, por_h in datos.groupby("horizonte"):
        inicios = por_h.groupby("bloque").semana_inicio.min().sort_values()
        for bloque, inicio in inicios.items():
            idx = por_h.index[por_h.bloque.eq(bloque)]
            corte = corte_bloque(por_h.loc[idx])
            previas = por_h[por_h.bloque.map(inicios).lt(inicio)]
            disponibles = previas[(previas.semana_inicio + pd.Timedelta(days=6)).le(corte)]
            fila = {"horizonte": h, "bloque": bloque, "corte": corte, "metodo": metodo,
                    "filas_calibracion": len(disponibles),
                    "positivos_calibracion": int(disponibles.brote.sum()),
                    "etiquetas_no_cerradas": len(previas) - len(disponibles)}
            if disponibles.brote.nunique() == 2:
                calibrar = ajustar_calibrador(disponibles.probabilidad_brote, disponibles.brote, metodo)
                datos.loc[idx, "probabilidad_calibrada"] = calibrar(datos.loc[idx, "probabilidad_brote"])
                diagnostico = seleccionar_umbral_f1(
                    disponibles.brote.to_numpy(int), calibrar(disponibles.probabilidad_brote))
                datos.loc[idx, "umbral_diagnostico_f1"] = diagnostico["umbral"]
                fila["ultima_etiqueta_usada"] = disponibles.semana_inicio.max() + pd.Timedelta(days=6)
            registro.append(fila)
    return datos, pd.DataFrame(registro)


def niveles_riesgo(p: pd.Series, cortes: dict = CORTES_RIESGO) -> pd.Categorical:
    """Niveles bajo/medio/alto/muy_alto con intervalos cerrados a la izquierda."""
    bordes = [-np.inf, cortes["medio"], cortes["alto"], cortes["muy_alto"], np.inf]
    return pd.cut(p, bins=bordes, labels=list(NIVELES), right=False)


# ---------------------------------------------------------------------------
# Métricas por bloque
# ---------------------------------------------------------------------------

def agregar_alertas_protocolo(datos: pd.DataFrame) -> pd.DataFrame:
    """Alertas con p calibrada ≥ 0,50, regla de casos y persistencia."""
    salida = datos.copy()
    limite = salida.umbral_brote_casos.to_numpy(float)
    salida["alerta_050"] = salida.probabilidad_calibrada.ge(UMBRAL_ALERTA) if "probabilidad_calibrada" in salida else False
    salida["alerta_diagnostico_f1"] = (salida.probabilidad_calibrada.ge(salida.umbral_diagnostico_f1)
                                       if "probabilidad_calibrada" in salida else False)
    if "casos_predichos" in salida:
        salida["alerta_regresion"] = alertas_desde_conteos(
            salida.casos_predichos.to_numpy(float), limite, MIN_OUTBREAK_CASES)
    salida["alerta_persistencia"] = alertas_desde_conteos(
        salida.persistencia.to_numpy(float), limite, MIN_OUTBREAK_CASES)
    return salida


def metricas_por_bloque(datos: pd.DataFrame) -> pd.DataFrame:
    """Una fila por horizonte y bloque con todas las métricas del protocolo."""
    filas = []
    for (h, bloque), g in datos.groupby(["horizonte", "bloque"]):
        y = g.brote.to_numpy(int)
        fila = {"horizonte": h, "bloque": bloque, "n": len(g), "positivos": int(y.sum())}
        if "probabilidad_calibrada" in g and g.probabilidad_calibrada.notna().all():
            pc = g.probabilidad_calibrada.to_numpy(float)
            m = metricas_alerta(y, g.alerta_050.to_numpy(bool), puntaje=pc)
            fila.update({f"{k}_050": m[k] for k in ("vp", "fp", "fn", "precision", "recall", "f1")})
            fila["auprc"] = m["auprc"]
            fila["brier"] = float(np.mean((pc - y) ** 2))
            fila["brier_sin_calibrar"] = float(np.mean((g.probabilidad_brote - y) ** 2))
            fila["prob_media_calibrada"] = float(pc.mean())
            fila["prevalencia"] = float(y.mean())
            niveles = niveles_riesgo(g.probabilidad_calibrada)
            for nivel in NIVELES:
                en_nivel = niveles == nivel
                fila[f"n_{nivel}"] = int(en_nivel.sum())
                fila[f"tasa_brote_{nivel}"] = float(y[en_nivel].mean()) if en_nivel.any() else None
            d = metricas_alerta(y, g.alerta_diagnostico_f1.to_numpy(bool))
            fila["diagnostico_umbral_f1"] = float(g.umbral_diagnostico_f1.iloc[0])
            fila["diagnostico_f1"] = d["f1"]
        if "alerta_regresion" in g:
            m = metricas_alerta(y, g.alerta_regresion.to_numpy(bool))
            fila.update({f"{k}_regresion": m[k] for k in ("precision", "recall", "f1")})
        limite = np.maximum(g.umbral_brote_casos.to_numpy(float), MIN_OUTBREAK_CASES)
        m = metricas_alerta(y, g.alerta_persistencia.to_numpy(bool),
                            puntaje=g.persistencia.to_numpy(float) - limite)
        fila.update({f"{k}_persistencia": m[k] for k in ("precision", "recall", "f1", "auprc")})
        if "estacional" in g and g.estacional.notna().all():
            est = g.estacional.to_numpy(float)
            m = metricas_alerta(y, alertas_desde_conteos(est, g.umbral_brote_casos.to_numpy(float),
                                                         MIN_OUTBREAK_CASES), puntaje=est - limite)
            fila.update({f"{k}_estacional": m[k] for k in ("precision", "recall", "f1", "auprc")})
            mae_p = metricas_conteos(g.casos_Dengue, g.persistencia)["mae"]
            fila["razon_mae_estacional"] = (metricas_conteos(g.casos_Dengue, est)["mae"] / mae_p
                                            if mae_p else None)
        if "casos_predichos" in g:
            mc = metricas_conteos(g.casos_Dengue, g.casos_predichos)
            mp = metricas_conteos(g.casos_Dengue, g.persistencia)
            fila.update({"mae": mc["mae"], "rmse": mc["rmse"], "mae_persistencia": mp["mae"],
                         "rmse_persistencia": mp["rmse"],
                         "razon_mae": mc["mae"] / mp["mae"] if mp["mae"] else None,
                         "razon_rmse": mc["rmse"] / mp["rmse"] if mp["rmse"] else None})
        filas.append(fila)
    return pd.DataFrame(filas)


def fiabilidad_por_bloque(datos: pd.DataFrame, n_bins: int = 10) -> pd.DataFrame:
    """Curva de fiabilidad de la probabilidad calibrada por bloque y agregada 2022–2023."""
    partes = []
    evaluables = datos[datos.probabilidad_calibrada.notna()]
    for (h, bloque), g in evaluables.groupby(["horizonte", "bloque"]):
        partes.append(diag.curva_fiabilidad(g.brote, g.probabilidad_calibrada, n_bins)
                      .reset_index(names="bin").assign(horizonte=h, bloque=bloque))
    for h, g in evaluables[evaluables.bloque.isin(BLOQUES_SELECCION)].groupby("horizonte"):
        partes.append(diag.curva_fiabilidad(g.brote, g.probabilidad_calibrada, n_bins)
                      .reset_index(names="bin").assign(horizonte=h, bloque="seleccion_2022_2023"))
    return pd.concat(partes, ignore_index=True)


# ---------------------------------------------------------------------------
# Antelación sobre inicios limpios
# ---------------------------------------------------------------------------

def antelacion_limpios(datos: pd.DataFrame, etiquetas: pd.DataFrame, alertas: list[str]) -> pd.DataFrame:
    """Antelación por episodio con inicio limpio en los bloques con alerta calibrada."""
    evaluables = datos[datos.bloque.ne(BLOQUE_CALIBRACION_INICIAL)
                       & datos.bloque.ne(BLOQUE_SENSIBILIDAD_CONTEOS)]
    tabla = diag.antelacion_episodios(evaluables, etiquetas, alertas)
    return tabla[tabla.semanas_previas_sin_brote >= diag.SIN_BROTE_PREVIO].reset_index(drop=True)


def _avisados(tabla: pd.DataFrame, alerta: str) -> np.ndarray:
    return tabla[alerta].ge(ANTELACION_MINIMA).to_numpy(float)


def bootstrap_estratificado(valores: np.ndarray, estratos: np.ndarray, n: int = N_BOOTSTRAP,
                            semilla: int = SEMILLA_BOOTSTRAP) -> np.ndarray:
    """Medias bootstrap remuestreando episodios dentro de cada estrato (temporada)."""
    rng = np.random.default_rng(semilla)
    grupos = [np.flatnonzero(estratos == e) for e in np.unique(estratos)]
    medias = np.empty(n)
    for i in range(n):
        idx = np.concatenate([rng.choice(g, size=len(g), replace=True) for g in grupos])
        medias[i] = valores[idx].mean()
    return medias


def resumen_antelacion_ic(tabla: pd.DataFrame, alerta: str) -> pd.DataFrame:
    """Fracción de inicios limpios avisados ≥ 2 semanas antes, con IC 95 % bootstrap."""
    filas = []
    for h, g in tabla.groupby("horizonte"):
        conjuntos = [(b, g[g.bloque.eq(b)]) for b in sorted(g.bloque.unique())]
        seleccion = g[g.bloque.isin(BLOQUES_SELECCION)]
        conjuntos.append(("seleccion_2022_2023", seleccion))
        for nombre, t in conjuntos:
            if t.empty:
                continue
            v = _avisados(t, alerta)
            medias = bootstrap_estratificado(v, t.bloque.to_numpy())
            filas.append({"horizonte": h, "bloque": nombre, "alerta": alerta, "episodios": len(t),
                          "avisados_2_o_mas": float(v.mean()),
                          "ic95_inferior": float(np.quantile(medias, 0.025)),
                          "ic95_superior": float(np.quantile(medias, 0.975))})
    return pd.DataFrame(filas)


def diferencia_antelacion(tabla_a: pd.DataFrame, tabla_b: pd.DataFrame, alerta_a: str,
                          alerta_b: str | None = None) -> pd.DataFrame:
    """Diferencia pareada A − B por episodio en 2022–2023, con IC 95 % bootstrap.

    Los episodios dependen solo de las etiquetas, así que A y B comparten
    exactamente el mismo conjunto para un mismo horizonte.
    """
    alerta_b = alerta_b or alerta_a
    llave = ["horizonte", "bloque", "ubigeo", "inicio"]
    a = tabla_a[tabla_a.bloque.isin(BLOQUES_SELECCION)]
    b = tabla_b[tabla_b.bloque.isin(BLOQUES_SELECCION)]
    pares = a[llave + [alerta_a]].merge(b[llave + [alerta_b]], on=llave, suffixes=("_a", "_b"),
                                        validate="one_to_one")
    if len(pares) != len(a) or len(pares) != len(b):
        raise ValueError("Las arquitecturas no comparten los mismos episodios")
    col_a = f"{alerta_a}_a" if alerta_a == alerta_b else alerta_a
    col_b = f"{alerta_b}_b" if alerta_a == alerta_b else alerta_b
    filas = []
    for h, g in pares.groupby("horizonte"):
        dif = g[col_a].ge(ANTELACION_MINIMA).to_numpy(float) - g[col_b].ge(ANTELACION_MINIMA).to_numpy(float)
        medias = bootstrap_estratificado(dif, g.bloque.to_numpy())
        por_temporada = {b: float(dif[g.bloque.eq(b).to_numpy()].mean()) for b in BLOQUES_SELECCION}
        filas.append({"horizonte": h, "episodios": len(g), "diferencia": float(dif.mean()),
                      "ic95_inferior": float(np.quantile(medias, 0.025)),
                      "ic95_superior": float(np.quantile(medias, 0.975)),
                      **{f"diferencia_{b}": v for b, v in por_temporada.items()}})
    return pd.DataFrame(filas)


# ---------------------------------------------------------------------------
# Evaluación completa, rangos de semillas y regla de decisión
# ---------------------------------------------------------------------------

def evaluar(pred: pd.DataFrame, etiquetas: pd.DataFrame, metodo: str = METODO_CALIBRACION) -> dict:
    """Aplica el protocolo completo a un conjunto de predicciones."""
    datos, calibracion = calibrar_cronologicamente(pred, metodo)
    datos = agregar_alertas_protocolo(datos)
    alertas = ["alerta_050", "alerta_persistencia"] + (["alerta_regresion"] if "alerta_regresion" in datos else [])
    antelacion = antelacion_limpios(datos, etiquetas, alertas)
    resultado = {
        "datos": datos, "calibracion": calibracion,
        "metricas": metricas_por_bloque(datos),
        "fiabilidad": fiabilidad_por_bloque(datos),
        "antelacion": antelacion,
        "antelacion_ic": pd.concat([resumen_antelacion_ic(antelacion, a) for a in alertas], ignore_index=True),
    }
    if "casos_predichos" in datos:
        datos = datos.assign(fase=diag.fase_curva(datos))
        resultado["errores_por_fase"] = diag.desglose_errores(datos, ["horizonte", "bloque", "fase"])
    return resultado


def rangos_semillas(metricas: list[pd.DataFrame]) -> pd.DataFrame:
    """Rango (máximo − mínimo) entre semillas por horizonte, bloque y métrica."""
    columnas = list(SENTIDO) + ["rmse", "mae", "recall_050", "precision_050"]
    todas = pd.concat(metricas, ignore_index=True)
    columnas = [c for c in columnas if c in todas]
    agrupado = todas.groupby(["horizonte", "bloque"])[columnas]
    return (agrupado.max() - agrupado.min()).reset_index()


def umbral_empate(*rangos: pd.DataFrame, horizontes: tuple[int, ...] = (2, 3, 4)) -> pd.DataFrame:
    """Umbral de empate: el mayor rango entre las arquitecturas comparadas.

    Un horizonte sin rangos propios (h=3 antes de medirlo) toma el mayor
    rango de los horizontes disponibles en el mismo bloque.
    """
    todos = pd.concat(rangos, ignore_index=True)
    por_h = todos.groupby(["horizonte", "bloque"]).max().reset_index()
    peor = todos.drop(columns="horizonte").groupby("bloque").max().reset_index()
    faltan = [h for h in horizontes if h not in set(por_h.horizonte)]
    extra = [peor.assign(horizonte=h) for h in faltan]
    return pd.concat([por_h, *extra], ignore_index=True)[por_h.columns]


def decidir(candidata: pd.DataFrame, referencia: pd.DataFrame, rangos: pd.DataFrame,
            dif_antelacion: pd.DataFrame) -> pd.DataFrame:
    """Veredicto preregistrado y simétrico por horizonte: gana, pierde, compensa o empata.

    ``candidata`` (A) y ``referencia`` (B) son métricas por bloque (mediana de
    semillas); ``rangos`` el umbral de empate por métrica; ``dif_antelacion``
    la diferencia pareada A − B de la antelación. Mejora y empeora exigen
    ambas temporadas de selección; las guardas solo vetan una victoria. Por
    construcción, A pierde frente a B si y solo si B gana frente a A.
    """
    filas = []
    for h in sorted(candidata.horizonte.unique()):
        c = candidata[candidata.horizonte.eq(h)].set_index("bloque")
        r = referencia[referencia.horizonte.eq(h)].set_index("bloque")
        e = rangos[rangos.horizonte.eq(h)].set_index("bloque")
        delta = {m: {b: SENTIDO[m] * (c.at[b, m] - r.at[b, m]) for b in BLOQUES_SELECCION}
                 for m in SENTIDO if m in c and m in r}
        mejora = {m: all(delta[m][b] > e.at[b, m] for b in BLOQUES_SELECCION) for m in delta}
        empeora = {m: all(delta[m][b] < -e.at[b, m] for b in BLOQUES_SELECCION) for m in delta}
        a = dif_antelacion[dif_antelacion.horizonte.eq(h)].iloc[0]
        mejora_ant = bool(a.ic95_inferior > 0 and all(a[f"diferencia_{b}"] > 0 for b in BLOQUES_SELECCION))
        empeora_ant = bool(a.ic95_superior < 0 and all(a[f"diferencia_{b}"] < 0 for b in BLOQUES_SELECCION))
        mejora_primaria = any(mejora.get(m, False) for m in PRIMARIAS) or mejora_ant
        empeora_primaria = any(empeora.get(m, False) for m in PRIMARIAS) or empeora_ant
        veto_a = [m for m in GUARDAS if empeora.get(m, False)]
        veto_b = [m for m in GUARDAS if mejora.get(m, False)]
        if mejora_primaria and not empeora_primaria and not veto_a:
            veredicto = "gana"
        elif empeora_primaria and not mejora_primaria and not veto_b:
            veredicto = "pierde"
        elif mejora_primaria or empeora_primaria:
            veredicto = "compensa (empate)"
        else:
            veredicto = "empate"
        filas.append({"horizonte": h, "veredicto": veredicto,
                      "mejora_f1_050": mejora.get("f1_050"), "empeora_f1_050": empeora.get("f1_050"),
                      "mejora_antelacion": mejora_ant, "empeora_antelacion": empeora_ant,
                      "vetos": ", ".join(veto_a) or None, "vetos_contra_referencia": ", ".join(veto_b) or None,
                      **{f"umbral_{m}_{b}": e.at[b, m] for m in delta for b in BLOQUES_SELECCION},
                      **{f"delta_{m}_{b}": SENTIDO[m] * v for m, d in delta.items() for b, v in d.items()}})
    return pd.DataFrame(filas)


def mediana_semillas(metricas: list[pd.DataFrame]) -> pd.DataFrame:
    """Mediana de cada métrica entre semillas, por horizonte y bloque."""
    todas = pd.concat(metricas, ignore_index=True)
    numericas = todas.select_dtypes("number").columns.difference(["horizonte"])
    return todas.groupby(["horizonte", "bloque"])[list(numericas)].median().reset_index()


def desde_compacta(predicciones: pd.DataFrame) -> pd.DataFrame:
    """Convierte ``predicciones_por_bloque.csv`` del experimento 30 al formato estándar (E1)."""
    comunes = [*KEY, "semana_inicio", "origen_cierre", "horizonte", "bloque",
               "casos_Dengue", "brote", "umbral_brote_casos"]
    reg = predicciones[predicciones.variante.eq(diag.VARIANTE_REGRESION)].copy()
    cls = predicciones[predicciones.variante.eq(diag.VARIANTE_CLASIFICACION)]
    reg["persistencia"] = np.where(reg.horizonte.eq(2), reg.casos_lag_2, reg.casos_lag_4)
    datos = reg[comunes + ["casos_predichos", "persistencia"]].merge(
        cls[comunes + ["probabilidad_brote"]], on=comunes, validate="one_to_one")
    if len(datos) != len(reg) or len(datos) != len(cls):
        raise ValueError("Regresión y clasificación no cubren las mismas filas")
    return validar_predicciones(datos)
