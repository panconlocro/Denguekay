"""Replay the confirmed-case forecasts under fixed weekly incidence definitions."""

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import nbinom

from denguekay.config.paths import UBIGEO_CATALOG
from denguekay.evaluation import protocol
from denguekay.model.probabilistic_output import count_threshold, negative_binomial_probability
from evaluate_alert_cutoffs import KEY
from evaluate_label_sensitivity import (
    DATE_KEY, DECISIVE, MODELS, calibration_indices, compare_onsets, contrasts, evaluate,
)
from run_contribution import training_data
import run_experiment as archive


OUTPUT = archive.OUTPUT / "sensibilidad_incidencia"
POPULATION = OUTPUT / "insumos" / "inei_poblacion_distrital_2018_2026.xlsx"
YEARS = range(2018, 2027)
BLOCKS = [f"temporada_{year}" for year in range(2019, 2027)]
DECIDING = [f"temporada_{year}" for year in DECISIVE if f"temporada_{year}" in BLOCKS]
RATES = (5, 10, 20)
UNIT = 100000
SOURCE = ("https://cdn.www.gob.pe/uploads/document/file/8261096/"
          "6894980-peru-poblacion-total-proyectada-al-30-de-junio-de-cada-ano-"
          "segun-departamento-provincia-y-distrito-2018-2026.xlsx?v=1768402069")


def read_population():
    table = pd.read_excel(POPULATION, sheet_name="POB. PROYECTADA 2018-2026", skiprows=4,
                          header=None, dtype={0: str})
    if table.iloc[0, 2:].tolist() != list(YEARS):
        raise ValueError("La publicación INEI tiene años distintos de 2018–2026")
    table = table.iloc[1:].set_axis(["ubigeo", "distrito_inei", *YEARS], axis=1)
    districts = pd.read_csv(UBIGEO_CATALOG, dtype={"ubigeo": str})
    official = table.loc[table.ubigeo.str.fullmatch(r"20\d{4}", na=False)
                         & ~table.ubigeo.str.endswith("00", na=True)]
    if len(official) != 65 or set(official.ubigeo) != set(districts.ubigeo):
        raise ValueError("Los UBIGEO INEI difieren del catálogo del estudio")
    pop = official.melt(id_vars=["ubigeo", "distrito_inei"], var_name="anio", value_name="poblacion_inei")
    if pop.duplicated(["ubigeo", "anio"]).any() or not pop.poblacion_inei.gt(0).all() or len(pop) != 585:
        raise ValueError("Población distrital incompleta, duplicada o inválida")
    if not pop.poblacion_inei.eq(np.floor(pop.poblacion_inei)).all():
        raise ValueError("La población distrital debe ser entera")
    pop = pop.astype({"anio": int, "poblacion_inei": int})
    local = pd.read_csv(archive.PANEL, dtype={"ubigeo": str}, usecols=["ubigeo", "anio", "poblacion"])
    local = local.drop_duplicates()
    if local.duplicated(["ubigeo", "anio"]).any():
        raise ValueError("La población cambia dentro de un distrito y año en el panel")
    overlap = pop.merge(local, on=["ubigeo", "anio"], validate="one_to_one")
    if len(overlap) != 520:
        raise ValueError("Solape poblacional inesperado")
    overlap = overlap.assign(igual=lambda d: d.poblacion_inei.eq(d.poblacion),
                             cambio_relativo=lambda d: d.poblacion_inei / d.poblacion - 1)
    return pop, overlap


def make_labels(main, population):
    target = main.loc[main.anio.isin(YEARS)].merge(
        population, on=["ubigeo", "anio"], how="left", validate="many_to_one")
    if target.poblacion_inei.isna().any() or target.duplicated(DATE_KEY).any():
        raise ValueError("Hay semanas sin denominador distrital")
    target = target.assign(incidencia=UNIT * target.casos_Dengue / target.poblacion_inei)
    result = {"principal": target.assign(k=count_threshold(target.umbral_brote_casos).astype(int))}
    for threshold in RATES:
        k = (threshold * target.poblacion_inei + UNIT - 1) // UNIT
        observed = UNIT * target.casos_Dengue >= threshold * target.poblacion_inei
        np.testing.assert_array_equal(observed, target.casos_Dengue.ge(k))
        result[f"incidencia_{threshold}"] = target.assign(k=k, brote=observed.astype("int8"))
    return result


def label_tables(labels, support):
    core = support[["bloque", *DATE_KEY]]
    base = labels["principal"].set_index(DATE_KEY).brote
    records, tables = [], []
    for scenario, label in labels.items():
        table = core.merge(label, on=DATE_KEY, validate="one_to_one")
        if len(table) != len(core):
            raise ValueError("Soporte desigual entre las etiquetas")
        principal = base.reindex(pd.MultiIndex.from_frame(table[DATE_KEY])).to_numpy()
        table = table.assign(agregada=table.brote.eq(1) & (principal == 0),
                             quitada=table.brote.eq(0) & (principal == 1),
                             k_1=table.k.eq(1), positivos_un_caso=table.brote.eq(1) & table.casos_Dengue.eq(1))
        summary = table.groupby("bloque", as_index=False).agg(
            filas=("brote", "size"), positivas=("brote", "sum"), agregadas=("agregada", "sum"),
            retiradas=("quitada", "sum"), semanas_k_1=("k_1", "sum"), positivos_un_caso=("positivos_un_caso", "sum"))
        records.append(summary.assign(escenario=scenario))
        tables.append(table.assign(escenario=scenario))
    return pd.concat(records, ignore_index=True), pd.concat(tables, ignore_index=True)


