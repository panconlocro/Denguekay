"""Cross training history and calibration history on archived common-season forecasts."""

from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import average_precision_score

import run_spatial_controls as spatial
from run_contribution import block_folds, calibrate

archive = spatial.archive
TUNING = archive.OUTPUT / "ajuste_simetrico"
OUTPUT = archive.OUTPUT / "historia_calibracion_comun"
STUDY = "v3_confirmados_historia_calibracion_comun"
GEO = spatial.RESOLUTION.parent / "insumos" / "geografia_distritos.csv"
BLOCKS = spatial.BLOCK_LIST[:-1]
MAIN = [f"temporada_{s}" for s in spatial.DECIDING if s != 2010]
FIELDS = ["brier", "ap", "log_score", "descalibracion", "discriminacion", "incertidumbre"]


def decompose(y, probability):
    p = np.asarray(probability, float)
    y = np.asarray(y, float)
    isotonic = IsotonicRegression(y_min=0, y_max=1).fit_transform(p, y)
    brier = float(np.mean((p - y) ** 2))
    reference = float(np.mean((isotonic - y) ** 2))
    uncertainty = float(y.mean() * (1 - y.mean()))
    if reference > min(brier, uncertainty) + 1e-12:
        raise ValueError("La descomposición isotónica produjo un componente negativo")
    bounded = np.clip(p, 1e-6, 1 - 1e-6)
    return {
        "brier": brier, "ap": float(average_precision_score(y, p)),
        "log_score": float(-np.mean(y * np.log(bounded) + (1 - y) * np.log1p(-bounded))),
        "descalibracion": brier - reference, "discriminacion": uncertainty - reference,
        "incertidumbre": uncertainty,
    }


def short_forecasts(inputs, origins, columns, hp, seed):
    out, diagnostics = [], []
    for block in BLOCKS:
        _, cutoff = spatial.eh._common_cutoffs(inputs["matrices"], *block[1:])
        start = cutoff - pd.DateOffset(years=3)
        shortened = origins.loc[origins.origen_cierre.ge(start)].reset_index(drop=True)
        prediction, audit = spatial.predict(inputs, shortened, [block], columns, hp, seed)
        training = archive.original.p3._training(shortened, cutoff)
        if (len(training) != audit.filas_entrenamiento.iloc[0]
                or training.origen_cierre.min() < start
                or (training.semana_inicio_h4.max() + pd.Timedelta(days=6)) > cutoff):
            raise ValueError(f"Ventana de entrenamiento inválida: {block[0]}")
        out.append(prediction)
        diagnostics.append(audit.assign(ventana_inicio=start, primer_origen=training.origen_cierre.min(),
                                        ultimo_cierre=training.semana_inicio_h4.max() + pd.Timedelta(days=6)))
    return pd.concat(out, ignore_index=True), pd.concat(diagnostics, ignore_index=True)


