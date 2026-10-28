"""Diccionario de las variables de la configuración final (HU0006-3).

Se genera desde el código: las columnas salen de ``configuracion_final``, los
nombres de gold de ``estrategias_horizonte.columnas_modelo(2)``, las etiquetas
de ``diagnostico_inicios.ETIQUETAS`` y los rangos se calculan en memoria sobre
la tabla de orígenes. Nada se escribe en ``data/``.

Uso (desde la raíz del repo)::

    python -m src.modeling.diccionario_variables
"""

import json

import pandas as pd

from src.modeling import diagnostico_inicios as di
from src.modeling import estrategias_horizonte as eh

# Texto por variable genérica. "ventana" es relativa al origen o = t − 2 de la fila h=2.
DEFINICIONES = {
    "hist_lag_a": {
        "fuente": "epidemiológica (casos de dengue, silver integrado)",
        "definicion": "casos de dengue de la semana de origen o",
        "ventana": "semana o", "transformacion": "ninguna (conteo)", "tipo": "entero ≥ 0",
        "nulos": "en gold, las 2 primeras semanas de cada distrito; esas filas no entran a la tabla de orígenes",
        "por_que": "persistencia: el mejor predictor simple del encargo de arquitectura (base_6)",
        "evidencia": "base_6, referencia B (fase 0)",
        "test_no_fuga": "tests/test_historia_calendario.py · test_cambios_despues_del_origen_no_alteran_ningun_horizonte"},
    "hist_lag_b": {
        "fuente": "epidemiológica", "definicion": "casos de dengue de la semana o − 1",
        "ventana": "semana o − 1", "transformacion": "ninguna (conteo)", "tipo": "entero ≥ 0",
        "nulos": "en gold, las 3 primeras semanas de cada distrito; no entran a la tabla de orígenes", "por_que": "tendencia inmediata junto con hist_lag_a",
        "evidencia": "base_6, referencia B (fase 0)",
        "test_no_fuga": "tests/test_historia_calendario.py · test_cambios_despues_del_origen_no_alteran_ningun_horizonte"},
    "hist_media_4": {
        "fuente": "epidemiológica", "definicion": "media de casos de las semanas o − 3 a o",
        "ventana": "semanas o − 3..o", "transformacion": "media móvil de 4 semanas", "tipo": "real ≥ 0",
        "nulos": "en gold, las 5 primeras semanas de cada distrito; no entran a la tabla de orígenes",
        "por_que": "nivel reciente menos ruidoso que un rezago",
        "evidencia": "base_6, referencia B (fase 0)",
        "test_no_fuga": "tests/test_historia_calendario.py · test_cuatro_semanas_solo_utiliza_observaciones_hasta_origen"},
    "hist_semanas_pos_4": {
        "fuente": "epidemiológica", "definicion": "número de semanas con al menos 1 caso entre o − 3 y o",
        "ventana": "semanas o − 3..o", "transformacion": "conteo de semanas positivas (0–4)", "tipo": "entero 0–4",
        "nulos": "en gold, las 5 primeras semanas de cada distrito; no entran a la tabla de orígenes",
        "por_que": "persistencia de la transmisión",
        "evidencia": "base_6, referencia B (fase 0)",
        "test_no_fuga": "tests/test_historia_calendario.py · test_cuatro_semanas_solo_utiliza_observaciones_hasta_origen"},
    "semana_epi_seno": {
        "fuente": "calendario", "definicion": "sen(2π · ((semana epi de t) − 1) mód 52 / 52)",
        "ventana": "semana objetivo t (conocida de antemano)", "transformacion": "codificación cíclica",
        "tipo": "real −1..1", "nulos": "ninguno", "por_que": "estacionalidad sin inventar un corte de temporada",
        "evidencia": "base_6, referencia B (fase 0)",
        "test_no_fuga": "tests/test_historia_calendario.py · test_calendario_conocido_y_semana_53"},
    "semana_epi_coseno": {
        "fuente": "calendario", "definicion": "cos(2π · ((semana epi de t) − 1) mód 52 / 52)",
        "ventana": "semana objetivo t (conocida de antemano)", "transformacion": "codificación cíclica",
        "tipo": "real −1..1", "nulos": "ninguno", "por_que": "pareja del seno: ubica la semana en el círculo",
        "evidencia": "base_6, referencia B (fase 0)",
        "test_no_fuga": "tests/test_historia_calendario.py · test_calendario_conocido_y_semana_53"},
    "propia_semanas_desde_ultimo_caso": {
        "fuente": "epidemiológica (en memoria, features_inicio)",
        "definicion": "semanas transcurridas desde la última semana con casos del distrito, hasta o",
        "ventana": "semanas ≤ o",
        "transformacion": f"tope {di.TOPE_SEMANAS_SIN_CASO} semanas", "tipo": "entero 0–52",
        "nulos": "ninguno (sin caso previo = tope)",
        "por_que": "cuánto lleva el distrito sin transmisión antes de un inicio",
        "evidencia": "B3: gana a B en h2 y h3 (fase 2b); C3 elegida (fase 2c); 3.ª por SHAP",
        "test_no_fuga": "tests/test_features_inicio.py · test_no_fuga_por_perturbacion y "
                        "test_no_fuga_por_perturbacion_en_origenes"},
    "propia_pendiente_4": {
        "fuente": "epidemiológica (en memoria, features_inicio)",
        "definicion": "pendiente MCO de log(1 + casos) en las semanas o − 3..o",
        "ventana": "semanas o − 3..o", "transformacion": "log1p y pendiente lineal de 4 puntos", "tipo": "real",
        "nulos": "nulo si faltan semanas de historia; ver el conteo de nulos en la tabla de orígenes",
        "por_que": "dirección del cambio reciente (a priori; no observada en la fase 1)",
        "evidencia": "B3 (fase 2b), C3 (fase 2c)",
        "test_no_fuga": "tests/test_features_inicio.py · test_no_fuga_por_perturbacion"},
    "propia_log_casos_temporada_anterior": {
        "fuente": "epidemiológica (en memoria; para 2017, histórico epi previo al panel)",
        "definicion": "log(1 + casos de la temporada anterior completa del distrito)",
        "ventana": "temporada anterior, cerrada antes de o",
        "transformacion": "suma de la temporada y log1p", "tipo": "real ≥ 0",
        "nulos": "nulo solo si falta en la historia un año necesario; la fila no se excluye",
        "por_que": "nivel previo del distrito (memoria de una temporada)",
        "evidencia": "B3 (fase 2b), C3 (fase 2c)",
        "test_no_fuga": "tests/test_features_inicio.py · test_temporada_2017_usa_la_historia y "
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
        "test_no_fuga": "tests/test_clima_features.py · test_ventana_h4_y_h2_acaba_en_origen y "
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
        "test_no_fuga": "tests/test_clima_features.py · test_ventana_h4_y_h2_acaba_en_origen y "
                        "test_cambio_posterior_al_origen_no_altera_feature"},
}

