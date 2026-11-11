"""Locate archived false alerts by district history and position relative to outbreaks."""

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from denguekay.config.paths import UBIGEO_CATALOG
from denguekay.evaluation import episodes, protocol
from evaluate_alert_cutoffs import EVALUATION, KEY, METHODS, OUTPUT, blocks, read_archive
from run_contribution import training_data
import run_experiment as archive


HORIZON = 4
POLICY = "presupuesto_1"
DESTINATION = OUTPUT / "diagnostico_falsos_avisos"
WEEK = pd.Timedelta(weeks=1)
HISTORY_CLASS = ["Sin casos registrados", "Casos sin semanas de brote", "Con semanas de brote"]


def classify(cases, outbreaks):
    return np.select([cases.eq(0), outbreaks.eq(0)], HISTORY_CLASS[:2], default=HISTORY_CLASS[2])


def outbreak_position(panel, district_episodes):
    if district_episodes.empty:
        return np.full(len(panel), "A más de dos semanas")
    weeks = panel.semana_inicio.to_numpy(dtype="datetime64[ns]")
    start = district_episodes.inicio.to_numpy(dtype="datetime64[ns]")
    end = district_episodes.fin.to_numpy(dtype="datetime64[ns]")
    previous = np.searchsorted(start, weeks, side="right") - 1
    following = previous + 1
    prev_end = end[np.maximum(previous, 0)]
    next_start = start[np.minimum(following, len(start) - 1)]
    inside = (previous >= 0) & (weeks <= prev_end)
    after = (previous >= 0) & (weeks > prev_end) & (weeks - prev_end <= 2 * WEEK)
    before = (following < len(start)) & (next_start - weeks <= 2 * WEEK)
    return np.select([inside, before & after, before, after],
                     ["Pausa dentro del episodio", "Entre dos episodios", "1–2 semanas antes", "1–2 semanas después"],
                     default="A más de dos semanas")


def district_context(test, cases, labels):
    last = test.groupby("bloque").origen_cierre.min()
    history = []
    district_episodes = episodes.episodes(labels)
    for block, cutoff in last.items():
        past_cases = cases.loc[(cases.semana_inicio + pd.Timedelta(days=6)).le(cutoff)]
        past_labels = labels.loc[(labels.semana_inicio + pd.Timedelta(days=6)).le(cutoff)]
        n_cases = past_cases.groupby("ubigeo").casos_Dengue.sum().rename("casos_previos")
        n_positive = past_labels.groupby("ubigeo").brote.sum().rename("semanas_brote_previas")
        past_episodes = episodes.episodes(past_labels).groupby("ubigeo").size().rename("episodios_previos")
        history.append(pd.concat([n_cases, n_positive, past_episodes], axis=1)
                       .fillna({"episodios_previos": 0}).reset_index().assign(bloque=block))
    district = pd.concat(history, ignore_index=True)
    season = test.groupby(["bloque", "ubigeo"], as_index=False).agg(
        casos_temporada=("casos_Dengue", "sum"), semanas_brote_temporada=("brote", "sum"))
    panel = test.merge(district, on=["bloque", "ubigeo"], validate="many_to_one").merge(
        season, on=["bloque", "ubigeo"], validate="many_to_one")
    lifetime = cases.groupby("ubigeo").casos_Dengue.sum().rename("casos_serie")
    positives = labels.groupby("ubigeo").brote.sum().rename("semanas_brote_serie")
    panel = panel.join(lifetime, on="ubigeo").join(positives, on="ubigeo")
    panel["historia_previa"] = classify(panel.casos_previos, panel.semanas_brote_previas)
    panel["temporada"] = classify(panel.casos_temporada, panel.semanas_brote_temporada)
    panel["serie_completa"] = classify(panel.casos_serie, panel.semanas_brote_serie)
    case_index = cases.set_index(["ubigeo", "semana_inicio"]).casos_Dengue
    for i in range(1, 5):
        keys = pd.MultiIndex.from_arrays([panel.ubigeo, panel.semana_inicio + i * WEEK])
        panel[f"casos_s{i}"] = case_index.reindex(keys).to_numpy()
    future = panel[["casos_s1", "casos_s2", "casos_s3", "casos_s4"]]
    if future.isna().any().any():
        raise ValueError("Faltan semanas futuras para clasificar la proximidad")
    panel["proximidad_casos"] = np.select(
        [panel.casos_Dengue.gt(0), future.iloc[:, :2].gt(0).any(axis=1), future.gt(0).any(axis=1)],
        ["Casos en semana objetivo", "Primeros casos en 1–2 semanas", "Primeros casos en 3–4 semanas"],
        default="Cero casos durante cinco semanas")
    positions = pd.Series(index=panel.index, dtype="object")
    for ubigeo, group in panel.groupby("ubigeo"):
        eps = district_episodes.loc[district_episodes.ubigeo.eq(ubigeo)]
        positions.loc[group.index] = outbreak_position(group, eps)
    panel["posicion_brote"] = positions.where(panel.brote.eq(0), "Semana de brote")
    panel["semana_temporada"] = (panel.semana_inicio - panel.bloque.map(
        test.groupby("bloque").semana_inicio.min())).dt.days // 7 + 1
    return panel


