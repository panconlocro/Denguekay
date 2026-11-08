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
# Phase 5 · counts (preregistered before running any phase 5 variant)
# ---------------------------------------------------------------------------

PHASE5_PRIMARY = "razon_mae"
PHASE5_GUARDS = ("razon_rmse", "f1_050", "auprc", "brier")
PHASE5_DIRECTION = {"razon_mae": -1, "razon_rmse": -1, "f1_050": 1, "auprc": 1, "brier": -1}
PHASE5_MIN_HORIZONS_WON = 2
PHASE5_SIMPLICITY = ("5a", "5c", "5b")  # a tie in a cross keeps the earlier (simpler) one

PHASE5 = {
    "fecha": "2026-11-03",
    "estado": "aprobado por Rosa (2026-11-03) con una lectura agregada (probabilidad desde la μ mezclada), "
              "commiteado antes de correr ninguna variante de la fase 5",
    "base": "L: C3 · E3 · S4_s3 desde 2005, hiperparámetros de la V1 (max_delta_step 0,7), Platt por horizonte "
            "con 1e-6 (cierre de las fases 2 y 3); predicciones guardadas de la 1a, 5 semillas",
    "por_que": "la HU0007-4 pide razón MAE y RMSE <= 0,85; L solo la cumple en 2023 · h4 y 2017 · h3/h4",
    "variantes": {
        "5a_mezcla": "conteo = w·μ + (1 - w)·persistencia, por horizonte y bloque. w de la grilla 0,00-1,00 (paso "
                     "0,01) que minimiza el MAE en las predicciones fuera de muestra de los bloques anteriores "
                     "del mismo horizonte cuya etiqueta cerró antes del primer origen del bloque (los datos "
                     "disponibles al corte, como el Platt cronológico); empate -> el w mayor (más cerca de L); "
                     "sin filas previas (2008), w = 1. Solo cambia el conteo: la probabilidad sigue saliendo del μ "
                     "de L, así que F1, AUPRC, Brier y antelación quedan iguales por construcción. No se "
                     "reentrena",
        "5b_max_delta_step": "por bloque y semilla, max_delta_step de la grilla {0,7; 1; 2; 3; 5; 10} elegido "
                             "con una validación interna dentro del entrenamiento del bloque: valida con los "
                             "orígenes cuyo objetivo h=2 cae en la última temporada del entrenamiento y entrena "
                             "con los que tienen el objetivo h=4 en temporadas anteriores (sin solapamiento); "
                             "criterio: MAE medio de h2-h4; empate -> el más cercano a 0,7. Después se reentrena "
                             "con todo el entrenamiento del bloque. Cambia μ y la probabilidad",
        "5c_peso_temporada": "3a2 de la fase 3 (peso por temporada [0,25, 1]), con sus predicciones guardadas "
                             "(fase3/predicciones_3a2.csv.gz). Entra porque en la fase 3 mejoró la razón MAE "
                             "(3-4 de 5 temporadas a favor por horizonte). No es ciega: esas cifras ya se "
                             "vieron, así que su veredicto con la regla de esta fase es en buena parte previsible",
    },
    "regla": "decide_phase5: la misma mecánica de 5 temporadas con la razón MAE como métrica primaria (mejora "
             "con >= 4 temporadas a favor y ninguna en contra, umbral de empate = mayor rango entre semillas de "
             "las dos variantes). Guardas que vetan con >= 3 de 5 en contra: razón RMSE (MAE y RMSE siempre "
             "juntos), F1, AUPRC y Brier. La antelación veta si empeora (IC95 superior < 0 y >= 4 temporadas en "
             "contra con la banda ±1/n). Veredictos: gana / pierde / compensa (empate) / empate, simétricos",
    "adopcion": f"gana en >= {PHASE5_MIN_HORIZONS_WON} de 3 horizontes y ninguno «pierde» ni «compensa "
                "(empate)». Si se adoptan varias, se cruzan con la misma regla; un empate deja la más simple "
                "(5a < 5c < 5b). Las combinaciones quedan para la fase 7",
    "guardas_antes_de_mirar_resultados": [
        "G11: la mezcla con w = 1 en todos los bloques devuelve exactamente el conteo de L; test de no fuga del "
        "ajuste de w (cambiar etiquetas y casos que cierran después del corte no cambia w)",
        "G12: 5b con la grilla {0,7} reproduce bit a bit las predicciones de L (semilla 17, cuda, n_jobs = 12); "
        "test de no fuga de la selección (solo usa orígenes de entrenamiento)",
        "G13: las predicciones guardadas de 3a2 tienen las 5 semillas y las mismas filas que L",
        "si una guarda falla, se detiene la fase y se explica; no se ajusta nada para que pase",
    ],
    "lecturas_que_no_deciden": [
        "conteo por fase de la curva (valle, subida, pico, bajada), siempre MAE y RMSE juntos",
        "HU0007-4 de regresión por celda (razón MAE y RMSE <= 0,85)",
        "w por horizonte y bloque (5a) y max_delta_step elegido por bloque y semilla (5b)",
        "2010 aparte, lectura sin 2010 (3 de 4) y 2024 como contraste",
        "5a con la misma μ (Rosa): la probabilidad NB2 se calcula con la μ mezclada y la α de L del bloque, "
        "horizonte y semilla, y luego Platt por horizonte con 1e-6; F1, AUPRC y Brier frente a L, para saber si "
        "casos, probabilidad e intervalo pueden salir de la misma μ. Antes se comprueba que NB2 con la μ y la α "
        "de L reproduce la probabilidad guardada de L",
    ],
    "mlflow": "denguekay/mejora_modelo_fase5_conteo",
}


def decide_phase5(candidate: pd.DataFrame, reference: pd.DataFrame, ranges: pd.DataFrame,
                  lead_time_diff: pd.DataFrame, seasons: tuple[int, ...] = DECIDING_SEASONS,
                  min_in_favour: int = MIN_IN_FAVOUR, guard_veto: int = GUARD_VETO_AGAINST) -> pd.DataFrame:
    """Phase 5 verdict per horizon: the razón MAE decides; RMSE ratio, F1, AUPRC, Brier and lead time guard."""
    blocks = [block_name(s) for s in seasons]
    rows = []
    for h in sorted(candidate.horizonte.unique()):
        c = candidate[candidate.horizonte.eq(h)].set_index("bloque")
        r = reference[reference.horizonte.eq(h)].set_index("bloque")
        e = ranges[ranges.horizonte.eq(h)].set_index("bloque")
        counts = {m: _season_signs({b: d * (c.at[b, m] - r.at[b, m]) for b in blocks}, {b: e.at[b, m] for b in blocks})
                  for m, d in PHASE5_DIRECTION.items()}
        f, a = counts[PHASE5_PRIMARY]
        improves, worsens = f >= min_in_favour and a == 0, a >= min_in_favour and f == 0
        lead = lead_time_diff[lead_time_diff.horizonte.eq(h)].iloc[0]
        lf, la = _season_signs({b: float(lead[f"diferencia_{b}"]) for b in blocks},
                               {b: 1 / float(lead[f"episodios_{b}"]) for b in blocks})
        lead_worse = bool(lead.ic95_superior < 0 and la >= min_in_favour and lf == 0)
        lead_better = bool(lead.ic95_inferior > 0 and lf >= min_in_favour and la == 0)
        veto_a = [m for m in PHASE5_GUARDS if counts[m][1] >= guard_veto] + (["antelacion"] if lead_worse else [])
        veto_b = [m for m in PHASE5_GUARDS if counts[m][0] >= guard_veto] + (["antelacion"] if lead_better else [])
        if improves and not veto_a:
            verdict = "gana"
        elif worsens and not veto_b:
            verdict = "pierde"
        elif improves or worsens:
            verdict = "compensa (empate)"
        else:
            verdict = "empate"
        rows.append({"horizonte": h, "veredicto": verdict, "vetos": ", ".join(veto_a) or None,
                     "vetos_contra_referencia": ", ".join(veto_b) or None,
                     **{f"a_favor_{m}": v[0] for m, v in counts.items()},
                     **{f"en_contra_{m}": v[1] for m, v in counts.items()},
                     "a_favor_antelacion": lf, "en_contra_antelacion": la})
    return pd.DataFrame(rows)


def adopt_phase5(verdict: pd.DataFrame) -> bool:
    """Adoption of a phase 5 variant: >= 2 horizons won and none lost or offset."""
    won = int(verdict.veredicto.eq("gana").sum())
    bad = verdict.veredicto.isin(["pierde", "compensa (empate)"]).any()
    return won >= PHASE5_MIN_HORIZONS_WON and not bad


# ---------------------------------------------------------------------------
# Phase 6 (reading, does not decide; approved by Rosa on 2026-11-03 before running)
# ---------------------------------------------------------------------------

PHASE6_GLM_LOG1P = ("hist_lag_a", "hist_lag_b", "hist_media_4")
PHASE6_GLM_MAXITER = 200
PHASE6_LGBM = {"n_estimators": 160, "max_depth": 3, "num_leaves": 8, "learning_rate": 0.05,
               "min_sum_hessian_in_leaf": 5.0, "min_child_samples": 1, "bagging_fraction": 0.8, "bagging_freq": 1,
               "feature_fraction": 0.9, "lambda_l2": 5.0, "lambda_l1": 0.0, "poisson_max_delta_step": 0.7}
PHASE6_PRIME_CLIMATE = ("hum_rel_media_media5_h2", "precip_total_mm_media5_h2")  # A3 of the V2

