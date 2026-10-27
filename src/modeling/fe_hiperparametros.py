"""Encargo de feature engineering e hiperparámetros sobre E3·S4_s2 (envoltura del flujo).

La arquitectura y el protocolo quedan fijos (``salida_probabilistica.predecir_e3``
con ``S4_s2`` y ``protocolo_arquitectura.evaluar``). Este módulo solo orquesta:

- insumos en memoria (panel, etiquetas, serie y matrices h=2, 3, 4), igual que
  el notebook 31;
- evaluación de una variante (columnas e hiperparámetros) con las 5 semillas;
- resumen de una variante: medianas, rangos, antelación y recall en brotes nuevos;
- comprobación de la reproducción frente a ``fase5_decision``;
- inventario de las candidatas de gold h=2 y sus antecedentes con S1.

Las variables nuevas van en su propio módulo (fase 2b) y la búsqueda de
hiperparámetros en ``hiperparametros.py`` (fase 3). Nada se escribe en ``data/``.
"""

import json
import time

import numpy as np
import pandas as pd

from src.modeling import estrategias_horizonte as eh
from src.modeling import protocolo_arquitectura as pa
from src.modeling import salida_probabilistica as sp
from src.modeling.contrato_xgboost import NO_PREDICTORAS, familias_predictoras
from src.modeling.train import PARAMETROS_BASE

ESTRATEGIA, FORMULACION = "E3", "S4_s2"
NOMBRE_REFERENCIA = "referencia_B"
BLOQUE_SELECCION_CONJUNTA = "seleccion_2022_2023"
DECIMALES_REPRODUCCION = 3
ABLACIONES_S1 = {"25_espacial": "ablacion_espacial", "26_clima": "ablacion_clima",
                 "27_sociodemografica": "ablacion_sociodemografica",
                 "28_fracciones": "ablacion_fracciones",
                 "29_poblacion_sin_seguro": "ablacion_poblacion_sin_seguro"}


# ---------------------------------------------------------------------------
# Insumos en memoria
# ---------------------------------------------------------------------------

def insumos(panel: pd.DataFrame, regla: dict) -> dict:
    """Etiquetas, serie y matrices h=2, 3, 4 como en el notebook 31 (celda de fase 3)."""
    from src.modeling.etiqueta_brote import ConfiguracionBroteEstacional
    from src.modeling.features import construir_etiquetas

    etiquetas = construir_etiquetas(panel, ConfiguracionBroteEstacional(
        regla["multiplicador"], regla["anios_previos"], regla["minimo_casos"]))
    serie = panel[["ubigeo", "anio", "semana", "semana_inicio", "casos_Dengue"]].merge(
        etiquetas[["ubigeo", "anio", "semana", "brote"]], on=["ubigeo", "anio", "semana"])
    serie["semana_inicio"] = pd.to_datetime(serie.semana_inicio)
    matrices = {h: eh.matriz_horizonte(panel, etiquetas, h) for h in eh.HORIZONTES_ESTRATEGIA}
    return {"etiquetas": etiquetas, "serie": serie, "matrices": matrices}


# ---------------------------------------------------------------------------
# Evaluación de una variante
# ---------------------------------------------------------------------------

def evaluar_variante(matrices: dict[int, pd.DataFrame], serie: pd.DataFrame, *,
                     columnas: list[str] | None = None, origenes: pd.DataFrame | None = None,
                     hiperparametros: dict | None = None, preparar_bloque=None,
                     semillas: tuple[int, ...] = pa.SEMILLAS) -> dict:
    """Predice con E3·S4_s2 y aplica el protocolo congelado, una vez por semilla.

    Devuelve ``{"predicciones": {semilla: df}, "evaluaciones": {semilla: dict}}``.
    """
    calibracion = sp.FORMULACIONES[FORMULACION]["calibracion"]
    predicciones, evaluaciones = {}, {}
    for semilla in semillas:
        pred = sp.predecir_e3(matrices, semilla, FORMULACION, columnas=columnas,
                              origenes=origenes, hiperparametros=hiperparametros,
                              preparar_bloque=preparar_bloque)
        predicciones[semilla] = pred
        evaluaciones[semilla] = pa.evaluar(pred, serie, calibracion)
    return {"predicciones": predicciones, "evaluaciones": evaluaciones}


