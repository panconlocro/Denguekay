"""Preregistration of the model improvement study (fixed before running each phase).

Phase 1 (approved by Rosa on 2026-11-03, before any phase 1 model was trained):

- comparison 1a: the V1 matrix (C3 = ``base_6`` + B3, E3 · S4_s3) trained from 2005
  against the same matrix trained from 2017;
- the new evaluation protocol (seasonal blocks with an expanding window since
  2005, Platt with every earlier closed season) and its multi-season decision
  rule, which decides every comparison from phase 2 on.

``decide_multi_season`` implements that rule. It is symmetric: A loses against
B if and only if B wins against A.
"""

import numpy as np
import pandas as pd

from denguekay.evaluation import protocol as pa

SEEDS = pa.SEEDS
DECIDING_SEASONS = (2010, 2015, 2016, 2022, 2023)
SEPARATE_SEASON = 2010           # reported apart: its block trains with few outbreaks
CONTRAST_SEASON = 2024
MIN_IN_FAVOUR = 4                # primary metric and lead time: seasons in favour out of 5
MAX_AGAINST = 0                  # ... and none against
GUARD_VETO_AGAINST = 3           # a guard vetoes a win if it is against in at least 3 of 5
PHASE1A_SEASONS = (2022, 2023)   # R has no training before 2017
PHASE1A_ADOPT = ("gana", "empate")  # compensa or pierde: stop and consult Rosa
G1_EXCEPTION = {"columna": "propia_semanas_desde_ultimo_caso", "valor_v1": 52,
                "ultimo_cierre": "2017-05-06"}  # amendment G1 (Rosa, 2026-11-03)
DIRECTION = pa.DIRECTION         # f1_050 (primary); auprc, brier, razon_mae (guards)
PRIMARY = pa.PRIMARY
GUARDS = pa.GUARDS


def block_name(season: int) -> str:
    return f"temporada_{season}"


