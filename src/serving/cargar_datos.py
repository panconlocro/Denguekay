"""Carga transaccional e idempotente del catálogo y de las observaciones.

Lee gold/silver/reference, valida GX y el linaje existentes y escribe solo
en la BD. Las etiquetas se copian de gold; no se recalculan ni se imputan.
"""

import argparse
from dataclasses import dataclass
from datetime import date, timedelta
import hashlib
import json
import math
import sys

import pandas as pd
from sqlalchemy import inspect, select
from sqlalchemy.exc import SQLAlchemyError

from src.db.configuracion import ConfiguracionBDInvalida
from src.db.modelos import CargaDatos, Distrito, ObservacionSemanal, ahora_utc
from src.db.sesion import crear_motor, transaccion
from src.modeling.contrato_xgboost import auditar_traspaso
from src.processing.agregacion_semanal import limpiar_nombres_para_cruce
from src.processing.epi_sala import load_ubigeo_catalog
from src.utils.calendario import semana_epi_mmwr
from src.utils.keys import normalizar
from src.utils.paths import (DISTRITOS_COORDS, GOLD, GOLD_MANIFEST, ROOT,
                             SILVER_EPI_HISTORICO, SILVER_INTEGRADO, SILVER_SALA,
                             UBIGEO_CATALOG)
from src.validation.calidad_gx import leer_gold, validar_entradas_modelado


@dataclass(frozen=True)
class DatosCarga:
    """Registros preparados y evidencia de validación que acompañan la carga."""
    distritos: list[dict]
    observaciones: list[dict]
    hashes: dict
    validacion_gx: dict
    fecha_corte_datos: date


def hashes_fuentes():
    """Huella de todas las entradas utilizadas, sin guardar credenciales."""
    fuentes = [UBIGEO_CATALOG, DISTRITOS_COORDS, SILVER_INTEGRADO,
               SILVER_INTEGRADO.with_suffix(".coverage.csv"), SILVER_EPI_HISTORICO,
               SILVER_SALA, GOLD_MANIFEST]
    fuentes += [GOLD / f"{SILVER_INTEGRADO.stem}_h{h}_gold.csv" for h in (2, 4)]
    return {str(p.relative_to(ROOT)).replace("\\", "/"):
            hashlib.sha256(p.read_bytes()).hexdigest() for p in fuentes}


def preparar_distritos(catalogo, coordenadas):
    """Relaciona centroides con UBIGEO mediante el cruce ya usado en silver."""
    if catalogo.ubigeo.duplicated().any() or not catalogo.ubigeo.str.fullmatch(r"[0-9]{6}").all():
        raise ValueError("El catálogo debe contener UBIGEO únicos de seis dígitos")
    cat = limpiar_nombres_para_cruce(catalogo)
    coords = limpiar_nombres_para_cruce(coordenadas)
    for datos in (cat, coords):
        datos["provincia_key"] = datos.provincia.map(normalizar)
        # GADM conserva nombres concatenados: se cruza sin espacios y se
        # exige unicidad; no se cambia el nombre ni el archivo de referencia.
        datos["distrito_key"] = datos.distrito_key.str.replace(" ", "", regex=False)
    cruce = cat.merge(coords[["provincia_key", "distrito_key", "lat", "lon"]],
                      on=["provincia_key", "distrito_key"], how="outer",
                      validate="one_to_one", indicator=True)
    if not cruce._merge.eq("both").all():
        raise ValueError("El catálogo y los centroides no contienen los mismos distritos")
    resultado = []
    for fila in cruce.itertuples():
        if not (math.isfinite(fila.lat) and math.isfinite(fila.lon)
                and -90 <= fila.lat <= 90 and -180 <= fila.lon <= 180):
            raise ValueError(f"Centroide inválido para {fila.ubigeo}")
        resultado.append({"ubigeo": fila.ubigeo, "nombre": fila.distrito,
                          "provincia": fila.provincia, "lat": float(fila.lat), "lon": float(fila.lon),
                          "geometria": None,
                          "motivo_geometria": "La referencia disponible contiene centroides, sin polígonos"})
    return sorted(resultado, key=lambda r: r["ubigeo"])