def resumir_variante(evaluaciones: dict[int, dict], serie: pd.DataFrame) -> dict:
    """Medianas y rangos de semillas, antelación y recall por tipo de semana brote."""
    metricas = [r["metricas"] for r in evaluaciones.values()]
    antelacion = pd.concat({s: r["antelacion_ic"].query("alerta == 'alerta_050'")
                            for s, r in evaluaciones.items()}, names=["semilla"]).reset_index(level=0)
    persistencia = next(iter(evaluaciones.values()))["antelacion_ic"].query("alerta == 'alerta_persistencia'")
    recall = pd.concat({s: sp.recall_por_tipo_semana(r["datos"], serie) for s, r in evaluaciones.items()},
                       names=["semilla"]).reset_index(level=0)
    return {
        "medianas": pa.mediana_semillas(metricas),
        "rangos": pa.rangos_semillas(metricas),
        "antelacion": (antelacion.groupby(["horizonte", "bloque"]).avisados_2_o_mas
                       .agg(mediana="median", minimo="min", maximo="max").reset_index()
                       .merge(persistencia[["horizonte", "bloque", "episodios", "avisados_2_o_mas"]]
                              .rename(columns={"avisados_2_o_mas": "persistencia"}),
                              on=["horizonte", "bloque"], how="left")),
        "recall_por_tipo": (recall.groupby(["horizonte", "bloque", "tipo"])
                            .agg(semanas=("semanas", "first"), recall_mediana=("recall", "median"),
                                 recall_minimo=("recall", "min"), recall_maximo=("recall", "max"))
                            .reset_index()),
    }


def diferencia_antelacion_persistencia(evaluacion: dict) -> pd.DataFrame:
    """Diferencia pareada modelo − persistencia en inicios limpios 2022–2023 (una semilla)."""
    t = evaluacion["antelacion"]
    return pa.diferencia_antelacion(t, t, "alerta_050", "alerta_persistencia")


# ---------------------------------------------------------------------------
# Reproducción frente al encargo de arquitectura
# ---------------------------------------------------------------------------

