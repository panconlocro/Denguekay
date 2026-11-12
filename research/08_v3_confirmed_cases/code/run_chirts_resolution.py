"""Evaluate native and coarsened CHIRTS on the same confirmed-case folds."""

import argparse
import ast
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

import run_experiment as archive
from assemble_chirts_history import COLS, OUTPUT as WEATHER_OUTPUT
from assemble_era5_candidate import OUTPUT as ERA5_OUTPUT
from audit_revision_inputs import BLOCKS, PARTIAL_BLOCK, cut_table
from denguekay.config.paths import SILVER_CHIRPS_PRECIP, SILVER_ENSO
from denguekay.evaluation import protocol
from run_contribution import training_data

OUTPUT = WEATHER_OUTPUT / "pronosticos"
WEEKLY = WEATHER_OUTPUT / "chirts_resoluciones_semanal.csv.gz"
ERA5 = ERA5_OUTPUT / "era5_piura_poligono_semanal.csv.gz"
BLOCK_LIST = [*BLOCKS, PARTIAL_BLOCK]
WINDOW, LAG = 5, 2
GEO = ["lat", "lon", "elevacion_dem90"]
WEATHER = ["lluvia_media5", "humedad_media5", "nino12_anom_media3"]
SEASONS = tuple(archive.rules.SEASON_2026_DECIDING)
STUDY = "v3_confirmados_resolucion_chirts"


def read_weekly(path, availability=None):
    columns = ["semana_inicio", *([availability] if availability else [])]
    return pd.read_csv(path, dtype={"ubigeo": str}, parse_dates=columns)


def add_weekly(origins, data, fields, availability):
    key = origins[["ubigeo", "origen_cierre"]].assign(
        semana_origen=lambda d: d.origen_cierre - pd.Timedelta(days=6))
    out = origins.copy()
    src = data.rename(columns={availability: "fecha_disponible"})
    for field, name in fields.items():
        roll = archive.original.pbr.rain_by_origin_week(src, extra_lag=LAG, window=WINDOW, value=field)
        joined = key.merge(roll, on=["ubigeo", "semana_origen"], how="left", validate="many_to_one")
        used = joined.R.notna()
        if (joined.loc[used, "publicada_max"].isna().any()
                or joined.loc[used, "publicada_max"].gt(joined.loc[used, "origen_cierre"]).any()
                or not joined.loc[used, "ultima_semana_usada"].eq(
                    joined.loc[used, "semana_origen"] - pd.Timedelta(weeks=LAG)).all()):
            raise ValueError(f"Disponibilidad o rezago incorrectos para {name}")
        out[name] = joined.R.to_numpy()
    return out


def prepare(inputs, geography):
    geo = pd.read_csv(geography, dtype={"ubigeo": str})
    if len(geo) != 65 or geo[GEO].isna().any().any() or geo.ubigeo.duplicated().any():
        raise ValueError("Coordenadas o elevación distrital inválidas")
    origins = inputs["origenes"].merge(geo, on="ubigeo", how="left", validate="many_to_one")
    rain = read_weekly(SILVER_CHIRPS_PRECIP, "fecha_disponible")
    origins = add_weekly(origins, rain, {"precip_total_mm": WEATHER[0]}, "fecha_disponible")
    era5 = read_weekly(ERA5, "fecha_disponible_proxy")
    origins = add_weekly(origins, era5, {"hr_poblacion": WEATHER[1]}, "fecha_disponible_proxy")
    chirts = read_weekly(WEEKLY).assign(fecha_chirts=lambda d: d.semana_inicio + pd.Timedelta(days=11))
    origins = add_weekly(origins, chirts, {field: field for field in COLS}, "fecha_chirts")
    origins = archive.original.p4.enso_at_origins(origins, archive.original.p4.read_enso())
    if origins[GEO + WEATHER].isna().any().any() or not archive.original.p4.guard_g21(origins)["pasa"]:
        raise ValueError("Faltan entradas climáticas comunes o hay Niño posterior al origen")
    if not origins[list(COLS)].isna().eq(origins[COLS[0]].isna(), axis=0).all().all():
        raise ValueError("Los brazos de temperatura tienen soporte distinto")
    for stat in ("tmax", "tmin"):
        origins[f"delta_{stat}"] = origins[f"{stat}_fina"] - origins[f"{stat}_gruesa"]
    base, hp = archive.original.p3._config()
    static = [*base, *GEO]
    shared = [*static, *WEATHER]
    arms = {
        "epidemiologia_geografia": static, "clima_sin_temperatura": shared,
        "chirts_025": [*shared, "tmax_gruesa", "tmin_gruesa"],
        "chirts_005": [*shared, "tmax_fina", "tmin_fina"],
        "chirts_025_mas_delta": [*shared, "tmax_gruesa", "tmin_gruesa", "delta_tmax", "delta_tmin"],
    }
    return origins, arms, hp


