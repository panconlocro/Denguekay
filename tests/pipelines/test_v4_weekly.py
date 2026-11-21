"""Weekly update of the frozen V4: order of the steps, new week or not, failures, lock and full runs.

Everything runs on a temporary SQLite database with a synthetic frozen package: no network, no ``data/``, no
database or ``mlflow.db`` of the team."""

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import json
import os
import shutil
from unittest.mock import patch

from sqlalchemy import func, select
from sqlalchemy.engine import URL

from v4_weekly_support import FIRST_CUTOFF, NEXT_CUTOFF, LiveCase
from denguekay.config.paths import (CONFIG, OPERATIONAL_CHIRPS, OPERATIONAL_ENSO, OPERATIONAL_ERA5_LAND,
                                    OPERATIONAL_SALA)
from denguekay.db.models import Prediction, Run, WeeklyObservation
from denguekay.db.session import make_engine, transaction
from denguekay.pipelines import v4_inputs, v4_weekly
from denguekay.pipelines.v4_weekly import Options, WeeklyError
from denguekay.serving import drift, emissions
from denguekay.serving import inference
from denguekay.serving.settings import service_settings


def counts(motor):
    with transaction(motor) as session:
        runs = session.execute(select(Run.tipo, Run.estado, func.count()).group_by(Run.tipo, Run.estado)).all()
        return {
            "ejecuciones": {(tipo, estado): n for tipo, estado, n in runs},
            "predicciones": session.scalar(select(func.count()).select_from(Prediction)),
            "observaciones": session.scalar(select(func.count()).select_from(WeeklyObservation)),
        }


def weekly_inferences(motor):
    with transaction(motor) as session:
        return [run for run in session.scalars(select(Run).where(Run.tipo == "inferencia", Run.estado == "exitosa"))
                if (run.detalle or {}).get("origen") == emissions.ORIGIN]