def audit_alerts():
    baseline_path = archive.OUTPUT / "comparadores_revision" / "predicciones_baselines.csv.gz"
    base = pd.read_csv(baseline_path, dtype={"ubigeo": str}, parse_dates=["semana_inicio", "origen_cierre"],
                       float_precision="round_trip")
    base = base.loc[base.horizonte.eq(HORIZON) & base.bloque.isin(blocks(EVALUATION))].reset_index(drop=True)
    _, _, _, data = training_data()
    keys = ["ubigeo", "semana_inicio"]
    observed = data["etiquetas"][keys + ["brote", "casos_Dengue"]].set_index(keys)
    aligned = observed.reindex(pd.MultiIndex.from_frame(base[keys]))
    np.testing.assert_array_equal(aligned.brote, base.brote)
    np.testing.assert_array_equal(aligned.casos_Dengue, base.casos_Dengue)
    catalog = pd.read_csv(UBIGEO_CATALOG, dtype={"ubigeo": str})
    fields = [*KEY, "origen_cierre", "brote", "casos_Dengue", "persistencia_prob"]
    context = district_context(base[fields], data["casos"], data["etiquetas"]).merge(
        catalog[["ubigeo", "distrito", "provincia"]], on="ubigeo", validate="many_to_one")
    pd.testing.assert_frame_equal(context[KEY], base[KEY])
    thresholds = pd.read_csv(OUTPUT / "cortes_desarrollo.csv", float_precision="round_trip")
    thresholds = thresholds.query("politica == @POLICY and horizonte == @HORIZON").set_index(["semilla", "metodo"]).corte
    detail = []
    for seed in protocol.SEEDS:
        path = archive.OUTPUT / "ajuste_simetrico" / "evaluacion" / f"b3_obs_s{seed}" / "predicciones.csv.gz"
        forecasts = read_archive(path, "probabilidad_calibrada")
        forecasts = forecasts.loc[forecasts.horizonte.eq(HORIZON) & forecasts.bloque.isin(blocks(EVALUATION))]
        forecasts = forecasts.reset_index(drop=True)
        pd.testing.assert_frame_equal(forecasts[[*KEY, "origen_cierre", "brote"]], base[[*KEY, "origen_cierre", "brote"]])
        scores = {"b3": forecasts.probabilidad_calibrada, "persistencia_prob": base.persistencia_prob}
        for method in METHODS:
            p = scores[method]
            cutoff = thresholds.loc[(seed, method)]
            alert = p.ge(cutoff)
            detail.append(context.assign(semilla=seed, metodo=method, probabilidad=p, corte=cutoff,
                                         fp=alert & context.brote.eq(0), vp=alert & context.brote.eq(1)))
    panel = pd.concat(detail, ignore_index=True)
    reference = pd.read_csv(OUTPUT / "evaluacion_por_semilla.csv").query(
        "politica == @POLICY and horizonte == @HORIZON")
    key = ["bloque", "semilla", "metodo"]
    pd.testing.assert_frame_equal(panel.groupby(key)[["fp", "vp"]].sum(),
                                  reference.set_index(key)[["fp", "vp"]].sort_index())
    return panel, context


