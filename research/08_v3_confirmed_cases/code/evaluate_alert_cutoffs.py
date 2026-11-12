"""Select fixed alert cutoffs in development and apply them to later seasons."""

from pathlib import Path

import pandas as pd

from denguekay.evaluation import episodes, protocol
from run_contribution import BUDGETS, budget_cutoff
import run_experiment as archive


DEVELOPMENT = tuple(archive.rules.HP_TUNING_OBJECTIVE_SEASONS)
EVALUATION = (2022, 2023, 2026)
METHODS = ("b3", "persistencia_prob")
KEY = ["bloque", "horizonte", "ubigeo", "semana_inicio"]
DATES = ["semana_inicio", "origen_cierre"]
OUTPUT = archive.OUTPUT / "cortes_alerta"
COUNT_FIELDS = ["filas", "episodios", "anticipados_2", "vp", "fp", "fn"]


def read_archive(path, probability):
    return pd.read_csv(path, usecols=[*KEY, "origen_cierre", "brote", probability],
                       dtype={"ubigeo": str}, parse_dates=DATES, float_precision="round_trip")


def blocks(seasons):
    return [f"temporada_{s}" for s in seasons]


def rates(data):
    return data.assign(
        proporcion_inicios=lambda d: d.anticipados_2 / d.episodios,
        falsos_por_distrito_52=lambda d: 52 * d.fp / d.filas,
        precision=lambda d: d.vp / (d.vp + d.fp),
        sensibilidad_semanal=lambda d: d.vp / (d.vp + d.fn),
        f1=lambda d: 2 * d.vp / (2 * d.vp + d.fp + d.fn),
    )


def cutoff_policies(data, seed, freeze):
    development = data.loc[
        data.bloque.isin(blocks(DEVELOPMENT))
        & (data.semana_inicio + pd.Timedelta(days=6)).le(freeze)
    ]
    evaluation = data.loc[data.bloque.isin(blocks(EVALUATION))].copy()
    if development.bloque.nunique() != len(DEVELOPMENT) or set(evaluation.bloque) != set(blocks(EVALUATION)):
        raise ValueError("Faltan temporadas del protocolo")
    if evaluation.origen_cierre.lt(freeze).any() or not development.semana_inicio.max() < evaluation.semana_inicio.min():
        raise ValueError("Desarrollo y evaluación se solapan")
    first = evaluation.groupby("bloque").semana_inicio.min()
    counts, cutoffs, event_tables = [], [], []
    for horizon, past in development.groupby("horizonte"):
        test = evaluation.loc[evaluation.horizonte.eq(horizon)].copy()
        records = {}
        for method in METHODS:
            for budget in (*BUDGETS, None):
                policy = "fijo_050" if budget is None else f"presupuesto_{budget:g}"
                cutoff = 0.5 if budget is None else budget_cutoff(past[method], past.brote, budget)
                key = f"{method}_{policy}"
                test[key] = test[method].ge(cutoff)
                n_false = int((past[method].ge(cutoff) & past.brote.eq(0)).sum())
                if budget is not None and n_false > int(len(past) * budget // 52):
                    raise ValueError("Corte de desarrollo fuera de presupuesto")
                record = {"horizonte": horizon, "metodo": method, "politica": policy, "semilla": seed}
                records[key] = record
                cutoffs.append({**record, "corte": cutoff, "presupuesto": budget,
                                "desarrollo_filas": len(past), "desarrollo_fp": n_false,
                                "desarrollo_falsos_por_distrito_52": 52 * n_false / len(past),
                                "ultima_etiqueta": past.semana_inicio.max() + pd.Timedelta(days=6),
                                "fecha_corte": freeze})
        labels = data.loc[data.horizonte.eq(horizon), ["ubigeo", "semana_inicio", "brote"]]
        events = episodes.episode_lead_time(test, labels, list(records))
        events = events.loc[
            events.semanas_previas_sin_brote.ge(episodes.NO_PREVIOUS_OUTBREAK)
            & events.inicio.ge(events.bloque.map(first) + episodes.ADJACENCY_WINDOW * episodes.WEEK)
        ].assign(semilla=seed)
        event_tables.append(events)
        for block, rows in test.groupby("bloque"):
            block_events = events.loc[events.bloque.eq(block)]
            observed = rows.brote.eq(1)
            for key, record in records.items():
                alert = rows[key]
                counts.append({**record, "bloque": block, "filas": len(rows),
                               "episodios": len(block_events),
                               "anticipados_2": int(block_events[key].ge(protocol.MIN_LEAD_TIME).sum()),
                               "vp": int((alert & observed).sum()), "fp": int((alert & ~observed).sum()),
                               "fn": int((~alert & observed).sum())})
    return pd.DataFrame(counts), pd.DataFrame(cutoffs), pd.concat(event_tables, ignore_index=True)


def main():
    baseline_path = archive.OUTPUT / "comparadores_revision" / "predicciones_baselines.csv.gz"
    baseline = read_archive(baseline_path, "persistencia_prob")
    base_columns = [*KEY, "origen_cierre", "brote"]
    freeze = baseline.loc[baseline.bloque.isin(blocks(EVALUATION)), "origen_cierre"].min()
    used = baseline.bloque.isin(blocks((*DEVELOPMENT, *EVALUATION)))
    if not baseline.loc[used, "persistencia_prob"].between(0, 1).all():
        raise ValueError("Persistencia sin probabilidades en el soporte seleccionado")
    inputs = {str(baseline_path.relative_to(archive.ROOT)): archive.sha256(baseline_path)}
    results = []
    for seed in protocol.SEEDS:
        path = archive.OUTPUT / "ajuste_simetrico" / "evaluacion" / f"b3_obs_s{seed}" / "predicciones.csv.gz"
        pred = read_archive(path, "probabilidad_calibrada")
        pd.testing.assert_frame_equal(baseline[base_columns], pred[base_columns])
        if not pred.loc[used, "probabilidad_calibrada"].between(0, 1).all():
            raise ValueError(f"b3 sin probabilidades para la semilla {seed}")
        inputs[str(path.relative_to(archive.ROOT))] = archive.sha256(path)
        results.append(cutoff_policies(baseline.assign(b3=pred.probabilidad_calibrada), seed, freeze))
    counts, cutoffs, events = [pd.concat(tables, ignore_index=True) for tables in zip(*results, strict=True)]
    per_season = counts.groupby(["bloque", "horizonte", "metodo", "politica"], as_index=False)[COUNT_FIELDS].median()
    pooled = per_season.groupby(["horizonte", "metodo", "politica"], as_index=False)[COUNT_FIELDS].sum()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    rates(counts).to_csv(OUTPUT / "evaluacion_por_semilla.csv", index=False)
    rates(per_season).to_csv(OUTPUT / "evaluacion_por_temporada.csv", index=False)
    rates(pooled).to_csv(OUTPUT / "evaluacion_conjunta.csv", index=False)
    cutoffs.to_csv(OUTPUT / "cortes_desarrollo.csv", index=False, float_format="%.17g")
    events.to_csv(OUTPUT / "inicios_por_distrito.csv", index=False)
    archive.write_json(OUTPUT / "manifiesto.json", {
        "desarrollo": DEVELOPMENT, "evaluacion": EVALUATION, "presupuestos": BUDGETS,
        "semillas": protocol.SEEDS, "congelamiento_del_corte": freeze.isoformat(),
        "insumos": inputs, "codigo": archive.sha256(Path(__file__)),
        "protocolo": archive.sha256(Path(__file__).resolve().parents[1] / "protocolo_cortes_alerta.md"),
    })


if __name__ == "__main__":
    main()
