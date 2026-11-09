"""Tests of the V3 closing helpers: the saved Platt parameters reproduce the protocol's calibration."""

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

import phase_v3_close as v3  # noqa: E402
from denguekay.evaluation import protocol as pa  # noqa: E402


def _predictions(seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for k, block in enumerate(("temporada_2008", "temporada_2009", "temporada_2010")):
        start = pd.Timestamp("2007-08-26") + pd.Timedelta(weeks=52 * k)
        for w in range(52):
            for u in ("200101", "200104"):
                p = float(rng.uniform(0.001, 0.9))
                rows.append({"ubigeo": u, "anio": 2007 + k, "semana": w + 1, "semana_inicio": start + pd.Timedelta(weeks=w),
                             "origen_cierre": start + pd.Timedelta(weeks=w) - pd.Timedelta(days=8), "horizonte": 2,
                             "bloque": block, "probabilidad_brote": p, "casos_predichos": 3 * p,
                             "brote": int(rng.uniform() < p), "casos_Dengue": 1, "umbral_brote_casos": 1.0,
                             "persistencia": 1.0})
    return pd.DataFrame(rows)


class TestPlatt(unittest.TestCase):
    def test_saved_parameters_reproduce_the_calibration(self):
        pred = _predictions()
        params = v3.platt_parameters(pred)
        self.assertTrue(np.isnan(params.set_index("bloque").loc["temporada_2008", "platt_a"]))
        cal, record = pa.calibrate_chronologically(pred)
        cal = cal.merge(params, on=["horizonte", "bloque"])
        has = cal.platt_a.notna()
        p = v3.apply_platt(cal.probabilidad_brote[has], cal.platt_a[has], cal.platt_b[has])
        self.assertLess(float(np.abs(p - cal.probabilidad_calibrada[has]).max()), 1e-12)
        rec = record.merge(params, on=["horizonte", "bloque"])
        self.assertTrue(rec.filas_calibracion_x.eq(rec.filas_calibracion_y).all())

    def test_hyperparameters_are_trial_191(self):
        from denguekay.model import frozen_configs as fc

        self.assertEqual(v3.hyperparameters(), fc.V3_HYPERPARAMETERS)
        self.assertEqual(v3.variant_columns()["V3"], fc.CONFIG_V3["columnas"])


if __name__ == "__main__":
    unittest.main()
