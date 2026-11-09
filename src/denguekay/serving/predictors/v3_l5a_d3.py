"""Predictor ``v3_l5a_d3``: model v3 (``CONFIG_V3``), L + 5a + d3 with the hyperparameters of trial 191.

Same E3 · S4_s3 regressor as the v2 (one XGBoost ``count:poisson`` multi-output model for t+2, t+3 and t+4 from the
origin o = t − 2, ``base_margin = log(cases of the origin + 0.5)``), with three differences:

- **variables:** ``base_6`` + B3 + d3 (ERA5-Land weekly mean temperature at o and its means over o−1..o−4,
  o−5..o−8 and o−9..o−12, from ``observacion_semanal.temp_media_era5_land_c``, migration 0007_v3);
- **training outside the database** (Rosa, 2026-11-09): the package is fitted on the long series from 2000
  (``features.long_history``), because the database starts in 2017 (decision M4). The database only gives the
  inference inputs: cases since 2017 (the deepest need is the outbreak threshold, 5 years before the target), the
  ERA5-Land temperature of the 13 weeks up to o and the outbreak rule;
- **published count (5a):** ``w · μ + (1 − w) · persistence`` with ``w`` per horizon; the probability uses μ, as
  in the study (``P(cases ≥ k)`` NB2 with the in-sample α, calibrated with Platt).

The package holds ``booster.json``, ``dispersion.json`` (α), ``platt.json`` (a and b) and ``mezcla.json`` (w),
per horizon. Platt and w are fitted with the frozen out-of-sample predictions of the model/v3 Release (seed 17,
every row of an earlier block whose label closed at the cutoff), the same rule as each block of the protocol. The
case interval is the central NB2 interval around the published count; it is **not calibrated** (pending R17).
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import platform

import numpy as np
import pandas as pd
import xgboost as xgb
from xgboost import __version__ as XGBOOST_VERSION

from denguekay.data.calendar import mmwr_epi_week
from denguekay.evaluation import protocol as pa
from denguekay.features import climate as cl
from denguekay.features.onset_features import PREVIOUS_SEASON_COLUMN
from denguekay.features.outbreak_label import future_outbreak_threshold
from denguekay.model import horizon_strategies as eh
from denguekay.model import probabilistic_output as sp
from denguekay.model import v3_training as vt
from denguekay.model.device import xgboost_settings
from denguekay.model.train import MIN_OUTBREAK_CASES
from denguekay.serving.artifacts import InvalidArtifact, sha256_bytes
from denguekay.serving.package import package_code
from denguekay.serving.predictors import v2_e3_s4 as v2
from denguekay.serving.predictors.base import OOS_COLUMNS, OUTPUT_COLUMNS, BuiltPackage, InferenceUnavailable, VersionSpec

KIND = "v3_l5a_d3"
CODE_PREFIX = "v3"
TASKS, PREFIXES, ALGORITHM, HORIZONS = v2.TASKS, v2.PREFIXES, v2.ALGORITHM, v2.HORIZONS
OOS_BLOCKS = v2.OOS_BLOCKS  # the blocks whose target weeks are in the database (2022-2025)
BOOSTER, DISPERSION, PLATT, MIXTURE = "booster.json", "dispersion.json", "platt.json", "mezcla.json"
TEMPERATURE = "temp_media_era5_land"  # serving.inputs name of observacion_semanal.temp_media_era5_land_c
NO_TEMPERATURE_REASON = "Falta la temperatura de ERA5-Land de las 13 semanas hasta el origen"
NO_HISTORY_REASON = v2.NO_HISTORY_REASON
# Parity of the fit with the frozen v3: this block refitted at its cutoff must give the Release predictions.
PARITY_BLOCK = ("temporada_2026", "temporada", 2026)
PARITY_TOLERANCE = 1e-6  # G41 of study 06
IMPORTANCE = v2.IMPORTANCE


# --- serving: vector of the origin ---------------------------------------------------

def _d3(climate, origin, ubigeos):
    """d3 at the origin (indexed by ubigeo) and the districts without the 13 weeks of temperature."""
    if climate is None or TEMPERATURE not in climate:
        return pd.DataFrame(columns=cl.D3_COLUMNS), set(ubigeos)
    weeks = [origin - pd.Timedelta(weeks=k) for k in range(cl.D3_DEPTH, -1, -1)]
    grid = pd.MultiIndex.from_product([sorted(ubigeos), weeks], names=["ubigeo", "semana_inicio"]).to_frame(index=False)
    data = climate[["ubigeo", "semana_inicio", TEMPERATURE]].assign(
        ubigeo=lambda d: d.ubigeo.astype(str), semana_inicio=lambda d: pd.to_datetime(d.semana_inicio))
    data = grid.merge(data.rename(columns={TEMPERATURE: cl.D3_SOURCE}), on=["ubigeo", "semana_inicio"], how="left",
                      validate="one_to_one")
    windows = cl.weather_windows(data)
    at = windows.loc[windows.semana_origen.eq(origin)].set_index("ubigeo")[cl.D3_COLUMNS]
    missing = set(at.index[at.isna().any(axis=1)])
    return at.drop(index=list(missing)), missing


def outbreak_rule(rule):
    """``parametro_sistema.regla_brote`` in the terms of ``outbreak_label``; k needs its minimum to be 2."""
    if rule is None or int(rule.get("minimo_casos", -1)) != MIN_OUTBREAK_CASES:
        raise InferenceUnavailable("La regla de brote de parametro_sistema no corresponde a la del modelo v3")
    return {"multiplicador": float(rule["k_desviaciones"]), "anios_previos": int(rule["anios_previos"])}


def target_thresholds(cases, origin, ubigeos, rule):
    """Outbreak threshold of t + 2, t + 3 and t + 4 for each district, from the cases (not rounded)."""
    rows = []
    for h in HORIZONS:
        cal = mmwr_epi_week(pd.Series([origin + pd.Timedelta(weeks=h)])).iloc[0]
        rows += [{"ubigeo": u, "anio": int(cal.anio_epi), "semana": int(cal.semana_epi), "horizonte": h} for u in ubigeos]
    targets = pd.DataFrame(rows)
    if targets.empty:
        return pd.DataFrame(columns=list(HORIZONS))
    try:
        threshold = future_outbreak_threshold(cases, None, targets, **outbreak_rule(rule))
    except ValueError as error:
        if "Faltan años de historia" in str(error):
            raise InferenceUnavailable(NO_HISTORY_REASON) from error
        raise InferenceUnavailable(str(error)) from error
    return targets.assign(umbral=threshold).pivot(index="ubigeo", columns="horizonte", values="umbral")


def origin_vectors(inputs, cutoff, columns):
    """(vectors indexed by ubigeo with ``columns``, the persistence and the thresholds of t+2..t+4, {ubigeo: reason})."""
    cases = inputs.cases
    if cases is None or cases.empty:
        raise InferenceUnavailable("No hay observaciones cerradas al corte solicitado")
    origin = v2.origin_week(cutoff)
    vectors, reasons = v2._base_6(cases, cutoff)
    vectors = vectors.join(v2._b3(cases, origin), how="left")
    d3, no_temperature = _d3(inputs.climate, origin, list(vectors.index))
    vectors = vectors.join(d3, how="left")
    for ubigeo in sorted(no_temperature & set(vectors.index)):
        reasons.setdefault(ubigeo, NO_TEMPERATURE_REASON)
    vectors = vectors.loc[~vectors.index.isin(list(reasons))]
    no_history = vectors.index[vectors[PREVIOUS_SEASON_COLUMN].isna()]
    for ubigeo in no_history:
        reasons[ubigeo] = NO_HISTORY_REASON
    vectors = vectors.drop(index=no_history)
    if not np.isfinite(vectors[columns].to_numpy(float)).all():
        raise ValueError("El vector de la v3 contiene valores faltantes o no finitos")
    thresholds = target_thresholds(cases, origin, list(vectors.index), inputs.outbreak_rule)
    return vectors.join(thresholds), reasons


# --- serving: prediction -------------------------------------------------------------------

class Predictor:
    kind = KIND
    required_inputs = frozenset({"casos", "clima", "regla_brote"})

    def __init__(self, horizons, columns, booster, alphas, coefficients, weights, interval_level):
        self.horizons, self.columns, self.booster = tuple(horizons), list(columns), booster
        self.alphas, self.coefficients, self.weights = alphas, coefficients, weights
        self.interval_level = interval_level

    @classmethod
    def from_package(cls, package):
        horizons = package.horizons
        variables = {tuple(package.manifest["variables"][str(h)][t]) for h in horizons for t in TASKS}
        if len(variables) != 1:
            raise InvalidArtifact("Las versiones de un paquete multisalida deben compartir sus variables")
        columns = list(variables.pop())
        if BOOSTER not in package.files:
            raise InvalidArtifact(f"El paquete {package.code} no trae {BOOSTER}")
        booster = v2.load_booster(package.files[BOOSTER])
        if booster.feature_names != columns:
            raise InvalidArtifact("Las columnas del booster no coinciden con la versión")
        alphas = v2._per_horizon(v2._json_file(package, DISPERSION).get("alfa", {}), horizons, DISPERSION)
        if any(a <= 0 for a in alphas.values()):
            raise InvalidArtifact(f"{DISPERSION} trae una dispersión no positiva")
        coefficients = v2._per_horizon(v2._json_file(package, PLATT).get("coeficientes", {}), horizons, PLATT)
        if any(len(c) != 2 for c in coefficients.values()):
            raise InvalidArtifact(f"{PLATT} debe traer a y b por horizonte")
        weights = v2._per_horizon(v2._json_file(package, MIXTURE).get("w", {}), horizons, MIXTURE)
        if any(not 0 <= w <= 1 for w in weights.values()):
            raise InvalidArtifact(f"{MIXTURE} trae un peso fuera de [0, 1]")
        if package.manifest["opciones"].get("formulacion") != vt.FORMULATION:
            raise InvalidArtifact(f"El paquete v3 debe declarar la formulación {vt.FORMULATION}")
        level = package.interval_level
        if level is None or not 0 < float(level) < 1:
            raise InvalidArtifact("El paquete v3 debe declarar el nivel de su intervalo")
        return cls(horizons, columns, booster, alphas, coefficients, weights, float(level))

    def counts(self, vectors):
        """μ of t+2, t+3 and t+4 (one column per output), with the origin's ``base_margin``."""
        frame = vectors.reset_index(drop=True)
        margin = vt.margin(frame)
        output = np.asarray(self.booster.predict(xgb.DMatrix(frame[self.columns].astype(float), base_margin=margin)), float)
        output = output.reshape(len(frame), len(HORIZONS))
        if not np.isfinite(output).all() or (output < 0).any():
            raise ValueError("El modelo de conteo produjo valores inválidos")
        return output

    def predict(self, inputs, cutoff, horizons):
        for h in horizons:
            if h not in self.horizons:
                raise InferenceUnavailable(f"sin modelo para h={h}")
        vectors, reasons = origin_vectors(inputs, cutoff, self.columns)
        counts = self.counts(vectors) if len(vectors) else np.empty((0, len(HORIZONS)))
        persistence = vectors["hist_lag_a"].to_numpy(float) if len(vectors) else np.empty(0)
        parts = []
        for h in horizons:
            mu, alpha = counts[:, HORIZONS.index(h)], self.alphas[h]
            frame = pd.DataFrame({"ubigeo": list(vectors.index), "horizonte": h})
            if len(vectors):
                raw = sp.negative_binomial_probability(mu, alpha, vectors[h].to_numpy(float))
                published = vt.published_count(mu, persistence, self.weights[h])
                low, high = v2.interval(published, alpha, self.interval_level)
                frame["probabilidad_brote"] = v2.platt(raw, *self.coefficients[h])
                frame["casos_estimados"] = published
                frame["casos_intervalo_inferior"], frame["casos_intervalo_superior"] = low, high
            missing = pd.DataFrame({"ubigeo": list(reasons), "horizonte": h, "motivo_no_disponible": list(reasons.values())})
            parts += [frame, missing]
        output = pd.concat(parts, ignore_index=True).reindex(columns=OUTPUT_COLUMNS)
        return output.astype({"probabilidad_brote": float, "casos_estimados": float,
                              "casos_intervalo_inferior": float, "casos_intervalo_superior": float})


