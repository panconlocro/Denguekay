"""Predictor ``v0_compact_xgb``: model v0, one XGBoost booster per task and horizon (compact protocol).

It wraps the TB1 serving without changing it: the vector comes from ``build_future_rows`` (lags of cases,
calendar and log census population 2017), the classifier gives the outbreak probability and the
regressor ``log1p`` cases. The package holds the four boosters (h=2 and h=4 × task); training reuses
``train.fit_models`` with the variants of the compact protocol, and the OOS predictions come from that
protocol.
"""

from dataclasses import dataclass
import platform

import numpy as np
import pandas as pd
import xgboost as xgb
from xgboost import __version__ as XGBOOST_VERSION

from denguekay.config.paths import GOLD, SILVER_INTEGRATED
from denguekay.evaluation.compact_validation import compact_variants
from denguekay.features.gold import HORIZONS as GOLD_HORIZONS
from denguekay.features.sociodemographics import DIRECT
from denguekay.model.device import xgboost_settings
from denguekay.model.future_rows import build_future_rows
from denguekay.model.train import BASE_PARAMS, counts_from_log1p, fit_models
from denguekay.serving.artifacts import InvalidArtifact, sha256_bytes
from denguekay.serving.package import package_code
from denguekay.serving.predictors.base import OOS_COLUMNS, OUTPUT_COLUMNS, BuiltPackage, InferenceUnavailable, VersionSpec
from denguekay.serving.protocol import load_protocol, variant_metrics

KIND = "v0_compact_xgb"
CODE_PREFIX = "v0"
TASKS = ("clasificacion", "regresion")
PREFIXES = {"clasificacion": "clf", "regresion": "reg"}
ALLOWED_VARIANTS = {"base_4", "base_6", "base_6_poblacion_2017"}
OOS_BLOCKS = ("temporada_2022", "temporada_2023", "temporada_2024", "calendario_2025")
NO_VECTOR_REASON = "No hay vector de características para el distrito"


def booster_name(horizon, task):
    return f"h{horizon}_{task}.json"


# --- serving ---------------------------------------------------------------------

def reference(population):
    """2017 census reference for ``build_future_rows``.

    ``build_sociodemography`` also requires three 2017 fractions; the v0 models only use
    ``log_poblacion_censo_2017``, so those fractions are filled with 0 and do not enter the vector.
    """
    data = population.copy()
    for column in DIRECT:
        data[column] = 0.0
    return data


def future_rows(inputs, horizon, cutoff, columns):
    """Vectors of the target cutoff + h from the database inputs. Returns (rows, {ubigeo: reason})."""
    if inputs.cases.empty:
        raise InferenceUnavailable("No hay observaciones cerradas al corte solicitado")
    try:
        rows, reasons = build_future_rows(inputs.cases, horizon, columns=columns,
                                          cutoff_date=pd.Timestamp(cutoff.fecha_fin),
                                          reference=reference(inputs.population))
    except ValueError as error:
        raise InferenceUnavailable(str(error)) from error
    return rows, {m["ubigeo"]: m["motivo"] for m in reasons}


def load_booster(content):
    try:
        booster = xgb.Booster()
        booster.load_model(bytearray(content))
    except (ValueError, xgb.core.XGBoostError) as error:
        raise InvalidArtifact("El artefacto XGBoost guardado no se puede cargar") from error
    # The API may run on CPU even if the version was trained on GPU.
    booster.set_param({"device": "cpu", "nthread": 1})
    return booster


