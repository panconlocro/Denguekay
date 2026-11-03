"""Tests of phase 5 (counts): mixture with persistence, max_delta_step selection and the decision rule."""

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

import phase1_history as p1  # noqa: E402
import phase3_onsets as p3  # noqa: E402
import phase5_counts as p5  # noqa: E402
import preregistration as pr  # noqa: E402
from test_phase2_calibration import _pred  # noqa: E402
from test_phase3_onsets import BLOCKS, _inputs  # noqa: E402


def _counts(seed: int = 0) -> pd.DataFrame:
    p = _pred(seed)
    rng = np.random.default_rng(seed)
    p["persistencia"] = rng.poisson(3, len(p)).astype(float)
    p["casos_Dengue"] = (0.6 * p.persistencia + rng.poisson(1, len(p))).astype(float)
    p["casos_predichos"] = p.casos_Dengue + rng.normal(0, 2, len(p)).clip(-1)
    return p


class TestMixture(unittest.TestCase):
    def test_fit_w(self):
        y = np.array([1.0, 2.0, 3.0])
        self.assertEqual(p5.fit_w(y, y + 5, y), 1.0)       # the model is exact
        self.assertEqual(p5.fit_w(y + 5, y, y), 0.0)       # persistence is exact
        self.assertEqual(p5.fit_w(y, y, y), 1.0)           # tie -> the largest w

    def test_first_block_keeps_the_model_and_w_is_recorded(self):
        mixed, record = p5.mix_chronologically(_counts())
        first = record.sort_values("corte").groupby("horizonte").head(1)
        self.assertTrue((first.w == 1.0).all())
        self.assertTrue((first.filas_ajuste == 0).all())
        base = _counts()
        b = base.bloque.eq("temporada_2008")
        np.testing.assert_array_equal(mixed.loc[b, "casos_predichos"].to_numpy(), base.loc[b, "casos_predichos"].to_numpy())
        self.assertTrue(record.w.between(0, 1).all())

    def test_no_leakage_of_w(self):
        """G11: labels and cases that close after a block's cut-off do not change its w."""
        from denguekay.evaluation import protocol as pa

        base = _counts(1)
        first = base[base.bloque.eq("temporada_2010")]
        key = ["horizonte", "bloque"]
        _, a = p5.mix_chronologically(base)
        for h, g in first.groupby("horizonte"):
            cut = pa.block_cutoff(g.assign(semana_inicio=pd.to_datetime(g.semana_inicio),
                                           origen_cierre=pd.to_datetime(g.origen_cierre)))
            altered = base.copy()
            later = (altered.semana_inicio + pd.Timedelta(days=6)).gt(cut)
            altered.loc[later, "casos_Dengue"] = altered.loc[later, "casos_Dengue"] * 5 + 3
            _, b = p5.mix_chronologically(altered)
            wa, wb = a.set_index(key).w, b.set_index(key).w
            self.assertEqual(wa[(h, "temporada_2010")], wb[(h, "temporada_2010")])
            self.assertFalse(wa.equals(wb))  # later blocks see the change: the test is not vacuous

    def test_probability_is_untouched(self):
        base = _counts(2)
        mixed, _ = p5.mix_chronologically(base)
        np.testing.assert_array_equal(mixed.probabilidad_brote.to_numpy(), base.probabilidad_brote.to_numpy())


