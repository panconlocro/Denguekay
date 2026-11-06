"""Tests of climate step d (weather windows): window definitions, heavy-rain days, no leakage (G36 on synthetic
data), consistency with the 5-week means (G35b), availability (G38), the climatology and the preregistration."""

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

import phase1b_prime as pb  # noqa: E402
import phase_b3_full_climate as b3  # noqa: E402
import phase_b_rain as pbr  # noqa: E402
import phase_d_weather_windows as pd1  # noqa: E402
import preregistration as pr  # noqa: E402

UBIGEOS = ("200101", "200202")
N_WEEKS = 30


def _daily(seed=0):
    rng = np.random.default_rng(seed)
    days = pd.date_range("2005-01-02", periods=7 * N_WEEKS, freq="D")
    frames = []
    for u in UBIGEOS:
        rain = rng.gamma(0.6, 8.0, len(days))
        frames.append(pd.DataFrame({"ubigeo": u, "fecha": days, "precip_mm": rain}))
    return pd.concat(frames, ignore_index=True)


def _inputs(seed=0):
    daily = _daily(seed)
    wd = pd1.weekly_from_daily(daily)
    chirps = wd.rename(columns={"suma": "precip_total_mm"})[["ubigeo", "semana_inicio", "precip_total_mm"]].copy()
    chirps["fecha_disponible"] = chirps.semana_inicio + pd.Timedelta(days=6 + 5)
    rng = np.random.default_rng(seed + 1)
    era5 = chirps[["ubigeo", "semana_inicio"]].assign(temp_media=rng.uniform(18, 32, len(chirps)),
                                                      hum_rel_media=rng.uniform(40, 95, len(chirps)))
    origins = chirps[["ubigeo"]].assign(origen_cierre=chirps.semana_inicio + pd.Timedelta(days=6))
    return daily, wd, chirps, era5, origins.reset_index(drop=True)


