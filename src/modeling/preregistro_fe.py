"""Preregistro de las variantes de variables (fase 1 del encargo de FE sobre E3·S4_s2).

Lista cerrada de variantes que la fase 2 compara contra la referencia B con la
regla simétrica del protocolo. **No se amplía después de ver resultados sin la
aprobación de Rosa.** Las ventanas son a priori; el diagnóstico de inicios
(``diagnostico_inicios``, temporadas 2017–2021) solo aporta la evidencia que
se cita en ``evidencia_fase1``.

Convenciones:

- ``o`` es el origen (``origen_cierre`` de la fila h=2 de ``tabla_origenes``);
  toda variable usa solo semanas ≤ ``o``. ``k`` = semanas antes del objetivo
  ``t = o + h``.
- En la fase 2, toda transformación aprendida (climatología y anomalías,
  ranking de distritos núcleo, CP1 socio) se **recalcula con el entrenamiento
  de cada bloque**; lo ajustado con 2017–2021 en la fase 1 era solo para el
  diagnóstico.
- Si una variante tiene nulos de arranque distintos de ``base_6``, ambas se
  evalúan sobre la intersección de filas y se reporta.
"""

ADVERTENCIA_RECONSTRUIDA = (
    "Las fracciones 2018–2024 son reconstrucción retrospectiva con 2025 y la fecha de publicación de la "
    "población anual no está verificada: el resultado no puede presentarse como un pronóstico que se habría "
    "podido emitir en esos años.")

