"""Carga transaccional e idempotente del almacén OE2 desde las fuentes del pipeline.

Lee reference, silver integrado (casos y clima), gold h2 (solo ``brote`` y
``umbral_brote_casos``: no se recalculan) y la Sala Situacional (contraste de
2025). Valida GX y el linaje existentes, y escribe solo en la BD: provincia,
distrito, semana_epidemiologica y observacion_semanal, registradas como una
``ejecucion`` de tipo ``ingesta``. No persiste feature engineering.
"""

import argparse
from dataclasses import dataclass, field
from datetime import date, timedelta
import hashlib
import json
import math
import sys

import pandas as pd
from sqlalchemy import inspect, select
from sqlalchemy.exc import SQLAlchemyError

from src.db.configuracion import ConfiguracionBDInvalida
from src.db.modelos import (Distrito, Ejecucion, ObservacionSemanal, Provincia,
                            SemanaEpidemiologica, ahora_utc)
from src.db.sesion import crear_motor, transaccion, upsert
from src.processing.agregacion_semanal import limpiar_nombres_para_cruce
from src.utils.calendario import semana_epi_mmwr
from src.utils.keys import normalizar
from src.utils.paths import (DISTRITOS_COORDS, GOLD, GOLD_MANIFEST, ROOT, SILVER_EPI_HISTORICO,
                             SILVER_INTEGRADO, SILVER_SALA, UBIGEO_CATALOG)

TRANSFORMACION = 2  # versión de esta transformación; forma parte de la huella de ingesta
SEMANA_INICIO_TEMPORADA = 35  # misma regla que el modelado (src/modeling/train.py)
COBERTURA = {"verified": "verificado", "missing": "sin_registro", "no_record": "sin_registro"}
CLIMA = {"temp_media": "temp_media_c", "temp_min": "temp_min_c", "temp_max": "temp_max_c",
         "precip_total_mm": "precip_total_mm", "hum_rel_media": "hum_rel_media_pct"}


@dataclass(frozen=True)
class DatosCarga:
    """Registros preparados y evidencia de validación que acompañan la carga."""
    provincias: list[dict]
    distritos: list[dict]
    semanas: list[dict]
    observaciones: list[dict]
    hashes: dict
    validacion_gx: dict
    fecha_corte_datos: date
    seleccion_experimental: dict = field(default_factory=dict)


def hashes_fuentes():
    """Huella de todas las entradas utilizadas, sin guardar credenciales."""
    fuentes = [UBIGEO_CATALOG, DISTRITOS_COORDS, SILVER_INTEGRADO,
               SILVER_INTEGRADO.with_suffix(".coverage.csv"), SILVER_EPI_HISTORICO,
               SILVER_SALA, GOLD_MANIFEST]
    fuentes += [GOLD / f"{SILVER_INTEGRADO.stem}_h{h}_gold.csv" for h in (2, 4)]
    return {str(p.relative_to(ROOT)).replace("\\", "/"):
            hashlib.sha256(p.read_bytes()).hexdigest() for p in fuentes}


def preparar_distritos(catalogo, coordenadas, poblacion_2017):
    """Relaciona centroides con UBIGEO mediante el cruce ya usado en silver."""
    if catalogo.ubigeo.duplicated().any() or not catalogo.ubigeo.str.fullmatch(r"[0-9]{6}").all():
        raise ValueError("El catálogo debe contener UBIGEO únicos de seis dígitos")
    cat = limpiar_nombres_para_cruce(catalogo)
    coords = limpiar_nombres_para_cruce(coordenadas)
    for datos in (cat, coords):
        datos["provincia_key"] = datos.provincia.map(normalizar)
        # GADM conserva nombres concatenados: se cruza sin espacios y se exige unicidad.
        datos["distrito_key"] = datos.distrito_key.str.replace(" ", "", regex=False)
    cruce = cat.merge(coords[["provincia_key", "distrito_key", "lat", "lon"]],
                      on=["provincia_key", "distrito_key"], how="outer",
                      validate="one_to_one", indicator=True)
    if not cruce._merge.eq("both").all():
        raise ValueError("El catálogo y los centroides no contienen los mismos distritos")
    provincias, distritos = {}, []
    for fila in cruce.itertuples():
        if not (math.isfinite(fila.lat) and math.isfinite(fila.lon)
                and -6.5 <= fila.lat <= -3.5 and -81.5 <= fila.lon <= -79.0):
            raise ValueError(f"Centroide fuera de Piura para {fila.ubigeo}")
        codigo = fila.ubigeo[:4]
        if provincias.setdefault(codigo, fila.provincia) != fila.provincia:
            raise ValueError(f"La provincia {codigo} tiene nombres distintos en el catálogo")
        poblacion = poblacion_2017.get(fila.ubigeo)
        distritos.append({"ubigeo": fila.ubigeo, "ubigeo_provincia": codigo, "nombre": fila.distrito,
                          "latitud": round(float(fila.lat), 6), "longitud": round(float(fila.lon), 6),
                          "poblacion_censo_2017": None if poblacion is None else int(poblacion),
                          "activo": True})
    return ([{"ubigeo_provincia": c, "nombre": n} for c, n in sorted(provincias.items())],
            sorted(distritos, key=lambda r: r["ubigeo"]))


