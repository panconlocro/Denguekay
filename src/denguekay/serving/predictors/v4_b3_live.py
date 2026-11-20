"""Publish frozen B3 boosters and obtain their origin vectors from the operational database."""

from dataclasses import dataclass, replace
from io import BytesIO
import json
from pathlib import PurePosixPath, PureWindowsPath

import numpy as np
import pandas as pd
from xgboost import XGBRegressor

from denguekay.config.paths import ROOT, V4_DATA_MANIFEST, V4_FROZEN, V4_GEOGRAPHY
from denguekay.features.b3 import GEO, climate_vector
from denguekay.serving.artifacts import InvalidArtifact, json_fingerprint, sha256_bytes
from denguekay.serving.package import package_code
from denguekay.serving.predictors import v2_e3_s4 as v2, v3_l5a_d3 as v3, v4_b3_obs as frozen
from denguekay.serving.predictors.base import BuiltPackage, InferenceUnavailable
from denguekay.serving.v4_load import prepare_load, source_hashes

KIND = "v4_b3_live"
GEOGRAPHY = "geografia.csv"
LOG_DATASETS = False  # the frozen CSV and sources are tracked by their manifest, without fitting again
RULE = {"minimo_casos": 2, "anios_previos": 5, "k_desviaciones": 1.5}


def _geography(data):
    geo = pd.read_csv(BytesIO(data), dtype={"ubigeo": str}, float_precision="round_trip").set_index(
        "ubigeo")
    if (len(geo) != 65 or not geo.index.is_unique or not geo.index.str.fullmatch(r"20[0-9]{4}").all()
            or not set(GEO) <= set(geo) or not np.isfinite(geo[list(GEO)].to_numpy(float)).all()):
        raise InvalidArtifact("Geografía incompleta del paquete V4")
    return geo[list(GEO)]


class Predictor(frozen.Predictor):
    kind = KIND
    required_inputs = frozenset({"casos_confirmados", "clima_b3", "nino12", "regla_brote"})

    @classmethod
    def from_package(cls, package):
        config = v2._json_file(package, frozen.PARAMETERS)
        predictor = cls._from_parameters(package, config)
        predictor.geography = _geography(package.files[GEOGRAPHY])
        return predictor

    def vectors(self, inputs, cutoff):
        cases = inputs.cases
        if cases is None or cases.empty:
            raise InferenceUnavailable("No hay casos confirmados al corte solicitado")
        if inputs.outbreak_rule is None or any(inputs.outbreak_rule.get(k) != v for k, v in RULE.items()):
            raise InferenceUnavailable("La regla de brote en la BD difiere del paquete congelado V4")
        origin = v2.origin_week(cutoff)
        base, reasons = v2._base_6(cases, cutoff)
        climate = climate_vector(inputs.climate, inputs.nino12, cutoff.fecha_fin, base.index)
        vectors = base.join(v2._b3(cases, origin)).join(self.geography).join(climate)
        missing = vectors.index[~np.isfinite(vectors[self.columns].to_numpy(float)).all(axis=1)]
        for ubigeo in missing:
            reasons.setdefault(ubigeo, "Falta historial, geografía o clima disponible al corte de V4")
        vectors = vectors.drop(index=missing)
        for ubigeo in self.geography.index.difference(base.index):
            reasons.setdefault(ubigeo, "Falta historial confirmado al corte de V4")
        if vectors.empty:
            return vectors, reasons
        thresholds = v3.target_thresholds(cases, origin, list(vectors.index), inputs.outbreak_rule)
        return vectors.join(thresholds), reasons


@dataclass
class Prepared:
    package: BuiltPackage
    hashes: dict