def analyze(seed, inputs, origins, columns, hp, fingerprint):
    source = TUNING / "evaluacion" / f"historia_geo_s{seed}"
    if json.loads((source / "control.json").read_text())["huella"] != fingerprint:
        raise ValueError(f"Archivo de predicciones incompatibles para semilla {seed}")
    full = pd.read_csv(source / "predicciones.csv.gz", dtype={"ubigeo": str},
                       parse_dates=["semana_inicio", "origen_cierre"], float_precision="round_trip",
                       usecols=[*archive.OBSERVATIONS, "probabilidad_cruda", "probabilidad_calibrada"])
    full = full.loc[full.bloque.str.startswith("temporada_")].reset_index(drop=True)
    short, fit = short_forecasts(inputs, origins, columns, hp, seed)
    key = archive.OBSERVATIONS
    pd.testing.assert_frame_equal(full[key], short[key], check_dtype=False)
    if len(full) != 193440 or full.duplicated(archive.closure.KEY).any():
        raise ValueError(f"Soporte regular inesperado para semilla {seed}")
    data = full[key].assign(corto=short.probabilidad_brote, largo=full.probabilidad_cruda)
    columns = ["corto", "largo"]
    recent, audit_recent = calibrate(data, columns, window=2)
    expanded, audit_expanded = calibrate(data, columns)
    np.testing.assert_allclose(expanded.largo, full.probabilidad_calibrada, atol=1e-12, rtol=0, equal_nan=True)
    audits = pd.concat([audit_recent.assign(historia_calibracion="dos_temporadas"),
                        audit_expanded.assign(historia_calibracion="expansiva")], ignore_index=True).assign(semilla=seed)
    if not audits.ultimo_cierre.le(audits.corte).all():
        raise ValueError("Una etiqueta de calibración cerró después del origen")
    pairs = audits.pivot(index=["bloque", "horizonte", "historia_calibracion"], columns="serie", values="filas")
    if not pairs.corto.eq(pairs.largo).all():
        raise ValueError("El calibrador usa distintas filas entre los dos entrenamientos")
    records = []
    for h, block, test, available, _ in block_folds(data):
        if test.brote.nunique() != 2:
            raise ValueError(f"Bloque sin dos clases: {block}, h{h}")
        for kind, pred in (("cruda", data), ("dos_temporadas", recent), ("expansiva", expanded)):
            for training in columns:
                p = pred.loc[test.index, training]
                if p.isna().all():
                    continue
                if not p.between(0, 1).all():
                    raise ValueError(f"Probabilidades fuera de soporte en {block}, h{h}, {kind}")
                records.append({
                    "bloque": block, "horizonte": h, "semilla": seed, "entrenamiento": training,
                    "calibracion": kind, "temporadas_previas": available.bloque.nunique(), "filas": len(test),
                    "positivos": int(test.brote.sum()), **decompose(test.brote, p),
                })
    traces = data[key].assign(
        corto_cruda=data.corto, largo_cruda=data.largo, corto_dos_temporadas=recent.corto,
        largo_dos_temporadas=recent.largo, corto_expansiva=expanded.corto, largo_expansiva=expanded.largo,
    )
    traces.to_csv(OUTPUT / f"predicciones_s{seed}.csv.gz", index=False)
    print(f"Semilla {seed}: {len(fit)} ajustes con ventana móvil; calibración expansiva reproducida.", flush=True)
    return pd.DataFrame(records), audits, fit


def contrasts(metrics):
    index = ["bloque", "horizonte", "semilla"]
    values = metrics.pivot(index=index, columns=["entrenamiento", "calibracion"], values=FIELDS)
    pairs = [
        ("entrenamiento_crudo", ("largo", "cruda"), ("corto", "cruda")),
        ("entrenamiento_con_dos_temporadas", ("largo", "dos_temporadas"), ("corto", "dos_temporadas")),
        ("entrenamiento_con_calibracion_expansiva", ("largo", "expansiva"), ("corto", "expansiva")),
        ("calibracion_en_entrenamiento_corto", ("corto", "expansiva"), ("corto", "dos_temporadas")),
        ("calibracion_en_entrenamiento_largo", ("largo", "expansiva"), ("largo", "dos_temporadas")),
    ]
    diffs = []
    for name, a, b in pairs:
        delta = pd.DataFrame({f: values[(f, *a)] - values[(f, *b)] for f in FIELDS})
        delta["brier_relativo"] = delta.brier / values[("brier", *b)]
        diffs.append(delta.dropna().reset_index().assign(contraste=name))
    detail = pd.concat(diffs, ignore_index=True)
    interaction = (detail.loc[detail.contraste.eq("calibracion_en_entrenamiento_largo")].set_index(index)[FIELDS]
                   - detail.loc[detail.contraste.eq("calibracion_en_entrenamiento_corto")].set_index(index)[FIELDS])
    detail = pd.concat([detail, interaction.reset_index().assign(contraste="interaccion_entrenamiento_calibracion")],
                       ignore_index=True)
    detail.to_csv(OUTPUT / "diferencias_pareadas_por_semilla.csv", index=False)
    medians = detail.groupby(["bloque", "horizonte", "contraste"], as_index=False)[[*FIELDS, "brier_relativo"]].median()
    medians.to_csv(OUTPUT / "diferencias_pareadas_por_temporada.csv", index=False)
    primary = medians.loc[medians.bloque.isin(MAIN)]
    summaries = []
    for name, data in (("principal", primary), ("sin_2026", primary.loc[primary.bloque.ne("temporada_2026")])):
        table = data.groupby(["horizonte", "contraste"], as_index=False).agg(
            **{f: (f, "mean") for f in [*FIELDS, "brier_relativo"]},
            temporadas=("brier", "size"), mejora_brier=("brier", lambda x: int(x.lt(0).sum())),
            ap_cambio_pequeno=("ap", lambda x: int(x.abs().le(0.01).sum())),
        )
        summaries.append(table.assign(conjunto=name))
    pd.concat(summaries, ignore_index=True).to_csv(OUTPUT / "resumen_contrastes.csv", index=False)