def predict_booster(booster, task, columns, vectors):
    """Evaluate exactly the columns of the version, in their order."""
    data = pd.DataFrame(vectors)
    if not columns or len(columns) != len(set(columns)):
        raise InvalidArtifact("La versión no contiene un esquema de variables válido")
    if not set(columns) <= set(data):
        raise ValueError("El vector no contiene todas las variables de la versión")
    x = data[columns].astype(float)
    if x.isna().any().any() or not np.isfinite(x.to_numpy()).all():
        raise ValueError("El vector contiene valores faltantes o no finitos")
    if booster.feature_names != columns:
        raise InvalidArtifact("Las columnas del booster no coinciden con la versión")
    output = booster.predict(xgb.DMatrix(x))
    if not np.isfinite(output).all():
        raise ValueError("El modelo produjo una predicción no finita")
    if task == "regresion":
        return counts_from_log1p(output)
    if ((output < 0) | (output > 1)).any():
        raise ValueError("El clasificador produjo probabilidades inválidas")
    return output


class Predictor:
    kind = KIND
    required_inputs = frozenset({"casos", "poblacion"})
    interval_level = None  # v0 does not estimate case intervals

    def __init__(self, horizons, variables, boosters):
        self.horizons, self.variables, self.boosters = tuple(horizons), variables, boosters

    @classmethod
    def from_package(cls, package):
        horizons = package.horizons
        variables = {h: {t: list(package.manifest["variables"][str(h)][t]) for t in TASKS} for h in horizons}
        boosters = {}
        for h in horizons:
            for task in TASKS:
                name = booster_name(h, task)
                if name not in package.files:
                    raise InvalidArtifact(f"El paquete {package.code} no trae {name}")
                boosters[h, task] = load_booster(package.files[name])
        return cls(horizons, variables, boosters)

    def predict(self, inputs, cutoff, horizons):
        parts = []
        for h in horizons:
            if h not in self.horizons:
                raise InferenceUnavailable(f"sin modelo para h={h}")
            columns = sorted({c for t in TASKS for c in self.variables[h][t]})
            rows, reasons = future_rows(inputs, h, cutoff, columns)
            frame = pd.DataFrame({"ubigeo": list(rows.ubigeo), "horizonte": h})
            if not rows.empty:
                frame["probabilidad_brote"] = list(map(float, predict_booster(
                    self.boosters[h, "clasificacion"], "clasificacion", self.variables[h]["clasificacion"], rows)))
                frame["casos_estimados"] = list(map(float, predict_booster(
                    self.boosters[h, "regresion"], "regresion", self.variables[h]["regresion"], rows)))
            missing = pd.DataFrame({"ubigeo": list(reasons), "horizonte": h, "motivo_no_disponible": list(reasons.values())})
            parts += [frame, missing]
        output = pd.concat(parts, ignore_index=True).reindex(columns=OUTPUT_COLUMNS)
        return output.astype({"probabilidad_brote": float, "casos_estimados": float,
                              "casos_intervalo_inferior": float, "casos_intervalo_superior": float})


# --- package building (publication) ------------------------------------------------

@dataclass
class PreparedVersion:
    data: dict
    artifact: bytes
    importances: list


@dataclass
class Prepared:
    protocol: object
    hashes: dict


def validate(horizons, options):
    """Fail on unknown variants or horizons without gold, before reading any source."""
    variants = (options or {}).get("variantes")
    if not isinstance(variants, dict) or set(variants) != set(TASKS) or not set(variants.values()) <= ALLOWED_VARIANTS:
        raise ValueError("Las variantes deben pertenecer al protocolo compacto")
    for h in horizons:
        if h not in GOLD_HORIZONS:
            raise ValueError(f"No hay gold ni contrato de modelado para horizonte {h}; no se inventarán predicciones")
        if not (GOLD / f"{SILVER_INTEGRATED.stem}_h{h}_gold.csv").exists():
            raise ValueError(f"Falta el gold para horizonte {h}")


def prepare(horizons, options):
    protocol = load_protocol(horizons, options["variantes"])
    return Prepared(protocol, dict(protocol.hashes))


def fingerprint_parameters():
    return {"parametros": BASE_PARAMS, "xgboost": XGBOOST_VERSION}


