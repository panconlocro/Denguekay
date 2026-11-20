"""Weekly update of the service with the frozen V4: new data, load and forecast of h = 2, 3 and 4.

``python -m denguekay.pipelines.v4_weekly`` brings the sources that keep moving (Sala Situacional, ERA5-Land,
CHIRPS and Niño 1+2) into ``data/silver/operativo/`` without the frozen cutoff, loads them into the database and
emits the forecast of the cutoff week with the frozen package ``v4_b3_live`` (the boosters of the ``model/v4``
Release), archiving every emission. It never trains a model, never writes the frozen copy of ``data/silver/`` or
``data/gold/``, and publishes nothing new if a step fails: load and inference share one transaction and the failure
is recorded in ``ejecucion``. The exception is ``--inicial`` on a new database: ``publish`` registers the frozen
package and commits its own load of the data first (its own transaction); if the emission then fails, that load and
the package stay, and no forecast is published. It is the V4 operation; ``weekly_update`` (selective update of the integrated silver
and the Sala of the per-version pipelines) is another thing and does not change.

Steps: preflight, Sala, is there a new week?, climate, publication (``--inicial`` only), load + inference + archive,
report. The orchestration takes its steps from a ``Steps`` object so that each one can be replaced in the tests.
"""

import argparse
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import sys
from time import perf_counter

import pandas as pd
from sqlalchemy import inspect, select
from sqlalchemy.exc import SQLAlchemyError

from denguekay.config.paths import (
    BRONZE_CHIRPS_EE_FINAL, BRONZE_CHIRPS_FINAL, BRONZE_CHIRPS_FINAL_FTP, BRONZE_CHIRPS_PRELIM, BRONZE_ENSO,
    BRONZE_SALA, CACHE_METEO, CACHE_METEO_ERA5_LAND_RECENT, DATA, DATA_DIR, OPERATIONAL_CHIRPS, OPERATIONAL_ENSO,
    OPERATIONAL_ERA5_LAND, OPERATIONAL_SALA, ROOT, SERVING_WEEKLY, V4_CHIRPS_SNAPSHOTS, V4_DATA_MANIFEST, V4_FROZEN,
    V4_GEOGRAPHY, V4_HISTORY, V4_INTEGRATED,
)
from denguekay.data.processing.epi_sala import SALA_FIRST_YEAR
from denguekay.data.validation.integrated_expectations import coverage_path
from denguekay.db.models import Run
from denguekay.db.session import make_engine, transaction
from denguekay.pipelines import v4_inputs
from denguekay.pipelines.weekly_update import run_sync
from denguekay.serving import drift, emissions
from denguekay.serving.emissions import HORIZONS, ORIGIN

LOCK_STALE_HOURS = 12
STALE_SALA_DAYS = 70   # a Sala whose last published week closed that long ago is reported (not an error)
STATES_OK = ("emitida", "sin_novedad", "cargada_sin_emitir", "dry_run")
EXPECTED_OPTIONS = {"sala": OPERATIONAL_SALA, "era5_land": OPERATIONAL_ERA5_LAND, "chirps": OPERATIONAL_CHIRPS,
                    "nino12": OPERATIONAL_ENSO}
INITIAL_COMMAND = "python -m denguekay.pipelines.v4_weekly --inicial"


class WeeklyError(RuntimeError):
    """A step failed. ``kind`` is the type of run that records it; ``recorded`` is set when it already did."""

    def __init__(self, message, *, kind="ingesta", step=None, recorded=False):
        super().__init__(message)
        self.kind, self.step, self.recorded = kind, step, recorded


@dataclass(frozen=True)
class Options:
    inicial: bool = False
    dry_run: bool = False
    sin_descargas: bool = False
    forzar: bool = False
    reemitir: bool = False
    preparar: bool = False

    @property
    def force(self):
        return self.forzar or self.reemitir


# --- default steps ---------------------------------------------------------------------

def required_files():
    """The frozen files the operation reads and does not write."""
    return [V4_INTEGRATED, coverage_path(V4_INTEGRATED), V4_HISTORY, V4_FROZEN / "paquete.json", V4_GEOGRAPHY]


def missing_files():
    return [path for path in required_files() if not path.is_file()]


