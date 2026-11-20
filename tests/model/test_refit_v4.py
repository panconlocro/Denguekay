"""Refit of the frozen V4: the pieces that do not need data/ (windows, Niño, mixture weight, history and calibration)."""

import json
from tempfile import TemporaryDirectory
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from xgboost import XGBRegressor

from denguekay.config.paths import V4_FROZEN
from denguekay.features.b3 import NINO
from denguekay.model import refit_v4 as refit

DAY = pd.Timedelta(days=1)


def weekly(values, start="2026-01-04"):
    weeks = pd.date_range(start, periods=len(values), freq="W-SUN")
    return pd.DataFrame({"ubigeo": "200101", "semana_inicio": weeks, "temp_media": values})


class TestWindows(unittest.TestCase):
    def test_the_weeks_used_at_origin_o_are_o_minus_6_to_o_minus_2(self):
        """Same definition as ``b3.climate_vector`` at serving time."""
        values = list(range(1, 13))
        frame = weekly(values)
        origin_index = 10
        origin = frame.semana_inicio.iloc[origin_index]
        out = refit.window_means(frame, "temp_media", origin)
        got = out.loc[out.semana_origen.eq(origin), "temp_media_media5_h2_obs"].iloc[0]
        self.assertEqual(got, np.mean(values[origin_index - 6: origin_index - 1]))

    def test_a_gap_leaves_the_windows_that_touch_it_empty(self):
        values = list(range(1, 17))
        frame = weekly(values)
        gapped = frame.drop(index=5)
        out = refit.window_means(gapped, "temp_media", frame.semana_inicio.iloc[15]).set_index("semana_origen")
        column = "temp_media_media5_h2_obs"
        self.assertTrue(pd.isna(out.loc[frame.semana_inicio.iloc[9], column]))    # window 3..7 includes index 5
        self.assertEqual(out.loc[frame.semana_inicio.iloc[13], column], np.mean(values[7:12]))   # window 7..11

    def test_origins_after_the_last_week_are_covered_with_empty_values(self):
        frame = weekly(list(range(1, 9)))
        origin = frame.semana_inicio.iloc[7] + 14 * DAY
        out = refit.window_means(frame, "temp_media", origin)
        self.assertIn(origin, set(out.semana_origen))


class TestNino(unittest.TestCase):
    def enso(self, availability=None):
        months = pd.period_range("2026-01", periods=6, freq="M")
        frame = pd.DataFrame({"anio": months.year, "mes": months.month, "nino12_anom": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]})
        frame["fecha_disponible"] = (months + 1).to_timestamp() + 9 * DAY if availability is None else availability
        return frame

    def test_mean_of_the_last_three_months_available_at_each_origin(self):
        origins = pd.DataFrame({"origen_cierre": pd.to_datetime(["2026-04-30", "2026-05-20", "2026-07-20"])})
        got = refit.nino_at_origins(origins, self.enso())
        # April 30: months available are Jan, Feb, Mar (published Feb 10, Mar 10, Apr 10): mean 2.
        # May 20: also April (published May 10): mean of Feb, Mar, Apr = 3.
        self.assertEqual(list(got[:2]), [2.0, 3.0])
        self.assertEqual(got[2], 5.0)     # July 20: through June (published July 10)

    def test_missing_months_are_rejected(self):
        enso = self.enso().drop(index=2)
        with self.assertRaises(ValueError):
            refit.nino_at_origins(pd.DataFrame({"origen_cierre": pd.to_datetime(["2026-06-01"])}), enso)

    def test_an_origin_before_the_third_month_has_no_value(self):
        got = refit.nino_at_origins(pd.DataFrame({"origen_cierre": pd.to_datetime(["2026-02-20"])}), self.enso())
        self.assertTrue(np.isnan(got[0]))