def validate(horizons, options):
    if horizons != v3.HORIZONS:
        raise ValueError("El paquete congelado V4 requiere los horizontes 2, 3 y 4")
    if set(options) - {"sala", "era5_land", "chirps", "nino12", "semanas_provisionales", "perfil_datos", "paquete_dir"}:
        raise ValueError("La publicación V4 solo admite opciones de procedencia de insumos")
    if options.get("perfil_datos", "release") not in ("release", "fuentes"):
        raise ValueError("perfil_datos debe ser release o fuentes")
    trailing = options.get("semanas_provisionales", 2)
    if type(trailing) is not int or trailing < 0:
        raise ValueError("semanas_provisionales debe ser un entero no negativo")
    for key in {"sala", "era5_land", "chirps", "nino12", "paquete_dir"} & options.keys():
        if not isinstance(options[key], str) or not options[key]:
            raise ValueError(f"La ruta de {key} debe ser relativa al repositorio")
        text = options[key]
        # Absolute in either convention: a path valid on Windows must not slip through on Linux or macOS.
        if (PurePosixPath(text).is_absolute() or PureWindowsPath(text).is_absolute() or PureWindowsPath(text).drive
                or ".." in PurePosixPath(text.replace("\\", "/")).parts):
            raise ValueError(f"La ruta de {key} debe ser relativa al repositorio")


def fingerprint_parameters():
    return {"modelo_congelado": "v4-b3", "inferencia": KIND}


def package_folder(options):
    """The package in use: the frozen V4 of the Release, or the refit one that ``paquete_dir`` names."""
    return ROOT / options["paquete_dir"] if options.get("paquete_dir") else V4_FROZEN


IMPORTANCE_NOTE = ("Clasificador y regresor del mismo horizonte comparten booster; sus importancias son idénticas")
PARTITION_SCHEME = ("Entrenamiento con las etiquetas cerradas al corte del paquete; calibración (Platt y peso de la "
                    "mezcla) con las predicciones fuera de muestra cerradas a ese corte; prueba fuera de muestra por "
                    "temporada: cada temporada se ajusta una vez, en su primer origen, y se evalúa en sus semanas "
                    "objetivo")
NO_INTERVAL = ("Sin intervalo de casos: el paquete V4 no declara nivel de intervalo; publica el conteo mezclado y la "
               "probabilidad calibrada")


def training_importances(folder, config, booster):
    """SHAP importances per horizon and the facts of the matrix the booster was fitted with.

    A refit package carries them (``refit_v4.IMPORTANCES_FILE``, hash-checked with the rest of the package). The
    frozen V4 of the Release does not, so its training matrix is rebuilt from the Release inputs and verified
    (``refit_v4.frozen_training_matrix``); no other matrix, and not the booster's gain, is ever used."""
    from denguekay.model import refit_v4 as refit

    if refit.IMPORTANCES_FILE in config["archivos"]:
        payload = refit.read_importances(folder, config)
        return {**payload, "origen": f"Archivo {refit.IMPORTANCES_FILE} del paquete: |SHAP| medio sobre la matriz "
                                     f"del ajuste ({payload['filas']} filas)"}
    if folder != V4_FROZEN:
        raise ValueError(f"El paquete de reajuste no trae {refit.IMPORTANCES_FILE}; reajústalo de nuevo "
                         "(python -m denguekay.model.refit_v4)")
    regressor = XGBRegressor()
    regressor.load_model(bytearray(booster))
    train = refit.frozen_training_matrix(config, regressor)
    payload = refit.importances_payload(regressor, train, config["columnas"][refit.ARM])
    return {**payload, "importancias": {int(h): rows for h, rows in payload["importancias"].items()},
            "origen": f"|SHAP| medio sobre la matriz de entrenamiento reconstruida con los insumos del Release "
                      f"({payload['filas']} filas; filas, columnas y dispersiones NB2 verificadas contra el paquete)"}