class TestFullRuns(LiveCase):
    def test_the_initial_run_publishes_loads_and_emits_the_three_horizons(self):
        report = self.run_weekly(Options(inicial=True))
        self.assertEqual(report["estado"], "emitida", report)
        self.assertEqual(report["id_semana_corte"], self.cutoff)
        self.assertEqual(report["disponibles"], {"2": 65, "3": 65, "4": 65})
        self.assertIs(report["parcial"], False)
        self.assertEqual([name for name, _, _ in self.calls], ["sala", "corte", "clima"])
        self.assertEqual(self.calls[0][1], (False,))
        self.assertEqual(self.calls[2][1], (False, True))
        state = counts(self.motor)
        self.assertEqual(state["ejecuciones"][("inferencia", "exitosa")], 3 + 3)    # 3 imported OOS blocks + 3 weekly
        self.assertEqual(state["ejecuciones"][("ingesta", "exitosa")], 1)
        self.assertEqual(state["ejecuciones"][("reentrenamiento", "exitosa")], 1)   # the registration of the frozen package
        self.assertEqual(sorted(run.detalle["horizonte"] for run in weekly_inferences(self.motor)), [2, 3, 4])
        self.assertTrue((self.base / report["emision"] / "emision.json").is_file())
        self.assertTrue((self.base / report["informe"]).is_file())
        self.assertFalse((self.base / "en_curso.lock").exists())
        self.assertIs(report["reentrenamiento_anual_pendiente"], False)
        self.assertEqual(report["seguimiento_prospectivo"]["2"]["n"], 0)
        self.assertEqual(report["monitoreo_deriva"]["horizontes"]["2"]["estado"], "sin_datos")   # nothing closed yet
        self.assertFalse(report["monitoreo_deriva"]["requiere_revision"])

    def test_a_failure_in_the_drift_review_never_fails_the_emission(self):
        with patch.object(drift, "drift_report", side_effect=ValueError("boom")):
            report = self.run_weekly(Options(inicial=True))
        self.assertEqual(report["estado"], "emitida", report)
        self.assertEqual(report["monitoreo_deriva"], "no disponible: ValueError")
        self.assertEqual(report["seguimiento_prospectivo"]["2"]["n"], 0)   # the follow-up and the notice survive
        self.assertIs(report["reentrenamiento_anual_pendiente"], False)
        self.assertEqual(counts(self.motor)["ejecuciones"].get(("inferencia", "fallida"), 0), 0)

    def test_the_second_run_with_the_same_data_is_without_news_and_creates_nothing(self):
        self.run_weekly(Options(inicial=True))
        before = counts(self.motor)
        self.calls.clear()
        report = self.run_weekly(Options())
        self.assertEqual(report["estado"], "sin_novedad")
        self.assertIs(report["corte_ya_emitido"], True)
        self.assertEqual([name for name, _, _ in self.calls], ["sala", "corte"])   # no climate download, no load
        self.assertEqual(counts(self.motor), before)
        self.assertEqual(len(list((self.base / "emisiones" / str(self.cutoff)).iterdir())), 1)

    def test_a_new_week_in_the_sala_emits_the_next_cutoff(self):
        self.run_weekly(Options(inicial=True))
        self.cutoff, self.published, self.current = self.cutoff + 1, self.published + 1, self.batch(NEXT_CUTOFF)
        report = self.run_weekly(Options())
        self.assertEqual(report["estado"], "emitida", report)
        self.assertEqual(report["id_semana_corte"], self.cutoff)
        self.assertEqual(len(weekly_inferences(self.motor)), 6)
        self.assertEqual({run.id_semana_corte for run in weekly_inferences(self.motor)}, {self.cutoff - 1, self.cutoff})
        self.assertEqual(counts(self.motor)["ejecuciones"][("ingesta", "exitosa")], 2)
        self.assertEqual(counts(self.motor)["ejecuciones"][("reentrenamiento", "exitosa")], 1)   # published only once

    def test_forcing_loads_the_data_without_emitting_again(self):
        self.run_weekly(Options(inicial=True))
        inferences = len(weekly_inferences(self.motor))
        self.calls.clear()
        report = self.run_weekly(Options(forzar=True))
        self.assertEqual(report["estado"], "cargada_sin_emitir")
        self.assertIn("clima", [name for name, _, _ in self.calls])
        self.assertEqual(len(weekly_inferences(self.motor)), inferences)
        self.assertEqual(len(list((self.base / "emisiones" / str(self.cutoff)).iterdir())), 1)

    def test_reissuing_emits_again_and_marks_the_archive(self):
        self.run_weekly(Options(inicial=True))
        report = self.run_weekly(Options(reemitir=True))
        self.assertEqual(report["estado"], "emitida", report)
        self.assertEqual(len(weekly_inferences(self.motor)), 6)
        folders = sorted((self.base / "emisiones" / str(self.cutoff)).iterdir())
        self.assertEqual(len(folders), 2)
        flags = [json.loads((folder / "emision.json").read_text(encoding="utf-8"))["reemision"] for folder in folders]
        self.assertEqual(flags, [False, True])

    def test_the_package_is_published_only_when_it_is_needed(self):
        published = []
        publish = lambda motor, cfg, storage: published.append(1) or v4_weekly.step_publish(motor, cfg, storage)
        self.run_weekly(Options(inicial=True), publish=publish)
        self.assertEqual(len(published), 1)
        self.cutoff, self.published, self.current = self.cutoff + 1, self.published + 1, self.batch(NEXT_CUTOFF)
        self.assertEqual(self.run_weekly(Options(inicial=True), publish=publish)["estado"], "emitida")
        self.assertEqual(len(published), 1)

    def test_without_the_initial_flag_an_unpublished_package_is_an_error_with_the_command(self):
        report = self.run_weekly(Options())
        self.assertEqual(report["estado"], "fallida")
        self.assertIn("--inicial", report["error"])
        self.assertEqual(counts(self.motor)["predicciones"], 0)

    def test_the_cutoff_that_loads_must_be_the_expected_one(self):
        self.run_weekly(Options(inicial=True))
        self.cutoff += 1   # the Sala says there is a newer week than the data that was loaded
        report = self.run_weekly(Options())
        self.assertEqual(report["estado"], "fallida")
        self.assertEqual(report["etapa"], "carga")
        self.assertEqual(len(weekly_inferences(self.motor)), 3)


