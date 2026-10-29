"""Predictor ``v2_e3_s4``: model v2 (``CONFIG_2026``), E3 multi-output with formulation S4_s3.

One XGBoost regressor (``count:poisson``, ``multi_output_tree``) predicts the cases of t+2, t+3 and t+4
from the origin o = t − 2, with ``base_margin = log(cases of the origin + 0.5)``. The outbreak
probability is ``P(cases ≥ k)`` of a negative binomial NB2 with the in-sample α of each output and
``k = max(⌊threshold⌋ + 1, 2)``, calibrated with Platt (stored as coefficients). The case interval is the
central NB2 interval at the package level; it is **not calibrated**: Platt only corrects the probability.

The vector of each district is built in memory from the database with the modelling functions:
``base_6`` (``build_future_rows`` with h=2), B3 (``onsets.own_history`` and
``onset_features.previous_season``), A3 (``build_observed_climate``) and the threshold of the target
weeks (``future_outbreak_threshold`` from ``casos_dengue``, not from the rounded threshold column). There
is no history before 2017 in the database (decision M4): an origin that needs it is unavailable.

The package holds ``booster.json``, ``dispersion.json`` (α per horizon) and ``platt.json`` (a and b per
horizon). Publication reuses ``frozen_configs`` (origins and block predictions), ``probabilistic_output.fit_e3``
(fit at the cutoff), ``protocol.calibrate_chronologically`` (OOS) and ``protocol.fit_platt``.
"""

from dataclasses import dataclass
import json
import platform

import numpy as np
import pandas as pd
from scipy import special, stats
import xgboost as xgb
from xgboost import XGBRegressor, __version__ as XGBOOST_VERSION

from denguekay.data.calendar import mmwr_epi_week
from denguekay.evaluation import protocol as pa
from denguekay.evaluation.compact_validation import compact_variants
from denguekay.evaluation.onsets import own_history, with_season
from denguekay.features.climate import MAIN_CLIMATE, build_observed_climate
from denguekay.features.onset_features import PREVIOUS_SEASON_COLUMN, previous_season
from denguekay.features.outbreak_label import future_outbreak_threshold
from denguekay.model import horizon_strategies as eh
from denguekay.model import probabilistic_output as sp
from denguekay.model.device import xgboost_settings
from denguekay.model.future_rows import build_future_rows
from denguekay.model.train import MIN_OUTBREAK_CASES
from denguekay.serving.artifacts import InvalidArtifact, sha256_bytes
from denguekay.serving.package import package_code
from denguekay.serving.predictors.base import OOS_COLUMNS, OUTPUT_COLUMNS, BuiltPackage, InferenceUnavailable, VersionSpec

KIND = "v2_e3_s4"
CODE_PREFIX = "v2"
TASKS = ("clasificacion", "regresion")
PREFIXES = {"clasificacion": "clf", "regresion": "reg"}
ALGORITHM = "xgboost_multisalida_bn"
HORIZONS = eh.STRATEGY_HORIZONS  # the three outputs of the regressor, always in this order
OOS_BLOCKS = ("temporada_2022", "temporada_2023", "temporada_2024", "calendario_2025")
PLATT_BLOCKS = ("temporada_2021", "temporada_2022", "temporada_2023", "temporada_2024")  # closed seasons
BOOSTER, DISPERSION, PLATT = "booster.json", "dispersion.json", "platt.json"
BASE_6_H2 = compact_variants(2)["base_6"]
A3_SOURCE = {f"{c}_media5_h2": c for c in MAIN_CLIMATE}
CLIMATE_WINDOW = 5
NO_HISTORY_REASON = "El origen necesita casos anteriores a 2017, que no están en la base de datos"
NO_CLIMATE_REASON = "Falta el clima observado de las 5 semanas hasta el origen"
IMPORTANCE = "shap_medio_por_horizonte"


# --- serving: vector of the origin ---------------------------------------------------

def origin_week(cutoff):
    return pd.Timestamp(cutoff.fecha_fin).normalize() - pd.Timedelta(days=6)