VARIANTES = [
    # ------------------------------------------------------------------
    # Bloque A: familias de gold h=2, re-ensayadas tal cual sobre E3·S4_s2
    # ------------------------------------------------------------------
    {"id": "A1", "bloque": "A", "fuente": "epidemiologica", "familia": "vecinos",
     "columnas": ["vecinos_media_casos_knn5_h2", "vecinos_frac_con_casos_knn5_h2"],
     "regla": "gold h=2 (vecinos_jerarquia.construir_vecinos_jerarquia, knn5 uniforme, casos de t−h)",
     "ventana": "semana o", "por_que": "re-ensayo de la ablación 25 (S1) sobre S4",
     "evidencia_fase1": "nivel de vecinos: observada en origen_2_4 y previa_5_8",
     "comparar_contra": ["referencia_B"]},
    {"id": "A2", "bloque": "A", "fuente": "epidemiologica", "familia": "jerarquia",
     "columnas": ["provincia_otros_casos_h2", "provincia_otros_frac_con_casos_h2",
                  "region_otros_casos_h2", "region_otros_frac_con_casos_h2"],
     "regla": "gold h=2 (otros distritos de la provincia y de la región, casos de t−h)",
     "ventana": "semana o", "por_que": "re-ensayo de la ablación 25 (S1, elegida en validación) sobre S4",
     "evidencia_fase1": "nivel provincial y regional: observada en origen_2_4 y previa_5_8",
     "comparar_contra": ["referencia_B"]},
    {"id": "A3", "bloque": "A", "fuente": "meteorologica", "familia": "clima_gold",
     "columnas": ["hum_rel_media_media5_h2", "precip_total_mm_media5_h2"],
     "regla": "gold h=2 (media de 5 semanas observadas hasta t−h)",
     "ventana": "semanas o−4..o", "por_que": "re-ensayo de la ablación 26 (S1, empeoró) sobre S4",
     "evidencia_fase1": "humedad y precipitación observadas: hipótesis solo 2017",
     "nulos_de_arranque": "65 filas (una semana por distrito): evaluar sobre la intersección",
     "comparar_contra": ["referencia_B"]},
    {"id": "A4", "bloque": "A", "fuente": "sociodemografica", "familia": "poblacion_2017",
     "columnas": ["log_poblacion_censo_2017"], "regla": "gold (censo 2017, fija)", "ventana": "fija",
     "por_que": "era parte del clasificador viejo base_6_poblacion_2017; S4 no tiene clasificador",
     "evidencia_fase1": "no evaluada (fija por distrito)", "comparar_contra": ["referencia_B"]},
    {"id": "A5", "bloque": "A", "fuente": "sociodemografica", "familia": "poblacion_anual",
     "columnas": ["log_poblacion_anual"], "regla": "gold (población anual interpolada)", "ventana": "año de t",
     "por_que": "re-ensayo de la ablación 27 sobre S4", "evidencia_fase1": "no evaluada",
     "advertencia": ADVERTENCIA_RECONSTRUIDA, "comparar_contra": ["referencia_B"]},
    {"id": "A6", "bloque": "A", "fuente": "sociodemografica", "familia": "fracciones_2017",
     "columnas": ["fraccion_rural_2017", "fraccion_menores_15_2017", "fraccion_desague_red_2017"],
     "regla": "gold (censo 2017, fijas)", "ventana": "fija", "por_que": "re-ensayo de la ablación 27 (fija_tres)",
     "evidencia_fase1": "no evaluada (fijas por distrito)", "comparar_contra": ["referencia_B"]},
    {"id": "A7", "bloque": "A", "fuente": "sociodemografica", "familia": "fracciones_anuales_cp1",
     "columnas": ["socio_anual_cp1"],
     "regla": "CP1 de las 15 fraccion_*_anual estandarizadas, ajustado con el entrenamiento de cada bloque "
              "(como el eje del notebook 21); una sola variante resumida, no una por fracción",
     "ventana": "año de t", "por_que": "resumen de la familia anual sin multiplicar comparaciones",
     "evidencia_fase1": "no evaluada", "advertencia": ADVERTENCIA_RECONSTRUIDA,
     "comparar_contra": ["referencia_B"]},
    # ------------------------------------------------------------------
    # Bloque B: variables nuevas, calculadas en memoria
    # ------------------------------------------------------------------
    {"id": "B1", "bloque": "B", "fuente": "epidemiologica", "familia": "dinamica_espacial",
     "columnas": ["vecinos_frac_en_brote", "vecinos_n_casos_nuevos",
                  "vecinos_log_media_casos_cambio_1", "vecinos_log_media_casos_cambio_4",
                  "provincia_otros_frac_en_brote", "provincia_log_otros_casos_cambio_1",
                  "provincia_log_otros_casos_cambio_4", "region_otros_frac_en_brote",
                  "region_log_otros_casos_cambio_1", "region_log_otros_casos_cambio_4"],
     "regla": "fracción en brote (etiqueta de la semana, que usa años previos y casos de la semana), nº de "
              "vecinos knn5 que pasan de 0 a >0 casos, y cambio de log(1 + casos) en 1 y 4 semanas; "
              "provincia y región excluyen al propio distrito",
     "ventana": "semana o; cambios o−1→o y o−4→o (1 y 4 semanas, fijados a priori para los tres niveles)",
     "por_que": "agrega la dirección y la etiqueta de brote de los otros distritos, que gold no trae",
     "evidencia_fase1": "observada: fracción en brote (3 niveles), nº con casos nuevos, cambio 1 semana en "
                        "origen_2_4 (3 niveles), cambio 4 semanas regional; vecinos cambio 4 semanas: no "
                        "observada; provincia cambio 4 semanas: hipótesis solo 2017 (se incluyen por simetría a priori)",
     "comparar_contra": ["referencia_B", "base_6+A1+A2"]},
    {"id": "B2", "bloque": "B", "fuente": "epidemiologica", "familia": "distritos_nucleo",
     "columnas": ["nucleo_log_casos", "nucleo_frac_en_brote", "nucleo_log_casos_cambio_4"],
     "regla": "los 5 distritos con más casos acumulados en el entrenamiento del bloque, excluido el propio: "
              "log(1 + casos), fracción en brote y cambio de log(1 + casos) en 4 semanas",
     "ventana": "semana o; cambio o−4→o",
     "por_que": "hipótesis de posible importación desde los distritos de más casos (sin lectura causal); "
                "N = 5 fijado a priori igual que knn5, no ajustado",
     "evidencia_fase1": "observada: nivel y fracción en brote en ambas ventanas; cambio 4 semanas en "
                        "origen_2_4 (en previa_5_8, hipótesis solo 2017)",
     "comparar_contra": ["referencia_B"]},
    {"id": "B3", "bloque": "B", "fuente": "epidemiologica", "familia": "historia_propia_ampliada",
     "columnas": ["propia_semanas_desde_ultimo_caso", "propia_pendiente_4", "propia_log_casos_temporada_anterior"],
     "regla": "semanas desde la última semana con casos (tope 52), pendiente MCO de log(1 + casos) en "
              "o−3..o, y log(1 + casos) de la temporada anterior completa; antes del panel (temporada 2016) "
              "con la historia de la regla de brote (epi_piura_semanal.csv del manifest, sin registro = cero); "
              "si no hay historia, nulo sin excluir la fila",
     "ventana": "hasta o; temporada anterior cerrada",
     "por_que": "base_6 resume 4 semanas; esto agrega cuánto lleva el distrito sin casos y su nivel previo",
     "evidencia_fase1": "semanas desde el último caso: observada; pendiente: no observada (se mantiene a "
                        "priori, hipótesis); temporada anterior: no evaluable en 2017. Aceleración descartada: "
                        "no observada y es una segunda diferencia de conteos chicos (más ruido que la pendiente)",
     "comparar_contra": ["referencia_B"]},
    {"id": "B4", "bloque": "B", "fuente": "epidemiologica", "familia": "linea_base_estacional",
     "columnas": ["linea_base_log_umbral_h2", "linea_base_log_umbral_h3", "linea_base_log_umbral_h4"],
     "regla": "log(1 + umbral) de la misma semana objetivo t+h en los 5 años previos (etiqueta_brote, con "
              "su test de no fuga), una columna por salida h=2, 3, 4, todas conocidas en el origen",
     "correccion": "2026-10-27, antes de cualquier resultado de la fase 2 (aprobada por Rosa): versión "
                   "anterior con 6 columnas (log(1 + media) y log(1 + umbral) por h); se deja solo el umbral "
                   "porque ya contiene la media (media + 1,5 DE) y conviene menos columnas con solo 5 años previos",
     "ventana": "años previos a la semana objetivo (se conoce al emitir)",
     "por_que": "lleva al modelo de conteo la referencia estacional que hoy solo usa la binomial negativa",
     "evidencia_fase1": "no aplica (no es dinámica previa al inicio)", "comparar_contra": ["referencia_B"]},
    {"id": "B5", "bloque": "B", "fuente": "meteorologica", "familia": "clima_incubacion",
     "columnas": [f"{c}_anomalia_{v}" for v in ("o4_o", "o9_o5")
                  for c in ("temp_media", "temp_min", "hum_rel_media", "precip_total_mm")],
     "regla": "media semanal de la anomalía (valor − climatología distrito × semana ajustada con el "
              "entrenamiento del bloque) en o−4..o y en o−9..o−5 (5 semanas cada una, sin solaparse)",
     "ventana": "o−4..o y o−9..o−5: k = h..h+4 y h+5..h+9; en h=4, 4–8 y 9–13 (las ventanas a priori 4–8 y 8–12 "
                "sin la semana compartida)",
     "correccion": "2026-10-27, antes de cualquier resultado de la fase 2b (aprobada por Rosa): versión anterior "
                   "o−8..o−4, que compartía la semana o−4 con la otra ventana",
     "por_que": "clima con rezagos de incubación que gold no trae (temperatura) y en anomalía, que quita el "
                "nivel propio del distrito y la semana",
     "evidencia_fase1": "anomalías de temperatura media (−) y humedad (+): observada; temperatura mínima y "
                        "precipitación: hipótesis solo 2017; valores sin anomalía de temperatura media: no observada",
     "comparar_contra": ["referencia_B", "base_6+A3"]},
]

