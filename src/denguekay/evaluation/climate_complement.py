"""Complementary study: gold climate (A3) on top of the final configuration, with a count rule.

A single comparison (number 20 of the FE study): F+A3 (C3 + the 2 A3 columns)
against F∩A3 (the final configuration retrained without the same rows with A3
start-up nulls). The protocol (``protocolo_arquitectura``) does not change; this
module's rule was preregistered before running (``COMPLEMENT_PREREGISTRATION``).
"""

import numpy as np
import pandas as pd

from denguekay.features import variant_registry as pr
from denguekay.evaluation.metrics import alert_metrics
from denguekay.evaluation import protocol as pa

A3_COLUMNS = next(list(v["columnas"]) for v in pr.VARIANTS if v["id"] == "A3")
COUNT_METRICS = ("razon_mae", "razon_rmse")
LOSING_VERDICT = "pierde"

COMPLEMENT_PREREGISTRATION = {
    "fecha": "2026-10-27, antes de cualquier corrida del complemento (encargo de Rosa)",
    "comparacion": "20 del encargo de FE (única del complemento)",
    "referencia": "F∩A3: configuración final (CONFIGURACION_2026, C3, 9 columnas) sin las filas con nulos de "
                  "arranque de A3",
    "candidata": "F+A3: C3 + hum_rel_media_media5_h2 y precip_total_mm_media5_h2 (11 columnas), todo lo demás "
                 "idéntico (E3 · S4_s3 · α dentro de la muestra · hiperparámetros heredados · Platt · p ≥ 0,50)",
    "lectura": "F completa (9 columnas, todas las filas) solo como referencia de lectura",
    "semillas": list(pa.SEEDS),
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


def _by_seed(evaluations: dict[int, dict]) -> pd.DataFrame:
    return pd.concat([r["metricas"].assign(semilla=s) for s, r in evaluations.items()], ignore_index=True)


def count_table(evaluations_a: dict[int, dict], evaluations_b: dict[int, dict],
                 blocks: tuple[str, ...] = pa.SELECTION_BLOCKS) -> pd.DataFrame:
    """Median delta (a - b) and tie threshold of each ratio, per horizon and season."""
    a, b = _by_seed(evaluations_a), _by_seed(evaluations_b)
    rows = []
    for h in sorted(a.horizonte.unique()):
        for block in blocks:
            ga = a[a.horizonte.eq(h) & a.bloque.eq(block)]
            gb = b[b.horizonte.eq(h) & b.bloque.eq(block)]
            for m in COUNT_METRICS:
                threshold = max(ga[m].max() - ga[m].min(), gb[m].max() - gb[m].min())
                delta = ga[m].median() - gb[m].median()
                rows.append({"horizonte": int(h), "bloque": block, "metrica": m, "mediana_candidata": ga[m].median(),
                              "mediana_referencia": gb[m].median(), "delta": delta, "umbral": threshold,
                              "baja": delta < -threshold, "sube": delta > threshold})
    return pd.DataFrame(rows)


def count_condition(table: pd.DataFrame, blocks: tuple[str, ...] = pa.SELECTION_BLOCKS) -> pd.DataFrame:
    """Count improves / worsens per horizon according to condition 1."""
    rows = []
    for h, g in table.groupby("horizonte"):
        g = g[g.bloque.isin(blocks)].set_index(["metrica", "bloque"])
        improves = all(bool(g.at[(m, b), "baja"]) for m in COUNT_METRICS for b in blocks)
        worsens = any(all(bool(g.at[(m, b), "sube"]) for b in blocks) for m in COUNT_METRICS)
        rows.append({"horizonte": int(h), "mejora_conteo": improves, "empeora_conteo": worsens})
    return pd.DataFrame(rows)


def decide(count: pd.DataFrame, verdict: pd.DataFrame) -> dict:
    """Condition 1 (count), condition 2 (the alert does not lose) and decision."""
    c1 = bool(count.mejora_conteo.any() and not count.empeora_conteo.any())
    loses = verdict.veredicto.eq(LOSING_VERDICT)
    c2 = not bool(loses.any())
    return {"condicion_1_conteo": c1, "condicion_2_alerta_no_pierde": c2,
            "horizontes_mejora_conteo": count.loc[count.mejora_conteo, "horizonte"].tolist(),
            "horizontes_empeora_conteo": count.loc[count.empeora_conteo, "horizonte"].tolist(),
            "horizontes_pierde_alerta": verdict.loc[loses, "horizonte"].tolist(),
            "adoptada": "F+A3" if c1 and c2 else "F"}


def reading_table(evaluations: dict[int, dict], name: str,
                  blocks: tuple[str, ...] = (*pa.SELECTION_BLOCKS, pa.CONTRAST_BLOCK)) -> pd.DataFrame:
    """Median and range across seeds of P, R, F1, AUPRC, Brier, ratios and absolute MAE/RMSE."""
    columns = ["precision_050", "recall_050", "f1_050", "auprc", "brier", "razon_mae", "razon_rmse", "mae", "rmse"]
    t = _by_seed(evaluations)
    t = t[t.bloque.isin(blocks)]
    g = t.groupby(["horizonte", "bloque"])[columns]
    return (g.median().join((g.max() - g.min()).add_prefix("rango_")).reset_index().assign(variante=name))


def cell_diagnosis(evaluations: dict[int, dict], horizon: int, block: str,
                      band: tuple[float, float] = (0.40, 0.50)) -> pd.DataFrame:
    """Discrimination or calibration? One row per seed for a cell (reading, it does not decide).

    AUPRC (the same with the calibrated or the raw probability: Platt is monotonic),
    calibrated and raw Brier, mean calibrated probability against prevalence,
    P / R / F1 at 0.50 and outbreak weeks with calibrated probability in
    ``[band[0], band[1])``.
    """
    rows = []
    for s, r in evaluations.items():
        g = r["datos"]
        g = g[g.horizonte.eq(horizon) & g.bloque.eq(block)]
        y = g.brote.to_numpy(int)
        cal, raw = g.probabilidad_calibrada.to_numpy(float), g.probabilidad_brote.to_numpy(float)
        m = alert_metrics(y, (cal >= pa.ALERT_THRESHOLD).astype(int), score=cal)
        in_band = (cal >= band[0]) & (cal < band[1])
        rows.append({"semilla": s, "semanas": len(y), "semanas_brote": int(y.sum()), "prevalencia": float(y.mean()),
                      "probabilidad_calibrada_media": float(cal.mean()), "probabilidad_cruda_media": float(raw.mean()),
                      "auprc": m["auprc"], "brier_calibrado": float(np.mean((cal - y) ** 2)),
                      "brier_sin_calibrar": float(np.mean((raw - y) ** 2)),
                      "precision_050": m["precision"], "recall_050": m["recall"], "f1_050": m["f1"],
                      "brote_en_banda": int((in_band & (y == 1)).sum()),
                      "brote_con_alerta": int(((cal >= pa.ALERT_THRESHOLD) & (y == 1)).sum())})
    return pd.DataFrame(rows)