class RemoteArchiveMixin:
    def remote_status(self):
        """``archivo_remoto`` of the horizon-2 inference of the only emission."""
        runs = [run for run in weekly_inferences(self.motor) if run.detalle["horizonte"] == 2]
        (run,) = runs
        return run.detalle["archivo_remoto"]


class TestRunnerWithoutState(RemoteArchiveMixin, LiveCase):
    """GitHub Actions starts with an empty machine: it prepares itself, keeps the archive in the Storage and says
    clearly when the refit package it is asked to serve is not there."""

    def test_the_prepare_flag_extracts_the_release_and_restores_the_bronze_without_publishing(self):
        self.run_weekly(Options(inicial=True))   # the package is published once, by the initial run
        self.calls.clear()
        present = iter([[v4_weekly.ROOT / "data" / "falta.csv"], []])
        published = []
        report = self.run_weekly(Options(preparar=True, reemitir=True), missing_files=lambda: next(present, []),
                                 publish=lambda *args: published.append(1))
        self.assertEqual(report["estado"], "emitida", report)
        self.assertEqual([name for name, _, _ in self.calls][0], "release")
        self.assertEqual(self.calls[-1][:2], ("clima", (False, True)))   # the bronze is restored when it is missing
        self.assertEqual(published, [])

    def test_without_the_prepare_or_initial_flag_missing_files_still_fail(self):
        report = self.run_weekly(Options(), missing_files=lambda: [v4_weekly.ROOT / "data" / "falta.csv"])
        self.assertEqual(report["estado"], "fallida")

    def test_the_prepare_flag_restores_the_missing_historical_bronze(self):
        with patch.object(v4_inputs, "download_era5_land"), patch.object(v4_inputs, "era5_land_silver"), \
                patch.object(v4_inputs, "climate_silver"), \
                patch.object(v4_inputs, "restore_published_bronze") as restore, \
                patch.object(v4_weekly, "historical_bronze_missing", return_value=[self.root / "falta"]):
            v4_weekly.step_climate(True, True)
            restore.assert_called_once_with()

    def test_the_emission_is_copied_to_the_storage_when_the_backend_is_not_local(self):
        self.cfg = replace(self.cfg, almacenamiento="supabase")
        report = self.run_weekly(Options(inicial=True))
        self.assertEqual(report["estado"], "emitida", report)
        relative = report["emision"].split("/", 1)[1]   # emisiones/<cutoff>/<stamp>
        self.assertEqual(sorted(report["archivo_en_storage"]),
                         sorted(f"reportes/emisiones/{relative}/{name}" for name in emissions.ARCHIVE_FILES))
        for path in report["archivo_en_storage"]:
            self.assertTrue(self.storage.exists(path))
        stored = json.loads(self.storage.read(f"reportes/emisiones/{relative}/emision.json"))
        self.assertEqual(stored["id_semana_corte"], self.cutoff)
        self.assertEqual(report["archivo_remoto"], "subido")
        self.assertEqual(self.remote_status()["estado"], "subido")   # also written to ejecucion.detalle

    def test_with_the_local_backend_the_archive_is_not_duplicated_in_the_storage(self):
        report = self.run_weekly(Options(inicial=True))
        self.assertNotIn("archivo_en_storage", report)

    def test_a_storage_failure_after_the_commit_is_a_warning_not_a_failed_emission(self):
        self.cfg = replace(self.cfg, almacenamiento="supabase")
        with patch.object(emissions, "upload_archive", side_effect=OSError("sin red")):
            report = self.run_weekly(Options(inicial=True))
        self.assertEqual(report["estado"], "emitida", report)
        self.assertTrue(report["archivo_en_storage"].startswith("fallido"))
        self.assertTrue(any("Storage" in w for w in report["advertencias"]))
        self.assertEqual(len(weekly_inferences(self.motor)), 3)   # the forecast stays published
        status = self.remote_status()
        self.assertEqual((status["estado"], status["intentos"]), ("fallido", 1))
        self.assertIn("OSError: sin red", status["error"])
        self.assertEqual(report["archivo_remoto"], "fallido")
        # The retry uploads it from the local folder and leaves it as ``subido``; a second retry has nothing to do.
        retry = v4_weekly.retry_archive(self.motor, self.cfg, self.storage, self.base)
        self.assertEqual((retry["estado"], retry["pendientes"], retry["subidos"]),
                         ("archivo_al_dia", 1, [status["ruta"]]))
        after = self.remote_status()
        self.assertEqual((after["estado"], after["intentos"]), ("subido", 2))
        for name in emissions.ARCHIVE_FILES:
            self.assertTrue(self.storage.exists(f"reportes/emisiones/{status['ruta']}/{name}"))
        self.assertEqual(v4_weekly.retry_archive(self.motor, self.cfg, self.storage, self.base)["pendientes"], 0)

    def test_a_retry_that_fails_again_or_has_no_local_folder_stays_pending_with_its_reason(self):
        self.cfg = replace(self.cfg, almacenamiento="supabase")
        with patch.object(emissions, "upload_archive", side_effect=OSError("sin red")):
            self.run_weekly(Options(inicial=True))
            retry = v4_weekly.retry_archive(self.motor, self.cfg, self.storage, self.base)
        self.assertEqual((retry["estado"], retry["pendientes"]), ("fallida", 1))
        self.assertIn("sin red", next(iter(retry["fallidos"].values())))
        self.assertEqual(self.remote_status()["intentos"], 2)
        shutil.rmtree(self.base / "emisiones")
        gone = v4_weekly.retry_archive(self.motor, self.cfg, self.storage, self.base)
        self.assertEqual(gone["estado"], "fallida")
        self.assertIn("no está la carpeta local", next(iter(gone["fallidos"].values())))
        self.assertEqual(self.remote_status()["estado"], "fallido")

    def test_the_retry_flag_of_the_command_line_runs_only_the_retry(self):
        fake_engine = type("Engine", (), {"dispose": lambda self: None})()
        with patch.object(v4_weekly, "retry_archive", return_value={"estado": "archivo_al_dia"}) as retry,                 patch.object(v4_weekly, "run") as run, patch.object(v4_weekly, "make_engine", return_value=fake_engine),                 patch("denguekay.serving.storage.storage_from_environment", return_value=object()):
            self.assertEqual(v4_weekly.main(["--reintentar-archivo"]), 0)
        retry.assert_called_once()
        run.assert_not_called()

    def test_the_emission_archives_the_utc_extraction_of_each_capture(self):
        captures = {"sala": {"2025": {"archivo": "2025_20261120T071341806116Z",
                                      "extraido_utc": "2026-11-20T07:13:41.806116+00:00", "precision": "instante"}},
                    "era5_land_reciente": {"archivo": "2026-11-15", "extraido_utc": "2026-11-20T07:30:00+00:00",
                                           "precision": "instante"},
                    "chirps": None, "enso": {"archivo": "sstoi_20261120.indices", "extraido_utc": "2026-11-20",
                                             "precision": "dia"}}
        report = self.run_weekly(Options(inicial=True), captures=lambda: captures)
        record = json.loads((self.base / report["emision"] / "emision.json").read_text(encoding="utf-8"))
        self.assertEqual(record["capturas"], captures)

    def test_with_the_local_backend_the_retry_has_nothing_to_upload(self):
        self.run_weekly(Options(inicial=True))
        retry = v4_weekly.retry_archive(self.motor, self.cfg, self.storage, self.base)
        self.assertEqual(retry["estado"], "archivo_al_dia")

    def test_the_dry_run_plans_the_release_extraction_for_the_prepare_flag(self):
        missing = [v4_weekly.ROOT / "data" / "falta.csv"]
        report = self.run_weekly(Options(dry_run=True, preparar=True), missing_files=lambda: missing)
        self.assertEqual(report["estado"], "dry_run")
        self.assertIn("extraer del Release lo que falta", report["pasos"])
        self.assertEqual(self.calls, [])

    def test_the_command_line_has_the_prepare_flag(self):
        captured = {}
        fake_engine = type("Engine", (), {"dispose": lambda self: None})()
        with patch.object(v4_weekly, "run", side_effect=lambda options, **kw: captured.update(o=options) or
                          {"estado": "dry_run"}), patch.object(v4_weekly, "make_engine", return_value=fake_engine),                 patch("denguekay.serving.storage.storage_from_environment"):
            self.assertEqual(v4_weekly.main(["--preparar", "--dry-run"]), 0)
        self.assertTrue(captured["o"].preparar and captured["o"].dry_run and not captured["o"].inicial)

    def test_a_partial_upload_to_the_storage_is_reported_as_failed_and_can_be_repeated(self):
        class Flaky:
            def __init__(self, inner):
                self.inner, self.saved = inner, 0

            def save(self, path, content):
                if path.startswith("reportes/"):   # only the archive of the emission, not the package
                    self.saved += 1
                    if self.saved == 2:
                        raise OSError("corte")
                self.inner.save(path, content)

            def __getattr__(self, name):
                return getattr(self.inner, name)

        self.cfg = replace(self.cfg, almacenamiento="supabase")
        inner = self.storage
        self.storage = Flaky(inner)
        report = self.run_weekly(Options(inicial=True))
        self.assertEqual(report["estado"], "emitida", report)
        self.assertEqual(report["archivo_en_storage"], "fallido: OSError")
        self.assertTrue(inner.exists(f"reportes/emisiones/{report['emision'].split('/', 1)[1]}/emision.json"))
        folder = self.base / report["emision"]
        again = emissions.upload_archive(inner, folder, self.base / "emisiones")   # x-upsert makes a retry safe
        self.assertEqual(len(again), 3)
        self.assertTrue(all(inner.exists(path) for path in again))

    def test_a_refit_package_that_is_not_on_the_machine_is_rejected_with_a_clear_message(self):
        options = {**self.cfg.opciones, "paquete_dir": "models/experimentos/mejora_modelo/v4_reajuste/no_existe"}
        self.cfg = replace(self.cfg, paquete={**self.cfg.paquete, "opciones": options})
        report = self.run_weekly(Options(inicial=True))
        self.assertEqual((report["estado"], report["etapa"]), ("fallida", "preflight"))
        self.assertIn("paquete_dir", report["error"])
        self.assertIn("Release model/v4", report["error"])
        self.assertEqual(self.calls, [])