# --- package building (publication) ------------------------------------------------

@dataclass
class Prepared:
    """Inputs of the publication, in memory: the long origins, the frozen OOS predictions and the parity check."""
    configuration: dict
    origins: pd.DataFrame  # features.long_history: base_6 + B3 + d3 and the three targets, RangeIndex
    reference: pd.DataFrame  # predicciones_v3.csv.gz of the model/v3 Release, seed 17
    series: pd.DataFrame  # weekly cases and labels of the long series (lead time of the evaluation)
    hashes: dict
    sha256_dataset: str
    parity: dict
    fingerprint: str | None


def validate(horizons, options):
    """Known configuration and horizons among the three outputs, before reading any source."""
    if (options or {}).get("configuracion") != "v3":
        raise ValueError("El paquete v3_l5a_d3 sirve la configuración congelada v3 (opciones.configuracion: v3)")
    level = (options or {}).get("nivel_intervalo")
    if not isinstance(level, (int, float)) or isinstance(level, bool) or not 0 < level < 1:
        raise ValueError("opciones.nivel_intervalo debe ser una probabilidad entre 0 y 1")
    if not horizons or not set(horizons) <= set(HORIZONS):
        raise ValueError("La v3 predice h=2, 3 y 4")


def configuration():
    from denguekay.model.registry import configuration as registry_configuration

    return registry_configuration("v3")


