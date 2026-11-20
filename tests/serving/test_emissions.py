"""Emissions of the weekly V4 update: detection, archive, prospective scores and the retraining notice."""

from datetime import date
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

import pandas as pd
from sqlalchemy import select

from v4_weekly_support import FIRST_CUTOFF, LiveCase
from denguekay.config.paths import V4_DATA_MANIFEST
from denguekay.data.calendar import mmwr_epi_week
from denguekay.db.models import Prediction, Run, WeeklyObservation, utc_now
from denguekay.db.session import transaction
from denguekay.pipelines import v4_weekly
from denguekay.serving import emissions, load_data


class TestAlreadyEmitted(LiveCase):
    def add_run(self, session, *, horizon, origin=emissions.ORIGIN, state="exitosa", kind="inferencia", cutoff=None):
        session.add(Run(tipo=kind, estado=state, id_semana_corte=cutoff or self.cutoff,
                        detalle={"origen": origin, "horizonte": horizon}))

    def test_needs_the_three_horizons_of_the_weekly_update(self):
        with transaction(self.motor) as session:
            load_data.persist_load(session, self.current)
            self.assertFalse(emissions.already_emitted(session, self.cutoff))
            self.add_run(session, horizon=2)
            self.add_run(session, horizon=3)
            self.assertFalse(emissions.already_emitted(session, self.cutoff))
            self.add_run(session, horizon=4, origin="api")                 # another origin does not count
            self.add_run(session, horizon=4, state="fallida")              # nor does a failed run
            self.add_run(session, horizon=4, kind="reentrenamiento")       # nor another type of run
            self.add_run(session, horizon=4, cutoff=self.cutoff - 1)       # nor another cutoff
            self.assertFalse(emissions.already_emitted(session, self.cutoff))
            self.add_run(session, horizon=4)
            self.assertTrue(emissions.already_emitted(session, self.cutoff))
            self.assertFalse(emissions.already_emitted(session, self.cutoff + 1))


class TestArchive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # These four tests only read the archive: emit once, keep every assertion, then clean up the owner.
        environment = LiveCase()
        cls.addClassCleanup(environment.doCleanups)
        environment.setUp()
        manifest = json.loads(V4_DATA_MANIFEST.read_text(encoding="utf-8"))
        files = {f["ruta"]: f["sha256"] for item in manifest["paquetes"] for f in item["archivos"]}
        same, other = "data/silver/confirmados/epi_piura_semanal.csv", "data/silver/confirmados/epi_sala_semanal.csv"
        from dataclasses import replace
        environment.current = replace(environment.current, hashes={
            **environment.current.hashes, same: files[same], other: "0" * 64,
            "data/silver/operativo/x.csv": "1" * 64})
        cls.report = environment.run_weekly()
        if cls.report["estado"] != "emitida":
            raise AssertionError(cls.report)
        cls.motor, cls.base = environment.motor, environment.base
        cls.cutoff, cls.published, cls.districts = environment.cutoff, environment.published, environment.districts
        cls.folder = cls.base / "emisiones" / str(cls.cutoff)

    def emission(self):
        folders = list(self.folder.iterdir())
        self.assertEqual(len(folders), 1)
        return folders[0], json.loads((folders[0] / "emision.json").read_text(encoding="utf-8"))

    def test_the_record_has_the_forecasts_and_the_origin_vectors(self):
        folder, record = self.emission()
        predictions = pd.read_csv(folder / "predicciones.csv", dtype={"ubigeo": str})
        self.assertEqual(len(predictions), 65 * 3)
        self.assertEqual(sorted(predictions.horizonte.unique()), [2, 3, 4])
        self.assertTrue(predictions.estado.eq("disponible").all())
        self.assertEqual(set(predictions.ubigeo), set(self.districts))
        vectors = pd.read_csv(folder / "vectores.csv", dtype={"ubigeo": str})
        self.assertEqual(len(vectors), 65)
        self.assertEqual(set(vectors.ubigeo), set(self.districts))
        self.assertFalse(vectors["hist_lag_a"].isna().any())   # the column of the synthetic model
        with transaction(self.motor) as session:
            stored = session.scalars(select(Prediction).where(Prediction.id_semana_corte == self.cutoff)).all()
            self.assertEqual(len(stored), 65 * 3)
            runs = {run.detalle["horizonte"]: run.id_ejecucion for run in session.scalars(select(Run).where(
                Run.tipo == "inferencia")) if run.detalle["origen"] == emissions.ORIGIN}   # not the imported OOS
            ingestion = session.scalar(select(Run.id_ejecucion).where(Run.tipo == "ingesta", Run.estado == "exitosa"))
        self.assertEqual(record["ejecuciones"], {"ingesta": ingestion, "inferencias": {str(h): runs[h] for h in (2, 3, 4)}})
        self.assertEqual(record["id_semana_corte"], self.cutoff)
        self.assertEqual(record["fecha_corte"], FIRST_CUTOFF.isoformat())
        self.assertIs(record["reemision"], False)
        self.assertEqual(record["paquete"]["tipo"], "v4_b3_live")
        self.assertEqual(record["huella_codigo"], "f" * 64)
        self.assertEqual(record["capturas"], {"sala": {"2025": "2025_prueba"}})
        self.assertEqual(record["predicciones"]["disponibles"], {"2": 65, "3": 65, "4": 65})

    def test_it_says_which_targets_the_sala_already_published_as_provisional(self):
        _, record = self.emission()
        self.assertEqual(record["ultima_semana_sala_publicada"], self.published)
        self.assertEqual(record["semanas_provisionales_excluidas"], [self.cutoff + 1, self.cutoff + 2])
        targets = {h: (item["id_semana_objetivo"], item["publicada_provisional_en_sala"])
                   for h, item in record["objetivos"].items()}
        self.assertEqual(targets, {"2": (self.cutoff + 2, True), "3": (self.cutoff + 3, False),
                                   "4": (self.cutoff + 4, False)})

    def test_it_compares_the_inputs_with_the_frozen_manifest(self):
        _, record = self.emission()
        self.assertEqual(record["panel_congelado"], {
            "data/silver/confirmados/epi_piura_semanal.csv": "coincide",
            "data/silver/confirmados/epi_sala_semanal.csv": "difiere"})   # the operational file is not in the manifest
        self.assertIn("data/silver/operativo/x.csv", record["insumos"])

    def test_the_archive_lives_under_the_cutoff_and_a_utc_stamp(self):
        folder, record = self.emission()
        self.assertRegex(folder.name, r"^\d{8}T\d{12}Z$")
        self.assertTrue(record["emitida_utc"].endswith("+00:00"))