def poblacion_censo_2017(silver):
    """Población 2017 del integrado (pob_censada_2017 del INEI); constante por distrito."""
    filas = silver.loc[silver.anio.eq(2017), ["ubigeo", "poblacion"]]
    if filas.groupby("ubigeo").poblacion.nunique().gt(1).any():
        raise ValueError("La población de 2017 no es constante dentro del año")
    poblacion = filas.drop_duplicates("ubigeo").set_index("ubigeo").poblacion
    if not poblacion.gt(0).all():
        raise ValueError("La población censal 2017 debe ser positiva")
    return poblacion.to_dict()


def semana_id(anio, semana):
    return int(anio) * 100 + int(semana)


def preparar_semanas(desde, hasta):
    """Calendario MMWR completo (incluye semana 53) entre dos domingos."""
    domingos = pd.Series(pd.date_range(desde, hasta, freq="7D"))
    if not domingos.dt.weekday.eq(6).all():
        raise ValueError("El calendario debe empezar en domingo")
    cal = semana_epi_mmwr(domingos)
    return [{"id_semana": semana_id(a, s), "anio": int(a), "semana": int(s),
             "fecha_inicio": d.date(), "fecha_fin": (d + timedelta(days=6)).date(),
             "temporada": int(a) + int(s >= SEMANA_INICIO_TEMPORADA)}
            for d, a, s in zip(domingos, cal.anio_epi, cal.semana_epi)]


def _opcional(valor, decimales=2):
    return None if pd.isna(valor) else round(float(valor), decimales)


