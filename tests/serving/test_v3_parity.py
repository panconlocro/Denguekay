"""Parity of the v3 serving with the long history (real data; skipped without data/).

The database starts in 2017 (decision M4). Serving builds the origin vector from cases since 2017 and the ERA5-Land
temperature column; the package is trained outside the database on the series since 2000. At an origin of 2025
both vectors must be equal (base_6, B3 and d3), and the served μ must equal the fit's μ (float32 of XGBoost).
"""

import json
import unittest
from types import SimpleNamespace

import numpy as np
import pandas as pd

from denguekay.config.paths import SILVER_EPI_HISTORICAL, SILVER_INTEGRATED, SILVER_SALA
from denguekay.features import climate as cl

HAS_DATA = SILVER_INTEGRATED.exists() and SILVER_EPI_HISTORICAL.exists() and SILVER_SALA.exists()
ORIGIN_CLOSE = pd.Timestamp("2025-06-28")
RULE = {"anios_previos": 5, "k_desviaciones": 1.5, "minimo_casos": 2}


@unittest.skipUnless(HAS_DATA, "Sin data/ (integrado, epi histórico y Sala): se omite la paridad de la v3")
class TestV3ServingParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from denguekay.data.loading import load_integrated
        from denguekay.features.long_history import long_inputs
        from denguekay.model import frozen_configs as fc
        from denguekay.serving.inputs import ServingInputs

        try:
            era5 = cl.era5_land_silver()
        except FileNotFoundError as error:
            raise unittest.SkipTest(str(error))
        panel = load_integrated(SILVER_INTEGRATED)
        cls.long = long_inputs(panel, era5)
        cls.columns = list(fc.CONFIG_V3["columnas"])
        closed = panel.loc[(pd.to_datetime(panel.semana_inicio) + pd.Timedelta(days=6)).le(ORIGIN_CLOSE)]
        cases = closed[["ubigeo", "anio", "semana", "semana_inicio", "casos_Dengue"]].astype({"casos_Dengue": float})
        cases = cases.assign(ubigeo=cases.ubigeo.astype("string"), semana_inicio=pd.to_datetime(cases.semana_inicio))
        weekly = cl.era5_land_weekly(era5, panel).rename(columns={"temp_media": "temp_media_era5_land"})
        climate = cases[["ubigeo", "anio", "semana", "semana_inicio"]].merge(
            weekly.assign(ubigeo=weekly.ubigeo.astype("string")), on=["ubigeo", "semana_inicio"], how="left")
        cls.inputs = ServingInputs(cases.reset_index(drop=True), climate.reset_index(drop=True), None, None, RULE)

    def test_vector_from_2017_equals_the_long_history(self):
        from denguekay.serving.predictors import v3_l5a_d3 as v3

        vectors, reasons = v3.origin_vectors(self.inputs, SimpleNamespace(fecha_fin=ORIGIN_CLOSE.date()), self.columns)
        self.assertEqual(reasons, {})
        origins = self.long["origenes"]
        reference = origins.loc[pd.to_datetime(origins.origen_cierre).eq(ORIGIN_CLOSE)].assign(
            ubigeo=lambda d: d.ubigeo.astype(str)).set_index("ubigeo")[self.columns]
        served = vectors[self.columns].rename(index=str).loc[reference.index]
        self.assertEqual(len(served), 65)
        np.testing.assert_allclose(served.to_numpy(float), reference.to_numpy(float), rtol=0, atol=1e-12)

    def test_served_mu_equals_the_fit(self):
        from xgboost import XGBRegressor  # noqa: F401  (the booster is loaded by the predictor)

        from denguekay.model import frozen_configs as fc
        from denguekay.model import v3_training as vt
        from denguekay.serving.predictors import v3_l5a_d3 as v3

        fitted = vt.fit(self.long["origenes"], ORIGIN_CLOSE, 17, self.columns,
                        {**fc.CONFIG_V3["hiperparametros"], "n_estimators": 60})
        booster = bytes(fitted.regressor.get_booster().save_raw(raw_format="json"))
        files = {v3.BOOSTER: booster,
                 v3.DISPERSION: json.dumps({"alfa": {str(h): a for h, a in fitted.alphas.items()}}).encode(),
                 v3.PLATT: json.dumps({"coeficientes": {str(h): [1.0, 0.0] for h in (2, 3, 4)}}).encode(),
                 v3.MIXTURE: json.dumps({"w": {str(h): 1.0 for h in (2, 3, 4)}}).encode()}
        package = SimpleNamespace(code="v3-paridad", horizons=(2, 3, 4), files=files, interval_level=0.8,
                                  manifest={"variables": {str(h): {t: self.columns for t in v3.TASKS} for h in (2, 3, 4)},
                                            "opciones": {"formulacion": vt.FORMULATION}})
        predictor = v3.Predictor.from_package(package)
        vectors, _ = v3.origin_vectors(self.inputs, SimpleNamespace(fecha_fin=ORIGIN_CLOSE.date()), self.columns)
        served = predictor.counts(vectors)
        origins = self.long["origenes"]
        rows = origins.loc[pd.to_datetime(origins.origen_cierre).eq(ORIGIN_CLOSE)].assign(
            ubigeo=lambda d: d.ubigeo.astype(str)).set_index("ubigeo").loc[[str(u) for u in vectors.index]].reset_index()
        expected = vt.predict_counts(fitted.regressor, rows, self.columns)
        np.testing.assert_allclose(served, expected, rtol=1e-6, atol=1e-8)


if __name__ == "__main__":
    unittest.main()