class TestProspectiveScores(LiveCase):
    SOURCE = {"fuente_casos": "sala_situacional", "estado_cobertura": "verificado", "fecha_extraccion": utc_now()}

    def test_brier_mae_and_counts_are_computed_by_hand(self):
        with transaction(self.motor) as session:
            load_data.persist_load(session, self.current)
            weekly = Run(tipo="inferencia", estado="exitosa", id_semana_corte=self.cutoff,
                         detalle={"origen": emissions.ORIGIN, "horizonte": 2})
            other = Run(tipo="inferencia", estado="exitosa", id_semana_corte=self.cutoff,
                        detalle={"origen": "api", "horizonte": 2})
            session.add_all([weekly, other])
            session.flush()
            target = self.cutoff + 2
            source = {**self.SOURCE, "id_ejecucion": weekly.id_ejecucion}
            rows = [  # (district, p, expected cases, observed outbreak, observed cases)
                (self.districts[0], 0.8, 3.0, True, 5), (self.districts[1], 0.2, 1.0, False, 0),
                (self.districts[2], 0.5, 2.0, False, 2)]
            for ubigeo, probability, cases, outbreak, observed in rows:
                session.add(Prediction(ubigeo=ubigeo, id_semana_corte=self.cutoff, id_semana_objetivo=target,
                                       horizonte=2, probabilidad_brote=probability, nivel_riesgo="medio",
                                       casos_estimados=cases, estado="disponible", id_ejecucion=weekly.id_ejecucion))
                session.add(WeeklyObservation(ubigeo=ubigeo, id_semana=target, casos_dengue=observed, brote=outbreak,
                                              **source))
            # Ignored: another origin, an unavailable prediction and a target week without observation.
            session.add(Prediction(ubigeo=self.districts[3], id_semana_corte=self.cutoff, id_semana_objetivo=target,
                                   horizonte=2, probabilidad_brote=0.9, nivel_riesgo="alto", casos_estimados=9.0,
                                   estado="disponible", id_ejecucion=other.id_ejecucion))
            session.add(WeeklyObservation(ubigeo=self.districts[3], id_semana=target, casos_dengue=0, brote=False,
                                          **source))
            session.add(Prediction(ubigeo=self.districts[4], id_semana_corte=self.cutoff, id_semana_objetivo=target,
                                   horizonte=2, estado="no_disponible", motivo_no_disponible="sin historial",
                                   id_ejecucion=weekly.id_ejecucion))
            session.add(Prediction(ubigeo=self.districts[5], id_semana_corte=self.cutoff, id_semana_objetivo=target + 1,
                                   horizonte=2, probabilidad_brote=0.4, nivel_riesgo="bajo", casos_estimados=1.0,
                                   estado="disponible", id_ejecucion=weekly.id_ejecucion))
            session.flush()
            scores = emissions.prospective_scores(session)
        self.assertEqual(scores["2"], {"n": 3, "brotes_observados": 1, "suma_probabilidades": 1.5,
                                       "brier": 0.11, "mae_casos": 1.0})
        self.assertEqual(scores["3"]["n"], 0)
        self.assertIsNone(scores["4"]["brier"])
        self.assertIsNone(scores["4"]["mae_casos"])

    def test_without_emissions_every_horizon_is_empty(self):
        with transaction(self.motor) as session:
            scores = emissions.prospective_scores(session)
        self.assertEqual({h: item["n"] for h, item in scores.items()}, {"2": 0, "3": 0, "4": 0})