def plot_components(metrics):
    block = metrics.loc[metrics.horizonte.eq(4) & metrics.bloque.isin(MAIN) & metrics.calibracion.ne("cruda")]
    raw = block.groupby(["bloque", "entrenamiento", "calibracion"], as_index=False)[
        ["brier", "descalibracion", "discriminacion"]].median()
    fig, axes = plt.subplots(1, 3, figsize=(11, 4), sharey=True, layout="constrained")
    for ax, (metric, title) in zip(axes, [("brier", "Brier"), ("descalibracion", "Descalibración"),
                                         ("discriminacion", "Discriminación")], strict=True):
        for (training, calibration), group in raw.groupby(["entrenamiento", "calibracion"]):
            ax.plot(group[metric], group.bloque.str[-4:], marker="o",
                    color="#087E83" if training == "largo" else "#BF602B",
                    ls="-" if calibration == "expansiva" else "--",
                    label=f"Entrenamiento {training} · Platt {calibration.replace('_', ' ')}")
        ax.set_title(title)
        ax.grid(alpha=0.22)
        ax.invert_yaxis()
    axes[0].legend(loc="best", fontsize=7)
    fig.supxlabel("Componente del pronóstico a cuatro semanas")
    fig.savefig(OUTPUT / "componentes_h4.png", dpi=180)
    fig.savefig(OUTPUT / "componentes_h4.pdf")
    plt.close(fig)


def plot_reliability():
    """Pooled h4 calibration diagram over the main evaluation seasons."""
    histories = ("dos_temporadas", "expansiva")
    grid = np.linspace(0.005, 0.995, 199)
    curves = {}
    for seed in spatial.pa.SEEDS:
        pred = pd.read_csv(OUTPUT / f"predicciones_s{seed}.csv.gz")
        pred = pred.loc[pred.horizonte.eq(4) & pred.bloque.isin(MAIN)]
        for training in ("corto", "largo"):
            for calibration in histories:
                p = pred[f"{training}_{calibration}"]
                fit = IsotonicRegression(y_min=0, y_max=1, out_of_bounds="nan").fit(p, pred.brote)
                curves.setdefault((training, calibration), []).append(fit.predict(grid))
    fig, axes = plt.subplots(1, 2, figsize=(8.5, 4.3), sharex=True, sharey=True, layout="constrained")
    for ax, training in zip(axes, ("corto", "largo"), strict=True):
        ax.plot([0, 1], [0, 1], color="#6A7075", ls=":", label="Calibración ideal")
        for calibration, color in zip(histories, ("#BF602B", "#087E83"), strict=True):
            values = np.asarray(curves[(training, calibration)])
            supported = np.isfinite(values).sum(axis=0) >= 3
            label = "Dos temporadas" if calibration == "dos_temporadas" else "Todas las temporadas previas"
            ax.step(grid[supported], np.nanmedian(values[:, supported], axis=0), color=color, label=label)
        ax.set(xlim=(0, 1), ylim=(0, 1), title=f"Entrenamiento {training}", aspect="equal")
        ax.grid(alpha=0.2)
    axes[0].legend(loc="upper left", fontsize=8)
    fig.supxlabel("Probabilidad pronosticada a cuatro semanas")
    fig.supylabel("Frecuencia observada de brote")
    fig.savefig(OUTPUT / "confiabilidad_h4.png", dpi=180)
    fig.savefig(OUTPUT / "confiabilidad_h4.pdf")
    plt.close(fig)


