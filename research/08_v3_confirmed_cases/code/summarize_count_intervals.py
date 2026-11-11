"""Summarize paired count-interval scores and build diagnostics for the manuscript."""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from denguekay.evaluation.metrics import alerts_from_counts
from evaluate_count_intervals import KEY, MODELS, OUTPUT, point_diagnostics, read_prediction
from denguekay.evaluation.protocol import SEEDS


CORE = ("b3_obs", "d3_obs", "historia_geo")
DISPLAY = {"b3_obs": "b3", "d3_obs": "d3", "historia_geo": "Historia y geografía"}
DISTRIBUTIONS = {
    "nb2_bruta": ("Media bruta NB2", "#777D87"),
    "nb2_publicada": ("Media publicada NB2", "#BA642A"),
    "pit_global": ("Recalibración global", "#6F64A0"),
    "pit_por_nivel": ("Recalibración por nivel", "#008081"),
}


def summarize_scores(detail):
    keys = ["variante", "distribucion", "horizonte", "estrato"]
    season = detail.groupby([*keys, "bloque"], as_index=False).median(numeric_only=True).drop(columns="semilla")
    season.to_csv(OUTPUT / "distribuciones_por_temporada.csv", index=False)
    summary = season.groupby(keys, as_index=False).mean(numeric_only=True)
    summary.to_csv(OUTPUT / "resumen_distribuciones.csv", index=False)
    scores = detail.pivot(index=["variante", "horizonte", "estrato", "bloque", "semilla"],
                          columns="distribucion", values=["wis", "cobertura_80", "ancho_80"])
    records = []
    for method in ("pit_global", "pit_por_nivel"):
        delta = pd.DataFrame({m: scores[(m, method)] - scores[(m, "nb2_publicada")]
                              for m in ("wis", "cobertura_80", "ancho_80")})
        delta["wis_relativo"] = delta.wis / scores[("wis", "nb2_publicada")].replace(0, np.nan)
        records.append(delta.reset_index().assign(recalibracion=method))
    paired = pd.concat(records, ignore_index=True)
    groups = ["variante", "horizonte", "estrato", "recalibracion"]
    median = paired.groupby([*groups, "bloque"], as_index=False).median(numeric_only=True).drop(columns="semilla")
    median.to_csv(OUTPUT / "diferencias_por_temporada.csv", index=False)
    final = median.groupby(groups, as_index=False).agg(
        wis=("wis", "mean"), wis_relativo=("wis_relativo", "mean"), cobertura_80=("cobertura_80", "mean"),
        ancho_80=("ancho_80", "mean"), temporadas=("bloque", "size"), temporadas_mejor=("wis", lambda x: int(x.lt(0).sum())),
    )
    final.to_csv(OUTPUT / "resumen_diferencias.csv", index=False)
    return summary


def compare_xgboost_wis(detail):
    support = detail.loc[detail.estrato.eq("todas") & detail.variante.isin(CORE)]
    paired = support.pivot(index=["distribucion", "horizonte", "bloque", "semilla"],
                           columns="variante", values="wis")
    rows = []
    for variant in ("b3_obs", "d3_obs"):
        delta = paired[variant] - paired.historia_geo
        cells = pd.DataFrame({"diferencia_wis": delta, "cambio_relativo_wis": delta / paired.historia_geo})
        rows.append(cells.groupby(level=["distribucion", "horizonte", "bloque"]).median()
                    .reset_index().assign(variante=variant, referencia="historia_geo"))
    pd.concat(rows, ignore_index=True).to_csv(OUTPUT / "wis_clima_pareado_por_temporada.csv", index=False)


def summarize_points(points):
    by = ["variante", "conteo", "horizonte", "estrato", "semilla"]
    points["error_absoluto_total"] = points.mae * points.filas
    points["error_cuadratico_total"] = points.rmse.pow(2) * points.filas
    pooled = points.groupby(by, as_index=False).agg(
        filas=("filas", "sum"), suma_pronosticada=("suma_pronosticada", "sum"), suma_observada=("suma_observada", "sum"),
        error_absoluto_total=("error_absoluto_total", "sum"), error_cuadratico_total=("error_cuadratico_total", "sum"),
    ).assign(mae_agrupado=lambda d: d.error_absoluto_total / d.filas,
             rmse_agrupado=lambda d: np.sqrt(d.error_cuadratico_total / d.filas))
    reference = (points.loc[points.variante.eq("persistencia_nb2"), ["horizonte", "estrato", "bloque", "mae"]]
                 .rename(columns={"mae": "mae_persistencia"}))
    paired = points.merge(reference, on=["horizonte", "estrato", "bloque"], validate="many_to_one")
    paired["razon_mae_persistencia"] = paired.mae / paired.mae_persistencia.replace(0, np.nan)
    pooled_ref = (pooled.loc[pooled.variante.eq("persistencia_nb2"), ["horizonte", "estrato", "mae_agrupado"]]
                  .rename(columns={"mae_agrupado": "mae_persistencia_agrupado"}))
    pooled = pooled.merge(pooled_ref, on=["horizonte", "estrato"], validate="many_to_one")
    pooled["razon_mae_agrupada"] = pooled.mae_agrupado / pooled.mae_persistencia_agrupado.replace(0, np.nan)
    group = ["variante", "conteo", "horizonte", "estrato"]
    by_season = paired.groupby([*group, "bloque"], as_index=False).median(numeric_only=True).drop(columns="semilla")
    by_season.to_csv(OUTPUT / "conteos_por_temporada.csv", index=False)
    report = by_season.groupby(group, as_index=False).mean(numeric_only=True)
    overall = pooled.groupby(group, as_index=False).median(numeric_only=True)[
        [*group, "mae_agrupado", "rmse_agrupado", "razon_mae_agrupada"]]
    report.merge(overall, on=group, validate="one_to_one").to_csv(OUTPUT / "resumen_conteos.csv", index=False)