class TestWindows(unittest.TestCase):
    def test_columns_of_the_preregistration(self):
        self.assertEqual(pd1.columns(), pr.STEP_D_COLUMNS)
        self.assertEqual(len(pr.STEP_D_COLUMNS), 14)
        self.assertFalse(any("nino" in c for c in pr.STEP_D_COLUMNS))
        self.assertEqual(pd1.HEAVY_RAIN_MM, pr.STEP_D_HEAVY_RAIN_MM)

    def test_window_definitions(self):
        """Each window is the mean of exactly its weeks; incomplete windows are NaN."""
        _, wd, chirps, era5, origins = _inputs()
        out = pd1.build_d1(origins, chirps, era5, wd)
        u = UBIGEOS[1]
        series = chirps[chirps.ubigeo.eq(u)].precip_total_mm.to_numpy()
        rows = out[out.ubigeo.eq(u)].reset_index(drop=True)
        for o in range(N_WEEKS):
            for name, (a, b) in pd1.WINDOWS.items():
                got = rows.loc[o, f"precip_total_mm_{name}"]
                if o - b < 0:
                    self.assertTrue(np.isnan(got), (o, name))
                else:
                    self.assertAlmostEqual(got, series[o - b:o - a + 1].mean(), places=12)
        temp = era5[era5.ubigeo.eq(u)].temp_media.to_numpy()
        self.assertAlmostEqual(rows.loc[20, "temp_media_media_s5_8"], temp[12:16].mean(), places=12)
        self.assertEqual(rows.loc[20, "precip_total_mm_ultima_semana"], chirps[chirps.ubigeo.eq(u)].semana_inicio.iloc[20])

    def test_heavy_rain_days(self):
        """Days with >= 20 mm (20.0 counts, 19.99 does not), summed over o-3..o and o-7..o-4."""
        daily, *_ = _inputs()
        daily = daily.copy()
        daily["precip_mm"] = 0.0
        first = daily.ubigeo.eq(UBIGEOS[0])
        days = daily.loc[first, "fecha"]
        daily.loc[first & daily.fecha.eq(days.iloc[7 * 8 + 1]), "precip_mm"] = 20.0     # week 8
        daily.loc[first & daily.fecha.eq(days.iloc[7 * 8 + 2]), "precip_mm"] = 19.99    # week 8, not heavy
        daily.loc[first & daily.fecha.eq(days.iloc[7 * 5 + 3]), "precip_mm"] = 45.0     # week 5
        wd = pd1.weekly_from_daily(daily)
        self.assertEqual(wd.dias_fuertes.sum(), 2)
        _, _, chirps, era5, origins = _inputs()
        chirps = chirps.assign(precip_total_mm=wd.suma.to_numpy())
        out = pd1.build_d1(origins, chirps, era5, wd)
        rows = out[out.ubigeo.eq(UBIGEOS[0])].reset_index(drop=True)
        self.assertEqual(rows.loc[8, "dias_precip_20mm_s0_3"], 2)    # weeks 5..8
        self.assertEqual(rows.loc[9, "dias_precip_20mm_s0_3"], 1)    # weeks 6..9
        self.assertEqual(rows.loc[12, "dias_precip_20mm_s4_7"], 2)   # weeks 5..8
        self.assertEqual(rows.loc[13, "dias_precip_20mm_s4_7"], 1)   # weeks 6..9 (the 20.0 of week 8)
        self.assertTrue(np.isnan(rows.loc[6, "dias_precip_20mm_s4_7"]))

    def test_no_leakage_by_perturbation(self):
        """G36 on synthetic data: weather after the origin week does not change any d1 column."""
        _, wd, chirps, era5, origins = _inputs()
        cut = chirps.semana_inicio.iloc[18]
        g = pd1.guard_no_leakage_real(origins, chirps, era5, wd, str(cut.date()))
        self.assertTrue(g["sin_cambios"])
        self.assertGreater(g["origenes_posteriores_que_cambian"], 0)
        self.assertTrue(g["pasa"])

    def test_daily_matches_silver_and_consistency(self):
        """G35a and G35b on synthetic data."""
        _, wd, chirps, era5, origins = _inputs()
        self.assertTrue(pd1.guard_daily_matches_silver(wd, chirps)["pasa"])
        broken = chirps.copy()
        broken.loc[3, "precip_total_mm"] += 0.5
        self.assertFalse(pd1.guard_daily_matches_silver(wd, broken)["pasa"])
        out = pd1.build_d1(origins, chirps, era5, wd)
        out = pbr.add_rain(out, pbr.rain_by_origin_week(chirps))
        out = pb.add_humidity(out, pb.humidity_by_origin_week(era5[["ubigeo", "semana_inicio", "hum_rel_media"]]))
        out = b3.add_temperature(out, b3.temperature_by_origin_week(era5[["ubigeo", "semana_inicio", "temp_media"]]))
        self.assertTrue(pd1.guard_consistency(out)["pasa"])

    def test_availability_and_coverage(self):
        _, wd, chirps, era5, origins = _inputs()
        out = pd1.build_d1(origins, chirps, era5, wd)
        g = pd1.guard_availability(out)
        self.assertTrue(g["pasa"])
        self.assertEqual(g["por_fuente"]["precip_total_mm"]["margen_minimo_dias"], 9)   # +5 published vs +14
        late = chirps.copy()
        late.loc[late.index[20], "fecha_disponible"] += pd.Timedelta(days=30)
        g = pd1.guard_availability(pd1.build_d1(origins, late, era5, wd))
        self.assertFalse(g["por_fuente"]["precip_total_mm"]["pasa"])
        self.assertFalse(g["por_fuente"]["dias_precip_20mm"]["pasa"])
        self.assertFalse(pd1.guard_availability(out, era5_delay_days=15)["pasa"])
        cov = pd1.guard_coverage(out, since="2005-03-27")   # week 12 onwards has every window
        self.assertTrue(cov["pasa"])
        self.assertFalse(pd1.guard_coverage(out, since="2005-01-01")["pasa"])


