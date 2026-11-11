"""Audit geographic and temporal coverage of the two external surveillance inputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd

from denguekay.data.ingestion.district_boundaries import ADM3_LAYER, pcode_to_ubigeo
from denguekay.features.long_history import week_grid

DEPARTMENTS = {"LAMBAYEQUE": "14", "TUMBES": "24"}
SOURCE_COLUMNS = ("departamento", "tipo_dx", "ubigeo", "ano", "semana")


def audit_department(
    notifications: pd.DataFrame,
    polygons: gpd.GeoDataFrame,
    department: str,
    prefix: str,
) -> dict:
    boundaries = polygons.loc[polygons["adm1_pcode"].eq(f"PE{prefix}")]
    if boundaries.empty or boundaries.crs is None:
        raise ValueError(f"Missing district boundaries or CRS for {department}")
    boundary_codes = pcode_to_ubigeo(boundaries["adm3_pcode"])
    if not boundary_codes.str.startswith(prefix).all() or boundary_codes.duplicated().any():
        raise ValueError(f"Invalid or duplicate boundary UBIGEO for {department}")

    codes = notifications["ubigeo"].str.strip()
    valid_codes = codes.str.fullmatch(r"[0-9]{1,6}", na=False)
    cases = notifications.loc[valid_codes].copy()
    cases["ubigeo"] = codes.loc[valid_codes].str.zfill(6)
    source_codes = set(cases["ubigeo"])
    polygon_codes = set(boundary_codes)

    year = pd.to_numeric(notifications["ano"], errors="coerce")
    week = pd.to_numeric(notifications["semana"], errors="coerce")
    valid_numbers = year.between(1900, 2100) & year.mod(1).eq(0) & week.between(1, 53) & week.mod(1).eq(0)
    week_keys = pd.MultiIndex.from_arrays([year.loc[valid_numbers], week.loc[valid_numbers]])
    if week_keys.empty:
        raise ValueError(f"No usable epidemiological weeks for {department}")
    calendar = week_grid(int(year.loc[valid_numbers].min()), int(year.loc[valid_numbers].max()))
    calendar_keys = pd.MultiIndex.from_frame(calendar[["anio", "semana"]])
    in_calendar = week_keys.isin(calendar_keys)
    observed_weeks = week_keys[in_calendar].unique().sort_values()
    if observed_weeks.empty:
        raise ValueError(f"No MMWR dates for {department}")

    return {
        "distritos_cod_ab": len(polygon_codes),
        "geometrias_invalidas_o_vacias": int((~boundaries.is_valid | boundaries.is_empty).sum()),
        "distritos_con_notificacion_confirmada_y_poligono": len(source_codes & polygon_codes),
        "poligonos_sin_notificacion_confirmada": sorted(polygon_codes - source_codes),
        "ubigeos_confirmados_sin_poligono": sorted(source_codes - polygon_codes),
        "notificaciones_confirmadas_con_ubigeo_malformado": int((~valid_codes).sum()),
        "notificaciones_confirmadas_fuera_del_calendario_mmwr": len(notifications) - int(in_calendar.sum()),
        "primera_semana_con_confirmados": [int(value) for value in observed_weeks[0]],
        "ultima_semana_con_confirmados": [int(value) for value in observed_weeks[-1]],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True, help="National surveillance CSV")
    parser.add_argument("--boundaries", type=Path, required=True, help="National COD-AB GeoJSON ZIP")
    args = parser.parse_args()
    data = pd.read_csv(args.cases, usecols=list(SOURCE_COLUMNS), dtype="string", encoding="utf-8-sig")
    departments = data["departamento"].str.strip().str.upper()
    confirmed = data["tipo_dx"].str.strip().str.upper().eq("C")
    polygons = gpd.read_file(f"zip://{args.boundaries.resolve().as_posix()}!{ADM3_LAYER}")
    results = {
        name: audit_department(data.loc[confirmed & departments.eq(name)], polygons, name, code)
        for name, code in DEPARTMENTS.items()
    }
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
