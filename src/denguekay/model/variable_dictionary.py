"""Dictionary of the variables of the final configuration (HU0006-3).

It is generated from the code: the columns come from ``frozen_configs``, the gold
names from ``horizon_strategies.model_columns(2)``, the labels from
``diagnostico_inicios.ETIQUETAS`` and the ranges are computed in memory on the
origin table. Nothing is written to ``data/``.

Usage (from the repository root)::

    python -m denguekay.model.variable_dictionary
"""

import json

import pandas as pd

from src.modeling import diagnostico_inicios as di
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
        "transformacion": f"tope {di.TOPE_SEMANAS_SIN_CASO} semanas", "tipo": "entero 0–52",
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
        row = {"variable": c, "etiqueta": di.ETIQUETAS.get(c, DEFINITIONS[c]["definicion"]),
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


def main() -> None:
    from denguekay.data.loading import load_integrated
    from denguekay.model import frozen_configs as cf
    from src.modeling import diagnostico_arquitectura as d
    from src.modeling import fe_hiperparametros as fh
    from denguekay.config.paths import VARIABLE_DICTIONARY, GOLD_MANIFEST, FE_HYPERPARAMETERS_METRICS, SILVER_INTEGRATED

    panel = load_integrated(SILVER_INTEGRATED)
    rule = json.loads(GOLD_MANIFEST.read_text(encoding="utf-8"))["regla_brote"]
    ins = fh.insumos(panel, rule)
    origins = cf.origins(panel, ins, rule)
    columns = cf.CONFIG_2026["columnas"]
    table = dictionary(columns, origins)
    by_season = statistics(origins, columns)
    text = to_markdown(table, by_season, cf.CONFIG_2026)
    VARIABLE_DICTIONARY.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
    d.guardar_seccion_metricas(FE_HYPERPARAMETERS_METRICS, "fase5_diccionario_variables",
                               {"variables": d.a_json(table), "por_temporada": d.a_json(by_season),
                                "insumo_inferencia": INFERENCE_INPUT})
    print(f"{VARIABLE_DICTIONARY} ({len(table)} variables)")


if __name__ == "__main__":
    main()
