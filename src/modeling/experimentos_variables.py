"""Experimentos de variables sobre E3·S4_s2 (fase 2 del encargo de FE).

Cada variante preregistrada (``preregistro_fe``) se suma a ``base_6`` y se
compara contra su referencia con la regla simétrica del protocolo
(``estrategias_horizonte.decidir_frente_a_referencia``, la misma del
notebook 31). Además se reporta una lectura que **no decide**:

- ``mejora_antelacion``: la de la regla (IC95 > 0, ambas temporadas y la
  mediana entre semillas en el mismo sentido);
- ``mejora_recall_nuevos``: la mediana del recall en las 2 primeras semanas de
  brotes nuevos sube, en 2022 y en 2023, más que el mayor rango entre
  semillas de las dos variantes;
- ``posible_senal_de_temporada``: la regla marca mejora de F1 a 0,50 y no se
  mueve ninguna de las dos anteriores.
"""

import numpy as np
import pandas as pd

from src.modeling import diagnostico_arquitectura as diag
from src.modeling import estrategias_horizonte as eh
from src.modeling import fe_hiperparametros as fh
from src.modeling import protocolo_arquitectura as pa

H_ULTIMO = eh.HORIZONTES_ESTRATEGIA[-1]


# ---------------------------------------------------------------------------
# Orígenes de una variante
# ---------------------------------------------------------------------------

def origenes_con(matrices: dict[int, pd.DataFrame], columnas_extra: list[str]) -> tuple[pd.DataFrame, dict]:
    """Tabla de orígenes con las columnas extra; quita filas con nulos de arranque.

    Devuelve ``(origenes, excluidas)``. La referencia de una variante con
    exclusiones se reentrena con estos mismos orígenes (intersección de filas).
    """
    origenes = eh.tabla_origenes(matrices[2])
    faltan = [c for c in columnas_extra if c not in origenes]
    if faltan:
        raise ValueError(f"Columnas ausentes en la tabla de orígenes: {faltan}")
    nulas = origenes[columnas_extra].isna().any(axis=1)
    excluidas = {"filas": int(nulas.sum()),
                 "primera": str(origenes.loc[nulas, "semana_inicio"].min().date()) if nulas.any() else None,
                 "ultima": str(origenes.loc[nulas, "semana_inicio"].max().date()) if nulas.any() else None}
    return origenes.loc[~nulas].reset_index(drop=True), excluidas


def filas_entrenamiento(origenes: pd.DataFrame, corte: pd.Timestamp) -> pd.Series:
    """Orígenes cuyo último objetivo (t+4) cerró al corte: el mismo criterio de ``predecir_e3``."""
    ultima = origenes[f"semana_inicio_h{H_ULTIMO}"]
    return ultima.notna() & (ultima + pd.Timedelta(days=6)).le(corte)


class Cp1PorBloque:
    """CP1 de varias columnas, con estandarización y PCA ajustadas por bloque.

    Media, DE y el primer componente se estiman solo con los orígenes de
    entrenamiento del bloque y se aplican igual a todos los orígenes. El
    signo se fija para que la carga de la primera columna (orden alfabético)
    sea positiva. ``ajustes`` guarda, por corte, la varianza explicada.
    """

    def __init__(self, columnas: list[str], nombre: str):
        self.columnas, self.nombre, self.ajustes = sorted(columnas), nombre, []

    def ajustar(self, origenes: pd.DataFrame, corte: pd.Timestamp) -> dict:
        train = origenes.loc[filas_entrenamiento(origenes, corte), self.columnas].to_numpy(float)
        if len(train) < 2 or np.isnan(train).any():
            raise ValueError("Entrenamiento insuficiente o con nulos para el CP1")
        media, de = train.mean(axis=0), train.std(axis=0)
        de = np.where(de > 0, de, 1.0)
        z = (train - media) / de
        _, s, vt = np.linalg.svd(z - z.mean(axis=0), full_matrices=False)
        carga = vt[0] * (1 if vt[0][0] >= 0 else -1)
        return {"corte": str(pd.Timestamp(corte).date()), "media": media, "de": de, "carga": carga,
                "varianza_explicada": float(s[0] ** 2 / (s ** 2).sum()), "filas_ajuste": len(train)}

    def __call__(self, origenes: pd.DataFrame, corte: pd.Timestamp) -> pd.DataFrame:
        ajuste = self.ajustar(origenes, corte)
        self.ajustes.append({k: (v.tolist() if isinstance(v, np.ndarray) else v) for k, v in ajuste.items()})
        z = (origenes[self.columnas].to_numpy(float) - ajuste["media"]) / ajuste["de"]
        return origenes.assign(**{self.nombre: z @ ajuste["carga"]})


# ---------------------------------------------------------------------------
# Lectura adicional y veredicto
# ---------------------------------------------------------------------------

def recall_por_fase(evaluaciones: dict[int, dict]) -> pd.DataFrame:
    """Recall a 0,50 calibrada por fase de la curva regional, mediana de semillas."""
    partes = []
    for semilla, r in evaluaciones.items():
        datos = r["datos"]
        datos = datos.assign(fase=diag.fase_curva(datos))
        pos = datos[datos.brote.eq(1) & datos.probabilidad_calibrada.notna()]
        partes.append(pos.groupby(["horizonte", "bloque", "fase"], observed=True).alerta_050
                      .agg(semanas="size", recall="mean").reset_index().assign(semilla=semilla))
    todas = pd.concat(partes, ignore_index=True).astype({"fase": str})
    return (todas.groupby(["horizonte", "bloque", "fase"])
            .agg(semanas=("semanas", "first"), recall=("recall", "median")).reset_index())