def main():
    previous, _, quality, inputs = spatial.training_data()
    design = json.loads((TUNING / "diseno.json").read_text())
    result = json.loads((TUNING / "resultados.json").read_text())
    if (design["epidemiologia"] != previous["configuracion"]["insumos"]
            or design["geografia"] != archive.sha256(GEO)
            or design["entorno"] != archive.device.xgboost_settings()
            or design["huella"] != result["huella"]):
        raise ValueError("El experimento usa entradas o entorno distintos del modelo archivado")
    geo = pd.read_csv(GEO, dtype={"ubigeo": str})
    origins = inputs["origenes"].merge(geo, on="ubigeo", validate="many_to_one")
    if len(origins) != len(inputs["origenes"]) or origins[spatial.GEO].isna().any().any():
        raise ValueError("Geografía incompleta")
    columns = design["variantes"]["historia_geo"]
    hp = result["hiperparametros"]["historia_geo"]
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=4) as executor:
        jobs = [executor.submit(analyze, seed, inputs, origins, columns, hp, design["huella"]) for seed in spatial.pa.SEEDS]
        results = [job.result() for job in as_completed(jobs)]
    metrics, audits, fit = [pd.concat(parts, ignore_index=True) for parts in zip(*results, strict=True)]
    metrics.to_csv(OUTPUT / "metricas_por_bloque_y_semilla.csv", index=False)
    audits.to_csv(OUTPUT / "cortes_calibracion.csv", index=False)
    fit.to_csv(OUTPUT / "cortes_entrenamiento_movil.csv", index=False)
    contrasts(metrics)
    plot_components(metrics)
    plot_reliability()
    selected = metrics.loc[metrics.bloque.isin(MAIN)]
    report = {"experimento": STUDY, "parametros": hp, "horizontes": {}}
    for h, group in selected.groupby("horizonte"):
        vals = (group.groupby(["bloque", "entrenamiento", "calibracion"])[FIELDS].median()
                .groupby(["entrenamiento", "calibracion"]).mean())
        report["horizontes"][str(h)] = {"variantes": {
            f"{training}_{calibration}": {"metricas": v}
            for (training, calibration), v in vals.to_dict("index").items()}}
    info = {
        "modelo_archivado": design["huella"], "periodo_movil_anios": 3, "semillas": list(spatial.pa.SEEDS),
        "codigo": archive.sha256(Path(__file__)),
        "protocolo": archive.sha256(Path(__file__).resolve().parents[1] / "protocolo_historia_calibracion_comun.md"),
    }
    fingerprint = hashlib.sha256(json.dumps(info, sort_keys=True).encode()).hexdigest()
    path = OUTPUT / "manifiesto.json"
    archive.write_json(path, {"huella": fingerprint, **info})
    run = archive.tracking.log_report(
        STUDY, report, metrics_path=path, output_dir=OUTPUT, gold_dir=archive.GOLD, data_quality=quality,
        log_datasets=False, tracking_uri=f"sqlite:///{archive.MLFLOW_DB.as_posix()}", fingerprint=fingerprint,
        description="Factorial retrospectivo de historia de entrenamiento y de calibración en el calendario común.",
    )
    archive.write_json(path, {"huella": fingerprint, "mlflow_run": run, **info})


if __name__ == "__main__":
    main()
