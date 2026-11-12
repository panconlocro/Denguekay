"""Compare confirmed-case labels and replay archived count predictions for seasonal alternatives."""

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import nbinom
from sklearn.metrics import average_precision_score

from denguekay.evaluation import episodes, protocol
from denguekay.features.outbreak_label import future_outbreak_threshold
from evaluate_alert_cutoffs import KEY
from run_contribution import training_data
import run_experiment as archive


DESTINATION = archive.OUTPUT / "sensibilidad_etiqueta_revision"
DECISIVE = tuple(archive.rules.SEASON_2026_DECIDING)
SEASONAL = ("principal", "A_2DE_5anios", "B_1p5DE_3anios", "minimo_1", "minimo_5", "estacional_Q75")
RECENT = (4, 8, 12)
MODELS = ("historia_geo", "b3_obs", "d3_obs")
MATCH_WEEKS = 4
WEEK = pd.Timedelta(weeks=1)
CLOSE = pd.Timedelta(days=6)
DATE_KEY = ["ubigeo", "semana_inicio"]


def make_labels(cases, main):
    targets = main[["ubigeo", "anio", "semana", "semana_inicio", "casos_Dengue"]].copy()
    regular = cases.sort_values(DATE_KEY).reset_index(drop=True)
    if not regular.groupby("ubigeo").semana_inicio.diff().dropna().eq(WEEK).all():
        raise ValueError("La serie confirmada tiene huecos semanales")
    reference = (cases.assign(semana_ref=cases.semana.clip(upper=52))
                 .groupby(["ubigeo", "anio", "semana_ref"]).casos_Dengue.sum())
    ref_week = targets.semana.clip(upper=52)
    previous = np.column_stack([
        reference.reindex(pd.MultiIndex.from_arrays([targets.ubigeo, targets.anio - lag, ref_week]))
        for lag in range(1, 6)
    ])
    if not np.isfinite(previous).all():
        raise ValueError("Faltan años en la referencia estacional")
    expected = np.mean(previous, axis=1) + 1.5 * np.std(previous, axis=1, ddof=1)
    np.testing.assert_allclose(expected, main.umbral_brote_casos, rtol=0, atol=1e-12)
    thresholds = {
        "principal": (main.umbral_brote_casos, 2),
        "A_2DE_5anios": (future_outbreak_threshold(cases, None, targets, multiplicador=2.0), 2),
        "B_1p5DE_3anios": (future_outbreak_threshold(cases, None, targets, multiplicador=1.5, anios_previos=3), 2),
        "minimo_1": (main.umbral_brote_casos, 1),
        "minimo_5": (main.umbral_brote_casos, 5),
        "estacional_Q75": (np.quantile(previous, 0.75, axis=1), 2),
    }
    lagged = regular.groupby("ubigeo").casos_Dengue.shift(1)
    for width in RECENT:
        total = lagged.groupby(regular.ubigeo).transform(lambda x: x.rolling(width).sum())
        squares = lagged.pow(2).groupby(regular.ubigeo).transform(lambda x: x.rolling(width).sum())
        # Integer counts give an exact zero numerator for constant windows.
        variance = (width * squares - total.pow(2)) / (width * (width - 1))
        threshold = total / width + 1.5 * np.sqrt(variance)
        series = regular.assign(umbral=threshold).set_index(DATE_KEY).umbral
        threshold = series.reindex(pd.MultiIndex.from_frame(targets[DATE_KEY])).to_numpy()
        thresholds[f"reciente_{width}"] = (threshold, 2)
    labels = {}
    for scenario, (threshold, floor) in thresholds.items():
        if not np.isfinite(threshold).all() or (np.asarray(threshold) < 0).any():
            raise ValueError(f"Umbral inválido: {scenario}")
        table = targets.assign(umbral=threshold, minimo=floor)
        table["k"] = np.maximum(np.floor(table.umbral).astype(int) + 1, floor)
        table["brote"] = table.casos_Dengue.ge(table.k).astype("int8")
        labels[scenario] = table
    np.testing.assert_array_equal(labels["principal"].brote, main.brote)
    return labels


def support_labels(labels, support):
    return {name: support.merge(table, on=DATE_KEY, validate="one_to_one")
            for name, table in labels.items()}


def label_summary(tables):
    rows = []
    principal = tables["principal"].set_index(DATE_KEY).brote
    for scenario, table in tables.items():
        p = principal.reindex(pd.MultiIndex.from_frame(table[DATE_KEY])).to_numpy()
        frame = table.assign(agregada=table.brote.eq(1) & (p == 0),
                             quitada=table.brote.eq(0) & (p == 1),
                             umbral_cero=table.umbral.eq(0),
                             positivo_en_minimo=table.brote.eq(1) & table.k.eq(table.minimo),
                             un_caso_bajo_minimo=table.casos_Dengue.eq(1) & table.umbral.lt(1) & table.minimo.gt(1))
        for block, part in frame.groupby("bloque"):
            row = {"escenario": scenario, "bloque": block, "filas": len(part), "positivas": int(part.brote.sum())}
            for col in ("agregada", "quitada", "umbral_cero", "positivo_en_minimo", "un_caso_bajo_minimo"):
                row[col] = int(part[col].sum())
            rows.append(row)
    return pd.DataFrame(rows)