PHASE1 = {
    "fecha": "2026-11-03",
    "aprobado_por": "Rosa (2026-11-03), antes de entrenar ningún modelo de la fase 1",
    "datos": {
        "casos": "silver epi 2000-2016 (ausencias = 0 casos, decisión de Rosa 2026-11-02) + integrado 2017-2025",
        "etiqueta": "regla de gold (media + 1,5 DE de la misma semana en los 5 años previos, >= 2 casos) con "
                    "future_outbreak_threshold; existe desde 2005-S01 y coincide con gold en 2017-2025",
        "socio": "no entra: C3 · S4_s3 no usa columnas socio (la población solo la usa el clasificador, que S4 "
                 "no tiene); el supuesto «socio < 2017 = valor 2017» del plan queda sin uso en la 1a",
        "clima": "no entra en la 1a (A3 es la 1b, cuando el equipo entregue el clima 2000-2016)",
        "pendiente_pipeline": "semana 53 de 2009 en epi_piura_semanal.csv (3 filas, 4 casos en Piura): fuera de "
                              "la grilla MMWR, no se corrige en este estudio",
    },
    "configuracion_comun": {
        "columnas": "base_6 + B3 (las 9 de la V1)",
        "estrategia": "E3", "formulacion": "S4_s3", "dispersion": "dentro_muestra",
        "hiperparametros": "heredados (frozen_configs.CONFIG_2026_V1)",
        "calibracion": "Platt cronológico con todas las temporadas cerradas anteriores al primer origen del "
                       "bloque (protocol.calibrate_chronologically con todos los bloques); recorte del logit 1e-6",
        "alerta": "p >= 0,50", "semillas": list(SEEDS),
    },
    "comparacion_1a": {
        "candidata_L": "C3 · E3 · S4_s3 entrenada con los orígenes cuyos tres objetivos tienen etiqueta "
                       "(desde 2005-S01); bloques por temporada 2008-2024 y calendario_2025; 2008 solo calibra",
        "referencia_R": "la misma configuración entrenada desde 2017 con la tabla de orígenes de la V1 "
                        "(frozen_configs.origins con CONFIG_2026_V1); bloques por temporada 2018-2024 y "
                        "calendario_2025; 2018 solo calibra",
        "temporadas_que_deciden": [2022, 2023],
        "motivo": "R no tiene entrenamiento antes de 2017, así que solo se pueden comparar en 2022-2023 "
                  "(2018-2021 calibran y tienen 1-90 semanas brote)",
        "regla": "decide_multi_season con 2022 y 2023, a favor en las 2 y ninguna en contra (la regla simétrica "
                 "de dos temporadas del estudio 05, protocol.decide), guardas que vetan si están en contra en "
                 "las 2, y la antelación con la banda neutra de ±1/n por temporada; umbral de empate = mayor "
                 "rango entre semillas de L y R",
        "decision": "si L gana o empata, el entrenamiento desde 2005 pasa a ser la base de la 1b y de las fases 2 "
                    "en adelante, con el protocolo de 5 temporadas; si L compensa o pierde, se detiene el estudio "
                    "y se consulta a Rosa (decisión de Rosa, 2026-11-03)",
        "contraste": "2024, no decide",
    },
    "protocolo_nuevo": {
        "bloques": "uno por temporada epidemiológica (semana 35 a 34), ventana creciente; el entrenamiento de "
                   "cada bloque usa los orígenes cuyos tres objetivos cerraron antes del primer origen del bloque",
        "temporadas_que_deciden": list(DECIDING_SEASONS),
        "contraste": CONTRAST_SEASON,
        "aparte": f"{SEPARATE_SEASON}: se reporta en una tabla aparte (entrena con pocos brotes: 2005-2009); "
                  "decide igual que las otras",
        "umbral_de_empate": "por métrica, horizonte y temporada, el mayor rango entre semillas de las dos "
                            "variantes (protocol.seed_ranges + protocol.tie_threshold)",
        "a_favor": "delta (con el signo de la métrica) > umbral de empate",
        "en_contra": "delta < -umbral de empate; un delta dentro de ±umbral es neutro (no cuenta a favor ni "
                     "en contra)",
        "metrica_primaria_mejora": f">= {MIN_IN_FAVOUR} temporadas a favor y {MAX_AGAINST} en contra",
        "metrica_primaria_empeora": f">= {MIN_IN_FAVOUR} temporadas en contra y {MAX_AGAINST} a favor",
        "antelacion": "diferencia pareada por inicio limpio (fracción avisada con >= 2 semanas, semilla 17), IC95 "
                      "bootstrap estratificado por temporada; banda neutra de un inicio por temporada: a favor si "
                      "la diferencia de la temporada es > 1/n, en contra si es < -1/n (n = inicios limpios de esa "
                      "temporada y horizonte); mejora si el IC95 inferior > 0, >= 4 temporadas a favor y ninguna "
                      "en contra (simétrico para empeora)",
        "guardas": f"una guarda veta una victoria si está en contra en >= {GUARD_VETO_AGAINST} de 5 temporadas "
                   "(y veta una derrota si está a favor en >= 3)",
        "veredicto": "F1 y antelación son las dos primarias y pesan igual. «Mejora» = mejora F1 o mejora la "
                     "antelación; «empeora» = empeora F1 o empeora la antelación. Gana: mejora, no empeora y "
                     "ninguna guarda la veta. Pierde: empeora, no mejora y ninguna guarda veta a la referencia. "
                     "Compensa (empate): una primaria mejora y la otra empeora, o hay mejora (o empeora) pero una "
                     "guarda la veta. Empate: ninguna primaria se mueve fuera de su banda neutra",
        "lectura_sin_2010": "la misma regla con 2015, 2016, 2022 y 2023 (>= 3 de 4 a favor y ninguna en "
                            "contra); solo lectura",
        "minimos_por_celda": "HU0007-4 y antelación con los mínimos de EVALUATION_2026 (30 semanas brote, "
                             "20 inicios limpios); por debajo, «no evaluable»",
    },
    "guardas_antes_de_mirar_resultados": [
        "G1: en los orígenes comunes, base_6 + B3 de la tabla larga son iguales a los de "
        "frozen_configs.origins(CONFIG_2026_V1) (atol 1e-12), con la excepción de la enmienda G1",
        "G2: R reproduce bit a bit, con la semilla 17, las predicciones guardadas de la V1 en los bloques "
        "2021-2025 (fase4/predicciones_s4s3_dentro_muestra.csv.gz), comparando las predicciones sin calibrar "
        "(μ = casos_predichos y probabilidad NB2 antes de Platt), con el dispositivo con que se grabaron "
        "(cuda, n_jobs = 12, XGBoost 3.4.1, Windows; MLflow fe_hiperparametros_fase4_verificacion). Si no "
        "coinciden exactamente o el dispositivo no está, se reporta la diferencia máxima y se detiene la fase",
        "G3: la etiqueta larga es igual a la de gold en 2017-2025 (verificado en la fase 0)",
        "G4: test de no fuga por perturbación de la tabla de orígenes larga (cambiar casos posteriores al "
        "origen no cambia sus variables)",
        "si una guarda falla, se detiene la fase y se explica; no se ajusta nada para que pase",
    ],
    "enmienda_G1": {
        "fecha": "2026-11-03", "aprobada_por": "Rosa, antes de entrenar ningún modelo de la fase 1",
        "motivo": "G1 falló en 134 de 30 160 orígenes (20 distritos, cierres del 2017-01-28 al 2017-05-06), solo "
                  "en propia_semanas_desde_ultimo_caso: la V1 la calcula sin las semanas anteriores a 2017 y da el "
                  "tope 52 a distritos que aún no tenían casos en 2017; la tabla larga ve su último caso de 2016",
        "regla": "se exceptúan de G1 los orígenes con propia_semanas_desde_ultimo_caso = 52 en la V1 y cierre "
                 "hasta el 2017-05-06; en ellos la tabla larga debe dar < 52 e igual a las semanas desde el último "
                 "caso recalculadas directamente desde la serie de casos larga. Las otras 8 columnas siguen "
                 "exigiendo igualdad en todos los orígenes",
        "consecuencia": "L usa los valores largos; R conserva la tabla exacta de la V1 (G2 no cambia). Esas filas "
                        "forman parte de la diferencia L - R y se declaran en el informe",
    },
    "lecturas_que_no_deciden": [
        "V1 tal cual (Platt solo con 2021) frente a R: efecto de calibrar con 2018-2021",
        "L en 2010 (aparte), 2015, 2016, 2017 y 2024: métricas por celda con su número de positivos",
        "recall en inicios limpios y antelación frente a la persistencia (IC por temporada)",
        "HU0007-4 por celda de L en las temporadas que deciden y en 2024",
        "conteo por fase de la curva (MAE y RMSE juntos)",
    ],
    "mlflow": "denguekay/mejora_modelo_fase1a_historia",
}


