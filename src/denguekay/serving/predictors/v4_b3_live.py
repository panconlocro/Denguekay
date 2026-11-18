"""Publish frozen B3 boosters and obtain their origin vectors from the operational database."""

from dataclasses import dataclass, replace
from io import BytesIO
import json
from pathlib import PurePosixPath, PureWindowsPath

import numpy as np
import pandas as pd

from denguekay.config.paths import ROOT, V4_DATA_MANIFEST, V4_FROZEN, V4_GEOGRAPHY
from denguekay.features.b3 import GEO, climate_vector
from denguekay.serving.artifacts import InvalidArtifact, sha256_bytes
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


def prepare(horizons, options):
    from denguekay.serving.demo_b3_v4 import read_bundle, prepare_observations, build_package

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
    files = {name: data for name, data in archived.files.items() if name != frozen.SNAPSHOT}
    files[GEOGRAPHY] = geography
    origin = {**archived.oos_detail, "alcance": "V4 B3 para pronósticos con observaciones de Piura al corte"}
    versions = [replace(spec, data={**spec.data, "reproducibilidad": origin}) for spec in archived.versions]
    report = {**archived.report, **origin, "experimento": "serving_v4_b3"}
    built = replace(archived, kind=KIND, code=package_code("v4", files), files=files, versions=versions,
                    oos_detail=origin, report=report)
    return Prepared(built, {manifest_path.relative_to(ROOT).as_posix(): digest,
                            V4_GEOGRAPHY.relative_to(ROOT).as_posix(): geo_digest})


def build(prepared, horizons, options, cutoff):
    return prepared.package