def predict(base, labels):
    plan = calibration_indices(base)
    lookup = pd.MultiIndex.from_frame(base[DATE_KEY])
    scenarios = {}
    for name, label in labels.items():
        table = label.set_index(DATE_KEY).reindex(lookup)
        np.testing.assert_array_equal(table.casos_Dengue, base.casos_Dengue)
        scenarios[name] = (table.k.to_numpy(), table.brote.to_numpy())
    np.testing.assert_array_equal(scenarios["principal"][1], base.brote)
    metrics, hashes = [], {}
    for name, (k, y) in scenarios.items():
        ratio = (base.persistencia.to_numpy(float) + 0.5) / (k + 0.5)
        metrics.append(evaluate(ratio / (1 + ratio), y, plan).assign(
            escenario=name, modelo="persistencia_prob", semilla=17))
    align = [*KEY, "origen_cierre", "casos_Dengue", "brote", "umbral_brote_casos"]
    for seed in protocol.SEEDS:
        for method in MODELS:
            path = archive.OUTPUT / "ajuste_simetrico" / "evaluacion" / f"{method}_s{seed}" / "predicciones.csv.gz"
            pred = pd.read_csv(path, usecols=[*align, "mu_modelo", "alpha_usada", "probabilidad_cruda"],
                               dtype={"ubigeo": str}, parse_dates=["semana_inicio", "origen_cierre"],
                               float_precision="round_trip")
            pred = pred.loc[pred.bloque.isin(BLOCKS)].reset_index(drop=True)
            pd.testing.assert_frame_equal(pred[align], base[align])
            mu = np.maximum(pred.mu_modelo.to_numpy(), 1e-9)
            alpha = pred.alpha_usada.to_numpy()
            original = negative_binomial_probability(mu, alpha, pred.umbral_brote_casos)
            np.testing.assert_allclose(original, pred.probabilidad_cruda, rtol=0, atol=1e-12)
            for name, (k, y) in scenarios.items():
                raw = nbinom.sf(k - 1, 1 / alpha, 1 / (1 + alpha * mu))
                if name == "principal":
                    np.testing.assert_allclose(raw, original, rtol=0, atol=1e-12)
                metrics.append(evaluate(raw, y, plan).assign(escenario=name, modelo=method, semilla=seed))
            hashes[str(path.relative_to(archive.ROOT))] = archive.sha256(path)
        print(f"Probabilidades recalculadas y verificadas, semilla {seed}.", flush=True)
    return pd.concat(metrics, ignore_index=True), hashes


def main():
    pop, overlap = read_population()
    confirmed, _, _, data = training_data()
    labels = make_labels(data["etiquetas"], pop)
    baseline_path = archive.OUTPUT / "comparadores_revision" / "predicciones_baselines.csv.gz"
    base = pd.read_csv(baseline_path, dtype={"ubigeo": str}, parse_dates=["semana_inicio", "origen_cierre"],
                       float_precision="round_trip")
    base = base.loc[base.bloque.isin(BLOCKS)].reset_index(drop=True)
    support = base.loc[base.horizonte.eq(4), ["bloque", *DATE_KEY]]
    if base.groupby("bloque").horizonte.nunique().ne(3).any() or support.duplicated(DATE_KEY).any():
        raise ValueError("Soporte común inválido")
    counts, panels = label_tables(labels, support)
    onsets, pairs = compare_onsets(labels, support)
    metrics, hashes = predict(base, labels)
    comparison = contrasts(metrics)
    decisive = comparison.loc[comparison.bloque.isin(DECIDING)]
    sensitivity = pd.concat([decisive.assign(sin_2026=False),
                             decisive.loc[decisive.bloque.ne("temporada_2026")].assign(sin_2026=True)])
    report = sensitivity.groupby(["escenario", "modelo", "horizonte", "sin_2026"], as_index=False).agg(
        delta_brier=("delta_brier", "mean"), delta_pct=("delta_pct", "mean"),
        temporadas=("delta_brier", "count"), mejores=("delta_brier", lambda x: int(x.lt(0).sum())))
    for filename, frame in (
        ("poblacion_inei.csv", pop), ("solape_con_panel_anterior.csv", overlap),
        ("etiquetas_por_temporada.csv", counts), ("etiquetas_comunes.csv.gz", panels),
        ("inicios_por_temporada.csv", onsets), ("inicios_emparejados.csv", pairs),
        ("metricas_probabilidades.csv", metrics), ("contrastes_por_temporada.csv", comparison),
        ("resumen_predictivo.csv", report),
    ):
        frame.to_csv(OUTPUT / filename, index=False)
    archive.write_json(OUTPUT / "manifiesto.json", {
        "poblacion": {"url": SOURCE, "sha256": archive.sha256(POPULATION), "filas": len(pop)},
        "incidencias": RATES, "soporte_calibracion": BLOCKS, "temporadas_decisivas": DECIDING,
        "filas_por_horizonte": len(support), "predicciones": {**hashes,
            str(baseline_path.relative_to(archive.ROOT)): archive.sha256(baseline_path)},
        "confirmados": confirmed["configuracion"]["insumos"], "codigo": archive.sha256(Path(__file__)),
        "protocolo": archive.sha256(Path(__file__).resolve().parents[1] / "protocolo_sensibilidad_incidencia.md"),
    })
    print(f"INEI: {len(pop)} distritos-año. Evaluación: {len(support)} filas por horizonte.", flush=True)


if __name__ == "__main__":
    main()