def read_reference(path=None, seed: int = 17) -> pd.DataFrame:
    """The frozen predictions of the v3 (Release model/v3) of one seed, checked against the registry manifest."""
    from denguekay.config.paths import ROOT, V3_DATA_MANIFEST, V3_REFERENCE_PREDICTIONS

    path = V3_REFERENCE_PREDICTIONS if path is None else path
    if not path.exists():
        raise FileNotFoundError(f"Faltan las predicciones de referencia de la v3 ({path.name}): descárguelas con "
                                "python -m denguekay.data.ingestion.release_bundles")
    manifest = json.loads(V3_DATA_MANIFEST.read_text(encoding="utf-8"))
    relative = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else None
    expected = {f["ruta"]: f["sha256"] for p in manifest["paquetes"] for f in p["archivos"]}.get(relative)
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if expected is not None and actual != expected:
        raise ValueError(f"{path.name} no es el del Release model/v3 (SHA-256 distinto del manifiesto)")
    data = pd.read_csv(path, dtype={"ubigeo": "string"}, float_precision="round_trip")
    data = data[data.semilla.eq(seed)].assign(ubigeo=lambda d: d.ubigeo.astype(str),
                                              semana_inicio=lambda d: pd.to_datetime(d.semana_inicio),
                                              origen_cierre=lambda d: pd.to_datetime(d.origen_cierre))
    return data.reset_index(drop=True)