def comparar_reproduccion(medianas: pd.DataFrame, referencia: list[dict],
                          decimales: int = DECIMALES_REPRODUCCION) -> pd.DataFrame:
    """Compara, métrica por métrica, las medianas nuevas con las guardadas.

    ``referencia`` es ``fase5_decision.metricas_mediana_semillas``. Una fila por
    (horizonte, bloque, métrica) con ambos valores, la diferencia absoluta y si
    coinciden al redondeo de ``decimales``. Las métricas guardadas sin
    contrapartida nueva (o al revés) también se reportan, como no coincidentes.
    """
    guardada = pd.DataFrame(referencia).melt(["horizonte", "bloque"], var_name="metrica", value_name="guardada")
    nueva = medianas.melt(["horizonte", "bloque"], var_name="metrica", value_name="reproducida")
    cruce = guardada.merge(nueva, on=["horizonte", "bloque", "metrica"], how="outer")
    g, r = cruce.guardada.astype(float), cruce.reproducida.astype(float)
    ambos_nulos = g.isna() & r.isna()
    cruce["diferencia_absoluta"] = (g - r).abs()
    cruce["coincide"] = ambos_nulos | (g.round(decimales) == r.round(decimales))
    return cruce.sort_values(["horizonte", "bloque", "metrica"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Inventario de candidatas de gold h=2 y antecedentes con S1
# ---------------------------------------------------------------------------

def inventario_candidatas(gold_h2: pd.DataFrame, matriz_h2: pd.DataFrame) -> pd.DataFrame:
    """Familia y nulos de arranque de cada candidata predictora de gold h=2.

    ``nulos_gold`` cuenta nulos en todo gold; ``nulos_tras_arranque`` los que
    quedan en la matriz modelable (después de las exclusiones de
    ``preparar_gold``), y ``en_base_6`` marca las 6 de la referencia.
    """
    familia = {c: f for f, cols in familias_predictoras(2).items() for c in cols}
    candidatas = [c for c in gold_h2.columns if c not in NO_PREDICTORAS]
    sin_familia = [c for c in candidatas if c not in familia]
    if sin_familia:
        raise ValueError(f"Candidatas de gold sin familia en el contrato: {sin_familia}")
    base = set(eh.columnas_modelo(2)[0])
    filas = []
    for c in candidatas:
        g = gold_h2[c]
        primera = gold_h2.loc[g.notna(), "semana_inicio"].min()
        filas.append({"columna": c, "familia": familia[c], "en_base_6": c in base,
                      "nulos_gold": int(g.isna().sum()), "fraccion_nulos_gold": float(g.isna().mean()),
                      "primera_semana_con_valor": str(pd.Timestamp(primera).date()) if pd.notna(primera) else None,
                      "nulos_tras_arranque": int(matriz_h2[c].isna().sum()) if c in matriz_h2 else None})
    return pd.DataFrame(filas)


def _f1_validacion(variante: dict, enfoque: str) -> dict[str, float]:
    """F1 de validación por temporada de una variante de las ablaciones 25–29."""
    salida = {}
    for fold in variante["folds_validacion"]:
        bloque = fold[enfoque]
        f1 = (bloque.get("alerta_derivada", {}) if enfoque == "regresion" else bloque.get("alerta_directa", {})).get("f1")
        salida[fold["bloque"]] = None if f1 is None else float(f1)
    return salida


def antecedentes_s1(metricas_ablaciones: dict[str, dict], horizonte: str = "2") -> pd.DataFrame:
    """Resultado de cada variante en las ablaciones 25–29 (S1, protocolo propio).

    Por variante: columnas añadidas a ``base_6``, F1 medio de validación
    (2021–2023) de la alerta derivada de la regresión y del clasificador, su
    diferencia con ``base_6`` y si fue la elegida en validación. **Antecedente:**
    otro protocolo (umbral elegido en validación, F1 medio, sin rangos de
    semillas), así que no es comparable con los veredictos de este encargo.
    """
    filas = []
    for notebook, d in metricas_ablaciones.items():
        bloque_h = d["horizontes"][horizonte]
        elegidas = bloque_h.get("elegidas_solo_validacion", {})
        planas = {}
        for k, v in elegidas.items():
            if isinstance(v, dict):
                for enfoque, var in v.items():
                    planas.setdefault(var, []).append(f"{k}:{enfoque}")
            else:
                planas.setdefault(v, []).append(k)
        variantes = bloque_h["variantes"]
        base_cols = set(variantes["base_6"]["columnas"])
        media_base = {e: np.nanmean([x for x in _f1_validacion(variantes["base_6"], e).values() if x is not None])
                      for e in ("regresion", "clasificacion")}
        for nombre, var in variantes.items():
            fila = {"ablacion": notebook, "variante": nombre,
                    "columnas_agregadas": [c for c in var["columnas"] if c not in base_cols],
                    "elegida_en_validacion": ", ".join(planas.get(nombre, [])) or None}
            for enfoque, corto in (("regresion", "reg"), ("clasificacion", "cls")):
                f1 = [x for x in _f1_validacion(var, enfoque).values() if x is not None]
                media = float(np.mean(f1)) if f1 else None
                fila[f"f1_val_medio_{corto}"] = media
                fila[f"delta_f1_val_{corto}_vs_base_6"] = None if media is None else media - media_base[enfoque]
            filas.append(fila)
    return pd.DataFrame(filas)


def cargar_ablaciones(directorio) -> dict[str, dict]:
    """Lee los JSON de las ablaciones 25–29 (solo lectura)."""
    return {n: json.loads((directorio / f"{a}.json").read_text(encoding="utf-8"))
            for n, a in ABLACIONES_S1.items()}


# ---------------------------------------------------------------------------
# Tiempos
# ---------------------------------------------------------------------------

def medir_ajuste(matrices: dict[int, pd.DataFrame], serie: pd.DataFrame, semilla: int = 17,
                 repeticiones: int = 3, hiperparametros: dict | None = None) -> pd.DataFrame:
    """Segundos de un ajuste completo (5 bloques × 1 semilla) y de su evaluación."""
    filas = []
    for i in range(repeticiones):
        t0 = time.perf_counter()
        pred = sp.predecir_e3(matrices, semilla, FORMULACION, hiperparametros=hiperparametros)
        t1 = time.perf_counter()
        pa.evaluar(pred, serie, sp.FORMULACIONES[FORMULACION]["calibracion"])
        t2 = time.perf_counter()
        filas.append({"repeticion": i + 1, "segundos_ajuste_prediccion": t1 - t0,
                      "segundos_evaluacion": t2 - t1, "segundos_total": t2 - t0})
    return pd.DataFrame(filas)


# ---------------------------------------------------------------------------
# MLflow (forma estándar horizontes → variantes → folds)
# ---------------------------------------------------------------------------

def reporte_mlflow(experimento: str, medianas: dict[str, pd.DataFrame],
                   semillas: tuple[int, ...] = pa.SEMILLAS, hiperparametros: dict | None = None) -> dict:
    """Reporte registrable con ``seguimiento_mlflow`` para una o varias variantes."""
    reporte = eh.reporte_mlflow(experimento, medianas, semillas)
    reporte["parametros"] = {**{k: v for k, v in PARAMETROS_BASE.items() if k != "random_state"},
                             "multi_strategy": "multi_output_tree", "objective": "count:poisson",
                             **(hiperparametros or {})}
    reporte["estrategia"], reporte["formulacion"] = ESTRATEGIA, FORMULACION
    return reporte
