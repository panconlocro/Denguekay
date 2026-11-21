"""First emission of each forecast (``emision_prediccion``): the prospective evaluation never reads a re-emission."""

from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
import io
import json
import shutil
from unittest.mock import patch

from sqlalchemy import delete, select

from serving.test_drift import DriftCase
from v4_weekly_support import LiveCase
from denguekay.db.models import EpiWeek, FirstEmission, Prediction, Run, WeeklyObservation, utc_now
from denguekay.db.session import transaction
from denguekay.pipelines.v4_weekly import Options
from denguekay.serving import drift, emissions, first_emission_backfill


class TestProfessorScenario(DriftCase):
    """Three forecasts with their outcomes, then one re-emitted 10 days after the close of its target week."""

    CASES = [(0.8, 3.0, True, 5), (0.2, 1.0, False, 0), (0.5, 2.0, False, 2)]   # p, expected cases, outbreak, observed

    def emit(self, session, rows, *, emitted_at, last_published):
        """What the weekly update does: a weekly run, the UPSERT of ``prediccion`` and the first-emission record."""
        run = Run(tipo="inferencia", estado="exitosa", id_semana_corte=self.cutoff,
                  detalle={"origen": emissions.ORIGIN, "horizonte": 2})
        session.add(run)
        session.flush()
        target = self.cutoff + 2
        for ubigeo, (p, cases, _, _) in zip(self.districts, rows):
            current = session.scalar(select(Prediction).where(
                Prediction.ubigeo == ubigeo, Prediction.id_semana_corte == self.cutoff, Prediction.horizonte == 2))
            if current is None:
                session.add(Prediction(ubigeo=ubigeo, id_semana_corte=self.cutoff, id_semana_objetivo=target,
                                       horizonte=2, probabilidad_brote=p, nivel_riesgo="medio", casos_estimados=cases,
                                       estado="disponible", id_ejecucion=run.id_ejecucion))
            else:   # the UPSERT of a re-emission overwrites the row
                current.probabilidad_brote, current.casos_estimados = p, cases
                current.id_ejecucion, current.fecha_generacion = run.id_ejecucion, emitted_at
        session.flush()
        result = emissions.record_first_emission(session, [{"id_ejecucion": run.id_ejecucion}],
                                                 last_published=last_published, emitted_at=emitted_at)
        return run, result

    def observe(self, session, run):
        target = self.cutoff + 2
        for ubigeo, (_, _, outbreak, observed) in zip(self.districts, self.CASES):
            session.add(WeeklyObservation(ubigeo=ubigeo, id_semana=target, casos_dengue=observed, brote=outbreak,
                                          **{**self.SOURCE, "id_ejecucion": run.id_ejecucion}))
        session.flush()

    def test_a_reissue_after_the_outcome_changes_neither_the_scores_nor_the_drift_nor_n(self):
        target = self.cutoff + 2
        with transaction(self.motor) as session:
            self.add_versions(session)
            run, first = self.emit(session, self.CASES, emitted_at=utc_now(), last_published=self.cutoff + 1)
            self.assertEqual(first, {"insertadas": 3, "ya_existian": 0})
            self.observe(session, run)
            before_scores, before_drift = emissions.prospective_scores(session), drift.drift_report(session)
            stored = {r.ubigeo: (r.probabilidad_brote, r.casos_estimados, r.id_ejecucion, r.fecha_emision)
                      for r in session.scalars(select(FirstEmission))}
            # Re-emission 10 days after the close of the target week, with other probabilities and cases and the Sala
            # already publishing the target: it overwrites ``prediccion`` and must not count.
            close = session.get(EpiWeek, target).fecha_fin + timedelta(days=10)
            reissued_at = datetime(close.year, close.month, close.day, tzinfo=timezone.utc)
            _, again = self.emit(session, [(0.99, 9.0, None, None), (0.01, 0.0, None, None), (0.99, 9.0, None, None)],
                                 emitted_at=reissued_at, last_published=target + 3)
            after_scores, after_drift = emissions.prospective_scores(session), drift.drift_report(session)
            overwritten = {r.ubigeo: r.probabilidad_brote for r in session.scalars(select(Prediction).where(
                Prediction.id_semana_corte == self.cutoff, Prediction.horizonte == 2))}
            kept = {r.ubigeo: (r.probabilidad_brote, r.casos_estimados, r.id_ejecucion, r.fecha_emision)
                    for r in session.scalars(select(FirstEmission))}
        self.assertEqual(again, {"insertadas": 0, "ya_existian": 3})
        # By hand: p = 0.8, 0.2, 0.5 against outbreaks 1, 0, 0 -> Brier (0.04 + 0.04 + 0.25) / 3 = 0.11; MAE (2 + 1 + 0) / 3 = 1.
        self.assertEqual(before_scores["2"], {"n": 3, "brotes_observados": 1, "suma_probabilidades": 1.5,
                                              "brier": 0.11, "mae_casos": 1.0})
        self.assertEqual(after_scores, before_scores)    # Brier, MAE, observed outbreaks and n are identical
        self.assertEqual(after_drift, before_drift)      # and so is the drift review
        self.assertEqual(overwritten[self.districts[0]], 0.99)   # ``prediccion`` did change, as the UPSERT does
        self.assertEqual(kept, stored)                   # the first emission did not

    def test_the_target_already_published_when_emitted_is_not_eligible(self):
        target = self.cutoff + 2
        with transaction(self.motor) as session:
            run, _ = self.emit(session, self.CASES, emitted_at=utc_now(), last_published=target)   # already published
            self.observe(session, run)
            self.assertEqual(emissions.prospective_scores(session)["2"]["n"], 0)
            self.assertTrue(emissions.prospective_frame(session).empty)