class TestMixtureWeight(unittest.TestCase):
    def test_best_weight_by_mae_and_ties_go_to_the_largest(self):
        mu = np.array([10.0, 10.0])
        persistence = np.array([0.0, 0.0])
        observed = np.array([10.0, 10.0])
        self.assertEqual(refit.fit_w(mu, persistence, observed), 1.0)
        # model and persistence give the same count: every weight ties, the largest wins
        self.assertEqual(refit.fit_w(np.array([4.0, 4.0]), np.array([4.0, 4.0]), np.array([1.0, 2.0])), 1.0)
        # the persistence is exact: w = 0
        self.assertEqual(refit.fit_w(np.array([0.0, 0.0]), np.array([3.0, 3.0]), np.array([3.0, 3.0])), 0.0)

    def test_the_weight_is_found_on_the_grid(self):
        mu, persistence = np.array([8.0, 8.0, 8.0]), np.array([2.0, 2.0, 2.0])
        observed = np.array([5.0, 5.0, 5.0])    # 0.5·8 + 0.5·2 = 5
        self.assertEqual(refit.fit_w(mu, persistence, observed), 0.5)


def block(name, first_target, weeks, horizon, positives, cut=None):
    """Synthetic out-of-sample block: three districts, ``weeks`` target weeks."""
    rows = []
    start = pd.Timestamp(first_target)
    for week in range(weeks):
        for i, ubigeo in enumerate(("200101", "200102", "200103")):
            target = start + week * 7 * DAY
            outbreak = int((week + i) % positives == 0)
            rows.append({"ubigeo": ubigeo, "anio": target.year, "semana": 1 + week, "semana_inicio": target,
                         "origen_cierre": target - (horizon - 1) * 7 * DAY - DAY, "horizonte": horizon,
                         "bloque": name, "casos_Dengue": 3 * outbreak, "brote": outbreak, "umbral_brote_casos": 2.0,
                         "persistencia": 1.0, "estacional": 1.0,
                         "casos_predichos": 1.0 + 2 * outbreak, "probabilidad_brote": 0.2 + 0.6 * outbreak,
                         "corte": cut or pd.Timestamp(first_target) - 30 * DAY})
    return rows


def synthetic(names_starts, horizons=(2, 3, 4), weeks=40, positives=4):
    rows = []
    for h in horizons:
        for name, start in names_starts:
            rows += block(name, start, weeks, h, positives)
    return pd.DataFrame(rows)


class TestHistory(unittest.TestCase):
    def archived(self):
        data = synthetic([("temporada_2025", "2024-09-01"), ("temporada_2026", "2025-09-07"),
                          (refit.REPLACED_BLOCK, "2026-09-06")])
        data = data.rename(columns={"casos_predichos": "mu_modelo", "probabilidad_brote": "probabilidad_cruda"})
        return data.assign(probabilidad_calibrada=np.nan, conteo_publicado=data.mu_modelo, w_mezcla=1.0)

    def test_the_replaced_block_is_dropped_and_the_new_blocks_are_scored(self):
        history = self.archived()
        new = synthetic([("temporada_2027", "2026-09-06")])
        table = refit.extend_history(history, new)
        self.assertNotIn(refit.REPLACED_BLOCK, set(table.bloque))
        self.assertEqual(set(table.bloque), {"temporada_2025", "temporada_2026", "temporada_2027"})
        fresh = table[table.bloque.eq("temporada_2027")]
        self.assertEqual(len(fresh), len(new))
        self.assertTrue(fresh.probabilidad_calibrada.between(0, 1).all())
        self.assertTrue(fresh.w_mezcla.between(0, 1).all())
        # the archived blocks keep their values untouched
        old = table[table.bloque.eq("temporada_2025")].reset_index(drop=True)
        pd.testing.assert_frame_equal(old, history[history.bloque.eq("temporada_2025")][refit.HISTORY_COLUMNS]
                                      .reset_index(drop=True))

    def test_without_new_blocks_only_the_partial_one_is_removed(self):
        table = refit.extend_history(self.archived(), synthetic([]).reindex(columns=[]))
        self.assertEqual(set(table.bloque), {"temporada_2025", "temporada_2026"})

    def test_the_new_block_is_calibrated_without_its_own_labels(self):
        history = self.archived()
        new = synthetic([("temporada_2027", "2026-09-06")])
        flipped = new.assign(brote=1 - new.brote, casos_Dengue=new.casos_Dengue + 5)
        a = refit.extend_history(history, new)
        b = refit.extend_history(history, flipped)
        pick = lambda t: t[t.bloque.eq("temporada_2027")].sort_values(["horizonte", "ubigeo", "semana_inicio"])
        np.testing.assert_allclose(pick(a).probabilidad_calibrada, pick(b).probabilidad_calibrada)
        np.testing.assert_allclose(pick(a).w_mezcla, pick(b).w_mezcla)

    def test_read_history_rejects_a_fit_after_its_origin_and_duplicates(self):
        data = self.archived()
        with TemporaryDirectory() as folder:
            path = Path(folder) / "historial.csv.gz"
            data.to_csv(path, index=False)
            self.assertEqual(len(refit.read_history(path)), len(data))
            late = data.assign(corte=data.origen_cierre + 7 * DAY)
            late.to_csv(path, index=False)
            with self.assertRaises(ValueError):
                refit.read_history(path)
            pd.concat([data, data.iloc[:1]]).to_csv(path, index=False)
            with self.assertRaises(ValueError):
                refit.read_history(path)

    def test_calibration_summary_is_a_platt_fit_with_its_rows(self):
        data = self.archived()
        data = data[data.horizonte.eq(2)]
        out = refit.calibrate(data, data.probabilidad_cruda)
        self.assertEqual(out["filas"], len(data))
        self.assertGreater(out["a"], 0)
        self.assertEqual(out["ultimo_cierre"], str((data.semana_inicio.max() + 6 * DAY).date()))


