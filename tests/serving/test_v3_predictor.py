"""Predictor v3_l5a_d3 with synthetic data (no database, no data/): vector, package, mixture, Platt and long history."""

import json
import unittest
from types import SimpleNamespace

import numpy as np
import pandas as pd
from xgboost import XGBRegressor

from denguekay.features import climate as cl
from denguekay.features import long_history as lh
from denguekay.model import frozen_configs as fc
from denguekay.model import v3_training as vt
from denguekay.serving.artifacts import InvalidArtifact
from denguekay.serving.inputs import ServingInputs
from denguekay.serving.predictors import predictor_module
from denguekay.serving.predictors import v3_l5a_d3 as v3
from denguekay.serving.predictors.base import InferenceUnavailable

RULE = {"anios_previos": 5, "k_desviaciones": 1.5, "minimo_casos": 2}
UBIGEOS = ["200101", "200104"]
COLUMNS = list(fc.CONFIG_V3["columnas"])


def weekly_frames(last="2024-06-29"):
    """Cases (2017 onwards, every week) and ERA5-Land temperature for two districts, closed at ``last``."""
    weeks = pd.date_range("2017-01-01", pd.Timestamp(last) - pd.Timedelta(days=6), freq="W-SUN")
    from denguekay.data.calendar import mmwr_epi_week

    cal = mmwr_epi_week(pd.Series(weeks))
    rows, rng = [], np.random.default_rng(3)
    for k, u in enumerate(UBIGEOS):
        for w, a, s in zip(weeks, cal.anio_epi, cal.semana_epi):
            rows.append({"ubigeo": u, "anio": int(a), "semana": int(s), "semana_inicio": w,
                         "casos_Dengue": float(rng.poisson(3 + 2 * k)),
                         "temp_media_era5_land": 24.0 + k + 0.01 * (w.dayofyear % 50)})
    frame = pd.DataFrame(rows)
    cases = frame[["ubigeo", "anio", "semana", "semana_inicio", "casos_Dengue"]].assign(ubigeo=lambda d: d.ubigeo.astype("string"))
    climate = frame[["ubigeo", "anio", "semana", "semana_inicio", "temp_media_era5_land"]].assign(
        ubigeo=lambda d: d.ubigeo.astype("string"))
    return cases, climate


def package(alphas=(0.7, 1.0, 1.3), weights=(0.8, 0.8, 0.9), formulation=vt.FORMULATION, level=0.8, columns=COLUMNS):
    rng = np.random.default_rng(0)
    x = pd.DataFrame(rng.random((80, len(columns))), columns=columns)
    model = XGBRegressor(objective="count:poisson", n_estimators=5, max_depth=2, multi_strategy="multi_output_tree",
                         tree_method="hist")
    model.fit(x, rng.poisson(3, (80, 3)).astype(float), base_margin=np.full((80, 3), np.log(3.5)))
    booster = bytes(model.get_booster().save_raw(raw_format="json"))
    files = {v3.BOOSTER: booster,
             v3.DISPERSION: json.dumps({"alfa": {str(h): a for h, a in zip((2, 3, 4), alphas)}}).encode(),
             v3.PLATT: json.dumps({"coeficientes": {str(h): [1.0, 0.0] for h in (2, 3, 4)}}).encode(),
             v3.MIXTURE: json.dumps({"w": {str(h): w for h, w in zip((2, 3, 4), weights)}}).encode()}
    manifest = {"variables": {str(h): {t: columns for t in v3.TASKS} for h in (2, 3, 4)},
                "opciones": {"configuracion": "v3", "formulacion": formulation, "nivel_intervalo": level}}
    return SimpleNamespace(code="v3-prueba", horizons=(2, 3, 4), files=files, manifest=manifest, interval_level=level)


def cutoff(close):
    return SimpleNamespace(fecha_fin=pd.Timestamp(close).date())


class TestVector(unittest.TestCase):
    def test_d3_windows_at_the_origin(self):
        _, climate = weekly_frames()
        origin = pd.Timestamp("2024-06-23")
        d3, missing = v3._d3(climate, origin, UBIGEOS)
        self.assertEqual(missing, set())
        series = climate[climate.ubigeo.eq("200101")].set_index("semana_inicio").temp_media_era5_land
        weeks = [origin - pd.Timedelta(weeks=k) for k in range(13)]
        self.assertAlmostEqual(d3.loc["200101", "temp_media_s0"], series[weeks[0]])
        self.assertAlmostEqual(d3.loc["200101", "temp_media_media_s1_4"], series[weeks[1:5]].mean())
        self.assertAlmostEqual(d3.loc["200101", "temp_media_media_s9_12"], series[weeks[9:13]].mean())

    def test_missing_temperature_week_makes_the_district_unavailable(self):
        _, climate = weekly_frames()
        hole = climate.ubigeo.eq("200104") & climate.semana_inicio.eq(pd.Timestamp("2024-05-05"))
        climate.loc[hole, "temp_media_era5_land"] = np.nan
        d3, missing = v3._d3(climate, pd.Timestamp("2024-06-23"), UBIGEOS)
        self.assertEqual(missing, {"200104"})
        self.assertEqual(list(d3.index), ["200101"])
        self.assertEqual(v3._d3(None, pd.Timestamp("2024-06-23"), UBIGEOS)[1], set(UBIGEOS))