def reproducibility(origin, config, importances, partition, horizon):
    """What ``version_modelo.reproducibilidad`` carries for one horizon, besides the package's origin."""
    seed = config["semilla_demo"]
    record = config["modelos"][f"b3_obs_s{seed}"]["por_horizonte"][str(horizon)]
    platt = record["platt"]
    return {
        **origin,
        "entrenamiento_inicio": importances["inicio"], "filas_entrenamiento": importances["filas"],
        "calibracion": ("Platt y peso de la mezcla del conteo por horizonte, ajustados al congelar el modelo con las "
                        f"predicciones fuera de muestra de b3_obs (semilla {seed}) cuya etiqueta cerró al "
                        f"{platt['ultimo_cierre']} ({platt['filas']} filas): "
                        f"h={horizon}, a={platt['a']:.4f}, b={platt['b']:.4f}, w={record['peso_modelo']:.2f}"),
        "calibracion_parametros": {"platt": {key: platt[key] for key in ("a", "b", "filas", "ultimo_cierre")},
                                   "peso_modelo": record["peso_modelo"]},
        "intervalo": NO_INTERVAL,
        "tipo_importancia": v2.IMPORTANCE, "nota_importancias": IMPORTANCE_NOTE,
        "origen_importancias": importances["origen"],
        "particion_temporal": {"esquema": PARTITION_SCHEME, "bloques": partition[horizon]},
    }


def prepare(horizons, options):
    from denguekay.serving.demo_b3_v4 import (
        build_package, joined_predictions, prepare_observations, read_bundle, temporal_partition)

    folder = package_folder(options)
    manifest_path = folder / "paquete.json"
    config, digest = read_bundle(folder)   # every file is checked against the package's own manifest
    if folder == V4_FROZEN:   # the frozen package must be exactly the one of the Release
        reference = json.loads(V4_DATA_MANIFEST.read_text(encoding="utf-8"))
        release = {file["ruta"]: file["sha256"] for item in reference["paquetes"] for file in item["archivos"]}
        if digest != release[manifest_path.relative_to(ROOT).as_posix()]:
            raise ValueError("El paquete V4 local difiere del manifiesto del release")
    geography = V4_GEOGRAPHY.read_bytes()
    geo_digest = sha256_bytes(geography)
    if geo_digest != config["fuentes"]["geografia"]:
        raise ValueError("La geografía local difiere de la V4 congelada")
    _geography(geography)
    _, observations = prepare_observations(folder, config, digest)
    archived = build_package(folder, config, digest, observations)
    # Metadata only: nothing below touches the booster, the parameters or the forecasts.
    importances = training_importances(folder, config, archived.files[frozen.BOOSTER])
    partition = temporal_partition(*joined_predictions(folder, observations, config["semilla_demo"]))
    files = {name: data for name, data in archived.files.items() if name != frozen.SNAPSHOT}
    files[GEOGRAPHY] = geography
    origin = {**archived.oos_detail, "alcance": "V4 B3 para pronósticos con observaciones de Piura al corte"}
    versions = [replace(spec, importances=importances["importancias"][spec.horizonte],
                        data={**spec.data, "reproducibilidad": reproducibility(origin, config, importances, partition,
                                                                               spec.horizonte)})
                for spec in archived.versions]
    report = {**archived.report, **origin, "experimento": "serving_v4_b3"}
    # The manifest hash identifies a version (``save_versions`` reuses the one with the same package and dataset), and
    # the files alone do not change when only this metadata does: its hash goes into the options, so a republication
    # with new importances or partition registers new versions instead of silently keeping the old ones.
    metadata = json_fingerprint([[spec.tarea, spec.horizonte, spec.data["reproducibilidad"], spec.importances]
                                 for spec in versions])
    built = replace(archived, kind=KIND, code=package_code("v4", files), files=files, versions=versions,
                    options={**archived.options, "huella_metadatos": metadata}, oos_detail=origin, report=report)
    return Prepared(built, {manifest_path.relative_to(ROOT).as_posix(): digest,
                            V4_GEOGRAPHY.relative_to(ROOT).as_posix(): geo_digest})


def build(prepared, horizons, options, cutoff):
    return prepared.package