def step_sala(offline):
    """Sala 2025 onwards without cutoff: the current and the previous year are scraped, the others replayed."""
    today = date.today()
    years = {year for year in (today.year, today.year - 1) if year >= SALA_FIRST_YEAR}
    return run_sync(v4_inputs.sala_silver(offline=offline, cutoff=None, refresh_years=years, output=OPERATIONAL_SALA))


def historical_bronze_missing():
    folders = [CACHE_METEO, *(folder for _, _, folder in v4_inputs._weather_caches()), BRONZE_CHIRPS_FINAL,
               BRONZE_CHIRPS_FINAL_FTP, BRONZE_CHIRPS_PRELIM, BRONZE_CHIRPS_EE_FINAL]
    return [folder for folder in folders if not (folder.is_dir() and any(folder.iterdir()))]


def step_climate(offline, initial):
    """ERA5-Land, CHIRPS and Niño 1+2 silver without cutoff, apart from the frozen copy."""
    if initial and historical_bronze_missing():
        v4_inputs.restore_published_bronze()
    report = {}
    if not offline:
        report["descarga_era5_land"] = v4_inputs.download_era5_land(max_hourly_waits=2)
    report["era5_land"] = v4_inputs.era5_land_silver(cutoff=None, output=OPERATIONAL_ERA5_LAND)
    report["clima"] = v4_inputs.climate_silver(offline=offline, cutoff=None, enso_output=OPERATIONAL_ENSO,
                                               chirps_output=OPERATIONAL_CHIRPS)
    return report


def step_expected_cutoff(options):
    """(cutoff id_semana, last published id_semana, provisional id_semana list) from the panel and the Sala."""
    from denguekay.features.long_history import sala_after_panel
    from denguekay.serving.load_data import week_id

    panel = pd.read_csv(V4_INTEGRATED, dtype={"ubigeo": "string"}, usecols=["ubigeo", "anio", "semana"])
    sala = pd.read_csv(ROOT / options.get("sala", OPERATIONAL_SALA.relative_to(ROOT).as_posix()),
                       dtype={"ubigeo": "string"})
    extra, dropped = sala_after_panel(panel, sala, provisional=options.get("semanas_provisionales", 2))
    if extra.empty:
        raise ValueError("La Sala no trae semanas posteriores al panel verificado")
    last = extra.sort_values(["anio", "semana"]).iloc[-1]
    published = sala.sort_values(["anio", "semana"]).iloc[-1]
    return (week_id(last.anio, last.semana), week_id(published.anio, published.semana),
            [week_id(year, week) for year, week in dropped])


def published_week_end(week):
    """Saturday that closes the epidemiological week ``week`` (``anio * 100 + semana``)."""
    from denguekay.features.long_history import week_grid

    year, number = divmod(week, 100)
    grid = week_grid(year, year)
    return (grid.loc[grid.semana.eq(number), "semana_inicio"].iloc[0] + pd.Timedelta(days=6)).date()


def step_prepare_load(options):
    from denguekay.serving.predictors import v4_b3_live

    return v4_b3_live.prepare_load(options)


def step_publish(motor, cfg, storage):
    from denguekay.serving.publish import publish

    return publish(motor, cfg=cfg, storage=storage, select_experimental=True, run_inference=False)


def step_captures():
    """The captures a run used (names only), for the archive of the emission."""
    def latest(paths):
        paths = sorted(paths)
        return paths[-1].name if paths else None

    return {
        "sala": {str(year): latest(BRONZE_SALA.glob(f"{year}_*")) for year in range(SALA_FIRST_YEAR, date.today().year + 1)},
        "era5_land_reciente": latest(CACHE_METEO_ERA5_LAND_RECENT.glob("????-??-??")),
        "chirps": latest(V4_CHIRPS_SNAPSHOTS.glob("*.zip")),
        "enso": latest(BRONZE_ENSO.glob("sstoi_????????.indices")),
    }


def step_code_fingerprint():
    from denguekay.serving.artifacts import json_fingerprint
    from denguekay.serving.publish import code_hashes

    return json_fingerprint(code_hashes())


@dataclass
class Steps:
    missing_files: object = missing_files
    ensure_release: object = v4_inputs.ensure_operational_release
    sala: object = step_sala
    expected_cutoff: object = step_expected_cutoff
    climate: object = step_climate
    publish: object = step_publish
    prepare_load: object = step_prepare_load
    captures: object = step_captures
    code_fingerprint: object = step_code_fingerprint
    package_version: object = field(default=lambda: package_version())