class TestFailures(LiveCase):
    def failures(self):
        with transaction(self.motor) as session:
            return list(session.scalars(select(Run).where(Run.estado == "fallida")))

    def test_a_source_that_fails_loads_nothing_and_is_recorded(self):
        self.run_weekly(Options(inicial=True))
        before = counts(self.motor)
        self.cutoff, self.published, self.current = self.cutoff + 1, self.published + 1, self.batch(NEXT_CUTOFF)

        def broken(offline):
            raise RuntimeError("Sala extraction failed")

        report = self.run_weekly(Options(), sala=broken)
        self.assertEqual(report["estado"], "fallida")
        self.assertEqual(report["etapa"], "sala")
        after = counts(self.motor)
        self.assertEqual(after["predicciones"], before["predicciones"])
        self.assertEqual(after["observaciones"], before["observaciones"])
        failure, = self.failures()
        self.assertEqual((failure.tipo, failure.detalle), ("ingesta", {"origen": "actualizacion_semanal", "etapa": "sala"}))
        self.assertIn("Sala extraction failed", failure.mensaje_error)
        self.assertFalse((self.base / "en_curso.lock").exists())

    def test_a_failure_in_h4_rolls_back_the_load_and_the_other_horizons(self):
        self.run_weekly(Options(inicial=True))
        before = counts(self.motor)
        emitted = len(weekly_inferences(self.motor))
        self.cutoff, self.published, self.current = self.cutoff + 1, self.published + 1, self.batch(NEXT_CUTOFF)
        real = inference.infer

        def failing(sesion, horizon, *args, **kwargs):
            result = real(sesion, horizon, *args, **kwargs)
            if horizon == 4:
                raise RuntimeError("falla simulada en h4")
            return result

        with patch.object(inference, "infer", failing):
            report = self.run_weekly(Options())
        self.assertEqual(report["estado"], "fallida")
        self.assertEqual(report["etapa"], "inferencia")
        with transaction(self.motor) as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(Prediction).where(
                Prediction.id_semana_corte == self.cutoff)), 0)
            self.assertEqual(session.scalar(select(func.count()).select_from(WeeklyObservation).where(
                WeeklyObservation.id_semana == self.cutoff)), 0)
        after = counts(self.motor)
        self.assertEqual((after["predicciones"], after["observaciones"]), (before["predicciones"], before["observaciones"]))
        self.assertEqual(len(weekly_inferences(self.motor)), emitted)
        self.assertEqual(counts(self.motor)["ejecuciones"][("ingesta", "exitosa")], 1)
        failure, = self.failures()
        self.assertEqual(failure.tipo, "inferencia")
        self.assertEqual(failure.detalle["etapa"], "inferencia")
        self.assertFalse((self.base / "emisiones" / str(self.cutoff)).exists())   # no archive of a rolled back emission

    def test_a_failure_in_the_initial_run_keeps_only_the_package_and_its_own_load(self):
        real = inference.infer

        def failing(sesion, horizon, *args, **kwargs):
            if horizon == 4:
                raise RuntimeError("falla simulada en h4")
            return real(sesion, horizon, *args, **kwargs)

        with patch.object(inference, "infer", failing):
            report = self.run_weekly(Options(inicial=True))
        self.assertEqual((report["estado"], report["etapa"]), ("fallida", "inferencia"))
        state = counts(self.motor)
        with transaction(self.motor) as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(Prediction).where(
                Prediction.id_semana_corte == self.cutoff)), 0)   # no forecast is published (the OOS history stays)
        self.assertEqual(len(weekly_inferences(self.motor)), 0)
        self.assertEqual(state["ejecuciones"][("reentrenamiento", "exitosa")], 1)   # publish committed its own load
        self.assertGreater(state["observaciones"], 0)
        self.assertFalse((self.base / "emisiones" / str(self.cutoff)).exists())

    def test_the_previous_forecast_stays_in_force(self):
        self.run_weekly(Options(inicial=True))
        with transaction(self.motor) as session:
            previous = {(p.ubigeo, p.horizonte): p.probabilidad_brote for p in session.scalars(select(Prediction))}
        self.cutoff, self.published, self.current = self.cutoff + 1, self.published + 1, self.batch(NEXT_CUTOFF)
        self.run_weekly(Options(), climate=lambda *args: (_ for _ in ()).throw(RuntimeError("sin red")))
        with transaction(self.motor) as session:
            now = {(p.ubigeo, p.horizonte): p.probabilidad_brote for p in session.scalars(select(Prediction))}
        self.assertEqual(now, previous)