PHASE6 = {
    "fecha": "2026-11-03",
    "estado": "aprobado por Rosa (2026-11-03) tal cual, commiteado antes de correr ninguna familia de la fase 6",
    "por_que": "saber si XGBoost es el límite o si lo son los datos. Es una lectura: ninguna familia se adopta en "
               "este estudio",
    "base": "L + 5a: L (C3 · E3 · S4_s3 desde 2005, hiperparámetros de la V1) con las predicciones guardadas de "
            "la 1a y la mezcla 5a del conteo (dos μ: casos desde la μ mezclada, probabilidad desde la μ del modelo)",
    "comun": "los mismos orígenes largos desde 2005 y la misma matriz C3 (9 columnas de rezagos de casos y "
             "calendario de la V1, sin clima); los mismos bloques (2008-2024 + calendario_2025) y cortes de "
             "entrenamiento (`phase3_onsets._training`); probabilidad NB2 con α dentro de la muestra (estimador "
             "de L, `negative_binomial_dispersion`) -> Platt por horizonte con recorte 1e-6 -> alerta p >= 0,50; "
             "el conteo con la mezcla 5a aplicada a cada familia, y además la μ sin mezclar",
    "familias": {
        "6a_nb_glm": "un GLM NB2 por horizonte (statsmodels `NegativeBinomial`, loglike nb2, máxima verosimilitud, "
                     f"maxiter {PHASE6_GLM_MAXITER}) con intercepto y offset log(hist_lag_a + 0,5) (el margen de "
                     f"S4_s3). Columnas: las 9 de C3; {', '.join(PHASE6_GLM_LOG1P)} entran como log(x + 1); todas "
                     "se estandarizan con la media y la desviación del entrenamiento de cada bloque. Sin "
                     "penalización; determinista (una corrida, repetida en las 5 claves de semilla). Un bloque "
                     "que no converge se marca y se reporta; no se ajusta nada",
        "6b_lightgbm": "LightGBM `objective=poisson`, un modelo por horizonte (no hay árboles multisalida: "
                       "diferencia declarada frente a E3), con init_score = margen de L. Hiperparámetros de la V1 "
                       f"traducidos: {PHASE6_LGBM}; deterministic=True, force_row_wise, CPU, 5 semillas. Sin "
                       "búsqueda de hiperparámetros",
    },
    "lectura": "cada familia frente a L + 5a, por bloque y horizonte con su número de positivos: F1, AUPRC, Brier, "
               "razón MAE y RMSE juntas, antelación; veredictos con la regla de 5 temporadas de la fase 3 "
               "(`decide_multi_season`, F1) y de la fase 5 (`decide_phase5`, razón MAE), marcados como lectura; "
               "2010 aparte, sin 2010 (3 de 4) y 2024 como contraste",
    "interpretacion": "si las dos empatan o pierden: indicio (no prueba) de que el límite son los datos. Si alguna "
                      "gana: hipótesis para un estudio posterior, sin lenguaje causal. Nada se adopta",
    "guardas_antes_de_mirar_resultados": [
        "G14: en cada bloque y familia, las filas de entrenamiento y el corte son los de L (alfas_L.csv)",
        "G15: test de no fuga por perturbación de las dos familias (cambiar etiquetas y casos posteriores al "
        "corte no cambia las predicciones del bloque)",
        "G16: LightGBM con la misma semilla da dos veces lo mismo, y la evaluación de L + 5a reproduce las "
        "métricas de fase5.json",
        "si una guarda falla, se detiene la fase y se explica; no se ajusta nada para que pase",
    ],
    "fase_6_prima": "preparada, no se corre ahora: el mismo código con C3 + rezagos de clima "
                    f"({', '.join(PHASE6_PRIME_CLIMATE)}, la A3 de la V2) calculados sobre el clima largo "
                    "2000-2025, cuando la 1b lo entregue. Lleva su propio preregistro antes de correr",
    "mlflow": "denguekay/mejora_modelo_fase6_otras_familias",
}

PHASE6_RIDGE_ALPHA = 1e-4    # 6a': small L2 penalty fixed a priori, only for blocks/horizons that do not converge

PHASE6_AMENDMENT = {
    "fecha": "2026-11-03",
    "estado": "pedida por Rosa después de ver que 6a no convergió (al menos un horizonte en los 18 bloques; h3 "
              "solo en 2 de 18); commiteada antes de correr 6a′. Es la única enmienda de la fase 6",
    "variante": "6a′ = GLM Poisson por horizonte (statsmodels `GLM`, familia Poisson, IRLS, maxiter "
                f"{PHASE6_GLM_MAXITER}) con intercepto y offset log(hist_lag_a + 0,5) (el margen de S4_s3); las "
                "mismas 9 columnas de C3 con la misma transformación (log1p de los niveles de casos) y "
                "estandarizadas con el entrenamiento de cada bloque; la α de la NB2 con el estimador de L "
                "(`negative_binomial_dispersion` sobre el ajuste dentro de la muestra), igual que L con XGBoost",
    "si_no_converge": f"ese bloque y horizonte se reajusta con una penalización L2 de {PHASE6_RIDGE_ALPHA} (sin "
                      "penalizar el intercepto; `fit_regularized`, L1_wt = 0) y se reporta",
    "regla_de_cierre": "si 6a′ no converge sin penalización en la mayoría de los ajustes bloque × horizonte "
                       "(> 27 de 54), la fase 6 se cierra con el GLM como no interpretable. Si converge, se lee "
                       "igual que 6a y 6b frente a L + 5a (lectura, no decide)",
    "guardas": "las de la fase 6: G14 (filas y corte de L), G15 (no fuga por perturbación, test), y la "
               "reproducción de L + 5a",
}


# ---------------------------------------------------------------------------
# Phase 1b' (approved by Rosa on 2026-11-04 before the ERA5-Land download finished)
# ---------------------------------------------------------------------------

PHASE1B_PRIME_COLUMN = "hum_rel_media_media5_h2"   # same definition as the humidity of A3 in gold.py
PHASE1B_PRIME_MIN_HORIZONS_WON = 2

PHASE1B_PRIME = {
    "fecha": "2026-11-04",
    "estado": "aprobado por Rosa (2026-11-04) tal cual, commiteado antes de que termine la descarga de ERA5-Land; "
              "se corre cuando el silver `meteo_humedad_era5_land_2000_2025.csv` esté listo",
    "por_que": "ERA5 a 0,25° deja idéntica la precipitación entre vecinos en 48 distritos; «Best match» no tiene el "
               "IFS antes de 2017; ERA5-Land (0,1°) no trae precipitación en Open-Meteo. Queda la humedad de "
               "ERA5-Land como única fuente 2000-2025: A3 solo con humedad",
    "candidata": f"L + 5a + H: H = `{PHASE1B_PRIME_COLUMN}` con la definición de gold.py, calculada en memoria "
                 "sobre la humedad semanal de ERA5-Land 2000-2025. Matriz C3 + H; E3 · S4_s3; hiperparámetros de "
                 "la V1; bloques 2008-2024 + calendario_2025; Platt por horizonte con 1e-6; alerta p >= 0,50; dos "
                 "μ con la mezcla 5a; 5 semillas",
    "referencia": "L + 5a (predicciones guardadas de la 1a con la mezcla 5a)",
    "regla": "decide_multi_season (fases 2 y 3): 5 temporadas (2010, 2015, 2016, 2022, 2023), F1 primaria; AUPRC, "
             "Brier, razón MAE y antelación como guardas",
    "adopcion": f"gana en >= {PHASE1B_PRIME_MIN_HORIZONS_WON} de 3 horizontes y ninguno «pierde» ni «compensa "
                "(empate)»",
    "lecturas_que_no_deciden": [
        "la regla de razón MAE de la fase 5 (decide_phase5)",
        "sin 2010 (3 de 4) y 2024 como contraste",
        "frente a la V2 en 2022 y 2023 con sus predicciones guardadas, y la HU0007-4 por celda",
        "diferencia ERA5-Land − «Best match» de la humedad 2017-2025 por año, en los 65 distritos",
    ],
    "guardas_antes_de_mirar_resultados": [
        "G17: la función que calcula H, aplicada al silver vigente («Best match»), reproduce exactamente la "
        "columna de humedad del gold (misma definición)",
        "G18: test de no fuga por perturbación: cambiar la humedad posterior al origen no cambia H",
        "G19: ningún origen desde 2005 queda sin H",
        "G20: L + 5a reproduce fase5.json",
        "si una guarda falla, se detiene la fase y se explica; no se ajusta nada para que pase",
    ],
    "despues": "la fase 4 (Niño 1+2) sobre la base que quede; si H se adopta, el Niño se vuelve a medir sobre la "
               "base nueva",
}


# ---------------------------------------------------------------------------
# Phase 4 (approved by Rosa on 2026-11-04 with the check of the raw file, before running)
# ---------------------------------------------------------------------------

PHASE4_COLUMNS = {"4a": ["nino12_anom_ultimo"], "4b": ["nino12_anom_media3"]}
PHASE4_MIN_HORIZONS_WON = 2
PHASE4_SIMPLICITY = ("4a", "4b")   # a tie in a cross keeps the earlier (simpler) one
PHASE4_TRAINING_MAX = 3.30         # largest monthly Niño 1+2 anomaly in 2000-2025 (2023-08)

PHASE4 = {
    "fecha": "2026-11-04",
    "estado": "aprobado por Rosa (2026-11-04) con un agregado (verificar 2026-10 contra el archivo crudo); "
              "commiteado antes de correr ninguna variante de la fase 4",
    "fuente": "NOAA CPC sstoi.indices (OISST v2.1, base 1991-2020), anomalía de la región Niño 1+2; silver "
              "`enso_nino12_mensual.csv` (538 meses, 1982-01 a 2026-10; crudo `sstoi_20261103.indices`)",
    "base": "L + 5a",
    "disponibilidad": "un mes se usa en un origen solo si su fecha_disponible (día 10 del mes siguiente) es <= "
                      "origen_cierre (el sábado que cierra la última semana observada)",
    "variantes": {
        "4a": "C3 + nino12_anom_ultimo: anomalía del último mes disponible al origen",
        "4b": "C3 + nino12_anom_media3: media de los 3 últimos meses disponibles al origen",
    },
    "comun": "E3 · S4_s3, hiperparámetros de la V1, bloques 2008-2024 + calendario_2025, Platt por horizonte con "
             "1e-6, alerta p >= 0,50, dos μ con la mezcla 5a, 5 semillas. El valor es el mismo para todos los "
             "distritos (señal regional entre años)",
    "regla": "decide_multi_season (fases 2 y 3), 5 temporadas, F1 primaria; AUPRC, Brier, razón MAE y antelación "
             "como guardas",
    "adopcion": f"gana en >= {PHASE4_MIN_HORIZONS_WON} de 3 horizontes y ninguno «pierde» ni «compensa (empate)». "
                "Si se adoptan las dos, se cruzan con la misma regla; un empate deja 4a",
    "lecturas_que_no_deciden": [
        "la regla de razón MAE de la fase 5",
        "recall en las 2 primeras semanas de brotes nuevos frente a brotes en curso",
        "sin 2010 (3 de 4) y 2024 como contraste",
        f"rango: 2000-2025 va de -1,90 a {PHASE4_TRAINING_MAX} (2023-08); 2026-10 = 5,25, fuera del rango de "
        "entrenamiento (riesgo de extrapolación para la app, fase 7)",
        "repetición después de la 1b′: si se adopta H, 4a y 4b se vuelven a medir con la misma regla sobre "
        "L + 5a + H; el primer resultado queda registrado",
    ],
    "guardas_antes_de_mirar_resultados": [
        "G21: ningún origen usa un mes con fecha_disponible > origen_cierre (tabla completa)",
        "G22: test de no fuga por perturbación (cambiar anomalías de meses aún no disponibles no cambia las "
        "variables)",
        "G23: ningún origen desde 2005 queda sin valor",
        "G24: L + 5a reproduce fase5.json",
        "si una guarda falla, se detiene la fase y se explica; no se ajusta nada para que pase",
    ],
    "mlflow": "denguekay/mejora_modelo_fase4_nino",
}


def adopt_phase4(verdict: pd.DataFrame) -> bool:
    """Adoption of a phase 4 variant: >= 2 horizons won and none lost or offset."""
    won = int(verdict.veredicto.eq("gana").sum())
    bad = verdict.veredicto.isin(["pierde", "compensa (empate)"]).any()
    return won >= PHASE4_MIN_HORIZONS_WON and not bad


# ---------------------------------------------------------------------------
# Climate step b: CHIRPS v3 rainfall over L + 5a (step b-VII; written on 2026-11-06, pending Rosa's review)
# ---------------------------------------------------------------------------

