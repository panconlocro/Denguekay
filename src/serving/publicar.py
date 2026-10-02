"""CLI de publicación: fuentes → ajuste XGBoost (train.py) → Storage y BD, con ejecución auditable.

Pasos: carga (ingesta), ajuste de servicio y registro MLflow (reentrenamiento),
versiones ``candidata`` con su booster en Storage, predicciones OOS del
protocolo como cortes pasados e inferencia del corte vigente.
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

from src.db.modelos import Ejecucion, ahora_utc
from src.db.sesion import crear_motor, transaccion
from src.modeling.seguimiento_mlflow import registrar_reporte
from src.modeling.train import PARAMETROS_BASE
from src.serving import parametros
from src.serving.almacenamiento import AlmacenamientoLocal
from src.serving.artefactos import huella_json
from src.serving.cargar_datos import (exigir_esquema, hashes_fuentes, persistir_carga, preparar_carga,
                                      registrar_fallo)
from src.serving.configuracion import configuracion_servicio
from src.serving.inferencia import importar_oos, inferir
from src.serving.modelos import entrenar_versiones_servicio, guardar_versiones, reporte_servicio
from src.serving.protocolo import cargar_protocolo
from src.utils.paths import GOLD, ROOT, SERVING_EJECUCIONES, SILVER_INTEGRADO, SRC


def hashes_codigo():
    """Los cambios de lógica también forman parte de la identidad de la publicación."""
    archivos = [p for nombre in ("serving", "db", "modeling", "validation", "utils")
                for p in (SRC / nombre).rglob("*.py")]
    return {str(p.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in archivos}


def publicacion_existente(sesion, huella):
    for ejecucion in sesion.scalars(select(Ejecucion).where(
            Ejecucion.tipo == "reentrenamiento", Ejecucion.estado == "exitosa").order_by(Ejecucion.id_ejecucion.desc())):
        if (ejecucion.detalle or {}).get("huella") == huella:
            return ejecucion
    return None


def publicar_en_bd(motor, carga, protocolo, preparadas, horizontes, cfg, run_id, huella, almacenamiento, inicio):
    """Versiones, OOS e inferencia vigente en una sola transacción."""
    with transaccion(motor) as sesion:
        ejecucion = Ejecucion(tipo="reentrenamiento", estado="en_curso", detalle={"huella": huella})
        sesion.add(ejecucion)
        sesion.flush()
        versiones = guardar_versiones(sesion, preparadas, run_id, parametros.criterios_aceptacion(sesion), almacenamiento)
        oos = importar_oos(sesion, protocolo, horizontes, cfg, versiones)
        vigentes = [inferir(sesion, h, almacenamiento=almacenamiento,
                            servir_no_validadas=cfg.servir_no_validadas, origen="publicacion")
                    for h in horizontes]
        resumen = {"mlflow_run_id": run_id, "fecha_corte_datos": str(carga.fecha_corte_datos),
                   "versiones": [{"codigo": v.codigo, "tarea": v.tarea, "horizonte": v.horizonte,
                                  "cumple_umbrales": v.cumple_umbrales, "estado": v.estado,
                                  "ruta_artefacto": v.ruta_artefacto} for v in versiones.values()],
                   "oos": oos, "inferencias_vigentes": vigentes}
        ejecucion.estado, ejecucion.fin = "exitosa", ahora_utc()
        ejecucion.id_semana_corte = vigentes[0]["id_semana_corte"] if vigentes else None
        ejecucion.detalle = {"huella": huella, "resumen": resumen,
                             "duracion_segundos": round(time.perf_counter() - inicio, 3)}
        sesion.flush()
        return {"id_ejecucion": ejecucion.id_ejecucion, "reutilizada": False, **resumen}


def publicar(motor, horizontes=None, *, cfg=None, almacenamiento=None):
    """Valida, ajusta, registra MLflow y confirma la publicación en la BD."""
    inicio = time.perf_counter()
    cfg = cfg or configuracion_servicio()
    almacenamiento = almacenamiento or AlmacenamientoLocal()
    horizontes = tuple(sorted(horizontes if horizontes is not None else cfg.horizontes))
    if not horizontes or len(set(horizontes)) != len(horizontes):
        raise ValueError("Indique horizontes no repetidos")
    for h in horizontes:
        if h not in (2, 4):
            raise ValueError("No hay gold ni contrato de modelado para horizonte 3; no se inventarán predicciones")
        if not (GOLD / f"{SILVER_INTEGRADO.stem}_h{h}_gold.csv").exists():
            raise ValueError(f"Falta el gold para horizonte {h}")
    exigir_esquema(motor)
    carga = preparar_carga()
    protocolo = cargar_protocolo(horizontes, cfg.variantes)
    hashes = {**carga.hashes, **protocolo.hashes, **hashes_codigo()}
    huella = huella_json({"hashes": hashes, "configuracion": asdict(cfg), "horizontes": horizontes,
                          "parametros": PARAMETROS_BASE, "xgboost": XGBOOST_VERSION,
                          "plataforma": f"{platform.system()} {platform.release()} {platform.machine()}"})
    with transaccion(motor) as sesion:
        persistir_carga(sesion, carga)
        previa = publicacion_existente(sesion, huella)
        if previa is not None:
            return {"id_ejecucion": previa.id_ejecucion, "reutilizada": True, **previa.detalle["resumen"]}
    try:
        preparadas = entrenar_versiones_servicio(protocolo, horizontes, cfg, carga.fecha_corte_datos)
        directorio = SERVING_EJECUCIONES / huella
        directorio.mkdir(parents=True, exist_ok=True)
        reporte = reporte_servicio(preparadas, protocolo, carga.fecha_corte_datos)
        reporte_path = directorio / "reporte_servicio.json"
        reporte_path.write_text(json.dumps(reporte, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        run_id = registrar_reporte("serving", reporte, metricas_path=reporte_path,
            salida_dir=directorio, gold_dir=GOLD, calidad_datos=carga.validacion_gx,
            descripcion="Ajuste de servicio. La evaluación temporal adjunta es importada del protocolo previo, no un entrenamiento OOS de esta corrida.")
        if carga.hashes != hashes_fuentes() or hashes_codigo() != {k: v for k, v in hashes.items() if k.startswith("src/")}:
            raise ValueError("Las entradas o el código cambiaron durante la ejecución; publicación rechazada")
        resumen = publicar_en_bd(motor, carga, protocolo, preparadas, horizontes, cfg, run_id, huella,
                                 almacenamiento, inicio)
        (directorio / "publicacion.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return resumen
    except Exception as error:
        registrar_fallo(motor, "reentrenamiento", error, {"huella": huella})
        raise


def main(argv=None):
    """``python -m src.serving.publicar --horizontes 2 4``."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--horizontes", nargs="+", type=int, choices=(2, 3, 4), default=None,
                        help="Horizontes con gold y contrato disponibles (2 y 4)")
    args = parser.parse_args(argv)
    motor = None
    try:
        motor = crear_motor()
        print(json.dumps(publicar(motor, args.horizontes), ensure_ascii=False, default=str))
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