def fit_one(inputs, origins, arm, columns, hp, seed, fingerprint):
    dest = OUTPUT / f"{arm}_s{seed}"
    if dest.exists():
        old = json.loads((dest / "control.json").read_text())
        if old["huella"] != fingerprint:
            raise ValueError(f"El checkpoint {dest.name} corresponde a otra configuración")
        return dest
    pred = archive.original.p3.predict_blocks_weighted(inputs["matrices"], origins, BLOCK_LIST, seed, columns, hp)
    fits = pred.attrs.pop("ajustes").assign(semilla=seed)
    table = archive.closure.full_table(pred, fits, arm, seed)
    check = archive.closure.check_table(table)
    if (table.duplicated(archive.closure.KEY).any() or check["calibrada_sin_platt"]
            or check["alpha_nulos"] or check["platt_diferencia_maxima"] > 1e-12
            or check["conteo_diferencia_maxima"] > 1e-12):
        raise ValueError(f"Predicciones inválidas: {arm}, semilla {seed}")
    with TemporaryDirectory(dir=OUTPUT) as tmp:
        path = Path(tmp)
        table.to_csv(path / "predicciones.csv.gz", index=False)
        fits.to_csv(path / "ajustes.csv", index=False)
        archive.closure.block_metrics(table).to_csv(path / "metricas.csv", index=False)
        archive.write_json(path / "control.json", {"huella": fingerprint, "filas": len(table), **check})
        path.rename(dest)
    return dest


