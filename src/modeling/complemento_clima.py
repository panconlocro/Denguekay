"""Encargo complementario: clima de gold (A3) sobre la configuración final, con regla de conteo.

Una sola comparación (la 20 del encargo de FE): F+A3 (C3 + las 2 columnas de A3)
frente a F∩A3 (la configuración final reentrenada sin las mismas filas con nulos
de arranque de A3). El protocolo (``protocolo_arquitectura``) no cambia; la
regla de este módulo se preregistró antes de correr (``PREREGISTRO_COMPLEMENTO``).
"""

import pandas as pd

from src.modeling import preregistro_fe as pr
from src.modeling import protocolo_arquitectura as pa

COLUMNAS_A3 = next(list(v["columnas"]) for v in pr.VARIANTES if v["id"] == "A3")
METRICAS_CONTEO = ("razon_mae", "razon_rmse")
VEREDICTO_PIERDE = "pierde"

PREREGISTRO_COMPLEMENTO = {
    "fecha": "2026-10-27, antes de cualquier corrida del complemento (encargo de Rosa)",
    "comparacion": "20 del encargo de FE (única del complemento)",
    "referencia": "F∩A3: configuración final (CONFIGURACION_2026, C3, 9 columnas) sin las filas con nulos de "
                  "arranque de A3",
    "candidata": "F+A3: C3 + hum_rel_media_media5_h2 y precip_total_mm_media5_h2 (11 columnas), todo lo demás "
                 "idéntico (E3 · S4_s3 · α dentro de la muestra · hiperparámetros heredados · Platt · p ≥ 0,50)",
    "lectura": "F completa (9 columnas, todas las filas) solo como referencia de lectura",
    "semillas": list(pa.SEMILLAS),
    "umbral_empate": "por métrica, horizonte y temporada, el mayor rango entre semillas (máx − mín) de las dos "
                     "variantes; para la razón MAE y la razón RMSE, sobre la razón por semilla",
    "delta": "mediana de las 5 semillas de F+A3 menos mediana de F∩A3 (convención del protocolo)",
    "desigualdades": "estrictas",
    "condicion_1_conteo": {
        "mejora_en_h": "razón MAE y razón RMSE bajan más que su umbral en 2022 y en 2023",
        "empeora_en_h": "razón MAE o razón RMSE suben más que su umbral en 2022 y en 2023",
        "se_cumple": "mejora en al menos un horizonte y no empeora en ninguno",
    },
    "condicion_2_alerta": "regla simétrica del protocolo (F1 a 0,50 y antelación primarios; AUPRC, Brier y razón "
                          "MAE guardas) de F+A3 frente a F∩A3; se cumple si ningún horizonte da «pierde» "
                          "(gana, empate y compensa son aceptables)",
    "decision": "si se cumplen las dos, se adopta F+A3 y hay configuración congelada nueva (fecha = commit de la "
                "constante nueva); si no, se queda F y el congelamiento sigue en 2026-10-27",
    "no_decide": "2024 es contraste; 2025 solo sensibilidad de conteos; robustez sin las 8 primeras semanas de "
                 "2017, SHAP, antelación, recall de brotes nuevos y conteo por fase son lectura",
}


def _por_semilla(evaluaciones: dict[int, dict]) -> pd.DataFrame:
    return pd.concat([r["metricas"].assign(semilla=s) for s, r in evaluaciones.items()], ignore_index=True)


def tabla_conteo(evaluaciones_a: dict[int, dict], evaluaciones_b: dict[int, dict],
                 bloques: tuple[str, ...] = pa.BLOQUES_SELECCION) -> pd.DataFrame:
    """Delta de medianas (a − b) y umbral de empate de cada razón, por horizonte y temporada."""
    a, b = _por_semilla(evaluaciones_a), _por_semilla(evaluaciones_b)
    filas = []
    for h in sorted(a.horizonte.unique()):
        for bloque in bloques:
            ga = a[a.horizonte.eq(h) & a.bloque.eq(bloque)]
            gb = b[b.horizonte.eq(h) & b.bloque.eq(bloque)]
            for m in METRICAS_CONTEO:
                umbral = max(ga[m].max() - ga[m].min(), gb[m].max() - gb[m].min())
                delta = ga[m].median() - gb[m].median()
                filas.append({"horizonte": int(h), "bloque": bloque, "metrica": m, "mediana_candidata": ga[m].median(),
                              "mediana_referencia": gb[m].median(), "delta": delta, "umbral": umbral,
                              "baja": delta < -umbral, "sube": delta > umbral})
    return pd.DataFrame(filas)


def condicion_conteo(tabla: pd.DataFrame, bloques: tuple[str, ...] = pa.BLOQUES_SELECCION) -> pd.DataFrame:
    """Mejora / empeora del conteo por horizonte según la condición 1."""
    filas = []
    for h, g in tabla.groupby("horizonte"):
        g = g[g.bloque.isin(bloques)].set_index(["metrica", "bloque"])
        mejora = all(bool(g.at[(m, b), "baja"]) for m in METRICAS_CONTEO for b in bloques)
        empeora = any(all(bool(g.at[(m, b), "sube"]) for b in bloques) for m in METRICAS_CONTEO)
        filas.append({"horizonte": int(h), "mejora_conteo": mejora, "empeora_conteo": empeora})
    return pd.DataFrame(filas)


def decidir(conteo: pd.DataFrame, veredicto: pd.DataFrame) -> dict:
    """Condición 1 (conteo), condición 2 (la alerta no pierde) y decisión."""
    c1 = bool(conteo.mejora_conteo.any() and not conteo.empeora_conteo.any())
    pierde = veredicto.veredicto.eq(VEREDICTO_PIERDE)
    c2 = not bool(pierde.any())
    return {"condicion_1_conteo": c1, "condicion_2_alerta_no_pierde": c2,
            "horizontes_mejora_conteo": conteo.loc[conteo.mejora_conteo, "horizonte"].tolist(),
            "horizontes_empeora_conteo": conteo.loc[conteo.empeora_conteo, "horizonte"].tolist(),
            "horizontes_pierde_alerta": veredicto.loc[pierde, "horizonte"].tolist(),
            "adoptada": "F+A3" if c1 and c2 else "F"}


def tabla_lectura(evaluaciones: dict[int, dict], nombre: str,
                  bloques: tuple[str, ...] = (*pa.BLOQUES_SELECCION, pa.BLOQUE_CONTRASTE)) -> pd.DataFrame:
    """Mediana y rango entre semillas de P, R, F1, AUPRC, Brier, razones y MAE/RMSE absolutos."""
    columnas = ["precision_050", "recall_050", "f1_050", "auprc", "brier", "razon_mae", "razon_rmse", "mae", "rmse"]
    t = _por_semilla(evaluaciones)
    t = t[t.bloque.isin(bloques)]
    g = t.groupby(["horizonte", "bloque"])[columnas]
    return (g.median().join((g.max() - g.min()).add_prefix("rango_")).reset_index().assign(variante=nombre))