def compare_onsets(labels, support):
    calendar = support[["semana_inicio", "bloque"]].drop_duplicates()
    clean = {}
    for scenario, table in labels.items():
        eps = episodes.episodes(table)
        clean[scenario] = eps.loc[eps.semanas_previas_sin_brote.ge(episodes.NO_PREVIOUS_OUTBREAK)]
    pairs, counts = [], []
    keys = ["ubigeo", "inicio"]
    for scenario, alternative in clean.items():
        if scenario == "principal":
            continue
        left = clean["principal"][keys].rename(columns={"inicio": "inicio_principal"})
        right = alternative[keys].rename(columns={"inicio": "inicio_alternativo"})
        pair = left.merge(right, on="ubigeo", validate="many_to_many")
        distance = (pair.inicio_alternativo - pair.inicio_principal).dt.days // 7
        pair = pair.loc[distance.abs().le(MATCH_WEEKS)].assign(diferencia_semanas=distance)
        if pair.duplicated(["ubigeo", "inicio_principal"]).any() or pair.duplicated(["ubigeo", "inicio_alternativo"]).any():
            raise ValueError("Emparejamiento ambiguo entre inicios limpios")
        pair = pair.merge(calendar, left_on="inicio_principal", right_on="semana_inicio", how="left")
        pair = pair.drop(columns="semana_inicio").rename(columns={"bloque": "bloque_principal"})
        pair = pair.merge(calendar, left_on="inicio_alternativo", right_on="semana_inicio", how="left")
        pairs.append(pair.drop(columns="semana_inicio").rename(columns={"bloque": "bloque_alternativo"})
                     .assign(escenario=scenario))
    for scenario, ep in clean.items():
        chosen = ep.merge(calendar, left_on="inicio", right_on="semana_inicio", validate="many_to_one")
        summary = chosen.assign(una_semana=chosen.semanas_brote.eq(1)).groupby("bloque", as_index=False).agg(
            inicios=("inicio", "size"), una_semana=("una_semana", "sum"))
        counts.append(summary.assign(escenario=scenario))
    return pd.concat(counts, ignore_index=True), pd.concat(pairs, ignore_index=True)


def calibration_indices(support):
    plan = []
    for h, data in support.groupby("horizonte"):
        starts = data.groupby("bloque").semana_inicio.min()
        for block, group in data.groupby("bloque"):
            cutoff = protocol.block_cutoff(group)
            previous = data.bloque.map(starts).lt(starts[block]) & (data.semana_inicio + CLOSE).le(cutoff)
            plan.append((h, block, group.index.to_numpy(), data.index[previous].to_numpy()))
    return plan


def evaluate(scores, y, plan, reference=None):
    cells = []
    for h, block, test, past in plan:
        observed = y[test]
        raw = scores[test]
        p = None
        if len(np.unique(y[past])) == 2:
            fit = protocol.fit_calibrator(scores[past], y[past])
            p = fit(raw)
        if reference is not None:
            if p is None:
                if not np.isnan(reference[test]).all():
                    raise ValueError("Soporte diferente de la calibración principal")
            else:
                np.testing.assert_allclose(p, reference[test], rtol=0, atol=1e-12)
        cells.append({"bloque": block, "horizonte": h, "filas": len(test), "positivos": int(observed.sum()),
                      "filas_calibracion": len(past), "positivos_calibracion": int(y[past].sum()),
                      "brier": np.mean((p - observed) ** 2) if p is not None else np.nan,
                      "ap": average_precision_score(observed, p) if p is not None and observed.any() else np.nan})
    return pd.DataFrame(cells)