class TestPredictor(unittest.TestCase):
    def setUp(self):
        self.cases, self.climate = weekly_frames()
        self.inputs = ServingInputs(self.cases, self.climate, None, None, RULE)
        self.predictor = v3.Predictor.from_package(package())

    def test_registered_and_loaded(self):
        self.assertIs(predictor_module("v3_l5a_d3"), v3)
        self.assertEqual(self.predictor.columns, COLUMNS)
        self.assertEqual(self.predictor.weights, {2: 0.8, 3: 0.8, 4: 0.9})

    def test_prediction_uses_the_mixture_for_the_count_and_mu_for_the_probability(self):
        out = self.predictor.predict(self.inputs, cutoff("2024-06-29"), (2, 3, 4))
        self.assertEqual(len(out), 6)
        vectors, _ = v3.origin_vectors(self.inputs, cutoff("2024-06-29"), COLUMNS)
        mu = self.predictor.counts(vectors)
        persistence = vectors["hist_lag_a"].to_numpy(float)
        h4 = out[out.horizonte.eq(4)].set_index("ubigeo").loc[list(vectors.index)]
        np.testing.assert_allclose(h4.casos_estimados, 0.9 * mu[:, 2] + 0.1 * persistence, rtol=1e-12)
        self.assertTrue(out.probabilidad_brote.between(0, 1).all())
        self.assertTrue((out.casos_intervalo_inferior <= out.casos_intervalo_superior).all())

    def test_unavailable_reasons(self):
        out = self.predictor.predict(ServingInputs(self.cases, None, None, None, RULE), cutoff("2024-06-29"), (2,))
        self.assertTrue(out.motivo_no_disponible.eq(v3.NO_TEMPERATURE_REASON).all())
        with self.assertRaises(InferenceUnavailable):
            self.predictor.predict(self.inputs, cutoff("2024-06-29"), (5,))
        with self.assertRaises(InferenceUnavailable):
            self.predictor.predict(ServingInputs(self.cases, self.climate, None, None, {**RULE, "minimo_casos": 1}),
                                   cutoff("2024-06-29"), (2,))
        with self.assertRaises(InferenceUnavailable):
            self.predictor.predict(ServingInputs(self.cases.iloc[:0], self.climate, None, None, RULE),
                                   cutoff("2024-06-29"), (2,))

    def test_invalid_packages(self):
        for bad in (package(alphas=(0.7, -1, 1.3)), package(weights=(0.8, 1.5, 0.9)), package(formulation="S1"),
                    package(level=None)):
            with self.subTest(bad=bad.manifest["opciones"]):
                with self.assertRaises(InvalidArtifact):
                    v3.Predictor.from_package(bad)
        for missing in (v3.MIXTURE, v3.BOOSTER):
            broken = package()
            broken.files.pop(missing)
            with self.subTest(missing=missing), self.assertRaises(InvalidArtifact):
                v3.Predictor.from_package(broken)
        bad_platt = package()
        bad_platt.files[v3.PLATT] = json.dumps({"coeficientes": {str(h): [1.0] for h in (2, 3, 4)}}).encode()
        mixed = package()
        mixed.manifest["variables"]["4"]["regresion"] = COLUMNS[:-1]
        wrong_columns = package(columns=[f"x{i}" for i in range(len(COLUMNS))])
        wrong_columns.manifest["variables"] = {str(h): {t: COLUMNS for t in v3.TASKS} for h in (2, 3, 4)}
        for bad in (bad_platt, mixed, wrong_columns):
            with self.assertRaises(InvalidArtifact):
                v3.Predictor.from_package(bad)

    def test_threshold_without_history_is_unavailable(self):
        recent = self.cases[self.cases.semana_inicio.ge(pd.Timestamp("2022-01-02"))].reset_index(drop=True)
        climate = self.climate[self.climate.semana_inicio.ge(pd.Timestamp("2022-01-02"))].reset_index(drop=True)
        with self.assertRaises(InferenceUnavailable):
            self.predictor.predict(ServingInputs(recent, climate, None, None, RULE), cutoff("2024-06-29"), (2,))


