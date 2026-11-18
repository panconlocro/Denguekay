"""Dictionary of the variables of the current configuration, the V4 (HU0006-1 and HU0006-3).

The V4 section (``v4_document``) is generated from the code: the 16 columns come from the versioned V4
specification and every one needs a complete entry (``v4_dictionary``). The v2 part below is kept as history.
It is generated from the code: the columns come from ``frozen_configs``, the gold
names from ``horizon_strategies.model_columns(2)``, the labels from
``diagnostico_inicios.ETIQUETAS`` and the ranges are computed in memory on the
origin table. Nothing is written to ``data/``.

Usage (from the repository root)::

    python -m denguekay.model.variable_dictionary
"""

import json

import pandas as pd

from denguekay.evaluation import onsets as di
from denguekay.model import horizon_strategies as eh

# Text per generic variable. "ventana" is relative to the origin o = t - 2 of the h=2 row.
DEFINITIONS = {
    "hist_lag_a": {
        "fuente": "epidemiológica (casos de dengue, silver integrado)",
        "definicion": "casos de dengue de la semana de origen o",
        "ventana": "semana o", "transformacion": "ninguna (conteo)", "tipo": "entero ≥ 0",
        "nulos": "en gold, las 2 primeras semanas de cada distrito; esas filas no entran a la tabla de orígenes",
        "por_que": "persistencia: el mejor predictor simple del encargo de arquitectura (base_6)",
        "evidencia": "base_6, referencia B (fase 0)",
        "test_no_fuga": "tests/features/test_history_calendar.py · test_cambios_despues_del_origen_no_alteran_ningun_horizonte"},
    "hist_lag_b": {
        "fuente": "epidemiológica", "definicion": "casos de dengue de la semana o − 1",
        "ventana": "semana o − 1", "transformacion": "ninguna (conteo)", "tipo": "entero ≥ 0",
        "nulos": "en gold, las 3 primeras semanas de cada distrito; no entran a la tabla de orígenes", "por_que": "tendencia inmediata junto con hist_lag_a",
        "evidencia": "base_6, referencia B (fase 0)",
        "test_no_fuga": "tests/features/test_history_calendar.py · test_cambios_despues_del_origen_no_alteran_ningun_horizonte"},
    "hist_media_4": {
        "fuente": "epidemiológica", "definicion": "media de casos de las semanas o − 3 a o",
        "ventana": "semanas o − 3..o", "transformacion": "media móvil de 4 semanas", "tipo": "real ≥ 0",
        "nulos": "en gold, las 5 primeras semanas de cada distrito; no entran a la tabla de orígenes",
        "por_que": "nivel reciente menos ruidoso que un rezago",
        "evidencia": "base_6, referencia B (fase 0)",
        "test_no_fuga": "tests/features/test_history_calendar.py · test_cuatro_semanas_solo_utiliza_observaciones_hasta_origen"},
    "hist_semanas_pos_4": {
        "fuente": "epidemiológica", "definicion": "número de semanas con al menos 1 caso entre o − 3 y o",
        "ventana": "semanas o − 3..o", "transformacion": "conteo de semanas positivas (0–4)", "tipo": "entero 0–4",
        "nulos": "en gold, las 5 primeras semanas de cada distrito; no entran a la tabla de orígenes",
        "por_que": "persistencia de la transmisión",
        "evidencia": "base_6, referencia B (fase 0)",
        "test_no_fuga": "tests/features/test_history_calendar.py · test_cuatro_semanas_solo_utiliza_observaciones_hasta_origen"},
    "semana_epi_seno": {
        "fuente": "calendario", "definicion": "sen(2π · ((semana epi de t) − 1) mód 52 / 52)",
        "ventana": "semana objetivo t (conocida de antemano)", "transformacion": "codificación cíclica",
        "tipo": "real −1..1", "nulos": "ninguno", "por_que": "estacionalidad sin inventar un corte de temporada",
        "evidencia": "base_6, referencia B (fase 0)",
        "test_no_fuga": "tests/features/test_history_calendar.py · test_calendario_conocido_y_semana_53"},
    "semana_epi_coseno": {
        "fuente": "calendario", "definicion": "cos(2π · ((semana epi de t) − 1) mód 52 / 52)",
        "ventana": "semana objetivo t (conocida de antemano)", "transformacion": "codificación cíclica",
        "tipo": "real −1..1", "nulos": "ninguno", "por_que": "pareja del seno: ubica la semana en el círculo",
        "evidencia": "base_6, referencia B (fase 0)",
        "test_no_fuga": "tests/features/test_history_calendar.py · test_calendario_conocido_y_semana_53"},
    "propia_semanas_desde_ultimo_caso": {
        "fuente": "epidemiológica (en memoria, features_inicio)",
        "definicion": "semanas transcurridas desde la última semana con casos del distrito, hasta o",
        "ventana": "semanas ≤ o",
        "transformacion": f"tope {di.MAX_WEEKS_WITHOUT_CASE} semanas", "tipo": "entero 0–52",
        "nulos": "ninguno (sin caso previo = tope)",
        "por_que": "cuánto lleva el distrito sin transmisión antes de un inicio",
        "evidencia": "B3: gana a B en h2 y h3 (fase 2b); C3 elegida (fase 2c); 3.ª por SHAP",
        "test_no_fuga": "tests/features/test_onset_features.py · test_no_fuga_por_perturbacion y "
                        "test_no_fuga_por_perturbacion_en_origenes"},
    "propia_pendiente_4": {
        "fuente": "epidemiológica (en memoria, features_inicio)",
        "definicion": "pendiente MCO de log(1 + casos) en las semanas o − 3..o",
        "ventana": "semanas o − 3..o", "transformacion": "log1p y pendiente lineal de 4 puntos", "tipo": "real",
        "nulos": "nulo si faltan semanas de historia; ver el conteo de nulos en la tabla de orígenes",
        "por_que": "dirección del cambio reciente (a priori; no observada en la fase 1)",
        "evidencia": "B3 (fase 2b), C3 (fase 2c)",
        "test_no_fuga": "tests/features/test_onset_features.py · test_no_fuga_por_perturbacion"},
    "propia_log_casos_temporada_anterior": {
        "fuente": "epidemiológica (en memoria; para 2017, histórico epi previo al panel)",
        "definicion": "log(1 + casos de la temporada anterior completa del distrito)",
        "ventana": "temporada anterior, cerrada antes de o",
        "transformacion": "suma de la temporada y log1p", "tipo": "real ≥ 0",
        "nulos": "nulo solo si falta en la historia un año necesario; la fila no se excluye",
        "por_que": "nivel previo del distrito (memoria de una temporada)",
        "evidencia": "B3 (fase 2b), C3 (fase 2c)",
        "test_no_fuga": "tests/features/test_onset_features.py · test_temporada_2017_usa_la_historia y "
                        "test_no_fuga_por_perturbacion"},
    "hum_rel_media_media5_h2": {
        "fuente": "meteorológica (Open-Meteo, archive API; diario agregado a semana MMWR; silver integrado)",
        "definicion": "media de la humedad relativa media semanal (%) de las semanas o − 4 a o",
        "ventana": "semanas o − 4..o (5 semanas observadas hasta el origen)",
        "transformacion": "media móvil de 5 semanas, sin climatología ni anomalía", "tipo": "real 0–100 (%)",
        "nulos": "en gold, las 6 primeras semanas de cada distrito; en la tabla de orígenes, la primera semana de "
                 "2017 (65 filas), que la configuración excluye",
        "por_que": "clima reciente; bajó las razones MAE y RMSE del conteo",
        "evidencia": "A3 (fase 2a, lectura de conteo); complemento de clima: F+A3 mejora el conteo en h2, h3 y h4",
        "test_no_fuga": "tests/features/test_climate.py · test_ventana_h4_y_h2_acaba_en_origen y "
                        "test_cambio_posterior_al_origen_no_altera_feature"},
    "precip_total_mm_media5_h2": {
        "fuente": "meteorológica (Open-Meteo, archive API; diario agregado a semana MMWR; silver integrado)",
        "definicion": "media de la precipitación total semanal (mm) de las semanas o − 4 a o",
        "ventana": "semanas o − 4..o (5 semanas observadas hasta el origen)",
        "transformacion": "media móvil de 5 semanas, sin climatología ni anomalía", "tipo": "real ≥ 0 (mm por semana)",
        "nulos": "en gold, las 6 primeras semanas de cada distrito; en la tabla de orígenes, la primera semana de "
                 "2017 (65 filas), que la configuración excluye",
        "por_que": "clima reciente; bajó las razones MAE y RMSE del conteo",
        "evidencia": "A3 (fase 2a, lectura de conteo); complemento de clima: F+A3 mejora el conteo en h2, h3 y h4",
        "test_no_fuga": "tests/features/test_climate.py · test_ventana_h4_y_h2_acaba_en_origen y "
                        "test_cambio_posterior_al_origen_no_altera_feature"},
}

