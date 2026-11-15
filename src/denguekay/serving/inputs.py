"""Inputs of the predictors, rebuilt in memory from the database for one cutoff week.

Only what a predictor declares in ``required_inputs`` is read; nothing is persisted and ``data/`` is never
read. There is no history before 2017 (decision M4): a predictor whose variables need it reports those
districts or origins as unavailable.
"""

from dataclasses import dataclass

import pandas as pd
from sqlalchemy import select

from denguekay.db.models import District, EpiWeek, Nino12Observation, WeeklyObservation
from denguekay.serving import parameters

INPUTS = frozenset({"casos", "clima", "poblacion", "calendario", "regla_brote", "casos_confirmados", "clima_b3", "nino12"})
# Database column -> modelling (silver/gold) name.
CLIMATE = {"temp_media_c": "temp_media", "temp_min_c": "temp_min", "temp_max_c": "temp_max",
           "precip_total_mm": "precip_total_mm", "hum_rel_media_pct": "hum_rel_media",
           "temp_media_era5_land_c": "temp_media_era5_land"}


@dataclass(frozen=True)
class ServingInputs:
    cases: pd.DataFrame | None  # ubigeo, anio, semana, semana_inicio, casos_Dengue (weeks closed at the cutoff)
    climate: pd.DataFrame | None  # ubigeo, anio, semana, semana_inicio and the CLIMATE columns
    population: pd.DataFrame | None  # ubigeo, poblacion (census 2017)
    calendar: pd.DataFrame | None  # id_semana, anio, semana, fecha_inicio, fecha_fin (whole calendar)
    outbreak_rule: dict | None  # parametro_sistema.regla_brote
    nino12: pd.DataFrame | None = None


def _weekly(sesion, end, columns, *, confirmed=False):
    query = select(
        WeeklyObservation.ubigeo, EpiWeek.anio, EpiWeek.semana, EpiWeek.fecha_inicio,
        *(getattr(WeeklyObservation, c) for c in columns)
    ).join(EpiWeek, EpiWeek.id_semana == WeeklyObservation.id_semana).where(EpiWeek.fecha_fin <= end)
    if confirmed:
        query = query.where(WeeklyObservation.casos_solo_confirmados.is_(True))
    rows = sesion.execute(query).all()
    return pd.DataFrame(rows, columns=["ubigeo", "anio", "semana", "semana_inicio", *columns])


def cases_panel(sesion, end, *, confirmed=False):
    """Cases per district and week closed at date ``end``."""
    panel = _weekly(sesion, end, ["casos_dengue"], confirmed=confirmed).rename(columns={"casos_dengue": "casos_Dengue"})
    panel["ubigeo"] = panel.ubigeo.astype("string")
    panel["semana_inicio"] = pd.to_datetime(panel.semana_inicio)
    panel["casos_Dengue"] = panel.casos_Dengue.astype(float)
    return panel.sort_values(["ubigeo", "semana_inicio"]).reset_index(drop=True)


def climate_panel(sesion, end):
    """Observed weekly climate closed at date ``end``, with the modelling names (missing values stay NaN)."""
    panel = _weekly(sesion, end, list(CLIMATE)).rename(columns=CLIMATE)
    panel["ubigeo"] = panel.ubigeo.astype("string")
    panel["semana_inicio"] = pd.to_datetime(panel.semana_inicio)
    for column in CLIMATE.values():
        panel[column] = panel[column].astype(float)
    return panel.sort_values(["ubigeo", "semana_inicio"]).reset_index(drop=True)


def b3_climate_panel(sesion, end):
    columns = {"temp_media_era5_land_c": "temp_media", "humedad_era5_land_pct": "hum_rel_media",
               "lluvia_chirps_mm": "precip_total_mm"}
    dates = ["semana_inicio", "fecha_era5_land_disponible", "fecha_chirps_disponible"]
    panel = _weekly(sesion, end, [*columns, *dates[1:]]).rename(columns=columns)
    for column in columns.values():
        panel[column] = panel[column].astype(float)
    for column in dates:
        panel[column] = pd.to_datetime(panel[column])
    return panel


def nino12_panel(sesion, end):
    rows = sesion.execute(select(Nino12Observation.mes, Nino12Observation.fecha_disponible,
                                 Nino12Observation.anomalia)
                          .where(Nino12Observation.fecha_disponible <= end)
                          .order_by(Nino12Observation.mes)).all()
    return pd.DataFrame(rows, columns=["mes", "fecha_disponible", "nino12_anom"])


def census_population(sesion):
    rows = sesion.execute(select(District.ubigeo, District.poblacion_censo_2017).where(
        District.poblacion_censo_2017.is_not(None))).all()
    population = pd.DataFrame(rows, columns=["ubigeo", "poblacion"])
    population["ubigeo"] = population.ubigeo.astype("string")
    return population


def calendar(sesion):
    rows = sesion.execute(select(EpiWeek.id_semana, EpiWeek.anio, EpiWeek.semana, EpiWeek.fecha_inicio,
                                 EpiWeek.fecha_fin).order_by(EpiWeek.id_semana)).all()
    return pd.DataFrame(rows, columns=["id_semana", "anio", "semana", "fecha_inicio", "fecha_fin"])


def build_inputs(sesion, cutoff, required):
    """``ServingInputs`` for the cutoff week (an ``EpiWeek``) with only the ``required`` inputs."""
    unknown = set(required) - INPUTS
    if unknown:
        raise ValueError(f"Entradas desconocidas para un predictor: {sorted(unknown)}")
    end = cutoff.fecha_fin
    cases = cases_panel(sesion, end, confirmed="casos" not in required) if required & {
        "casos", "casos_confirmados"} else None
    climate = climate_panel(sesion, end) if "clima" in required else (
        b3_climate_panel(sesion, end) if "clima_b3" in required else None)
    return ServingInputs(
        cases=cases,
        climate=climate,
        population=census_population(sesion) if "poblacion" in required else None,
        calendar=calendar(sesion) if "calendario" in required else None,
        outbreak_rule=parameters.read(sesion, "regla_brote") if "regla_brote" in required else None,
        nino12=nino12_panel(sesion, end) if "nino12" in required else None)