class TestPreflightAndLock(LiveCase):
    def test_the_lock_prevents_two_runs_and_a_stale_one_is_replaced(self):
        lock = self.base / "en_curso.lock"
        lock.parent.mkdir(parents=True)
        lock.write_text("{}", encoding="utf-8")
        report = self.run_weekly(Options(inicial=True))
        self.assertEqual((report["estado"], report["etapa"]), ("fallida", "preflight"))
        self.assertIn("en curso", report["error"])
        self.assertTrue(lock.exists())   # the other run's lock is not ours to remove
        with transaction(self.motor) as session:   # a run that did not start is not a failed run
            self.assertEqual(session.scalar(select(func.count()).select_from(Run).where(Run.estado == "fallida")), 0)
        old = (datetime.now(timezone.utc) - timedelta(hours=v4_weekly.LOCK_STALE_HOURS + 1)).timestamp()
        os.utime(lock, (old, old))
        self.assertEqual(self.run_weekly(Options(inicial=True))["estado"], "emitida")
        self.assertFalse(lock.exists())

    def test_a_data_dir_override_is_rejected(self):
        with patch.dict(os.environ, {"DENGUEKAY_DATA_DIR": "data_anteriores/v2"}):
            report = self.run_weekly(Options(inicial=True))
        self.assertEqual((report["estado"], report["etapa"]), ("fallida", "preflight"))
        self.assertIn("DENGUEKAY_DATA_DIR", report["error"])
        self.assertEqual(self.calls, [])
        # HU0019-4: the failed preflight is a failed run with its reason, and nothing was published.
        with transaction(self.motor) as session:
            (failed,) = session.scalars(select(Run).where(Run.estado == "fallida")).all()
            self.assertIn("DENGUEKAY_DATA_DIR", failed.mensaje_error)
            self.assertEqual((failed.detalle["origen"], failed.detalle["etapa"]), (emissions.ORIGIN.replace(
                "actualizacion_semanal", "actualizacion_semanal"), "preflight"))
        self.assertEqual((counts(self.motor)["predicciones"], len(weekly_inferences(self.motor))), (0, 0))

    def test_a_configuration_other_than_the_operational_one_is_rejected(self):
        for change in ({"perfil_datos": "release"}, {"sala": "data/silver/confirmados/epi_sala_semanal.csv"},
                       {"era5_land": "data/silver/meteo_humedad_era5_land_2000_2026.csv"}):
            with self.subTest(change=change):
                original = service_settings(CONFIG, environ={})
                self.cfg = replace(original, paquete={**original.paquete, "opciones": {**original.opciones, **change}})
                report = self.run_weekly(Options(inicial=True))
                self.assertEqual((report["estado"], report["etapa"]), ("fallida", "preflight"))
                self.assertEqual(self.calls, [])

    def test_another_package_type_is_rejected(self):
        self.cfg = replace(self.cfg, paquete={**self.cfg.paquete, "tipo": "v3_l5a_d3"})
        self.assertEqual(self.run_weekly(Options(inicial=True))["etapa"], "preflight")

    def test_missing_frozen_files_ask_for_the_initial_run_or_extract_the_release(self):
        missing = [v4_weekly.ROOT / "data" / "falta.csv"]
        report = self.run_weekly(Options(), missing_files=lambda: missing)
        self.assertEqual(report["estado"], "fallida")
        self.assertIn(v4_weekly.INITIAL_COMMAND, report["error"])
        self.assertNotIn("release", [name for name, _, _ in self.calls])
        present = iter([missing, []])
        report = self.run_weekly(Options(inicial=True), missing_files=lambda: next(present, []))
        self.assertEqual(report["estado"], "emitida", report)
        self.assertEqual(self.calls[0][0], "release")

    def test_a_database_without_the_schema_is_rejected_with_the_migration_command(self):
        bare = make_engine(URL.create("sqlite", database=str(self.root / "vacia.db")))
        self.addCleanup(bare.dispose)
        report = v4_weekly.run(Options(inicial=True), motor=bare, cfg=self.cfg, storage=self.storage,
                               steps=self.steps(), base=self.base)
        self.assertEqual((report["estado"], report["etapa"]), ("fallida", "preflight"))
        self.assertIn("alembic upgrade head", report["error"])


