"""Evaluate calibration and stratified probability skill on the common held-out rows."""

import numpy as np
import pandas as pd

from denguekay.evaluation import episodes, protocol
from evaluate_alert_cutoffs import KEY, blocks, read_archive
from evaluate_history_calibration import decompose
from run_contribution import training_data
import run_spatial_controls as spatial


archive = spatial.archive
DESTINATION = archive.OUTPUT / "diagnostico_probabilidades_revision"
MODELS = ("b3_obs", "d3_obs", "historia_geo")
METHODS = (*MODELS, "persistencia_prob", "climatologia")


def annotate(base, labels):
    labelled = episodes.episodes(labels)
    first_two = pd.concat([
        labelled[["ubigeo", "inicio"]].assign(semana_inicio=lambda d: d.inicio + n * episodes.WEEK)
        for n in (0, 1)
    ])
    keys = ["ubigeo", "semana_inicio"]
    base = base.merge(first_two[keys].assign(primera_o_segunda=True),
                      on=keys, how="left", validate="many_to_one")
    base["estado_objetivo"] = np.select(
        [base.brote.eq(0), base.primera_o_segunda.eq(True)],
        ["sin_brote", "inicio_1_2"], default="continuacion")
    prior = []
    for block, group in base.groupby("bloque"):
        cutoff = group.origen_cierre.min()
        rates = (labels.loc[(labels.semana_inicio + pd.Timedelta(days=6)).le(cutoff)]
                 .groupby("ubigeo").brote.mean().rename("prevalencia_previa"))
        if len(rates) != 65:
            raise ValueError(f"Historia insuficiente para definir endemicidad en {block}")
        median = rates.loc[rates.gt(0)].median()
        district = rates.reset_index().assign(bloque=block)
        district["endemicidad"] = np.select(
            [district.prevalencia_previa.eq(0), district.prevalencia_previa.le(median)],
            ["sin_brote_previo", "baja"], default="alta")
        prior.append(district)
    return base.merge(pd.concat(prior, ignore_index=True), on=["ubigeo", "bloque"], validate="many_to_one")


def score(group, seed, block, horizon, family, stratum):
    if group.brote.nunique() != 2:
        return []
    results = {method: decompose(group.brote, group[method]) for method in METHODS}
    rows = []
    for method, stats in results.items():
        rows.append({
            "bloque": block, "horizonte": horizon, "semilla": seed, "familia": family,
            "estrato": stratum, "metodo": method, "filas": len(group), "positivos": int(group.brote.sum()),
            **stats, "bss_persistencia": 1 - stats["brier"] / results["persistencia_prob"]["brier"],
            "bss_climatologia": 1 - stats["brier"] / results["climatologia"]["brier"],
        })
    return rows


def analyze(data, seed):
    results, calibration, components = [], [], []
    for (block, horizon), group in data.groupby(["bloque", "horizonte"]):
        results.extend(score(group, seed, block, horizon, "todas", "todas"))
        for stratum, subset in group.groupby("endemicidad"):
            results.extend(score(subset, seed, block, horizon, "endemicidad_previa", stratum))
        for stratum in ("inicio_1_2", "continuacion"):
            subset = group.loc[group.estado_objetivo.isin(["sin_brote", stratum])]
            results.extend(score(subset, seed, block, horizon, "fase_con_negativos_comunes", stratum))
        for stratum, subset in group.groupby("estado_objetivo"):
            for method in METHODS:
                components.append({
                    "bloque": block, "horizonte": horizon, "semilla": seed, "estrato": stratum,
                    "metodo": method, "filas": len(subset), "positivos": int(subset.brote.sum()),
                    "perdida_cuadratica": float(((subset.brote - subset[method]) ** 2).sum()),
                })
        for method in (*MODELS, "persistencia_prob"):
            p = group[method]
            diagnostic = protocol.fit_platt(p, group.brote)
            high = group.loc[p.ge(0.30)]
            calibration.append({
                "bloque": block, "horizonte": horizon, "semilla": seed, "metodo": method,
                "pendiente": float(diagnostic.coef_[0, 0]), "intercepto": float(diagnostic.intercept_[0]),
                "p_ge_030_filas": len(high), "p_ge_030_observados": int(high.brote.sum()),
                "p_ge_030_esperados": float(high[method].sum()),
            })
    return pd.DataFrame(results), pd.DataFrame(calibration), pd.DataFrame(components)


def main():
    base = pd.read_csv(archive.OUTPUT / "comparadores_revision" / "predicciones_baselines.csv.gz",
                       dtype={"ubigeo": str}, parse_dates=["semana_inicio", "origen_cierre"], float_precision="round_trip")
    in_scope = blocks(spatial.DECIDING)
    base = base.loc[base.bloque.isin(in_scope)].reset_index(drop=True)
    keys = [*KEY, "origen_cierre", "brote"]
    _, _, _, study = training_data()
    data = annotate(base, study["etiquetas"])
    pd.testing.assert_frame_equal(data[keys], base[keys])
    output = []
    for seed in protocol.SEEDS:
        run = data.copy()
        for method in MODELS:
            path = archive.OUTPUT / "ajuste_simetrico" / "evaluacion" / f"{method}_s{seed}" / "predicciones.csv.gz"
            forecast = read_archive(path, "probabilidad_calibrada")
            forecast = forecast.loc[forecast.bloque.isin(in_scope)].reset_index(drop=True)
            pd.testing.assert_frame_equal(forecast[keys], base[keys])
            run[method] = forecast.probabilidad_calibrada
        if not run[list(METHODS)].apply(lambda p: p.between(0, 1)).all().all():
            raise ValueError("Probabilidades fuera de soporte")
        output.append(analyze(run, seed))
    DESTINATION.mkdir(exist_ok=True)
    metrics, cal, components = [pd.concat(x, ignore_index=True) for x in zip(*output, strict=True)]
    metrics.to_csv(DESTINATION / "metricas_estratificadas.csv", index=False)
    cal.to_csv(DESTINATION / "pendientes_interceptos_y_riesgo_alto.csv", index=False)
    components.to_csv(DESTINATION / "contribuciones_brier_por_fase.csv", index=False)
    check = components.groupby(["bloque", "horizonte", "semilla", "metodo"])[["perdida_cuadratica", "filas"]].sum()
    full = metrics.loc[metrics.familia.eq("todas")].set_index(check.index.names)
    np.testing.assert_allclose(check.perdida_cuadratica / check.filas, full.brier.reindex(check.index),
                               atol=1e-12, rtol=0)
    print(f"{len(metrics)} celdas de probabilidad y estratos; contribuciones a Brier verificadas.")


if __name__ == "__main__":
    main()
