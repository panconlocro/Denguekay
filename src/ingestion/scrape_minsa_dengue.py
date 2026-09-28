"""Read district-year dengue series from the public MINSA/DGE Sala chart.

The Shiny chart exposes a full annual series per district. Callers select the
weeks they need after extraction. Raw responses are optional runtime artifacts.
"""

import asyncio
import html
import json
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

from src.utils.keys import normalizar_sala

URL = "https://app7.dge.gob.pe/maps2/shiny_metaxenicas_web/"
CHART = "ten-fig02b-echart"


def observed_weekly_points(raw_points: list, year: int) -> list[list[int]]:
    """Keep observed weeks and reject internal gaps or malformed case counts."""
    points = [point["value"] for point in raw_points]
    weeks = [week for week, _ in points]
    if weeks != list(range(1, len(weeks) + 1)) or not weeks:
        raise RuntimeError(f"Sala weekly series for {year} is malformed")
    first_unobserved = next((index for index, (_, value) in enumerate(points) if value is None), len(points))
    if any(value is not None for _, value in points[first_unobserved:]):
        raise RuntimeError(f"Sala weekly series for {year} contains an internal missing week")
    observed = points[:first_unobserved]
    if not observed or any(not isinstance(value, (int, float)) or value < 0 or int(value) != value for _, value in observed):
        raise RuntimeError(f"Sala case counts for {year} are malformed")
    return observed


def initial_inputs(page: str) -> dict:
    """Build the initial Shiny inputs from the site's HTML."""
    values = {}
    for input_id, options in re.findall(r'<select id="([^"]+)"[^>]*>(.*?)</select>', page, re.S):
        selected = re.search(r'<option value="([^"]*)" selected', options)
        if selected:
            values[input_id] = selected[1]
    for name, value in re.findall(r'<input type="radio" name="([^"]+)" value="([^"]+)" checked', page):
        values[name] = value
    for input_id in re.findall(r'<button [^>]*class="[^"]*action-button[^"]*"[^>]*id="([^"]+)"', page):
        values[input_id + ":shiny.action"] = 0
    values.update({
        "ten-pn01": "Tendencias", "dir-pn01": "Tendencias",
        ".clientdata_pixelratio": 1, ".clientdata_url_protocol": "https:",
        ".clientdata_url_hostname": "app7.dge.gob.pe", ".clientdata_url_port": "",
        ".clientdata_url_pathname": "/maps2/shiny_metaxenicas_web/",
        ".clientdata_url_search": "", ".clientdata_url_hash": "",
    })
    for input_id in re.findall(r'id="([^"]+)"', page):
        if any(part in input_id for part in ("-echart", "-kpi", "-tbl", "-map", "-card")):
            values[".clientdata_output_" + input_id + "_hidden"] = True
    for input_id in (CHART, "ten-kpi01-title", "ten-kpi01-kpi01"):
        values[".clientdata_output_" + input_id + "_hidden"] = False
    values[".clientdata_output_" + CHART + "_width"] = 1000
    values[".clientdata_output_" + CHART + "_height"] = 400
    return values


