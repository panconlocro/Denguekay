"""Serve the B3 paper predictor against the verified V4 demo origin."""

from io import BytesIO

import numpy as np
import pandas as pd

from denguekay.serving.artifacts import InvalidArtifact
from denguekay.serving.predictors import v2_e3_s4 as v2, v3_l5a_d3 as v3
from denguekay.serving.predictors.base import InferenceUnavailable

KIND = "v4_b3_obs"
SNAPSHOT = "origen.csv"
PARAMETERS = "b3.json"
BOOSTER = "booster.ubj"


class Predictor(v3.Predictor):
    kind = KIND
    required_inputs = frozenset()

    @classmethod
    def from_package(cls, package):
        config = v2._json_file(package, PARAMETERS)
        horizons = package.horizons
        columns = config["columnas"]
        for h in horizons:
            if any(package.manifest["variables"][str(h)][task] != columns for task in v3.TASKS):
                raise InvalidArtifact("Las variables del manifiesto V4 difieren del predictor")
        booster = v2.load_booster(package.files[BOOSTER])
        if booster.feature_names != columns:
            raise InvalidArtifact("Las variables V4 difieren del booster")
        alpha = v2._per_horizon(config["dispersion"], horizons, "dispersion")
        platt = v2._per_horizon(config["platt"], horizons, "platt")
        weights = v2._per_horizon(config["mezcla"], horizons, "mezcla")
        if (any(value <= 0 for value in alpha.values()) or any(len(pair) != 2 for pair in platt.values())
                or any(not 0 <= value <= 1 for value in weights.values())):
            raise InvalidArtifact("Parámetros probabilísticos inválidos en el paquete V4")
        cutoff = pd.Timestamp(config["corte"])
        if cutoff.dayofweek != 5 or package.interval_level is not None:
            raise InvalidArtifact("Origen o intervalo inválido en el paquete V4")
        vectors = pd.read_csv(BytesIO(package.files[SNAPSHOT]), dtype={"ubigeo": str},
                              float_precision="round_trip").set_index("ubigeo", verify_integrity=True)
        thresholds = {f"umbral_h{h}": h for h in horizons}
        fields = [*columns, *thresholds]
        if (len(vectors) != 65 or not vectors.index.str.fullmatch(r"20[0-9]{4}").all()
                or not set(fields) <= set(vectors)
                or not np.isfinite(vectors[fields].to_numpy(float)).all()
                or vectors[list(thresholds)].lt(0).any().any()):
            raise InvalidArtifact("Vectores distritales V4 incompletos o inválidos")
        predictor = cls(horizons, columns, booster, alpha, platt, weights, None)
        predictor.cutoff = cutoff.date()
        predictor.snapshot = vectors.rename(columns=thresholds)
        return predictor

    def vectors(self, inputs, cutoff):
        if cutoff.fecha_fin != self.cutoff:
            raise InferenceUnavailable(f"La demo V4 tiene vectores verificados para el corte {self.cutoff}")
        return self.snapshot, {}
