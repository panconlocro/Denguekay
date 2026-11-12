"""Sensitivity of paired Brier differences to crossed district and season effects."""

import numpy as np
import pandas as pd
from scipy.stats import t

from evaluate_alert_cutoffs import blocks, read_archive
import run_spatial_controls as spatial


archive = spatial.archive
OUTPUT = archive.OUTPUT / "incertidumbre_por_temporada"
TUNING = archive.OUTPUT / "ajuste_simetrico" / "evaluacion"
DECISIVE = blocks(spatial.DECIDING)
MODELS = ("b3_obs", "d3_obs")
KEY = ["bloque", "horizonte", "ubigeo", "semana_inicio", "origen_cierre", "brote"]


def load(variant, seed):
    path = TUNING / f"{variant}_s{seed}" / "predicciones.csv.gz"
    pred = read_archive(path, "probabilidad_calibrada")
    return pred.loc[pred.bloque.isin(DECISIVE)].reset_index(drop=True)


def loss_cells():
    parts = []
    for seed in spatial.pa.SEEDS:
        base = load("historia_geo", seed)
        for model in MODELS:
            predictions = load(model, seed)
            pd.testing.assert_frame_equal(predictions[KEY], base[KEY])
            loss_delta = (predictions.probabilidad_calibrada - base.brote) ** 2 - (
                base.probabilidad_calibrada - base.brote) ** 2
            part = (base[["bloque", "horizonte", "ubigeo"]].assign(diferencia=loss_delta)
                    .groupby(["bloque", "horizonte", "ubigeo"], as_index=False)
                    .agg(diferencia=("diferencia", "mean"), filas=("diferencia", "size")))
            if len(part) != 6 * 3 * 65 or part.diferencia.isna().any():
                raise ValueError("Matriz distrito-temporada incompleta")
            if not part.groupby(["bloque", "horizonte"]).filas.nunique().eq(1).all():
                raise ValueError("Distinto número de semanas por distrito en una misma temporada")
            parts.append(part.assign(semilla=seed, variante=model))
    return pd.concat(parts, ignore_index=True)


def crossed_anova(table):
    """Method-of-moments variance components for a balanced crossed layout."""
    n_seasons, n_districts = table.shape
    grand = table.mean()
    season_mean = table.mean(axis=1)
    district_mean = table.mean(axis=0)
    residual = table - season_mean[:, None] - district_mean + grand
    ms_season = n_districts * np.sum((season_mean - grand) ** 2) / (n_seasons - 1)
    ms_district = n_seasons * np.sum((district_mean - grand) ** 2) / (n_districts - 1)
    ms_residual = np.sum(residual ** 2) / ((n_seasons - 1) * (n_districts - 1))
    raw_season = (ms_season - ms_residual) / n_districts
    raw_district = (ms_district - ms_residual) / n_seasons
    season_var, district_var = max(raw_season, 0), max(raw_district, 0)
    se = np.sqrt(season_var / n_seasons + district_var / n_districts + ms_residual / table.size)
    margin = t.ppf(0.975, n_seasons - 1) * se
    return {"diferencia_brier": grand, "temporadas": n_seasons, "distritos": n_districts,
            "var_temporada": season_var, "var_distrito": district_var, "var_residual": ms_residual,
            "frontera_temporada": raw_season < 0, "frontera_distrito": raw_district < 0,
            "error_estandar": se, "ic_inf": grand - margin, "ic_sup": grand + margin}


def main():
    cells = loss_cells()
    OUTPUT.mkdir(exist_ok=True)
    cells.to_csv(OUTPUT / "diferencias_distrito_temporada_semilla.csv.gz", index=False)
    averaged = cells.groupby(["bloque", "horizonte", "ubigeo", "variante"], as_index=False).diferencia.mean()
    results = []
    groups = [(str(seed), group) for seed, group in cells.groupby("semilla")] + [("media_semillas", averaged)]
    for summary, rows in groups:
        for (variant, h), group in rows.groupby(["variante", "horizonte"]):
            wide = group.pivot(index="bloque", columns="ubigeo", values="diferencia").reindex(DECISIVE)
            if wide.shape != (6, 65) or wide.isna().any().any():
                raise ValueError("Matriz de efectos cruzados incompleta")
            for omit in (None, *DECISIVE):
                table = wide if omit is None else wide.drop(index=omit)
                results.append({"semilla": summary, "variante": variant, "horizonte": h,
                                "omitida": omit or "ninguna", **crossed_anova(table.to_numpy())})
    pd.DataFrame(results).to_csv(OUTPUT / "sensibilidad_efectos_cruzados.csv", index=False)
    print(f"{len(results)} contrastes de efectos cruzados auditados.")


if __name__ == "__main__":
    main()