def count_alert_disagreement(blocks):
    rows, extra = [], []
    for model in CORE:
        for seed in SEEDS:
            path = MODELS / f"{model}_s{seed}" / "predicciones.csv.gz"
            frame = read_prediction(path, [*KEY, "mu_modelo", "conteo_publicado", "probabilidad_calibrada"])
            context = frame.loc[frame.bloque.isin(["temporada_2024", "temporada_2025"])]
            for (h, block), part in context.groupby(["horizonte", "bloque"]):
                support = np.ones(len(part), dtype=bool)
                past = point_diagnostics(part, support, part.persistencia)
                for column in ("mu_modelo", "conteo_publicado"):
                    stats = point_diagnostics(part, support, part[column])
                    extra.append({"variante": model, "semilla": seed, "horizonte": h, "bloque": block,
                                  "conteo": column, "filas": len(part), "mae_persistencia": past["mae"],
                                  "razon_mae_persistencia": stats["mae"] / past["mae"], **stats})
            selected = frame.loc[frame.bloque.isin(blocks)]
            for (h, block), part in selected.groupby(["horizonte", "bloque"]):
                by_count = alerts_from_counts(part.conteo_publicado, part.umbral_brote_casos, 2)
                by_prob = part.probabilidad_calibrada.ge(0.50).to_numpy()
                rows.append({"variante": model, "semilla": seed, "horizonte": h, "bloque": block, "filas": len(part),
                             "solo_probabilidad": int((by_prob & ~by_count).sum()),
                             "solo_conteo": int((by_count & ~by_prob).sum()),
                             "discordantes": int((by_prob != by_count).sum())})
    pd.DataFrame(rows).to_csv(OUTPUT / "discordancia_probabilidad_y_conteo.csv", index=False)
    pd.DataFrame(extra).to_csv(OUTPUT / "conteos_2024_y_2025_por_semilla.csv", index=False)


def plot(summary, hist):
    fig, axes = plt.subplots(3, 3, figsize=(11.5, 8.8), sharey="row", layout="constrained")
    q = summary.loc[summary.horizonte.eq(4)]
    for i, model in enumerate(CORE):
        h = hist.loc[hist.variante.eq(model) & hist.horizonte.eq(4)]
        h = (h.groupby(["distribucion", "semilla", "bin"], as_index=False)[["masa", "filas"]].sum()
             .assign(prop=lambda d: d.masa / d.filas).groupby(["distribucion", "bin"], as_index=False).prop.median())
        axes[0, i].set_title(DISPLAY[model])
        for method, (label, color) in DISTRIBUTIONS.items():
            p = h.loc[h.distribucion.eq(method)].sort_values("bin")
            axes[0, i].stairs(p.prop, np.linspace(0, 1, 11), color=color, lw=1.6, label=label)
            for row, stratum in ((1, "todas"), (2, "brote")):
                selected = q.loc[q.variante.eq(model) & q.distribucion.eq(method) & q.estrato.eq(stratum)].iloc[0]
                axes[row, i].plot([0.5, 0.8, 0.95], selected[["cobertura_50", "cobertura_80", "cobertura_95"]].astype(float),
                                  color=color, lw=1.6, marker="o")
        axes[0, i].axhline(0.1, color="#555555", ls=":", lw=1)
        for row in (1, 2):
            axes[row, i].plot([0.5, 0.95], [0.5, 0.95], color="#555555", ls=":", lw=1)
            axes[row, i].set_ylim(0.25, 1)
        axes[0, i].set_xlabel("PIT")
        axes[2, i].set_xlabel("Cobertura nominal")
        for ax in axes[:, i]:
            ax.grid(axis="y", alpha=0.18)
    axes[0, 0].set_ylabel("Frecuencia por intervalo PIT")
    axes[1, 0].set_ylabel("Cobertura en todas las semanas")
    axes[2, 0].set_ylabel("Cobertura en semanas de brote")
    axes[0, 0].legend(fontsize=7.0, loc="upper right")
    fig.savefig(OUTPUT / "calibracion_conteos_h4.png", dpi=180)
    fig.savefig(OUTPUT / "calibracion_conteos_h4.pdf")
    plt.close(fig)


def main():
    detail = pd.read_csv(OUTPUT / "distribuciones.csv.gz")
    points = pd.read_csv(OUTPUT / "conteos.csv.gz")
    hist = pd.read_csv(OUTPUT / "histogramas_pit.csv.gz")
    key = ["variante", "semilla", "horizonte", "bloque", "distribucion"]
    mass = hist.groupby(key).agg(assigned=("masa", "sum"), expected=("filas", "first"))
    np.testing.assert_allclose(mass.assigned, mass.expected, rtol=0, atol=1e-7)
    summary = summarize_scores(detail)
    compare_xgboost_wis(detail)
    summarize_points(points)
    count_alert_disagreement(detail.bloque.unique())
    plot(summary, hist)
    print("Tablas, discordancias y figura verificadas.")


if __name__ == "__main__":
    main()
