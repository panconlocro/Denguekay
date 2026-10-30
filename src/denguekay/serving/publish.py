"""Publication CLI: sources -> package of the configured predictor type -> Storage and database, audited.

Steps: load (ingestion), the type's fit and its MLflow logging (retraining), the package (manifest and
files) in Storage, its ``candidata`` versions (one per task and horizon) and its OOS predictions as past
cutoffs. The current inference is done by the API (``POST /admin/inferencias``, decision D2); ``--inferir``
also runs it in this process for local use. ``--seleccionar-experimental`` makes the package's versions the
experimental selection of its horizons (``parametro_sistema.seleccion_experimental``) in the same transaction:
which model is served is operational data, set by publication and not by a migration.
"""

import argparse
import hashlib
import json
import platform
import sys
import time

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from denguekay.db.models import Run, utc_now
from denguekay.db.session import make_engine, transaction
from denguekay.model.tracking import log_report
from denguekay.serving import parameters as parametros
from denguekay.serving.storage import storage_from_environment
from denguekay.serving.artifacts import json_fingerprint
from denguekay.serving.load_data import (require_schema, source_hashes, persist_load, prepare_load,
                                      record_failure)
from denguekay.serving.settings import service_settings
from denguekay.serving.inference import import_oos, infer
from denguekay.serving.models import save_versions, thresholds
from denguekay.serving.package import save_package
from denguekay.serving.predictors import predictor_module
from denguekay.config.paths import GOLD, ROOT, SERVING_RUNS, SRC