def parity(origins, matrices, reference, config, seed: int = 17) -> dict:
    """Refit ``PARITY_BLOCK`` at its cutoff and compare μ with the frozen predictions of that block."""
    block, kind, period = PARITY_BLOCK
    _, cutoff = eh._common_cutoffs(matrices, kind, period)
    fitted = vt.fit(origins, cutoff, seed, list(config["columnas"]), config["hiperparametros"])
    mu = vt.predict_counts(fitted.regressor, origins, list(config["columnas"]))
    keys = origins[["ubigeo", "origen_cierre"]].assign(origen_cierre=lambda d: pd.to_datetime(d.origen_cierre))
    worst, rows = 0.0, 0
    for step, h in enumerate(HORIZONS):
        ref = reference.loc[reference.bloque.eq(block) & reference.horizonte.eq(h), ["ubigeo", "origen_cierre", "mu_modelo"]]
        both = ref.merge(keys.assign(mu=mu[:, step]), on=["ubigeo", "origen_cierre"], how="left", validate="one_to_one")
        if both.mu.isna().any():
            raise ValueError(f"Faltan orígenes del bloque {block} en las entradas de la v3")
        worst, rows = max(worst, float(np.abs(both.mu - both.mu_modelo).max())), rows + len(both)
    setup = xgboost_settings()
    return {"bloque": block, "corte": str(pd.Timestamp(cutoff).date()), "filas": rows, "diferencia_maxima": worst,
            "tolerancia": PARITY_TOLERANCE, "pasa": worst <= PARITY_TOLERANCE, "entorno": f"device={setup['device']}"}


