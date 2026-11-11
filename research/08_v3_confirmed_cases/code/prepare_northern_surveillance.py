"""Download and reconcile official weekly confirmed-case series for external districts."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
from tempfile import TemporaryDirectory
from urllib.request import urlopen

import geopandas as gpd
import pandas as pd
from websockets.asyncio.client import connect

from audit_northern_transfer_inputs import DEPARTMENTS
from denguekay.data.ingestion.district_boundaries import ADM3_LAYER, compact_key, pcode_to_ubigeo
from denguekay.data.ingestion.minsa_sala_scraper import CHART, URL, SalaClient, confirmed_weekly_points, initial_inputs
from denguekay.data.keys import normalize_sala


def sala_label(value: str) -> str:
    """Recover the enye displayed as an eth in the Sala geography labels."""
    return value.replace("Ð", "Ñ").replace("ð", "ñ")


def catalog(cod_ab: Path) -> pd.DataFrame:
    districts = gpd.read_file(f"zip://{cod_ab.resolve()}!{ADM3_LAYER}")
    selected = districts.loc[districts.adm1_pcode.isin(f"PE{code}" for code in DEPARTMENTS.values())].copy()
    selected["ubigeo"] = pcode_to_ubigeo(selected.adm3_pcode)
    if len(selected) != 51 or selected.ubigeo.duplicated().any():
        raise ValueError("Expected 51 unique destination districts")
    return pd.DataFrame(selected[["ubigeo", "adm1_name", "adm2_name", "adm3_name"]]).sort_values("ubigeo")


async def fetch_chart(client: SalaClient, geography: tuple[str, ...], year: int) -> dict:
    client.run_number += 1
    response = await client.call({"ten-run:shiny.action": client.run_number})
    chart = response[CHART]["x"]["opts"]
    title = chart["title"][0]
    if normalize_sala(sala_label(title["subtext"])) != normalize_sala(sala_label("DENGUE - " + ", ".join(geography))):
        raise ValueError(f"Unexpected geography for {geography}: {title['subtext']}")
    return {
        "geografia": geography, "anio": year, "tipo_dx": "C", "consulta_utc": datetime.now(timezone.utc).isoformat(),
        "titulo": title, "puntos": confirmed_weekly_points(chart, year),
    }


def weekly_counts(chart: dict) -> pd.Series:
    return pd.Series(dict(chart["puntos"]), dtype="int64").rename_axis("semana")


def reconcile(aggregate: dict, children: list[dict]) -> None:
    expected = weekly_counts(aggregate)
    child_weeks = [weekly_counts(chart) for chart in children]
    if not child_weeks or any(not weeks.index.equals(expected.index) for weeks in child_weeks):
        raise ValueError(f"Mismatched weekly support for {aggregate['geografia']}")
    observed = pd.concat(child_weeks, axis=1).sum(axis=1)
    if not observed.equals(expected):
        differences = (observed - expected).loc[lambda s: s.ne(0)]
        raise ValueError(f"District totals differ from {aggregate['geografia']}: {differences.to_dict()}")


async def get_department(client: SalaClient, districts: pd.DataFrame, department: str, year: int):
    await client.call({"ten-fyear": str(year), "ten-fdepa-filter": department})
    control = await fetch_chart(client, (department,), year)
    all_records, province_controls = [], []
    provinces = {compact_key(sala_label(label)): (value, label) for value, label in client.options["ten-fprov-filter"] if value != "0"}
    for province, official in districts.groupby("adm2_name"):
        province_value, province_label = provinces[compact_key(province)]
        await client.call({"ten-fprov-filter": province_value, "ten-fdist-filter": "0"})
        aggregate = await fetch_chart(client, (department, province_label), year)
        province_controls.append(aggregate)
        options = {compact_key(sala_label(label)): (value, label) for value, label in client.options["ten-fdist-filter"] if value != "0"}
        records = []
        for district in official.itertuples(index=False):
            name = compact_key(district.adm3_name)
            if name not in options:
                raise ValueError(f"Missing Sala selector for {district.ubigeo} {district.adm3_name}: {sorted(options)}")
            district_value, district_label = options[name]
            await client.send("0|m|" + json.dumps({"method": "update", "data": {"ten-fdist-filter": district_value}}))
            chart = await fetch_chart(client, (department, province_label, district_label), year)
            records.append(chart | {"ubigeo": district.ubigeo})
        reconcile(aggregate, records)
        all_records.extend(records)
        print(department, province, len(records), flush=True)
    reconcile(control, province_controls)
    return all_records, [control, *province_controls]


async def extract(districts: pd.DataFrame, year: int):
    with urlopen(URL, timeout=30) as response:
        page = response.read().decode()
    socket = URL.replace("https:", "wss:") + "__sockjs__/n=" + secrets.token_hex(9) + "/000/" + secrets.token_hex(4) + "/websocket"
    rows, controls = [], []
    # Separate sessions keep the department controls independent.
    for department, prefix in DEPARTMENTS.items():
        district_table = districts.loc[districts.ubigeo.str.startswith(prefix)]
        async with connect(socket, origin="https://app7.dge.gob.pe", open_timeout=30, max_size=20_000_000) as ws:
            if await ws.recv() != "o":
                raise RuntimeError("Sala did not open a Shiny session")
            client = SalaClient(ws, None)
            await client.send("0|o|")
            await client.call(initial_inputs(page), method="init")
            found, summaries = await get_department(client, district_table, department, year)
            rows.extend(found)
            controls.extend(summaries)
        socket = URL.replace("https:", "wss:") + "__sockjs__/n=" + secrets.token_hex(9) + "/000/" + secrets.token_hex(4) + "/websocket"
    return rows, controls


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cod-ab", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--year", type=int, required=True)
    args = parser.parse_args()
    records, controls = asyncio.run(extract(catalog(args.cod_ab), args.year))
    frame = pd.DataFrame(
        {"ubigeo": r["ubigeo"], "anio": r["anio"], "semana": week, "casos_Dengue": count, "tipo_dx": "C"}
        for r in records for week, count in r["puntos"]
    )
    if frame.ubigeo.nunique() != 51 or frame.duplicated(["ubigeo", "anio", "semana"]).any():
        raise ValueError("Incomplete or duplicated district series")
    args.output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=args.output) as temp:
        staging = Path(temp)
        frame.to_csv(staging / f"sala_{args.year}.csv", index=False)
        (staging / f"sala_{args.year}.json").write_text(
            json.dumps({"fuente": URL, "distritos": records, "controles": controls}, ensure_ascii=False, indent=2) + "\n"
        )
        for path in staging.iterdir():
            path.replace(args.output / path.name)


if __name__ == "__main__":
    main()
