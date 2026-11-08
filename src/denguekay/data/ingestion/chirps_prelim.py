"""
CHIRPS v3 daily preliminary (``sat``) from the CHC for the days that have no final yet (study 06, step b-V).

The preliminary comes as one global GeoTIFF per day (about 11 MB, not a COG), so each file is downloaded whole
into a temporary folder outside data/, checked against the grid of the final windows (same tolerance as the
method guard of b-IV), and only the Piura window (the same rows and columns as data/bronze/chirps/v3_sat/final/)
is saved in data/bronze/chirps/v3_sat/prelim/AAAA/. The run manifest keeps, for each day, the URL, the sha256,
size and Last-Modified of the global file. Bronze is never overwritten.

Pace: one file per request and at least ``MIN_PAUSE_S`` seconds between requests (the directory listing counts
as one); the run stops at the first HTTP 429 or any other error and does not retry.

FTP (decision of Rosa, 2026-11-08): the CHC's anonymous FTP (``FTP_HOST``) serves the same files without the
HTTPS rate limit. ``FtpSource`` and ``download_ftp`` fetch the preliminary or the final of each day (passive mode,
binary transfer, size checked against ``SIZE``, sha256, the GeoTIFF opened and ``check_grid`` against the final
windows), one second apart, and stop at the first error. A day that is already in bronze is fetched again and
compared: if its Piura window is identical nothing is written; if it was revised, the new window is saved apart in
``AAAA/<fecha_descarga>/``. The final goes to ``BRONZE_CHIRPS_FINAL_FTP``.

Source: https://www.chc.ucsb.edu/data/chirps3 (CC BY 4.0).
"""

from __future__ import annotations

import ftplib
import hashlib
import json
import re
import time
from datetime import date, datetime
from pathlib import Path

import numpy as np

from denguekay.config.paths import BRONZE_CHIRPS_FINAL, BRONZE_CHIRPS_FINAL_FTP, BRONZE_CHIRPS_PRELIM
from denguekay.data.ingestion import chirps_ee as ce
from denguekay.data.ingestion.chirps import USER_AGENT, save_window

PRODUCT = "CHIRPS v3.0 diario preliminar, desagregación sat (GeoTIFF global)"
PRELIM_DIR_URL = "https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/prelim/sat/{y}/"
PRELIM_FILE = "chirps-v3.0.prelim.{y}.{m:02d}.{d:02d}.tif"
MIN_PAUSE_S = 60.0
TIMEOUT_S = 300
_LISTED = re.compile(r'href="chirps-v3\.0\.prelim\.(\d{4})\.(\d{2})\.(\d{2})\.tif"')


class RateLimited(Exception):
    """The server answered HTTP 429."""


def file_name(day: date) -> str:
    return PRELIM_FILE.format(y=day.year, m=day.month, d=day.day)


def day_url(day: date) -> str:
    return PRELIM_DIR_URL.format(y=day.year) + file_name(day)


def day_path(day: date, folder: Path = BRONZE_CHIRPS_PRELIM) -> Path:
    return folder / f"{day.year}" / file_name(day)


def parse_listing(html: str) -> list[date]:
    """Days with a preliminary file in an Apache directory listing of ``prelim/sat/AAAA/``."""
    return sorted({date(int(y), int(m), int(d)) for y, m, d in _LISTED.findall(html)})


def days_to_fetch(listed: list[date], first_day: date) -> list[date]:
    """Listed days from ``first_day`` on; stops if they do not start at ``first_day`` or have a gap."""
    days = [d for d in listed if d >= first_day]
    if not days:
        return []
    expected = [date.fromordinal(o) for o in range(first_day.toordinal(), days[-1].toordinal() + 1)]
    if days != expected:
        missing = sorted(set(expected) - set(days))
        raise RuntimeError(f"El listado del preliminar tiene huecos desde {first_day}: faltan {missing}")
    return days


def check_response(status: int, headers=None) -> None:
    """429 -> RateLimited (with the Retry-After header, if any, in the message); any other non-200 -> error."""
    if status == 429:
        retry = (headers or {}).get("Retry-After")
        raise RateLimited(f"HTTP 429 (Retry-After: {retry!r})")
    if status != 200:
        raise RuntimeError(f"HTTP {status}")