class TestMixing(unittest.TestCase):
    def test_the_first_block_keeps_the_model_count_and_later_ones_use_a_fitted_weight(self):
        data = synthetic([("temporada_2025", "2024-09-01"), ("temporada_2026", "2025-09-07")], horizons=(2,))
        mixed = refit.mix_chronologically(data)
        first = mixed[mixed.bloque.eq("temporada_2025")]
        self.assertTrue(first.w_mezcla.eq(1.0).all())
        pd.testing.assert_series_equal(first.conteo_publicado, first.casos_predichos, check_names=False)
        second = mixed[mixed.bloque.eq("temporada_2026")]
        self.assertTrue(second.w_mezcla.between(0, 1).all())
        np.testing.assert_allclose(second.conteo_publicado,
                                   second.w_mezcla * second.casos_predichos + (1 - second.w_mezcla) * second.persistencia)


def tiny_regressor(columns=("hist_lag_a", "hist_media_4")):
    """A real multi-output booster over synthetic origins (3 outputs, as the V4 booster)."""
    rng = np.random.default_rng(0)
    x = pd.DataFrame(rng.integers(0, 6, size=(200, len(columns))).astype(float), columns=list(columns))
    y = np.column_stack([x.iloc[:, 0] + h for h in (2, 3, 4)])
    model = XGBRegressor(objective="count:poisson", n_estimators=3, max_depth=2, tree_method="hist",
                         multi_strategy="multi_output_tree", random_state=17, n_jobs=1).fit(x, y)
    return model, x.assign(semana_inicio=pd.Timestamp("2005-01-02"))


class TestImportancesFile(unittest.TestCase):
    def package(self, folder, **changes):
        model, train = tiny_regressor()
        columns = ["hist_lag_a", "hist_media_4"]
        payload = refit.importances_payload(model, train, columns)
        (Path(folder) / refit.IMPORTANCES_FILE).write_text(json.dumps({**payload, **changes}), encoding="utf-8")
        config = {"semilla_demo": 17, "columnas": {"b3_obs": columns},
                  "modelos": {"b3_obs_s17": {"filas_entrenamiento": len(train)}}}
        return config, payload

    def test_the_payload_ranks_every_column_per_horizon_and_records_the_training_rows(self):
        model, train = tiny_regressor()
        payload = refit.importances_payload(model, train, ["hist_lag_a", "hist_media_4"])
        self.assertEqual((payload["filas"], payload["inicio"]), (200, "2005-01-02"))
        self.assertEqual(set(payload["importancias"]), {"2", "3", "4"})
        for rows in payload["importancias"].values():
            self.assertEqual([row["rango"] for row in rows], [1, 2])
            self.assertGreaterEqual(rows[0]["importancia"], rows[1]["importancia"])

    def test_a_package_file_is_read_with_integer_horizons(self):
        with TemporaryDirectory() as folder:
            config, payload = self.package(folder)
            read = refit.read_importances(folder, config)
            self.assertEqual(set(read["importancias"]), {2, 3, 4})
            self.assertEqual(read["importancias"][2], payload["importancias"]["2"])

    def test_a_file_that_does_not_match_the_fit_is_refused(self):
        for changes in ({"filas": 199}, {"columnas": ["hist_lag_a"]}, {"tipo": "gain"}):
            with self.subTest(changes=changes), TemporaryDirectory() as folder:
                config, _ = self.package(folder, **changes)
                with self.assertRaises(ValueError):
                    refit.read_importances(folder, config)

    def test_missing_ranks_or_variables_are_refused(self):
        with TemporaryDirectory() as folder:
            config, payload = self.package(folder)
            broken = json.loads(json.dumps(payload["importancias"]))
            broken["3"][0]["rango"] = 2
            self.package(folder, importancias=broken)
            with self.assertRaises(ValueError):
                refit.read_importances(folder, config)


