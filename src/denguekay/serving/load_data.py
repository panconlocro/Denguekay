"""Transactional, idempotent load of the OE2 store from the pipeline sources.

It reads reference, integrated silver (cases and climate), gold h2 (only ``brote``
and ``umbral_brote_casos``: they are not recomputed) and the Sala Situacional
(2025 cross-check). It validates the existing GX and lineage, and writes only to
the database: provincia, distrito, semana_epidemiologica and observacion_semanal,
recorded as an ``ejecucion`` of type ``ingesta``. It persists no feature engineering.
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

from denguekay.db.settings import InvalidDatabaseSettings
from denguekay.db.models import (District, Run, WeeklyObservation, Province,
                            EpiWeek, utc_now)
from denguekay.db.session import make_engine, transaction, upsert
from denguekay.data.processing.weekly_aggregation import clean_names_for_join
from denguekay.data.calendar import mmwr_epi_week
from denguekay.data.keys import normalize
from denguekay.config.paths import (DISTRICT_COORDS, GOLD, GOLD_MANIFEST, ROOT, SILVER_EPI_HISTORICAL,
                             SILVER_INTEGRATED, SILVER_SALA, UBIGEO_CATALOG)

# Version of this transformation; part of the ingestion fingerprint. 3: humidity is no longer rounded (M5).
TRANSFORMATION = 3
SEASON_START_WEEK = 35  # same rule as the modelling (src/denguekay/model/train.py)
COVERAGE = {"verified": "verificado", "missing": "sin_registro", "no_record": "sin_registro"}
CLIMATE = {"temp_media": "temp_media_c", "temp_min": "temp_min_c", "temp_max": "temp_max_c",
         "precip_total_mm": "precip_total_mm", "hum_rel_media": "hum_rel_media_pct"}
# Decimals kept per climate column (numeric(5,2) / numeric(7,2) of the DDL); None = full value
# (hum_rel_media_pct is double precision since 0005_v1, so A3 matches gold, decision M5).
CLIMATE_DECIMALS = {"temp_media_c": 2, "temp_min_c": 2, "temp_max_c": 2, "precip_total_mm": 2,
                    "hum_rel_media_pct": None}


@dataclass(frozen=True)
class LoadBatch:
    """Prepared records and the validation evidence that come with the load."""
    provincias: list[dict]
    distritos: list[dict]
    semanas: list[dict]
    observaciones: list[dict]
    hashes: dict
    validacion_gx: dict
    fecha_corte_datos: date


def source_hashes():
    """Fingerprint of every input used, without storing credentials."""
    sources = [UBIGEO_CATALOG, DISTRICT_COORDS, SILVER_INTEGRATED,
               SILVER_INTEGRATED.with_suffix(".coverage.csv"), SILVER_EPI_HISTORICAL,
               SILVER_SALA, GOLD_MANIFEST]
    sources += [GOLD / f"{SILVER_INTEGRATED.stem}_h{h}_gold.csv" for h in (2, 4)]
    return {str(p.relative_to(ROOT)).replace("\\", "/"):
            hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}


def prepare_districts(catalog, coordinates, population_2017):
    """Relate centroids to UBIGEO with the join already used in silver."""
    if catalog.ubigeo.duplicated().any() or not catalog.ubigeo.str.fullmatch(r"[0-9]{6}").all():
        raise ValueError("El catálogo debe contener UBIGEO únicos de seis dígitos")
    cat = clean_names_for_join(catalog)
    coords = clean_names_for_join(coordinates)
    for data in (cat, coords):
        data["provincia_key"] = data.provincia.map(normalize)
        # GADM keeps concatenated names: the join is done without spaces and uniqueness is required.
        data["distrito_key"] = data.distrito_key.str.replace(" ", "", regex=False)
    join = cat.merge(coords[["provincia_key", "distrito_key", "lat", "lon"]],
                      on=["provincia_key", "distrito_key"], how="outer",
                      validate="one_to_one", indicator=True)
    if not join._merge.eq("both").all():
        raise ValueError("El catálogo y los centroides no contienen los mismos distritos")
    provinces, districts = {}, []
    for row in join.itertuples():
        if not (math.isfinite(row.lat) and math.isfinite(row.lon)
                and -6.5 <= row.lat <= -3.5 and -81.5 <= row.lon <= -79.0):
            raise ValueError(f"Centroide fuera de Piura para {row.ubigeo}")
        code = row.ubigeo[:4]
        if provinces.setdefault(code, row.provincia) != row.provincia:
            raise ValueError(f"La provincia {code} tiene nombres distintos en el catálogo")
        population = population_2017.get(row.ubigeo)
        districts.append({"ubigeo": row.ubigeo, "ubigeo_provincia": code, "nombre": row.distrito,
                          "latitud": round(float(row.lat), 6), "longitud": round(float(row.lon), 6),
                          "poblacion_censo_2017": None if population is None else int(population),
                          "activo": True})
    return ([{"ubigeo_provincia": c, "nombre": n} for c, n in sorted(provinces.items())],
            sorted(districts, key=lambda r: r["ubigeo"]))


def census_population_2017(silver):
    """2017 population of the integrated dataset (INEI pob_censada_2017); constant per district."""
    rows = silver.loc[silver.anio.eq(2017), ["ubigeo", "poblacion"]]
    if rows.groupby("ubigeo").poblacion.nunique().gt(1).any():
        raise ValueError("La población de 2017 no es constante dentro del año")
    population = rows.drop_duplicates("ubigeo").set_index("ubigeo").poblacion
    if not population.gt(0).all():
        raise ValueError("La población censal 2017 debe ser positiva")
    return population.to_dict()


def week_id(year, week):
    return int(year) * 100 + int(week)


def prepare_weeks(start, end):
    """Full MMWR calendar (week 53 included) between two Sundays."""
    sundays = pd.Series(pd.date_range(start, end, freq="7D"))
    if not sundays.dt.weekday.eq(6).all():
        raise ValueError("El calendario debe empezar en domingo")
    cal = mmwr_epi_week(sundays)
    return [{"id_semana": week_id(a, s), "anio": int(a), "semana": int(s),
             "fecha_inicio": d.date(), "fecha_fin": (d + timedelta(days=6)).date(),
             "temporada": int(a) + int(s >= SEASON_START_WEEK)}
            for d, a, s in zip(sundays, cal.anio_epi, cal.semana_epi)]


def _optional(value, decimals=2):
    if pd.isna(value):
        return None
    return float(value) if decimals is None else round(float(value), decimals)


def prepare_observations(silver, coverage, gold, sala):
    """Silver cases and climate; brote and threshold copied from gold; 2025 cross-checked with the Sala."""
    keys = ["ubigeo", "anio", "semana"]
    for name, data in (("silver", silver), ("gold", gold), ("cobertura", coverage)):
        if data.empty or data.duplicated(keys).any():
            raise ValueError(f"{name} debe contener semanas distritales únicas")
        if not data.ubigeo.str.fullmatch(r"[0-9]{6}").all():
            raise ValueError(f"{name} debe conservar ubigeo como texto de seis dígitos")
    calendar = mmwr_epi_week(silver.semana_inicio)
    if not (calendar.anio_epi.eq(silver.anio).all() and calendar.semana_epi.eq(silver.semana).all()):
        raise ValueError("El año/semana de silver no coincide con el calendario MMWR")
    if not silver.anio.between(2017, 2025).all():
        raise ValueError("La procedencia posterior a 2025 requiere una revisión explícita")
    data = silver.merge(gold[keys + ["casos_Dengue", "brote", "umbral_brote_casos"]], on=keys,
                         how="left", validate="one_to_one", suffixes=("", "_gold"), indicator=True)
    if not data._merge.eq("both").all():
        raise ValueError("Gold no contiene la etiqueta de todas las semanas de silver")
    equal = data.casos_Dengue.eq(data.casos_Dengue_gold) | (data.casos_Dengue.isna() & data.casos_Dengue_gold.isna())
    if not equal.all():
        raise ValueError("Los casos de silver y gold no coinciden")
    data = data.drop(columns="_merge").merge(coverage[keys + ["source"]], on=keys, how="left",
                                               validate="one_to_one", indicator=True)
    if not data._merge.eq("both").all():
        raise ValueError("Falta la cobertura de algunas semanas")
    comparison = data.loc[data.anio.eq(2025), keys + ["casos_Dengue"]].merge(
        sala[keys + ["casos_Dengue"]], on=keys, how="left", validate="one_to_one",
        suffixes=("", "_sala"), indicator=True)
    if not (comparison._merge.eq("both").all() and comparison.casos_Dengue.eq(comparison.casos_Dengue_sala).all()):
        raise ValueError("Los casos de 2025 no coinciden con la Sala Situacional")
    cutoff = data.semana_inicio.max().date() + timedelta(days=6)
    result = []
    for row in data.itertuples():
        cases = None if pd.isna(row.casos_Dengue) else float(row.casos_Dengue)
        if cases is not None and (not math.isfinite(cases) or cases < 0 or not cases.is_integer()):
            raise ValueError(f"Conteo de casos inválido en {row.ubigeo}/{row.anio}/{row.semana}")
        if pd.isna(row.brote) or row.brote not in (0, 1):
            raise ValueError("La etiqueta brote debe provenir de gold y valer 0 o 1")
        if not math.isfinite(float(row.umbral_brote_casos)) or row.umbral_brote_casos < 0:
            raise ValueError("El umbral de brote de gold debe ser finito y no negativo")
        record = {"ubigeo": row.ubigeo, "id_semana": week_id(row.anio, row.semana),
                    "casos_dengue": None if cases is None else int(cases), "brote": bool(row.brote),
                    "umbral_brote_casos": round(float(row.umbral_brote_casos), 2),
                    "fuente_casos": "sala_situacional" if row.anio == 2025 else "excel_historico",
                    "estado_cobertura": COVERAGE.get(row.source, "pendiente")}
        record.update({destination: _optional(getattr(row, origin), CLIMATE_DECIMALS[destination])
                       for origin, destination in CLIMATE.items()})
        result.append(record)
    return result, cutoff


def prepare_from_tables(catalog, coordinates, silver, coverage, gold, sala, hashes, gx_validation):
    """Build the whole batch; kept apart from file reading so it can be tested with fixtures."""
    provinces, districts = prepare_districts(catalog, coordinates, census_population_2017(silver))
    observations, cutoff = prepare_observations(silver, coverage, gold, sala)
    known = {d["ubigeo"] for d in districts}
    if not {o["ubigeo"] for o in observations} <= known:
        raise ValueError("Hay observaciones de distritos fuera del catálogo")
    # The calendar covers the history and one year of future inference targets.
    weeks = prepare_weeks(date(2017, 1, 1), pd.Timestamp(cutoff) + pd.Timedelta(days=371))
    return LoadBatch(provinces, districts, weeks, observations, hashes, gx_validation, cutoff)


def read_silver(path=SILVER_INTEGRATED):
    return pd.read_csv(path, dtype={"ubigeo": "string"}, parse_dates=["semana_inicio"])


def prepare_load():
    """Validate the original files before preparing any write."""
    from denguekay.features.model_input_contract import audit_handoff
    from denguekay.data.processing.epi_sala import load_ubigeo_catalog
    from denguekay.data.validation.gx_quality import read_gold, validate_modeling_inputs

    hashes = source_hashes()
    audit_handoff()
    quality = validate_modeling_inputs(gold_dir=GOLD, silver_path=SILVER_INTEGRATED)
    gold, _ = read_gold(GOLD, 2)
    data = prepare_from_tables(
        load_ubigeo_catalog(UBIGEO_CATALOG), pd.read_csv(DISTRICT_COORDS), read_silver(),
        pd.read_csv(SILVER_INTEGRATED.with_suffix(".coverage.csv"), dtype={"ubigeo": "string"}),
        gold, pd.read_csv(SILVER_SALA, dtype={"ubigeo": "string"}), hashes, quality)
    if hashes != source_hashes():
        raise ValueError("Las fuentes cambiaron durante la validación; vuelva a ejecutar la carga")
    return data


def load_fingerprint(data):
    return hashlib.sha256(json.dumps({"transformacion": TRANSFORMATION, "hashes": data.hashes},
                                     sort_keys=True).encode("utf-8")).hexdigest()


def existing_ingestion(sesion, fingerprint):
    """Portable lookup by detalle->>'huella' (on PostgreSQL a unique index backs it)."""
    for run in sesion.scalars(select(Run).where(
            Run.tipo == "ingesta", Run.estado == "exitosa").order_by(Run.id_ejecucion.desc())):
        if (run.detalle or {}).get("huella") == fingerprint:
            return run
    return None


def persist_load(sesion, data):
    """Insert/update the batch in the caller's transaction, without duplicating it."""
    if not data.validacion_gx.get("exito"):
        raise ValueError("No se permite cargar entradas que no aprobaron GX")
    fingerprint = load_fingerprint(data)
    previous = existing_ingestion(sesion, fingerprint)
    if previous is not None:
        return {**previous.detalle["resumen"], "id_ejecucion": previous.id_ejecucion, "reutilizada": True}
    run = Run(tipo="ingesta", estado="en_curso", detalle={"huella": fingerprint})
    sesion.add(run)
    sesion.flush()
    instant = utc_now()
    upsert(sesion, Province.__table__, data.provincias, ["ubigeo_provincia"])
    upsert(sesion, District.__table__, data.distritos, ["ubigeo"])
    upsert(sesion, EpiWeek.__table__, data.semanas, ["id_semana"])
    upsert(sesion, WeeklyObservation.__table__,
           [{**o, "fecha_extraccion": instant, "id_ejecucion": run.id_ejecucion} for o in data.observaciones],
           ["ubigeo", "id_semana"])
    last = max(o["id_semana"] for o in data.observaciones)
    summary = {"provincias": len(data.provincias), "distritos": len(data.distritos),
               "semanas_calendario": len(data.semanas), "observaciones": len(data.observaciones),
               "fecha_corte_datos": str(data.fecha_corte_datos), "id_semana_corte": last}
    run.estado = "exitosa"
    run.id_semana_corte = last
    run.fin = utc_now()
    run.detalle = {"huella": fingerprint, "hashes_entrada": data.hashes,
                         "validacion_gx": data.validacion_gx, "resumen": summary,
                         "fecha_extraccion": instant.isoformat()}
    sesion.flush()
    return {**summary, "id_ejecucion": run.id_ejecucion, "reutilizada": False}