_D3_COMMON = {
    "fuente": "meteorológica: ERA5-Land (0,1°) de Open-Meteo, archive API con models=era5_land, temperature_2m_mean "
              "diaria (zona America/Lima) en el centroide del distrito, agregada a semana MMWR (domingo a sábado); "
              "silver meteo_humedad_era5_land_2000_2026.csv (estudio 06)",
    "transformacion": "media de las temperaturas medias semanales de la ventana, sin climatología ni anomalía",
    "tipo": "real (°C)",
    "nulos": "nulo si falta alguna semana de la ventana; ningún origen de 2005 en adelante queda nulo (guarda G42 "
             "del estudio 06), así que no se excluye ninguna fila",
    "por_que": "clima reciente y rezagado: la temperatura modula la transmisión del vector (hipótesis del estudio)",
    "evidencia": "d3 de la matriz de clima del estudio 06; base de la V3 por decisión de Rosa con contexto",
    "test_no_fuga": "research/06_model_improvement/tests/test_phase_d_weather_windows.py (ventanas hasta el origen)",
}
DEFINITIONS.update({
    "temp_media_s0": {**_D3_COMMON, "definicion": "temperatura media de la semana de origen o", "ventana": "semana o"},
    "temp_media_media_s1_4": {**_D3_COMMON, "definicion": "media de la temperatura media semanal de o − 4 a o − 1",
                              "ventana": "semanas o − 4..o − 1"},
    "temp_media_media_s5_8": {**_D3_COMMON, "definicion": "media de la temperatura media semanal de o − 8 a o − 5",
                              "ventana": "semanas o − 8..o − 5"},
    "temp_media_media_s9_12": {**_D3_COMMON, "definicion": "media de la temperatura media semanal de o − 12 a o − 9",
                               "ventana": "semanas o − 12..o − 9"},
})
UNITS = {"hist_lag_a": "casos", "hist_lag_b": "casos", "hist_media_4": "casos por semana",
         "hist_semanas_pos_4": "semanas (0–4)", "semana_epi_seno": "adimensional (−1 a 1)",
         "semana_epi_coseno": "adimensional (−1 a 1)", "propia_semanas_desde_ultimo_caso": "semanas (0–52)",
         "propia_pendiente_4": "log(1 + casos) por semana", "propia_log_casos_temporada_anterior": "log(1 + casos)",
         "hum_rel_media_media5_h2": "%", "precip_total_mm_media5_h2": "mm por semana",
         "temp_media_s0": "°C", "temp_media_media_s1_4": "°C", "temp_media_media_s5_8": "°C",
         "temp_media_media_s9_12": "°C"}