def _base_6(cases, cutoff):
    """``base_6`` at the origin with generic names: the h=2 history of target o + 2 is the one at o."""
    try:
        rows, missing = build_future_rows(cases, 2, columns=BASE_6_H2, cutoff_date=pd.Timestamp(cutoff.fecha_fin))
    except ValueError as error:
        raise InferenceUnavailable(str(error)) from error
    vectors = eh.to_generic(rows, 2)[["ubigeo", *eh.GENERIC]].set_index("ubigeo")
    return vectors, {m["ubigeo"]: m["motivo"] for m in missing}


def _b3(cases, origin):
    """B3 at the origin: weeks since the last case, 4-week slope and the previous season."""
    y = cases.pivot(index="semana_inicio", columns="ubigeo", values="casos_Dengue").sort_index()
    if origin not in y.index:
        raise InferenceUnavailable("No hay observaciones de la semana de origen")
    own = pd.DataFrame({name: table.loc[origin] for name, table in own_history(y).items()})
    week = cases.loc[cases.semana_inicio.eq(origin), ["ubigeo", "anio", "semana"]].drop_duplicates("ubigeo")
    week["temporada"] = with_season(week)
    seasons = previous_season(cases, cases.iloc[:0]).merge(week[["ubigeo", "temporada"]], on=["ubigeo", "temporada"])
    own[PREVIOUS_SEASON_COLUMN] = seasons.set_index("ubigeo")[PREVIOUS_SEASON_COLUMN]
    return own


def _a3(climate, origin):
    """A3 at the origin with ``build_observed_climate`` (gold h=2), per district.

    Each district uses its run of complete weeks that ends at the origin (the whole series when nothing is
    missing, as in gold). Two weeks after the origin are appended with a placeholder value: the h=2
    column of target o + 2 is the mean of the 5 weeks up to o, which never reads them.
    """
    columns = list(MAIN_CLIMATE)
    runs, missing = [], set()
    for ubigeo, district in climate.sort_values(["ubigeo", "semana_inicio"]).groupby("ubigeo", sort=True):
        complete = district[columns].notna().all(axis=1).to_numpy()
        gaps = np.flatnonzero(~complete)
        run = district.iloc[gaps[-1] + 1:] if len(gaps) else district
        if len(run) < CLIMATE_WINDOW or run.semana_inicio.iloc[-1] != origin:
            missing.add(ubigeo)
            continue
        dates = pd.Series([origin + pd.Timedelta(weeks=k) for k in (1, 2)])
        cal = mmwr_epi_week(dates)
        future = pd.DataFrame({"ubigeo": ubigeo, "anio": cal.anio_epi.to_numpy(), "semana": cal.semana_epi.to_numpy(),
                               "semana_inicio": dates.to_numpy(), **{c: 0.0 for c in columns}})
        runs += [run[["ubigeo", "anio", "semana", "semana_inicio", *columns]], future]
    if not runs:
        return pd.DataFrame(columns=list(A3_SOURCE)), missing
    observed = build_observed_climate(pd.concat(runs, ignore_index=True), 2, CLIMATE_WINDOW, MAIN_CLIMATE)
    target = observed.loc[observed.semana_inicio.eq(origin + pd.Timedelta(weeks=2))]
    return target.set_index("ubigeo")[list(A3_SOURCE)], missing


def outbreak_rule(rule):
    """``parametro_sistema.regla_brote`` in the terms of ``outbreak_label``; k needs its minimum to be 2."""
    if rule is None or int(rule.get("minimo_casos", -1)) != MIN_OUTBREAK_CASES:
        raise InferenceUnavailable("La regla de brote de parametro_sistema no corresponde a la del modelo v2")
    return {"multiplicador": float(rule["k_desviaciones"]), "anios_previos": int(rule["anios_previos"])}