STEP_B_RAIN_COLUMN = "precip_total_mm_media5_h2"   # same definition as the rainfall of A3 in gold.py
STEP_B_COLUMNS = {"b1": [STEP_B_RAIN_COLUMN], "b2": [PHASE1B_PRIME_COLUMN, STEP_B_RAIN_COLUMN]}
STEP_B_MIN_HORIZONS_WON = 2
STEP_B_SIMPLICITY = ("b1", "b2")   # a tie in a cross keeps the earlier (simpler) one
STEP_B_REFERENCE_DAYS = 14

STEP_B = {
    "fecha": "2026-11-06",
    "estado": "propuesto el 2026-11-06 (paso b-VII), commiteado sin correr nada; pendiente de la revisión de Rosa",
    "decisiones": "plan.md, «Decisiones de Rosa (2026-11-06, lluvia de CHIRPS v3)», puntos 1, 2, 3 y 5",
    "fuente": "CHIRPS v3 diario sat, versión final de Google Earth Engine (UCSB-CHC/CHIRPS/V3/DAILY_SAT), media del "
              "polígono distrital ponderada por área (COD-AB de Perú, IGN/OCHA, CC BY-IGO 3.0); silver "
              "`precip_chirps_v3_semanal_desde_2000.csv` (90 675 filas, 65 distritos, semanas MMWR de 7 días del "
              "2000-01-02 al 2026-09-20, todas `final`, sin vacíos; escrito en b-V el 2026-11-06). Guarda de método "
              "de b-IV: diferencia máxima 0,063 mm día-distrito frente a la media local. No se une con la lluvia "
              "«Best match» de Open-Meteo",
    "base": "L + 5a",
    "variantes": {
        "b1": f"C3 + `{STEP_B_RAIN_COLUMN}`: lluvia CHIRPS como media de las 5 semanas que terminan en la semana "
              "del origen (la definición de la A3 de la V2, con la alineación h=2), calculada en memoria",
        "b2": f"C3 + `{PHASE1B_PRIME_COLUMN}` (humedad de ERA5-Land, la H de la 1b′) + `{STEP_B_RAIN_COLUMN}` "
              "(lluvia CHIRPS): la A3 de la V2 con fuentes largas",
    },
    "comun": "E3 · S4_s3, hiperparámetros de la V1, orígenes desde 2005, bloques 2008-2024 + calendario_2025, Platt "
             "por horizonte con 1e-6, alerta p >= 0,50, dos μ con la mezcla 5a, 5 semillas. Sin ajuste de "
             "hiperparámetros ni de columnas después de ver resultados",
    "disponibilidad": f"una semana de lluvia se usa en un origen solo si su `fecha_disponible` (fin de la péntada "
                      f"preliminar de su sábado + 5 días) es <= origen_cierre + {STEP_B_REFERENCE_DAYS} días "
                      "(referencia de Rosa, hipótesis por el atraso de la Sala del MINSA)",
    "regla": "decide_multi_season (fases 2 y 3, igual que la 1b′): 5 temporadas (2010, 2015, 2016, 2022, 2023), F1 "
             "primaria; AUPRC, Brier, razón MAE y antelación como guardas. Cada variante frente a L + 5a",
    "adopcion": f"gana en >= {STEP_B_MIN_HORIZONS_WON} de 3 horizontes y ninguno «pierde» ni «compensa (empate)». "
                "Si se adoptan las dos, se cruzan b2 frente a b1 con la misma regla; un empate deja b1 (más simple)",
    "lecturas_que_no_deciden": [
        "la regla de razón MAE de la fase 5 (decide_phase5)",
        "sin 2010 (3 de 4) y 2024 como contraste",
        "recall en las 2 primeras semanas de brotes nuevos frente a brotes en curso",
        "frente a la V2 en 2022 y 2023 con sus predicciones guardadas, y la HU0007-4 por celda",
        f"diferencia CHIRPS − «Best match» de `{STEP_B_RAIN_COLUMN}` 2017-2025 por año, en los 65 distritos",
        "versiones de las semanas que llegan a los orígenes (se espera solo `final`); la brecha preliminar-final "
        "se mide aparte en b-VI y no cambia este veredicto",
    ],
    "guardas_antes_de_mirar_resultados": [
        "G25: la función que calcula la lluvia, aplicada al silver vigente («Best match»), reproduce exactamente "
        f"`{STEP_B_RAIN_COLUMN}` del gold (misma definición)",
        "G26: test de no fuga por perturbación: cambiar la lluvia de semanas posteriores a la del origen no "
        "cambia la variable",
        f"G27 (tipo G21): ningún origen usa una semana con fecha_disponible > origen_cierre + "
        f"{STEP_B_REFERENCE_DAYS} días (tabla completa, con la fecha_disponible del silver)",
        "G28: ningún origen desde 2005 queda sin lluvia (b1) ni sin lluvia y humedad (b2)",
        "G29: L + 5a reproduce fase5.json",
        "b2: G17 y G19 de la 1b′ se repiten sobre H",
        "si una guarda falla, se detiene el paso y se explica; no se ajusta nada para que pase",
    ],
    "codigo": "code/phase_b_rain.py (variable, G25, G27, G28); tests/test_phase_b_rain.py (G26)",
    "notebook": "notebooks/12_paso_b_lluvia_chirps.ipynb",
    "mlflow": "denguekay/mejora_modelo_paso_b_lluvia_chirps",
    "despues": "si b1 o b2 se adopta, la base cambia y se repite el Niño 1+2 (paso c) con su misma regla; si no, la "
               "base sigue siendo L + 5a y el paso c no se corre. Luego la fase 7",
}


def adopt_step_b(verdict: pd.DataFrame) -> bool:
    """Adoption of a step b variant (b1 or b2): >= 2 horizons won and none lost or offset."""
    won = int(verdict.veredicto.eq("gana").sum())
    bad = verdict.veredicto.isin(["pierde", "compensa (empate)"]).any()
    return won >= STEP_B_MIN_HORIZONS_WON and not bad


# ---------------------------------------------------------------------------
# Climate step b, variant b3 (added on 2026-11-06 after seeing b1 and b2; pending Rosa's review)
# ---------------------------------------------------------------------------

STEP_B3_TEMP_COLUMN = "temp_media_media5_h2"   # gold naming: weekly temp_media, 5-week mean, h=2 alignment
STEP_B3_COLUMNS = [PHASE1B_PRIME_COLUMN, STEP_B_RAIN_COLUMN, STEP_B3_TEMP_COLUMN, *PHASE4_COLUMNS["4b"]]
# Counterfactual reading of the Niño: origins chosen before looking at any b3 result (first Saturday of February
# and of March of the two seasons with most cases), the 65 districts, and the values of the anomaly to impose
STEP_B3_COUNTERFACTUAL_ORIGINS = ("2017-02-04", "2017-03-04", "2023-02-04", "2023-03-04")
STEP_B3_COUNTERFACTUAL_VALUES = (2.0, 3.3, 5.25)
STEP_B3_COUNTERFACTUAL_SEED = 17

STEP_B3 = {
    "fecha": "2026-11-06",
    "estado": "agregada el 2026-11-06 DESPUÉS de ver b1 y b2 (empate en los tres horizontes las dos); aprobada por "
              "Rosa el 2026-11-06 con dos cambios hechos antes de correr (ver «cambios_de_rosa»)",
    "cambios_de_rosa": [
        "adopt_step_b3: en la otra regla bloquean tanto «pierde» como «compensa (empate)», igual que adopt_step_b. "
        "Motivo: en la V2 el clima se adoptó por el conteo mientras la F1 de la alerta en 2022 · h4 caía de 0,525 "
        "a 0,333; no se quiere repetir",
        "G33: retraso de publicación de ERA5-Land = 7 días, no 5 (medido por Rosa el 2026-11-06: Open-Meteo con "
        "models=era5_land trae relative_humidity_2m_mean hasta el 2026-10-31)",
    ],
    "motivo": [
        "probar el clima completo, con interacciones (humedad, lluvia, temperatura y Niño juntos en el árbol), y la "
        "temperatura, que nunca se probó en el estudio",
        "el Niño Costero de magnitud extraordinaria que el ENFEN prevé para setiembre de 2026 a mayo de 2027 "
        "(Comunicado Oficial ENFEN N.° 16-2026, según Rosa; Claude lo encontró citado en la prensa, Panamericana "
        "del 16/09/2026, y no pudo abrir el texto oficial en gob.pe)",
    ],
    "variante": f"b3 = C3 + `{PHASE1B_PRIME_COLUMN}` (humedad ERA5-Land, la H de la 1b′) + `{STEP_B_RAIN_COLUMN}` "
                f"(lluvia CHIRPS v3, silver de b-V) + `{STEP_B3_TEMP_COLUMN}` (temperatura media de ERA5-Land, media "
                "de las 5 semanas que terminan en la semana del origen, alineación h=2, de "
                "`meteo_humedad_era5_land_2000_2025.csv`) + `nino12_anom_media3` (la 4b de la fase 4: media de los "
                "3 últimos meses publicados al origen)",
    "comun": "igual que L + 5a: E3 · S4_s3, hiperparámetros de la V1, orígenes desde 2005, bloques 2008-2024 + "
             "calendario_2025, Platt por horizonte con 1e-6, alerta p >= 0,50, dos μ con la mezcla 5a, 5 semillas",
    "base": "L + 5a",
    "regla": "fijada antes de correr b3, DESPUÉS de ver que el clima mejora en parte el conteo (razón MAE a favor en "
             "2 a 4 de 5 temporadas en b1 y b2, y en 2024). b3 se adopta si (a) gana la alerta con "
             "decide_multi_season frente a L + 5a (adopt_step_b: >= 2 horizontes ganados y ninguno «pierde» ni "
             "«compensa (empate)») y la regla del conteo no tiene ningún «pierde» ni «compensa (empate)»; o (b) gana "
             "el conteo con la regla de la fase 5 (decide_phase5; adopt_phase5: >= 2 horizontes ganados y ninguno "
             "«pierde» ni «compensa (empate)») y la regla de la alerta no tiene ningún «pierde» ni «compensa "
             "(empate)». Un empate deja L + 5a",
    "guardas_antes_de_mirar_resultados": [
        "G25 a G29 del paso b (lluvia: definición, no fuga, disponibilidad contra origen_cierre + 14 días, "
        "cobertura de las 4 columnas de clima desde 2005, L + 5a reproduce fase5.json)",
        "G17 y G19 de la 1b′ sobre la humedad",
        "G21 y G22 de la fase 4 sobre el Niño (ningún origen usa un mes con fecha_disponible > origen_cierre; test "
        "de no fuga por perturbación)",
        f"G30: definición de `{STEP_B3_TEMP_COLUMN}`: la función, aplicada a la temperatura del silver vigente "
        "(«Best match»), es igual a build_observed_climate(h=2) de gold.py (el gold no trae temperatura)",
        "G31: test de no fuga por perturbación de la temperatura",
        "G32: ningún origen desde 2005 sin temperatura (incluida en la cobertura de G28)",
        "G33: disponibilidad de la temperatura contra origen_cierre + 14 días (ERA5-Land, 7 días de retraso; la "
        "humedad sale de las mismas semanas)",
        "G34: la anomalía Niño 1+2 de 2026-10 vale 5,25 en el archivo crudo de la NOAA (`sstoi_20261103.indices`) y "
        "en el silver",
        "si una guarda falla, se detiene b3 y se explica; no se ajusta nada para que pase",
    ],
    "lecturas_que_no_deciden": [
        "SHAP de b3 por horizonte (media de |SHAP| del regresor, semilla 17) en temporada_2022, temporada_2023 y "
        "temporada_2024, en el formato de complemento_clima.shap_por_horizonte_semilla_17 del estudio 05",
        "HU0007-4 por celda y comparación con la V2 en 2022 y 2023",
        "sin 2010 (3 de 4), 2024 como contraste y recall de las 2 primeras semanas de brotes nuevos",
        "riesgo de extrapolación del Niño: rango de nino12_anom_media3 en los orígenes desde 2005 frente al valor "
        "actual (media de agosto a octubre de 2026 en el silver)",
        "contrafactual del Niño: con el modelo de b3 del bloque que predice cada origen (semilla "
        f"{STEP_B3_COUNTERFACTUAL_SEED}), en los orígenes {', '.join(STEP_B3_COUNTERFACTUAL_ORIGINS)} y los 65 "
        f"distritos, nino12_anom_media3 = {', '.join(str(v) for v in STEP_B3_COUNTERFACTUAL_VALUES)} y su valor real, "
        "con todo lo demás fijo: probabilidad calibrada (el Platt del bloque y horizonte, ajustado con las "
        "predicciones fuera de muestra anteriores de b3, como en el protocolo), distritos en alerta (p >= 0,50) y "
        "casos predichos con la mezcla 5a (la w del bloque y horizonte de b3), por origen y horizonte",
        "b3 frente a L + 5a en temporada_2017 y temporada_2023 (F1, AUPRC, Brier y razón MAE por horizonte)",
    ],
    "comparaciones": "b3 es la tercera variante del paso b (después de b1 y b2): con más comparaciones aumenta la "
                     "probabilidad de un «gana» por azar; se reporta junto con los empates de b1 y b2",
    "mlflow": "denguekay/mejora_modelo_paso_b_lluvia_chirps (el mismo experimento del paso b)",
    "codigo": "code/phase_b3_full_climate.py (temperatura, G30, G33, G34, rango del Niño); "
              "tests/test_phase_b3_full_climate.py (G31 y la regla)",
    "notebook": "notebooks/13_paso_b3_clima_completo.ipynb",
    "despues": "si b3 se adopta, la base cambia a L + 5a + b3 y se le consulta a Rosa antes de la fase 7 (el Niño ya "
               "está dentro de b3, así que el paso c no se repite aparte); si no, la base sigue siendo L + 5a",
}


