"""``prepare_load`` of the V4 labels each observation from the source record and never changes a count (HU0004-1).

Fixtures only: the heavy readers (validation, climate, geography, labels) are replaced and the real ones are exercised
by the Release test of ``tests/features/test_gold_v4_equivalence.py``. What runs for real here is the union of the panel
with the Sala weeks, the coverage labels and the records the database receives."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import pandas as pd

from denguekay.serving import v4_load

DISTRICTS = ["200101", "200102"]
# MMWR weeks: 2024 SE 51 starts 2024-12-15, 2025 SE 1 starts 2024-12-29.
PANEL_WEEKS = [(2024, 51, "2024-12-15"), (2024, 52, "2024-12-22"), (2025, 1, "2024-12-29")]
SALA_WEEKS = [(2025, 1), (2025, 2), (2025, 3)]


def panel():
    return pd.DataFrame([
        {"ubigeo": u, "anio": y, "semana": w, "semana_inicio": pd.Timestamp(start), "casos_Dengue": 4 if (u, w) == ("200101", 51) else 0,
         "temp_media": 25.0, "temp_min": 20.0, "temp_max": 30.0, "precip_total_mm": 1.0, "hum_rel_media": 70.0}
        for u in DISTRICTS for y, w, start in PANEL_WEEKS])


def history():
    # 200101 has a record (4 cases) in 2024 SE 51; no other district-week of 2024 has one.
    return pd.DataFrame({"ubigeo": ["200101"], "anio": [2024], "semana": [51], "casos_Dengue": [4]})


def sala():
    # The Sala publishes explicit points: 200101 for SE 1, 2 and 3 (zeros included) and 200102 for SE 2 and 3 only.
    rows = [("200101", y, w) for y, w in SALA_WEEKS] + [("200102", y, w) for y, w in SALA_WEEKS[1:]]
    return pd.DataFrame([{"ubigeo": u, "anio": y, "semana": w, "casos_Dengue": 0, "tipo_dx": "C"} for u, y, w in rows])


def run_prepare(panel_frame=None, history_frame=None, sala_frame=None):
    """``prepare_load`` on fixtures: the heavy readers are replaced, the rest runs for real."""
    with TemporaryDirectory() as folder:
        root = Path(folder)
        (panel() if panel_frame is None else panel_frame).to_csv(root / "panel.csv", index=False)
        (history() if history_frame is None else history_frame).to_csv(root / "history.csv", index=False)
        (sala() if sala_frame is None else sala_frame).to_csv(root / "sala.csv", index=False)
        pd.DataFrame({"lat": [0]}).to_csv(root / "coords.csv", index=False)
        options = {"perfil_datos": "fuentes", "semanas_provisionales": 0, "sala": str(root / "sala.csv"),
                   "era5_land": str(root / "x"), "chirps": str(root / "x"), "nino12": str(root / "x")}
        climate = pd.DataFrame({"ubigeo": DISTRICTS, "semana_inicio": pd.Timestamp("2024-12-15"),
                                "temp_media_era5_land_c": 24.0, "humedad_era5_land_pct": 60.0, "lluvia_chirps_mm": 0.5,
                                "fecha_era5_land_disponible": pd.NaT, "fecha_chirps_disponible": pd.NaT})
        with patch.multiple(v4_load, V4_INTEGRATED=root / "panel.csv", V4_HISTORY=root / "history.csv",
                            DISTRICT_COORDS=root / "coords.csv", source_hashes=lambda options: {"x": "1"},
                            validate_confirmed_panel=lambda *a: None, load_case_coverage=lambda *a: None,
                            coverage_path=lambda path: root / "none.csv",
                            load_ubigeo_catalog=lambda path: pd.DataFrame({"ubigeo": DISTRICTS}),
                            long_case_series=lambda recent, history_path: recent,
                            long_labels=lambda cases: cases.assign(brote=0, umbral_brote_casos=1.5),
                            _weekly_climate=lambda paths, panel: climate, _nino12=lambda path: [],
                            read_boundaries=lambda: {}), \
                patch("denguekay.data.validation.gx_quality.validate_integrated_gx", return_value={"exito": True}), \
                patch.object(v4_load.loader, "prepare_districts", return_value=([], [])), \
                patch.object(v4_load.loader, "census_population_2017", return_value={}):
            return v4_load.prepare_load(options)


class TestPrepareLoadLabels(unittest.TestCase):
    def prepare(self):
        return run_prepare()

    def test_each_observation_is_labelled_from_the_source_record_and_keeps_its_count(self):
        records = {(r["ubigeo"], r["id_semana"]): r for r in self.prepare().observaciones}
        self.assertEqual(len(records), 10)   # 2 districts x (3 panel weeks + 2 Sala weeks after the panel)
        expected = {
            ("200101", 202451): ("datos_abiertos_confirmados", "verificado", 4),     # in the history, with its cases
            ("200102", 202451): ("datos_abiertos_confirmados", "sin_registro", 0),   # no record: zero by project rule
            ("200101", 202452): ("datos_abiertos_confirmados", "sin_registro", 0),
            ("200101", 202501): ("sala_situacional", "verificado", 0),               # an explicit Sala zero
            ("200102", 202501): ("sala_situacional", "sin_registro", 0),             # the Sala has no point for it
            ("200101", 202502): ("sala_situacional", "verificado", 0),
            ("200102", 202503): ("sala_situacional", "verificado", 0),
        }
        for key, (source, coverage, cases) in expected.items():
            with self.subTest(key=key):
                self.assertEqual((records[key]["fuente_casos"], records[key]["estado_cobertura"],
                                  records[key]["casos_dengue"]), (source, coverage, cases))
        self.assertTrue(all(isinstance(ubigeo, str) and len(ubigeo) == 6 for ubigeo, _ in records))
        self.assertEqual({r["casos_dengue"] for r in records.values()} - {0, 4}, set())   # no count is invented


if __name__ == "__main__":
    unittest.main()