def preparar_observaciones(gold, sala):
    """Copia casos/etiquetas y comprueba la procedencia de cada semana 2025."""
    claves = ["ubigeo", "anio", "semana"]
    if gold.empty or gold.duplicated(claves).any():
        raise ValueError("Gold debe contener observaciones únicas y no estar vacío")
    if not gold.ubigeo.str.fullmatch(r"[0-9]{6}").all():
        raise ValueError("Gold debe conservar ubigeo como texto de seis dígitos")
    calendario = semana_epi_mmwr(gold.semana_inicio)
    if not (calendario.anio_epi.eq(gold.anio).all() and calendario.semana_epi.eq(gold.semana).all()):
        raise ValueError("El año/semana de gold no coincide con el calendario MMWR")
    if not gold.anio.between(2017, 2025).all():
        raise ValueError("La procedencia posterior a 2025 requiere una revisión explícita")
    if sala.duplicated(claves).any():
        raise ValueError("La Sala contiene semanas distritales duplicadas")
    comparacion = gold.loc[gold.anio.eq(2025), claves + ["casos_Dengue"]].merge(
        sala[claves + ["casos_Dengue"]], on=claves, how="left", validate="one_to_one",
        suffixes=("_gold", "_sala"), indicator=True)
    if not (comparacion._merge.eq("both").all()
            and comparacion.casos_Dengue_gold.eq(comparacion.casos_Dengue_sala).all()):
        raise ValueError("Los casos de gold 2025 no coinciden con la Sala Situacional")
    corte = gold.semana_inicio.max().date() + timedelta(days=6)
    resultado = []
    for fila in gold.itertuples():
        casos = None if pd.isna(fila.casos_Dengue) else float(fila.casos_Dengue)
        if casos is not None and (not math.isfinite(casos) or casos < 0 or not casos.is_integer()):
            raise ValueError(f"Conteo de casos inválido en {fila.ubigeo}/{fila.anio}/{fila.semana}")
        if pd.isna(fila.brote) or fila.brote not in (0, 1):
            raise ValueError("La etiqueta brote debe provenir de gold y valer 0 o 1")
        if not math.isfinite(float(fila.umbral_brote_casos)) or fila.umbral_brote_casos < 0:
            raise ValueError("El umbral de brote de gold debe ser finito y no negativo")
        resultado.append({"ubigeo": fila.ubigeo, "anio": int(fila.anio), "semana": int(fila.semana),
                          "semana_inicio": fila.semana_inicio.date(),
                          "casos": None if casos is None else int(casos),
                          "brote": bool(fila.brote), "umbral_brote_casos": float(fila.umbral_brote_casos),
                          "procedencia": "Sala Situacional MINSA 2025" if fila.anio == 2025 else "Excel histórico MINSA",
                          "motivo": "No hay observación de casos en la fuente" if casos is None else None,
                          "fecha_corte_datos": corte})
    return resultado, corte


def preparar_carga():
    """Valida archivos originales antes de preparar cualquier escritura."""
    hashes = hashes_fuentes()
    auditar_traspaso()
    calidad = validar_entradas_modelado(gold_dir=GOLD, silver_path=SILVER_INTEGRADO)
    catalogo = load_ubigeo_catalog(UBIGEO_CATALOG)
    coords = pd.read_csv(DISTRITOS_COORDS)
    distritos = preparar_distritos(catalogo, coords)
    gold, _ = leer_gold(GOLD, 2)
    panel = pd.read_csv(SILVER_INTEGRADO, dtype={"ubigeo": "string"})
    geografia = panel[["ubigeo", "lat", "lon"]].drop_duplicates().set_index("ubigeo")
    if geografia.index.has_duplicates:
        raise ValueError("El integrado contiene centroides distintos para un mismo UBIGEO")
    for distrito in distritos:
        centroide = geografia.loc[distrito["ubigeo"]]
        if not all(math.isclose(distrito[c], centroide[c], abs_tol=1e-8) for c in ("lat", "lon")):
            raise ValueError("Los centroides de referencia no coinciden con la geografía auditada de silver")
    sala = pd.read_csv(SILVER_SALA, dtype={"ubigeo": "string"})
    observaciones, corte = preparar_observaciones(gold, sala)
    if hashes != hashes_fuentes():
        raise ValueError("Las fuentes cambiaron durante la validación; vuelva a ejecutar la carga")
    return DatosCarga(distritos, observaciones, hashes, calidad, corte)