def adopt_step_b3(alert_verdict: pd.DataFrame, count_verdict: pd.DataFrame) -> bool:
    """b3: wins the alert (adopt_step_b) with no «pierde» nor «compensa (empate)» in the count, or wins the count
    (adopt_phase5) with neither in the alert. Anything else (a tie) keeps L + 5a."""
    bad = ["pierde", "compensa (empate)"]
    alert_loses = alert_verdict.veredicto.isin(bad).any()
    count_loses = count_verdict.veredicto.isin(bad).any()
    return bool((adopt_step_b(alert_verdict) and not count_loses) or (adopt_phase5(count_verdict) and not alert_loses))


# ---------------------------------------------------------------------------
# Climate step d: weather windows (added on 2026-11-06 after seeing b1, b2 and b3; pending Rosa's review)
# ---------------------------------------------------------------------------

STEP_D_SOURCES = ("precip_total_mm", "temp_media", "hum_rel_media")
STEP_D_WINDOWS = ("s0", "media_s1_4", "media_s5_8", "media_s9_12")
STEP_D_HEAVY_RAIN_MM = 20.0
STEP_D_HEAVY_COLUMNS = ["dias_precip_20mm_s0_3", "dias_precip_20mm_s4_7"]
STEP_D_COLUMNS = [f"{s}_{w}" for s in STEP_D_SOURCES for w in STEP_D_WINDOWS] + STEP_D_HEAVY_COLUMNS
STEP_D_REPORT_SEASONS = (*DECIDING_SEASONS, CONTRAST_SEASON)
STEP_D_SHAP_BLOCKS = ("temporada_2022", "temporada_2023", "temporada_2024")
STEP_D_SHAP_SEED = 17
STEP_D_NO_LEAK_CUT = "2016-12-31"   # real-data perturbation: every week after it is changed
STEP_D_BRIER_PRIMARY = "brier"      # criterion (c), added by Rosa before running
STEP_D_BRIER_GUARDS = ("auprc", "f1_050", "razon_mae")   # plus the lead time

STEP_D = {
    "fecha": "2026-11-06",
    "estado": "agregado el 2026-11-06 DESPUÉS de ver b1, b2 y b3 (empate en los tres horizontes las tres); "
              "aprobado por Rosa el 2026-11-06 con tres respuestas y un agregado (criterio c), hechos antes de "
              "correr (ver «respuestas_de_rosa»)",
    "respuestas_de_rosa": [
        "umbral: >= 20 mm (R20mm del ETCCDI)",
        "climatología del Brier skill score: la propuesta, tal cual",
        "si las comparaciones no coinciden: la base pasa a d1 solo si gana frente a L + 5a; si además pierde "
        "frente a b3, se consulta a Rosa antes de la fase 7",
        "agregado: criterio de adopción (c) por la calidad de la probabilidad, frente a L + 5a y frente a b3. "
        "Motivo declarado por Rosa: la calidad de la p sin corte importa más que el F1 al corte de 0,50, que es "
        "un umbral de uso",
    ],
    "motivo": "la media de 5 semanas heredada de la V2 no dice cuándo llovió, y los inicios de brote podrían depender "
              "de ventanas más antiguas (hipótesis de Rosa)",
    "variante": "d1 = C3 + 14 columnas calculadas en memoria con el último dato disponible en la semana del origen "
                "o (nunca semanas posteriores): para la lluvia CHIRPS v3 (silver de b-V), la temperatura media y la "
                "humedad relativa de ERA5-Land (silvers de la 1b′ y de b3), el valor de la semana o y las medias de "
                "o−1..o−4, o−5..o−8 y o−9..o−12, sin solaparse (12 columnas); para la lluvia, además, los días con "
                f">= {STEP_D_HEAVY_RAIN_MM:g} mm en o−3..o y en o−7..o−4, contados sobre las medias diarias por "
                "polígono ponderadas por área que devolvió Earth Engine (bronze `ee_final`, los mismos días que suma "
                "el silver). Sin Niño",
    "columnas": STEP_D_COLUMNS,
    "umbral_lluvia_fuerte": {
        "valor": f">= {STEP_D_HEAVY_RAIN_MM:g} mm por día (media del polígono distrital)",
        "justificacion": [
            "es el índice R20mm de la lista de 27 índices del ETCCDI "
            "(https://etccdi.pacificclimate.org/list_27_indices.shtml, consultada el 2026-11-06): conteo anual de "
            "días con PRCP >= 20 mm; un umbral estándar, no elegido mirando el modelo",
            "en los datos (bronze `ee_final`, 2005-2025, 65 distritos; sin mirar resultados del modelo): 20 mm cae "
            "entre el percentil 90 (17,8 mm) y el 95 (26,4 mm) de los días con >= 1 mm; con > 20 mm hay una mediana "
            "de 3,1 días al año por distrito (mínimo 0,33, máximo 16,3); todos los distritos tienen alguno, pero 18 "
            "lo superan en 5 o menos de los 21 años. De enero a abril, el 33 % de las ventanas de 4 semanas tienen "
            "al menos un día (74 % en 2017 y 61 % en 2023)",
            "con 10 mm la variable se acerca a «hubo lluvia» en la sierra (mediana de 6,1 días al año, máximo 35,5); "
            "con 30 mm, 26 distritos lo superan en 5 o menos años y la variable queda casi siempre en 0",
            "la media del polígono suaviza los extremos de los píxeles, así que 20 mm por polígono es más exigente "
            "que 20 mm en una estación; queda como hipótesis, no se verificó contra estaciones",
            "Rosa escribió primero «más de 20 mm» y confirmó >= 20 mm, como el ETCCDI, antes de correr",
        ],
    },
    "comun": "igual que L + 5a: E3 · S4_s3, hiperparámetros de la V1, orígenes desde 2005, bloques 2008-2024 + "
             "calendario_2025, Platt por horizonte con 1e-6, alerta p >= 0,50, dos μ con la mezcla 5a, 5 semillas. "
             "Sin ajuste de hiperparámetros, de ventanas, del umbral ni de columnas después de ver resultados",
    "disponibilidad": "CHIRPS y días fuertes: cada semana usada tiene `fecha_disponible` (silver) <= origen_cierre + "
                      f"{STEP_B_REFERENCE_DAYS} días; ERA5-Land: la semana más reciente usada (la del origen) se publica "
                      f"su sábado + 7 días <= origen_cierre + {STEP_B_REFERENCE_DAYS} días (retraso medido por Rosa)",
    "comparaciones": {
        "d1_frente_a_L_5a": "regla de b3 (adopt_step_b3): gana la alerta (decide_multi_season + adopt_step_b) sin "
                            "«pierde» ni «compensa (empate)» en el conteo, o gana el conteo (decide_phase5 + "
                            "adopt_phase5) sin «pierde» ni «compensa (empate)» en la alerta; o (c) gana por el "
                            "Brier (decide_step_d_brier + adopt_step_b) sin «pierde» ni «compensa (empate)» ni en "
                            "la alerta (F1) ni en el conteo; un empate deja L + 5a",
        "d1_frente_a_b3": "la misma regla con b3 como referencia (predicciones guardadas de b3, 5 semillas). b3 no se "
                          "adoptó, así que este cruce responde si las ventanas le ganan a la media de 5 semanas con "
                          "el Niño, y no cambia la base por sí solo. Aceptado por Rosa: la base pasa a "
                          "d1 solo si d1 gana frente a L + 5a; si además pierde frente a b3, se reporta y se le "
                          "consulta a Rosa antes de la fase 7. d1 y b3 difieren en dos cosas (ventanas y Niño), así "
                          "que el cruce no separa sus efectos",
    },
    "criterio_c": "agregado por Rosa antes de correr. decide_step_d_brier: la regla multi-temporada (mismas 5 "
                  "temporadas, MIN_IN_FAVOUR = 4 a favor y 0 en contra, umbral de empate = rango de semillas) con el "
                  "Brier (probabilidad calibrada, menor es mejor) como métrica principal y AUPRC, F1 a 0,50, razón "
                  "MAE y antelación como guardas (una guarda veta si está en contra en >= 3 de 5; la antelación veta "
                  "si su IC95 queda por debajo de 0 con >= 4 temporadas en contra y ninguna a favor, como en "
                  "decide_phase5). Se adopta por (c) si gana en >= 2 horizontes sin «pierde» ni «compensa (empate)» "
                  "en el Brier, y ni la alerta (F1) ni el conteo tienen «pierde» ni «compensa (empate)»",
    "metricas_reportadas_que_no_deciden": [
        "Brier y AUPRC por celda (horizonte × temporada de 2010, 2015, 2016, 2022, 2023 y 2024), mediana de las 5 "
        "semillas, para L + 5a, b3 y d1 (las del protocolo, con la probabilidad calibrada)",
        "Brier skill score frente a la climatología: 1 − Brier / Brier_clim. Climatología (propuesta, fuera de "
        "muestra): para cada bloque y horizonte, la frecuencia de brote del mismo distrito en las semanas "
        "epidemiológicas a ±2 de la semana objetivo (circular, la 53 cuenta como 52), con las etiquetas de la serie "
        "desde 2005 cerradas al primer origen del bloque (las mismas que puede usar el calibrador); un distrito sin "
        "esas filas toma la frecuencia de todos (aceptada por Rosa). Mediana de las 5 semillas",
        "AUPRC restringido a los distrito-semana con persistencia < umbral_brote_casos en el origen (con el número "
        "de filas y de positivos); mediana de las 5 semillas; vacío si la celda no tiene positivos",
    ],
    "guardas_antes_de_mirar_resultados": [
        "G29: L + 5a reproduce fase5.json",
        "G39: las predicciones guardadas de b3, evaluadas de nuevo, reproducen las métricas de paso_b3.json",
        "G35 (definición): (a) las sumas semanales del bronze diario de Earth Engine son iguales a precip_total_mm "
        "del silver en las mismas semanas (las del silver, todas presentes); (b) para cada fuente, (semana o + 4 × "
        "media o−1..o−4) / 5 es igual a la media de 5 semanas ya validada (G25 lluvia, G17 humedad, G30 "
        "temperatura); (c) tests con datos sintéticos de cada ventana y del conteo de días fuertes",
        "G36 (no fuga por perturbación): test sintético y, sobre los datos reales, cambiar la lluvia, los días "
        f"fuertes, la temperatura y la humedad de las semanas posteriores a {STEP_D_NO_LEAK_CUT} no cambia ninguna "
        "columna de los orígenes hasta esa semana (y sí cambia alguna posterior)",
        "G37 (cobertura): ningún origen desde 2005 sin alguna de las 14 columnas",
        f"G38 (disponibilidad contra origen_cierre + {STEP_B_REFERENCE_DAYS} días): CHIRPS y días fuertes con la "
        "fecha_disponible del silver; ERA5-Land con 7 días de retraso",
        "G17, G25 y G30 se repiten porque G35b se apoya en ellas",
        "si una guarda falla, se detiene el paso d y se explica; no se ajusta nada para que pase",
    ],
    "lecturas_que_no_deciden": [
        "SHAP de d1 por horizonte (media de |SHAP| del regresor, semilla 17) en temporada_2022, temporada_2023 y "
        "temporada_2024, en el formato de b3",
        "HU0007-4 por celda (2022 y 2023) para L + 5a, b3 y d1",
        "criterio (c) para b3 frente a L + 5a: declarado como posterior a ver los resultados de b3; es una lectura "
        "y no cambia la decisión de b3",
    ],
    "multiples_comparaciones": "d es la cuarta variante de clima después de b1, b2 y b3 (todas en empate) y se "
                               "compara dos veces; con más comparaciones aumenta la probabilidad de un «gana» por "
                               "azar; se reporta junto con los empates anteriores",
    "mlflow": "denguekay/mejora_modelo_paso_b_lluvia_chirps (el experimento del paso b)",
    "metricas": "docs/metricas/paso_d.json",
    "codigo": "code/phase_d_weather_windows.py (columnas, G35-G38, climatología y métricas reportadas); "
              "tests/test_phase_d_weather_windows.py (ventanas, conteo, G36 sintética, regla, climatología)",
    "notebook": "notebooks/14_paso_d_ventanas_clima.ipynb (se escribe al correr)",
    "despues": "si d1 se adopta, la base cambia a L + 5a + d1 y se le consulta a Rosa antes de la fase 7; si no, la "
               "base sigue siendo L + 5a",
}