class TestWeeklyUpdateRecordsIt(LiveCase):
    def rows(self):
        with transaction(self.motor) as session:
            return session.scalars(select(FirstEmission).order_by(FirstEmission.horizonte, FirstEmission.ubigeo)).all()

    @staticmethod
    def snapshot(rows):
        return [(r.ubigeo, r.horizonte, r.probabilidad_brote, r.casos_estimados, r.id_ejecucion, r.fecha_emision)
                for r in rows]

    def test_the_weekly_update_records_the_first_emission_and_a_reissue_leaves_it_alone(self):
        report = self.run_weekly(Options(inicial=True))
        self.assertEqual(report["estado"], "emitida", report)
        self.assertEqual(report["primera_emision"], {"insertadas": 65 * 3, "ya_existian": 0})
        first = self.rows()
        self.assertEqual(len(first), 65 * 3)
        self.assertEqual({r.horizonte for r in first}, {2, 3, 4})
        self.assertTrue(all(r.procedencia == "emision" and r.ultima_semana_sala_publicada == self.published
                            for r in first))
        # Eligibility: h = 2 targets the week the Sala has already published (provisional); h = 3 and 4 do not.
        self.assertEqual({r.horizonte for r in first if r.id_semana_objetivo > r.ultima_semana_sala_publicada}, {3, 4})
        snapshot = self.snapshot(first)

        again = self.run_weekly(Options(reemitir=True))
        self.assertEqual(again["estado"], "emitida", again)
        self.assertEqual(again["primera_emision"], {"insertadas": 0, "ya_existian": 65 * 3})
        with transaction(self.motor) as session:
            current = session.scalars(select(Prediction).where(Prediction.id_semana_corte == self.cutoff)).all()
            self.assertEqual(len(current), 65 * 3)                          # one row each, overwritten by the UPSERT
            self.assertEqual({r.id_ejecucion for r in current}.isdisjoint({r[4] for r in snapshot}), True)   # new runs
        self.assertEqual(self.snapshot(self.rows()), snapshot)