def target_thresholds(cases, origin, ubigeos, rule):
    """Outbreak threshold of t + 2, t + 3 and t + 4 for each district, computed from the cases (not rounded)."""
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
    """(vectors indexed by ubigeo with ``columns`` and the thresholds of t+2..t+4, {ubigeo: reason})."""
    cases = inputs.cases
    if cases is None or cases.empty:
        raise InferenceUnavailable("No hay observaciones cerradas al corte solicitado")
    origin = origin_week(cutoff)
    vectors, reasons = _base_6(cases, cutoff)
    vectors = vectors.join(_b3(cases, origin), how="left")
    climate, no_climate = _a3(inputs.climate, origin)
    vectors = vectors.join(climate, how="left")
    for ubigeo in sorted(no_climate & set(vectors.index)):
        reasons.setdefault(ubigeo, NO_CLIMATE_REASON)
    vectors = vectors.loc[~vectors.index.isin(list(reasons))]
    no_history = vectors.index[vectors[PREVIOUS_SEASON_COLUMN].isna()]
    for ubigeo in no_history:
        reasons[ubigeo] = NO_HISTORY_REASON
    vectors = vectors.drop(index=no_history)
    values = vectors[columns].to_numpy(float)
    if not np.isfinite(values).all():
        raise ValueError("El vector de la v2 contiene valores faltantes o no finitos")
    thresholds = target_thresholds(cases, origin, list(vectors.index), inputs.outbreak_rule)
    return vectors.join(thresholds), reasons


# --- serving: prediction -------------------------------------------------------------------

def load_booster(content):
    try:
        booster = xgb.Booster()
        booster.load_model(bytearray(content))
    except (ValueError, xgb.core.XGBoostError) as error:
        raise InvalidArtifact("El artefacto XGBoost guardado no se puede cargar") from error
    booster.set_param({"device": "cpu", "nthread": 1})
    return booster


def platt(p, a, b):
    """Platt with stored coefficients: ``expit(a · logit(p) + b)``, as ``LogisticRegression.predict_proba``."""
    return special.expit(pa.platt_logit(p) * a + b)


def interval(mu, alpha, level):
    """Central NB2(mu, alpha) interval with probability ``level`` (quantiles (1 − level)/2 and (1 + level)/2)."""
    mu = np.clip(np.asarray(mu, float), 1e-9, None)
    r = 1 / alpha
    distribution = stats.nbinom(r, r / (r + mu))
    return distribution.ppf((1 - level) / 2), distribution.ppf((1 + level) / 2)


def _json_file(package, name):
    if name not in package.files:
        raise InvalidArtifact(f"El paquete {package.code} no trae {name}")
    try:
        return json.loads(package.files[name].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InvalidArtifact(f"{name} del paquete {package.code} no es JSON válido") from error


def _per_horizon(values, horizons, name):
    output = {}
    for h in horizons:
        value = values.get(str(h))
        numbers = value if isinstance(value, list) else [value]
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and np.isfinite(v) for v in numbers):
            raise InvalidArtifact(f"{name} no trae valores válidos para h={h}")
        output[h] = value
    return output


