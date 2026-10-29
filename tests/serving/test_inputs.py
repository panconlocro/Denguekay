"""ServingInputs from the database: only the requested inputs, and the climate as loaded (M5)."""

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from backend_support import datos_muestra, leer_csv, motor_temporal
from denguekay.db.models import EpiWeek
from denguekay.db.session import transaction
from denguekay.serving.inputs import build_inputs
from denguekay.serving.load_data import persist_load


class TestInputs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        path = Path(cls.folder.name)
        load = datos_muestra(path)
        cls.load = replace(load, observaciones=[o for o in load.observaciones if o["id_semana"] >= 202530])
        cls.engine = motor_temporal(path)
        with transaction(cls.engine) as s:
            persist_load(s, cls.load)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()
        cls.folder.cleanup()

    def test_only_requested_inputs_closed_at_the_cutoff(self):
        with transaction(self.engine) as s:
            cutoff = s.get(EpiWeek, 202540)
            inputs = build_inputs(s, cutoff, {"casos"})
            self.assertIsNone(inputs.climate)
            self.assertIsNone(inputs.population)
            self.assertLessEqual(inputs.cases.semana_inicio.max().date(), cutoff.fecha_inicio)
            self.assertEqual(inputs.cases.ubigeo.dtype, "string")
            with self.assertRaisesRegex(ValueError, "desconocidas"):
                build_inputs(s, cutoff, {"historia_2000"})
            everything = build_inputs(s, cutoff, {"casos", "clima", "poblacion", "calendario", "regla_brote"})
            self.assertEqual(everything.outbreak_rule["anios_previos"], 5)
            self.assertIn(202553, set(everything.calendar.id_semana))  # the whole calendar, future weeks too

    def test_humidity_is_not_rounded(self):
        """M5: the database keeps the full humidity, so A3 built from it can reproduce gold."""
        silver = leer_csv("silver_muestra.csv").set_index(["ubigeo", "anio", "semana"])
        with transaction(self.engine) as s:
            climate = build_inputs(s, s.get(EpiWeek, 202552), {"clima"}).climate.set_index(["ubigeo", "anio", "semana"])
        expected = silver.loc[climate.index, "hum_rel_media"]
        self.assertTrue((expected.round(2) != expected).any())  # the fixture has more than two decimals
        self.assertTrue((climate.hum_rel_media == expected).all())


if __name__ == "__main__":
    unittest.main()