class TestMetrics(unittest.TestCase):
    def _series(self):
        weeks = pd.date_range("2005-01-02", "2009-12-27", freq="7D")
        cal = pd.DataFrame({"semana_inicio": weeks})
        cal["semana"] = cal.semana_inicio.dt.isocalendar().week.astype(int).clip(upper=52)
        rows = []
        for u in UBIGEOS:
            s = cal.assign(ubigeo=u)
            s["brote"] = ((s.semana.between(8, 12)) & (u == UBIGEOS[0])).astype(int)
            rows.append(s)
        return pd.concat(rows, ignore_index=True)

    def test_climatology_uses_only_closed_labels(self):
        series = self._series()
        target = pd.Timestamp("2009-03-01")
        wk = int(series.loc[series.semana_inicio.eq(target), "semana"].iloc[0])
        pred = pd.DataFrame({"ubigeo": list(UBIGEOS), "semana_inicio": [target] * 2, "horizonte": 2,
                             "bloque": "temporada_2009", "origen_cierre": [pd.Timestamp("2009-02-14")] * 2})
        clim = pd1.climatology(pred, series)
        hist = series[(series.semana_inicio + pd.Timedelta(days=6)) <= pd.Timestamp("2009-02-14")]
        near = hist[(hist.semana - wk).abs().le(2) & hist.ubigeo.eq(UBIGEOS[0])]
        self.assertAlmostEqual(clim.iloc[0], near.brote.mean())
        self.assertEqual(clim.iloc[1], 0.0)
        # a label after the cutoff must not move the climatology
        later = series.copy()
        later.loc[later.semana_inicio.gt(pd.Timestamp("2009-02-14")), "brote"] = 1
        self.assertEqual(pd1.climatology(pred, later).tolist(), clim.tolist())

    def test_reported_metrics(self):
        rng = np.random.default_rng(3)
        n = 200
        y = rng.integers(0, 2, n)
        data = pd.DataFrame({"horizonte": 2, "bloque": "temporada_2022", "brote": y,
                             "probabilidad_calibrada": np.clip(y * 0.6 + rng.uniform(0, 0.4, n), 0, 1),
                             "persistencia": rng.integers(0, 10, n), "umbral_brote_casos": 5.0})
        clim = pd.Series(np.full(n, y.mean()), index=data.index)
        m = pd1.reported_metrics(data, clim, ["temporada_2022"]).iloc[0]
        self.assertAlmostEqual(m.brier_climatologia, y.mean() * (1 - y.mean()))
        self.assertAlmostEqual(m.bss_climatologia, 1 - m.brier / m.brier_climatologia)
        self.assertEqual(m.n_bajo_umbral, int((data.persistencia < 5).sum()))
        self.assertGreater(m.bss_climatologia, 0)


class TestRule(unittest.TestCase):
    def test_rule_is_the_one_of_b3(self):
        def v(*verdicts):
            return pd.DataFrame({"horizonte": [2, 3, 4], "veredicto": list(verdicts)})

        self.assertTrue(pr.adopt_step_d(v("gana", "gana", "empate"), v("empate", "empate", "empate")))
        self.assertTrue(pr.adopt_step_d(v("empate", "empate", "empate"), v("gana", "gana", "empate")))
        self.assertFalse(pr.adopt_step_d(v("gana", "gana", "empate"), v("empate", "pierde", "empate")))
        self.assertFalse(pr.adopt_step_d(v("gana", "gana", "gana"), v("compensa (empate)", "empate", "empate")))
        self.assertFalse(pr.adopt_step_d(v("empate", "empate", "empate"), v("empate", "empate", "empate")))

    def test_record(self):
        self.assertIn("pendiente de la revisión de Rosa", pr.STEP_D["estado"])
        self.assertEqual(pr.STEP_D["columnas"], pr.STEP_D_COLUMNS)
        self.assertEqual(set(pr.STEP_D["comparaciones"]), {"d1_frente_a_L_5a", "d1_frente_a_b3"})


if __name__ == "__main__":
    unittest.main()
