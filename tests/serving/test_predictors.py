"""Predictor port: output validation, interval level of the package and intervals end to end (C3, P2)."""

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import pandas as pd
from sqlalchemy import select

from backend_support import datos_muestra, motor_temporal
from serving_support import fijar_seleccion, preparar_muestra, sample_package
from apps.api import queries
from denguekay.db.models import Prediction, SystemParameter
from denguekay.db.session import transaction
from denguekay.serving import parameters
from denguekay.serving.inference import InferenceUnavailable, infer
from denguekay.serving.inputs import INPUTS
from denguekay.serving.load_data import persist_load
from denguekay.serving.models import save_versions, thresholds
from denguekay.serving.package import save_package
from denguekay.serving.predictors.base import OUTPUT_COLUMNS, validate_output
from denguekay.serving.storage import LocalStorage

UBIGEOS = ["200101", "200201", "200502"]


def output_row(**changes):
    row = {"ubigeo": "200101", "horizonte": 2, "probabilidad_brote": 0.4, "casos_estimados": 3.0,
           "casos_intervalo_inferior": None, "casos_intervalo_superior": None, "motivo_no_disponible": None}
    return pd.DataFrame([{**row, **changes}], columns=OUTPUT_COLUMNS)


class IntervalPredictor:
    """Test predictor that asks for every input and estimates case intervals."""
    kind = "test_intervals"
    required_inputs = INPUTS
    interval_level = 0.9
    horizons = (2, 4)
    seen = []

    def predict(self, inputs, cutoff, horizons):
        self.seen.append(inputs)
        ubigeos = sorted(set(inputs.cases.ubigeo))
        return pd.DataFrame({"ubigeo": ubigeos, "horizonte": horizons[0], "probabilidad_brote": 0.6,
                             "casos_estimados": 5.0, "casos_intervalo_inferior": 2.0,
                             "casos_intervalo_superior": 9.0, "motivo_no_disponible": None},
                            columns=OUTPUT_COLUMNS)


class TestOutputValidation(unittest.TestCase):
    def test_valid_output_and_errors(self):
        validate_output(output_row(), (2,), None)
        validate_output(output_row(casos_intervalo_inferior=1.0, casos_intervalo_superior=4.0), (2,), 0.8)
        bad = [(output_row().drop(columns="motivo_no_disponible"), None), (output_row(horizonte=4), None),
               (pd.concat([output_row(), output_row()]), None), (output_row(probabilidad_brote=1.5), None),
               (output_row(casos_estimados=-1.0), None), (output_row(casos_intervalo_inferior=1.0), 0.8),
               (output_row(casos_intervalo_inferior=1.0, casos_intervalo_superior=4.0), None),
               (output_row(casos_intervalo_inferior=5.0, casos_intervalo_superior=4.0), 0.8),
               (output_row(probabilidad_brote=None, casos_estimados=None, casos_intervalo_inferior=1.0,
                           casos_intervalo_superior=2.0, motivo_no_disponible="sin datos"), 0.8)]
        for frame, level in bad:
            with self.subTest(frame=frame.to_dict("records")), self.assertRaises(ValueError):
                validate_output(frame, (2,), level)


class TestIntervalLevel(unittest.TestCase):
    """The manifest declares the level; inference rejects (409) one different from parametro_sistema."""

    @classmethod
    def setUpClass(cls):
        cls.cfg, protocol, trained = preparar_muestra()
        cls.package = replace(sample_package(cls.cfg, protocol, trained), interval_level=0.9)
        cls.base = tempfile.TemporaryDirectory()
        load = datos_muestra(Path(cls.base.name))
        cls.load = replace(load, observaciones=[o for o in load.observaciones if o["id_semana"] >= 202530])

    @classmethod
    def tearDownClass(cls):
        cls.base.cleanup()

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.engine = motor_temporal(Path(self.folder.name))
        self.storage = LocalStorage(Path(self.folder.name) / "storage")
        with transaction(self.engine) as s:
            persist_load(s, self.load)
            meets = thresholds(self.package, parameters.acceptance_criteria(s))
            path, sha = save_package(self.storage, self.package, meets)
            save_versions(s, self.package, path, sha, "run-test", meets)
        # Since phase 4 load_data does not seed the selection: the v0 tests set it (as publish would).
        fijar_seleccion(self.engine)

    def tearDown(self):
        self.engine.dispose()
        self.folder.cleanup()

    def infer(self):
        with transaction(self.engine) as s:
            return infer(s, 2, 202552, storage=self.storage, servir_no_validadas=True)

    def set_level(self, level):
        with transaction(self.engine) as s:
            s.get(SystemParameter, "nivel_intervalo_casos").valor = {"nivel": level}

    def test_different_level_answers_409(self):
        with self.assertRaisesRegex(InferenceUnavailable, "nivel_intervalo_casos"):
            self.infer()

    def test_same_level_writes_intervals_and_the_api_shows_them(self):
        self.set_level(0.9)
        IntervalPredictor.seen = []
        with mock.patch("denguekay.serving.inference.load_predictor", return_value=IntervalPredictor()):
            result = self.infer()
        self.assertEqual(result["disponibles"], 3)
        inputs = IntervalPredictor.seen[0]
        self.assertTrue(all(x is not None for x in (inputs.cases, inputs.climate, inputs.population,
                                                     inputs.calendar, inputs.outbreak_rule)))
        self.assertIn("hum_rel_media", inputs.climate)
        with transaction(self.engine) as s:
            rows = list(s.scalars(select(Prediction).where(Prediction.casos_intervalo_inferior.is_not(None))))
            self.assertEqual(sorted(p.ubigeo for p in rows), UBIGEOS)
            self.assertEqual({(p.casos_intervalo_inferior, p.casos_intervalo_superior) for p in rows}, {(2.0, 9.0)})
            dto = queries.prediction_dtos(s, rows)[0]
            self.assertEqual((dto["nivel_intervalo"], dto["motivo_intervalo"]), (0.9, None))
        # Changing the parameter forces a new inference: the same package is no longer accepted.
        self.set_level(0.8)
        with self.assertRaises(InferenceUnavailable):
            self.infer()


if __name__ == "__main__":
    unittest.main()
