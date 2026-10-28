"""Normalize and validate district-week dengue series from the Sala."""

from pathlib import Path

import pandas as pd

from src.utils.keys import normalizar_sala

KEY = ["ubigeo", "anio", "semana"]


def load_ubigeo_catalog(path: Path) -> pd.DataFrame:
    """Load the tracked Piura district lookup, including Sala selector labels."""
    catalog = pd.read_csv(path, dtype={"ubigeo": "string"})
    required = {"provincia", "distrito", "ubigeo"}
    if not required <= set(catalog):
        raise ValueError(f"UBIGEO catalogue lacks columns: {sorted(required - set(catalog))}")
    catalog = catalog.copy()
    catalog["ubigeo"] = catalog["ubigeo"].str.zfill(6)
    catalog["provincia_sala"] = catalog["provincia"].map(normalizar_sala)
    catalog["distrito_sala"] = catalog["distrito"].map(
        lambda value: normalizar_sala(value).removesuffix("_S")
    )
    if catalog["ubigeo"].duplicated().any() or catalog[["provincia_sala", "distrito_sala"]].duplicated().any():
        raise ValueError("UBIGEO catalogue has duplicate codes or Sala district labels")
    return catalog


def _points(record: dict) -> dict[int, int]:
    points = record.get("points")
    if not isinstance(points, list):
        raise ValueError("Sala record lacks weekly points")
    weeks = [int(pair[0]) for pair in points]
    if not weeks or weeks != list(range(1, len(weeks) + 1)):
        raise ValueError("Sala weekly points are not contiguous from week 1")
    values = {}
    for week, raw_value in points:
        value = int(raw_value)
        if value < 0 or value != raw_value:
            raise ValueError("Sala case counts must be nonnegative integers")
        values[int(week)] = value
    return values


def normalize_sala_records(records: list[dict], controls: list[dict], catalog: pd.DataFrame) -> pd.DataFrame:
    """Map Sala names to UBIGEO and reconcile full-province/year extractions."""
    lookup = {
        (row.provincia_sala, row.distrito_sala): row.ubigeo
        for row in catalog.itertuples()
    }
    expected_by_province = catalog.groupby("provincia_sala").size().to_dict()
    province_controls = {
        normalizar_sala(item["provincia"]): _points(item)
        for item in controls if item.get("nivel") == "provincia"
    }
    department_controls = [_points(item) for item in controls if item.get("nivel") == "departamento"]
    if not records:
        raise ValueError("Sala returned no district records")
    year = int(records[0].get("anio", records[0].get("ano")))
    parsed = {}
    for item in records:
        if int(item.get("anio", item.get("ano"))) != year:
            raise ValueError("Sala returned mixed years")
        label = (normalizar_sala(item["provincia"]), normalizar_sala(item["distrito"]))
        if label not in lookup:
            raise ValueError(f"Sala district has no UBIGEO mapping: {label}")
        if label in parsed:
            raise ValueError(f"Sala returned duplicate district: {label}")
        parsed[label] = _points(item)

    rows = []
    full_department = len(parsed) == len(catalog)
    department_last_week = max(department_controls[0]) if full_department and len(department_controls) == 1 else None
    for (province, district), observed in parsed.items():
        full_province = sum(key[0] == province for key in parsed) == expected_by_province[province]
        control = province_controls.get(province)
        if full_province and control is None:
            raise ValueError(f"Sala lacks province control for {province}")
        if full_province and max(observed) > max(control):
            raise ValueError(f"Sala district has weeks beyond province control: {province}, {district}")
        last_week = max(max(control), department_last_week or 0) if full_province else max(observed)
        weeks = range(1, last_week + 1)
        for week in weeks:
            if week not in observed and (not full_province or week <= max(observed)):
                raise ValueError(f"Sala omitted an internal district week: {province}, {district}, {week}")
            rows.append({
                "ubigeo": lookup[(province, district)], "anio": year, "semana": week,
                "casos_Dengue": observed.get(week, 0),
                "semana_observada_en_grafico": int(week in observed),
                "provincia": province, "distrito": district,
            })
    result = pd.DataFrame(rows)
    if result.duplicated(KEY).any():
        raise ValueError("Sala normalization produced duplicate district-weeks")

    for province, count in expected_by_province.items():
        if sum(key[0] == province for key in parsed) != count:
            continue
        actual = result[result["provincia"] == province].groupby("semana")["casos_Dengue"].sum().to_dict()
        control = {week: province_controls[province].get(week, 0) for week in actual}
        if actual != control:
            raise ValueError(f"Sala province totals do not reconcile: {province}")
    if full_department:
        if len(department_controls) != 1:
            raise ValueError("Sala lacks a unique department control")
        actual = result.groupby("semana")["casos_Dengue"].sum().to_dict()
        control = {week: department_controls[0].get(week, 0) for week in actual}
        if actual != control:
            raise ValueError("Sala department totals do not reconcile")
    return result.sort_values(KEY).reset_index(drop=True)


def upsert_sala_silver(path: Path, fresh: pd.DataFrame) -> None:
    """Store normalized runtime output by district-year-week without duplicates."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        previous = pd.read_csv(path, dtype={"ubigeo": "string"})
        fresh = pd.concat([previous, fresh], ignore_index=True)
    fresh.drop_duplicates(KEY, keep="last").sort_values(KEY).to_csv(path, index=False)
