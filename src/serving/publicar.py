"""CLI de publicación: fuentes reales → XGBoost → BD, con ejecución auditable."""

import argparse
from dataclasses import asdict
import hashlib
import json
import platform
import sys
import time

import pandas as pd
from sqlalchemy import inspect, select
from sqlalchemy.exc import SQLAlchemyError
from xgboost import __version__ as XGBOOST_VERSION

from src.db.modelos import EjecucionPrediccion
from src.db.sesion import crear_motor, transaccion
from src.modeling.inferencia_futura import construir_filas_futuras
from src.modeling.seguimiento_mlflow import registrar_reporte
from src.modeling.train import PARAMETROS_BASE
from src.modeling.validacion_temporal_compacta import variantes_compactas
from src.serving.artefactos import huella_json
from src.serving.cargar_datos import preparar_carga, persistir_carga, hashes_fuentes
from src.serving.configuracion import configuracion_servicio
from src.serving.modelos import entrenar_versiones_servicio, versiones_historicas, reporte_servicio
from src.serving.protocolo import cargar_protocolo
from src.serving.publicacion import publicar_lote
from src.utils.paths import GOLD, ROOT, SRC, SERVING_EJECUCIONES, SILVER_INTEGRADO


def hashes_codigo():
    """Los cambios de lógica también forman parte de la identidad de ejecución."""
    archivos = [p for nombre in ("serving", "db", "modeling", "validation", "utils")
                for p in (SRC / nombre).rglob("*.py")]
    return {str(p.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in archivos}


def iniciar_ejecucion(sesion, huella, corte, hashes):
    """Reutiliza completadas, permite reintentar fallidas y evita carreras."""
    anterior = sesion.scalar(select(EjecucionPrediccion).where(EjecucionPrediccion.huella == huella).with_for_update())
    if anterior is not None:
        if anterior.estado == "completada":
            return anterior.id, {**anterior.resumen, "reutilizada": True}
        if anterior.estado == "en_proceso":
            raise ValueError("Ya existe una ejecución en proceso con estas entradas; espere a que termine")
        anterior.estado = "en_proceso"
        anterior.motivo = None
        return anterior.id, None
    ejecucion = EjecucionPrediccion(huella=huella, fecha_corte_datos=corte,
        hashes_entrada=hashes, versiones_usadas=[], estado="en_proceso", filas_generadas=0,
        duracion_segundos=0, resumen={})
    sesion.add(ejecucion)
    sesion.flush()
    return ejecucion.id, None


def publicar(motor, horizontes=None, *, cfg=None):
    """Valida, ajusta, registra MLflow y confirma toda la publicación en la BD."""
    inicio = time.perf_counter()
    cfg = cfg or configuracion_servicio()
    horizontes = tuple(sorted(horizontes if horizontes is not None else cfg.horizontes))
    if not horizontes or len(set(horizontes)) != len(horizontes):
        raise ValueError("Indique horizontes no repetidos")
    for h in horizontes:
        if h not in (2, 4):
            raise ValueError("No hay gold ni contrato de modelado para horizonte 3; no se inventarán predicciones")
        if not (GOLD / f"{SILVER_INTEGRADO.stem}_h{h}_gold.csv").exists():
            raise ValueError(f"Falta el gold para horizonte {h}")
    columnas_bd = {c["name"] for c in inspect(motor).get_columns("version_modelo")}
    if not {"huella", "criterios_validacion", "origen"} <= columnas_bd:
        raise ValueError("Aplique alembic upgrade head antes de publicar inferencia")
    carga = preparar_carga()
    protocolo = cargar_protocolo(horizontes, cfg.variantes)
    hashes = {**carga.hashes, **protocolo.hashes, **hashes_codigo()}
    huella = huella_json({"hashes": hashes, "configuracion": asdict(cfg), "horizontes": horizontes,
        "parametros": PARAMETROS_BASE, "xgboost": XGBOOST_VERSION,
        "plataforma": f"{platform.system()} {platform.release()} {platform.machine()}"})
    with transaccion(motor) as sesion:
        persistir_carga(sesion, carga)
        ejecucion_id, reutilizada = iniciar_ejecucion(sesion, huella, carga.fecha_corte_datos, hashes)
    if reutilizada is not None:
        return reutilizada
    try:
        panel = pd.read_csv(SILVER_INTEGRADO, dtype={"ubigeo": "string"}, parse_dates=["semana_inicio"])
        futuros, no_disponibles = {}, []
        for h in horizontes:
            columnas = sorted(set(c for n in cfg.variantes.values() for c in variantes_compactas(h)[n]))
            futuros[h], motivos = construir_filas_futuras(panel, h, columnas=columnas,
                                                        fecha_corte=carga.fecha_corte_datos)
            no_disponibles += motivos
        preparadas = entrenar_versiones_servicio(protocolo, horizontes, cfg, carga.fecha_corte_datos)
        preparadas.update(versiones_historicas(protocolo, horizontes, cfg))
        directorio = SERVING_EJECUCIONES / huella
        directorio.mkdir(parents=True, exist_ok=True)
        reporte = reporte_servicio(preparadas, protocolo, futuros, carga.fecha_corte_datos)
        reporte_path = directorio / "reporte_servicio.json"
        reporte_path.write_text(json.dumps(reporte, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (directorio / "evaluacion_temporal_importada.json").write_bytes(protocolo.metricas_path.read_bytes())
        for (h, tipo, bloque), version in preparadas.items():
            if bloque == "servicio":
                (directorio / f"servicio_h{h}_{tipo}.json").write_text(
                    json.dumps(version.datos["artefacto"], ensure_ascii=False) + "\n", encoding="utf-8")
        for h, filas in futuros.items():
            filas.to_csv(directorio / f"vectores_futuros_h{h}.csv", index=False)
        run_id = registrar_reporte("serving", reporte, metricas_path=reporte_path,
            salida_dir=directorio, gold_dir=GOLD, calidad_datos=carga.validacion_gx,
            descripcion="Ajuste de servicio. La evaluación temporal adjunta es importada del protocolo previo, no un entrenamiento OOS de esta corrida.")
        if carga.hashes != hashes_fuentes() or hashes_codigo() != {k: v for k, v in hashes.items() if k.startswith("src/")}:
            raise ValueError("Las entradas o el código cambiaron durante la ejecución; publicación rechazada")
        for clave, archivo in (("protocolo_metricas", protocolo.metricas_path), ("protocolo_predicciones", protocolo.predicciones_path)):
            if hashes[clave] != hashlib.sha256(archivo.read_bytes()).hexdigest():
                raise ValueError("El protocolo cambió durante la ejecución; publicación rechazada")
        with transaccion(motor) as sesion:
            resumen = publicar_lote(sesion, ejecucion_id, preparadas, futuros, protocolo,
                horizontes, cfg, run_id, no_disponibles, time.perf_counter() - inicio)
        (directorio / "publicacion.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return resumen
    except Exception as error:
        with transaccion(motor) as sesion:
            ejecucion = sesion.get(EjecucionPrediccion, ejecucion_id)
            if ejecucion.estado != "completada":
                ejecucion.estado = "fallida"
                ejecucion.motivo = f"La publicación falló ({type(error).__name__}); no se confirmaron modelos ni predicciones"
                ejecucion.duracion_segundos = time.perf_counter() - inicio
        raise


def main(argv=None):
    """``python -m src.serving.publicar --horizontes 2 4``."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--horizontes", nargs="+", type=int, choices=(2, 3, 4), default=None,
                        help="Horizontes con gold y contrato disponibles")
    args = parser.parse_args(argv)
    motor = None
    try:
        motor = crear_motor()
        print(json.dumps(publicar(motor, args.horizontes), ensure_ascii=False))
        return 0
    except SQLAlchemyError:
        print("No se pudo publicar: revise la conexión, migraciones y permisos de la BD", file=sys.stderr)
    except (ValueError, OSError) as error:
        print(f"Publicación rechazada: {error}", file=sys.stderr)
    except Exception as error:
        print(f"La publicación no terminó ({type(error).__name__}); revise sus artefactos y la ejecución registrada", file=sys.stderr)
    finally:
        if motor is not None:
            motor.dispose()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