def decide_step_d_brier(candidate: pd.DataFrame, reference: pd.DataFrame, ranges: pd.DataFrame,
                        lead_time_diff: pd.DataFrame, seasons: tuple[int, ...] = DECIDING_SEASONS,
                        min_in_favour: int = MIN_IN_FAVOUR, guard_veto: int = GUARD_VETO_AGAINST) -> pd.DataFrame:
    """Criterion (c) of step d per horizon: the Brier decides; AUPRC, F1 at 0.50, razón MAE and lead time guard
    (same structure as ``decide_phase5``)."""
    blocks = [block_name(s) for s in seasons]
    metrics = (STEP_D_BRIER_PRIMARY, *STEP_D_BRIER_GUARDS)
    rows = []
    for h in sorted(candidate.horizonte.unique()):
        c = candidate[candidate.horizonte.eq(h)].set_index("bloque")
        r = reference[reference.horizonte.eq(h)].set_index("bloque")
        e = ranges[ranges.horizonte.eq(h)].set_index("bloque")
        counts = {m: _season_signs({b: DIRECTION[m] * (c.at[b, m] - r.at[b, m]) for b in blocks},
                                   {b: e.at[b, m] for b in blocks}) for m in metrics}
        f, a = counts[STEP_D_BRIER_PRIMARY]
        improves, worsens = f >= min_in_favour and a == 0, a >= min_in_favour and f == 0
        lead = lead_time_diff[lead_time_diff.horizonte.eq(h)].iloc[0]
        lf, la = _season_signs({b: float(lead[f"diferencia_{b}"]) for b in blocks},
                               {b: 1 / float(lead[f"episodios_{b}"]) for b in blocks})
        lead_worse = bool(lead.ic95_superior < 0 and la >= min_in_favour and lf == 0)
        lead_better = bool(lead.ic95_inferior > 0 and lf >= min_in_favour and la == 0)
        veto_a = [m for m in STEP_D_BRIER_GUARDS if counts[m][1] >= guard_veto] + (["antelacion"] if lead_worse else [])
        veto_b = [m for m in STEP_D_BRIER_GUARDS if counts[m][0] >= guard_veto] + (["antelacion"] if lead_better else [])
        if improves and not veto_a:
            verdict = "gana"
        elif worsens and not veto_b:
            verdict = "pierde"
        elif improves or worsens:
            verdict = "compensa (empate)"
        else:
            verdict = "empate"
        rows.append({"horizonte": h, "veredicto": verdict, "vetos": ", ".join(veto_a) or None,
                     "vetos_contra_referencia": ", ".join(veto_b) or None,
                     **{f"a_favor_{m}": v[0] for m, v in counts.items()},
                     **{f"en_contra_{m}": v[1] for m, v in counts.items()},
                     "a_favor_antelacion": lf, "en_contra_antelacion": la})
    return pd.DataFrame(rows)


def adopt_step_d_criteria(alert_verdict: pd.DataFrame, count_verdict: pd.DataFrame,
                          brier_verdict: pd.DataFrame) -> dict:
    """Criteria (a) alert, (b) count and (c) Brier of step d; each one blocked by «pierde» or «compensa (empate)»
    in the alert or the count (and (a), (b) by the other one, as in b3)."""
    bad = ["pierde", "compensa (empate)"]
    alert_bad = bool(alert_verdict.veredicto.isin(bad).any())
    count_bad = bool(count_verdict.veredicto.isin(bad).any())
    a = bool(adopt_step_b(alert_verdict) and not count_bad)
    b = bool(adopt_phase5(count_verdict) and not alert_bad)
    c = bool(adopt_step_b(brier_verdict) and not alert_bad and not count_bad)
    return {"a_alerta": a, "b_conteo": b, "c_brier": c, "adopta": a or b or c}


def adopt_step_d(alert_verdict: pd.DataFrame, count_verdict: pd.DataFrame,
                 brier_verdict: pd.DataFrame | None = None) -> bool:
    """d1 against a reference (L + 5a or b3): the rule of b3, plus criterion (c) when the Brier verdict is given."""
    if brier_verdict is None:
        return adopt_step_b3(alert_verdict, count_verdict)
    return adopt_step_d_criteria(alert_verdict, count_verdict, brier_verdict)["adopta"]


# ---------------------------------------------------------------------------
# Season 2026 evaluation: decision rule (approved by Rosa on 2026-11-08, before any 2026 data was downloaded)
# ---------------------------------------------------------------------------

SEASON_2026_DECIDING = (2010, 2015, 2016, 2022, 2023, 2026)
SEASON_2026_MIN_IN_FAVOUR = 5      # out of 6, and none against
SEASON_2026_GUARD_VETO = 4         # out of 6 (the 3 of 5 of the multi-season rule)
SEASON_2026_MIN_OUTBREAK_WEEKS = 30   # EVALUATION_2026: below it, the horizon uses the 5-season rule
SEASON_2026_VARIANTS = ("b3", "d1", "d2")   # each against L + 5a; d2 = d1 + nino12_anom_media3
SEASON_2026_SIMPLICITY = ("b3", "d1", "d2")  # 4, 14 and 15 climate columns; a tie in a cross keeps the earlier
SEASON_2026_PROVISIONAL_WEEKS = 2  # the last 2 published Sala weeks stay out of the metrics (reported apart)

