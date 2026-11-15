"""Materialize the frozen B3 training specification from validated V4 silver inputs."""

import argparse
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

from denguekay.config.paths import (
    ROOT, SILVER_CHIRPS_PRECIP, SILVER_CONFIRMED, SILVER_ENSO, SILVER_INTEGRATED,
    SILVER_METEO_ERA5_LAND_2000_2026, UBIGEO_CATALOG, V4_CHIRPS, V4_ENSO, V4_ERA5_LAND, V4_GEOGRAPHY, V4_GOLD,
    V4_GOLD_MANIFEST, V4_HISTORY, V4_INTEGRATED, V4_SALA, V4_STUDY_MANIFEST,
)
from denguekay.data.loading import load_integrated
from denguekay.data.validation.integrated_expectations import coverage_path, load_case_coverage
from denguekay.data.validation.v4_panel import validate_confirmed_panel
from denguekay.features.b3 import GEO, NINO, WEATHER
from denguekay.features.long_history import OUTBREAK_RULE, long_inputs

KEY = ["ubigeo", "anio", "semana"]
DAY = pd.Timedelta(days=1)
HORIZONS = (2, 3, 4)


@dataclass(frozen=True)
class GoldInputs:
    panel: Path
    history: Path
    sala: Path
    era5: Path
    chirps: Path
    enso: Path
    geography: Path


def input_paths(release=False):
    if release:
        return GoldInputs(SILVER_CONFIRMED / SILVER_INTEGRATED.name, V4_HISTORY, V4_SALA,
                          SILVER_METEO_ERA5_LAND_2000_2026, SILVER_CHIRPS_PRECIP, SILVER_ENSO, V4_GEOGRAPHY)
    return GoldInputs(V4_INTEGRATED, V4_HISTORY, V4_SALA, V4_ERA5_LAND, V4_CHIRPS, V4_ENSO, V4_GEOGRAPHY)


def read_csv(path, dates=()):
    return pd.read_csv(path, dtype={"ubigeo": "string"}, parse_dates=list(dates), float_precision="round_trip")


def _weekly_means(frame, value, target):
    """Use the frozen five-week rolling aggregation and published-at-origin check."""
    data = frame.sort_values(["ubigeo", "semana_inicio"]).reset_index(drop=True)
    grouped = data.groupby("ubigeo")
    if not grouped.semana_inicio.diff().dropna().eq(7 * DAY).all():
        raise ValueError(f"Missing or duplicate weeks for {value}")
    mean = grouped[value].transform(lambda s: s.rolling(5, min_periods=5).mean())
    observed = mean.groupby(data.ubigeo).shift(2)
    publication = grouped.fecha_disponible
    latest = pd.concat([publication.shift(period) for period in range(2, 7)], axis=1).max(axis=1, skipna=False)
    valid = latest.notna() & latest.le(data.semana_inicio + 6 * DAY)
    return data.assign(**{target: observed.where(valid)}).set_index(["ubigeo", "semana_inicio"])[target]


def climate_table(era, rain, enso, origins):
    """Return B3 climate predictors in origin order without reading future publications."""
    sources = {"temp_media": era, "hum_rel_media": era, "precip_total_mm": rain}
    windows = pd.concat([_weekly_means(sources[value], value, output) for value, (_, output) in WEATHER.items()],
                        axis=1)
    key = pd.MultiIndex.from_arrays([origins.ubigeo, origins.origen_cierre - 6 * DAY], names=windows.index.names)
    result = windows.reindex(key).reset_index(drop=True)
    monthly = enso.sort_values(["anio", "mes"]).reset_index(drop=True)
    months = pd.PeriodIndex.from_fields(year=monthly.anio, month=monthly.mes, freq="M")
    if (months.hasnans or months.has_duplicates or (np.diff(months.asi8) != 1).any()
            or monthly.fecha_disponible.isna().any() or not monthly.fecha_disponible.is_monotonic_increasing):
        raise ValueError("Incomplete or unordered Niño 1+2 months")
    monthly[NINO] = monthly.nino12_anom.rolling(3).mean()
    index = origins[["origen_cierre"]].assign(position=np.arange(len(origins))).sort_values("origen_cierre")
    nino = pd.merge_asof(index, monthly[["fecha_disponible", NINO]], left_on="origen_cierre",
                         right_on="fecha_disponible", direction="backward").sort_values("position")
    result[NINO] = nino[NINO].to_numpy()
    return result


def _read_era(path, panel):
    era = read_csv(path, ("semana_inicio",))
    locations = panel[["lat", "lon", "ubigeo"]].drop_duplicates()
    era = era.merge(locations, on=["lat", "lon"], how="left", validate="many_to_one")
    if era.ubigeo.isna().any():
        raise ValueError("ERA5-Land coordinates do not map to the integrated panel")
    if "fecha_disponible" in era:
        era["fecha_disponible"] = pd.to_datetime(era.fecha_disponible)
    else:
        era["fecha_disponible"] = era.semana_inicio + 13 * DAY
    return era


