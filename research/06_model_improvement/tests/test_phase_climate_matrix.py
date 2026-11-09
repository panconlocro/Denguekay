"""Tests of the climate matrix: e1 anomalies (G45 definition, G46 no leakage by the origin, G47 no leakage by the
cutoff, the leave-one-season-out exclusion) and n1 (G49 monotone, G50 zero constraints = no constraints)."""

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

import phase_climate_matrix as cm  # noqa: E402
import phase_d_weather_windows as pdw  # noqa: E402
import preregistration as pr  # noqa: E402

UBIGEOS = ("200101", "200202")


def _sources(n_weeks=160, seed=0):
    rng = np.random.default_rng(seed)
    weeks = pd.date_range("2000-01-02", periods=n_weeks, freq="7D")
    rows = []
    for u in UBIGEOS:
        rows.append(pd.DataFrame({"ubigeo": u, "semana_inicio": weeks, "precip_total_mm": rng.gamma(1, 20, n_weeks),
                                  "temp_media": rng.uniform(18, 32, n_weeks), "hum_rel_media": rng.uniform(40, 95, n_weeks),
                                  "dias_fuertes": rng.integers(0, 3, n_weeks).astype(float)}))
    d = pd.concat(rows, ignore_index=True)
    chirps = d[["ubigeo", "semana_inicio", "precip_total_mm"]].assign(fecha_disponible=d.semana_inicio + pd.Timedelta(days=11))
    era5 = d[["ubigeo", "semana_inicio", "temp_media", "hum_rel_media"]]
    daily = d[["ubigeo", "semana_inicio", "dias_fuertes"]]
    origins = d[["ubigeo"]].assign(origen_cierre=d.semana_inicio + pd.Timedelta(days=6))
    return {"chirps": chirps, "era5": era5, "semanal_diario": daily}, origins.reset_index(drop=True)


class TestE1(unittest.TestCase):
    def test_columns_match_the_preregistration(self):
        sources, origins = _sources()
        out = cm.E1Builder(sources).add(origins, cutoff=pd.Timestamp("2002-06-01"))
        self.assertTrue(set(pr.MATRIX_E1) <= set(out.columns))

    def test_definition_anomaly_windows(self):
        """G45 (synthetic): each e1 window is the value's window minus the climatology's window."""
        sources, origins = _sources()
        cutoff = pd.Timestamp("2002-06-01")
        b = cm.E1Builder(sources)
        d1 = pdw.build_d1(origins, sources["chirps"], sources["era5"],
                          sources["semanal_diario"].rename(columns={})[["ubigeo", "semana_inicio", "dias_fuertes"]])
        g = cm.guard_e1_definition(b, d1, cutoff)
        self.assertTrue(g["pasa"], g)

    def test_climatology_uses_weeks_closed_at_the_cutoff_only(self):
        """G47 (synthetic): weather after the cutoff changes neither the climatology nor e1 before the cutoff."""
        sources, origins = _sources()
        g = cm.guard_e1_cutoff(sources, origins, pd.Timestamp("2002-06-01"))
        self.assertTrue(g["pasa"], g)
        self.assertGreater(g["origenes_hasta_el_corte"], 100)

    def test_no_leakage_by_the_origin(self):
        """G46: with the climatology fixed, weather after the origin week does not change e1."""
        sources, origins = _sources()
        cutoff = pd.Timestamp("2001-12-31")
        base = cm.E1Builder(sources).add(origins, cutoff=cutoff)
        cut = pd.Timestamp("2002-09-01")
        altered = {}
        for k, d in sources.items():
            d = d.copy()
            later = d.semana_inicio > cut
            for c in ("precip_total_mm", "temp_media", "hum_rel_media", "dias_fuertes"):
                if c in d:
                    d.loc[later, c] = d.loc[later, c] * 2 + 5
            altered[k] = d
        other = cm.E1Builder(altered).add(origins, cutoff=cutoff)
        early = (origins.origen_cierre - pd.Timedelta(days=6)) <= cut
        np.testing.assert_array_equal(base.loc[early, pr.MATRIX_E1].to_numpy(float), other.loc[early, pr.MATRIX_E1].to_numpy(float))
        self.assertFalse(np.allclose(base.loc[~early, pr.MATRIX_E1].dropna().to_numpy(float),
                                     other.loc[~early, pr.MATRIX_E1].dropna().to_numpy(float)))

    def test_loso_climatology_excludes_the_period(self):
        sources, _ = _sources()
        s = cm.weekly_series(sources)["temp_media"]
        full = cm.climatology(s, "temp_media")
        excl = cm.climatology(s, "temp_media", exclude=(pd.Timestamp("2001-01-01"), pd.Timestamp("2001-12-31")))
        kept = s[~s.semana_inicio.between("2001-01-01", "2001-12-31")]
        manual = kept.groupby(["ubigeo", "celda"]).temp_media.mean().to_numpy()
        np.testing.assert_allclose(excl.climatologia.to_numpy(), manual)
        self.assertFalse(np.allclose(full.climatologia.to_numpy(), excl.climatologia.to_numpy()))

    def test_incomplete_climatology_stops(self):
        sources, _ = _sources(n_weeks=30)
        with self.assertRaises(ValueError):
            cm.climatology(cm.weekly_series(sources)["temp_media"], "temp_media")


class TestN1(unittest.TestCase):
    def test_monotone_hp(self):
        hp = cm.monotone_hp({"max_depth": 3}, ["a", cm.NINO, "b"], {cm.NINO: 1})
        self.assertEqual(hp["monotone_constraints"], (0, 1, 0))
        self.assertEqual(hp["max_depth"], 3)

    def test_constraint_is_monotone_and_zero_constraint_is_neutral(self):
        """G49/G50 on synthetic data with the E3 multi-output trees."""
        import xgboost as xgb

        rng = np.random.default_rng(0)
        x = rng.normal(size=(1500, 3))
        y = np.column_stack([rng.poisson(np.exp(1 - 0.8 * x[:, 0]))] * 3).astype(float)
        common = dict(objective="count:poisson", tree_method="hist", multi_strategy="multi_output_tree",
                      n_estimators=60, random_state=1)
        grid = np.repeat(x[:5], 40, axis=0)
        grid[:, 0] = np.tile(np.linspace(-3, 3, 40), 5)
        m = xgb.XGBRegressor(monotone_constraints=(1, 0, 0), **common).fit(x, y)
        p = m.predict(grid).reshape(5, 40, 3)
        self.assertGreaterEqual(float(np.diff(p, axis=1).min()), -1e-9)
        a = xgb.XGBRegressor(**common).fit(x, y).predict(x)
        b = xgb.XGBRegressor(monotone_constraints=(0, 0, 0), **common).fit(x, y).predict(x)
        np.testing.assert_array_equal(a, b)


if __name__ == "__main__":
    unittest.main()