SEASON_2026 = {
    "fecha": "2026-11-08",
    "estado": "regla de decisión aprobada por Rosa el 2026-11-08 antes de bajar los datos de 2026; guardas, "
              "métricas, lecturas y validación dejando una temporada fuera escritas el 2026-11-08 después del punto 1 de "
              "datos (aprobado por Rosa) y ANTES de entrenar ningún modelo con 2026",
    "temporada_2026": "semana 35 de 2025 a semana 34 de 2026 (bloque temporada_2026, entrenado con los orígenes hasta "
                      "la temporada 2025; Platt y la w de 5a con los bloques anteriores)",
    "posterior_2026": "semanas 35 de 2026 en adelante (bloque posterior_2026, entrenado hasta la temporada 2026, lo que "
                      "tendría la app en septiembre de 2026); solo se reporta, no decide",
    "semanas_provisionales": f"las {SEASON_2026_PROVISIONAL_WEEKS} últimas semanas publicadas en la Sala (al 2026-11-08, "
                             "la 42 y la 43 de 2026) no entran en las métricas y se reportan aparte; si una bajada "
                             "nueva las cambia, se usan los valores nuevos",
    "variantes": "L + 5a (referencia, sin clima), b3, d1 y d2 = d1 + nino12_anom_media3, todas con orígenes desde 2005, "
                 "lluvia CHIRPS v3 y temperatura y humedad de ERA5-Land",
    "regla": "por horizonte, decide_step_d_brier sobre las temporadas 2010, 2015, 2016, 2022, 2023 y 2026: el Brier "
             f"(probabilidad calibrada) gana con >= {SEASON_2026_MIN_IN_FAVOUR} de 6 temporadas a favor y 0 en contra "
             "(umbral de empate = rango de semillas); AUPRC, F1 a 0,50, razón MAE y antelación son guardas y vetan con "
             f">= {SEASON_2026_GUARD_VETO} de 6 en contra. Si 2026 no llega a {SEASON_2026_MIN_OUTBREAK_WEEKS} semanas "
             "brote en un horizonte, ese horizonte usa las 5 temporadas de siempre (4 de 5 y vetos con 3 de 5)",
    "adopcion": "frente a L + 5a: >= 2 horizontes ganados y ningún «pierde» ni «compensa (empate)» en el Brier, y "
                "ningún «pierde» ni «compensa (empate)» en la alerta (F1, decide_multi_season) ni en el conteo (razón "
                "MAE, decide_phase5), calculados sobre las mismas temporadas y con los mismos mínimos. Si se adopta "
                "más de una variante, se cruzan entre sí con la misma regla y un empate deja la más simple (b3, luego "
                "d1, luego d2)",
    "declaraciones": [
        "la regla (el Brier como métrica principal y 2026 entre las temporadas que deciden) se fijó DESPUÉS de ver "
        "los pasos b y d (b1, b2, b3 y d1 empataron con L + 5a)",
        "d2 se agrega después de ver d1; con b3, d1 y d2 son tres comparaciones más sobre L + 5a",
        "con esto EVALUATION_2026 deja de ser independiente para la V3: la prueba independiente pasa a ser lo "
        "publicado después del congelamiento (el resto de la temporada 2026-2027); ver plan.md, «Decisiones de Rosa "
        "(2026-11-08)»",
    ],
    "datos": {
        "casos": "serie larga del estudio (silver epi 2005-2016 + integrado 2017-2025) + la Sala 2026 del silver "
                 "epi_sala_semanal.csv (semanas 1 a 41: la 42 y la 43 son provisionales y no entran), en memoria; "
                 "etiquetas con la regla de gold (5 años previos)",
        "lluvia": "silver precip_chirps_v3_semanal_desde_2000.csv (reemplazado el 2026-11-08: final hasta la semana del "
                  "2026-09-20 y preliminar del 2026-09-27 al 2026-10-25)",
        "dias_fuertes": "final: bronze ee_final; semanas preliminares: medias diarias por polígono de las ventanas "
                        "preliminares del bronze, calculadas con chirps_precipitation.daily_from_windows de "
                        "feat/chirps-precipitation (5b6f6cd) y guardadas como insumo del experimento en "
                        "models/experimentos/mejora_modelo/temporada_2026/ (no en data/)",
        "humedad_y_temperatura": "silver meteo_humedad_era5_land_2000_2026.csv",
        "nino": "silver enso_nino12_mensual.csv (hasta 2026-10)",
    },
    "bloques": "los de siempre (temporada_2008 a temporada_2024 y calendario_2025) + temporada_2026 (temporada 2026) "
               "+ posterior_2026 (temporada 2027 hasta la semana 41 de 2026); Platt por horizonte y w de 5a con los "
               "bloques anteriores, como siempre; 5 semillas; las 4 variantes se reentrenan en todos los bloques",
    "guardas_antes_de_mirar_resultados": [
        "G40: la serie extendida reproduce exactamente casos y etiquetas 2005-2025 de la serie del estudio, y sus "
        "filas de 2026 son las del silver de la Sala (65 distritos, semanas 1 a 41)",
        "G41: L, b3 y d1 reentrenadas con los datos extendidos reproducen sus predicciones guardadas en los 19 "
        "bloques anteriores (diferencia máxima de casos_predichos y probabilidad_brote <= 1e-6)",
        "G29: L + 5a reproduce fase5.json",
        "G17, G25, G30 y G35b: definición de humedad, lluvia, temperatura y ventanas (como en b3 y d)",
        "G35a: las sumas semanales del diario (Earth Engine + preliminar) son iguales al silver de lluvia en todas sus "
        "semanas, también las preliminares",
        "G42: ningún origen desde 2005 hasta el último de posterior_2026 sin alguna columna de clima de b3, d1 o d2",
        "G43: disponibilidad contra origen_cierre + 14 días: lluvia y días fuertes con la fecha_disponible del silver "
        "(incluidas las semanas preliminares), ERA5-Land con 7 días, Niño con su fecha_disponible (G21)",
        "G44: los tests de no fuga por perturbación de la lluvia, la temperatura, el Niño y las ventanas (G22, G26, "
        "G31 y G36)",
        "si una guarda falla, se detiene la evaluación y se explica; no se ajusta nada para que pase",
    ],
    "metricas_por_celda": "para L + 5a, b3, d1 y d2, mediana de 5 semillas, en las 6 temporadas que deciden, 2017, "
                          "2024 y posterior_2026: Brier, Brier skill score con la climatología del paso d, AUPRC "
                          "general y en inicios (persistencia < max(umbral_brote_casos, 2)), F1 a 0,50, razón MAE y "
                          "RMSE, con el número de semanas brote; la HU0007-4 por celda en 2022, 2023 y 2026",
    "lecturas_que_no_deciden": [
        "posterior_2026 (entrenado hasta la temporada 2026), con sus semanas brote",
        "las 2 semanas provisionales: casos y semanas brote observados",
        "rango de nino12_anom_media3 en el entrenamiento de cada bloque frente a su valor en cada origen de "
        "temporada_2026 y posterior_2026",
        "qué orígenes usan lluvia preliminar (alguna semana de su ventana con version = prelim)",
        "antelación en temporada_2026 (20 inicios limpios) y en posterior_2026 (17, debajo del mínimo: no evaluable)",
    ],
    "validacion_dejando_una_temporada_fuera": {
        "temporadas": [2010, 2015, 2016, 2017, 2022, 2023, 2024, 2026],
        "entrenamiento": "orígenes desde 2005 con sus 3 objetivos etiquetados, menos los que tienen la semana del "
                         "origen o algún objetivo dentro de la temporada dejada fuera ampliada 4 semanas antes y 4 "
                         "después; el resto de las temporadas, pasadas y futuras (hasta la semana 41 de 2026)",
        "calibracion": "Platt por horizonte ajustado con las predicciones fuera de muestra de las otras 7 temporadas "
                       "dejadas fuera (nunca con la evaluada); la w de 5a, igual",
        "metricas": "las de metricas_por_celda menos la antelación, mediana de 5 semillas, por temporada y horizonte",
        "lectura": "diferencias de b3, d1 y d2 frente a L + 5a (modelo sin clima frente a modelos con clima)",
        "declaracion": "es optimista: usa temporadas futuras, y la temporada siguiente a la dejada fuera usa su total "
                       "en propia_log_casos_temporada_anterior. Solo compara variantes entre sí; nunca se reporta como "
                       "rendimiento esperado y no decide",
    },
    "enmienda_2026_11_08": "al correr (antes de entrenar ningún modelo) la serie no se pudo armar: el panel integrado "
                           "termina en la semana 52 de 2025 (2025-12-21) y le falta la 53 (2025-12-28), así que había un "
                           "hueco antes de 2026. Se agrega la semana 53 de 2025 desde el mismo silver de la Sala (65 "
                           "filas). G40 compara las filas de la serie del estudio y reporta aparte las agregadas; G41 "
                           "compara cada predicción guardada y cuenta aparte las filas nuevas de los bloques guardados "
                           "(los objetivos de esa semana en calendario_2025). Ningún bloque anterior cambia por esto",
    "mlflow": "denguekay/mejora_modelo_temporada_2026",
    "metricas": "docs/metricas/temporada_2026.json",
    "codigo": "code/phase_2026.py; notebook notebooks/15_temporada_2026.ipynb",
}


def decide_season_2026(candidate: pd.DataFrame, reference: pd.DataFrame, ranges: pd.DataFrame,
                       lead_time_diff: pd.DataFrame, outbreak_weeks_2026: dict[int, int]) -> pd.DataFrame:
    """Brier verdict per horizon over the 6 seasons, or over the usual 5 in a horizon where 2026 has fewer than
    ``SEASON_2026_MIN_OUTBREAK_WEEKS`` outbreak weeks."""
    rows = []
    for h in sorted(candidate.horizonte.unique()):
        six = outbreak_weeks_2026.get(h, 0) >= SEASON_2026_MIN_OUTBREAK_WEEKS
        seasons = SEASON_2026_DECIDING if six else DECIDING_SEASONS
        k, veto = (SEASON_2026_MIN_IN_FAVOUR, SEASON_2026_GUARD_VETO) if six else (MIN_IN_FAVOUR, GUARD_VETO_AGAINST)
        sel = [c[c.horizonte.eq(h)] for c in (candidate, reference, ranges, lead_time_diff)]
        rows.append(decide_step_d_brier(*sel, seasons=seasons, min_in_favour=k, guard_veto=veto)
                    .assign(temporadas=len(seasons)))
    return pd.concat(rows, ignore_index=True)


def adopt_season_2026(brier_verdict: pd.DataFrame, alert_verdict: pd.DataFrame, count_verdict: pd.DataFrame) -> bool:
    """>= 2 horizons won by the Brier, and no «pierde» nor «compensa (empate)» in the Brier, the alert or the count."""
    bad = ["pierde", "compensa (empate)"]
    won = int(brier_verdict.veredicto.eq("gana").sum())
    return bool(won >= STEP_B_MIN_HORIZONS_WON
                and not any(v.veredicto.isin(bad).any() for v in (brier_verdict, alert_verdict, count_verdict)))


# ---------------------------------------------------------------------------
# Climate matrix: every reasonable way to use the climate, compared (written on 2026-11-08 after seeing the
# season 2026 results; not run; pending Rosa's review)
# ---------------------------------------------------------------------------

_NINO = "nino12_anom_media3"
_WINDOWS = ("s0", "media_s1_4", "media_s5_8", "media_s9_12")
_win = lambda source: [f"{source}_{w}" for w in _WINDOWS]
_anom = lambda source: [f"{source}_anomalia_{w}" for w in _WINDOWS]
MATRIX_HEAVY_ANOMALY = ["dias_precip_20mm_anomalia_s0_3", "dias_precip_20mm_anomalia_s4_7"]
MATRIX_E1 = [*_anom("precip_total_mm"), *_anom("temp_media"), *_anom("hum_rel_media"), *MATRIX_HEAVY_ANOMALY]

