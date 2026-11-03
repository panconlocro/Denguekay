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
# Phase 2 · calibration (preregistered before any phase 2 calibration was run)
# ---------------------------------------------------------------------------

PHASE2_EPS_REFERENCE = 1e-6
PHASE2_EPS_SMALL = 1e-15
PHASE2_ISOTONIC_MIN_POSITIVES = 500
PHASE2_AUPRC_VETO = 2            # stricter than GUARD_VETO_AGAINST: AUPRC vetoes with 2 of 5 seasons
PHASE2_CALIBRATION_VETO = 3      # calibrated worse than uncalibrated in >= 3 of 5 seasons: not adoptable
PHASE2_MIN_HORIZONS_WON = 2      # adopted with "gana" in >= 2 horizons and no "pierde"/"compensa"
PHASE2_PARAMETERS = {"platt_agrupado": 2, "platt": 6, "beta": 9, "isotonica": None}  # fewer = simpler

PHASE2 = {
    "fecha": "2026-11-03",
    "estado": "aprobado por Rosa sin cambios (2026-11-03), commiteado antes de calibrar ninguna variante",
    "base": "L de la fase 1a (C3 · E3 · S4_s3, entrenada desde 2005, hiperparámetros de la V1): se recalibran "
            "sus predicciones sin calibrar guardadas (fase1a/predicciones_L.csv.gz, 5 semillas). No se "
            "reentrena nada; μ no cambia, así que la razón MAE es idéntica en todas las variantes",
    "fijo": "alerta p >= 0,50, etiqueta de brote, bloques, cortes y etiquetas cerradas del protocolo de 5 "
            "temporadas (PHASE1['protocolo_nuevo'])",
    "referencia": "Platt por horizonte con recorte del logit 1e-6 (la calibración de L en la 1a)",
    "paso_A_recorte": {
        "candidata": f"Platt por horizonte con recorte {PHASE2_EPS_SMALL:g}",
        "motivo": "en L, 1e-6 aplasta el 6,5 % de las probabilidades sin calibrar (todas las filas, bloques y "
                  "semillas); 1e-15 aplasta el 2,6 %; el 0,02 % es exactamente 0. 1e-15 es el menor recorte "
                  "con 1 - eps distinguible de 1 en float64, así que el recorte sigue siendo simétrico. Las "
                  "fracciones son de la entrada (sin etiquetas), no de resultados",
        "decision": "el recorte que salga de este paso (1e-15 solo si gana con la regla de adopción) se usa en "
                    "el paso B para Platt y beta",
    },
    "paso_B_familias": {
        "platt_agrupado": "un Platt por bloque con las filas de h2, h3 y h4 cuyas etiquetas cerraron antes del "
                          "primero de los tres primeros orígenes del bloque; se aplica a los tres horizontes",
        "beta": "calibración beta de Kull, Silva Filho y Flach (AISTATS 2017, PMLR 54: 623-631): logística sobre "
                "[ln p, -ln(1 - p)], 3 parámetros por horizonte; con a = b es Platt. Monotonía (decisión de este "
                "estudio): si un coeficiente sale negativo, se quita ese término y se reajusta; sin términos, "
                "respaldo Platt",
        "isotonica": f"por horizonte, solo en bloques cuyo calibrador tiene >= {PHASE2_ISOTONIC_MIN_POSITIVES} "
                     "positivos; por debajo, respaldo Platt (por construcción, 2010, con unos 259 positivos, "
                     "queda neutro y la isotónica necesita las otras 4 temporadas a favor). Antecedente: la S5 "
                     "del estudio 04 probó la isotónica con 71-84 positivos en el calibrador de 2022 y empató "
                     "con S1 en E3",
        "umbral_isotonica": "fijado a priori: unas 6 veces los positivos del antecedente S5; no se ajusta",
    },
    "regla": "decide_phase2 = decide_multi_season (5 temporadas, 4 de 5 a favor y ninguna en contra, umbral de "
             "empate por rango entre semillas, antelación con banda ±1/n, F1 y antelación pesan igual) con una "
             f"guarda de AUPRC más estricta: veta si está en contra en >= {PHASE2_AUPRC_VETO} de 5 temporadas "
             "(Brier y razón MAE siguen con 3 de 5)",
    "por_que_auprc_mas_estricta": "un calibrador monótono no cambia el orden dentro de un bloque; la AUPRC solo "
                                  "puede moverse por empates (recorte, escalones de la isotónica) o por un "
                                  "calibrador no monótono. Una caída de AUPRC en esta fase es un artefacto de la "
                                  "calibración, no un cambio del modelo",
    "guarda_calibracion": "por horizonte y temporada que decide, la temporada cuenta en contra si el Brier o el "
                          "log-loss calibrados son mayores que los sin calibrar en las 5 semillas. Si cuenta en "
                          f"contra en >= {PHASE2_CALIBRATION_VETO} de 5 temporadas, la variante no se adopta en "
                          "ningún horizonte. Se reporta también para la referencia",
    "adopcion": f"una variante se adopta si gana en >= {PHASE2_MIN_HORIZONS_WON} de 3 horizontes, ninguno es "
                "«pierde» ni «compensa (empate)» y pasa la guarda de calibración. Si en el paso B se adoptan "
                "varias, se cruzan entre sí con la misma regla; si el cruce empata, se queda la de menos "
                "parámetros (Platt agrupado 2 < Platt por horizonte 6 < beta 9 < isotónica). Si ninguna se "
                "adopta, se queda la referencia. La configuración final usa un solo calibrador en los tres "
                "horizontes",
    "guardas_antes_de_mirar_resultados": [
        "G5: calibrate_variant con Platt por horizonte y 1e-6 reproduce bit a bit "
        "protocol.calibrate_chronologically en las 5 semillas de L",
        "G6: con Platt (por horizonte o agrupado) y beta, la probabilidad calibrada es no decreciente en la sin "
        "calibrar dentro de cada horizonte y bloque",
        "G7: test de no fuga del calibrador: cambiar etiquetas que cierran después del corte de un bloque no "
        "cambia su probabilidad calibrada (por horizonte y agrupado)",
        "si una guarda falla, se detiene la fase y se explica; no se ajusta nada para que pase",
    ],
    "lecturas_que_no_deciden": [
        "2010 aparte, lectura sin 2010 (3 de 4) y 2024 como contraste",
        "parámetros de cada calibrador por bloque (a, b, c; respaldo de beta e isotónica)",
        "curvas de fiabilidad y semanas brote en [0,40, 0,50) por temporada",
        "recall en inicios limpios y antelación frente a la persistencia",
        "HU0007-4 por celda (la regresión no cambia con la calibración)",
        "comparación con la V1 tal cual en 2022-2023 (ganancia de referencia de la 1a)",
    ],
    "multiplicidad": "4 candidatas contra una referencia: la regla exige 4 de 5 temporadas y 2 de 3 horizontes "
                     "para limitar adopciones por azar; las variantes que empatan no se adoptan",
    "mlflow": "denguekay/mejora_modelo_fase2_calibracion",
}