def package_version():
    try:
        return importlib.metadata.version("denguekay")
    except importlib.metadata.PackageNotFoundError:
        return "desconocida"


# --- preflight ---------------------------------------------------------------------------

def check_environment(cfg):
    if os.environ.get("DENGUEKAY_DATA_DIR") or DATA_DIR != DATA:
        raise WeeklyError("DENGUEKAY_DATA_DIR está definido: la operación semanal es dueña de data/ y exige que no lo esté",
                          step="preflight")
    options = cfg.opciones
    if cfg.tipo_paquete != "v4_b3_live" or tuple(cfg.horizontes) != HORIZONS:
        raise WeeklyError("config.yaml debe servir el paquete v4_b3_live con los horizontes 2, 3 y 4", step="preflight")
    if options.get("paquete_dir") and not (ROOT / options["paquete_dir"] / "paquete.json").is_file():
        raise WeeklyError(
            f"config.yaml sirve el reajuste serving.paquete.opciones.paquete_dir = {options['paquete_dir']} y su carpeta "
            "(paquete.json) no está en este equipo: cópiela desde donde la dejó refit_v4 (fuera de Git) o quite la "
            "opción para servir el paquete congelado del Release model/v4 (docs/backend/operacion.md)",
            step="preflight")
    if options.get("perfil_datos") != "fuentes":
        raise WeeklyError("serving.paquete.opciones.perfil_datos debe ser «fuentes»", step="preflight")
    for key, path in EXPECTED_OPTIONS.items():
        if options.get(key) != path.relative_to(ROOT).as_posix():
            raise WeeklyError(f"serving.paquete.opciones.{key} debe ser {path.relative_to(ROOT).as_posix()}",
                              step="preflight")


def check_database(motor):
    from denguekay.serving.load_data import require_schema

    try:
        require_schema(motor)
    except ValueError as error:
        raise WeeklyError(str(error), step="preflight") from error
    if "observacion_nino12" not in set(inspect(motor).get_table_names()):
        raise WeeklyError("Falta la tabla observacion_nino12 (migración 0008_v4): ejecute alembic upgrade head",
                          step="preflight")


def acquire_lock(path, *, now):
    """Exclusive creation of the lock file; one older than ``LOCK_STALE_HOURS`` is an orphan and is replaced."""
    path.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            with open(path, "x", encoding="utf-8") as lock:
                lock.write(json.dumps({"pid": os.getpid(), "desde_utc": now.isoformat()}))
            return True
        except FileExistsError:
            age = now - datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            if age < timedelta(hours=LOCK_STALE_HOURS):
                raise WeeklyError(f"Ya hay una actualización semanal en curso ({path.name}); si no es así, borre el "
                                  f"candado: {path}", step="preflight") from None
            path.unlink(missing_ok=True)
    raise WeeklyError("No se pudo tomar el candado de la actualización semanal", step="preflight")


# --- database queries ------------------------------------------------------------------------

def last_emitted(sesion):
    runs = [run for run in sesion.scalars(select(Run).where(Run.tipo == "inferencia", Run.estado == "exitosa"))
            if (run.detalle or {}).get("origen") == ORIGIN]
    return max((run.id_semana_corte for run in runs), default=None)


def serving_ready(motor, cfg, storage):
    """(True, None) when every horizon has versions in use that belong to the frozen V4 package."""
    from denguekay.serving.artifacts import InvalidArtifact
    from denguekay.serving.inference import package_of, select_versions
    from denguekay.serving.predictors import v4_b3_live

    with transaction(motor) as sesion:
        for horizon in HORIZONS:
            versions, reason = select_versions(sesion, horizon, cfg.servir_no_validadas)
            if reason is not None:
                return False, reason
            try:
                package = package_of(versions, storage)
            except InvalidArtifact as error:
                return False, str(error)
            if package.kind != v4_b3_live.KIND:
                return False, f"El paquete en uso en h={horizon} no es {v4_b3_live.KIND}"
    return True, None


# --- run -------------------------------------------------------------------------------------------