def _partition(metrics):
    fields = ("bloque", "tipo", "corte_ajuste", "primera_semana_objetivo", "ultima_semana_objetivo",
              "n_entrenamiento", "n_prueba", "calibracion")
    return {name: {c: f[c] for c in fields if c in f} for name, f in metrics["bloques"].items()}


def train_service_versions(protocol, horizons, variants, cutoff):
    """Use every label closed at the cutoff and the same functions/hyperparameters.

    ``fit_models`` returns both targets; the component selected by configuration is kept, without
    changing the training logic.
    """
    versions = {}
    for h in horizons:
        train = closed_training(protocol, h, cutoff)
        pairs = {name: fit_models(train, compact_variants(h)[name]) for name in set(variants.values())}
        for task, name in variants.items():
            booster = pairs[name][1 if task == "clasificacion" else 0].get_booster()
            versions[h, task] = service_version(protocol, h, task, name, cutoff, train,
                                                bytes(booster.save_raw(raw_format="json")), booster)
    return versions


def closed_training(protocol, horizon, cutoff):
    """Rows of the serving fit: every label closed at the cutoff."""
    source = protocol.data[horizon]
    train = source.loc[(source.semana_inicio + pd.Timedelta(days=6)).le(pd.Timestamp(cutoff))].copy()
    if train.empty or train.brote.nunique() != 2:
        raise ValueError("El ajuste final requiere etiquetas cerradas y ambas clases")
    return train


def service_version(protocol, horizon, task, name, cutoff, train, artifact, booster):
    """``PreparedVersion`` of one task: protocol metadata, the booster bytes and its gain importances."""
    evaluation = protocol.report
    metrics = variant_metrics(protocol, horizon, name)
    data = {
        "algoritmo": "xgboost",
        "variables": compact_variants(horizon)[name], "hiperparametros": dict(BASE_PARAMS),
        "metricas": metrics,
        "umbral_probabilidad": (metrics["bloques"]["calendario_2025"]["clasificacion"]["umbral_probabilidad"]
                                if task == "clasificacion" else None),
        "sha256_dataset": evaluation["horizontes"][str(horizon)]["sha256_gold"],
        "reproducibilidad": {
            "variante": name, "device": xgboost_settings()["device"],
            "version_xgboost": XGBOOST_VERSION,
            "plataforma": f"{platform.system()} {platform.release()} {platform.machine()}",
            "entrenamiento_inicio": str(train.semana_inicio.min().date()),
            "entrenamiento_corte": str(cutoff),
            "sha256_manifiesto_gold": evaluation["sha256_manifest_gold"],
            "sha256_booster": sha256_bytes(artifact),
            "particion_temporal": {"bloques": _partition(metrics),
                                   "criterio_seleccion": evaluation["criterio_seleccion"],
                                   "nota_2024": evaluation["nota_2024"],
                                   "alcance": "Servicio: ajuste con etiquetas cerradas al corte"}},
    }
    gains = booster.get_score(importance_type="gain")
    importances = [{"variable": c, "importancia": float(g), "rango": span}
                   for span, (c, g) in enumerate(sorted(gains.items(), key=lambda x: (-x[1], x[0])), 1)]
    return PreparedVersion(data, artifact, importances)


def versions_from_boosters(protocol, horizons, variants, cutoff, artifacts):
    """Same versions as ``train_service_versions`` from already trained boosters, without fitting.

    ``artifacts`` = {(horizon, task): booster JSON bytes}. XGBoost does not train bit for bit the same
    on every operating system, so the parity of the serving freezes the boosters instead of refitting.
    """
    versions = {}
    for h in horizons:
        train = closed_training(protocol, h, cutoff)
        for task, name in variants.items():
            artifact = artifacts[h, task]
            versions[h, task] = service_version(protocol, h, task, name, cutoff, train, artifact,
                                                load_booster(artifact))
    return versions