def persistir_carga(sesion, datos):
    """Inserta/actualiza el lote en la transacción del llamador, sin duplicarlo."""
    if not datos.validacion_gx.get("exito"):
        raise ValueError("No se permite cargar entradas que no aprobaron GX")
    huella = hashlib.sha256(json.dumps({"transformacion": 1, "hashes": datos.hashes},
                                      sort_keys=True).encode("utf-8")).hexdigest()
    carga = sesion.scalar(select(CargaDatos).where(CargaDatos.huella == huella))
    if carga is not None:
        return {"carga_id": carga.id, "reutilizada": True, "distritos": carga.filas_distritos,
                "observaciones": carga.filas_observaciones, "fecha_corte_datos": str(carga.fecha_corte_datos)}
    carga = CargaDatos(huella=huella, hashes_entrada=datos.hashes,
                      validacion_gx=datos.validacion_gx, fecha_corte_datos=datos.fecha_corte_datos,
                      filas_distritos=len(datos.distritos), filas_observaciones=len(datos.observaciones))
    sesion.add(carga)
    sesion.flush()
    existentes = {r.ubigeo: r for r in sesion.scalars(select(Distrito))}
    for registro in datos.distritos:
        distrito = existentes.get(registro["ubigeo"])
        if distrito is None:
            sesion.add(Distrito(**registro))
        elif any(getattr(distrito, k) != v for k, v in registro.items()):
            for clave, valor in registro.items():
                setattr(distrito, clave, valor)
            distrito.fecha_actualizacion = ahora_utc()
    sesion.flush()
    existentes = {(r.ubigeo, r.anio, r.semana): r for r in sesion.scalars(select(ObservacionSemanal))}
    nuevas = []
    for registro in datos.observaciones:
        observacion = existentes.get((registro["ubigeo"], registro["anio"], registro["semana"]))
        if observacion is None:
            nuevas.append({**registro, "carga_id": carga.id})
        elif any(getattr(observacion, k) != v for k, v in registro.items()):
            for clave, valor in registro.items():
                setattr(observacion, clave, valor)
            observacion.carga_id = carga.id
            observacion.fecha_actualizacion = ahora_utc()
    if nuevas:
        sesion.execute(ObservacionSemanal.__table__.insert(), nuevas)
    sesion.flush()
    return {"carga_id": carga.id, "reutilizada": False, "distritos": len(datos.distritos),
            "observaciones": len(datos.observaciones), "fecha_corte_datos": str(datos.fecha_corte_datos)}


def cargar_datos(motor):
    """Exige una BD migrada y publica toda la carga en una sola transacción."""
    if not {"distrito", "observacion_semanal", "carga_datos"} <= set(inspect(motor).get_table_names()):
        raise ValueError("Faltan tablas: ejecute alembic upgrade head antes de cargar")
    datos = preparar_carga()
    with transaccion(motor) as sesion:
        return persistir_carga(sesion, datos)


def main(argv=None):
    """CLI sin credenciales en argumentos ni en salidas de error."""
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    motor = None
    try:
        motor = crear_motor()
        print(json.dumps(cargar_datos(motor), ensure_ascii=False))
        return 0
    except SQLAlchemyError:
        print("No se pudo completar la carga en la BD; revise conexión, migraciones y permisos", file=sys.stderr)
        return 1
    except (ConfiguracionBDInvalida, ValueError, OSError) as error:
        print(f"Carga rechazada: {error}", file=sys.stderr)
        return 1
    finally:
        if motor is not None:
            motor.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
