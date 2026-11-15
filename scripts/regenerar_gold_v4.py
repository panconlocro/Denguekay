"""Regenera el gold del ajuste congelado B3 (model/v4) con los insumos del release.

Ejecutar desde la raíz del checkout después de instalar requirements.txt con
constraints.txt y extraer datos_v4.zip y modelo_v4.zip.
"""

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import json
import os
import sys

os.environ["DENGUEKAY_XGB_DEVICE"] = "cpu"
os.environ["DENGUEKAY_XGB_NJOBS"] = "2"
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")

import numpy as np
import pandas as pd

from denguekay.config.paths import GOLD, MODELS, RESEARCH, ROOT, SILVER_CHIRPS_PRECIP
from denguekay.data.calendar import mmwr_epi_week
from denguekay.data.validation.gx_quality import validate_modeling_inputs
from denguekay.features.long_history import long_inputs, OUTBREAK_RULE
from denguekay.features.model_input_contract import audit_handoff

def main():
    study = RESEARCH / "08_v3_confirmed_cases"
    sys.path.insert(0, str(study / "code"))
    import freeze_v4 as freeze

    archive = freeze.archive
    spatial = freeze.spatial
    day = pd.Timedelta(days=1)
    manifest_path = study / "manifiesto_b3_v4.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    columns = manifest["columnas"]["b3_obs"]
    horizons = manifest["horizontes"]
    cutoff = pd.Timestamp(manifest["corte"])
    package = MODELS / "experimentos/mejora_modelo/v4_b3_confirmados"
    geography = spatial.RESOLUTION.parent / "insumos/geografia_distritos.csv"
    output = GOLD

    source_paths = {"geografia": geography}
    for name, expected in manifest["fuentes"].items():
        path = source_paths.get(name) or (ROOT / name if name.startswith("data/") else SILVER_CHIRPS_PRECIP.parent / name)
        if archive.sha256(path) != expected:
            raise ValueError(f"Insumo distinto de la V4 congelada: {name}")
        source_paths[name] = path

    audit_handoff(silver_path=archive.PANEL, history_path=archive.HISTORY)
    with TemporaryDirectory(prefix="dk-v4-gx-") as gx:
        quality = validate_modeling_inputs(silver_path=archive.PANEL, gx_directory=Path(gx))
    if not quality["exito"]:
        raise ValueError("Great Expectations rechazó los insumos")

    panel = archive.load_integrated(archive.PANEL)
    sala = freeze.read(archive.SALA)
    if not sala.tipo_dx.eq("C").all():
        raise ValueError("La Sala contiene categorías distintas de confirmados")
    inputs = long_inputs(panel, archive.ERA5, sala=sala, history_path=archive.HISTORY)
    if inputs["ultima_semana"] + 6 * day != cutoff:
        raise ValueError("El último cierre de la serie no coincide con V4")

    geo = freeze.read(geography)
    rain = freeze.read(SILVER_CHIRPS_PRECIP, ("semana_inicio", "fecha_disponible"))
    era = archive.original.era5_2026(panel).assign(fecha_disponible=lambda d: d.semana_inicio + 13 * day)
    weather = spatial.weekly_fields(rain, era, lag=2)
    climate_columns = {col: f"{col}_obs" for col in spatial.B3}
    observed_weather = weather[["ubigeo", "semana_origen", *spatial.B3]].rename(columns=climate_columns)
    origins = (inputs["origenes"].assign(semana_origen=lambda d: d.origen_cierre - 6 * day)
               .merge(geo[["ubigeo", *spatial.GEO]], on="ubigeo", validate="many_to_one")
               .merge(observed_weather, on=["ubigeo", "semana_origen"], how="left", validate="many_to_one"))
    targets = [f"semana_inicio_h{h}" for h in horizons]
    complete = origins.dropna(subset=targets)
    train = complete.loc[(complete[targets[-1]] + 6 * day).le(cutoff)].copy()
    expected_rows = {value["filas_entrenamiento"] for value in manifest["modelos"].values()}
    if expected_rows != {len(train)} or not np.isfinite(train[columns].to_numpy(float)).all():
        raise ValueError("El tamaño o la integridad de las variables difiere del ajuste V4")

    # Anchor the multi-output rows on the h2 target, the same convention as E3.
    key = ["ubigeo", "anio", "semana"]
    calendar = mmwr_epi_week(train.semana_inicio)
    if (train.duplicated(key).any() or train.ubigeo.nunique() != len(geo)
            or not train.ubigeo.str.fullmatch(r"\d{6}").all()
            or not calendar.anio_epi.eq(train.anio).all()
            or not calendar.semana_epi.eq(train.semana).all()
            or not train.semana_inicio.eq(train.semana_inicio_h2).all()):
        raise ValueError("Llaves o calendario MMWR inconsistentes")

    cases = inputs["casos"].set_index(["ubigeo", "semana_inicio"])["casos_Dengue"]
    labels = inputs["etiquetas"].set_index(["ubigeo", "semana_inicio"])
    origin_cases = cases.reindex(pd.MultiIndex.from_frame(train[["ubigeo", "semana_origen"]]))
    np.testing.assert_array_equal(train.hist_lag_a.to_numpy(), origin_cases.to_numpy())

    out = train[[*key, "semana_inicio", "origen_inicio", "origen_cierre", *columns]].copy()
    for h in horizons:
        target = f"semana_inicio_h{h}"
        if not train[target].eq(train.origen_cierre - 6 * day + pd.Timedelta(weeks=h)).all():
            raise ValueError(f"Desalineación de fechas en h{h}")
        reference = labels.reindex(pd.MultiIndex.from_frame(train[["ubigeo", target]]))
        for field in ("casos_Dengue", "brote"):
            np.testing.assert_array_equal(train[f"{field}_h{h}"].to_numpy(), reference[field].to_numpy())
        out[target] = train[target]
        out[f"casos_Dengue_h{h}"] = train[f"casos_Dengue_h{h}"].astype("int64")
        out[f"umbral_brote_casos_h{h}"] = reference.umbral_brote_casos.to_numpy()
        out[f"brote_h{h}"] = train[f"brote_h{h}"].astype("int8")
        expected_label = (out[f"casos_Dengue_h{h}"].gt(out[f"umbral_brote_casos_h{h}"])
                          & out[f"casos_Dengue_h{h}"].ge(OUTBREAK_RULE["minimo_casos"]))
        np.testing.assert_array_equal(out[f"brote_h{h}"].to_numpy(), expected_label.to_numpy())

    # Rebuild the independent inference vector with the same inputs and compare to the frozen package.
    origin = cutoff - 6 * day
    past = inputs["casos"].loc[inputs["casos"].semana_inicio.le(origin)]
    base, missing = freeze.v2._base_6(past, SimpleNamespace(fecha_fin=cutoff.date()))
    if missing:
        raise ValueError(f"Historias del último origen incompletas: {missing}")
    recent = (base.join(freeze.v2._b3(past, origin)).join(geo.set_index("ubigeo")[spatial.GEO])
              .join(observed_weather.loc[observed_weather.semana_origen.eq(origin)].set_index("ubigeo")[list(climate_columns.values())]))
    thresholds = freeze.v3.target_thresholds(past, origin, list(recent.index), manifest["regla_brote"])
    recent = recent[columns].join(thresholds.rename(columns={h: f"umbral_h{h}" for h in horizons}))
    frozen = freeze.read(package / "origen.csv").set_index("ubigeo")
    if archive.sha256(package / "origen.csv") != manifest["archivos"]["origen.csv"]:
        raise ValueError("El origen de la demo no coincide con el manifiesto")
    pd.testing.assert_frame_equal(recent.sort_index(), frozen.sort_index(), check_dtype=False, rtol=0, atol=1e-12)

    print(f"{len(out)} filas de entrenamiento y {len(columns)} predictores; origen de la demo validado", flush=True)
    output.mkdir(parents=True, exist_ok=True)
    csv_name = "piura_confirmados_v4_gold.csv"
    manifest_name = "manifest_v4.json"
    with TemporaryDirectory(prefix=".v4-gold-", dir=output) as folder:
        temp = Path(folder)
        csv_path = temp / csv_name
        out.to_csv(csv_path, index=False, date_format="%Y-%m-%d", lineterminator="\n")
        dates = ["semana_inicio", "origen_inicio", "origen_cierre", *targets]
        exported = freeze.read(csv_path, dates)
        pd.testing.assert_frame_equal(out.reset_index(drop=True), exported, check_dtype=False, check_exact=True)
        for col in columns:
            exported[col] = exported[col].astype(train[col].dtype)
        pd.testing.assert_frame_equal(train[columns].reset_index(drop=True), exported[columns], check_exact=True)

        # Refit from disk to verify that the export carries the exact inputs of the archived boosters.
        matches = {}
        for arm, predictors in manifest["columnas"].items():
            seed = manifest["semilla_demo"]
            fit = freeze.sp.fit_e3(exported, cutoff, seed, manifest["formulacion"], predictors, [],
                                  freeze.sp.e3_parameters(manifest["hiperparametros"]),
                                  freeze.sp.e3_margin(exported, manifest["formulacion"]))
            booster_name = f"{arm}_s{seed}.ubj"
            booster = temp / booster_name
            fit.regressor.save_model(booster)
            expected = manifest["archivos"][booster_name]
            if archive.sha256(booster) != expected:
                reference_booster = freeze.XGBRegressor()
                reference_booster.load_model(package / booster_name)
                print("Tipos calculados:", fit.regressor.get_booster().feature_types, flush=True)
                print("Tipos de la referencia:", reference_booster.get_booster().feature_types, flush=True)
                print("Entorno:", freeze.archive.device.xgboost_settings(), flush=True)
                raise ValueError(f"El ajuste desde el CSV difiere del booster congelado: {booster_name}")
            matches[booster_name] = expected
            print(f"Paridad SHA-256: {booster_name}", flush=True)

        metadata = {
            "version_modelo": "v4-b3",
            "alcance": "Matriz de entrenamiento del ajuste final congelado con casos confirmados de Piura",
            "formulacion": manifest["formulacion"],
            "archivo": csv_name,
            "sha256": archive.sha256(csv_path),
            "llave": key,
            "semana_inicio": "Inicio de la semana objetivo de h2. Las tres salidas comparten un mismo origen.",
            "corte_etiquetas": cutoff.date().isoformat(),
            "filas": len(out),
            "distritos": int(out.ubigeo.nunique()),
            "semanas_objetivo_h2": int(out.semana_inicio.nunique()),
            "horizontes": horizons,
            "rango_por_horizonte": {
                str(h): {"desde": out[f"semana_inicio_h{h}"].min().date().isoformat(),
                         "hasta": out[f"semana_inicio_h{h}"].max().date().isoformat(),
                         "casos": int(out[f"casos_Dengue_h{h}"].sum()),
                         "semanas_distritales_elevadas": int(out[f"brote_h{h}"].sum())}
                for h in horizons
            },
            "columnas": list(out.columns),
            "predictores": manifest["columnas"],
            "tipos_predictores": {col: str(train[col].dtype) for col in columns},
            "regla_brote": manifest["regla_brote"],
            "rezago_ventana_meteorologica_semanas": 2,
            "semanas_provisionales_excluidas": inputs["semanas_provisionales"],
            "manifiesto_fijado": {"ruta": str(manifest_path.relative_to(ROOT)), "sha256": archive.sha256(manifest_path)},
            "fuentes_verificadas": {
                name: {"ruta": str(source_paths[name].relative_to(ROOT)), "sha256": digest}
                for name, digest in manifest["fuentes"].items()
            },
            "derivacion": [str(p.relative_to(ROOT)) for p in
                           (study / "code/freeze_v4.py", study / "code/run_spatial_controls.py")],
            "validacion": {
                "great_expectations_insumos": {name: suite["evaluadas"] for name, suite in quality["suites"].items()},
                "paridad_vector_demo_distritos": len(recent),
                "paridad_boosters_desde_csv": matches,
            }
        }
        archive.write_json(temp / manifest_name, metadata)
        for name in (csv_name, manifest_name):
            target = output / name
            if target.exists() and archive.sha256(target) != archive.sha256(temp / name):
                raise FileExistsError(f"Ya existe una versión distinta de {target}")
        for name in (csv_name, manifest_name):
            os.replace(temp / name, output / name)
    print(json.dumps({"filas": metadata["filas"], "distritos": metadata["distritos"],
                      "rango_por_horizonte": metadata["rango_por_horizonte"], "csv": str(output / csv_name),
                      "manifest": str(output / manifest_name)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