def code_hashes():
    """Logic changes are also part of the publication's identity."""
    # Decision D6: the code identity covers the whole denguekay package.
    files = sorted((SRC / "denguekay").rglob("*.py"))
    return {str(p.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in files}


def existing_publication(sesion, fingerprint):
    for run in sesion.scalars(select(Run).where(
            Run.tipo == "reentrenamiento", Run.estado == "exitosa").order_by(Run.id_ejecucion.desc())):
        if (run.detalle or {}).get("huella") == fingerprint:
            return run
    return None


def infer_current(motor, horizons, storage, servir_no_validadas):
    """Current inference of each horizon (what ``POST /admin/inferencias`` does), in one transaction."""
    with transaction(motor) as sesion:
        return [infer(sesion, h, storage=storage, servir_no_validadas=servir_no_validadas, origin="publicacion")
                for h in horizons]


def select_published(motor, summary, horizons):
    """Experimental selection with the versions of an already registered (reused) publication."""
    codes = {(v["horizonte"], v["tarea"]): v["codigo"] for v in summary["versiones"]}
    selection = {h: {task: codes[h, task] for (vh, task) in sorted(codes) if vh == h} for h in horizons}
    with transaction(motor) as sesion:
        return parametros.set_experimental_selection(sesion, selection)


def publish_to_db(motor, load, built, run_id, fingerprint, storage, start, *, servir_no_validadas=True,
                  run_inference=False, select_experimental=False):
    """Package in Storage, versions and OOS in a single transaction; optionally the experimental selection
    of its horizons and the current inference (which then uses that selection)."""
    with transaction(motor) as sesion:
        run = Run(tipo="reentrenamiento", estado="en_curso", detalle={"huella": fingerprint})
        sesion.add(run)
        sesion.flush()
        meets = thresholds(built, parametros.acceptance_criteria(sesion))
        path, sha256 = save_package(storage, built, meets)
        versions = save_versions(sesion, built, path, sha256, run_id, meets)
        oos = import_oos(sesion, built.oos, built.oos_detail, versions) if built.oos is not None else []
        selection = (parametros.set_experimental_selection(sesion, selection_of(versions, built.horizons))
                     if select_experimental else None)
        current = ([infer(sesion, h, storage=storage, servir_no_validadas=servir_no_validadas, origin="publicacion")
                    for h in built.horizons] if run_inference else [])
        summary = {"mlflow_run_id": run_id, "fecha_corte_datos": str(load.fecha_corte_datos),
                   "paquete": {"codigo": built.code, "tipo_predictor": built.kind, "ruta": path, "sha256": sha256},
                   "versiones": [{"codigo": v.codigo, "tarea": v.tarea, "horizonte": v.horizonte,
                                  "cumple_umbrales": v.cumple_umbrales, "estado": v.estado,
                                  "ruta_artefacto": v.ruta_artefacto} for v in versions.values()],
                   "oos": oos, "seleccion_experimental": selection, "inferencias_vigentes": current}
        run.estado, run.fin = "exitosa", utc_now()
        run.id_semana_corte = current[0]["id_semana_corte"] if current else None
        run.detalle = {"huella": fingerprint, "resumen": summary,
                       "duracion_segundos": round(time.perf_counter() - start, 3)}
        sesion.flush()
        return {"id_ejecucion": run.id_ejecucion, "reutilizada": False, **summary}


def selection_of(versions, horizons):
    """{horizon: {task: code}} of a package's versions."""
    return {h: {task: v.codigo for (vh, task), v in sorted(versions.items()) if vh == h} for h in horizons}


def publish(motor, horizons=None, *, cfg=None, storage=None, run_inference=False, select_experimental=False):
    """Validate, fit, log to MLflow and commit the publication in the database."""
    start = time.perf_counter()
    cfg = cfg or service_settings()
    storage = storage or storage_from_environment(cfg.almacenamiento)
    builder = predictor_module(cfg.tipo_paquete)
    horizons = tuple(sorted(horizons if horizons is not None else cfg.horizontes))
    if not horizons or len(set(horizons)) != len(horizons):
        raise ValueError("Indique horizontes no repetidos")
    builder.validate(horizons, cfg.opciones)
    require_schema(motor)
    load = prepare_load()
    prepared = builder.prepare(horizons, cfg.opciones)
    hashes = {**load.hashes, **prepared.hashes, **code_hashes()}
    fingerprint = json_fingerprint({"hashes": hashes, "configuracion": cfg.publication_options(), "horizontes": horizons,
                                    **builder.fingerprint_parameters(),
                                    "plataforma": f"{platform.system()} {platform.release()} {platform.machine()}"})
    with transaction(motor) as sesion:
        persist_load(sesion, load)
        previous = existing_publication(sesion, fingerprint)
        if previous is not None:
            summary = {"id_ejecucion": previous.id_ejecucion, "reutilizada": True, **previous.detalle["resumen"]}
    if previous is not None:
        if select_experimental:
            summary["seleccion_experimental"] = select_published(motor, summary, horizons)
        if run_inference:
            summary["inferencias_vigentes"] = infer_current(motor, horizons, storage, cfg.servir_no_validadas)
        return summary
    try:
        built = builder.build(prepared, horizons, cfg.opciones, load.fecha_corte_datos)
        directory = SERVING_RUNS / fingerprint
        directory.mkdir(parents=True, exist_ok=True)
        report_path = directory / "reporte_servicio.json"
        report_path.write_text(json.dumps(built.report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        run_id = log_report("serving", built.report, metrics_path=report_path,
            output_dir=directory, gold_dir=GOLD, data_quality=load.validacion_gx,
            description="Ajuste de servicio. La evaluación temporal adjunta es importada del protocolo previo, no un entrenamiento OOS de esta corrida.")
        if load.hashes != source_hashes() or code_hashes() != {k: v for k, v in hashes.items() if k.startswith("src/denguekay/")}:
            raise ValueError("Las entradas o el código cambiaron durante la ejecución; publicación rechazada")
        summary = publish_to_db(motor, load, built, run_id, fingerprint, storage, start,
                                servir_no_validadas=cfg.servir_no_validadas, run_inference=run_inference,
                                select_experimental=select_experimental)
        (directory / "publicacion.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str) + "\n",
                                                    encoding="utf-8")
        return summary
    except Exception as error:
        record_failure(motor, "reentrenamiento", error, {"huella": fingerprint})
        raise


def main(argv=None):
    """``python -m denguekay.serving.publish [--horizontes 2 3 4] [--seleccionar-experimental] [--inferir]``."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--horizontes", nargs="+", type=int, choices=(2, 3, 4), default=None,
                        help="Por defecto, los del paquete configurado en config.yaml (serving.paquete)")
    parser.add_argument("--seleccionar-experimental", action="store_true",
                        help="Fija las versiones publicadas como selección experimental de sus horizontes")
    parser.add_argument("--inferir", action="store_true",
                        help="Además corre la inferencia vigente en este proceso (uso local; en despliegue la hace la API)")
    args = parser.parse_args(argv)
    motor = None
    try:
        motor = make_engine()
        print(json.dumps(publish(motor, args.horizontes, run_inference=args.inferir,
                                 select_experimental=args.seleccionar_experimental), ensure_ascii=False, default=str))
        return 0
    except SQLAlchemyError:
        print("No se pudo publicar: revise la conexión, migraciones y permisos de la BD", file=sys.stderr)
    except (ValueError, OSError) as error:
        print(f"Publicación rechazada: {error}", file=sys.stderr)
    except Exception as error:
        print(f"La publicación no terminó ({type(error).__name__}); revise la ejecución registrada", file=sys.stderr)
    finally:
        if motor is not None:
            motor.dispose()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
