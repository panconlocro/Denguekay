"""Prepare a validated batch of confirmed cases and observed climate for V4."""

from datetime import date, timedelta

import numpy as np
import pandas as pd

from denguekay.config.paths import (DISTRICT_BOUNDARIES, DISTRICT_COORDS, ROOT, UBIGEO_CATALOG, V4_CHIRPS, V4_ENSO, V4_ERA5_LAND,
                                    V4_HISTORY, V4_INTEGRATED, V4_SALA)
from denguekay.data.processing.district_locations import read_v4_era5
from denguekay.data.processing.epi_sala import load_ubigeo_catalog
from denguekay.data.validation.integrated_expectations import coverage_path, load_case_coverage
from denguekay.data.validation.v4_panel import validate_confirmed_panel
from denguekay.features.long_history import long_case_series, long_labels, sala_after_panel
from denguekay.serving import load_data as loader
from denguekay.serving.artifacts import sha256_bytes
from denguekay.serving.geometries import read_boundaries

def _uses_sources(options):
    return options.get("perfil_datos", "release") == "fuentes"


def _paths(options):
    # Both profiles read the same files (a run from the sources writes the Release names); they differ in the checks.
    return {
        "sala": ROOT / options.get("sala", V4_SALA),
        "era5_land": ROOT / options.get("era5_land", V4_ERA5_LAND),
        "chirps": ROOT / options.get("chirps", V4_CHIRPS),
        "nino12": ROOT / options.get("nino12", V4_ENSO),
    }


def source_hashes(options):
    medallion = _uses_sources(options)
    panel, history = V4_INTEGRATED, V4_HISTORY
    paths = [UBIGEO_CATALOG, DISTRICT_COORDS, DISTRICT_BOUNDARIES, panel, history, coverage_path(panel), *_paths(options).values()]
    if not medallion:
        paths.extend([loader.GOLD_MANIFEST, loader.GOLD / f"{panel.stem}_h2_gold.csv"])
    return {path.relative_to(ROOT).as_posix(): sha256_bytes(path.read_bytes()) for path in paths}


def _read(path, dates=()):
    return pd.read_csv(path, dtype={"ubigeo": "string"}, parse_dates=list(dates), float_precision="round_trip")


def _weekly_climate(paths, panel):
    era = read_v4_era5(paths["era5_land"])
    rain = _read(paths["chirps"], ("semana_inicio", "fecha_disponible"))
    columns = ["ubigeo", "semana_inicio"]
    a = era[columns + ["temp_media", "hum_rel_media", "fecha_disponible"]].rename(columns={
        "temp_media": "temp_media_era5_land_c", "hum_rel_media": "humedad_era5_land_pct",
        "fecha_disponible": "fecha_era5_land_disponible",
    })
    b = rain[columns + ["precip_total_mm", "fecha_disponible"]].rename(columns={
        "precip_total_mm": "lluvia_chirps_mm", "fecha_disponible": "fecha_chirps_disponible",
    })
    result = a.merge(b, on=columns, how="outer", validate="one_to_one")
    if not set(result.ubigeo) <= set(panel.ubigeo):
        raise ValueError("Clima de distritos fuera del catálogo de Piura")
    for column in ("fecha_era5_land_disponible", "fecha_chirps_disponible"):
        result[column] = pd.to_datetime(result[column])
        if (result[column] < result.semana_inicio + pd.Timedelta(days=6)).any():
            raise ValueError(f"{column} antecede el cierre de la observación semanal")
    for column, numeric_range in {"temp_media_era5_land_c": (-20, 50),
                                  "humedad_era5_land_pct": (0, 100),
                                  "lluvia_chirps_mm": (0, 1500)}.items():
        if not result[column].dropna().between(*numeric_range).all():
            raise ValueError(f"Rango inválido en {column}")
    return result


def _nino12(path):
    frame = _read(path, ("fecha_disponible",))
    months = pd.PeriodIndex.from_fields(year=frame.anio, month=frame.mes, freq="M")
    if (months.has_duplicates or frame.fecha_disponible.isna().any()
            or (frame.fecha_disponible < (months + 1).to_timestamp()).any()
            or not np.isfinite(frame.nino12_anom.to_numpy(float)).all()):
        raise ValueError("Serie Niño 1+2 inválida")
    return [{"mes": month.start_time.date(), "fecha_disponible": available.date(), "anomalia": float(value)}
            for month, available, value in zip(months, frame.fecha_disponible, frame.nino12_anom)]