class Timer:
    def __init__(self, report):
        self.durations = report.setdefault("duraciones_segundos", {})

    def __call__(self, name):
        timer = self

        class Block:
            def __enter__(self):
                self.start = perf_counter()

            def __exit__(self, *exc):
                timer.durations[name] = round(timer.durations.get(name, 0) + perf_counter() - self.start, 2)

        return Block()


def write_report(report, base):
    folder = Path(base) / "ejecuciones"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{emissions.stamp(emissions.now_utc())}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    return path


def dry_run(options, motor, steps, cfg):
    """State of the operation without network, locks or writes."""
    report = {"estado": "dry_run", "banderas": options.__dict__.copy()}
    report["archivos_faltantes"] = [path.relative_to(ROOT).as_posix() for path in steps.missing_files()]
    report["silver_operativos"] = {path.name: path.is_file() for path in EXPECTED_OPTIONS.values()}
    captures = sorted(BRONZE_SALA.glob("*_*")) if BRONZE_SALA.is_dir() else []
    report["ultima_captura_sala"] = captures[-1].name if captures else None
    try:
        with transaction(motor) as sesion:
            check_database(motor)
            report["ultimo_corte_emitido"] = last_emitted(sesion)
    except (WeeklyError, SQLAlchemyError) as error:
        report["ultimo_corte_emitido"] = None
        report["base_de_datos"] = f"no lista: {error}"
    plan = ["preflight"]
    if (options.inicial or options.preparar) and report["archivos_faltantes"]:
        plan.append("extraer del Release lo que falta")
    plan += ["Sala", "¿semana nueva?"]
    if not options.sin_descargas:
        plan.append("descargas de clima")
    plan += ["silver de ERA5-Land, CHIRPS y Niño 1+2"]
    if options.inicial:
        plan.append("publicar el paquete V4 si hace falta (selección experimental)")
    plan += ["carga + inferencia h2, h3 y h4 + archivo de la emisión", "informe"]
    report["pasos"] = plan
    return report