class TestPackageBuilding(unittest.TestCase):
    def reference(self):
        rng = np.random.default_rng(5)
        rows = []
        for b, start in (("temporada_2008", "2007-08-26"), ("temporada_2009", "2008-08-24")):
            for i, w in enumerate(pd.date_range(start, periods=30, freq="W-SUN")):
                for h in (2, 3, 4):
                    p = float(rng.uniform(0.01, 0.9))
                    rows.append({"bloque": b, "horizonte": h, "ubigeo": "200101", "semana_inicio": w,
                                 "probabilidad_cruda": p, "brote": int(rng.uniform() < p), "mu_modelo": 3 * p,
                                 "persistencia": 2.0, "casos_Dengue": float(rng.poisson(2))})
        return pd.DataFrame(rows)

    def test_calibration_rows_are_earlier_and_closed(self):
        ref = self.reference()
        rows = v3.calibration_rows(ref, 2, pd.Timestamp("2008-09-06"))
        self.assertTrue((rows.semana_inicio + pd.Timedelta(days=6) <= pd.Timestamp("2008-09-06")).all())
        coefficients, weights, used = v3.platt_and_mixture(ref, (2, 3, 4), pd.Timestamp("2009-03-01"))
        self.assertEqual(set(coefficients), {2, 3, 4})
        self.assertTrue(all(0 <= w <= 1 for w in weights.values()))
        self.assertEqual(used[2]["bloques"], ["temporada_2008", "temporada_2009"])

    def test_validate_options(self):
        v3.validate((2, 3, 4), {"configuracion": "v3", "nivel_intervalo": 0.8})
        for horizons, options in (((2,), {"configuracion": "v2", "nivel_intervalo": 0.8}),
                                  ((2,), {"configuracion": "v3", "nivel_intervalo": 1.0}),
                                  ((5,), {"configuracion": "v3", "nivel_intervalo": 0.8})):
            with self.assertRaises(ValueError):
                v3.validate(horizons, options)
        self.assertEqual(v3.fingerprint_parameters()["configuracion"], "v3")


class TestTrainingHelpers(unittest.TestCase):
    def test_persistence_weight(self):
        y = np.array([1.0, 2, 3, 4])
        self.assertEqual(vt.fit_persistence_weight(y, np.zeros(4), y), 1.0)
        self.assertEqual(vt.fit_persistence_weight(np.zeros(4), y, y), 0.0)
        self.assertEqual(vt.fit_persistence_weight([], [], []), 1.0)
        np.testing.assert_allclose(vt.published_count([2.0], [4.0], 0.25), [3.5])

    def test_training_rows_have_closed_targets(self):
        origins = pd.DataFrame({"origen_cierre": pd.to_datetime(["2020-01-04", "2020-01-11"]),
                                "semana_inicio": pd.to_datetime(["2020-01-12", "2020-01-19"]),
                                **{f"semana_inicio_h{h}": pd.to_datetime(["2020-01-12", "2020-01-19"]) + pd.Timedelta(weeks=h - 2)
                                   for h in (2, 3, 4)}})
        rows = vt.training_rows(origins, pd.Timestamp("2020-02-01"))
        self.assertEqual(len(rows), 1)
        with self.assertRaises(ValueError):
            vt.training_rows(origins, pd.Timestamp("2019-01-01"))


class TestLongHistory(unittest.TestCase):
    def test_sala_after_panel_drops_the_provisional_weeks(self):
        panel = pd.DataFrame({"ubigeo": ["200101"], "anio": [2025], "semana": [52], "semana_inicio": ["2025-12-21"],
                              "casos_Dengue": [1]})
        sala = pd.DataFrame({"ubigeo": ["200101"] * 5, "anio": [2025, 2025, 2026, 2026, 2026],
                             "semana": [52, 53, 1, 2, 3], "casos_Dengue": [1, 2, 3, 4, 5]})
        after, provisional = lh.sala_after_panel(panel, sala, provisional=2)
        self.assertEqual(provisional, [(2026, 2), (2026, 3)])
        self.assertEqual(list(zip(after.anio, after.semana)), [(2025, 53), (2026, 1)])
        self.assertEqual(str(after.semana_inicio.iloc[0].date()), "2025-12-28")

    def test_week_grid(self):
        grid = lh.week_grid(2025, 2025)
        self.assertEqual((int(grid.semana.min()), int(grid.semana.max())), (1, 53))

    def test_labels_rule(self):
        cases = pd.DataFrame([{"ubigeo": "200101", "anio": y, "semana": 10, "semana_inicio": pd.Timestamp(f"{y}-03-05"),
                               "casos_Dengue": c} for y, c in zip(range(2000, 2007), (0, 0, 0, 0, 0, 5, 1))])
        labels = lh.long_labels(cases)
        self.assertEqual(list(labels.brote), [1, 0])  # 2006: 1 case is above the threshold but below the minimum


class TestWeatherWindows(unittest.TestCase):
    def test_gap_is_an_error_and_windows_need_every_week(self):
        weeks = pd.date_range("2024-01-07", periods=14, freq="W-SUN")
        data = pd.DataFrame({"ubigeo": "200101", "semana_inicio": weeks, "temp_media": np.arange(14.0)})
        out = cl.weather_windows(data).set_index("semana_origen")
        self.assertTrue(np.isnan(out.loc[weeks[11], "temp_media_media_s9_12"]))
        self.assertEqual(out.loc[weeks[12], "temp_media_media_s9_12"], np.mean([0, 1, 2, 3]))
        with self.assertRaises(ValueError):
            cl.weather_windows(data.drop(index=5))


if __name__ == "__main__":
    unittest.main()