class TestDryRun(LiveCase):
    def setUp(self):
        super().setUp()
        patcher = patch.object(v4_weekly, "BRONZE_SALA", self.root / "bronce")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_it_reports_the_state_and_touches_nothing(self):
        self.run_weekly(Options(inicial=True))
        before = counts(self.motor)
        files = sorted(path for path in self.base.rglob("*"))

        def forbidden(*args, **kwargs):
            raise AssertionError("dry-run no debe llamar a ningún paso")

        steps = v4_weekly.Steps(missing_files=lambda: [], ensure_release=forbidden, sala=forbidden,
                                expected_cutoff=forbidden, climate=forbidden, publish=forbidden,
                                prepare_load=forbidden, captures=forbidden, code_fingerprint=forbidden)
        report = v4_weekly.run(Options(dry_run=True, inicial=True), motor=self.motor, cfg=self.cfg,
                               storage=self.storage, steps=steps, base=self.base)
        self.assertEqual(report["estado"], "dry_run")
        self.assertEqual(report["ultimo_corte_emitido"], self.cutoff)
        self.assertEqual(report["archivos_faltantes"], [])
        self.assertIn("Sala", report["pasos"])
        self.assertEqual(counts(self.motor), before)
        self.assertEqual(sorted(path for path in self.base.rglob("*")), files)
        self.assertFalse((self.base / "en_curso.lock").exists())

    def test_it_works_before_the_database_is_ready(self):
        bare = make_engine(URL.create("sqlite", database=str(self.root / "vacia.db")))
        self.addCleanup(bare.dispose)
        report = v4_weekly.run(Options(dry_run=True), motor=bare, cfg=self.cfg, storage=self.storage,
                               steps=self.steps(), base=self.base)
        self.assertEqual(report["estado"], "dry_run")
        self.assertIsNone(report["ultimo_corte_emitido"])
        self.assertIn("no lista", report["base_de_datos"])
        self.assertFalse(self.base.exists())