MATRIX_VARIANTS = {
    # 5-week means
    "b1": [STEP_B_RAIN_COLUMN],
    "b2": [PHASE1B_PRIME_COLUMN, STEP_B_RAIN_COLUMN],
    "b3": list(STEP_B3_COLUMNS),
    "b4": [c for c in STEP_B3_COLUMNS if c != _NINO],
    # weekly windows
    "d1": list(STEP_D_COLUMNS),
    "d2": [*STEP_D_COLUMNS, _NINO],
    "d3": _win("temp_media"),
    "d4": [*_win("precip_total_mm"), *STEP_D_HEAVY_COLUMNS],
    "d5": _win("hum_rel_media"),
    # anomalies against the block's district x epi-week climatology
    "e1": list(MATRIX_E1),
    "e2": [*MATRIX_E1, _NINO],
    # monotone Niño
    "n1": list(STEP_B3_COLUMNS),
}
MATRIX_MONOTONE = {"n1": {_NINO: 1}}   # +1: the prediction does not go down when the Niño goes up; the rest 0
# Simplicity order for the crosses (a tie keeps the earlier one): fewer columns; with equal columns, without Niño
# before with Niño; then unconstrained before constrained (b3 before n1); d3 before d5 and d1/d2 before e1/e2 are
# arbitrary choices fixed now (windows need no per-block fit, anomalies do)
MATRIX_SIMPLICITY = ("b1", "b2", "b4", "d3", "d5", "b3", "n1", "d4", "d1", "e1", "d2", "e2")
MATRIX_FIXED_CROSSES = (("d1", "b3"), ("d2", "b3"), ("e1", "b3"))
MATRIX_REUSE = ("L + 5a", "b3", "d1", "d2")   # temporada_2026 predictions saved on 2026-11-08
MATRIX_SHAP_BLOCKS = ("temporada_2022", "temporada_2023", "temporada_2026")
MATRIX_SHAP_TOP_BRIER = 3
CLIMATOLOGY_BUFFER_WEEKS = 4
MATRIX_LOSO_MIN_CELLS = 16   # of the 24 leave-one-season-out cells (8 seasons x 3 horizons) with a better Brier
MATRIX_LOSO_CELLS = 24


def matrix_comparisons(n_adopted: int) -> int:
    """Comparisons of the matrix: each variant against L + 5a, the fixed crosses and every pair of adopted ones."""
    return len(MATRIX_VARIANTS) + len(MATRIX_FIXED_CROSSES) + n_adopted * (n_adopted - 1) // 2


def adopt_matrix(brier_verdict: pd.DataFrame, alert_verdict: pd.DataFrame, count_verdict: pd.DataFrame,
                 loso_better_cells: int) -> bool:
    """A matrix variant is adopted if it wins with SEASON_2026 against L + 5a AND its Brier is better than L + 5a's
    in at least ``MATRIX_LOSO_MIN_CELLS`` of the 24 leave-one-season-out cells (filter added by Rosa on 2026-11-08
    against winners by chance)."""
    return bool(adopt_season_2026(brier_verdict, alert_verdict, count_verdict)
                and loso_better_cells >= MATRIX_LOSO_MIN_CELLS)


def select_matrix_base(adopted: list[str], beats) -> str | None:
    """Base after the crosses: go through the adopted variants in ``MATRIX_SIMPLICITY`` order; a later one replaces
    the current one only if it wins the cross (``beats(challenger, current) -> bool``, the SEASON_2026 rule). A tie
    keeps the simpler. ``None`` if nothing was adopted."""
    ordered = [v for v in MATRIX_SIMPLICITY if v in adopted]
    if not ordered:
        return None
    best = ordered[0]
    for challenger in ordered[1:]:
        if beats(challenger, best):
            best = challenger
    return best


CLIMATE_MATRIX = {
    "fecha": "2026-11-08",
    "estado": "preregistrada el 2026-11-08 DESPUÉS de ver los resultados de la temporada 2026 (b3 adoptada por el "
              "Brier; d1 y d2 en empate); aprobada por Rosa el 2026-11-08 con tres respuestas y un agregado hechos "
              "antes de correr (ver «respuestas_de_rosa»)",
    "respuestas_de_rosa": [
        "desempates del orden de simplicidad aceptados (d3 antes que d5; ventanas antes que anomalías)",
        "los días >= 20 mm también como anomalía en e1 y e2: aceptado",
        f"agregado (filtro contra ganadores por azar): una variante solo se adopta si, además de ganar con SEASON_2026 "
        f"frente a L + 5a, mejora el Brier frente a L + 5a en al menos {MATRIX_LOSO_MIN_CELLS} de las "
        f"{MATRIX_LOSO_CELLS} celdas de la validación dejando una temporada fuera (8 temporadas × 3 horizontes; "
        "mediana de 5 semillas; mejora = Brier estrictamente menor). Aplica igual a b3 (19 de 24 en la corrida del "
        "2026-11-08), para que la base vigente pase el mismo filtro. Se agregó para controlar las comparaciones "
        "múltiples, ANTES de ver los resultados de b4, d3, d4, d5, e1, e2 y n1 (los de b1, b2, b3, d1 y d2 en "
        "SEASON_2026 ya se habían visto en parte)",
    ],
    "motivo": "Rosa quiere conocer todas las formas razonables de usar el clima, comparadas entre sí, antes del "
              "diagnóstico frente a la persistencia",
    "base": "L + 5a (sin clima). Todas las variantes: orígenes desde 2005, lluvia CHIRPS v3, temperatura y humedad "
            "ERA5-Land, Niño 1+2 de la NOAA; los mismos bloques, Platt, 5a y semillas que SEASON_2026",
    "variantes": {
        "b1": "media de 5 semanas de la lluvia (paso b)",
        "b2": "b1 + media de 5 semanas de la humedad (paso b)",
        "b3": "b2 + media de 5 semanas de la temperatura + nino12_anom_media3",
        "b4": "b3 sin el Niño",
        "d1": "las 14 columnas del paso d (4 ventanas de lluvia, temperatura y humedad + 2 conteos de días >= 20 mm)",
        "d2": "d1 + nino12_anom_media3",
        "d3": "solo las 4 ventanas de temperatura",
        "d4": "solo las 4 ventanas de lluvia + los 2 conteos de días >= 20 mm",
        "d5": "solo las 4 ventanas de humedad",
        "e1": "las 14 columnas de d1 como anomalía frente a la climatología distrito × semana epidemiológica del bloque",
        "e2": "e1 + nino12_anom_media3",
        "n1": "las columnas de b3 con monotone_constraints de XGBoost: +1 en nino12_anom_media3 y 0 en el resto",
    },
    "columnas": MATRIX_VARIANTS,
    "anomalias_e1": {
        "referencia": "la B5 del estudio 05 (denguekay.features.onset_features: anomalías de clima con la climatología "
                      "ajustada con el corte de cada bloque, prepare_block) y features.climate.fit_climatology "
                      "(media distrito × semana epidemiológica, la 53 comparte celda con la 52, solo semanas cerradas "
                      "al corte)",
        "climatologia": "para cada bloque, la media por distrito y semana epidemiológica de cada serie semanal "
                        "(lluvia CHIRPS, temperatura y humedad ERA5-Land, y días >= 20 mm por semana) con las "
                        "semanas desde 2000 cuyo sábado es <= el corte del bloque (su primer origen); se calcula "
                        "dentro del bucle de bloques (prepare_block de predict_blocks_weighted), como la B5",
        "columnas": "anomalía semanal = valor − climatología de su distrito y semana; cada ventana de d1 se calcula "
                    "sobre la anomalía (media en las ventanas de lluvia, temperatura y humedad; suma en los dos "
                    "conteos de días >= 20 mm), con las mismas semanas que d1",
        "nota": "las filas de entrenamiento y de prueba de un bloque usan la misma climatología (la del corte), como "
                "la B5; ningún dato posterior al corte entra",
        "dejando_una_temporada_fuera": f"la climatología se ajusta con todas las semanas fuera de la temporada dejada "
                                       f"fuera ampliada {CLIMATOLOGY_BUFFER_WEEKS} semanas antes y después",
    },
    "nino_monotono_n1": "XGBoost 3.4.1 respeta monotone_constraints con multi_strategy=multi_output_tree (comprobado "
                        "el 2026-11-08 con datos sintéticos de relación decreciente: la predicción restringida quedó "
                        "plana). La restricción actúa sobre la parte de los árboles; con la base_margin fija, μ es "
                        "monótona en el Niño, y también la probabilidad NB2 (creciente en μ) y la calibrada si la "
                        "pendiente de Platt es positiva (se reporta)",
    "regla": "SEASON_2026 (decide_season_2026 + adopt_season_2026): el Brier sobre 2010, 2015, 2016, 2022, 2023 y "
             "2026, gana con >= 5 de 6 a favor y 0 en contra, vetos con >= 4 de 6; adopción con >= 2 horizontes "
             "ganados y sin «pierde» ni «compensa» en el Brier, la F1 ni la razón MAE; y, para adoptar, el filtro "
             f"de la validación dejando una temporada fuera (adopt_matrix: >= {MATRIX_LOSO_MIN_CELLS} de "
             f"{MATRIX_LOSO_CELLS} celdas con mejor Brier que L + 5a). Los cruces entre adoptadas usan "
             "SEASON_2026 sin el filtro",
    "comparaciones": {
        "1": "cada una de las 12 variantes frente a L + 5a",
        "2": "las adoptadas cruzadas entre sí, todos los pares, con la misma regla; la base resulta de "
             "select_matrix_base (orden de MATRIX_SIMPLICITY; una posterior reemplaza a la vigente solo si gana el "
             "cruce; un empate deja la más simple)",
        "3": "d1, d2 y e1 frente a b3 con la misma regla, aunque no se adopten; se reporta como cruce y no cambia la "
             "base por sí solo",
    },
    "numero_de_comparaciones": "12 frente a L + 5a + 3 cruces fijos + k(k−1)/2 cruces entre las k adoptadas: entre 15 y "
                               "81 (cada una con 3 reglas en 3 horizontes)",
    "metricas_por_variante": "Brier, BSS frente a la climatología del paso d, AUPRC general y en inicios "
                             "(persistencia < max(umbral_brote_casos, 2)), F1 a 0,50, razón MAE y razón RMSE, mediana de "
                             "5 semillas, en las 6 temporadas que deciden, 2017, 2024 y posterior_2026; la HU0007-4 por "
                             "celda en temporada_2026 y posterior_2026 (posterior_2026 solo se reporta)",
    "dejando_una_temporada_fuera": "la lectura de SEASON_2026 (2010, 2015, 2016, 2017, 2022, 2023, 2024 y 2026) para las "
                                   "12 variantes; optimista, solo compara variantes entre sí y no decide",
    "shap": f"por horizonte (media de |SHAP| del regresor, semilla 17) en {', '.join(MATRIX_SHAP_BLOCKS)}, de las "
            f"variantes adoptadas y de las {MATRIX_SHAP_TOP_BRIER} mejores por el Brier (mediana, sobre las 6 temporadas "
            "y los 3 horizontes, de la diferencia de Brier frente a L + 5a)",
    "reutilizacion": "las predicciones de L + 5a, b3, d1 y d2 guardadas el 2026-11-08 (todos los bloques, 5 semillas) se "
                     "reutilizan si G41 confirma que se reproducen: se reentrena la semilla 17 de cada una en todos los "
                     "bloques y debe coincidir con la guardada (diferencia <= 1e-6). b1 y b2 solo tienen guardados los "
                     "bloques anteriores a 2026: se reentrenan completas y G41 se aplica a esos bloques. Si una guarda "
                     "G41 falla, esa variante se reentrena completa y se reporta",
    "guardas_antes_de_mirar_resultados": [
        "las de SEASON_2026 (G17, G25, G29, G30, G35a, G35b, G40, G42, G43 y G44) sobre los mismos datos",
        "b4, d3, d4 y d5 son subconjuntos de columnas ya validadas (b3 y d1): se repiten su cobertura y "
        "disponibilidad",
        "G45 (definición de e1): con datos sintéticos, la anomalía de cada ventana es la ventana del valor menos la "
        "ventana de la climatología; en los datos reales, para cada bloque, columna de e1 + la misma ventana de la "
        "climatología = columna de d1 (diferencia <= 1e-9)",
        "G46 (no fuga de e1 por el origen): cambiar el clima de las semanas posteriores al origen no cambia ninguna "
        "columna de e1",
        "G47 (no fuga de e1 por el corte): cambiar el clima de las semanas posteriores al corte de un bloque no cambia "
        "su climatología ni las columnas de e1 de los orígenes anteriores al corte",
        "G48 (cobertura y disponibilidad de e1): ningún origen desde 2005 sin valor; las mismas semanas que d1, con su "
        "disponibilidad contra origen_cierre + 14 días",
        "G49 (n1 monótono): con el modelo de cada bloque (semilla 17), para 1000 orígenes al azar y el Niño en una grilla "
        "de −3 a 6, μ no baja en ningún horizonte; se reporta la pendiente de Platt de cada bloque y horizonte",
        "G50 (n1 sin la restricción reproduce b3): con monotone_constraints en 0, n1 da exactamente las predicciones "
        "de b3 (semilla 17, un bloque)",
        "si una guarda falla, se detiene y se explica; no se ajusta nada para que pase",
    ],
    "declaraciones": [
        "la matriz se fijó DESPUÉS de ver los resultados de la temporada 2026",
        "con 12 variantes y hasta 81 comparaciones crece la probabilidad de un «gana» por azar; los «gana» se "
        "reportan junto con el número total de comparaciones y no se corrige el umbral",
        "b1, b2, b3, d1 y d2 ya se compararon antes (pasos b y d y temporada 2026); aquí se repiten con la regla de "
        "SEASON_2026 para tenerlas en la misma tabla",
    ],
    "codigo": "code/phase_climate_matrix.py (anomalías de e1 y e2, restricción monótona de n1, guardas G45 a G50); "
              "tests/test_phase_climate_matrix.py; el resto reutiliza phase_2026.py",
    "notebook": "notebooks/16_matriz_clima.ipynb",
    "metricas": "docs/metricas/matriz_clima.json",
    "mlflow": "denguekay/mejora_modelo_matriz_clima",
    "despues": "el diagnóstico frente a la persistencia",
}