def mejora_recall_nuevos(resumen_a: dict, resumen_b: dict,
                         bloques: tuple[str, ...] = pa.BLOQUES_SELECCION) -> pd.DataFrame:
    """Delta de la mediana del recall en brotes nuevos (A − B) frente al mayor rango de semillas."""
    def nuevos(r):
        t = r["recall_por_tipo"]
        t = t[t.tipo.eq("brote_nuevo") & t.bloque.isin(bloques)].set_index(["horizonte", "bloque"])
        return t.assign(rango=t.recall_maximo - t.recall_minimo)
    a, b = nuevos(resumen_a), nuevos(resumen_b)
    t = pd.DataFrame({"recall_nuevos_a": a.recall_mediana, "recall_nuevos_b": b.recall_mediana,
                      "umbral": np.maximum(a.rango, b.rango)})
    t["delta"] = t.recall_nuevos_a - t.recall_nuevos_b
    t["supera"] = t.delta > t.umbral
    filas = []
    for h, g in t.reset_index().groupby("horizonte"):
        fila = {"horizonte": h, "mejora_recall_nuevos": bool(g.supera.all() and len(g) == len(bloques))}
        for _, r in g.iterrows():
            sufijo = r.bloque.replace("temporada_", "")
            fila |= {f"recall_nuevos_delta_{sufijo}": r.delta, f"recall_nuevos_umbral_{sufijo}": r.umbral}
        filas.append(fila)
    return pd.DataFrame(filas)


def comparar_familia(nombre: str, evaluaciones_a: dict[int, dict], resumen_a: dict,
                     referencia: str, evaluaciones_b: dict[int, dict], resumen_b: dict) -> pd.DataFrame:
    """Veredicto de la regla simétrica más la lectura de antelación, recall en nuevos y temporada."""
    veredicto = eh.decidir_frente_a_referencia({nombre: evaluaciones_a, referencia: evaluaciones_b},
                                               nombre, referencia)
    return marcar_senal_temporada(veredicto.merge(mejora_recall_nuevos(resumen_a, resumen_b), on="horizonte"))


def marcar_senal_temporada(tabla: pd.DataFrame) -> pd.DataFrame:
    """Sube F1 (según la regla) sin mejorar la antelación ni el recall en brotes nuevos."""
    return tabla.assign(posible_senal_de_temporada=(tabla.mejora_f1_050.fillna(False).astype(bool)
                                                    & ~tabla.mejora_antelacion.fillna(False).astype(bool)
                                                    & ~tabla.mejora_recall_nuevos.fillna(False).astype(bool)))


def tabla_metricas(resumen: dict, nombre: str) -> pd.DataFrame:
    """Medianas de semillas por horizonte y temporada con las columnas del reporte."""
    columnas = ["horizonte", "bloque", "precision_050", "recall_050", "f1_050", "auprc", "brier",
                "razon_mae", "razon_rmse"]
    return resumen["medianas"][columnas].assign(variante=nombre)


def figura_deltas(metricas: pd.DataFrame, referencias: dict[str, str], metrica: str = "f1_050",
                  bloques: tuple[str, ...] = pa.BLOQUES_SELECCION):
    """Delta de una métrica (variante − su referencia) por horizonte y temporada de selección."""
    import matplotlib.pyplot as plt

    variantes = list(referencias)
    fig, ejes = plt.subplots(1, len(bloques), figsize=(6.5 * len(bloques), 4), squeeze=False, sharey=True)
    for ax, bloque in zip(ejes.ravel(), bloques):
        x = np.arange(len(variantes))
        for i, h in enumerate(eh.HORIZONTES_ESTRATEGIA):
            deltas = []
            for v in variantes:
                a = metricas.query("variante == @v and horizonte == @h and bloque == @bloque")[metrica]
                b = metricas.query("variante == @referencias[@v] and horizonte == @h and bloque == @bloque")[metrica]
                deltas.append(float(a.iloc[0] - b.iloc[0]))
            ax.bar(x + (i - 1) * 0.27, deltas, 0.27, label=f"h={h}")
        ax.axhline(0, color="grey", linewidth=0.8)
        ax.set_xticks(x, variantes)
        ax.set_title(bloque.replace("temporada_", "Temporada "))
        ax.set_ylabel(f"Δ {metrica} (variante − referencia)")
        ax.legend(fontsize=8)
    fig.suptitle("Bloque A sobre E3·S4_s2: diferencia frente a la referencia (mediana de 5 semillas)")
    fig.tight_layout()
    return fig


def evaluar_y_resumir(matrices, serie, *, columnas, origenes, preparar_bloque=None) -> dict:
    """``fe_hiperparametros.evaluar_variante`` + ``resumir_variante`` en un paso."""
    r = fh.evaluar_variante(matrices, serie, columnas=columnas, origenes=origenes, preparar_bloque=preparar_bloque)
    return {**r, "resumen": fh.resumir_variante(r["evaluaciones"], serie)}
