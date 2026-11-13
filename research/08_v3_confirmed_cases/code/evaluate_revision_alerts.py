"""Compare archived alert rankings and audit discordant early outbreak warnings."""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, precision_recall_curve

from denguekay.config.paths import UBIGEO_CATALOG
from denguekay.evaluation import episodes, protocol
from denguekay.evaluation.metrics import alert_metrics, alerts_from_counts
from denguekay.model.probabilistic_output import count_threshold
from evaluate_alert_cutoffs import DEVELOPMENT, EVALUATION, KEY, OUTPUT, blocks, read_archive
from run_contribution import budget_cutoff, training_data
import run_experiment as archive


DECISIVE = tuple(archive.rules.SEASON_2026_DECIDING)
MODELS = ("b3_obs", "d3_obs", "historia_geo")
METHODS = (*MODELS, "persistencia_prob")
DISPLAY = {"b3_obs": "b3", "d3_obs": "d3", "historia_geo": "Historia + geografía",
           "persistencia_prob": "Persistencia probabilística", "persistencia_det": "Persistencia determinista"}
COLORS = {"b3_obs": "#007C82", "d3_obs": "#7668A8", "historia_geo": "#5A646C",
          "persistencia_prob": "#C86A23", "persistencia_det": "#151515"}
DESTINATION = OUTPUT / "precision_sensibilidad"
HORIZONS = (2, 3, 4)


def curve_and_match(group, method, point):
    y, score = group.brote, group[method]
    precision, recall, thresholds = precision_recall_curve(y, score)
    curve = pd.DataFrame({"precision": precision[:-1], "sensibilidad": recall[:-1], "corte": thresholds})
    admissible = curve.loc[curve.precision.ge(point["precision"] - 1e-12)]
    if admissible.empty:
        match = {"sensibilidad": 0.0, "precision": np.nan, "corte": np.nan}
    else:
        match = admissible.sort_values(["sensibilidad", "precision", "corte"], ascending=False).iloc[0].to_dict()
    match.update(persistencia_precision=point["precision"], persistencia_sensibilidad=point["recall"],
                 ap=average_precision_score(y, score), filas=len(y), semanas_brote=int(y.sum()))
    match["delta_sensibilidad"] = match["sensibilidad"] - point["recall"]
    return curve, match


def compare_rankings(data, seed):
    decisive = data.loc[data.bloque.isin(blocks(DECISIVE))]
    cuts = [(str(h), decisive.loc[decisive.horizonte.eq(h)]) for h in HORIZONS]
    cuts.append(("todos", decisive))
    records, curves = [], []
    for horizon, rows in cuts:
        for block, group in [("conjunto", rows), *rows.groupby("bloque")]:
            point = alert_metrics(group.brote, group.persistencia_det)
            for method in METHODS:
                curve, match = curve_and_match(group, method, point)
                info = {"horizonte": horizon, "bloque": block, "metodo": method, "semilla": seed}
                records.append({**info, **match})
                if block == "conjunto":
                    curves.append(curve.assign(**info))
    return pd.DataFrame(records), pd.concat(curves, ignore_index=True)


def onset_comparison(data, seed, labels, freeze):
    evaluation = data.loc[data.bloque.isin(blocks(EVALUATION))].copy()
    development = data.loc[
        data.bloque.isin(blocks(DEVELOPMENT)) & (data.semana_inicio + pd.Timedelta(days=6)).le(freeze)]
    first = evaluation.groupby("bloque").semana_inicio.min()
    events, operating = [], []
    for h in HORIZONS:
        test = evaluation.loc[evaluation.horizonte.eq(h)].copy()
        past = development.loc[development.horizonte.eq(h)]
        alert_columns = ["persistencia_det"]
        for method in METHODS:
            for policy, cutoff in (("050", 0.50), ("ajustada", budget_cutoff(past[method], past.brote, 1.0))):
                name = f"{method}_{policy}"
                test[name] = test[method].ge(cutoff)
                alert_columns.append(name)
        timed = episodes.episode_lead_time(test, labels, alert_columns)
        timed = timed.loc[timed.semanas_previas_sin_brote.ge(episodes.NO_PREVIOUS_OUTBREAK)
                          & timed.inicio.ge(timed.bloque.map(first) + episodes.ADJACENCY_WINDOW * episodes.WEEK)]
        info = test[["ubigeo", "semana_inicio", "origen_cierre", "casos_Dengue", "persistencia", "umbral_brote_casos"]]
        info = info.rename(columns={"semana_inicio": "inicio", "casos_Dengue": "casos_en_inicio"})
        timed = timed.merge(info, on=["ubigeo", "inicio"], validate="one_to_one")
        timed["minimo_entero_inicio"] = count_threshold(timed.umbral_brote_casos)
        timed["persistencia_alcanza_umbral"] = timed.persistencia.ge(timed.minimo_entero_inicio)
        events.append(timed.assign(semilla=seed))
        for block, group in test.groupby("bloque"):
            outcomes = timed.loc[timed.bloque.eq(block)]
            for name in alert_columns:
                operating.append({"bloque": block, "horizonte": h, "semilla": seed, "regla": name,
                                  "episodios": len(outcomes), "anticipados_2": int(outcomes[name].ge(2).sum()),
                                  **alert_metrics(group.brote, group[name])})
    return pd.concat(events, ignore_index=True), pd.DataFrame(operating)