def summarize(paths, arms, inputs, hp, quality, details):
    observations, metrics = None, []
    cuts, _ = cut_table(inputs)
    cuts = cuts.rename(columns={"filas_elegibles_calibracion": "filas_calibracion"})
    for path in paths:
        obs = pd.read_csv(path / "predicciones.csv.gz", usecols=archive.OBSERVATIONS + ["filas_calibracion"],
                          dtype={"ubigeo": str}, parse_dates=["semana_inicio", "origen_cierre"])
        if observations is None:
            observations = obs
        else:
            pd.testing.assert_frame_equal(observations, obs)
        metrics.append(pd.read_csv(path / "metricas.csv"))
    close = cuts.dropna(subset=["ultima_etiqueta_calibracion"])
    if close.ultima_etiqueta_calibracion.gt(close.primer_origen).any():
        raise ValueError("Una etiqueta de calibración es posterior al origen")
    labels = ["bloque", "horizonte"]
    check = observations.merge(cuts[labels + ["filas_calibracion"]], on=labels, suffixes=("", "_corte"),
                               validate="many_to_one")
    if not check.filas_calibracion.eq(check.filas_calibracion_corte).all():
        raise ValueError("La calibración archivada difiere del corte de etiquetas")
    if len(observations) != 194805:
        raise ValueError("La evaluación difiere del calendario de 64 935 filas por horizonte")
    metrics = pd.concat(metrics, ignore_index=True)
    metrics.to_csv(OUTPUT / "metricas_por_bloque.csv", index=False)
    cuts.to_csv(OUTPUT / "cortes.csv", index=False)
    w = metrics.pivot(index=["bloque", "horizonte", "semilla"], columns="variante", values="brier")
    pairs = [
        ("chirts_005", "chirts_025"), ("chirts_025_mas_delta", "chirts_025"),
        ("chirts_005", "clima_sin_temperatura"), ("chirts_025", "clima_sin_temperatura"),
        ("chirts_005", "epidemiologia_geografia"), ("clima_sin_temperatura", "epidemiologia_geografia"),
    ]
    contrast = pd.concat([
        w.assign(delta=w[a]-w[b], delta_relativo=(w[a]-w[b])/w[b])[["delta", "delta_relativo"]]
        .reset_index().assign(candidata=a, referencia=b) for a,b in pairs], ignore_index=True)
    paired = contrast.groupby(["candidata", "referencia", "bloque", "horizonte"], as_index=False)[
        ["delta", "delta_relativo"]].median()
    paired.to_csv(OUTPUT / "diferencias_por_temporada.csv", index=False)
    chosen = paired.loc[paired.bloque.isin([f"temporada_{s}" for s in SEASONS])]
    summary = []
    for omitted in (None, *SEASONS):
        data = chosen if omitted is None else chosen.loc[chosen.bloque.ne(f"temporada_{omitted}")]
        for (a,b,h), group in data.groupby(["candidata", "referencia", "horizonte"]):
            summary.append({
                "candidata": a, "referencia": b, "horizonte": h, "temporada_omitida": omitted,
                "temporadas": len(group), "brier_delta": group.delta.mean(),
                "brier_delta_relativo": group.delta_relativo.mean(), "favorables": int(group.delta.lt(0).sum()),
            })
    pd.DataFrame(summary).to_csv(OUTPUT / "resumen_y_sensibilidad.csv", index=False)
    report = {"experimento": STUDY, "parametros": hp, "horizontes": {}}
    regular = metrics.loc[metrics.bloque.isin([f"temporada_{s}" for s in SEASONS])]
    for h in archive.HORIZONS:
        by_arm = regular.loc[regular.horizonte.eq(h)].groupby(["variante", "bloque"])[
            ["brier", "auprc"]].median().groupby("variante").mean().to_dict("index")
        report["horizontes"][str(h)] = {"variantes": {a: {"metricas": by_arm[a]} for a in arms}}
    manifest = OUTPUT / "resultados.json"
    details.update(filas_por_variante_semilla=len(observations), calidad_datos=quality)
    archive.write_json(manifest, details)
    details["mlflow_run"] = archive.tracking.log_report(
        STUDY, report, metrics_path=manifest, output_dir=OUTPUT, gold_dir=archive.GOLD, data_quality=quality,
        log_datasets=False, tracking_uri=f"sqlite:///{archive.MLFLOW_DB.as_posix()}", fingerprint=details["huella"],
        description="Contraste pareado de CHIRTS a 0,05 y 0,25 grados con confirmados, geografía y calendario común.",
    )
    archive.write_json(manifest, details)
    print(f"Resultados: {OUTPUT} | MLflow {details['mlflow_run']}", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("geografia", type=Path)
    parser.add_argument("--codigo-ajustes", type=Path, help="Snapshot anterior con idénticas funciones de ajuste")
    args = parser.parse_args()
    archived, _, quality, inputs = training_data()
    origins, arms, hp = prepare(inputs, args.geografia)
    device = archive.device.xgboost_settings()
    details = {
        "semillas": list(protocol.SEEDS), "variantes": arms, "hiperparametros": hp, "entorno": device,
        "insumos_epidemiologicos": archived["configuracion"]["insumos"],
        "insumos_climaticos": {p.name: archive.sha256(p) for p in (WEEKLY, ERA5, SILVER_CHIRPS_PRECIP, SILVER_ENSO)},
        "geografia": archive.sha256(args.geografia), "codigo": archive.sha256(Path(__file__)),
        "protocolo": archive.sha256(Path(__file__).resolve().parents[1] / "protocolo_resolucion_chirts.md"),
        "origenes_sin_temperatura": int(origins[COLS[0]].isna().sum()),
    }
    if args.codigo_ajustes:
        names = {"read_weekly", "add_weekly", "prepare", "fit_one"}

        def functions(path):
            return {node.name: ast.dump(node) for node in ast.parse(path.read_text()).body
                    if isinstance(node, ast.FunctionDef) and node.name in names}

        if functions(Path(__file__)) != functions(args.codigo_ajustes):
            raise ValueError("El snapshot no conserva las funciones de ajuste")
        details["codigo"] = archive.sha256(args.codigo_ajustes)
    details["huella"] = hashlib.sha256(json.dumps(details, sort_keys=True).encode()).hexdigest()
    details["codigo_resumen"] = archive.sha256(Path(__file__))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    print(f"GE y alineación verificados: {len(origins)} orígenes, "
          f"{details['origenes_sin_temperatura']} sin temperatura, {len(arms)} variantes", flush=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = [pool.submit(fit_one, inputs, origins, arm, columns, hp, seed, details["huella"])
                for arm, columns in arms.items() for seed in protocol.SEEDS]
        paths = []
        for task in as_completed(jobs):
            path = task.result()
            paths.append(path)
            print(f"Ajustado {path.name} ({len(paths)}/{len(jobs)})", flush=True)
    summarize(sorted(paths), arms, inputs, hp, quality, details)


if __name__ == "__main__":
    main()