def service_report(trained, protocol, cutoff):
    """Standard shape for MLflow; the time metrics are imported, not from this fit."""
    report = {"experimento": "versiones_de_servicio", "parametros": dict(BASE_PARAMS),
              "version_xgboost": XGBOOST_VERSION, "fecha_corte_datos": str(cutoff),
              "device_evaluacion_importada": protocol.report["parametros"]["device"],
              "evaluacion_generada_en_esta_corrida": False,
              "nota_metricas": "Las métricas temporales importadas se adjuntan como evidencia histórica; no son una evaluación del ajuste final",
              "sha256_manifest_gold": protocol.report["sha256_manifest_gold"], "horizontes": {}}
    for (h, task), prepared in trained.items():
        data = prepared.data
        block = report["horizontes"].setdefault(str(h), {
            "archivo_gold": protocol.report["horizontes"][str(h)]["archivo_gold"],
            "sha256_gold": data["sha256_dataset"], "variantes": {}})
        block["variantes"][f"{data['reproducibilidad']['variante']}_{task}"] = {
            "columnas": data["variables"], "tipo_modelo": task, "corte_ajuste_servicio": str(cutoff),
            "umbral_probabilidad": data["umbral_probabilidad"], "sha256_artefacto": sha256_bytes(prepared.artifact)}
    return report


def oos_table(protocol, horizons, variants):
    """Out-of-sample predictions of the protocol, one row per district-week, in the import order."""
    rows = []
    for h in horizons:
        # load_protocol already checked each block's coverage against gold.
        present = set(protocol.predictions.loc[protocol.predictions.horizonte.eq(h), "bloque"])
        for block in [b for b in OOS_BLOCKS if b in present]:
            base = protocol.predictions.loc[protocol.predictions.horizonte.eq(h) & protocol.predictions.bloque.eq(block)]
            cls = base.loc[base.variante.eq(variants["clasificacion"])].set_index(["ubigeo", "anio", "semana"]).sort_index()
            reg = base.loc[base.variante.eq(variants["regresion"])].set_index(["ubigeo", "anio", "semana"]).sort_index()
            if cls.empty or not cls.index.equals(reg.index):
                raise ValueError(f"Clasificación y regresión OOS no comparten semanas en {block} h={h}")
            for (ubigeo, year, week), row in cls.iterrows():
                rows.append({"horizonte": h, "bloque": block, "ubigeo": ubigeo, "anio": int(year), "semana": int(week),
                             "origen_cierre": pd.Timestamp(row.origen_cierre),
                             "probabilidad_brote": float(row.probabilidad_brote),
                             "casos_estimados": float(reg.loc[(ubigeo, year, week), "casos_predichos"])})
    return pd.DataFrame(rows, columns=OOS_COLUMNS)


def build(prepared, horizons, options, cutoff, trained=None):
    """``BuiltPackage`` of v0: four boosters, their versions, the protocol's OOS and the MLflow report."""
    variants = options["variantes"]
    protocol = prepared.protocol
    trained = trained or train_service_versions(protocol, horizons, variants, cutoff)
    files = {booster_name(h, task): p.artifact for (h, task), p in trained.items()}
    versions = [VersionSpec(task, h, f"{PREFIXES[task]}-h{h}-v", dict(p.data), p.importances)
                for (h, task), p in trained.items()]
    variables = {str(h): {task: list(trained[h, task].data["variables"]) for task in TASKS} for h in horizons}
    return BuiltPackage(
        kind=KIND, code=package_code(CODE_PREFIX, files), horizons=tuple(horizons), files=files,
        variables=variables, interval_level=None, options={"variantes": dict(variants)}, versions=versions,
        oos=oos_table(protocol, horizons, variants),
        oos_detail={"variantes": dict(variants), "sha256_protocolo": protocol.hashes,
                    "nota": "Predicciones fuera de muestra del protocolo temporal; sin booster conservado"},
        report=service_report(trained, protocol, cutoff))