INSUMO_INFERENCIA = {
    "nombre": "margen_persistencia (no es columna del modelo)",
    "definicion": "log(casos de la semana de origen + 0,5); base_margin de las tres salidas en S4_s3",
    "uso": "obligatorio en entrenamiento e inferencia: sin los casos del origen no se puede predecir",
    "test_no_fuga": "tests/test_salida_probabilistica.py · test_s4_y_s3_sin_fuga_por_perturbacion_del_futuro",
}
ROTULOS_INSUMO = {"nombre": "Nombre", "definicion": "Definición", "uso": "Uso", "test_no_fuga": "Test de no fuga"}


def columnas_gold_h2() -> dict[str, str]:
    """Nombre genérico → columna de gold h=2 (solo base_6)."""
    reg, _ = eh.columnas_modelo(2)
    return dict(zip(eh.GENERICAS, reg))


def estadisticas(origenes: pd.DataFrame, columnas: list[str]) -> pd.DataFrame:
    """Mínimo, mediana, máximo y nulos por variable y temporada del origen."""
    largo = origenes[["temporada", *columnas]].melt(id_vars="temporada", var_name="variable")
    g = largo.groupby(["variable", "temporada"]).value
    return (g.agg(minimo="min", mediana="median", maximo="max").join(g.apply(lambda s: int(s.isna().sum())).rename("nulos"))
            .reset_index())


def diccionario(columnas: list[str], origenes: pd.DataFrame | None = None) -> pd.DataFrame:
    """Una fila por variable con definición, ventana, nulos, evidencia y rango global observado."""
    faltan = [c for c in columnas if c not in DEFINICIONES]
    if faltan:
        raise ValueError(f"Variables sin definición en el diccionario: {faltan}")
    gold = columnas_gold_h2()
    filas = []
    for c in columnas:
        fila = {"variable": c, "etiqueta": di.ETIQUETAS.get(c, DEFINICIONES[c]["definicion"]),
                "columna_gold_h2": gold.get(c, "no está en gold (propuesta)"),
                **DEFINICIONES[c]}
        if origenes is not None:
            v = origenes[c]
            fila.update({"minimo": float(v.min()), "mediana": float(v.median()), "maximo": float(v.max()),
                         "nulos_observados": int(v.isna().sum()), "filas": int(len(v)),
                         "periodo": f"{pd.to_datetime(origenes.origen_cierre).min():%Y-%m-%d} a "
                                    f"{pd.to_datetime(origenes.origen_cierre).max():%Y-%m-%d}"})
        filas.append(fila)
    return pd.DataFrame(filas)