# ---------------------------------------------------------------------------
# Multi-season decision rule (phases 2 onwards and 1b)
# ---------------------------------------------------------------------------

def _season_signs(delta: dict[int, float], threshold: dict[int, float]) -> tuple[int, int]:
    in_favour = sum(delta[b] > threshold[b] for b in delta)
    against = sum(delta[b] < -threshold[b] for b in delta)
    return in_favour, against


def decide_phase1a(candidate: pd.DataFrame, reference: pd.DataFrame, ranges: pd.DataFrame,
                   lead_time_diff: pd.DataFrame) -> pd.DataFrame:
    """Comparison 1a: the multi-season rule with 2022 and 2023, both in favour and guards vetoing in both."""
    n = len(PHASE1A_SEASONS)
    return decide_multi_season(candidate, reference, ranges, lead_time_diff, seasons=PHASE1A_SEASONS,
                               min_in_favour=n, guard_veto=n)


def decide_multi_season(candidate: pd.DataFrame, reference: pd.DataFrame, ranges: pd.DataFrame,
                        lead_time_diff: pd.DataFrame, seasons: tuple[int, ...] = DECIDING_SEASONS,
                        min_in_favour: int = MIN_IN_FAVOUR, guard_veto: int = GUARD_VETO_AGAINST) -> pd.DataFrame:
    """Preregistered verdict per horizon over several deciding seasons.

    ``candidate`` and ``reference``: seed medians per ``horizonte`` and ``bloque``;
    ``ranges``: tie threshold per metric (``protocol.tie_threshold``);
    ``lead_time_diff``: one row per horizon with ``ic95_inferior``,
    ``ic95_superior``, ``diferencia_<block>`` and ``episodios_<block>`` for every
    deciding season. A season's lead-time difference counts in favour only
    beyond one onset (``> 1/n``) and against only below ``-1/n``.
    """
    blocks = [block_name(s) for s in seasons]
    rows = []
    for h in sorted(candidate.horizonte.unique()):
        c = candidate[candidate.horizonte.eq(h)].set_index("bloque")
        r = reference[reference.horizonte.eq(h)].set_index("bloque")
        e = ranges[ranges.horizonte.eq(h)].set_index("bloque")
        counts = {}
        for m in DIRECTION:
            if m not in c or m not in r:
                continue
            delta = {b: DIRECTION[m] * (c.at[b, m] - r.at[b, m]) for b in blocks}
            counts[m] = _season_signs(delta, {b: e.at[b, m] for b in blocks})
        improves = {m: f >= min_in_favour and a == 0 for m, (f, a) in counts.items()}
        worsens = {m: a >= min_in_favour and f == 0 for m, (f, a) in counts.items()}
        lead = lead_time_diff[lead_time_diff.horizonte.eq(h)].iloc[0]
        lead_delta = {b: float(lead[f"diferencia_{b}"]) for b in blocks}
        # Neutral band of one onset per season (Rosa, 2026-11-03).
        lead_f, lead_a = _season_signs(lead_delta, {b: 1 / float(lead[f"episodios_{b}"]) for b in blocks})
        improves_lead = bool(lead.ic95_inferior > 0 and lead_f >= min_in_favour and lead_a == 0)
        worsens_lead = bool(lead.ic95_superior < 0 and lead_a >= min_in_favour and lead_f == 0)
        improves_primary = any(improves.get(m, False) for m in PRIMARY) or improves_lead
        worsens_primary = any(worsens.get(m, False) for m in PRIMARY) or worsens_lead
        veto_a = [m for m in GUARDS if m in counts and counts[m][1] >= guard_veto]
        veto_b = [m for m in GUARDS if m in counts and counts[m][0] >= guard_veto]
        if improves_primary and not worsens_primary and not veto_a:
            verdict = "gana"
        elif worsens_primary and not improves_primary and not veto_b:
            verdict = "pierde"
        elif improves_primary or worsens_primary:
            verdict = "compensa (empate)"
        else:
            verdict = "empate"
        rows.append({"horizonte": h, "veredicto": verdict,
                     "mejora_antelacion": improves_lead, "empeora_antelacion": worsens_lead,
                     "vetos": ", ".join(veto_a) or None, "vetos_contra_referencia": ", ".join(veto_b) or None,
                     **{f"a_favor_{m}": f for m, (f, _) in counts.items()},
                     **{f"en_contra_{m}": a for m, (_, a) in counts.items()},
                     "a_favor_antelacion": lead_f, "en_contra_antelacion": lead_a})
    return pd.DataFrame(rows)