class Predictor:
    kind = KIND
    required_inputs = frozenset({"casos", "clima", "regla_brote"})

    def __init__(self, horizons, columns, booster, alphas, coefficients, interval_level, formulation):
        self.horizons, self.columns, self.booster = tuple(horizons), list(columns), booster
        self.alphas, self.coefficients = alphas, coefficients
        self.interval_level, self.formulation = interval_level, formulation

    @classmethod
    def from_package(cls, package):
        horizons = package.horizons
        variables = {tuple(package.manifest["variables"][str(h)][t]) for h in horizons for t in TASKS}
        if len(variables) != 1:
            raise InvalidArtifact("Las versiones de un paquete multisalida deben compartir sus variables")
        columns = list(variables.pop())
        if BOOSTER not in package.files:
            raise InvalidArtifact(f"El paquete {package.code} no trae {BOOSTER}")
        booster = load_booster(package.files[BOOSTER])
        if booster.feature_names != columns:
            raise InvalidArtifact("Las columnas del booster no coinciden con la versión")
        alphas = _per_horizon(_json_file(package, DISPERSION).get("alfa", {}), horizons, DISPERSION)
        if any(a <= 0 for a in alphas.values()):
            raise InvalidArtifact(f"{DISPERSION} trae una dispersión no positiva")
        coefficients = _per_horizon(_json_file(package, PLATT).get("coeficientes", {}), horizons, PLATT)
        if any(len(c) != 2 for c in coefficients.values()):
            raise InvalidArtifact(f"{PLATT} debe traer a y b por horizonte")
        formulation = package.manifest["opciones"].get("formulacion")
        if formulation not in sp.FORMULATIONS or sp.FORMULATIONS[formulation]["probabilidad"] != "binomial_negativa":
            raise InvalidArtifact("El paquete v2 debe declarar una formulación S4")
        level = package.interval_level
        if level is None or not 0 < float(level) < 1:
            raise InvalidArtifact("El paquete v2 debe declarar el nivel de su intervalo")
        return cls(horizons, columns, booster, alphas, coefficients, float(level), formulation)

    def counts(self, vectors):
        """Expected cases of t+2, t+3 and t+4 (one column per output), with the origin's ``base_margin``."""
        frame = vectors.reset_index(drop=True)
        x = frame[self.columns].astype(float)
        margin = sp.e3_margin(frame, self.formulation)
        output = np.asarray(self.booster.predict(xgb.DMatrix(x, base_margin=margin)), float)
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
        parts = []
        for h in horizons:
            step = HORIZONS.index(h)
            mu, alpha = counts[:, step], self.alphas[h]
            frame = pd.DataFrame({"ubigeo": list(vectors.index), "horizonte": h})
            if len(vectors):
                raw = sp.negative_binomial_probability(mu, alpha, vectors[h].to_numpy(float))
                low, high = interval(mu, alpha, self.interval_level)
                frame["probabilidad_brote"] = platt(raw, *self.coefficients[h])
                frame["casos_estimados"] = mu
                frame["casos_intervalo_inferior"], frame["casos_intervalo_superior"] = low, high
            missing = pd.DataFrame({"ubigeo": list(reasons), "horizonte": h, "motivo_no_disponible": list(reasons.values())})
            parts += [frame, missing]
        output = pd.concat(parts, ignore_index=True).reindex(columns=OUTPUT_COLUMNS)
        return output.astype({"probabilidad_brote": float, "casos_estimados": float,
                              "casos_intervalo_inferior": float, "casos_intervalo_superior": float})


# --- package building (publication) ------------------------------------------------

@dataclass
class Prepared:
    """Inputs of the publication, in memory: the frozen configuration's origins and block predictions."""
    configuration: dict
    origins: pd.DataFrame  # frozen_configs.origins: base_6 + B3 + A3 and the three targets, RangeIndex
    predictions: pd.DataFrame  # frozen_configs.predict of every block plus calibrate_chronologically (full data)
    series: pd.DataFrame  # weekly cases and labels (variants.inputs()["serie"]): lead time of the evaluation
    hashes: dict
    sha256_dataset: str
    fingerprint: str | None  # behavioural fingerprint (decision D1) when computed on the frozen gold
    fingerprint_matches: bool | None


@dataclass
class FrozenFit:
    """An already trained service fit (cross-platform parity): booster JSON, α and Platt per horizon."""
    booster: bytes
    alphas: dict
    platt: dict


def validate(horizons, options):
    """Known configuration and horizons among the three outputs, before reading any source."""
    if (options or {}).get("configuracion") != "v2":
        raise ValueError("El paquete v2_e3_s4 sirve la configuración congelada v2 (opciones.configuracion: v2)")
    level = (options or {}).get("nivel_intervalo")
    if not isinstance(level, (int, float)) or isinstance(level, bool) or not 0 < level < 1:
        raise ValueError("opciones.nivel_intervalo debe ser una probabilidad entre 0 y 1")
    if not horizons or not set(horizons) <= set(HORIZONS):
        raise ValueError("La v2 predice h=2, 3 y 4")


