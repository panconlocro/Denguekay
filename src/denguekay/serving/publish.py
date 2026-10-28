"""Publication CLI: sources -> XGBoost fit (train.py) -> Storage and database, with an auditable run.

Steps: load (ingestion), serving fit and MLflow logging (retraining), ``candidata``
versions with their booster in Storage, the protocol's OOS predictions as past
cutoffs and the inference of the current cutoff.
"""

import argparse
from dataclasses import asdict
import hashlib
import json
import platform
import sys
import time

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from xgboost import __version__ as XGBOOST_VERSION

from denguekay.db.models import Run, utc_now
from denguekay.db.session import make_engine, transaction
from denguekay.model.tracking import log_report
from denguekay.model.train import BASE_PARAMS
from denguekay.serving import parameters as parametros
from denguekay.serving.storage import LocalStorage
from denguekay.serving.artifacts import json_fingerprint
from denguekay.serving.load_data import (require_schema, source_hashes, persist_load, prepare_load,
                                      record_failure)
from denguekay.serving.settings import service_settings
from denguekay.serving.inference import import_oos, infer
from denguekay.serving.models import train_service_versions, save_versions, service_report
from denguekay.serving.protocol import load_protocol
from denguekay.config.paths import GOLD, ROOT, SERVING_RUNS, SILVER_INTEGRATED, SRC


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


def publish_to_db(motor, load, protocol, prepared_versions, horizons, cfg, run_id, fingerprint, storage, start):
    """Versions, OOS and current inference in a single transaction."""
    with transaction(motor) as sesion:
        run = Run(tipo="reentrenamiento", estado="en_curso", detalle={"huella": fingerprint})
        sesion.add(run)
        sesion.flush()
        versions = save_versions(sesion, prepared_versions, run_id, parametros.acceptance_criteria(sesion), storage)
        oos = import_oos(sesion, protocol, horizons, cfg, versions)
        current_rows = [infer(sesion, h, storage=storage,
                            servir_no_validadas=cfg.servir_no_validadas, origin="publicacion")
                    for h in horizons]
        summary = {"mlflow_run_id": run_id, "fecha_corte_datos": str(load.fecha_corte_datos),
                   "versiones": [{"codigo": v.codigo, "tarea": v.tarea, "horizonte": v.horizonte,
                                  "cumple_umbrales": v.cumple_umbrales, "estado": v.estado,
                                  "ruta_artefacto": v.ruta_artefacto} for v in versions.values()],
                   "oos": oos, "inferencias_vigentes": current_rows}
        run.estado, run.fin = "exitosa", utc_now()
        run.id_semana_corte = current_rows[0]["id_semana_corte"] if current_rows else None
        run.detalle = {"huella": fingerprint, "resumen": summary,
                             "duracion_segundos": round(time.perf_counter() - start, 3)}
        sesion.flush()
        return {"id_ejecucion": run.id_ejecucion, "reutilizada": False, **summary}


def publish(motor, horizons=None, *, cfg=None, storage=None):
    """Validate, fit, log to MLflow and commit the publication in the database."""
    start = time.perf_counter()
    cfg = cfg or service_settings()
    storage = storage or LocalStorage()
    horizons = tuple(sorted(horizons if horizons is not None else cfg.horizontes))
    if not horizons or len(set(horizons)) != len(horizons):
        raise ValueError("Indique horizontes no repetidos")
    for h in horizons:
        if h not in (2, 4):
            raise ValueError("No hay gold ni contrato de modelado para horizonte 3; no se inventarán predicciones")
        if not (GOLD / f"{SILVER_INTEGRATED.stem}_h{h}_gold.csv").exists():
            raise ValueError(f"Falta el gold para horizonte {h}")
    require_schema(motor)
    load = prepare_load()
    protocol = load_protocol(horizons, cfg.variantes)
    hashes = {**load.hashes, **protocol.hashes, **code_hashes()}
    fingerprint = json_fingerprint({"hashes": hashes, "configuracion": asdict(cfg), "horizontes": horizons,
                          "parametros": BASE_PARAMS, "xgboost": XGBOOST_VERSION,
                          "plataforma": f"{platform.system()} {platform.release()} {platform.machine()}"})
    with transaction(motor) as sesion:
        persist_load(sesion, load)
        previous = existing_publication(sesion, fingerprint)
        if previous is not None:
            return {"id_ejecucion": previous.id_ejecucion, "reutilizada": True, **previous.detalle["resumen"]}
    try:
        prepared_versions = train_service_versions(protocol, horizons, cfg, load.fecha_corte_datos)
        directory = SERVING_RUNS / fingerprint
        directory.mkdir(parents=True, exist_ok=True)
        report = service_report(prepared_versions, protocol, load.fecha_corte_datos)
        report_path = directory / "reporte_servicio.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        run_id = log_report("serving", report, metrics_path=report_path,
            output_dir=directory, gold_dir=GOLD, data_quality=load.validacion_gx,
            description="Ajuste de servicio. La evaluación temporal adjunta es importada del protocolo previo, no un entrenamiento OOS de esta corrida.")
        if load.hashes != source_hashes() or code_hashes() != {k: v for k, v in hashes.items() if k.startswith("src/")}:
            raise ValueError("Las entradas o el código cambiaron durante la ejecución; publicación rechazada")
        summary = publish_to_db(motor, load, protocol, prepared_versions, horizons, cfg, run_id, fingerprint,
                                 storage, start)
        (directory / "publicacion.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return summary
    except Exception as error:
        record_failure(motor, "reentrenamiento", error, {"huella": fingerprint})
        raise


def main(argv=None):
    """``python -m denguekay.serving.publish --horizontes 2 4``."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--horizontes", nargs="+", type=int, choices=(2, 3, 4), default=None,
                        help="Horizontes con gold y contrato disponibles (2 y 4)")
    args = parser.parse_args(argv)
    motor = None
    try:
        motor = make_engine()
        print(json.dumps(publish(motor, args.horizontes), ensure_ascii=False, default=str))
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