def prepare(horizons, options):
    """Long series and origins from the silver files (outside the database), the Release OOS and the parity.

    On the GPU the refitted parity block must reproduce the frozen predictions (the reference was recorded on
    CUDA); on the CPU XGBoost samples differently (subsample/colsample), so the result is recorded, not required.
    """
    from denguekay.config.paths import (SILVER_EPI_HISTORICAL, SILVER_INTEGRATED, SILVER_SALA,
                                        V3_REFERENCE_PREDICTIONS)
    from denguekay.data.loading import load_integrated
    from denguekay.features.long_history import long_inputs
    from denguekay.model import frozen_configs as fc

    config = configuration()
    era5 = cl.era5_land_silver()
    panel = load_integrated(SILVER_INTEGRATED)
    inputs = long_inputs(panel, era5)
    reference = read_reference()
    files = [SILVER_INTEGRATED, SILVER_EPI_HISTORICAL, SILVER_SALA, era5, V3_REFERENCE_PREDICTIONS]
    hashes = {f"v3:{p.name}": hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    dataset = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode("utf-8")).hexdigest()
    check = parity(inputs["origenes"], inputs["matrices"], reference, config)
    on_gpu = check["entorno"] == "device=cuda"
    if on_gpu and not check["pasa"]:
        raise ValueError(f"El ajuste de la v3 no reproduce sus predicciones congeladas en este entorno ({check}); "
                         "no se publica un modelo distinto del evaluado")
    fingerprint = fc.V3_FINGERPRINTS.get("device=cuda") if on_gpu and check["pasa"] else None
    return Prepared(config, inputs["origenes"], reference, inputs["serie"], hashes, dataset, check, fingerprint)


def fingerprint_parameters():
    return {"configuracion": "v3", "xgboost": XGBOOST_VERSION}


def calibration_rows(reference, horizon, cutoff):
    """Frozen OOS of ``horizon`` usable at ``cutoff``: earlier blocks, label closed at the cutoff."""
    closed = pd.Timestamp(cutoff)
    data = reference.loc[reference.horizonte.eq(horizon)]
    starts = data.groupby("bloque").semana_inicio.min()
    earlier = starts.index[starts.le(closed)]
    return data.loc[data.bloque.isin(earlier) & (data.semana_inicio + pd.Timedelta(days=6)).le(closed)]


def platt_and_mixture(reference, horizons, cutoff):
    """Platt (a, b), w and the rows used, per horizon."""
    coefficients, weights, rows = {}, {}, {}
    for h in horizons:
        data = calibration_rows(reference, h, cutoff)
        model = pa.fit_platt(data.probabilidad_cruda, data.brote)
        coefficients[h] = [float(model.coef_[0, 0]), float(model.intercept_[0])]
        weights[h] = vt.fit_persistence_weight(data.mu_modelo, data.persistencia, data.casos_Dengue)
        rows[h] = {"filas": int(len(data)), "positivos": int(data.brote.sum()),
                   "bloques": sorted(data.bloque.unique(), key=lambda b: data.loc[data.bloque.eq(b), "semana_inicio"].min())}
    return coefficients, weights, rows


def protocol_predictions(reference):
    """Frozen predictions in the protocol format: published count and raw probability (``pa.evaluate`` calibrates)."""
    columns = [*pa.PREDICTION_COLUMNS, "estacional"]
    return reference[columns].assign(casos_predichos=reference.conteo_publicado,
                                     probabilidad_brote=reference.probabilidad_cruda)