class Pacer:
    """At least ``pause`` seconds between the start of two requests."""

    def __init__(self, pause: float = MIN_PAUSE_S, sleep=time.sleep, clock=time.monotonic):
        self.pause, self.sleep, self.clock, self.last = pause, sleep, clock, None

    def wait(self) -> None:
        if self.last is not None:
            left = self.pause - (self.clock() - self.last)
            if left > 0:
                self.sleep(left)
        self.last = self.clock()


def fetch_listing(year: int, get) -> str:
    r = get(PRELIM_DIR_URL.format(y=year), headers={"User-Agent": USER_AGENT}, timeout=60)
    check_response(r.status_code, r.headers)
    return r.text


def fetch_global(day: date, tmp_dir: Path, get) -> dict:
    """Download one global file whole into ``tmp_dir``; sha256, bytes and Last-Modified of the response."""
    url = day_url(day)
    r = get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_S)
    check_response(r.status_code, r.headers)
    content = r.content
    expected = r.headers.get("Content-Length")
    if expected is not None and int(expected) != len(content):
        raise RuntimeError(f"{url}: {len(content)} bytes, se esperaban {expected}")
    path = Path(tmp_dir) / file_name(day)
    path.write_bytes(content)
    return {"dia": day.isoformat(), "url": url, "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(), "last_modified": r.headers.get("Last-Modified"),
            "ruta_temporal": path}


def reference_grid(folder: Path = BRONZE_CHIRPS_FINAL) -> dict:
    """Transform, shape, CRS and dtype of the final windows (the first saved one)."""
    import rasterio

    first = next(iter(sorted(folder.glob("*/chirps-v3.0.sat.*.tif"))), None)
    if first is None:
        raise FileNotFoundError(f"No hay ventanas del final en {folder}")
    with rasterio.open(first) as ds:
        return {"transform": tuple(ds.transform)[:6], "shape": (ds.height, ds.width), "crs": ds.crs,
                "dtype": ds.dtypes[0], "archivo": first.name}


def crop_to_reference(global_path: Path, ref: dict) -> tuple[np.ndarray, dict, dict]:
    """Check the global grid against the final windows (``ce.check_grid``) and cut the same rows and columns.

    Raises ``ValueError`` if the grid does not match within ``ce.GRID_TOLERANCE_DEG`` or the window falls
    outside the file. Values are untouched (-9999 included)."""
    import rasterio
    from rasterio.windows import Window

    with rasterio.open(global_path) as ds:
        grid = ce.check_grid(ref["transform"], tuple(ds.transform)[:6])
        grid["crs"] = str(ds.crs)
        if not grid["pasa"] or ds.crs != ref["crs"]:
            raise ValueError(f"La grilla del preliminar no coincide con la del final: {grid}")
        col, row = (int(round(v)) for v in grid["desfase_pixeles"])
        height, width = ref["shape"]
        if col < 0 or row < 0 or col + width > ds.width or row + height > ds.height:
            raise ValueError("La ventana de Piura se sale del archivo global.")
        window = Window(col, row, width, height)
        data = ds.read(1, window=window)
        profile = {"driver": "GTiff", "dtype": data.dtype.name, "count": 1, "height": height, "width": width,
                   "crs": ds.crs, "transform": ds.window_transform(window)}
    return data, profile, grid


