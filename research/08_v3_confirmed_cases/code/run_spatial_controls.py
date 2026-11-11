"""Re-run historical b3/d3 and evaluate prespecified spatial controls."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

import run_experiment as archive
from audit_revision_inputs import BLOCKS, PARTIAL_BLOCK, cut_table
from denguekay.config.paths import SILVER_CHIRPS_PRECIP, SILVER_ENSO
from denguekay.data.calendar import mmwr_epi_week
from denguekay.data.seasons import assign_season
from denguekay.evaluation import protocol as pa
from denguekay.features import climate as cl
from denguekay.model import horizon_strategies as eh, probabilistic_output as sp
from run_chirts_resolution import GEO, OUTPUT as RESOLUTION
from run_contribution import training_data

OUTPUT = archive.OUTPUT / "controles_espaciales"
BLOCK_LIST = [*BLOCKS, PARTIAL_BLOCK]
PLACEBO_SEEDS = (20261110, 20261111, 20261112)
DECIDING = tuple(archive.rules.SEASON_2026_DECIDING)
B3 = archive.rules.STEP_B3_COLUMNS
D3 = list(cl.D3_COLUMNS)
TEMP = archive.original.b3.TEMP_COLUMN
FORM = "S4_s3"
DAY = pd.Timedelta(days=1)
STUDY = "v3_confirmados_controles_espaciales"


def weekly_fields(rain, era, lag):
    pbr = archive.original.pbr
    slots = []
    for frame, value, column in (
        (rain, "precip_total_mm", pbr.COLUMN), (era, "temp_media", TEMP),
        (era, "hum_rel_media", archive.original.pb.COLUMN),
    ):
        means = pbr.rain_by_origin_week(frame, extra_lag=lag, value=value)
        present = means.R.notna()
        allowed = means.semana_origen + (6 if lag else 20) * DAY
        if means.loc[present, "publicada_max"].gt(allowed[present]).any():
            raise ValueError(f"Fecha posterior al corte para {column}")
        slots.append(means.rename(columns={"R": column}).set_index(["ubigeo", "semana_origen"])[column])
    # Both d3 and b3 use the same underlying ERA5-Land temperature.
    limits = {name: (a + lag, b + lag) for name, (a, b) in cl.D3_WINDOWS.items()}
    d3 = cl.weather_windows(era, windows=limits).set_index(["ubigeo", "semana_origen"])
    fields = pd.concat([*slots, d3], axis=1).reset_index()
    enso = archive.original.p4.read_enso()
    dates = fields[["semana_origen"]].drop_duplicates().assign(origen_cierre=lambda d: d.semana_origen + 6*DAY)
    en = archive.original.p4.enso_at_origins(dates, enso)
    if not archive.original.p4.guard_g21(en)["pasa"]:
        raise ValueError("Niño posterior al origen")
    return fields.merge(en[["semana_origen", archive.original.b3.NINO_COLUMN]],
                        on="semana_origen", validate="many_to_one")


def weather_at(fields, origins, dates):
    keys = origins[["ubigeo"]].assign(semana_origen=np.asarray(dates))
    result = keys.merge(fields, on=["ubigeo", "semana_origen"], how="left", validate="many_to_one")
    values = result[B3 + D3]
    if values.isna().any().any() or len(values) != len(origins):
        raise ValueError(f"Campos climáticos faltantes: {values.isna().sum().to_dict()}")
    return values


def donor_schedule(origins, fields, seed):
    weeks = origins[["semana_origen"]].drop_duplicates().sort_values("semana_origen").reset_index(drop=True)
    epi = mmwr_epi_week(weeks.semana_origen)
    weeks["temporada"] = assign_season(epi.anio_epi, epi.semana_epi, 35)
    seasons = sorted(weeks.temporada.unique())
    draws = dict(zip(seasons, np.random.default_rng(seed).integers(1, 5, size=len(seasons))))
    weeks["desfase_anios"] = weeks.temporada.map(draws)
    weeks["anio_donante"] = epi.anio_epi - weeks.desfase_anios
    weeks["semana_epi_origen"] = epi.semana_epi
    grid = fields[["semana_origen"]].drop_duplicates().reset_index(drop=True)
    names = mmwr_epi_week(grid.semana_origen)
    index = pd.MultiIndex.from_arrays([names.anio_epi, names.semana_epi])
    lookup = pd.Series(grid.semana_origen.to_numpy(), index=index)
    keys = pd.MultiIndex.from_arrays([weeks.anio_donante, weeks.semana_epi_origen])
    donor = lookup.reindex(keys).reset_index(drop=True)
    missing = donor.isna()
    if missing.any():
        if not weeks.loc[missing, "semana_epi_origen"].eq(53).all():
            raise ValueError("La grilla donante tiene un hueco distinto de SE 53")
        donor.loc[missing] = lookup.reindex(
            pd.MultiIndex.from_arrays([weeks.loc[missing, "anio_donante"], np.full(missing.sum(), 52)])
        ).to_numpy()
    if not donor.lt(weeks.semana_origen).all():
        raise ValueError("El placebo accede al origen o a fechas posteriores")
    return weeks.assign(fecha_donante=donor, reemplazo_se53=missing, semilla_placebo=seed)


def prepare(inputs, geography):
    geo = pd.read_csv(geography, dtype={"ubigeo": str})
    origins = inputs["origenes"].merge(geo, on="ubigeo", validate="many_to_one")
    if len(origins) != len(inputs["origenes"]) or origins[GEO].isna().any().any():
        raise ValueError("Faltan controles geográficos")
    origins["semana_origen"] = origins.origen_cierre - 6*DAY
    origins["semana_epi_origen"] = mmwr_epi_week(origins.semana_origen).semana_epi
    rain = pd.read_csv(SILVER_CHIRPS_PRECIP, dtype={"ubigeo": str},
                       parse_dates=["semana_inicio", "fecha_disponible"])
    panel = archive.load_integrated(archive.PANEL)
    era = archive.original.era5_2026(panel).assign(fecha_disponible=lambda d: d.semana_inicio + 13*DAY)
    historic = weekly_fields(rain, era, lag=0)
    actual = weekly_fields(rain, era, lag=2)
    old = weather_at(historic, origins, origins.semana_origen)
    raw = weather_at(actual, origins, origins.semana_origen)
    for c in B3 + D3:
        if c in D3:
            np.testing.assert_allclose(origins[c], old[c], rtol=0, atol=1e-10)
        origins[f"{c}_hist"] = old[c].to_numpy()
        origins[f"{c}_obs"] = raw[c].to_numpy()
    schedules = []
    for i, seed in enumerate(PLACEBO_SEEDS, 1):
        plan = donor_schedule(origins, actual, seed)
        dates = origins.semana_origen.map(plan.set_index("semana_origen").fecha_donante)
        placebo = weather_at(actual, origins, dates)
        for field in (B3 + D3 if i == 1 else [TEMP]):
            origins[f"{field}_p{i}"] = placebo[field].to_numpy()
        schedules.append(plan)
    base, hp = archive.original.p3._config()
    geo_base = [*base, *GEO]
    b3_shared = [f"{v}_obs" for v in B3 if v != TEMP]
    arms = {
        "historia": list(base), "b3_historico": [*base, *(f"{v}_hist" for v in B3)],
        "d3_historico": [*base, *(f"{v}_hist" for v in D3)], "historia_geo": geo_base,
        "b3_obs": [*geo_base, *(f"{v}_obs" for v in B3)],
        "b3_placebo_conjunto": [*geo_base, *(f"{v}_p1" for v in B3)],
        "b3_anomalia": [*geo_base, *b3_shared, "temperatura_anomalia"],
        "d3_obs": [*geo_base, *(f"{v}_obs" for v in D3)],
        "d3_placebo": [*geo_base, *(f"{v}_p1" for v in D3)],
        **{f"b3_placebo_t{i}": [*geo_base, *(f"{v}_p{i}" if v == TEMP else f"{v}_obs" for v in B3)]
           for i in range(1, 4)},
    }
    return origins, arms, hp, pd.concat(schedules, ignore_index=True)


def anomalies(origins, cutoff):
    keys = ["ubigeo", "semana_epi_origen"]
    field = f"{TEMP}_obs"
    train = archive.original.p3._training(origins, cutoff)
    climate = train.groupby(keys)[field].mean()
    avg = climate.reindex(pd.MultiIndex.from_frame(origins[keys])).to_numpy(copy=True)
    missing = np.isnan(avg)
    if missing.any():
        if not origins.loc[missing, "semana_epi_origen"].eq(53).all():
            raise ValueError("Climatología ausente fuera de la SE 53")
        match = origins.loc[missing, keys].assign(semana_epi_origen=52)
        avg[missing] = climate.reindex(pd.MultiIndex.from_frame(match))
    if not np.isfinite(avg).all():
        raise ValueError("Climatología de entrenamiento incompleta")
    return origins.assign(temperatura_anomalia=origins[field] - avg)


def predict(inputs, origins, blocks, columns, params, seed, anomaly=False):
    args = sp.e3_parameters(params)
    model_type = sp.FORMULATIONS[FORM]["conteo"]
    margin = sp.e3_margin(origins, FORM)
    parts, fits = [], []
    for block, kind, period in blocks:
        tests, cutoff = eh._common_cutoffs(inputs["matrices"], kind, period)
        data = anomalies(origins, cutoff) if anomaly else origins
        fit = sp.fit_e3(data, cutoff, seed, FORM, columns, [], args, margin)
        first = min(t.origen_cierre.min() for t in tests.values())
        last = max(t.origen_cierre.max() for t in tests.values())
        selected = np.flatnonzero(data.origen_cierre.between(first, last))
        targets = data.iloc[selected][["ubigeo", "origen_cierre"]].copy()
        means = sp.predict_count(fit.regressor, data.iloc[selected][columns], model_type, margin[selected])
        for j, h in enumerate(archive.HORIZONS):
            test = tests[h].merge(targets.assign(mu=means[:, j]),
                                  on=["ubigeo", "origen_cierre"], how="left", validate="one_to_one")
            if test.mu.isna().any():
                raise ValueError(f"Origen faltante en {block}, h{h}")
            p = sp.negative_binomial_probability(test.mu, fit.alphas[j], test.umbral_brote_casos)
            parts.append(eh._output(test, block, test.mu, p))
        fits.append({"bloque": block, "corte": cutoff, "semilla": seed, "regimen": None,
                     "filas_entrenamiento": len(fit.train),
                     **{f"alpha_h{h}": fit.alphas[j] for j, h in enumerate(archive.HORIZONS)}})
    return pd.concat(parts, ignore_index=True), pd.DataFrame(fits)


def parity(inputs, origins, columns, hp):
    blocks = [("temporada_2008", "temporada", 2008), ("temporada_2025", "temporada", 2025)]
    a = archive.original.p3.predict_blocks_weighted(inputs["matrices"], origins, blocks, 17, columns, hp)
    b, _ = predict(inputs, origins, blocks, columns, hp, 17)
    pd.testing.assert_frame_equal(a[list(b.columns)], b, rtol=0, atol=1e-12)


def save_fit(inputs, origins, arm, columns, hp, seed, fingerprint):
    dest = OUTPUT / f"{arm}_s{seed}"
    if dest.exists():
        if json.loads((dest / "control.json").read_text())["huella"] != fingerprint:
            raise ValueError(f"Ajuste de otra configuración en {dest.name}")
        return dest
    pred, fits = predict(inputs, origins, BLOCK_LIST, columns, hp, seed, anomaly=(arm == "b3_anomalia"))
    table = archive.closure.full_table(pred, fits, arm, seed)
    guard = archive.closure.check_table(table)
    if (table.duplicated(archive.closure.KEY).any() or guard["alpha_nulos"]
            or guard["calibrada_sin_platt"] or guard["platt_diferencia_maxima"] > 1e-12
            or guard["conteo_diferencia_maxima"] > 1e-12):
        raise ValueError(f"Predicciones inválidas en {arm}, semilla {seed}")
    with TemporaryDirectory(dir=OUTPUT) as temp:
        path = Path(temp)
        table.to_csv(path / "predicciones.csv.gz", index=False)
        fits.to_csv(path / "ajustes.csv", index=False)
        archive.closure.block_metrics(table).to_csv(path / "metricas.csv", index=False)
        archive.write_json(path / "control.json", {"huella": fingerprint, "filas": len(table), **guard})
        path.rename(dest)
    return dest


def compatible_geo(arms, geography, archived, hp):
    evidence = json.loads((RESOLUTION / "resultados.json").read_text())
    if (evidence["variantes"]["epidemiologia_geografia"] != arms["historia_geo"]
            or evidence["hiperparametros"] != hp or evidence["geografia"] != archive.sha256(geography)
            or evidence["insumos_epidemiologicos"] != archived["configuracion"]["insumos"]
            or evidence["entorno"] != archive.device.xgboost_settings()):
        raise ValueError("El brazo con geografía previo difiere de este diseño")
    return [RESOLUTION / f"epidemiologia_geografia_s{s}" for s in pa.SEEDS]


def assemble(paths, inputs):
    cut, _ = cut_table(inputs)
    cut = cut.rename(columns={"filas_elegibles_calibracion": "filas_calibracion"})
    check, metrics = None, []
    for path in sorted(paths):
        frame = pd.read_csv(path / "predicciones.csv.gz", usecols=archive.OBSERVATIONS + ["filas_calibracion"],
                            dtype={"ubigeo": str}, parse_dates=["semana_inicio", "origen_cierre"])
        if check is None:
            check = frame
        else:
            pd.testing.assert_frame_equal(check, frame)
        metrics.append(pd.read_csv(path / "metricas.csv").replace({"epidemiologia_geografia": "historia_geo"}))
    test = check.merge(cut[["bloque", "horizonte", "filas_calibracion"]], on=["bloque", "horizonte"],
                       validate="many_to_one", suffixes=("", "_previstas"))
    if len(test) != 194805 or not test.filas_calibracion.eq(test.filas_calibracion_previstas).all():
        raise ValueError("Filas o calibración diferentes a los cortes auditados")
    cut.to_csv(OUTPUT / "cortes.csv", index=False)
    metrics = pd.concat(metrics, ignore_index=True)
    metrics.to_csv(OUTPUT / "metricas_por_bloque.csv", index=False)
    return metrics


def contrasts(metrics):
    values = metrics.pivot(index=["bloque", "horizonte", "semilla"], columns="variante", values="brier")
    pairs = [
        ("b3_historico", "historia"), ("d3_historico", "historia"), ("b3_historico", "d3_historico"),
        ("b3_obs", "historia_geo"), ("d3_obs", "historia_geo"), ("b3_anomalia", "historia_geo"),
        ("b3_obs", "b3_anomalia"), ("d3_obs", "d3_placebo"), ("b3_obs", "b3_placebo_conjunto"),
        *[("b3_obs", f"b3_placebo_t{i}") for i in range(1, 4)],
    ]
    detail = pd.concat([
        values.assign(delta=values[a]-values[b], relativo=(values[a]-values[b])/values[b])[["delta", "relativo"]]
        .reset_index().assign(candidata=a, referencia=b) for a,b in pairs], ignore_index=True)
    med = detail.groupby(["candidata", "referencia", "bloque", "horizonte"], as_index=False)[
        ["delta", "relativo"]].median()
    tape = med.loc[med.referencia.str.startswith("b3_placebo_t")].groupby(
        ["candidata", "bloque", "horizonte"], as_index=False)[["delta", "relativo"]].median()
    med = pd.concat([med, tape.assign(referencia="mediana_placebos_temperatura")], ignore_index=True)
    med.to_csv(OUTPUT / "contrastes_por_temporada.csv", index=False)
    chosen = med.loc[med.bloque.isin([f"temporada_{s}" for s in DECIDING])]
    summary = []
    for omit in (None, *DECIDING):
        frame = chosen if omit is None else chosen.loc[chosen.bloque.ne(f"temporada_{omit}")]
        for (a,b,h), g in frame.groupby(["candidata", "referencia", "horizonte"]):
            summary.append({"candidata": a, "referencia": b, "horizonte": h, "omitida": omit,
                            "delta": g.delta.mean(), "relativo": g.relativo.mean(),
                            "mejores": int(g.delta.lt(0).sum()), "temporadas": len(g)})
    pd.DataFrame(summary).to_csv(OUTPUT / "resumen_y_sensibilidad.csv", index=False)


def save_report(metrics, hp, quality, info):
    chosen = metrics.loc[metrics.bloque.isin([f"temporada_{s}" for s in DECIDING])]
    report = {"experimento": STUDY, "parametros": hp, "horizontes": {}}
    for h, block in chosen.groupby("horizonte"):
        vals = block.groupby(["variante", "bloque"])[["brier", "auprc"]].median().groupby("variante").mean()
        report["horizontes"][str(h)] = {"variantes": {k: {"metricas": v} for k, v in vals.to_dict("index").items()}}
    path = OUTPUT / "resultados.json"
    archive.write_json(path, info)
    info["mlflow_run"] = archive.tracking.log_report(
        STUDY, report, metrics_path=path, output_dir=OUTPUT, gold_dir=archive.GOLD, data_quality=quality,
        log_datasets=False, tracking_uri=f"sqlite:///{archive.MLFLOW_DB.as_posix()}", fingerprint=info["huella"],
        description="Réplica histórica y controles espaciales, placebos y anomalías con confirmados.",
    )
    archive.write_json(path, info)
    print("MLflow", info["mlflow_run"], flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("geografia", type=Path)
    args = parser.parse_args()
    archived, _, quality, inputs = training_data()
    origins, arms, hp, schedules = prepare(inputs, args.geografia)
    prev = compatible_geo(arms, args.geografia, archived, hp)
    parity(inputs, origins, arms["historia_geo"], hp)
    print("Alineación y paridad verificadas. Se reutilizan las cinco semillas de historia y geografía.", flush=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    schedules.to_csv(OUTPUT / "placebos_donantes.csv", index=False)
    info = {"hiperparametros": hp, "variantes": arms, "semillas": list(pa.SEEDS),
            "semillas_placebo": list(PLACEBO_SEEDS), "entorno": archive.device.xgboost_settings(),
            "geografia": archive.sha256(args.geografia), "codigo": archive.sha256(Path(__file__)),
            "protocolo": archive.sha256(Path(__file__).resolve().parents[1] / "protocolo_controles_espaciales.md"),
            "fuentes": {p.name: archive.sha256(p) for p in (SILVER_CHIRPS_PRECIP, SILVER_ENSO)},
            "epidemiologia": archived["configuracion"]["insumos"]}
    info["huella"] = hashlib.sha256(json.dumps(info, sort_keys=True).encode()).hexdigest()
    info["calidad"] = quality
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = [pool.submit(save_fit, inputs, origins, arm, columns, hp, seed, info["huella"])
                for arm, columns in arms.items() if arm != "historia_geo" for seed in pa.SEEDS]
        paths = []
        for future in as_completed(jobs):
            path = future.result()
            paths.append(path)
            print(f"{len(paths)}/{len(jobs)} {path.name}", flush=True)
    metrics = assemble([*paths, *prev], inputs)
    contrasts(metrics)
    save_report(metrics, hp, quality, info)


if __name__ == "__main__":
    main()