def preparar_observaciones(silver, cobertura, gold, sala):
    """Casos y clima de silver; brote y umbral copiados de gold; 2025 contrastado con la Sala."""
    claves = ["ubigeo", "anio", "semana"]
    for nombre, datos in (("silver", silver), ("gold", gold), ("cobertura", cobertura)):
        if datos.empty or datos.duplicated(claves).any():
            raise ValueError(f"{nombre} debe contener semanas distritales únicas")
        if not datos.ubigeo.str.fullmatch(r"[0-9]{6}").all():
            raise ValueError(f"{nombre} debe conservar ubigeo como texto de seis dígitos")
    calendario = semana_epi_mmwr(silver.semana_inicio)
    if not (calendario.anio_epi.eq(silver.anio).all() and calendario.semana_epi.eq(silver.semana).all()):
        raise ValueError("El año/semana de silver no coincide con el calendario MMWR")
    if not silver.anio.between(2017, 2025).all():
        raise ValueError("La procedencia posterior a 2025 requiere una revisión explícita")
    datos = silver.merge(gold[claves + ["casos_Dengue", "brote", "umbral_brote_casos"]], on=claves,
                         how="left", validate="one_to_one", suffixes=("", "_gold"), indicator=True)
    if not datos._merge.eq("both").all():
        raise ValueError("Gold no contiene la etiqueta de todas las semanas de silver")
    iguales = datos.casos_Dengue.eq(datos.casos_Dengue_gold) | (datos.casos_Dengue.isna() & datos.casos_Dengue_gold.isna())
    if not iguales.all():
        raise ValueError("Los casos de silver y gold no coinciden")
    datos = datos.drop(columns="_merge").merge(cobertura[claves + ["source"]], on=claves, how="left",
                                               validate="one_to_one", indicator=True)
    if not datos._merge.eq("both").all():
        raise ValueError("Falta la cobertura de algunas semanas")
    comparacion = datos.loc[datos.anio.eq(2025), claves + ["casos_Dengue"]].merge(
        sala[claves + ["casos_Dengue"]], on=claves, how="left", validate="one_to_one",
        suffixes=("", "_sala"), indicator=True)
    if not (comparacion._merge.eq("both").all() and comparacion.casos_Dengue.eq(comparacion.casos_Dengue_sala).all()):
        raise ValueError("Los casos de 2025 no coinciden con la Sala Situacional")
    corte = datos.semana_inicio.max().date() + timedelta(days=6)
    resultado = []
    for fila in datos.itertuples():
        casos = None if pd.isna(fila.casos_Dengue) else float(fila.casos_Dengue)
        if casos is not None and (not math.isfinite(casos) or casos < 0 or not casos.is_integer()):
            raise ValueError(f"Conteo de casos inválido en {fila.ubigeo}/{fila.anio}/{fila.semana}")
        if pd.isna(fila.brote) or fila.brote not in (0, 1):
            raise ValueError("La etiqueta brote debe provenir de gold y valer 0 o 1")
        if not math.isfinite(float(fila.umbral_brote_casos)) or fila.umbral_brote_casos < 0:
            raise ValueError("El umbral de brote de gold debe ser finito y no negativo")
        registro = {"ubigeo": fila.ubigeo, "id_semana": semana_id(fila.anio, fila.semana),
                    "casos_dengue": None if casos is None else int(casos), "brote": bool(fila.brote),
                    "umbral_brote_casos": round(float(fila.umbral_brote_casos), 2),
                    "fuente_casos": "sala_situacional" if fila.anio == 2025 else "excel_historico",
                    "estado_cobertura": COBERTURA.get(fila.source, "pendiente")}
        registro.update({destino: _opcional(getattr(fila, origen)) for origen, destino in CLIMA.items()})
        resultado.append(registro)
    return resultado, corte


def preparar_desde_tablas(catalogo, coordenadas, silver, cobertura, gold, sala, hashes, validacion_gx,
                          seleccion_experimental=None):
    """Arma el lote completo; separado de la lectura de archivos para probarlo con fixtures."""
    provincias, distritos = preparar_distritos(catalogo, coordenadas, poblacion_censo_2017(silver))
    observaciones, corte = preparar_observaciones(silver, cobertura, gold, sala)
    conocidos = {d["ubigeo"] for d in distritos}
    if not {o["ubigeo"] for o in observaciones} <= conocidos:
        raise ValueError("Hay observaciones de distritos fuera del catálogo")
    # El calendario cubre la historia y un año de objetivos futuros de inferencia.
    semanas = preparar_semanas(date(2017, 1, 1), pd.Timestamp(corte) + pd.Timedelta(days=371))
    return DatosCarga(provincias, distritos, semanas, observaciones, hashes, validacion_gx, corte,
                      seleccion_experimental or {})


def leer_silver(ruta=SILVER_INTEGRADO):
    return pd.read_csv(ruta, dtype={"ubigeo": "string"}, parse_dates=["semana_inicio"])


def preparar_carga():
    """Valida archivos originales antes de preparar cualquier escritura."""
    from src.modeling.contrato_xgboost import auditar_traspaso
    from src.processing.epi_sala import load_ubigeo_catalog
    from src.serving.configuracion import configuracion_servicio
    from src.validation.calidad_gx import leer_gold, validar_entradas_modelado

    hashes = hashes_fuentes()
    auditar_traspaso()
    calidad = validar_entradas_modelado(gold_dir=GOLD, silver_path=SILVER_INTEGRADO)
    gold, _ = leer_gold(GOLD, 2)
    datos = preparar_desde_tablas(
        load_ubigeo_catalog(UBIGEO_CATALOG), pd.read_csv(DISTRITOS_COORDS), leer_silver(),
        pd.read_csv(SILVER_INTEGRADO.with_suffix(".coverage.csv"), dtype={"ubigeo": "string"}),
        gold, pd.read_csv(SILVER_SALA, dtype={"ubigeo": "string"}), hashes, calidad,
        configuracion_servicio().seleccion_experimental)
    if hashes != hashes_fuentes():
        raise ValueError("Las fuentes cambiaron durante la validación; vuelva a ejecutar la carga")
    return datos