def download_prelim(days: list[date], *, get, pacer: Pacer, tmp_dir: Path, ref: dict,
                    folder: Path = BRONZE_CHIRPS_PRELIM, log=print) -> dict:
    """Download, check and cut each missing day; stops at the first 429 or other error (no retries)."""
    summary = {"estado": "completa", "error": None, "dias": [], "ya_estaban": [], "grillas_ok": 0}
    t0 = time.time()
    for day in days:
        target = day_path(day, folder)
        if target.exists():
            summary["ya_estaban"].append(day.isoformat())
            continue
        pacer.wait()
        try:
            info = fetch_global(day, tmp_dir, get)
            data, profile, grid = crop_to_reference(info["ruta_temporal"], ref)
        except RateLimited as exc:
            summary.update(estado="detenida_429", error=f"{day}: {exc}")
            log(f"{day}: HTTP 429; se detiene.")
            break
        except Exception as exc:  # noqa: BLE001 - any other failure stops the run, reported as is
            summary.update(estado="detenida_error", error=f"{day}: {type(exc).__name__}: {exc}"[:300])
            log(f"{day}: {exc}; se detiene.")
            break
        finally:
            for p in Path(tmp_dir).glob("*.tif"):
                p.unlink()
        save_window(data, profile, target)
        summary["grillas_ok"] += 1
        info.pop("ruta_temporal")
        summary["dias"].append({**info, "grilla": grid, "archivo": target.name,
                                "sin_dato": int((data == ce.NODATA).sum())})
        log(f"{day}: {info['bytes']} bytes, Last-Modified {info['last_modified']}, grilla ok "
            f"({time.time() - t0:.0f} s)")
    summary["segundos"] = round(time.time() - t0, 1)
    return summary