def summarize(panel, by):
    rows = (panel.assign(negativa=panel.brote.eq(0))
            .groupby(["metodo", "semilla", *by], as_index=False)
            .agg(fp=("fp", "sum"), vp=("vp", "sum"), filas=("fp", "size"), negativas=("negativa", "sum")))
    return rows.groupby(["metodo", *by], as_index=False).agg(
        fp_medio=("fp", "mean"), fp_min=("fp", "min"), fp_max=("fp", "max"),
        vp_medio=("vp", "mean"), filas=("filas", "first"), negativas=("negativas", "first")
    ).assign(fp_por_distrito_52=lambda d: 52 * d.fp_medio / d.filas,
             fp_por_100_semanas_negativas=lambda d: 100 * d.fp_medio / d.negativas)


def plot_weekly(weekly, context):
    actual = context.groupby(["bloque", "semana_inicio"], as_index=False).casos_Dengue.sum()
    fig, axes = plt.subplots(2, 3, figsize=(12, 6), sharex="col", layout="constrained")
    for i, (block, weeks) in enumerate(actual.groupby("bloque")):
        date, case = weeks.semana_inicio, weeks.casos_Dengue
        axes[0, i].plot(date, case, color="#34383d", lw=1.6)
        axes[0, i].fill_between(date, case, color="#b3b8bb", alpha=0.4)
        axes[0, i].set_title(block.replace("temporada_", "Temporada "))
        for method, color, label in (("b3", "#007C82", "b3"),
                                     ("persistencia_prob", "#C86A23", "Persistencia probabilística")):
            subset = weekly.loc[weekly.bloque.eq(block) & weekly.metodo.eq(method)]
            axes[1, i].plot(subset.semana_inicio, subset.fp_medio, label=label, color=color, lw=1.5)
        axes[1, i].xaxis.set_major_locator(mdates.MonthLocator(interval=3))
        axes[1, i].xaxis.set_major_formatter(mdates.DateFormatter("%m/%y"))
        axes[0, i].set_ylim(0, case.max() * 1.08)
        axes[1, i].set_ylim(0, weekly.fp_medio.max() * 1.10)
        for ax in axes[:, i]:
            ax.grid(axis="y", alpha=0.25)
    axes[0, 0].set_ylabel("Casos confirmados en Piura")
    axes[1, 0].set_ylabel("Falsos avisos semanales")
    axes[1, 0].legend(loc="upper left", fontsize=8)
    fig.supxlabel("Semana objetivo (mes/año). La escala de casos varía por temporada.")
    fig.savefig(DESTINATION / "falsos_avisos_y_casos_por_semana.png", dpi=180)
    plt.close(fig)


def main():
    panel, context = audit_alerts()
    DESTINATION.mkdir(exist_ok=True)
    for field in ("historia_previa", "temporada", "serie_completa", "proximidad_casos", "posicion_brote"):
        summarize(panel, [field]).to_csv(DESTINATION / f"{field}.csv", index=False)
        summarize(panel, ["bloque", field]).to_csv(DESTINATION / f"{field}_por_temporada.csv", index=False)
    summarize(panel, ["bloque", "ubigeo", "distrito", "provincia"]).to_csv(
        DESTINATION / "por_distrito_y_temporada.csv", index=False)
    summarize(panel, ["ubigeo", "distrito", "provincia"]).to_csv(DESTINATION / "por_distrito.csv", index=False)
    weekly = summarize(panel, ["bloque", "semana_inicio", "semana_temporada"])
    weekly.to_csv(DESTINATION / "por_semana.csv", index=False)
    panel.loc[panel.fp].to_csv(DESTINATION / "falsos_avisos_por_fila.csv.gz", index=False)
    context[["bloque", "ubigeo", "distrito", "provincia", "casos_previos", "semanas_brote_previas", "episodios_previos",
             "casos_temporada", "semanas_brote_temporada", "casos_serie", "semanas_brote_serie",
             "historia_previa", "temporada", "serie_completa"]].drop_duplicates().to_csv(
        DESTINATION / "contexto_por_distrito_y_temporada.csv", index=False)
    plot_weekly(weekly, context)
    print(f"{len(context)} filas auditadas. {DESTINATION}")


if __name__ == "__main__":
    main()