def run(options, *, motor, cfg, storage, steps=None, now=None, base=None):
    """Run the update and return its report (``estado`` in ``STATES_OK`` or ``fallida``). It raises nothing it can
    record: failures end in the report and in ``ejecucion``."""
    steps = steps or Steps()
    base = Path(base) if base is not None else SERVING_WEEKLY
    started = now or emissions.now_utc()
    report = {"iniciada_utc": started.isoformat(), "banderas": options.__dict__.copy()}
    timer = Timer(report)
    if options.dry_run:
        return dry_run(options, motor, steps, cfg)
    locked = False
    stage = "preflight"
    try:
        check_environment(cfg)
        locked = acquire_lock(base / "en_curso.lock", now=started)
        missing = steps.missing_files()
        if missing:
            if not (options.inicial or options.preparar):
                raise WeeklyError("Faltan archivos de la copia congelada (" + ", ".join(
                    path.relative_to(ROOT).as_posix() for path in missing) + f"); ejecute: {INITIAL_COMMAND}",
                                  step=stage)
            with timer("release"):
                report["release"] = steps.ensure_release()
            if steps.missing_files():
                raise WeeklyError("Después de extraer el Release siguen faltando archivos", step=stage)
        check_database(motor)

        stage = "sala"
        with timer("sala"):
            steps.sala(options.sin_descargas)
        cutoff, last_published, provisional = steps.expected_cutoff(cfg.opciones)
        report.update(id_semana_corte=cutoff, ultima_semana_sala_publicada=last_published)
        if (date.today() - published_week_end(last_published)).days > STALE_SALA_DAYS:
            report.setdefault("advertencias", []).append(
                f"La última semana publicada por la Sala ({last_published}) cerró hace más de {STALE_SALA_DAYS} días")
        with transaction(motor) as sesion:
            emitted = emissions.already_emitted(sesion, cutoff)
        report["corte_ya_emitido"] = emitted
        if emitted and not options.force:
            report["estado"] = "sin_novedad"
            return finish(report, motor, base, cutoff, timer, cfg.opciones)

        stage = "clima"
        with timer("clima"):
            report["clima"] = steps.climate(options.sin_descargas, options.inicial or options.preparar)

        if options.inicial:
            stage = "publicacion"
            ready, reason = serving_ready(motor, cfg, storage)
            if not ready:
                report["publicacion"] = reason
                with timer("publicacion"):
                    try:
                        steps.publish(motor, cfg, storage)
                    except Exception as error:
                        raise WeeklyError(f"La publicación del paquete V4 falló: {error}", kind="reentrenamiento",
                                          step=stage, recorded=True) from error
                ready, reason = serving_ready(motor, cfg, storage)
                if not ready:
                    raise WeeklyError(f"El paquete V4 no quedó en uso: {reason}", step=stage)
        else:
            ready, reason = serving_ready(motor, cfg, storage)
            if not ready:
                raise WeeklyError(f"El paquete V4 no está publicado ({reason}); ejecute: {INITIAL_COMMAND}",
                                  step="preflight")

        stage = "carga"
        with timer("carga"):
            data = steps.prepare_load(cfg.opciones)
        loaded = max(row["id_semana"] for row in data.observaciones)
        if loaded != cutoff:
            raise WeeklyError(f"El corte cargado ({loaded}) no es el esperado ({cutoff})", step=stage)
        emit = (not emitted) or options.reemitir
        archive = None
        try:
            with timer("inferencia"), transaction(motor) as sesion:
                ingestion = steps_persist(sesion, data)
                if emit:
                    stage = "inferencia"
                    emitted_at = emissions.now_utc()
                    results = emit_horizons(sesion, cutoff, storage, cfg)
                    first = emissions.record_first_emission(sesion, results, last_published=last_published,
                                                            emitted_at=emitted_at)
                    archive = emissions.archive_emission(
                        sesion, cutoff=cutoff, ingestion=ingestion, results=results, load=data,
                        emitted_at=emitted_at, reissue=emitted, last_published=last_published,
                        provisional=provisional, captures=steps.captures(),
                        code_fingerprint=steps.code_fingerprint(), package_version=steps.package_version(),
                        frozen_manifest=json.loads(V4_DATA_MANIFEST.read_text(encoding="utf-8")),
                        servir_no_validadas=cfg.servir_no_validadas, storage=storage, base=base / "emisiones")
        except BaseException:
            if archive is not None:
                shutil.rmtree(archive, ignore_errors=True)
                try:
                    archive.parent.rmdir()   # the cutoff folder, when this was its only emission
                except OSError:
                    pass
            raise
        report["carga"] = {key: ingestion[key] for key in ("id_ejecucion", "reutilizada", "observaciones")
                           if key in ingestion}
        if emit:
            record = json.loads((archive / "emision.json").read_text(encoding="utf-8"))
            report["emision"] = archive.relative_to(base).as_posix()
            if cfg.almacenamiento != "local":   # the runner may not survive: keep the archive in the Storage too
                try:
                    report["archivo_en_storage"] = emissions.upload_archive(storage, archive, base / "emisiones")
                except Exception as error:   # noqa: BLE001 - the emission is already committed; say it, do not undo it
                    report["archivo_en_storage"] = f"fallido: {type(error).__name__}"
                    report.setdefault("advertencias", []).append(
                        f"La emisión quedó en la BD pero su archivo no se copió al Storage ({type(error).__name__}); "
                        f"consérvelo desde {archive.relative_to(base).as_posix()}")
            report["primera_emision"] = first
            report["disponibles"] = record["predicciones"]["disponibles"]
            report["ejecuciones"] = record["ejecuciones"]
            reasons = unavailable_reasons(archive / "predicciones.csv")
            report["parcial"] = bool(reasons)
            if reasons:
                report["motivos_no_disponible"] = reasons
            report["estado"] = "emitida"
        else:
            report["estado"] = "cargada_sin_emitir"
        return finish(report, motor, base, cutoff, timer, cfg.opciones)
    except Exception as error:
        report["estado"] = "fallida"
        report["error"] = f"{type(error).__name__}: {error}"
        report["etapa"] = getattr(error, "step", None) or stage
        if not getattr(error, "recorded", False) and report["etapa"] != "preflight":
            kind = getattr(error, "kind", None) or ("inferencia" if stage == "inferencia" else "ingesta")
            record_failure_safely(motor, kind, error, {"origen": ORIGIN, "etapa": report["etapa"]})
        return finish(report, None, base, None, timer)
    finally:
        if locked:
            (base / "en_curso.lock").unlink(missing_ok=True)