def plot_curves(curves, matches):
    fig, axes = plt.subplots(2, 2, figsize=(9.2, 7.2), sharex=True, sharey=True, layout="constrained")
    grid = np.linspace(0.001, 1, 1000)
    for ax, (h, title) in zip(axes.flat, (("2", "h2"), ("3", "h3"), ("4", "h4"), ("todos", "h2–h4 agrupados")), strict=True):
        subset = curves.loc[curves.horizonte.eq(h)]
        for method, group in subset.groupby("metodo"):
            lines = []
            for _, scores in group.groupby("semilla"):
                ordered = scores.sort_values("sensibilidad")
                recall = ordered.sensibilidad.to_numpy()
                precision = np.maximum.accumulate(ordered.precision.to_numpy()[::-1])[::-1]
                lines.append(precision[np.searchsorted(recall, grid, side="left")])
            ax.step(grid, np.median(lines, axis=0), where="pre", color=COLORS[method], label=DISPLAY[method])
        point = matches.loc[matches.horizonte.eq(h)].iloc[0]
        ax.scatter(point.persistencia_sensibilidad, point.persistencia_precision,
                   s=58, marker="D", color="#151515", edgecolor="white", zorder=5, label="Persistencia determinista")
        ax.set_title(title)
        ax.set(xlim=(0, 1), ylim=(0, 1.02))
        ax.grid(alpha=0.2)
    axes[0, 0].legend(loc="lower left", fontsize=7.8)
    fig.supxlabel("Sensibilidad para semanas de brote")
    fig.supylabel("Precisión")
    fig.savefig(DESTINATION / "curvas_precision_sensibilidad.png", dpi=190)
    fig.savefig(DESTINATION / "curvas_precision_sensibilidad.pdf")
    plt.close(fig)



def decision_scores(data, seed):
    """Net benefit per district-week at fixed false-positive to false-negative cost ratios."""
    rows = []
    support = data.loc[data.bloque.isin(blocks(EVALUATION))]
    for (h, block), group in support.groupby(["horizonte", "bloque"]):
        y = group.brote.to_numpy(bool)
        for threshold in np.linspace(0.05, 0.50, 46):
            cost = threshold / (1 - threshold)
            for method in (*METHODS, "persistencia_det"):
                alert = group[method].to_numpy(bool) if method == "persistencia_det" else group[method].ge(threshold)
                vp = int((alert & y).sum())
                fp = int((alert & ~y).sum())
                rows.append({"horizonte": h, "bloque": block, "metodo": method, "semilla": seed,
                             "corte": threshold, "costo_fp_sobre_fn": cost, "n": len(y),
                             "vp": vp, "fp": fp, "beneficio_neto": (vp - cost * fp) / len(y)})
    return pd.DataFrame(rows)


def plot_decision_scores(scores):
    h4 = scores.loc[scores.horizonte.eq(4)]
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.7), sharey=True, layout="constrained")
    for ax, (block, season) in zip(axes, h4.groupby("bloque"), strict=True):
        for method, group in season.groupby("metodo"):
            rows = group.sort_values("costo_fp_sobre_fn")
            ax.plot(rows.costo_fp_sobre_fn, 100 * rows.beneficio_neto, color=COLORS[method], label=DISPLAY[method])
        ax.axhline(0, lw=0.8, color="#9C9C9C")
        ax.set_title(block.replace("temporada_", "Temporada "))
        ax.grid(alpha=0.2)
    axes[0].legend(loc="upper right", fontsize=7)
    fig.supxlabel("Costo de una falsa alarma / costo de perder una semana de brote")
    fig.supylabel("Beneficio neto por 100 semanas distritales")
    fig.savefig(DESTINATION / "beneficio_neto_h4.png", dpi=180)
    fig.savefig(DESTINATION / "beneficio_neto_h4.pdf")
    plt.close(fig)