def oos_table(reference, horizons):
    """Calibrated OOS of the frozen v3 (blocks 2022–2025), one row per district and target week."""
    data = reference.loc[reference.horizonte.isin(horizons) & reference.bloque.isin(OOS_BLOCKS)].copy()
    data["orden_bloque"] = data.bloque.map({b: i for i, b in enumerate(OOS_BLOCKS)})
    data = data.sort_values(["horizonte", "orden_bloque", "ubigeo", "anio", "semana"], kind="mergesort")
    return pd.DataFrame({"horizonte": data.horizonte.astype(int), "bloque": data.bloque, "ubigeo": data.ubigeo,
                         "anio": data.anio.astype(int), "semana": data.semana.astype(int),
                         "origen_cierre": pd.to_datetime(data.origen_cierre),
                         "probabilidad_brote": data.probabilidad_calibrada.astype(float),
                         "casos_estimados": data.conteo_publicado.astype(float)}).reset_index(drop=True)[OOS_COLUMNS]


def _dumps(value):
    return (json.dumps(value, ensure_ascii=False, indent=1, sort_keys=True) + "\n").encode("utf-8")


def build(prepared, horizons, options, cutoff, trained=None):
    """``BuiltPackage`` of v3: one booster, α, Platt and w, six versions, the frozen OOS and the report."""
    config = prepared.configuration
    horizons = tuple(sorted(horizons))
    columns = list(config["columnas"])
    level = float(options["nivel_intervalo"])
    closed = pd.Timestamp(cutoff)
    fitted = vt.fit(prepared.origins, closed, config["semilla_despliegue"], columns, config["hiperparametros"])
    booster = bytes(fitted.regressor.get_booster().save_raw(raw_format="json"))
    coefficients, weights, rows = platt_and_mixture(prepared.reference, horizons, closed)
    files = {BOOSTER: booster,
             DISPERSION: _dumps({"alfa": {str(h): float(fitted.alphas[h]) for h in horizons},
                                 "metodo": "NB2 por máxima verosimilitud con las predicciones dentro de la muestra "
                                           "del ajuste de servicio (dispersión dentro_muestra)"}),
             PLATT: _dumps({"coeficientes": {str(h): coefficients[h] for h in horizons},
                            "forma": "p = expit(a · logit(clip(q, 1e-6, 1 − 1e-6)) + b)",
                            "datos": "predicciones fuera de muestra congeladas de la v3 (Release model/v3, semilla 17) "
                                     "de los bloques anteriores con la etiqueta cerrada al corte",
                            "filas": {str(h): rows[h] for h in horizons}}),
             MIXTURE: _dumps({"w": {str(h): weights[h] for h in horizons},
                              "forma": "casos = w · μ + (1 − w) · persistencia (casos de la semana de origen)",
                              "datos": "las mismas filas que Platt; w de la grilla 0,00–1,00 con el menor MAE"})}
    shap = v2.importances(fitted.regressor, fitted.train[columns])
    setup = xgboost_settings()
    reproducibility = {
        "configuracion": "CONFIG_V3 (denguekay.model.frozen_configs), ficha models/registry/v3",
        "formulacion": vt.FORMULATION, "semilla": config["semilla_despliegue"], "grupo_artefacto": None,
        "device": setup["device"], "version_xgboost": XGBOOST_VERSION,
        "plataforma": f"{platform.system()} {platform.release()} {platform.machine()}",
        "entrenamiento_inicio": str(pd.to_datetime(fitted.train.semana_inicio).min().date()),
        "entrenamiento_corte": str(closed.date()), "filas_entrenamiento": int(len(fitted.train)),
        "sha256_booster": sha256_bytes(booster), "huella_comportamiento": prepared.fingerprint,
        "paridad_con_la_v3_congelada": prepared.parity, "tipo_importancia": IMPORTANCE,
        "calibracion": "Platt y w con las OOS congeladas de la v3 (semilla 17) cerradas al corte",
        "intervalo": f"NB2 central al {level:.2f} alrededor del conteo publicado, sin calibrar",
        "sha256_entradas": dict(prepared.hashes)}
    hyperparameters = {**sp.count_objective(sp.FORMULATIONS[vt.FORMULATION]["conteo"]),
                       **eh.parameters(config["semilla_despliegue"], **sp.e3_parameters(config["hiperparametros"]))}
    code = package_code(CODE_PREFIX, files)
    reproducibility["grupo_artefacto"] = code
    table = pa.evaluate(protocol_predictions(prepared.reference), prepared.series)["metricas"]
    versions = []
    for h in horizons:
        metrics = v2.protocol_metrics(table, h)
        metrics["procedencia"] = ("Protocolo por bloques de la v3 congelada (estudio 06, semilla 17, Platt cronológico, "
                                  "conteo publicado 5a); métricas de los modelos de cada bloque, no del ajuste de servicio")
        for task in TASKS:
            data = {"algoritmo": ALGORITHM, "variables": columns, "hiperparametros": hyperparameters,
                    "metricas": metrics,
                    "umbral_probabilidad": pa.ALERT_THRESHOLD if task == "clasificacion" else None,
                    "sha256_dataset": prepared.sha256_dataset, "reproducibilidad": dict(reproducibility)}
            versions.append(VersionSpec(task, h, f"{CODE_PREFIX}-{PREFIXES[task]}-h{h}-", data, shap[h]))
    report = {"experimento": "versiones_de_servicio", "tipo_predictor": KIND, "parametros": hyperparameters,
              "version_xgboost": XGBOOST_VERSION, "fecha_corte_datos": str(closed.date()),
              "evaluacion_generada_en_esta_corrida": False,
              "nota_metricas": "Métricas del protocolo por bloques de la v3 congelada (predicciones del Release "
                               "model/v3, semilla 17); no evalúan el ajuste de servicio",
              "huella_comportamiento": prepared.fingerprint or "", "paridad": prepared.parity,
              "horizontes": {str(h): {"sha256_gold": prepared.sha256_dataset, "variantes": {}} for h in horizons}}
    return BuiltPackage(
        kind=KIND, code=code, horizons=horizons, files=files,
        variables={str(h): {task: columns for task in TASKS} for h in horizons}, interval_level=level,
        options={"configuracion": "v3", "formulacion": vt.FORMULATION, "nivel_intervalo": level},
        versions=versions, oos=oos_table(prepared.reference, horizons),
        oos_detail={"configuracion": "v3", "paquete": code,
                    "nota": "OOS del protocolo por bloques de la v3 congelada (semilla 17), calibradas y con el conteo "
                            "publicado 5a; reemplazan a las de la v2 en la serie"},
        report=report, fingerprint=prepared.fingerprint)