def record_failure(motor, kind, error, detail=None):
    """Record a failed run in its own transaction."""
    with transaction(motor) as sesion:
        sesion.add(Run(tipo=kind, estado="fallida", fin=utc_now(), detalle=detail or {},
                             mensaje_error=f"{type(error).__name__}: {error}"[:2000]))


def require_schema(motor):
    tables = set(inspect(motor).get_table_names())
    if not {"ejecucion", "observacion_semanal", "parametro_sistema", "semana_epidemiologica"} <= tables:
        raise ValueError("Faltan tablas del esquema OE2: ejecute alembic upgrade head antes de cargar")


def load_data(motor):
    """Require a migrated database and publish the whole load in a single transaction."""
    require_schema(motor)
    try:
        data = prepare_load()
    except (ValueError, OSError) as error:
        record_failure(motor, "ingesta", error, {"etapa": "preparacion"})
        raise
    try:
        with transaction(motor) as sesion:
            return persist_load(sesion, data)
    except (SQLAlchemyError, ValueError) as error:
        record_failure(motor, "ingesta", error, {"huella": load_fingerprint(data)})
        raise


def main(argv=None):
    """CLI without credentials in arguments or error output."""
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    motor = None
    try:
        motor = make_engine()
        print(json.dumps(load_data(motor), ensure_ascii=False))
        return 0
    except SQLAlchemyError:
        print("No se pudo completar la carga en la BD; revise conexión, migraciones y permisos", file=sys.stderr)
        return 1
    except (InvalidDatabaseSettings, ValueError, OSError) as error:
        print(f"Carga rechazada: {error}", file=sys.stderr)
        return 1
    finally:
        if motor is not None:
            motor.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