B6_CONDICIONAL = {
    "id": "B6", "bloque": "B", "fuente": "sociodemografica", "familia": "variantes_socio_nuevas",
    "estado": "no preregistrada: solo si alguna de A4–A7 gana; en ese caso se propone a Rosa antes de correrla",
    "por_que": "la fase 1 no analizó lo socio (fijo por distrito, no describe la dinámica previa al inicio)",
}

ACLARACION_EXTENSION = (
    "2026-10-27, antes de cualquier resultado de la fase 2b (aprobada por Rosa): en las comparaciones de "
    "extensión el candidato es base_6 + familia A + familia B y la referencia base_6 + familia A (B1: "
    "base_6+A1+A2+B1 frente a base_6+A1+A2; B5: base_6+A3+B5 frente a base_6+A3), para medir qué agrega lo nuevo.")

COMBINADA = {
    "id": "C", "fecha": "2026-10-27, antes de cualquier corrida de la fase 2c (aprobado por Rosa)",
    "regla_de_entrada": "familias de A y B que ganan (o empatan con mejor antelación o recall en brotes nuevos) "
                        "frente a su referencia; sin búsqueda hacia adelante",
    "candidatas": {"C": ["B1", "B2", "B3"], "C3": ["B3"]},
    "comparaciones": [
        {"candidata": "C", "referencia": "B", "nota": "intersección de filas de C (B∩C)"},
        {"candidata": "C3", "referencia": "B", "nota": "es la comparación B3 frente a B de la 2b; se reutiliza "
                                                         "porque las filas son las mismas (B3 no excluye filas)"},
        {"candidata": "C", "referencia": "C3", "nota": "intersección de filas de C (C3∩C)"},
    ],
    "decision": [
        "«gana a X» = adoptable frente a X: gana en algún horizonte y no pierde en ninguno (estrategias_horizonte.adopcion)",
        "si ni C ni C3 ganan a B, se mantiene base_6",
        "si solo una de las dos gana a B, se elige esa",
        "si ambas ganan a B: C si gana a C3; si C empata o pierde frente a C3, C3",
        "ante empate entre candidatas del mismo nivel gana la de menos columnas: es la versión por variables de "
        "la regla de simplicidad del protocolo (menos modelos)",
    ],
    "robustez_solo_lectura": "para la elegida frente a B: quitar del entrenamiento, una a la vez, las primeras 8 "
                             "semanas de orígenes de 2017 y la temporada 2018 (5 semillas) y reportar si se mantiene "
                             "el signo de la diferencia de F1 y de antelación en 2022 y 2023; no decide",
    "shap": "importancia SHAP por horizonte de la elegida (HU0008-4), semilla 17, bloques 2022, 2023 y 2024",
}