class TestPartialAndHelpers(LiveCase):
    def test_unavailable_reasons_are_counted(self):
        path = self.root / "predicciones.csv"
        path.write_text("ubigeo,estado,motivo_no_disponible\n200101,disponible,\n200102,no_disponible,sin historial\n"
                        "200103,no_disponible,sin historial\n", encoding="utf-8")
        self.assertEqual(v4_weekly.unavailable_reasons(path), {"sin historial": 2})

    def test_a_partial_emission_lists_its_reasons(self):
        with patch.object(v4_weekly, "unavailable_reasons", return_value={"sin clima": 4}):
            report = self.run_weekly(Options(inicial=True))
        self.assertEqual(report["estado"], "emitida")
        self.assertIs(report["parcial"], True)
        self.assertEqual(report["motivos_no_disponible"], {"sin clima": 4})

    def test_the_stale_sala_is_only_a_warning(self):
        self.published = self.cutoff   # last published week: 2025-W03, long ago
        report = self.run_weekly(Options(inicial=True))
        self.assertEqual(report["estado"], "emitida")
        self.assertTrue(any("cerró hace más de" in item for item in report["advertencias"]))


class TestDefaultSteps(LiveCase):
    """The data steps use the operational files and no cutoff, and write nothing of the frozen copy."""

    def test_the_sala_step_refreshes_the_current_and_the_previous_year(self):
        recorded = {}

        async def fake(**kwargs):
            recorded.update(kwargs)

        with patch.object(v4_inputs, "sala_silver", fake):
            v4_weekly.step_sala(False)
            self.assertEqual(recorded["offline"], False)
            v4_weekly.step_sala(True)
        self.assertIsNone(recorded["cutoff"])
        self.assertEqual(recorded["output"], OPERATIONAL_SALA)
        self.assertEqual(recorded["refresh_years"], {date.today().year, date.today().year - 1})
        self.assertTrue(recorded["offline"])

    def test_the_climate_step_writes_the_operational_files_without_cutoff(self):
        with patch.object(v4_inputs, "download_era5_land") as download, \
                patch.object(v4_inputs, "era5_land_silver") as era5, patch.object(v4_inputs, "climate_silver") as climate, \
                patch.object(v4_inputs, "restore_published_bronze") as restore, \
                patch.object(v4_weekly, "historical_bronze_missing", return_value=[]):
            v4_weekly.step_climate(False, False)
            download.assert_called_once_with(max_hourly_waits=2)
            era5.assert_called_once_with(cutoff=None, output=OPERATIONAL_ERA5_LAND)
            climate.assert_called_once_with(offline=False, cutoff=None, enso_output=OPERATIONAL_ENSO,
                                            chirps_output=OPERATIONAL_CHIRPS)
            restore.assert_not_called()
            download.reset_mock()
            climate.reset_mock()
            v4_weekly.step_climate(True, False)   # --sin-descargas: nothing from the network
            download.assert_not_called()
            self.assertTrue(climate.call_args.kwargs["offline"])

    def test_the_initial_run_restores_the_missing_historical_bronze_first(self):
        with patch.object(v4_inputs, "download_era5_land"), patch.object(v4_inputs, "era5_land_silver"), \
                patch.object(v4_inputs, "climate_silver"), \
                patch.object(v4_inputs, "restore_published_bronze") as restore, \
                patch.object(v4_weekly, "historical_bronze_missing", return_value=[self.root / "falta"]):
            v4_weekly.step_climate(True, False)
            restore.assert_not_called()
            v4_weekly.step_climate(True, True)
            restore.assert_called_once_with()

    def test_the_operational_files_never_coincide_with_a_release_name(self):
        from denguekay.config.paths import V4_CHIRPS, V4_ENSO, V4_ERA5_LAND, V4_SALA
        self.assertFalse({OPERATIONAL_SALA, OPERATIONAL_ERA5_LAND, OPERATIONAL_CHIRPS, OPERATIONAL_ENSO}
                         & {V4_SALA, V4_ERA5_LAND, V4_CHIRPS, V4_ENSO})


if __name__ == "__main__":
    import unittest
    unittest.main()