def configuration():
    from denguekay.model.registry import configuration as registry_configuration

    return registry_configuration("v2")


def prepare(horizons, options):
    """Panel, labels and B3 in memory as in the FE study (gold h=2 + B3, decision M7); block predictions.

    The behavioural fingerprint is compared with the frozen one only when gold h=2 is the frozen dataset
    (the v2 card cites its SHA-256); with new data the fingerprint is recorded but cannot match.
    """
    import hashlib

    from denguekay.config.paths import GOLD, GOLD_MANIFEST, SILVER_EPI_HISTORICAL, SILVER_INTEGRATED
    from denguekay.data.loading import load_integrated
    from denguekay.evaluation import variants
    from denguekay.model import frozen_configs as cf
    from denguekay.model.registry import card

    config = configuration()
    panel = load_integrated(SILVER_INTEGRATED)
    rule = json.loads(GOLD_MANIFEST.read_text(encoding="utf-8"))["regla_brote"]
    inputs = variants.inputs(panel, rule)
    origins = cf.origins(panel, inputs, rule, configuration=config)
    raw = cf.predict(inputs["matrices"], origins, configuration=config)
    predictions, _ = pa.calibrate_chronologically(raw)
    gold_h2 = GOLD / f"{SILVER_INTEGRATED.stem}_h2_gold.csv"
    files = [SILVER_INTEGRATED, SILVER_EPI_HISTORICAL, GOLD_MANIFEST, gold_h2]
    hashes = {f"v2:{p.name}": hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    sha256_gold = hashes[f"v2:{gold_h2.name}"]
    frozen_gold = card("v2")["gold"]["2"]["sha256"] == sha256_gold
    fingerprint = cf.fingerprint(raw, config)
    matches = None
    if frozen_gold:
        expected = cf.REFERENCE_FINGERPRINTS.get(cf.setup_key(xgboost_settings()), {}).get("V2")
        matches = None if expected is None else fingerprint == expected
        if matches is False:
            raise ValueError("Las predicciones de la v2 no reproducen su huella congelada en este entorno; "
                             "no se publica un modelo distinto del evaluado")
    return Prepared(config, origins, predictions, inputs["serie"], hashes, sha256_gold, fingerprint, matches)


def fingerprint_parameters():
    return {"configuracion": "v2", "xgboost": XGBOOST_VERSION}


def _number(value):
    return None if value is None or pd.isna(value) else float(value)


def protocol_metrics(table, horizon):
    """Saved metrics per block (``pa.evaluate(...)["metricas"]``) in the shape of ``evaluation.acceptance``."""
    blocks = {}
    for row in table.loc[table.horizonte.eq(horizon)].itertuples(index=False):
        row = row._asdict()
        blocks[row["bloque"]] = {
            "bloque": row["bloque"], "n": int(row["n"]), "positivos": int(row["positivos"]),
            "clasificacion": {"umbral_probabilidad": pa.ALERT_THRESHOLD,
                              "alerta_directa": {m: _number(row.get(f"{m}_050")) for m in ("precision", "recall", "f1")},
                              "auprc": _number(row.get("auprc")), "brier": _number(row.get("brier"))},
            "regresion": {"conteos": {"mae": _number(row.get("mae")), "rmse": _number(row.get("rmse"))}},
            "persistencia": {"conteos": {"mae": _number(row.get("mae_persistencia")),
                                         "rmse": _number(row.get("rmse_persistencia"))}}}
    return {"bloques": blocks,
            "procedencia": "Protocolo por bloques de la configuración congelada (semilla 17, Platt cronológico); "
                           "métricas de los modelos de cada bloque, no del ajuste de servicio"}


def platt_coefficients(predictions, horizons, cutoff):
    """Platt per horizon with the OOS of the seasons closed at the cutoff (2021–2024)."""
    output, rows = {}, {}
    for h in horizons:
        data = predictions.loc[predictions.horizonte.eq(h) & predictions.bloque.isin(PLATT_BLOCKS)]
        data = data.loc[(pd.to_datetime(data.semana_inicio) + pd.Timedelta(days=6)).le(pd.Timestamp(cutoff))]
        model = pa.fit_platt(data.probabilidad_brote, data.brote)
        output[h] = [float(model.coef_[0, 0]), float(model.intercept_[0])]
        rows[h] = len(data)
    return output, rows


def oos_table(predictions, horizons):
    """Calibrated OOS of the protocol (blocks 2022–2025), one row per district and target week."""
    data = predictions.loc[predictions.horizonte.isin(horizons) & predictions.bloque.isin(OOS_BLOCKS)].copy()
    data["orden_bloque"] = data.bloque.map({b: i for i, b in enumerate(OOS_BLOCKS)})
    data = data.sort_values(["horizonte", "orden_bloque", "ubigeo", "anio", "semana"], kind="mergesort")
    return pd.DataFrame({"horizonte": data.horizonte.astype(int), "bloque": data.bloque, "ubigeo": data.ubigeo,
                         "anio": data.anio.astype(int), "semana": data.semana.astype(int),
                         "origen_cierre": pd.to_datetime(data.origen_cierre),
                         "probabilidad_brote": data.probabilidad_calibrada.astype(float),
                         "casos_estimados": data.casos_predichos.astype(float)}).reset_index(drop=True)[OOS_COLUMNS]


def fit_service(prepared, cutoff):
    """E3 fit with every origin whose three targets closed at the cutoff (the same function as each block)."""
    config = prepared.configuration
    columns = list(config["columnas"])
    fitted = sp.fit_e3(prepared.origins, pd.Timestamp(cutoff), config["semilla_despliegue"], config["formulacion"],
                       columns, [*columns, eh.POPULATION], sp.e3_parameters(config["hiperparametros"]),
                       sp.e3_margin(prepared.origins, config["formulacion"]))
    return fitted.regressor, dict(zip(HORIZONS, fitted.alphas)), fitted.train


def importances(regressor, x):
    """Mean |SHAP| of each output, per horizon (decision M3), computed at publication."""
    table = sp.shap_importance_by_horizon(regressor, x)
    output = {}
    for h in HORIZONS:
        values = table.loc[f"h={h}"].sort_values(ascending=False, kind="mergesort")
        ranked = sorted(values.items(), key=lambda item: (-item[1], item[0]))
        output[h] = [{"variable": c, "importancia": float(v), "rango": span} for span, (c, v) in enumerate(ranked, 1)]
    return output


def _dumps(value):
    return (json.dumps(value, ensure_ascii=False, indent=1, sort_keys=True) + "\n").encode("utf-8")


def build(prepared, horizons, options, cutoff, trained=None):
    """``BuiltPackage`` of v2: one booster, its α and Platt, six versions, the protocol's OOS and the report."""
    config = prepared.configuration
    horizons = tuple(sorted(horizons))
    columns = list(config["columnas"])
    level = float(options["nivel_intervalo"])
    closed = pd.Timestamp(cutoff)
    if trained is None:
        regressor, alphas, train = fit_service(prepared, closed)
        coefficients, platt_rows = platt_coefficients(prepared.predictions, horizons, closed)
        booster = bytes(regressor.get_booster().save_raw(raw_format="json"))
    else:
        booster, alphas, coefficients, platt_rows = trained.booster, dict(trained.alphas), dict(trained.platt), None
        regressor = XGBRegressor()
        regressor.load_model(bytearray(booster))
        # The rows the frozen booster was fitted with (same selection as fit_e3), for its SHAP importances.
        targets = [f"semana_inicio_h{h}" for h in HORIZONS]
        complete = prepared.origins.dropna(subset=targets)
        train = complete.loc[(complete[targets[-1]] + pd.Timedelta(days=6)).le(closed)]
    files = {BOOSTER: booster,
             DISPERSION: _dumps({"alfa": {str(h): float(alphas[h]) for h in horizons},
                                 "metodo": "NB2 por máxima verosimilitud con las predicciones dentro de la muestra "
                                           "del ajuste de servicio (dispersión dentro_muestra)"}),
             PLATT: _dumps({"coeficientes": {str(h): list(map(float, coefficients[h])) for h in horizons},
                            "forma": "p = expit(a · logit(clip(q, 1e-6, 1 − 1e-6)) + b)",
                            "bloques": list(PLATT_BLOCKS), "filas": {str(h): n for h, n in (platt_rows or {}).items()}})}
    shap = importances(regressor, train[columns])
    reproducibility = {
        "configuracion": "CONFIG_2026 (denguekay.model.frozen_configs), ficha models/registry/v2",
        "formulacion": config["formulacion"], "semilla": config["semilla_despliegue"],
        "grupo_artefacto": None,  # filled below with the package code
        "device": xgboost_settings()["device"], "version_xgboost": XGBOOST_VERSION,
        "plataforma": f"{platform.system()} {platform.release()} {platform.machine()}",
        "entrenamiento_inicio": str(pd.to_datetime(train.semana_inicio).min().date()),
        "entrenamiento_corte": str(closed.date()), "filas_entrenamiento": int(len(train)),
        "sha256_booster": sha256_bytes(booster), "huella_comportamiento": prepared.fingerprint,
        "huella_coincide_con_congelada": prepared.fingerprint_matches,
        "tipo_importancia": IMPORTANCE,
        "calibracion": "Platt con las OOS de las temporadas cerradas 2021–2024",
        "intervalo": f"NB2 central al {level:.2f}, sin calibrar (Platt solo calibra la probabilidad)",
        "sha256_entradas": dict(prepared.hashes)}
    hyperparameters = {**sp.count_objective(sp.FORMULATIONS[config["formulacion"]]["conteo"]),
                       **eh.parameters(config["semilla_despliegue"], **sp.e3_parameters(config["hiperparametros"]))}
    code = package_code(CODE_PREFIX, files)
    reproducibility["grupo_artefacto"] = code
    versions = []
    table = pa.evaluate(prepared.predictions, prepared.series)["metricas"]
    for h in horizons:
        metrics = protocol_metrics(table, h)
        for task in TASKS:
            data = {"algoritmo": ALGORITHM, "variables": columns, "hiperparametros": hyperparameters,
                    "metricas": metrics,
                    "umbral_probabilidad": pa.ALERT_THRESHOLD if task == "clasificacion" else None,
                    "sha256_dataset": prepared.sha256_dataset, "reproducibilidad": dict(reproducibility)}
            versions.append(VersionSpec(task, h, f"{CODE_PREFIX}-{PREFIXES[task]}-h{h}-", data, shap[h]))
    report = {"experimento": "versiones_de_servicio", "tipo_predictor": KIND, "parametros": hyperparameters,
              "version_xgboost": XGBOOST_VERSION, "fecha_corte_datos": str(closed.date()),
              "evaluacion_generada_en_esta_corrida": True,
              "nota_metricas": "Métricas del protocolo por bloques recalculado en esta corrida (semilla 17); "
                               "no evalúan el ajuste de servicio",
              "huella_comportamiento": prepared.fingerprint or "",
              "horizontes": {str(h): {"sha256_gold": prepared.sha256_dataset, "variantes": {}} for h in horizons}}
    return BuiltPackage(
        kind=KIND, code=code, horizons=horizons, files=files,
        variables={str(h): {task: columns for task in TASKS} for h in horizons}, interval_level=level,
        options={"configuracion": "v2", "formulacion": config["formulacion"], "nivel_intervalo": level},
        versions=versions, oos=oos_table(prepared.predictions, horizons),
        oos_detail={"configuracion": "v2", "paquete": code,
                    "nota": "OOS del protocolo por bloques de la v2, calibradas con Platt cronológico; "
                            "reemplazan las de la v0 en la serie (M6)"},
        report=report, fingerprint=prepared.fingerprint)