def lead_time_difference_multi(table_a: pd.DataFrame, table_b: pd.DataFrame, alert: str,
                               seasons: tuple[int, ...] = DECIDING_SEASONS) -> pd.DataFrame:
    """Paired A - B lead-time difference over the deciding seasons (generalises ``protocol.lead_time_difference``)."""
    blocks = [block_name(s) for s in seasons]
    key = ["horizonte", "bloque", "ubigeo", "inicio"]
    a, b = table_a[table_a.bloque.isin(blocks)], table_b[table_b.bloque.isin(blocks)]
    pairs = a[key + [alert]].merge(b[key + [alert]], on=key, suffixes=("_a", "_b"), validate="one_to_one")
    if len(pairs) != len(a) or len(pairs) != len(b):
        raise ValueError("Las variantes no comparten los mismos episodios")
    rows = []
    for h, g in pairs.groupby("horizonte"):
        diff = (g[f"{alert}_a"].ge(pa.MIN_LEAD_TIME).to_numpy(float)
                - g[f"{alert}_b"].ge(pa.MIN_LEAD_TIME).to_numpy(float))
        means = pa.stratified_bootstrap(diff, g.bloque.to_numpy())
        rows.append({"horizonte": h, "episodios": len(g), "diferencia": float(diff.mean()),
                     "ic95_inferior": float(np.quantile(means, 0.025)),
                     "ic95_superior": float(np.quantile(means, 0.975)),
                     **{f"diferencia_{bl}": float(diff[g.bloque.eq(bl).to_numpy()].mean()) for bl in blocks},
                     **{f"episodios_{bl}": int(g.bloque.eq(bl).sum()) for bl in blocks}})
    return pd.DataFrame(rows)