FASE4 = {
    "fecha": "2026-10-27, antes de cualquier corrida de la fase 4 (aprobado por Rosa)",
    "configuracion_de_partida": "C3·S4_s2 (base_6 + B3), hiperparámetros heredados (la fase 3 dejó la base), "
                                "α dentro de la muestra",
    "4.1_interaccion": "no se corre: los hiperparámetros elegidos en la fase 3 son los mismos que usó la fase 2, "
                       "así que reevaluar las familias con ellos daría exactamente las mismas predicciones (mismos "
                       "datos, semillas y parámetros) y no agrega información",
    "4.2_alfa": {
        "candidata": "C3·S4_s2 con α OOS", "referencia": "C3·S4_s2 con α dentro de la muestra",
        "alfa_oos": "por bloque y horizonte, máxima verosimilitud NB2 con las predicciones fuera de muestra de "
                    "todos los bloques anteriores (acumuladas) cuya semana objetivo cerró en el corte del bloque",
        "primer_bloque": "temporada_2021 usa el pseudo-bloque temporada_2020 (entrenado con lo cerrado al "
                         "2019-08-03), que solo estima α: no se evalúa ni entra en Platt",
        "respaldo": "si la α OOS de un bloque y horizonte no converge, queda a menos de 1e-3 (en log α) de un "
                    "límite del optimizador [-12, 6], o sale de [mín / 5, máx × 5] de las α dentro de la muestra "
                    "de 2021–2024 (mismo horizonte y semilla), ese bloque usa la α dentro de la muestra y se "
                    "reporta (salida_probabilistica.alfas_oos); fijado en el código antes de ver ninguna α OOS",
        "nota_rango": "el rango usa las α dentro de la muestra de los 4 bloques, incluidos los posteriores al "
                      "bloque que se revisa; es solo un control de validez, no entra en ninguna predicción",
        "adopcion": "gana → α OOS; empate o pierde → α dentro de la muestra (más simple: sin pseudo-bloque)",
        "limitacion": "2020 tiene solo 2 semanas brote y cruza el inicio de la pandemia (posible subregistro, "
                      "hipótesis); la dispersión de una temporada tranquila puede no representar la de una "
                      "epidémica, y esa α entra en la cadena de Platt de 2022",
        "lectura": "α por bloque y horizonte con los dos métodos, incluida la de 2021 (OOS desde 2020)",
    },
    "4.3_s4_s3": {
        "candidata": "C3·S4_s3", "referencia": "C3·S4_s2",
        "alfa": "la que salga de la 4.2, en las dos ramas",
        "adopcion": "gana → S4_s3; empate → S4_s2 (más simple: sin margen de persistencia); pierde → S4_s2",
    },
    "4.4_rangos": "mínimo, mediana, máximo y rango de las 5 semillas de la configuración final por métrica, "
                  "bloque (2022–2025) y horizonte, más antelación, recall de brotes nuevos y α; si la "
                  "configuración final no cambia, se reutilizan las semillas de la base de la fase 3",
    "lecturas_que_no_deciden": ["antelación", "recall de brotes nuevos", "posible señal de temporada",
                                "costo en el conteo con el contraste 2024",
                                "robustez sin las 8 primeras semanas de orígenes de 2017"],
    "regla": "simétrica del protocolo, 5 semillas, por horizonte; 2024 no decide",
}