def huella_carga(datos):
    return hashlib.sha256(json.dumps({"transformacion": TRANSFORMACION, "hashes": datos.hashes},
                                     sort_keys=True).encode("utf-8")).hexdigest()


def ingesta_existente(sesion, huella):
    """Búsqueda portable por detalle->>'huella' (en PostgreSQL la respalda un índice único)."""
    for ejecucion in sesion.scalars(select(Ejecucion).where(
            Ejecucion.tipo == "ingesta", Ejecucion.estado == "exitosa").order_by(Ejecucion.id_ejecucion.desc())):
        if (ejecucion.detalle or {}).get("huella") == huella:
            return ejecucion
    return None


def persistir_carga(sesion, datos):
    """Inserta/actualiza el lote en la transacción del llamador, sin duplicarlo."""
    from src.serving.parametros import sembrar_seleccion_experimental

    if not datos.validacion_gx.get("exito"):
        raise ValueError("No se permite cargar entradas que no aprobaron GX")
    huella = huella_carga(datos)
    previa = ingesta_existente(sesion, huella)
    if previa is not None:
        return {**previa.detalle["resumen"], "id_ejecucion": previa.id_ejecucion, "reutilizada": True}
    ejecucion = Ejecucion(tipo="ingesta", estado="en_curso", detalle={"huella": huella})
    sesion.add(ejecucion)
    sesion.flush()
    instante = ahora_utc()
    upsert(sesion, Provincia.__table__, datos.provincias, ["ubigeo_provincia"])
    upsert(sesion, Distrito.__table__, datos.distritos, ["ubigeo"])
    upsert(sesion, SemanaEpidemiologica.__table__, datos.semanas, ["id_semana"])
    upsert(sesion, ObservacionSemanal.__table__,
           [{**o, "fecha_extraccion": instante, "id_ejecucion": ejecucion.id_ejecucion} for o in datos.observaciones],
           ["ubigeo", "id_semana"])
    if datos.seleccion_experimental:
        sembrar_seleccion_experimental(sesion, datos.seleccion_experimental)
    ultima = max(o["id_semana"] for o in datos.observaciones)
    resumen = {"provincias": len(datos.provincias), "distritos": len(datos.distritos),
               "semanas_calendario": len(datos.semanas), "observaciones": len(datos.observaciones),
               "fecha_corte_datos": str(datos.fecha_corte_datos), "id_semana_corte": ultima}
    ejecucion.estado = "exitosa"
    ejecucion.id_semana_corte = ultima
    ejecucion.fin = ahora_utc()
    ejecucion.detalle = {"huella": huella, "hashes_entrada": datos.hashes,
                         "validacion_gx": datos.validacion_gx, "resumen": resumen,
                         "fecha_extraccion": instante.isoformat()}
    sesion.flush()
    return {**resumen, "id_ejecucion": ejecucion.id_ejecucion, "reutilizada": False}


def registrar_fallo(motor, tipo, error, detalle=None):
    """Deja constancia de una ejecución fallida en su propia transacción."""
    with transaccion(motor) as sesion:
        sesion.add(Ejecucion(tipo=tipo, estado="fallida", fin=ahora_utc(), detalle=detalle or {},
                             mensaje_error=f"{type(error).__name__}: {error}"[:2000]))


def exigir_esquema(motor):
    tablas = set(inspect(motor).get_table_names())
    if not {"ejecucion", "observacion_semanal", "parametro_sistema", "semana_epidemiologica"} <= tablas:
        raise ValueError("Faltan tablas del esquema OE2: ejecute alembic upgrade head antes de cargar")


def cargar_datos(motor):
    """Exige una BD migrada y publica toda la carga en una sola transacción."""
    exigir_esquema(motor)
    datos = preparar_carga()
    try:
        with transaccion(motor) as sesion:
            return persistir_carga(sesion, datos)
    except (SQLAlchemyError, ValueError) as error:
        registrar_fallo(motor, "ingesta", error, {"huella": huella_carga(datos)})
        raise


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