class SalaClient:
    """Small client for the Sala's Shiny WebSocket protocol."""

    def __init__(self, websocket, artifact_dir: Path | None):
        self.websocket = websocket
        self.artifact_dir = artifact_dir
        self.sequence = 0
        self.run_number = 0
        self.options: dict[str, list[tuple[str, str]]] = {}
        self.log = (artifact_dir / "responses.ndjson").open("w", encoding="utf-8") if artifact_dir else None

    async def send(self, message: str) -> None:
        await self.websocket.send(json.dumps([f"{self.sequence:X}#" + message]))
        self.sequence += 1

    async def call(self, data: dict, method: str = "update") -> dict:
        await self.send("0|m|" + json.dumps({"method": method, "data": data}))
        received = {}
        while True:
            raw = await asyncio.wait_for(self.websocket.recv(), timeout=90)
            if raw == "h":
                continue
            if not raw.startswith("a"):
                raise RuntimeError(f"Unexpected Sala response: {raw[:120]}")
            done = False
            for message in json.loads(raw[1:]):
                if message.startswith("ACK "):
                    continue
                tag, body = message.split("#", 1)
                await self.websocket.send(json.dumps([f"ACK {int(tag, 16) + 1:X}"]))
                if "|c|" in body:
                    raise RuntimeError(f"Sala returned an error: {body[:300]}")
                payload = json.loads(body.split("|m|", 1)[1])
                if self.log:
                    self.log.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(), "request": data, "response": payload}, ensure_ascii=False) + "\n")
                    self.log.flush()
                if payload.get("errors") or payload.get("custom", {}).get("alert"):
                    raise RuntimeError(f"Sala returned an error: {payload.get('errors') or payload.get('custom')}")
                for item in payload.get("inputMessages", []):
                    options = item["message"].get("options", "")
                    if "<option " in options:
                        self.options[item["id"]] = [
                            (html.unescape(value), html.unescape(label))
                            for value, label in re.findall(r'<option value="([^"]*)"[^>]*>(.*?)</option>', options, re.S)
                        ]
                if "values" in payload:
                    received.update(payload["values"])
                    done = True
            if done:
                return received

    async def extract(self, year: int, province: str = "0", district: str = "0", level: str = "distrito") -> dict:
        self.run_number += 1
        response = await self.call({"ten-run:shiny.action": self.run_number})
        if CHART not in response:
            raise RuntimeError("Sala did not return a fresh weekly chart")
        chart = response[CHART]["x"]["opts"]
        if "semanal" not in chart["title"][0]["text"].lower():
            raise RuntimeError("Sala returned a chart with unexpected time granularity")
        series = [item for item in chart["series"] if str(item["name"]) == str(year)]
        if len(series) != 1:
            raise RuntimeError(f"Sala has no unique weekly series for {year}")
        points = observed_weekly_points(series[0]["data"], year)
        record = {
            "departamento": "PIURA", "provincia": province, "distrito": district,
            "nivel": level, "anio": year,
            "consulta_utc": datetime.now(timezone.utc).isoformat(),
            "fuente": URL, "titulo": chart["title"][0], "points": points,
            "kpi": {key: value for key, value in response.items() if "kpi" in key},
            "chart": response[CHART],
        }
        if self.artifact_dir:
            name = f"{level}_{province}_{district}".replace(" ", "_").replace("/", "_")
            (self.artifact_dir / f"{name}.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        return record

    def close(self) -> None:
        if self.log:
            self.log.close()


async def scrape_sala(
    year: int, targets: set[tuple[str, str]], artifact_dir: Path | None = None,
    url: str = URL,
) -> tuple[list[dict], list[dict]]:
    """Scrape requested normalized (province, district) labels for one year."""
    try:
        from websockets.asyncio.client import connect
    except ImportError as exc:
        raise RuntimeError("The Sala scraper requires 'websockets'; run the project setup first") from exc
    if artifact_dir:
        artifact_dir.mkdir(parents=True, exist_ok=True)
    try:
        page = urlopen(url, timeout=40).read().decode("utf-8")
        socket_url = url.replace("https:", "wss:") + "__sockjs__/n=" + secrets.token_hex(9) + "/000/" + secrets.token_hex(4) + "/websocket"
        async with connect(socket_url, origin="https://app7.dge.gob.pe", open_timeout=40, max_size=20_000_000) as websocket:
            if await websocket.recv() != "o":
                raise RuntimeError("Sala did not open the Shiny socket")
            client = SalaClient(websocket, artifact_dir)
            try:
                await client.send("0|o|")
                await client.call(initial_inputs(page), method="init")
                await client.call({"ten-fyear": str(year), "ten-fdepa-filter": "PIURA", "ten-tog02c": "2"})
                controls = [await client.extract(year, level="departamento")]
                records = []
                found = set()
                for province_value, province_name in client.options.get("ten-fprov-filter", []):
                    province_key = normalizar_sala(province_name)
                    if province_value == "0" or not any(key[0] == province_key for key in targets):
                        continue
                    await client.call({"ten-fprov-filter": province_value, "ten-fdist-filter": "0"})
                    districts = list(client.options.get("ten-fdist-filter", []))
                    controls.append(await client.extract(year, province_name, level="provincia"))
                    for district_value, district_name in districts:
                        key = (province_key, normalizar_sala(district_name))
                        if district_value == "0" or key not in targets:
                            continue
                        await client.send("0|m|" + json.dumps({"method": "update", "data": {"ten-fdist-filter": district_value}}))
                        records.append(await client.extract(year, province_name, district_name))
                        found.add(key)
                if found != targets:
                    raise RuntimeError(f"Sala district selectors missing: {sorted(targets - found)}")
                return records, controls
            finally:
                client.close()
    except Exception as exc:
        raise RuntimeError(f"Sala extraction failed for {year}: {exc}") from exc
