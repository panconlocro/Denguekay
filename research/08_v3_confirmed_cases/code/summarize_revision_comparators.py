"""Build paired probabilities and point-count tables from archived predictions."""

import numpy as np
import pandas as pd

import run_statistical_benchmarks as bench

archive = bench.archive
HORIZON = ["bloque", "horizonte"]
KEY = [*HORIZON, "ubigeo", "semana_inicio"]
SEASONS = [f"temporada_{s}" for s in bench.spatial.DECIDING]


def count_scores(data, column, arm, seed):
    observed, predicted = data.casos_Dengue, data[column]
    error = predicted - observed
    rows = data[HORIZON].assign(mae=error.abs(), mse=error ** 2, sesgo=error)
    rows = rows.groupby(HORIZON, as_index=False).mean()
    return rows.assign(variante=arm, semilla=seed, rmse=np.sqrt(rows.pop("mse")))


def main():
    tune = archive.OUTPUT / "ajuste_simetrico"
    folder = bench.OUTPUT
    baselines = pd.read_csv(folder / "predicciones_baselines.csv.gz", dtype={"ubigeo": str})
    common = baselines.loc[baselines.persistencia_prob.notna()].reset_index(drop=True)
    if len(common) != 184665 or common.climatologia.isna().any():
        raise ValueError("La persistencia y la climatología no comparten el soporte esperado")
    t = pd.concat([pd.read_csv(tune / "metricas_por_bloque.csv"),
                   pd.read_csv(folder / "metricas_por_bloque.csv")], ignore_index=True)
    t = t.loc[t.bloque.isin(common.bloque)]
    reference = t.loc[t.variante.isin(["persistencia_prob", "climatologia"])].pivot(
        index=HORIZON, columns="variante", values="brier").reset_index()
    quality = t.merge(reference, on=HORIZON, validate="many_to_one", how="left")
    if not quality[["persistencia_prob", "climatologia"]].gt(0).all().all():
        raise ValueError("Brier de referencia inválido")
    quality = quality.assign(bss_persistencia=1 - quality.brier / quality.persistencia_prob,
                             bss_climatologia=1 - quality.brier / quality.climatologia)
    quality.to_csv(folder / "probabilidades_por_bloque_y_semilla.csv", index=False)
    common_seasons = common.loc[common.bloque.isin(SEASONS)].reset_index(drop=True)
    counts = [count_scores(common_seasons, "persistencia", "persistencia_conteo", 17)]
    locations = sorted([*(tune / "evaluacion").glob("*_s*/predicciones.csv.gz"),
                        *folder.glob("*_s*/predicciones.csv.gz")])
    if len(locations) != 23:
        raise ValueError("Faltan predicciones de conteo de los tres modelos y comparadores")
    columns = [*KEY, "variante", "semilla", "casos_Dengue", "estacional", "mu_modelo", "conteo_publicado"]
    for i, path in enumerate(locations):
        data = pd.read_csv(path, usecols=columns, dtype={"ubigeo": str})
        data = data.loc[data.bloque.isin(SEASONS)].reset_index(drop=True)
        pd.testing.assert_frame_equal(data[[*KEY, "casos_Dengue"]], common_seasons[[*KEY, "casos_Dengue"]])
        if not np.isfinite(data[["estacional", "mu_modelo", "conteo_publicado"]]).all().all():
            raise ValueError(f"Conteos no finitos: {path.parent.name}")
        arm, seed = data.loc[0, ["variante", "semilla"]]
        if i == 0:
            counts.append(count_scores(data, "estacional", "ingenuo_estacional", 17))
        for column, name in (("mu_modelo", "crudo"), ("conteo_publicado", "mezclado")):
            counts.append(count_scores(data, column, arm, seed).assign(salida=name))
    count_cells = pd.concat(counts, ignore_index=True).fillna({"salida": "base"})
    count_cells.to_csv(folder / "conteos_por_bloque_y_semilla.csv", index=False)
    p = quality.loc[quality.bloque.isin(SEASONS)]
    prob_summary = p.groupby(["variante", *HORIZON])[["brier", "auprc", "bss_persistencia", "bss_climatologia"]].median()
    prob_summary.groupby(["variante", "horizonte"]).mean().reset_index().to_csv(
        folder / "tabla_probabilidades.csv", index=False)
    count_summary = count_cells.groupby(["variante", "salida", *HORIZON])[["mae", "rmse", "sesgo"]].median()
    count_summary.groupby(["variante", "salida", "horizonte"]).mean().reset_index().to_csv(
        folder / "tabla_conteos.csv", index=False)


if __name__ == "__main__":
    main()