def build_offline(cutoff=None, horizons=HORIZONS, level: float = 0.80):
    """Build the v3 package without a database (``python -m denguekay.serving.predictors.v3_l5a_d3``): the same
    ``prepare`` and ``build`` as the publication. The default cutoff is the last week of the integrated panel,
    the one ``load_data`` loads; ``publish`` uses the cutoff of its load."""
    from denguekay.config.paths import SILVER_INTEGRATED
    from denguekay.data.loading import load_integrated

    options = {"configuracion": "v3", "nivel_intervalo": level}
    validate(horizons, options)
    if cutoff is None:
        cutoff = pd.to_datetime(load_integrated(SILVER_INTEGRATED).semana_inicio).max() + pd.Timedelta(days=6)
    prepared = prepare(horizons, options)
    return build(prepared, horizons, options, pd.Timestamp(cutoff)), prepared


def main(argv=None):
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Construye el paquete servido de la v3 sin BD y lo guarda en una carpeta.")
    parser.add_argument("--corte", help="sábado de corte (AAAA-MM-DD); por defecto, el último del integrado")
    parser.add_argument("--salida", type=Path, required=True, help="carpeta donde guardar los archivos del paquete")
    args = parser.parse_args(argv)
    built, prepared = build_offline(args.corte)
    args.salida.mkdir(parents=True, exist_ok=True)
    for name, content in built.files.items():
        (args.salida / name).write_bytes(content)
    (args.salida / "reporte.json").write_text(json.dumps(built.report, ensure_ascii=False, indent=1, default=str) + "\n",
                                              encoding="utf-8")
    print(json.dumps({"paquete": built.code, "paridad": prepared.parity, "huella": prepared.fingerprint,
                      "archivos": sorted(built.files)}, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