def compact_markdown(columns: list[str]) -> str:
    """One-table dictionary (column, definition, units, window, transformation, missing values) of ``columns``."""
    table = dictionary(columns)
    lines = ["| Columna | Definición | Unidades | Ventana | Transformación | Faltantes |", "|---|---|---|---|---|---|"]
    for _, f in table.iterrows():
        lines.append(f"| `{f.variable}` | {f.definicion} | {UNITS[f.variable]} | {f.ventana} | {f.transformacion} "
                     f"| {f.nulos} |")
    return "\n".join(lines)

INFERENCE_INPUT = {
    "nombre": "margen_persistencia (no es columna del modelo)",
    "definicion": "log(casos de la semana de origen + 0,5); base_margin de las tres salidas en S4_s3",
    "uso": "obligatorio en entrenamiento e inferencia: sin los casos del origen no se puede predecir",
    "test_no_fuga": "tests/model/test_probabilistic_output.py · test_s4_y_s3_sin_fuga_por_perturbacion_del_futuro",
}
INPUT_LABELS = {"nombre": "Nombre", "definicion": "Definición", "uso": "Uso", "test_no_fuga": "Test de no fuga"}


def gold_h2_columns() -> dict[str, str]:
    """Generic name -> gold h=2 column (base_6 only)."""
    reg, _ = eh.model_columns(2)
    return dict(zip(eh.GENERIC, reg))