# ---------------------------------------------------------------------------
# Combined alert (Rosa, 2026-11-08, after the diagnosis against persistence)
# ---------------------------------------------------------------------------

COMBINED_ALERT_VARIANTS = ("d3", "b3")          # d3 = the V3 base, b3 = the challenger; each against itself
COMBINED_ALERT_PRIMARY = "f1_050"
COMBINED_ALERT_GUARDS = ("precision_050",)      # plus the lead time on clean onsets (guard, not a way to win)
COMBINED_ALERT_NINO = (2017, 2026)              # Niño seasons; posterior_2026 is reported with them
COMBINED_ALERT_NORMAL = (2010, 2015, 2016, 2022, 2023, 2024)
COMBINED_ALERT_REPORTED = (2010, 2015, 2016, 2017, 2022, 2023, 2024, 2026)


def decide_combined_alert(candidate: pd.DataFrame, reference: pd.DataFrame, ranges: pd.DataFrame,
                          lead_time_diff: pd.DataFrame, outbreak_weeks_2026: dict[int, int]) -> pd.DataFrame:
    """Verdict per horizon of the combined alert against the 0.50 alert alone of the same variant.

    The alert rule of SEASON_2026 as Rosa stated it on 2026-11-08: F1 at 0.50 is the primary metric over the 6
    seasons (wins with >= 5 of 6 in favour and 0 against; loses symmetrically); precision at 0.50 and the lead time
    on clean onsets are guards (a guard against in >= 4 of 6 vetoes a win -> «compensa (empate)»). Unlike
    ``decide_multi_season``, the lead time is only a guard: it cannot make a win by itself. A horizon where 2026 has
    fewer than ``SEASON_2026_MIN_OUTBREAK_WEEKS`` outbreak weeks uses the 5 usual seasons (4 of 5, veto 3 of 5).
    A season's lead-time difference counts beyond one onset (``> 1/n``), as in ``decide_multi_season``.
    """
    rows = []
    for h in sorted(candidate.horizonte.unique()):
        six = outbreak_weeks_2026.get(h, 0) >= SEASON_2026_MIN_OUTBREAK_WEEKS
        seasons = SEASON_2026_DECIDING if six else DECIDING_SEASONS
        k, veto = (SEASON_2026_MIN_IN_FAVOUR, SEASON_2026_GUARD_VETO) if six else (MIN_IN_FAVOUR, GUARD_VETO_AGAINST)
        blocks = [block_name(s) for s in seasons]
        c = candidate[candidate.horizonte.eq(h)].set_index("bloque")
        r = reference[reference.horizonte.eq(h)].set_index("bloque")
        e = ranges[ranges.horizonte.eq(h)].set_index("bloque")
        counts = {m: _season_signs({b: c.at[b, m] - r.at[b, m] for b in blocks}, {b: e.at[b, m] for b in blocks})
                  for m in (COMBINED_ALERT_PRIMARY, *COMBINED_ALERT_GUARDS)}
        lead = lead_time_diff[lead_time_diff.horizonte.eq(h)].iloc[0]
        counts["antelacion"] = _season_signs({b: float(lead[f"diferencia_{b}"]) for b in blocks},
                                             {b: 1 / float(lead[f"episodios_{b}"]) for b in blocks})
        f, a = counts[COMBINED_ALERT_PRIMARY]
        improves, worsens = f >= k and a == 0, a >= k and f == 0
        veto_a = [m for m in (*COMBINED_ALERT_GUARDS, "antelacion") if counts[m][1] >= veto]
        veto_b = [m for m in (*COMBINED_ALERT_GUARDS, "antelacion") if counts[m][0] >= veto]
        if improves and not veto_a:
            verdict = "gana"
        elif worsens and not veto_b:
            verdict = "pierde"
        elif improves or worsens:
            verdict = "compensa (empate)"
        else:
            verdict = "empate"
        rows.append({"horizonte": h, "veredicto": verdict, "temporadas": len(seasons),
                     "vetos": ", ".join(veto_a) or None, "vetos_contra_referencia": ", ".join(veto_b) or None,
                     **{f"a_favor_{m}": v[0] for m, v in counts.items()},
                     **{f"en_contra_{m}": v[1] for m, v in counts.items()}})
    return pd.DataFrame(rows)


def adopt_combined_alert(verdict: pd.DataFrame) -> bool:
    """>= 2 horizons won and no «pierde» nor «compensa (empate)» (the adoption of SEASON_2026, on the alert)."""
    return bool(verdict.veredicto.eq("gana").sum() >= STEP_B_MIN_HORIZONS_WON
                and not verdict.veredicto.isin(["pierde", "compensa (empate)"]).any())


COMBINED_ALERT = {
    "fecha": "2026-11-08",
    "estado": "preregistrada el 2026-11-08 DESPUÉS del diagnóstico frente a la persistencia (que mostró que la "
              "persistencia avisa más inicios limpios de 2026 que p >= 0,50); commiteada antes de calcular",
    "pedido_de_rosa": "alerta combinada = probabilidad calibrada >= 0,50 o alerta de la persistencia, sobre las "
                      "predicciones guardadas, sin reentrenar; d3 (base) y b3 (retadora), cada una frente a sí misma "
                      "con la alerta solo por p >= 0,50",
    "definicion": {
        "alerta_050": "probabilidad_calibrada >= 0,50 (protocol.ALERT_THRESHOLD), Platt por horizonte con los "
                      "bloques anteriores (protocolo del estudio)",
        "alerta_persistencia": "la ya existente del protocolo (denguekay.evaluation.protocol.add_protocol_alerts -> "
                               "metrics.alerts_from_counts): persistencia > umbral_brote_casos de la semana objetivo "
                               "y persistencia >= MIN_OUTBREAK_CASES (2 casos); persistencia = casos del distrito en "
                               "la semana del origen",
        "alerta_combinada": "alerta_050 o alerta_persistencia; reemplaza a alerta_050 en las métricas a 0,50 "
                            "(F1, precisión, recall, vp, fp, fn) y en la antelación",
    },
    "datos": "predicciones guardadas de d3 (models/experimentos/mejora_modelo/matriz_clima/predicciones_d3.csv.gz) "
             "y b3 (temporada_2026/predicciones_b3.csv.gz), 5 semillas, reevaluadas con el protocolo del estudio "
             "(p26.inputs_2026, mezcla 5a); medianas de 5 semillas",
    "regla": "decide_combined_alert: F1 a 0,50 principal sobre 2010, 2015, 2016, 2022, 2023 y 2026 (gana con >= 5 de "
             "6 a favor y 0 en contra; pierde simétrico); guardas: precisión a 0,50 y antelación en los inicios "
             "limpios (en contra en >= 4 de 6 veta la victoria -> «compensa (empate)»); umbral de empate = mayor "
             "rango entre semillas de las dos alertas (protocol.tie_threshold); antelación con la semilla 17 y la "
             "banda de un inicio por temporada; un horizonte con < 30 semanas brote en 2026 usa las 5 temporadas "
             "habituales. Adopción: >= 2 horizontes ganados y ningún «pierde» ni «compensa» "
             "(adopt_combined_alert)",
    "no_cambia": "la probabilidad, el Brier, la AUPRC y el conteo son los mismos en las dos alertas; por eso no "
                 "entran en la regla",
    "reportado_sin_decidir": [
        "precisión, recall y F1 a 0,50 por temporada y horizonte (2010, 2015, 2016, 2017, 2022, 2023, 2024, 2026 y "
        "posterior_2026) de las dos alertas",
        "falsas alarmas añadidas (fp combinada − fp sola, mediana de semillas) en años normales (2010, 2015, 2016, "
        "2022, 2023, 2024) y en años de Niño (2017, 2026 y posterior_2026)",
        "HU0007-4 por celda (sp.hu0007_4_compliance) con la alerta combinada",
        "lectura: el veredicto de la regla de la alerta tal como está en decide_multi_season (la antelación también "
        "puede ganar)",
    ],
    "declaraciones": [
        "se fijó después de ver el diagnóstico frente a la persistencia y con 2026 entre las temporadas que deciden",
        "la alerta combinada avisa en un superconjunto de las semanas de p >= 0,50: el recall y la antelación no "
        "pueden empeorar, así que la guarda de la antelación no puede vetar; la única que puede es la precisión",
        "dos comparaciones (d3 y b3); se adopta para cada variante por separado",
    ],
    "codigo": "code/phase_combined_alert.py; tests/test_combined_alert.py",
    "notebook": "notebooks/18_alerta_combinada.ipynb",
    "metricas": "docs/metricas/alerta_combinada.json",
    "despues": "con el OK de Rosa, el preregistro del ajuste de hiperparámetros sobre L + 5a + d3 (sin correr)",
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