def decide_phase2(candidate: pd.DataFrame, reference: pd.DataFrame, ranges: pd.DataFrame,
                  lead_time_diff: pd.DataFrame) -> pd.DataFrame:
    """The multi-season rule with the stricter AUPRC veto of phase 2 (symmetric)."""
    verdict = decide_multi_season(candidate, reference, ranges, lead_time_diff)
    out = []
    for _, v in verdict.iterrows():
        v = v.copy()
        if v.veredicto == "gana" and v.get("en_contra_auprc", 0) >= PHASE2_AUPRC_VETO:
            v["veredicto"], v["vetos"] = "compensa (empate)", ", ".join(filter(None, [v.vetos, "auprc"]))
        elif v.veredicto == "pierde" and v.get("a_favor_auprc", 0) >= PHASE2_AUPRC_VETO:
            v["veredicto"] = "compensa (empate)"
            v["vetos_contra_referencia"] = ", ".join(filter(None, [v.vetos_contra_referencia, "auprc"]))
        out.append(v)
    return pd.DataFrame(out).reset_index(drop=True)


def adopt_phase2(verdict: pd.DataFrame, calibration_against: pd.Series) -> bool:
    """Adoption of a phase 2 variant: >= 2 horizons won, none lost or offset, calibration guard passed.

    ``calibration_against``: seasons against per horizon (``calibration_guard`` summed by horizon).
    """
    won = int(verdict.veredicto.eq("gana").sum())
    bad = verdict.veredicto.isin(["pierde", "compensa (empate)"]).any()
    vetoed = bool((calibration_against >= PHASE2_CALIBRATION_VETO).any())
    return won >= PHASE2_MIN_HORIZONS_WON and not bad and not vetoed