class TestBackfill(LiveCase):
    def setUp(self):
        super().setUp()
        self.assertEqual(self.run_weekly(Options(inicial=True))["estado"], "emitida")
        self.archive = self.base / "emisiones"
        with transaction(self.motor) as session:
            session.execute(delete(FirstEmission))   # as if the table did not exist when it was emitted

    def run_backfill(self, **options):
        with transaction(self.motor) as session:
            return first_emission_backfill.backfill(session, self.archive, **options)

    def rows(self):
        with transaction(self.motor) as session:
            return session.scalars(select(FirstEmission)).all()

    def test_it_uses_the_oldest_archived_emission_of_each_cutoff(self):
        self.run_weekly(Options(reemitir=True))   # a second archived emission of the same cutoff
        with transaction(self.motor) as session:
            session.execute(delete(FirstEmission))   # the reissue refilled it: empty it again before the backfill
        folders = sorted((self.archive / str(self.cutoff)).iterdir())
        self.assertEqual(len(folders), 2)
        report = self.run_backfill()
        self.assertEqual(report["cortes"], {str(self.cutoff): "archivo"})
        self.assertEqual(report["filas"], {"archivo": 65 * 3, "prediccion_actual": 0})
        rows = self.rows()
        record = json.loads((folders[0] / "emision.json").read_text(encoding="utf-8"))
        self.assertEqual({r.id_ejecucion for r in rows}, set(record["ejecuciones"]["inferencias"].values()))
        self.assertTrue(all(r.procedencia == "archivo" and r.ultima_semana_sala_publicada == self.published
                            for r in rows))
        self.assertEqual({r.fecha_emision.replace(tzinfo=None) for r in rows},
                         {datetime.fromisoformat(record["emitida_utc"]).replace(tzinfo=None)})

    def test_without_an_archive_it_uses_the_current_row_and_marks_it_as_unknown(self):
        shutil.rmtree(self.archive)
        report = self.run_backfill()
        self.assertEqual(report["cortes"], {str(self.cutoff): "prediccion_actual"})
        rows = self.rows()
        self.assertEqual(len(rows), 65 * 3)
        self.assertTrue(all(r.procedencia == "prediccion_actual" and r.ultima_semana_sala_publicada is None
                            for r in rows))
        with transaction(self.motor) as session:   # never eligible: its publication state is unknown
            self.assertTrue(emissions.prospective_frame(session).empty)

    def command(self, *arguments):
        """The command line, on the temporary database, and the JSON it prints."""
        with patch.object(first_emission_backfill, "make_engine", return_value=self.motor),                 redirect_stdout(io.StringIO()) as output:
            self.assertEqual(first_emission_backfill.main(list(arguments)), 0)
        return json.loads(output.getvalue())

    def test_the_command_reports_without_writing_from_a_folder_of_fixtures(self):
        report = self.command("--carpeta", str(self.archive), "--sin-escribir")
        self.assertEqual(report["cortes"], {str(self.cutoff): "archivo"})
        self.assertEqual(report["filas"], {"archivo": 65 * 3, "prediccion_actual": 0})
        self.assertEqual(self.rows(), [])     # --sin-escribir inserts nothing

    def test_the_command_without_an_archive_inserts_the_current_row_marked_prediccion_actual(self):
        report = self.command("--carpeta", str(self.root / "no_hay_archivo"))
        self.assertEqual(report["cortes"], {str(self.cutoff): "prediccion_actual"})
        self.assertEqual(report["filas"], {"archivo": 0, "prediccion_actual": 65 * 3})
        rows = self.rows()
        self.assertEqual({(r.procedencia, r.ultima_semana_sala_publicada) for r in rows}, {("prediccion_actual", None)})
        self.assertEqual(self.command("--carpeta", str(self.root / "no_hay_archivo"))["cortes"],
                         {str(self.cutoff): "ya tenía primera emisión"})   # a second run changes nothing

    def test_it_is_idempotent_and_can_report_without_writing(self):
        self.assertEqual(self.run_backfill(write=False)["filas"]["archivo"], 65 * 3)
        self.assertEqual(self.rows(), [])
        self.run_backfill()
        before = {(r.ubigeo, r.horizonte, r.id_ejecucion) for r in self.rows()}
        again = self.run_backfill()
        self.assertEqual(again["cortes"], {str(self.cutoff): "ya tenía primera emisión"})
        self.assertEqual({(r.ubigeo, r.horizonte, r.id_ejecucion) for r in self.rows()}, before)