class TestMaxDeltaStep(unittest.TestCase):
    def test_g12_grid_of_the_reference_reproduces_l(self):
        from denguekay.model import frozen_configs as cf

        _, matrices, origins, _ = _inputs()
        c = cf.CONFIG_2026_V1
        a = p1.predict_blocks(matrices, origins, BLOCKS, 17, c["columnas"], c["hiperparametros"])
        b = p3.predict_blocks_weighted(matrices, origins, BLOCKS, 17, c["columnas"], c["hiperparametros"],
                                       hyperparameters_fn=p5.mds_selector(c["hiperparametros"], grid=(0.7,)))
        for col in ("casos_predichos", "probabilidad_brote"):
            np.testing.assert_array_equal(a[col].to_numpy(), b[col].to_numpy())
        self.assertTrue((b.attrs["ajustes"].hp_max_delta_step == 0.7).all())

    def test_selection_uses_only_training_origins(self):
        """G12: the choice of a block does not depend on origins outside its training."""
        from denguekay.model import frozen_configs as cf

        _, matrices, origins, _ = _inputs()
        c = cf.CONFIG_2026_V1
        cutoff = pd.Timestamp("2006-08-26")
        train = p3._training(origins, cutoff)
        margin = __import__("denguekay.model.probabilistic_output", fromlist=["e3_margin"]).e3_margin(origins, "S4_s3")
        choose = p5.mds_selector(c["hiperparametros"], grid=(0.7, 2.0, 5.0))
        a = choose(train, margin, c["columnas"], 17)
        altered = origins.copy()
        outside = ~altered.index.isin(train.index)
        altered.loc[outside, "casos_Dengue_h2"] = 999.0
        b = choose(p3._training(altered, cutoff), margin, c["columnas"], 17)
        self.assertEqual(a["max_delta_step"], b["max_delta_step"])
        self.assertIn(a["max_delta_step"], (0.7, 2.0, 5.0))


BLOCKS5 = [pr.block_name(s) for s in pr.DECIDING_SEASONS]


def _metrics(mae, rmse=(1.0,) * 5, f1=(0.5,) * 5):
    return pd.DataFrame([{"horizonte": 2, "bloque": b, "razon_mae": m, "razon_rmse": r, "f1_050": f, "auprc": 0.5,
                          "brier": 0.1} for b, m, r, f in zip(BLOCKS5, mae, rmse, f1)])


def _ranges():
    return pd.DataFrame([{"horizonte": 2, "bloque": b, **{m: 0.01 for m in pr.PHASE5_DIRECTION}} for b in BLOCKS5])


def _lead(diff=0.0, low=-0.1, high=0.1):
    return pd.DataFrame([{"horizonte": 2, "ic95_inferior": low, "ic95_superior": high,
                          **{f"diferencia_{b}": diff for b in BLOCKS5}, **{f"episodios_{b}": 20 for b in BLOCKS5}}])


class TestDecidePhase5(unittest.TestCase):
    ref = _metrics((1.0,) * 5)

    def _v(self, cand, ref=None, lead=None):
        return pr.decide_phase5(cand, ref if ref is not None else self.ref, _ranges(),
                                lead if lead is not None else _lead()).iloc[0]

    def test_mae_decides(self):
        self.assertEqual(self._v(_metrics((0.9, 0.9, 0.9, 0.9, 1.0))).veredicto, "gana")
        self.assertEqual(self._v(_metrics((0.9, 0.9, 0.9, 1.0, 1.0))).veredicto, "empate")
        self.assertEqual(self._v(_metrics((0.9, 0.9, 0.9, 0.9, 1.1))).veredicto, "empate")

    def test_symmetric(self):
        cand = _metrics((0.9, 0.9, 0.9, 0.9, 1.0))
        self.assertEqual(self._v(self.ref, ref=cand).veredicto, "pierde")

    def test_rmse_and_f1_guard(self):
        v = self._v(_metrics((0.9,) * 5, rmse=(1.1, 1.1, 1.1, 1.0, 1.0)))
        self.assertEqual((v.veredicto, v.vetos), ("compensa (empate)", "razon_rmse"))
        v = self._v(_metrics((0.9,) * 5, f1=(0.4, 0.4, 0.4, 0.5, 0.5)))
        self.assertEqual((v.veredicto, v.vetos), ("compensa (empate)", "f1_050"))

    def test_lead_time_guard(self):
        v = self._v(_metrics((0.9,) * 5), lead=_lead(diff=-0.1, low=-0.2, high=-0.01))
        self.assertEqual((v.veredicto, v.vetos), ("compensa (empate)", "antelacion"))

    def test_adoption_and_record(self):
        v = lambda *xs: pd.DataFrame({"horizonte": [2, 3, 4], "veredicto": list(xs)})
        self.assertTrue(pr.adopt_phase5(v("gana", "gana", "empate")))
        self.assertFalse(pr.adopt_phase5(v("gana", "compensa (empate)", "gana")))
        self.assertEqual(p5.MDS_GRID[0], p5.MDS_REFERENCE)
        self.assertIn("5c_peso_temporada", pr.PHASE5["variantes"])


if __name__ == "__main__":
    unittest.main()