# ---------------------------------------------------------------------------
# Phase 3 · outbreak onsets (preregistered before training any phase 3 model)
# ---------------------------------------------------------------------------

PHASE3_ONSET_WEIGHT = 5.0
PHASE3_SEASON_WEIGHT_CLIP = (0.25, 1.0)  # Rosa: no season weighs more than today
PHASE3_MIN_REGIME_ROWS = 100
PHASE3_MIN_HORIZONS_WON = 2
PHASE3_SIMPLICITY = ("3a1", "3a2", "3b", "3c")  # a tie in a cross keeps the earlier (simpler) one

PHASE3 = {
    "fecha": "2026-11-03",
    "estado": "aprobado por Rosa (2026-11-03) con dos ajustes (recorte de 3a2 a [0,25, 1]; fiabilidad y Brier por "
              "régimen en 3b y 3c), commiteado antes de entrenar ningún modelo de la fase 3",
    "base": "L: C3 · E3 · S4_s3 entrenada desde 2005 con los hiperparámetros de la V1, Platt por horizonte con "
            "recorte 1e-6 (cierre de la fase 2); bloques por temporada 2008-2024 y calendario_2025",
    "fijo": "alerta p >= 0,50, etiqueta, bloques, cortes, calibración (Platt por horizonte, 1e-6), 5 semillas, "
            "regla de 5 temporadas",
    "por_que": "en L el recall de las 2 primeras semanas de brotes nuevos es 0,12-0,19 en 2022-2023 y 0,02-0,13 en "
               "2010, 2015 y 2016, frente a 0,66-0,89 en brotes en curso; la fase 2 mostró que no es de calibración",
    "brote_nuevo": "semana brote entre las 2 primeras de un episodio con inicio limpio (>= 8 semanas sin brote "
                   "antes), la misma definición de recall_by_week_type; el inicio de un episodio solo depende de "
                   "etiquetas anteriores",
    "variantes": {
        "3a1_peso_inicios": f"sample_weight = {PHASE3_ONSET_WEIGHT:g} para los orígenes de entrenamiento con al "
                            "menos uno de sus tres objetivos en brote nuevo, 1 para el resto. Un solo valor, fijado a "
                            "priori (sin grilla, para no multiplicar comparaciones). La α se estima sin pesos",
        "3a2_peso_temporada": "sample_weight por temporada del objetivo h=2: mediana(C) / C_s, recortado a "
                              f"[{PHASE3_SEASON_WEIGHT_CLIP[0]:g}, {PHASE3_SEASON_WEIGHT_CLIP[1]:g}], con C_s los "
                              "casos objetivo h=2 de los orígenes de entrenamiento del bloque en la temporada s (sin "
                              "casos: el tope). Las temporadas grandes (2017, 2023) pesan menos y ninguna pesa más que hoy (ajuste de "
                              "Rosa: no subir el peso de temporadas casi sin casos, como 2019 y 2020). Se recalcula en cada "
                              "bloque con su entrenamiento",
        "3b_dos_regimenes": "un modelo para orígenes sin brote en la semana de origen (régimen de inicios) y otro "
                            "para orígenes en brote (en curso), mismas columnas e hiperparámetros, cada uno con su α "
                            "por horizonte. El estado es la etiqueta de la semana de origen, conocida al cierre del "
                            "origen. Si un régimen tiene menos de "
                            f"{PHASE3_MIN_REGIME_ROWS} orígenes de entrenamiento en un bloque, ese bloque usa el "
                            "modelo único para ese régimen (se reporta). Un solo Platt por horizonte sobre la "
                            "probabilidad combinada",
        "3c_B1_B2_en_inicios": "3b con B1 (dinámica espacial, 10 columnas) y B2 (distritos núcleo, 3 columnas, "
                               "ranking ajustado con los casos cerrados al corte de cada bloque) solo en el modelo de "
                               "inicios, calculados en memoria sobre la serie larga. Antecedente: en el estudio 05 no "
                               "agregaron sobre B3 en el modelo único, pero la fase 1 los marcó observados en los "
                               "inicios",
    },
    "orden": "3a1, 3a2 y 3b se comparan cada una contra L. 3c se compara contra 3b si 3b se adopta y contra L si "
             "no (y se reporta también frente a 3b). Una a la vez: no se combinan pesos con regímenes en esta fase",
    "regla": "decide_multi_season tal cual (5 temporadas, 4 de 5 a favor y ninguna en contra, umbral de empate por "
             "rango entre semillas, antelación con banda ±1/n, F1 y antelación pesan igual; AUPRC, Brier y razón "
             "MAE vetan con 3 de 5). La AUPRC vuelve al veto general porque aquí el modelo cambia el orden",
    "adopcion": f"gana en >= {PHASE3_MIN_HORIZONS_WON} de 3 horizontes y ningún horizonte «pierde» ni «compensa "
                "(empate)». Si se adoptan varias, se cruzan con la misma regla; un empate en el cruce deja la más "
                "simple (3a1 < 3a2 < 3b < 3c). Si ninguna se adopta, L sigue siendo la base",
    "guardas_antes_de_mirar_resultados": [
        "G8: predict_blocks_weighted sin pesos ni regímenes reproduce bit a bit las predicciones guardadas de L "
        "(fase1a/predicciones_L.csv.gz, μ y probabilidad sin calibrar, semilla 17, todos los bloques), en el "
        "dispositivo de la 1a (cuda, n_jobs = 12). Con pesos iguales a 1 se reporta la diferencia máxima",
        "G9: tests de no fuga: cambiar etiquetas o casos posteriores al corte no cambia los pesos de los orígenes de "
        "entrenamiento (3a1, 3a2); cambiar etiquetas posteriores al cierre del origen no cambia su régimen (3b)",
        "G10 (solo si se llega a 3c): test de no fuga por perturbación de B1 y B2 sobre la serie larga, y B2 con "
        "el ranking del corte del bloque",
        "si una guarda falla, se detiene la fase y se explica; no se ajusta nada para que pase",
    ],
    "lecturas_que_no_deciden": [
        "recall en brote nuevo y en curso por temporada (la pregunta de la fase)",
        "2010 aparte, lectura sin 2010 (3 de 4) y 2024 como contraste",
        "HU0007-4 por celda, con regresión (la razón MAE y RMSE cambian con los pesos y los regímenes)",
        "pesos efectivos por temporada (3a2) y filas y respaldos por régimen (3b)",
        "3b y 3c: curva de fiabilidad y Brier calibrado por régimen (estado al origen), solo lectura (Rosa)",
        "conteo por fase de la curva",
    ],
    "mlflow": "denguekay/mejora_modelo_fase3_inicios",
}