class TestFrozenSourcesGuard(unittest.TestCase):
    def test_a_missing_or_different_input_is_refused_before_anything_is_built(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            names = ("panel", "history", "sala", "era", "chirps", "enso", "geo")
            sources = {key: root / f"{name}.csv" for key, name in zip(
                ("panel_path", "history_path", "sala_path", "era_path", "chirps_path", "enso_path", "geography"), names)}
            for path in sources.values():
                path.write_text("x", encoding="utf-8")
            (root / "panel.coverage.csv").write_text("x", encoding="utf-8")
            with patch.object(refit, "ROOT", root), patch.object(refit, "coverage_path",
                                                                  lambda path: root / "panel.coverage.csv"):
                declared = {path.name: refit.sha256_file(path) for path in [*sources.values(), root / "panel.coverage.csv"]}
                declared["geografia"] = declared["geo.csv"]
                config = {"fuentes": declared}
                refit.check_frozen_sources(config, sources)   # all declared and equal: accepted
                (root / "enso.csv").write_text("other", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "enso.csv difiere"):
                    refit.check_frozen_sources(config, sources)
                (root / "enso.csv").unlink()
                with self.assertRaisesRegex(ValueError, "Falta el insumo enso.csv"):
                    refit.check_frozen_sources(config, sources)


@unittest.skip("refit() no se puede ejecutar de punta a punta con xgboost 3.4.1: su aserción de exactitud entre el booster "
               "en memoria y el recargado falla por ~1e-7, también en develop (problema preexistente, ver el PR)")
class TestRefitKeepsItsImportances(unittest.TestCase):
    def test_a_refit_at_the_frozen_cutoff_writes_and_registers_the_importances_of_its_own_matrix(self):
        with TemporaryDirectory() as folder:
            output = Path(folder) / "paquete"
            config = refit.refit(output, base=V4_FROZEN, **refit.frozen_sources())
            self.assertIn(refit.IMPORTANCES_FILE, config["archivos"])
            self.assertEqual(config["archivos"][refit.IMPORTANCES_FILE], refit.sha256_file(output / refit.IMPORTANCES_FILE))
            read = refit.read_importances(output, config)
            self.assertEqual((read["filas"], config["modelos"]["b3_obs_s17"]["filas_entrenamiento"]), (73775, 73775))


class TestWriteImportances(unittest.TestCase):
    def test_the_file_is_written_where_the_package_hashes_it_and_read_back(self):
        model, train = tiny_regressor()
        columns = ["hist_lag_a", "hist_media_4"]
        with TemporaryDirectory() as folder:
            payload = refit.write_importances(folder, model, train, columns)
            path = Path(folder) / refit.IMPORTANCES_FILE
            self.assertTrue(path.is_file())
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), payload)
            config = {"semilla_demo": 17, "columnas": {"b3_obs": columns},
                      "modelos": {"b3_obs_s17": {"filas_entrenamiento": len(train)}}}
            self.assertEqual(refit.read_importances(folder, config)["importancias"][4], payload["importancias"]["4"])


if __name__ == "__main__":
    unittest.main()
