"""Describe the fitted b3 temperature response at h4 in season 2023."""

import argparse
from pathlib import Path
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import run_spatial_controls as spatial


def temperature_ale(inputs, origins, columns, hp):
    tests, cutoff = spatial.eh._common_cutoffs(inputs["matrices"], "temporada", 2023)
    margin = spatial.sp.e3_margin(origins, spatial.FORM)
    params = spatial.sp.e3_parameters(hp)
    fit = spatial.sp.fit_e3(origins, cutoff, 17, spatial.FORM, columns, [], params, margin)
    field = f"{spatial.TEMP}_obs"
    edges = np.unique(np.quantile(fit.train[field], np.linspace(0, 1, 11)))
    keys = ["ubigeo", "origen_cierre"]
    positions = origins[[*keys, field]].assign(posicion=np.arange(len(origins)))
    test = tests[4][[*keys, "umbral_brote_casos"]].merge(
        positions, on=keys, how="left", validate="one_to_one"
    )
    if test.posicion.isna().any():
        raise ValueError("Origen ausente para ALE")
    covered = test[field].between(edges[0], edges[-1])
    observed = test.loc[covered].copy()
    bins = np.searchsorted(edges[1:-1], observed[field], side="right")
    count = spatial.sp.FORMULATIONS[spatial.FORM]["conteo"]
    h4 = spatial.archive.HORIZONS.index(4)

    def probability(temperature):
        x = origins.iloc[observed.posicion.to_numpy(int)][columns].assign(**{field: temperature})
        m = margin[observed.posicion.to_numpy(int)]
        mu = spatial.sp.predict_count(fit.regressor, x, count, m)[:, h4]
        return spatial.sp.negative_binomial_probability(mu, fit.alphas[h4], observed.umbral_brote_casos)

    diff = probability(edges[bins + 1]) - probability(edges[bins])
    audit = pd.DataFrame({"bin": bins, "diferencia": diff}).groupby("bin").diferencia.agg(["size", "mean"])
    if len(audit) != len(edges) - 1 or not np.isfinite(diff).all():
        raise ValueError("Hay un intervalo ALE sin soporte o diferencias no finitas")
    effect = np.r_[0, audit["mean"].cumsum()]
    centered = effect - np.average((effect[1:] + effect[:-1]) / 2, weights=audit["size"])
    table = pd.DataFrame({
        "temp_min_c": edges[:-1], "temp_max_c": edges[1:], "filas": audit["size"],
        "cambio_local_pp": 100 * audit["mean"], "ale_min_pp": 100 * centered[:-1],
        "ale_max_pp": 100 * centered[1:],
    })
    table.to_csv(spatial.OUTPUT / "ale_b3_h4_2023.csv", index=False)
    fig, (ax, counts) = plt.subplots(2, 1, figsize=(7, 5.2), sharex=True,
                                     gridspec_kw={"height_ratios": [3, 1]}, layout="constrained")
    ax.plot(edges, 100 * centered, marker="o", color="#126B70", lw=2)
    ax.axhline(0, color="#8A8F92", linestyle="--", linewidth=1)
    ax.set_ylabel("Efecto local acumulado\n(puntos porcentuales)")
    ax.set_title("Respuesta del modelo b3 a la temperatura\nPiura, temporada 2023 · horizonte de cuatro semanas")
    counts.bar(edges[:-1], audit["size"], width=np.diff(edges), align="edge", color="#81AAB0", edgecolor="white")
    counts.set_ylabel("Filas")
    counts.set_xlabel("Temperatura media (°C)")
    fig.savefig(spatial.OUTPUT / "ale_b3_h4_2023.png", dpi=180)
    plt.close(fig)
    return {"corte": cutoff.isoformat(), "filas_totales": len(test), "filas_con_soporte": len(observed),
            "filas_entrenamiento": len(fit.train), "rango_c": [float(edges[0]), float(edges[-1])],
            "rango_ale_pp": [float(100 * centered.min()), float(100 * centered.max())]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("geografia", type=Path)
    args = parser.parse_args()
    _, _, _, inputs = spatial.training_data()
    origins, arms, hp, _ = spatial.prepare(inputs, args.geografia)
    spatial.OUTPUT.mkdir(parents=True, exist_ok=True)
    summary = temperature_ale(inputs, origins, arms["b3_obs"], hp)
    spatial.archive.write_json(spatial.OUTPUT / "ale_b3_h4_2023.json", summary)
    print(summary, flush=True)
    # Measure CPU cost on one development fold without calculating or inspecting its metrics.
    development = [("temporada_2021", "temporada", 2021)]
    timings = {}
    for name, params in (("heredados", hp), ("extremo_reducido", {**hp, "n_estimators": 700, "max_depth": 6}),
                         ("trial_191", spatial.archive.frozen_configs.V3_HYPERPARAMETERS)):
        start = time.perf_counter()
        spatial.predict(inputs, origins, development, arms["d3_obs"], params, 17)
        timings[name] = time.perf_counter() - start
        print(name, timings[name], flush=True)
    spatial.archive.write_json(spatial.OUTPUT / "tiempos_ajuste_simetrico.json", timings)


if __name__ == "__main__":
    main()