PHASE3_AMENDMENT = {
    "fecha": "2026-11-03",
    "aprobada_por": "Rosa, después de ver 3a1, 3a2 y 3b y antes de entrenar 3c",
    "reemplaza": "3c_B1_B2_en_inicios (B1 + B2 solo en el modelo de inicios de 3b)",
    "variante": "3c_prima: L + B1 + B2 en el modelo único (C3 + B1 + B2 = 22 columnas), mismos hiperparámetros, "
                "α dentro de la muestra, Platt por horizonte con 1e-6; B1 sin ajuste y B2 con el ranking del "
                "núcleo de cada corte de bloque, en memoria sobre la serie larga (casos desde 2000, etiqueta desde "
                "2005)",
    "referencia": "L",
    "regla": "la misma de PHASE3: decide_multi_season y adopt_phase3",
    "motivo": "3b dejó el recall de brote nuevo en 0-0,06 y bajó la antelación en h2, h3 y h4; 3c sobre 3b "
              "partiría de una base que empeora lo que intenta arreglar",
    "no_es_ciega": "la enmienda se hizo después de ver los resultados de 3a y 3b; es anterior a cualquier corrida "
                   "de 3c_prima y se declara en el informe",
    "cierre": "si 3c_prima empata o pierde (no se adopta), la fase 3 se cierra con L como base",
    "guardas": "G10 (tests de no fuga de B1 y B2 y equivalencia con weekly_status en 2017-2025) pasa antes de "
               "entrenar; G8 ya pasó",
}


def adopt_phase3(verdict: pd.DataFrame) -> bool:
    """Adoption of a phase 3 variant: >= 2 horizons won and none lost or offset."""
    won = int(verdict.veredicto.eq("gana").sum())
    bad = verdict.veredicto.isin(["pierde", "compensa (empate)"]).any()
    return won >= PHASE3_MIN_HORIZONS_WON and not bad


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