def comparaciones() -> dict:
    """Número de comparaciones preregistradas (cada una se evalúa en h=2, 3 y 4)."""
    por_variante = sum(len(v["comparar_contra"]) for v in VARIANTES)
    return {"bloque_A": sum(len(v["comparar_contra"]) for v in VARIANTES if v["bloque"] == "A"),
            "bloque_B": sum(len(v["comparar_contra"]) for v in VARIANTES if v["bloque"] == "B"),
            "combinada": 2, "total": por_variante + 2, "condicional_B6": 1,
            "fase3_hiperparametros": 1, "fase4": 2, "total_encargo": por_variante + 2 + 1 + 2,
            "nota_encargo": "total (fases 2a–2c) + 1 de la fase 3 + 2 de la fase 4 (4.2 y 4.3); la 4.1 no se corre",
            "nota_combinada": "C frente a B y C frente a C3; C3 frente a B reutiliza B3 frente a B (2b)",
            "nota": "cada comparación se evalúa por horizonte (h=2, 3, 4); 2024 no decide"}


def como_dict() -> dict:
    """Preregistro completo, listo para guardar en el JSON de métricas."""
    return {"variantes": VARIANTES, "b6": B6_CONDICIONAL, "combinada": COMBINADA, "fase4": FASE4,
            "aclaracion_extension": ACLARACION_EXTENSION,
            "comparaciones": comparaciones(),
            "reglas": ["ventanas a priori, sin elegir el rezago que más resaltó",
                       "transformaciones aprendidas ajustadas con el entrenamiento de cada bloque",
                       "nulos de arranque distintos: evaluar sobre la intersección y reportar",
                       "la lista no se amplía sin aprobación de Rosa"]}