def statistics(origins: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Minimum, median, maximum and nulls per variable and origin season."""
    length = origins[["temporada", *columns]].melt(id_vars="temporada", var_name="variable")
    g = length.groupby(["variable", "temporada"]).value
    return (g.agg(minimo="min", mediana="median", maximo="max").join(g.apply(lambda s: int(s.isna().sum())).rename("nulos"))
            .reset_index())


def dictionary(columns: list[str], origins: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per variable with definition, window, nulls, evidence and observed global range."""
    missing = [c for c in columns if c not in DEFINITIONS]
    if missing:
        raise ValueError(f"Variables sin definición en el diccionario: {missing}")
    gold = gold_h2_columns()
    rows = []
    for c in columns:
        row = {"variable": c, "etiqueta": di.LABELS.get(c, DEFINITIONS[c]["definicion"]),
                "columna_gold_h2": gold.get(c, "no está en gold (propuesta)"),
                **DEFINITIONS[c]}
        if origins is not None:
            v = origins[c]
            row.update({"minimo": float(v.min()), "mediana": float(v.median()), "maximo": float(v.max()),
                         "nulos_observados": int(v.isna().sum()), "filas": int(len(v)),
                         "periodo": f"{pd.to_datetime(origins.origen_cierre).min():%Y-%m-%d} a "
                                    f"{pd.to_datetime(origins.origen_cierre).max():%Y-%m-%d}"})
        rows.append(row)
    return pd.DataFrame(rows)


def _n(x: float) -> str:
    """Short number with a decimal comma; floating point residues show as 0."""
    return f"{round(float(x), 6) + 0.0:.4g}".replace(".", ",")


def to_markdown(table: pd.DataFrame, by_season: pd.DataFrame | None, configuration: dict) -> str:
    """Dictionary document (regenerated; do not edit by hand)."""
    lines = ["# Diccionario de variables de la configuración final (HU0006-3)", "",
              "> Generado por `python -m denguekay.model.variable_dictionary`; no editar a mano.", "",
              f"Configuración: {configuration['matriz']} · {configuration['estrategia']} · "
              f"{configuration['formulacion']} · α {configuration['dispersion']}. El origen es `o = t − 2` "
              "(fila h=2); las tres salidas (t+2, t+3, t+4) usan las mismas variables.", ""]
    for _, f in table.iterrows():
        lines += [f"## `{f.variable}`", "", f"- **Etiqueta:** {f.etiqueta}",
                   f"- **Columna en gold h=2:** `{f.columna_gold_h2}`", f"- **Fuente:** {f.fuente}",
                   f"- **Definición:** {f.definicion}", f"- **Ventana:** {f.ventana}",
                   f"- **Transformación:** {f.transformacion}", f"- **Tipo:** {f.tipo}", f"- **Nulos:** {f.nulos}",
                   f"- **Por qué está:** {f.por_que}", f"- **Evidencia:** {f.evidencia}",
                   f"- **Test de no fuga:** {f.test_no_fuga}"]
        if "minimo" in table:
            lines.append(f"- **Rango observado (orígenes {f.periodo}, {f.filas} filas):** {_n(f.minimo)} a "
                          f"{_n(f.maximo)}, mediana {_n(f.mediana)}; {int(f.nulos_observados)} nulos")
        lines.append("")
    lines += ["## Insumo de inferencia: margen de persistencia", "",
               *(f"- **{INPUT_LABELS[k]}:** {v}" for k, v in INFERENCE_INPUT.items()), ""]
    if by_season is not None:
        lines += ["## Rango por temporada del origen", "", "| Variable | Temporada | Mínimo | Mediana | Máximo | Nulos |",
                   "|---|---|---|---|---|---|"]
        for _, f in by_season.iterrows():
            lines.append(f"| `{f.variable}` | {int(f.temporada)} | {_n(f.minimo)} | {_n(f.mediana)} | {_n(f.maximo)} "
                          f"| {int(f.nulos)} |")
        lines.append("")
    return "\n".join(lines)


# --- V4 (current configuration: b3_obs with confirmed cases) -------------------------------------------------

V4_FIELDS = ("descripcion", "fuente", "unidad", "ventana", "regla", "rezago")
V4_FIELD_LABELS = {"descripcion": "Descripción", "fuente": "Fuente", "unidad": "Unidad", "ventana": "Ventana temporal",
                   "regla": "Regla de cálculo", "rezago": "Rezago respecto del origen"}

_V4_CASES = ("epidemiológica: casos confirmados de dengue de Piura (CSV epidemiológico confirmado hasta 2024 y "
             "Sala Situacional del MINSA desde 2025), con la historia desde 2000 para completar las ventanas")
_V4_ERA5 = ("meteorológica: ERA5-Land (0,1°) vía la API de archivo de Open-Meteo, valor diario en el punto del "
            "distrito, agregado a semana epidemiológica (domingo a sábado)")
_V4_LAG_5 = ("la ventana termina 2 semanas antes del origen (o − 2): la última semana climática que ya está publicada "
             "al cierre del origen; no es el rezago de un horizonte")


def _v4_climate(variable, source, unit, availability):
    return {
        "fuente": source, "unidad": unit,
        "ventana": "5 semanas epidemiológicas: o − 6, o − 5, o − 4, o − 3 y o − 2",
        "regla": (f"media aritmética de {variable} semanal de las 5 semanas; solo cuenta una semana si su fecha de "
                  f"disponibilidad es anterior o igual al cierre del origen ({availability}); si falta alguna de las "
                  "5, el valor es nulo y el distrito no se pronostica, con el motivo registrado"),
        "rezago": _V4_LAG_5,
    }


V4_DEFINITIONS = {
    "hist_lag_a": {
        "descripcion": "Casos confirmados del distrito en la semana de origen.", "fuente": _V4_CASES,
        "unidad": "casos por semana", "ventana": "semana o",
        "regla": "valor de casos_Dengue de la semana o, sin transformación",
        "rezago": "0 semanas respecto del origen; para el objetivo t = o + h equivale a t − h"},
    "hist_lag_b": {
        "descripcion": "Casos confirmados del distrito en la semana anterior al origen.", "fuente": _V4_CASES,
        "unidad": "casos por semana", "ventana": "semana o − 1",
        "regla": "valor de casos_Dengue de la semana o − 1, sin transformación",
        "rezago": "1 semana respecto del origen; para el objetivo t = o + h equivale a t − h − 1"},
    "hist_media_4": {
        "descripcion": "Nivel reciente de casos: media de las últimas 4 semanas hasta el origen.", "fuente": _V4_CASES,
        "unidad": "casos por semana", "ventana": "4 semanas: o − 3, o − 2, o − 1 y o",
        "regla": "media aritmética de casos_Dengue en la ventana; se exigen las 4 semanas (sin completar con ceros)",
        "rezago": "la ventana termina en el origen (rezago 0); equivale a las 4 semanas que terminan en t − h"},
    "hist_semanas_pos_4": {
        "descripcion": "Persistencia de la transmisión: semanas con casos entre las últimas 4 hasta el origen.",
        "fuente": _V4_CASES, "unidad": "semanas (0 a 4)", "ventana": "4 semanas: o − 3, o − 2, o − 1 y o",
        "regla": "número de semanas de la ventana con casos_Dengue mayor que 0; se exigen las 4 semanas",
        "rezago": "la ventana termina en el origen (rezago 0); equivale a las 4 semanas que terminan en t − h"},
    "semana_epi_seno": {
        "descripcion": "Posición estacional de la semana objetivo del horizonte 2, parte seno.",
        "fuente": "calendario epidemiológico MMWR (no usa observaciones)", "unidad": "adimensional (−1 a 1)",
        "ventana": "semana o + 2 (la semana objetivo de la fila del horizonte 2; el vector del origen es el mismo "
                   "para h = 2, 3 y 4)",
        "regla": "sen(2π · ((semana epidemiológica de o + 2) − 1) mód 52 / 52); la semana 53 ocupa la misma posición "
                 "que la semana 1",
        "rezago": "ninguno: el calendario de la semana objetivo se conoce de antemano"},
    "semana_epi_coseno": {
        "descripcion": "Posición estacional de la semana objetivo del horizonte 2, parte coseno.",
        "fuente": "calendario epidemiológico MMWR (no usa observaciones)", "unidad": "adimensional (−1 a 1)",
        "ventana": "semana o + 2 (la semana objetivo de la fila del horizonte 2; el vector del origen es el mismo "
                   "para h = 2, 3 y 4)",
        "regla": "cos(2π · ((semana epidemiológica de o + 2) − 1) mód 52 / 52); la semana 53 ocupa la misma posición "
                 "que la semana 1",
        "rezago": "ninguno: el calendario de la semana objetivo se conoce de antemano"},
    "propia_semanas_desde_ultimo_caso": {
        "descripcion": "Cuánto lleva el distrito sin transmisión: semanas desde la última semana con casos.",
        "fuente": _V4_CASES + "; calculada en memoria",
        "unidad": "semanas (0 a 52)", "ventana": "todas las semanas hasta o, incluida o",
        "regla": f"o menos la posición de la última semana con casos_Dengue mayor que 0 (0 si o tiene casos); "
                 f"tope de {di.MAX_WEEKS_WITHOUT_CASE} semanas, que también se usa si el distrito no tiene caso previo",
        "rezago": "usa solo semanas hasta el origen (rezago 0); no ve nada posterior a o"},
    "propia_pendiente_4": {
        "descripcion": "Dirección del cambio reciente de los casos: pendiente de log(1 + casos) en 4 semanas.",
        "fuente": _V4_CASES + "; calculada en memoria",
        "unidad": "log(1 + casos) por semana", "ventana": "4 semanas: o − 3, o − 2, o − 1 y o",
        "regla": "pendiente de mínimos cuadrados de log(1 + casos_Dengue) contra el tiempo (4 puntos equiespaciados); "
                 "nula si falta alguna de las 4 semanas",
        "rezago": "la ventana termina en el origen (rezago 0)"},
    "propia_log_casos_temporada_anterior": {
        "descripcion": "Nivel previo del distrito: casos de la temporada anterior completa.",
        "fuente": _V4_CASES + "; calculada en memoria",
        "unidad": "log(1 + casos de la temporada)",
        "ventana": "temporada anterior a la del origen, cerrada antes de o (la temporada empieza en la semana 35)",
        "regla": "log(1 + suma de casos_Dengue de la temporada anterior del distrito); nula solo si falta de la "
                 "historia un año necesario",
        "rezago": "temporada completa y cerrada antes del origen; no usa semanas posteriores a o"},
    "lat": {
        "descripcion": "Latitud del punto del distrito.",
        "fuente": "geográfica: coordenadas del punto del distrito de las consultas climáticas "
                  "(data/reference/distritos_piura_coords.csv), en el archivo geografia_distritos.csv del paquete",
        "unidad": "grados decimales", "ventana": "estática (no varía en el tiempo)",
        "regla": "se toma tal cual del archivo de geografía congelado (65 distritos); su SHA-256 está en la ficha de la V4",
        "rezago": "no aplica: constante del distrito"},
    "lon": {
        "descripcion": "Longitud del punto del distrito.",
        "fuente": "geográfica: coordenadas del punto del distrito de las consultas climáticas "
                  "(data/reference/distritos_piura_coords.csv), en el archivo geografia_distritos.csv del paquete",
        "unidad": "grados decimales", "ventana": "estática (no varía en el tiempo)",
        "regla": "se toma tal cual del archivo de geografía congelado (65 distritos); su SHA-256 está en la ficha de la V4",
        "rezago": "no aplica: constante del distrito"},
    "elevacion_dem90": {
        "descripcion": "Elevación del punto del distrito.",
        "fuente": "geográfica: modelo digital de elevación GLO-90 (90 m) consultado con la API de elevación de "
                  "Open-Meteo en el punto del distrito",
        "unidad": "metros sobre el nivel del mar", "ventana": "estática (no varía en el tiempo)",
        "regla": "se toma tal cual del archivo de geografía congelado (65 distritos); su SHA-256 está en la ficha de la V4",
        "rezago": "no aplica: constante del distrito"},
    "hum_rel_media_media5_h2_obs": {
        "descripcion": "Humedad relativa reciente: media de 5 semanas que terminan 2 semanas antes del origen.",
        **_v4_climate("hum_rel_media", _V4_ERA5 + "; variable relative_humidity_2m_mean", "% (0 a 100)",
                      "ERA5-Land: fecha_era5_land_disponible de la BD, o el domingo de la semana más 13 días en "
                      "el silver sin esa fecha")},
    "precip_total_mm_media5_h2_obs": {
        "descripcion": "Lluvia reciente: media de 5 semanas que terminan 2 semanas antes del origen.",
        **_v4_climate("precip_total_mm", "precipitación: CHIRPS v3 (final y preliminar) agregada por distrito, "
                      "diaria, a semana epidemiológica (domingo a sábado)", "mm por semana",
                      "CHIRPS: fecha_chirps_disponible, el cierre del pentad que contiene el sábado más 5 días")},
    "temp_media_media5_h2_obs": {
        "descripcion": "Temperatura reciente: media de 5 semanas que terminan 2 semanas antes del origen.",
        **_v4_climate("temp_media", _V4_ERA5 + "; variable temperature_2m_mean", "°C",
                      "ERA5-Land: fecha_era5_land_disponible de la BD, o el domingo de la semana más 13 días en "
                      "el silver sin esa fecha")},
    "nino12_anom_media3_obs": {
        "descripcion": "Anomalía reciente del océano frente a Piura: media de los 3 últimos meses publicados del "
                       "Niño 1+2.",
        "fuente": "oceánica: anomalía mensual Niño 1+2 del índice OISST v2.1 de NOAA CPC (sstoi.indices); un solo "
                  "valor para todos los distritos",
        "unidad": "°C (anomalía)", "ventana": "los 3 últimos meses consecutivos publicados al cierre del origen",
        "regla": "media aritmética de la anomalía mensual de esos 3 meses; un mes está publicado desde el día 10 del "
                 "mes siguiente; si no hay 3 meses consecutivos, el valor es nulo",
        "rezago": "entre 1 y 3 meses de retraso por la publicación del índice; usa solo meses ya publicados al "
                  "cierre del origen"},
}

V4_NO_LEAK_TESTS = {
    "historia y calendario": "tests/features/test_history_calendar.py",
    "historia propia": "tests/features/test_onset_features.py",
    "clima, Niño 1+2 y disponibilidad": "tests/features/test_gold_v4.py · "
                                         "test_uses_only_the_five_eligible_weeks_and_three_published_months",
}
V4_GROUPS = (
    ("historia y calendario", ("hist_lag_a", "hist_lag_b", "hist_media_4", "hist_semanas_pos_4", "semana_epi_seno",
                               "semana_epi_coseno")),
    ("historia propia", ("propia_semanas_desde_ultimo_caso", "propia_pendiente_4",
                         "propia_log_casos_temporada_anterior")),
    ("geografía", ("lat", "lon", "elevacion_dem90")),
    ("clima, Niño 1+2 y disponibilidad", ("hum_rel_media_media5_h2_obs", "precip_total_mm_media5_h2_obs",
                                           "temp_media_media5_h2_obs", "nino12_anom_media3_obs")),
)


def v4_spec() -> dict:
    """Specification of the frozen V4 (versioned in ``research/08``): columns, cutoff, horizons and rule."""
    from denguekay.config.paths import V4_STUDY_MANIFEST

    return json.loads(V4_STUDY_MANIFEST.read_text(encoding="utf-8"))


def v4_columns() -> list[str]:
    """The 16 columns of the V4 (b3_obs), in the order of the frozen package and of ``features/gold_v4.py``."""
    return list(v4_spec()["columnas"]["b3_obs"])


def v4_dictionary(columns: list[str] | None = None) -> pd.DataFrame:
    """One row per V4 column with name, description, source, unit, window, rule and lag.

    It fails if a column has no entry, if an entry misses a field or is empty, or if the dictionary has an entry
    that is not a column of the V4 (so a column cannot be added or removed without updating the dictionary)."""
    columns = v4_columns() if columns is None else list(columns)
    missing = [c for c in columns if c not in V4_DEFINITIONS]
    if missing:
        raise ValueError(f"Columnas de la V4 sin entrada en el diccionario: {missing}")
    extra = sorted(set(V4_DEFINITIONS) - set(columns))
    if extra:
        raise ValueError(f"Entradas del diccionario que no son columnas de la V4: {extra}")
    incomplete = [f"{c}.{f}" for c in columns for f in V4_FIELDS
                  if not (isinstance(V4_DEFINITIONS[c].get(f), str) and V4_DEFINITIONS[c][f].strip())]
    if incomplete:
        raise ValueError(f"Entradas incompletas del diccionario de la V4: {incomplete}")
    return pd.DataFrame([{"variable": c, **{f: V4_DEFINITIONS[c][f] for f in V4_FIELDS}} for c in columns])


def v4_markdown(spec: dict | None = None, columns: list[str] | None = None) -> str:
    """V4 section of the dictionary document (main section)."""
    spec = v4_spec() if spec is None else spec
    table = v4_dictionary(columns)
    group_of = {c: name for name, members in V4_GROUPS for c in members}
    lines = ["## V4 vigente (b3_obs, casos confirmados)", "",
             f"Configuración: matriz `b3_obs` ({len(table)} columnas) · formulación {spec['formulacion']} · "
             f"horizontes {', '.join(map(str, spec['horizontes']))} semanas · etiquetas hasta el {spec['corte']}. "
             "Es el modelo que sirve el predictor `v4_b3_live` (ficha en `models/registry/v4/`).", "",
             "**Convención de tiempo.** El origen `o` es la semana de corte: la semana epidemiológica (domingo a "
             "sábado) cuyo cierre es la fecha de corte de los datos. La semana objetivo es `t = o + h` con "
             "h = 2, 3 o 4. El modelo calcula **un solo vector de 16 columnas en `o`** y lo usa para los tres "
             "horizontes, así que ninguna variable mira después de `o`: «rezago respecto de `t − h`» significa que "
             "la semana `o` es la última que se observa para el objetivo `t = o + h`. Las variables de clima y "
             "Niño 1+2 respetan además la fecha de publicación de su fuente.", "",
             "Las columnas salen de `research/08_v3_confirmed_cases/manifiesto_b3_v4.json`, igual que en el paquete "
             "congelado y en `features/gold_v4.py`; una prueba falla si una columna no tiene entrada completa "
             "(`tests/model/test_variable_dictionary_v4.py`).", ""]
    lines += ["| # | Variable | Grupo | Unidad | Ventana temporal |", "|---|---|---|---|---|"]
    for i, row in enumerate(table.itertuples(), 1):
        lines.append(f"| {i} | `{row.variable}` | {group_of[row.variable]} | {row.unidad} | {row.ventana} |")
    lines.append("")
    for row in table.itertuples():
        lines += [f"### `{row.variable}`", ""]
        lines += [f"- **{V4_FIELD_LABELS[f]}:** {getattr(row, f)}" for f in V4_FIELDS]
        lines.append("")
    lines += ["### Pruebas de no fuga", ""]
    lines += [f"- {group}: `{test}`" for group, test in V4_NO_LEAK_TESTS.items()]
    lines.append("")
    return "\n".join(lines)


def v4_document() -> str:
    """Whole document: V4 first, then the v2 as history (compact table, generated from the v2 definitions)."""
    from denguekay.model import frozen_configs as cf

    lines = ["# Diccionario de variables", "",
             "> Generado por `python -m denguekay.model.variable_dictionary`; no editar a mano.", "",
             "La configuración vigente es la **V4**. La v2 queda como histórico al final; su diccionario completo, "
             "con rangos por temporada, está en [`diccionario_variables_v2.md`](diccionario_variables_v2.md).", "",
             v4_markdown(), "## Histórico: v2 (HU0006-3, congelada antes de la V3)", "",
             "Tabla resumida de las 11 columnas de la configuración v2 (`CONFIG_2026`), que ya no se sirve.", "",
             compact_markdown(cf.CONFIG_2026["columnas"]), ""]
    return "\n".join(lines)


def main_v2() -> None:
    """Regenerate the full v2 document (history). It needs the v2 integrated panel, so it runs from the v2 tag."""
    from denguekay.data.loading import load_integrated
    from denguekay.model import frozen_configs as cf
    from denguekay.evaluation import episodes as d
    from denguekay.evaluation import variants as fh
    from denguekay.config.paths import VARIABLE_DICTIONARY, GOLD_MANIFEST, FE_HYPERPARAMETERS_METRICS, SILVER_INTEGRATED

    panel = load_integrated(SILVER_INTEGRATED)
    rule = json.loads(GOLD_MANIFEST.read_text(encoding="utf-8"))["regla_brote"]
    ins = fh.inputs(panel, rule)
    origins = cf.origins(panel, ins, rule)
    columns = cf.CONFIG_2026["columnas"]
    table = dictionary(columns, origins)
    by_season = statistics(origins, columns)
    text = to_markdown(table, by_season, cf.CONFIG_2026)
    VARIABLE_DICTIONARY.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
    d.save_metrics_section(FE_HYPERPARAMETERS_METRICS, "fase5_diccionario_variables",
                               {"variables": d.to_json(table), "por_temporada": d.to_json(by_season),
                                "insumo_inferencia": INFERENCE_INPUT})
    print(f"{VARIABLE_DICTIONARY} ({len(table)} variables)")


def main() -> None:
    from denguekay.config.paths import VARIABLE_DICTIONARY

    text = v4_document()
    VARIABLE_DICTIONARY.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
    print(f"{VARIABLE_DICTIONARY} ({len(v4_columns())} variables de la V4)")


if __name__ == "__main__":
    main()
