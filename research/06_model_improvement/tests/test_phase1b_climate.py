"""Tests of the phase 1b weather consistency comparison (synthetic weekly tables, no data)."""

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

import phase1b_climate as cl  # noqa: E402


def _weekly(shift: float = 0.0, weeks: int = 10) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    rows = []
    for d in (1, 2):
        for i, w in enumerate(pd.date_range("2017-01-01", periods=weeks, freq="7D")):
            rows.append({"id_distrito": d, "semana_inicio": w, "anio": 2017 + (i >= weeks // 2),
                         **{v: float(rng.uniform(10, 30)) for v in cl.WEEKLY_VARIABLES}})
    t = pd.DataFrame(rows)
    t["temp_media"] = t["temp_media"] + shift
    return t


class TestCompare(unittest.TestCase):
    def test_identical_caches(self):
        a = _weekly()
        s = cl.compare(cl.paired(a, a.copy())).set_index("variable")
        self.assertTrue((s.iguales == 1).all())
        self.assertTrue((s.mae == 0).all())
        self.assertTrue(np.allclose(s.correlacion, 1))
        self.assertEqual(cl.coverage(a, a), {"semanas_actual": 20, "semanas_fijo": 20, "solo_actual": 0,
                                             "solo_fijo": 0})

    def test_shift_is_fixed_minus_current_and_by_year(self):
        a, f = _weekly(), _weekly(shift=0.5)
        s = cl.compare(cl.paired(a, f), by=["anio"])
        t = s[s.variable.eq("temp_media")]
        self.assertEqual(sorted(t.anio), [2017, 2018])
        self.assertTrue(np.allclose(t.diferencia_media, 0.5))
        self.assertTrue(np.allclose(t.mae, 0.5))
        other = s[s.variable.eq("precip_total_mm")]
        self.assertTrue((other.mae == 0).all())

    def test_only_shared_weeks_are_paired(self):
        a, f = _weekly(weeks=10), _weekly(weeks=8)
        self.assertEqual(len(cl.paired(a, f)), 16)
        self.assertEqual(cl.coverage(a, f)["solo_actual"], 4)


class TestSharedCells(unittest.TestCase):
    def test_nearest_cell_and_sharing(self):
        districts = pd.DataFrame({"id_distrito": [1, 2, 3], "distrito": ["A", "B", "C"],
                                  "lat": [-5.01, -5.06, -5.40], "lon": [-80.02, -79.99, -80.6]})
        cells = cl.nearest_era5_cell(districts)
        self.assertEqual(cells.lat_celda.tolist(), [-5.0, -5.0, -5.5])
        s = cl.shared_cells(cells)
        self.assertEqual((s["celdas"], s["distritos_que_comparten"], s["grupos"]), (2, 2, [[1, 2]]))

    def test_identical_series(self):
        a = _weekly()
        b = a[a.id_distrito.eq(1)].assign(id_distrito=3)  # district 3 copies district 1
        r = cl.identical_series(pd.concat([a, b]))
        self.assertEqual((r["distritos"], r["series_distintas"], r["grupos"]), (3, 2, [[1, 3]]))


if __name__ == "__main__":
    unittest.main()