class TestRetrainingNotice(unittest.TestCase):
    class Session:
        def __init__(self, end):
            self.end = end

        def get(self, model, key):
            return SimpleNamespace(fecha_fin=self.end)

    def test_the_v4_close_is_week_34_of_2027(self):
        close = emissions.season_close(date(2026, 10, 17))
        self.assertEqual(close, date(2027, 8, 28))
        week = mmwr_epi_week(pd.Series([pd.Timestamp(close) - pd.Timedelta(days=6)])).iloc[0]
        self.assertEqual((int(week.anio_epi), int(week.semana_epi)), (2027, 34))

    def test_the_labels_of_the_card_are_the_frozen_ones(self):
        self.assertEqual(emissions.labels_cutoff_of_v4(), date(2026, 10, 17))

    def test_the_archive_of_an_emission_is_uploaded_with_its_cutoff_and_stamp(self):
        from tempfile import TemporaryDirectory

        from denguekay.serving.storage import LocalStorage

        with TemporaryDirectory() as directory:
            base = Path(directory) / "emisiones"
            folder = base / "202643" / "20261118T000000000000Z"
            folder.mkdir(parents=True)
            for name in emissions.ARCHIVE_FILES:
                (folder / name).write_bytes(name.encode())
            storage = LocalStorage(Path(directory) / "storage")
            paths = emissions.upload_archive(storage, folder, base)
            self.assertEqual(paths, [f"reportes/emisiones/202643/20261118T000000000000Z/{n}"
                                     for n in emissions.ARCHIVE_FILES])
            self.assertEqual(storage.read(paths[0]), b"emision.json")

    def test_a_refit_package_moves_the_labels_cutoff_and_switches_the_notice_off(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from unittest.mock import patch
        from denguekay.config import paths

        with TemporaryDirectory() as folder:
            package = Path(folder) / "reajuste"
            package.mkdir()
            (package / "paquete.json").write_text(json.dumps({"corte": "2027-08-28"}), encoding="utf-8")
            options = {"paquete_dir": "reajuste"}
            with patch.object(paths, "ROOT", Path(folder)):
                self.assertEqual(emissions.labels_cutoff_of_v4(options), date(2027, 8, 28))
        notice = emissions.retraining_due(self.Session(date(2027, 9, 4)), 202799, labels_cutoff=date(2027, 8, 28))
        self.assertIs(notice["reentrenamiento_anual_pendiente"], False)     # next close: 2028-08-26
        self.assertEqual(notice["cierre_temporada"], "2028-08-26")

    def test_a_close_that_already_passed_moves_to_the_next_year(self):
        self.assertEqual(emissions.season_close(date(2026, 8, 29)), date(2027, 8, 28))   # close of 2026 not after it
        self.assertEqual(emissions.season_close(date(2026, 8, 28)), date(2026, 8, 29))

    def test_false_before_and_true_from_the_close(self):
        for end, expected in ((date(2026, 11, 7), False), (date(2027, 8, 21), False), (date(2027, 8, 28), True),
                              (date(2027, 10, 2), True)):
            with self.subTest(end=end):
                notice = emissions.retraining_due(self.Session(end), 202799, labels_cutoff=date(2026, 10, 17))
                self.assertIs(notice["reentrenamiento_anual_pendiente"], expected)
                self.assertEqual(notice["cierre_temporada"], "2027-08-28")


if __name__ == "__main__":
    unittest.main()
