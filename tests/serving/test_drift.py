"""Drift monitoring (HU0009-2): fewer than 8 weeks, degradation, no degradation and a reference of 0."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from sqlalchemy import select

from backend_support import motor_temporal
from denguekay.db.models import FirstEmission, ModelVersion, Prediction, Run, WeeklyObservation, utc_now
from denguekay.db.session import transaction
from denguekay.serving import drift, emissions, load_data
from denguekay.serving import parameters as parametros
from v4_weekly_support import LiveCase

BLOCK = "temporadas_2022_2026"
REFERENCE = {"recall": 0.8, "precision": 0.8, "f1": 0.8, "mae": 1.0, "rmse": 1.5}


def metrics_of(reference):
    return {"bloques": {BLOCK: {
        "clasificacion": {"alerta_directa": {k: reference[k] for k in ("recall", "precision", "f1")}},
        "regresion": {"conteos": {"mae": reference["mae"], "rmse": reference["rmse"]}}}}}


class DriftCase(LiveCase):
    SOURCE = {"fuente_casos": "sala_situacional", "estado_cobertura": "verificado", "fecha_extraccion": utc_now()}

    def setUp(self):
        super().setUp()
        with transaction(self.motor) as session:
            load_data.persist_load(session, self.current)

    def add_versions(self, session, reference=REFERENCE):
        codes = {}
        for horizon in emissions.HORIZONS:
            for task, prefix in (("clasificacion", "clf"), ("regresion", "reg")):
                code = f"d-{prefix}-h{horizon}"
                session.add(ModelVersion(
                    codigo=code, tarea=task, horizonte=horizon, algoritmo="xgboost", variables=[], hiperparametros={},
                    metricas=metrics_of(reference), umbral_probabilidad=0.5 if task == "clasificacion" else None,
                    cumple_umbrales=True, mlflow_run_id="x", ruta_artefacto="x", sha256_artefacto="0" * 64,
                    sha256_dataset="0" * 64))
                codes.setdefault(horizon, {})[task] = code
        session.flush()
        parametros.set_experimental_selection(session, codes)

    def add_weeks(self, session, rows_by_week, horizon=2):
        """rows_by_week: one list per target week of (probability, expected cases, observed outbreak, observed cases)."""
        run = Run(tipo="inferencia", estado="exitosa", id_semana_corte=self.cutoff,
                  detalle={"origen": emissions.ORIGIN, "horizonte": horizon})
        session.add(run)
        session.flush()
        for offset, rows in enumerate(rows_by_week):
            target = self.cutoff + horizon + offset
            source = {**self.SOURCE, "id_ejecucion": run.id_ejecucion}
            for ubigeo, (p, expected, outbreak, observed) in zip(self.districts, rows, strict=False):
                session.add(Prediction(ubigeo=ubigeo, id_semana_corte=target - horizon, id_semana_objetivo=target,
                                       horizonte=horizon, probabilidad_brote=p, nivel_riesgo="medio",
                                       casos_estimados=expected, estado="disponible", id_ejecucion=run.id_ejecucion))
                # The first emission that the drift review reads: its target was not yet published by the Sala.
                session.add(FirstEmission(ubigeo=ubigeo, id_semana_corte=target - horizon, id_semana_objetivo=target,
                                          horizonte=horizon, probabilidad_brote=p, nivel_riesgo="medio",
                                          casos_estimados=expected, estado="disponible", id_ejecucion=run.id_ejecucion,
                                          fecha_emision=utc_now(), ultima_semana_sala_publicada=target - 1))
                session.add(WeeklyObservation(ubigeo=ubigeo, id_semana=target, casos_dengue=observed, brote=outbreak,
                                              **source))
        session.flush()

    @staticmethod
    def perfect_week():
        # 2 outbreaks found, 2 quiet districts quiet; cases estimated exactly: recall = precision = F1 = 1, MAE = RMSE = 0.
        return [(0.9, 4.0, True, 4), (0.9, 4.0, True, 4), (0.1, 0.0, False, 0), (0.1, 0.0, False, 0)]

    @staticmethod
    def poor_week():
        # 1 of 2 outbreaks found and 1 false alarm: recall 0.5, precision 0.5, F1 0.5; errors of 3 and 1 cases.
        return [(0.9, 4.0, True, 4), (0.1, 1.0, True, 4), (0.9, 3.0, False, 0), (0.1, 0.0, False, 0)]


class TestDriftReport(DriftCase):
    def report(self, weeks, reference=REFERENCE):
        with transaction(self.motor) as session:
            self.add_versions(session, reference)
            self.add_weeks(session, weeks)
            return drift.drift_report(session)

    def test_with_fewer_than_8_weeks_only_records(self):
        full = self.report([self.poor_week()] * 7)
        result = full["horizontes"]["2"]
        self.assertEqual((result["estado"], result["semanas_cerradas"], result["con_decision"]),
                         ("solo_registro", 7, False))
        self.assertEqual(result["marcadas"], [])
        self.assertEqual(result["metricas"]["recall"]["periodo"], 0.5)
        self.assertGreater(result["metricas"]["recall"]["degradacion_relativa"], 0.10)   # computed, not flagged
        self.assertFalse(result["metricas"]["recall"]["marcada"])
        self.assertFalse(full["requiere_revision"])

    def test_with_8_weeks_flags_the_degraded_metrics_by_hand_computed_values(self):
        full = self.report([self.poor_week()] * 8)
        result = full["horizontes"]["2"]
        self.assertEqual((result["estado"], result["semanas_cerradas"], result["con_decision"]),
                         ("degradacion_detectada", 8, True))
        metrics = result["metricas"]
        # period: recall 0.5, F1 0.5, MAE (0+3+3+0)/4 = 1.5, RMSE sqrt((0+9+9+0)/4) = 2.1213; reference 0.8 / 0.8 / 1 / 1.5
        self.assertAlmostEqual(metrics["recall"]["degradacion_relativa"], (0.8 - 0.5) / 0.8, places=6)
        self.assertAlmostEqual(metrics["f1"]["degradacion_relativa"], (0.8 - 0.5) / 0.8, places=6)
        self.assertAlmostEqual(metrics["mae"]["periodo"], 1.5)
        self.assertAlmostEqual(metrics["mae"]["degradacion_relativa"], 0.5, places=6)
        self.assertAlmostEqual(metrics["rmse"]["degradacion_relativa"], (18 / 4) ** 0.5 / 1.5 - 1, places=5)
        self.assertEqual(result["marcadas"], ["recall", "f1", "mae", "rmse"])
        self.assertIsNone(metrics["precision"]["degradacion_relativa"])   # no rule in the criterion: never flagged
        self.assertFalse(metrics["precision"]["marcada"])
        self.assertTrue(full["requiere_revision"])
        self.assertEqual(full["metricas_marcadas"], {"2": ["recall", "f1", "mae", "rmse"]})
        self.assertEqual(full["horizontes"]["3"]["estado"], "sin_datos")

    def test_without_degradation_nothing_is_flagged(self):
        result = self.report([self.perfect_week()] * 8)["horizontes"]["2"]
        self.assertEqual((result["estado"], result["marcadas"]), ("sin_degradacion", []))
        self.assertEqual(result["metricas"]["recall"]["degradacion_relativa"], -0.25)   # an improvement is negative

    def test_exactly_10_percent_is_not_flagged(self):
        reference = {**REFERENCE, "recall": 5 / 9}   # 0.5 is 10 % below 5/9
        result = self.report([self.poor_week()] * 8, reference)["horizontes"]["2"]
        self.assertAlmostEqual(result["metricas"]["recall"]["degradacion_relativa"], 0.1, places=6)
        self.assertNotIn("recall", result["marcadas"])

    def test_a_reference_of_0_has_no_relative_degradation(self):
        reference = {**REFERENCE, "recall": 0.0, "mae": 0.0}
        result = self.report([self.poor_week()] * 8, reference)["horizontes"]["2"]
        for name in ("recall", "mae"):
            self.assertIsNone(result["metricas"][name]["degradacion_relativa"])
            self.assertFalse(result["metricas"][name]["marcada"])
            self.assertIn("referencia 0", result["metricas"][name]["motivo"])
        self.assertEqual(result["marcadas"], ["f1", "rmse"])

    def test_without_the_aggregate_block_in_the_versions_there_is_no_reference(self):
        with transaction(self.motor) as session:
            self.add_versions(session)
            for version in session.scalars(select(ModelVersion)):
                version.metricas = {"bloques": {"temporada_2024": {}}}
            self.add_weeks(session, [self.poor_week()] * 8)
            result = drift.drift_report(session)["horizontes"]["2"]
        self.assertEqual(result["estado"], "sin_referencia")
        self.assertEqual(result["marcadas"], [])

    def test_without_emissions_every_horizon_is_empty(self):
        with transaction(self.motor) as session:
            result = drift.drift_report(session)
        self.assertEqual({h: r["estado"] for h, r in result["horizontes"].items()},
                         {"2": "sin_datos", "3": "sin_datos", "4": "sin_datos"})
        self.assertFalse(result["requiere_revision"])

    def test_it_registers_a_maintenance_run_and_changes_no_version(self):
        with transaction(self.motor) as session:
            self.add_versions(session)
            self.add_weeks(session, [self.poor_week()] * 8)
            before = parametros.experimental_selection(session)
            report = drift.drift_report(session)
            run_id = drift.register(session, report, self.cutoff)
            run = session.get(Run, run_id)
            self.assertEqual((run.tipo, run.estado, run.detalle["origen"]), ("mantenimiento", "exitosa", drift.ORIGIN))
            self.assertTrue(run.detalle["requiere_revision"])
            self.assertEqual(parametros.experimental_selection(session), before)
            self.assertEqual(session.scalars(select(ModelVersion).where(ModelVersion.estado == "activa")).all(), [])


class TestDriftCommand(DriftCase):
    def test_main_prints_and_records_unless_told_not_to(self):
        with transaction(self.motor) as session:
            self.add_versions(session)
            self.add_weeks(session, [self.poor_week()] * 8)
        with patch.object(drift, "make_engine", return_value=self.motor), patch.object(self.motor, "dispose"):
            self.assertEqual(drift.main(["--sin-registrar"]), 0)
            with transaction(self.motor) as session:
                self.assertEqual(len(session.scalars(select(Run).where(Run.tipo == "mantenimiento")).all()), 0)
            self.assertEqual(drift.main([]), 0)
            with transaction(self.motor) as session:
                runs = session.scalars(select(Run).where(Run.tipo == "mantenimiento")).all()
                self.assertEqual([r.detalle["origen"] for r in runs], [drift.ORIGIN])


if __name__ == "__main__":
    unittest.main()