def _n(x: float) -> str:
    """Número corto con coma decimal; los residuos de punto flotante se muestran como 0."""
    return f"{round(float(x), 6) + 0.0:.4g}".replace(".", ",")


def a_markdown(tabla: pd.DataFrame, por_temporada: pd.DataFrame | None, configuracion: dict) -> str:
    """Documento del diccionario (se regenera; no editar a mano)."""
    lineas = ["# Diccionario de variables de la configuración final (HU0006-3)", "",
              "> Generado por `python -m src.modeling.diccionario_variables`; no editar a mano.", "",
              f"Configuración: {configuracion['matriz']} · {configuracion['estrategia']} · "
              f"{configuracion['formulacion']} · α {configuracion['dispersion']}. El origen es `o = t − 2` "
              "(fila h=2); las tres salidas (t+2, t+3, t+4) usan las mismas variables.", ""]
    for _, f in tabla.iterrows():
        lineas += [f"## `{f.variable}`", "", f"- **Etiqueta:** {f.etiqueta}",
                   f"- **Columna en gold h=2:** `{f.columna_gold_h2}`", f"- **Fuente:** {f.fuente}",
                   f"- **Definición:** {f.definicion}", f"- **Ventana:** {f.ventana}",
                   f"- **Transformación:** {f.transformacion}", f"- **Tipo:** {f.tipo}", f"- **Nulos:** {f.nulos}",
                   f"- **Por qué está:** {f.por_que}", f"- **Evidencia:** {f.evidencia}",
                   f"- **Test de no fuga:** {f.test_no_fuga}"]
        if "minimo" in tabla:
            lineas.append(f"- **Rango observado (orígenes {f.periodo}, {f.filas} filas):** {_n(f.minimo)} a "
                          f"{_n(f.maximo)}, mediana {_n(f.mediana)}; {int(f.nulos_observados)} nulos")
        lineas.append("")
    lineas += ["## Insumo de inferencia: margen de persistencia", "",
               *(f"- **{ROTULOS_INSUMO[k]}:** {v}" for k, v in INSUMO_INFERENCIA.items()), ""]
    if por_temporada is not None:
        lineas += ["## Rango por temporada del origen", "", "| Variable | Temporada | Mínimo | Mediana | Máximo | Nulos |",
                   "|---|---|---|---|---|---|"]
        for _, f in por_temporada.iterrows():
            lineas.append(f"| `{f.variable}` | {int(f.temporada)} | {_n(f.minimo)} | {_n(f.mediana)} | {_n(f.maximo)} "
                          f"| {int(f.nulos)} |")
        lineas.append("")
    return "\n".join(lineas)


def main() -> None:
    from src.eda.carga import cargar_integrado
    from src.modeling import configuracion_final as cf
    from src.modeling import diagnostico_arquitectura as d
    from src.modeling import fe_hiperparametros as fh
    from denguekay.config.paths import DICCIONARIO_VARIABLES, GOLD_MANIFEST, METRICAS_FE_HIPERPARAMETROS, SILVER_INTEGRADO

    panel = cargar_integrado(SILVER_INTEGRADO)
    regla = json.loads(GOLD_MANIFEST.read_text(encoding="utf-8"))["regla_brote"]
    ins = fh.insumos(panel, regla)
    origenes = cf.origenes(panel, ins, regla)
    columnas = cf.CONFIGURACION_2026["columnas"]
    tabla = diccionario(columnas, origenes)
    por_temporada = estadisticas(origenes, columnas)
    texto = a_markdown(tabla, por_temporada, cf.CONFIGURACION_2026)
    DICCIONARIO_VARIABLES.write_bytes(texto.replace("\n", "\r\n").encode("utf-8"))
    d.guardar_seccion_metricas(METRICAS_FE_HIPERPARAMETROS, "fase5_diccionario_variables",
                               {"variables": d.a_json(tabla), "por_temporada": d.a_json(por_temporada),
                                "insumo_inferencia": INSUMO_INFERENCIA})
    print(f"{DICCIONARIO_VARIABLES} ({len(tabla)} variables)")


if __name__ == "__main__":
    main()