def write_run_manifest(summary: dict, extra: dict, folder: Path = BRONZE_CHIRPS_PRELIM) -> Path:
    """One JSON per run, never overwritten."""
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    path = folder / f"manifiesto_prelim_{stamp}.json"
    n = 1
    while path.exists():
        path, n = folder / f"manifiesto_prelim_{stamp}_{n}.json", n + 1
    path.write_text(json.dumps({**extra, **summary}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return path


# --- FTP (2026-11-08) ------------------------------------------------------------------------------------------

FTP_HOST = "ftp.chc.ucsb.edu"
FTP_DIRS = {"prelim": "/products/CHIRPS/v3.0/daily/prelim/sat/{y}", "final": "/products/CHIRPS/v3.0/daily/final/sat/{y}"}
FTP_FILES = {"prelim": PRELIM_FILE, "final": "chirps-v3.0.sat.{y}.{m:02d}.{d:02d}.tif"}
FTP_FOLDERS = {"prelim": BRONZE_CHIRPS_PRELIM, "final": BRONZE_CHIRPS_FINAL_FTP}
FTP_PAUSE_S = 1.0
_FTP_NAME = {"prelim": re.compile(r"chirps-v3\.0\.prelim\.(\d{4})\.(\d{2})\.(\d{2})\.tif$"),
             "final": re.compile(r"chirps-v3\.0\.sat\.(\d{4})\.(\d{2})\.(\d{2})\.tif$")}


def ftp_file_name(day: date, version: str) -> str:
    return FTP_FILES[version].format(y=day.year, m=day.month, d=day.day)


def ftp_remote_path(day: date, version: str) -> str:
    return FTP_DIRS[version].format(y=day.year) + "/" + ftp_file_name(day, version)


def ftp_target(day: date, version: str, folder: Path | None = None) -> Path:
    return (folder or FTP_FOLDERS[version]) / f"{day.year}" / ftp_file_name(day, version)


def revision_path(day: date, version: str, stamp: str, folder: Path | None = None) -> Path:
    """Where a revised window goes: ``AAAA/<stamp>/<file>`` (``stamp`` = download date), never over the first."""
    return (folder or FTP_FOLDERS[version]) / f"{day.year}" / stamp / ftp_file_name(day, version)


def parse_ftp_names(names: list[str], version: str) -> list[date]:
    """Days in an FTP name listing (full paths or bare names)."""
    out = set()
    for n in names:
        m = _FTP_NAME[version].search(n)
        if m:
            out.add(date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
    return sorted(out)


class FtpSource:
    """Anonymous, passive, binary FTP session with the CHC (``ftp_factory`` is replaced in the tests)."""

    def __init__(self, host: str = FTP_HOST, timeout: int = 60, ftp_factory=ftplib.FTP):
        self.host, self.timeout, self.ftp_factory, self.ftp = host, timeout, ftp_factory, None

    def __enter__(self):
        self.ftp = self.ftp_factory(self.host, timeout=self.timeout)
        self.ftp.login()
        self.ftp.set_pasv(True)
        self.ftp.voidcmd("TYPE I")
        return self

    def __exit__(self, *exc):
        try:
            self.ftp.quit()
        except ftplib.all_errors:
            pass

    def listing(self, version: str, year: int) -> list[date]:
        return parse_ftp_names(self.ftp.nlst(FTP_DIRS[version].format(y=year)), version)

    def fetch(self, day: date, version: str, tmp_dir: Path) -> dict:
        """Download one global file into ``tmp_dir``; its size must equal what ``SIZE`` reports."""
        remote = ftp_remote_path(day, version)
        size = self.ftp.size(remote)
        path = Path(tmp_dir) / ftp_file_name(day, version)
        h = hashlib.sha256()
        with open(path, "wb") as f:
            def write(chunk):
                f.write(chunk)
                h.update(chunk)
            self.ftp.retrbinary(f"RETR {remote}", write, blocksize=1 << 16)
        got = path.stat().st_size
        if size is None or got != size:
            raise RuntimeError(f"{remote}: {got} bytes, el servidor informa {size}")
        try:
            modified = self.ftp.voidcmd(f"MDTM {remote}").split()[-1]
        except ftplib.all_errors:
            modified = None
        return {"dia": day.isoformat(), "version": version, "ruta_ftp": remote, "bytes": got, "tamano_servidor": size,
                "sha256": h.hexdigest(), "mdtm": modified, "ruta_temporal": path}


def _read_window(path: Path) -> np.ndarray:
    import rasterio

    with rasterio.open(path) as ds:
        return ds.read(1)


def download_ftp(days: list[date], version: str, *, source, tmp_dir: Path, ref: dict, stamp: str,
                 folder: Path | None = None, pause: float = FTP_PAUSE_S, sleep=time.sleep, log=print) -> dict:
    """Fetch, check and cut each day; a day already in bronze is compared and, if revised, saved apart.
    Stops at the first error (no retries)."""
    base = folder or FTP_FOLDERS[version]
    summary = {"estado": "completa", "error": None, "version": version, "dias": [], "sin_cambios": [],
               "revisiones": [], "grillas_ok": 0}
    t0 = time.time()
    for i, day in enumerate(days):
        if i:
            sleep(pause)
        try:
            info = source.fetch(day, version, tmp_dir)
            data, profile, grid = crop_to_reference(info["ruta_temporal"], ref)
        except Exception as exc:  # noqa: BLE001 - FTP, size, GeoTIFF or grid: stop and report as is
            summary.update(estado="detenida_error", error=f"{day}: {type(exc).__name__}: {exc}"[:300])
            log(f"{day}: {exc}; se detiene.")
            break
        finally:
            for p in Path(tmp_dir).glob("*.tif"):
                p.unlink()
        info.pop("ruta_temporal")
        summary["grillas_ok"] += 1
        target = ftp_target(day, version, base)
        record = {**info, "grilla": grid, "sin_dato": int((data == ce.NODATA).sum())}
        if target.exists():
            if np.array_equal(_read_window(target), data):
                summary["sin_cambios"].append(day.isoformat())
                log(f"{day}: ya estaba, sin cambios")
                continue
            target = revision_path(day, version, stamp, base)
            if target.exists():
                raise FileExistsError(f"{target} ya existe")
            summary["revisiones"].append(day.isoformat())
        save_window(data, profile, target)
        summary["dias"].append({**record, "archivo": target.relative_to(base).as_posix()})
        log(f"{day}: {info['bytes']} bytes, grilla ok ({time.time() - t0:.0f} s)")
    summary["segundos"] = round(time.time() - t0, 1)
    return summary


def write_ftp_manifest(summary: dict, extra: dict, version: str, folder: Path | None = None) -> Path:
    """One JSON per FTP run in the version's folder, never overwritten."""
    folder = folder or FTP_FOLDERS[version]
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    path = folder / f"manifiesto_ftp_{version}_{stamp}.json"
    n = 1
    while path.exists():
        path, n = folder / f"manifiesto_ftp_{version}_{stamp}_{n}.json", n + 1
    path.write_text(json.dumps({**extra, **summary}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return path