def prepare_load(options):
    from denguekay.data.validation.gx_quality import validate_integrated_gx, validate_modeling_inputs
    from denguekay.features.model_input_contract import audit_handoff

    hashes = source_hashes(options)
    medallion = _uses_sources(options)
    panel_path, history_path = V4_INTEGRATED, V4_HISTORY
    paths = _paths(options)
    panel = _read(panel_path, ("semana_inicio",))
    if medallion:
        validate_confirmed_panel(panel, load_case_coverage(coverage_path(panel_path)))
        suite = validate_integrated_gx(panel_path)
        quality = {"exito": suite["exito"], "suites": {"silver_integrado": suite}}
    else:
        audit_handoff(silver_path=panel_path, history_path=history_path)
        quality = validate_modeling_inputs(silver_path=panel_path)
    sala = _read(paths["sala"])
    if sala.empty or not sala.tipo_dx.eq("C").all():
        raise ValueError("V4 requiere la serie de diagnóstico confirmado de la Sala Situacional")
    extra, _ = sala_after_panel(panel, sala, provisional=options.get("semanas_provisionales", 2))
    recent = pd.concat([panel, extra], ignore_index=True)
    catalog = load_ubigeo_catalog(UBIGEO_CATALOG)
    recent = recent.sort_values(["ubigeo", "semana_inicio"]).reset_index(drop=True)
    cases = pd.to_numeric(recent.casos_Dengue)
    expected_weeks = pd.date_range(recent.semana_inicio.min(), recent.semana_inicio.max(), freq="W-SUN")
    if (set(recent.ubigeo) != set(catalog.ubigeo)
            or recent.duplicated(["ubigeo", "semana_inicio"]).any()
            or set(recent.semana_inicio) != set(expected_weeks)
            or not recent.groupby("ubigeo").size().eq(len(expected_weeks)).all()
            or not np.isfinite(cases).all() or not cases.ge(0).all() or not cases.mod(1).eq(0).all()):
        raise ValueError("Faltan semanas verificadas de confirmados o hay valores inválidos")

    labels = long_labels(long_case_series(recent, history_path))
    observed = recent.merge(labels[["ubigeo", "semana_inicio", "brote", "umbral_brote_casos"]],
                            on=["ubigeo", "semana_inicio"], validate="one_to_one")
    observed = observed.merge(_weekly_climate(paths, panel), on=["ubigeo", "semana_inicio"],
                              how="left", validate="one_to_one")
    provinces, districts = loader.prepare_districts(
        catalog, pd.read_csv(DISTRICT_COORDS), loader.census_population_2017(panel), read_boundaries())
    cutoff = observed.semana_inicio.max().date() + timedelta(days=6)
    weeks = loader.prepare_weeks(date(2017, 1, 1), cutoff + timedelta(days=371))
    records = []
    for row in observed.itertuples():
        records.append({
            "ubigeo": row.ubigeo, "id_semana": loader.week_id(row.anio, row.semana),
            "casos_dengue": int(row.casos_Dengue), "casos_solo_confirmados": True,
            "umbral_brote_casos": round(float(row.umbral_brote_casos), 2), "brote": bool(row.brote),
            "fuente_casos": "sala_situacional" if row.anio >= 2025 else "excel_historico",
            "estado_cobertura": "verificado",
            **{destination: loader._optional(getattr(row, source), loader.CLIMATE_DECIMALS[destination])
               for source, destination in loader.CLIMATE.items()},
            "temp_media_era5_land_c": loader._optional(row.temp_media_era5_land_c, None),
            "humedad_era5_land_pct": loader._optional(row.humedad_era5_land_pct, None),
            "lluvia_chirps_mm": loader._optional(row.lluvia_chirps_mm, None),
            "fecha_era5_land_disponible": (None if pd.isna(row.fecha_era5_land_disponible)
                                          else row.fecha_era5_land_disponible.date()),
            "fecha_chirps_disponible": (None if pd.isna(row.fecha_chirps_disponible)
                                       else row.fecha_chirps_disponible.date()),
        })
    nino = _nino12(paths["nino12"])
    if hashes != source_hashes(options):
        raise ValueError("Los insumos cambiaron mientras se preparaba la carga V4")
    return loader.LoadBatch(provinces, districts, weeks, records, hashes, quality, cutoff, nino)