def _gold_frame(inputs, spec, *, release=False):
    panel = load_integrated(inputs.panel)
    if not release:
        locations = read_csv(inputs.panel)[["ubigeo", "lat", "lon"]].drop_duplicates()
        panel = panel.drop(columns=["lat", "lon"]).merge(locations, how="left", on="ubigeo", validate="many_to_one")
    coverage = load_case_coverage(coverage_path(inputs.panel))
    if coverage is None:
        raise ValueError("Confirmed panel coverage is missing")
    validate_confirmed_panel(panel, coverage)
    sala = read_csv(inputs.sala)
    if sala.empty or not sala.tipo_dx.eq("C").all():
        raise ValueError("V4 requires confirmed Sala observations")
    cutoff = pd.Timestamp(spec["corte"])
    data = long_inputs(panel, inputs.era5, sala=sala, history_path=inputs.history)
    if data["ultima_semana"] + 6 * DAY < cutoff:
        raise ValueError(f"Confirmed observations do not reach the frozen cutoff {cutoff.date()}")
    origins = data["origenes"]
    targets = [f"semana_inicio_h{h}" for h in HORIZONS]
    train = origins.dropna(subset=targets)
    train = train.loc[train.semana_inicio_h4.add(6 * DAY).le(cutoff)].reset_index(drop=True)
    geography = read_csv(inputs.geography)
    if (geography.ubigeo.duplicated().any() or set(geography.ubigeo) != set(panel.ubigeo)
            or not np.isfinite(geography[list(GEO)].to_numpy(float)).all()):
        raise ValueError("Invalid frozen district geography")
    train = train.merge(geography[["ubigeo", *GEO]], on="ubigeo", how="left", validate="many_to_one")
    climate = climate_table(_read_era(inputs.era5, panel), read_csv(inputs.chirps, ("semana_inicio", "fecha_disponible")),
                            read_csv(inputs.enso, ("fecha_disponible",)), train)
    train = train.join(climate)
    predictors = spec["columnas"]["b3_obs"]
    if train.empty or not np.isfinite(train[predictors].to_numpy(float)).all() or train.duplicated(KEY).any():
        raise ValueError("Incomplete or duplicate B3 training rows")
    if not train.ubigeo.astype("string").str.fullmatch(r"\d{6}").all():
        raise ValueError("Invalid UBIGEO in V4 gold")

    labels = data["etiquetas"].set_index(["ubigeo", "semana_inicio"])
    out = train[[*KEY, "semana_inicio", "origen_inicio", "origen_cierre", *predictors]].copy()
    for h, target in zip(HORIZONS, targets, strict=True):
        if not train[target].eq(train.origen_cierre - 6 * DAY + pd.Timedelta(weeks=h)).all():
            raise ValueError(f"Misaligned V4 target at h{h}")
        actual = labels.reindex(pd.MultiIndex.from_frame(train[["ubigeo", target]]))
        counts = train[f"casos_Dengue_h{h}"].astype("int64")
        flags = train[f"brote_h{h}"].astype("int8")
        limits = actual.umbral_brote_casos.to_numpy()
        np.testing.assert_array_equal(actual.casos_Dengue, counts)
        np.testing.assert_array_equal(actual.brote, flags)
        np.testing.assert_array_equal(counts.gt(limits) & counts.ge(OUTBREAK_RULE["minimo_casos"]), flags)
        out[target] = train[target]
        out[f"casos_Dengue_h{h}"] = counts
        out[f"umbral_brote_casos_h{h}"] = limits
        out[f"brote_h{h}"] = flags
    return out, data["semanas_provisionales"]


def generate_gold(*, release=False):
    """Export gold using the frozen specification and the selected silver input paths."""
    spec = json.loads(V4_STUDY_MANIFEST.read_bytes())
    frozen_rule = {"minimo_casos": OUTBREAK_RULE["minimo_casos"], "anios_previos": OUTBREAK_RULE["anios_previos"],
                   "k_desviaciones": OUTBREAK_RULE["multiplicador"]}
    if tuple(spec["horizontes"]) != HORIZONS or spec["regla_brote"] != frozen_rule:
        raise ValueError("The V4 specification and feature implementation do not agree")
    inputs = input_paths(release)
    sources = [*vars(inputs).values(), coverage_path(inputs.panel), UBIGEO_CATALOG]
    hashes = {path.relative_to(ROOT).as_posix(): sha256(path.read_bytes()).hexdigest() for path in sources}
    if sha256(inputs.geography.read_bytes()).hexdigest() != spec["fuentes"]["geografia"]:
        raise ValueError("The frozen district geography must be extracted from the V4 release")
    if release:
        archive_sources = {path.relative_to(ROOT).as_posix(): path for path in sources}
        archive_sources.update({path.name: path for path in (inputs.chirps, inputs.enso)})
        for name, expected in spec["fuentes"].items():
            if name in archive_sources and sha256(archive_sources[name].read_bytes()).hexdigest() != expected:
                raise ValueError(f"V4 release input differs from the frozen manifest: {name}")
    frame, provisional = _gold_frame(inputs, spec, release=release)
    V4_GOLD.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=V4_GOLD.parent) as temp:
        csv = Path(temp) / V4_GOLD.name
        manifest = Path(temp) / V4_GOLD_MANIFEST.name
        frame.to_csv(csv, index=False, date_format="%Y-%m-%d", lineterminator="\n")
        metadata = {"version_modelo": "v4-b3", "archivo": csv.name, "sha256": sha256(csv.read_bytes()).hexdigest(),
                    "corte_etiquetas": spec["corte"], "llave": KEY, "horizontes": list(HORIZONS),
                    "filas": len(frame), "distritos": int(frame.ubigeo.nunique()),
                    "predictores": spec["columnas"], "regla_brote": spec["regla_brote"],
                    "semanas_provisionales": provisional, "fuentes": hashes,
                    "origen_insumos": "release" if release else "fuentes"}
        manifest.write_bytes((json.dumps(metadata, ensure_ascii=False, indent=2) + "\n").encode())
        csv.replace(V4_GOLD)
        manifest.replace(V4_GOLD_MANIFEST)
    return metadata


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--desde-release", action="store_true", help="usa los insumos verificados de datos_v4.zip")
    args = parser.parse_args(argv)
    print(json.dumps(generate_gold(release=args.desde_release), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
