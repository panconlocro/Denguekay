"""Describe uncertainty in paired Brier differences with seasons as resampling units."""

from itertools import product

import numpy as np
import pandas as pd
from scipy import stats

import run_spatial_controls as spatial


archive = spatial.archive
OUTPUT = archive.OUTPUT / "incertidumbre_por_temporada"
MODELS = ("b3_obs", "d3_obs")
DECISIVE = [f"temporada_{s}" for s in spatial.DECIDING]


def season_resamples(values):
    n = len(values)
    draws = np.asarray(list(product(range(n), repeat=n)))
    medians = np.median(values, axis=1)
    blocks = medians[draws].mean(axis=1)
    joint = values[draws].mean(axis=1).ravel()
    signs = np.asarray(list(product((-1, 1), repeat=n)))
    null = (signs * medians).mean(axis=1)
    observed = float(medians.mean())
    margin = stats.t.ppf(0.975, n - 1) * stats.sem(medians)
    return {
        "estimacion": observed,
        "temporadas": n, "semillas": values.shape[1],
        "secuencia_bootstrap": len(draws),
        "temporadas_ic_inf": np.quantile(blocks, 0.025),
        "temporadas_ic_sup": np.quantile(blocks, 0.975),
        "temporadas_y_semilla_ic_inf": np.quantile(joint, 0.025),
        "temporadas_y_semilla_ic_sup": np.quantile(joint, 0.975),
        "minima_media_por_semilla": values.mean(axis=0).min(),
        "maxima_media_por_semilla": values.mean(axis=0).max(),
        "sensibilidad_t_pareada_ic_inf": observed - margin,
        "sensibilidad_t_pareada_ic_sup": observed + margin,
        "p_cambio_signos": np.mean(np.abs(null) >= abs(observed) - 1e-15),
    }


def main():
    metrics = pd.read_csv(archive.OUTPUT / "ajuste_simetrico" / "metricas_por_bloque.csv")
    metrics = metrics.loc[metrics.bloque.isin(DECISIVE)]
    key = ["bloque", "horizonte", "semilla"]
    if not metrics.groupby(key)[["n", "positivos"]].nunique().eq(1).all().all():
        raise ValueError("Soporte diferente entre los modelos climáticos y el comparador")
    cells = metrics.pivot(index=key, columns="variante", values="brier")
    records = []
    for method in MODELS:
        delta = cells[method] - cells.historia_geo
        for score, series in (("absoluto", delta), ("relativo", delta / cells.historia_geo)):
            for h, group in series.groupby("horizonte"):
                table = group.droplevel("horizonte").unstack("semilla").reindex(DECISIVE)
                if table.shape != (6, 5) or table.isna().any().any():
                    raise ValueError("Falta una temporada o semilla pareada")
                for omit in (None, *DECISIVE):
                    sample = table if omit is None else table.drop(index=omit)
                    records.append({"metodo": method, "horizonte": h, "escala": score,
                                    "omitida": omit or "ninguna", **season_resamples(sample.to_numpy())})
    OUTPUT.mkdir(exist_ok=True)
    pd.DataFrame(records).to_csv(OUTPUT / "intervalos_y_sensibilidades.csv", index=False)
    print(f"{len(records)} contrastes de incertidumbre por temporadas, con y sin exclusiones.")


if __name__ == "__main__":
    main()