def main():
    baseline_path = archive.OUTPUT / "comparadores_revision" / "predicciones_baselines.csv.gz"
    base = pd.read_csv(baseline_path, dtype={"ubigeo": str}, parse_dates=["semana_inicio", "origen_cierre"],
                       float_precision="round_trip")
    base = base.loc[base.bloque.str.startswith("temporada_")].reset_index(drop=True)
    base["persistencia_det"] = alerts_from_counts(base.persistencia, base.umbral_brote_casos, 2)
    freeze = base.loc[base.bloque.isin(blocks(EVALUATION)), "origen_cierre"].min()
    used = base.bloque.isin(blocks(set(DECISIVE) | set(DEVELOPMENT)))
    align = [*KEY, "origen_cierre", "brote"]
    _, _, _, data = training_data()
    labels = data["etiquetas"][["ubigeo", "semana_inicio", "brote"]]
    ep_reference = pd.read_csv(OUTPUT / "inicios_por_distrito.csv", dtype={"ubigeo": str}, parse_dates=["inicio"])
    ep_key = ["semilla", "bloque", "horizonte", "ubigeo", "inicio"]
    ref_cols = ["b3_presupuesto_1", "persistencia_prob_presupuesto_1"]
    ep_reference = ep_reference.set_index(ep_key)[ref_cols].sort_index()
    tracks = []
    for seed in protocol.SEEDS:
        run = base.copy()
        for method in MODELS:
            path = archive.OUTPUT / "ajuste_simetrico" / "evaluacion" / f"{method}_s{seed}" / "predicciones.csv.gz"
            fitted = read_archive(path, "probabilidad_calibrada")
            fitted = fitted.loc[fitted.bloque.str.startswith("temporada_")].reset_index(drop=True)
            pd.testing.assert_frame_equal(fitted[align], base[align])
            run[method] = fitted.probabilidad_calibrada
        if not run.loc[used, list(METHODS)].apply(lambda s: s.between(0, 1)).all().all():
            raise ValueError("Probabilidades faltantes en desarrollo o evaluación")
        matches, curves = compare_rankings(run, seed)
        events, operating = onset_comparison(run, seed, labels, freeze)
        residual = (run.loc[run.horizonte.eq(4) & run.bloque.isin(blocks(EVALUATION))]
                    .assign(residuo=lambda d: d.brote - d.b3_obs).groupby(["bloque", "ubigeo"], as_index=False)
                    .agg(residuo=("residuo", "mean"), positivos=("brote", "sum")).assign(semilla=seed))
        tracks.append((matches, curves, events, residual, operating, decision_scores(run, seed)))
    matches, curves, events, residual, operating, decisions = [pd.concat(tables, ignore_index=True) for tables in zip(*tracks, strict=True)]
    current = events.set_index(ep_key)[["b3_obs_ajustada", "persistencia_prob_ajustada"]].sort_index()
    current.columns = ref_cols
    pd.testing.assert_frame_equal(current, ep_reference)
    catalog = pd.read_csv(UBIGEO_CATALOG, dtype={"ubigeo": str})
    events = events.merge(catalog, on="ubigeo", validate="many_to_one")
    DESTINATION.mkdir(exist_ok=True)
    matches.to_csv(DESTINATION / "sensibilidad_a_precision_de_persistencia.csv", index=False)
    group = ["horizonte", "bloque", "metodo"]
    matches.groupby(group, as_index=False).median(numeric_only=True).drop(columns="semilla").to_csv(
        DESTINATION / "resumen_sensibilidad.csv", index=False)
    curves.to_csv(DESTINATION / "puntos_curvas.csv.gz", index=False)
    events.to_csv(DESTINATION / "inicios_comparados.csv", index=False)
    residual.groupby(["bloque", "ubigeo"], as_index=False).median(numeric_only=True).drop(columns="semilla").to_csv(
        DESTINATION / "residuo_b3_por_distrito.csv", index=False)
    operating.to_csv(DESTINATION / "operacion_por_metodo_y_semilla.csv", index=False)
    decisions.to_csv(DESTINATION / "beneficio_neto_por_temporada_y_semilla.csv", index=False)
    decision_summary = decisions.groupby(["horizonte", "bloque", "metodo", "corte"], as_index=False).median(numeric_only=True)
    decision_summary.drop(columns="semilla").to_csv(DESTINATION / "resumen_beneficio_neto.csv", index=False)
    plot_curves(curves, matches.loc[matches.bloque.eq("conjunto")])
    plot_decision_scores(decision_summary)
    print(f"{len(matches)} comparaciones, {len(events)} filas de episodios. {DESTINATION}")


if __name__ == "__main__":
    main()