def steps_persist(sesion, data):
    from denguekay.serving.load_data import persist_load

    return persist_load(sesion, data)


def emit_horizons(sesion, cutoff, storage, cfg):
    from denguekay.serving.inference import infer

    results = []
    for horizon in HORIZONS:
        result = infer(sesion, horizon, cutoff, storage=storage, servir_no_validadas=cfg.servir_no_validadas,
                       origin=ORIGIN)
        if not result.get("paquete") or not result.get("disponibles"):
            raise WeeklyError(f"La inferencia de h={horizon} no produjo predicciones disponibles "
                              f"({result.get('motivo')})", kind="inferencia", step="inferencia")
        results.append(result)
    return results


def unavailable_reasons(path):
    frame = pd.read_csv(path)
    rows = frame[frame.estado.ne("disponible")]
    return {} if rows.empty else {str(reason): int(count) for reason, count in
                                  rows.motivo_no_disponible.value_counts().items()}


def record_failure_safely(motor, kind, error, detail):
    from denguekay.serving.load_data import record_failure

    try:
        record_failure(motor, kind, error, detail)
    except Exception as secondary:   # the report still carries the failure
        print(f"No se pudo registrar el fallo en ejecucion: {type(secondary).__name__}", file=sys.stderr)


def finish(report, motor, base, cutoff, timer, options=None):
    """Follow-up and notice (when the database answers), then the report file."""
    if motor is not None and cutoff is not None:
        try:
            with transaction(motor) as sesion:
                report["seguimiento_prospectivo"] = emissions.prospective_scores(sesion)
                try:   # the review is a record: a failure in it must never lose the follow-up or the weekly report
                    report["monitoreo_deriva"] = drift.drift_report(sesion)
                except Exception as error:   # noqa: BLE001
                    report["monitoreo_deriva"] = f"no disponible: {type(error).__name__}"
                try:   # the package folder that names the labels cutoff may not exist on the machine that runs this
                    notice = emissions.retraining_due(sesion, cutoff, options=options)
                except (OSError, ValueError, KeyError) as error:
                    notice = {}
                    report["aviso_reentrenamiento"] = f"no disponible: {type(error).__name__}: {error}"
            report.update(notice)
            if notice.get("reentrenamiento_anual_pendiente"):
                report["aviso"] = ("Se alcanzó el cierre de la temporada: corresponde el reentrenamiento anual "
                                   "(docs/modeling/reentrenamiento.md). Esta actualización no entrena.")
        except SQLAlchemyError as error:
            report["seguimiento_prospectivo"] = f"no disponible: {type(error).__name__}"
    report["terminada_utc"] = emissions.now_utc().isoformat()
    report["informe"] = write_report(report, base).relative_to(base).as_posix()
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inicial", action="store_true",
                        help="Primera corrida en una BD nueva: extrae lo que falte del Release y publica el paquete V4")
    parser.add_argument("--dry-run", action="store_true", help="Muestra el estado y los pasos sin red ni escrituras")
    parser.add_argument("--preparar", action="store_true",
                        help="Equipo vacío (GitHub Actions): extrae del Release lo que falte y restaura el bronce "
                             "histórico verificado, sin publicar el paquete")
    parser.add_argument("--sin-descargas", action="store_true", help="Reanuda desde los cachés, sin red")
    parser.add_argument("--forzar", action="store_true", help="Carga aunque el corte ya esté emitido (sin emitir)")
    parser.add_argument("--reemitir", action="store_true", help="Emite de nuevo un corte ya emitido (implica --forzar)")
    args = parser.parse_args(argv)
    options = Options(args.inicial, args.dry_run, args.sin_descargas, args.forzar, args.reemitir, args.preparar)
    motor = None
    try:
        from denguekay.serving.settings import service_settings
        from denguekay.serving.storage import storage_from_environment

        cfg = service_settings()
        motor = make_engine()
        report = run(options, motor=motor, cfg=cfg, storage=storage_from_environment(cfg.almacenamiento))
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return 0 if report["estado"] in STATES_OK else 1
    except (SQLAlchemyError, ValueError, OSError) as error:
        print(f"Actualización semanal rechazada: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    finally:
        if motor is not None:
            motor.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