def score_archives(base, labels):
    support = base[[*KEY, "origen_cierre", "casos_Dengue", "brote"]]
    plan = calibration_indices(support)
    scenario_arrays = {}
    lookup = pd.MultiIndex.from_frame(support[DATE_KEY])
    for name in SEASONAL:
        table = labels[name].set_index(DATE_KEY).reindex(lookup)
        np.testing.assert_array_equal(table.casos_Dengue, support.casos_Dengue)
        scenario_arrays[name] = table.k.to_numpy(), table.brote.to_numpy()
    results = []
    for scenario, (k, y) in scenario_arrays.items():
        ratio = (base.persistencia.to_numpy(float) + 0.5) / (k + 0.5)
        reference = base.persistencia_prob.to_numpy(float) if scenario == "principal" else None
        results.append(evaluate(ratio / (1 + ratio), y, plan, reference).assign(
            escenario=scenario, modelo="persistencia_prob", semilla=17))
    paths = {}
    for seed in protocol.SEEDS:
        for method in MODELS:
            path = archive.OUTPUT / "ajuste_simetrico" / "evaluacion" / f"{method}_s{seed}" / "predicciones.csv.gz"
            fields = [*support.columns, "mu_modelo", "alpha_usada", "probabilidad_cruda", "probabilidad_calibrada"]
            preds = pd.read_csv(path, usecols=fields, dtype={"ubigeo": str}, parse_dates=["semana_inicio", "origen_cierre"],
                                float_precision="round_trip")
            pd.testing.assert_frame_equal(preds[support.columns], support)
            mu = np.maximum(preds.mu_modelo.to_numpy(), 1e-9)
            alpha = preds.alpha_usada.to_numpy()
            for scenario, (k, y) in scenario_arrays.items():
                raw = nbinom.sf(k - 1, 1 / alpha, 1 / (1 + alpha * mu))
                reference = None
                if scenario == "principal":
                    np.testing.assert_allclose(raw, preds.probabilidad_cruda, rtol=0, atol=1e-12)
                    reference = preds.probabilidad_calibrada.to_numpy()
                results.append(evaluate(raw, y, plan, reference).assign(
                    escenario=scenario, modelo=method, semilla=seed))
            paths[str(path.relative_to(archive.ROOT))] = archive.sha256(path)
        print(f"Probabilidades reproducidas, semilla {seed}", flush=True)
    return pd.concat(results, ignore_index=True), paths


def contrasts(metrics):
    key = ["escenario", "bloque", "horizonte"]
    model = metrics.loc[metrics.modelo.isin(MODELS)].pivot(index=[*key, "semilla"], columns="modelo", values="brier")
    frames = []
    for name in MODELS[1:]:
        diff = model[name] - model.historia_geo
        frames.append(pd.DataFrame({"delta_brier": diff, "delta_pct": 100 * diff / model.historia_geo})
                      .groupby(level=key).median().reset_index().assign(modelo=name))
    return pd.concat(frames, ignore_index=True)


def main():
    confirmed, _, _, data = training_data()
    labels = make_labels(data["casos"], data["etiquetas"])
    baseline_path = archive.OUTPUT / "comparadores_revision" / "predicciones_baselines.csv.gz"
    base = pd.read_csv(baseline_path, dtype={"ubigeo": str}, parse_dates=["semana_inicio", "origen_cierre"],
                       float_precision="round_trip")
    support = base.loc[base.horizonte.eq(4), ["bloque", *DATE_KEY]]
    if len(support) != 64935 or support.duplicated(DATE_KEY).any():
        raise ValueError("Soporte común inválido")
    tables = support_labels(labels, support)
    if any(len(table) != len(support) for table in tables.values()):
        raise ValueError("Una etiqueta cambió el soporte")
    DESTINATION.mkdir(exist_ok=True)
    pd.concat([t.assign(escenario=s) for s, t in tables.items()], ignore_index=True).to_csv(
        DESTINATION / "etiquetas_comunes.csv.gz", index=False)
    label_summary(tables).to_csv(DESTINATION / "etiquetas_por_temporada.csv", index=False)
    onset_counts, onset_pairs = compare_onsets(labels, support)
    onset_counts.to_csv(DESTINATION / "inicios_por_temporada.csv", index=False)
    onset_pairs.to_csv(DESTINATION / "inicios_emparejados.csv", index=False)
    print("Etiquetas e inicios calculados", flush=True)
    metrics, paths = score_archives(base, labels)
    metrics.to_csv(DESTINATION / "metricas_probabilidades.csv", index=False)
    comparison = contrasts(metrics)
    comparison.to_csv(DESTINATION / "contrastes_por_temporada.csv", index=False)
    decisive = comparison.loc[comparison.bloque.isin([f"temporada_{s}" for s in DECISIVE])]
    rows = pd.concat([decisive.assign(sin_2026=False),
                      decisive.loc[decisive.bloque.ne("temporada_2026")].assign(sin_2026=True)])
    rows.groupby(["escenario", "modelo", "horizonte", "sin_2026"], as_index=False).agg(
        delta_brier=("delta_brier", "mean"), delta_pct=("delta_pct", "mean"),
        temporadas=("delta_brier", "count"), mejores=("delta_brier", lambda x: int(x.lt(0).sum()))
    ).to_csv(DESTINATION / "resumen_predictivo.csv", index=False)
    archive.write_json(DESTINATION / "manifiesto.json", {
        "escenarios_con_probabilidades": SEASONAL, "ventanas_recientes": RECENT,
        "temporadas_decisivas": DECISIVE, "tolerancia_inicios_semanas": MATCH_WEEKS,
        "entradas_confirmadas": confirmed["configuracion"]["insumos"],
        "predicciones": {**paths, str(baseline_path.relative_to(archive.ROOT)): archive.sha256(baseline_path)},
        "codigo": archive.sha256(Path(__file__)),
        "protocolo": archive.sha256(Path(__file__).resolve().parents[1] / "protocolo_sensibilidad_etiqueta_confirmados.md"),
    })


if __name__ == "__main__":
    main()
