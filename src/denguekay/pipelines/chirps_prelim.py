"""
CHIRPS v3 preliminary from the CHC and the weekly silver (study 06, step b-V).

    python -u -m denguekay.pipelines.chirps_prelim download   # days without final, paced, stops at the first 429
    python -u -m denguekay.pipelines.chirps_prelim silver     # final (Earth Engine) + preliminary -> weekly silver

``download`` starts on the day after the last final month (``chirps_ee.LAST_MONTH``) and ends on the last day
listed in ``prelim/sat/AAAA/``. Global files go to a temporary folder outside data/ and are deleted once cut.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

from denguekay.config.paths import BRONZE_CHIRPS_EE_FINAL, BRONZE_CHIRPS_PRELIM, DISTRICT_BOUNDARIES, SILVER_CHIRPS_PRECIP
from denguekay.data.ingestion import chirps_ee as ce
from denguekay.data.ingestion import chirps_prelim as cpr
from denguekay.data.ingestion.chirps import git_commit


def first_day_without_final(last_month: str = ce.LAST_MONTH) -> date:
    return ce.month_days(last_month)[-1] + timedelta(days=1)


def download(log=print) -> int:
    import requests

    first = first_day_without_final()
    ref = cpr.reference_grid()
    pacer = cpr.Pacer()
    pacer.wait()
    try:
        listed = cpr.parse_listing(cpr.fetch_listing(first.year, requests.get))
    except cpr.RateLimited:
        log("Listado: HTTP 429; se detiene sin bajar nada.")
        return 2
    days = cpr.days_to_fetch(listed, first)
    log(f"Listado {first.year}: {len(listed)} días; por bajar desde {first}: {len(days)} "
        f"({days[0] if days else '-'} a {days[-1] if days else '-'})")
    with tempfile.TemporaryDirectory(prefix="chirps_prelim_") as tmp:
        summary = cpr.download_prelim(days, get=requests.get, pacer=pacer, tmp_dir=Path(tmp), ref=ref, log=log)
    extra = {"producto": cpr.PRODUCT, "listado": cpr.PRELIM_DIR_URL.format(y=first.year),
             "rango_pedido": [str(first), str(days[-1]) if days else None], "pausa_minima_s": cpr.MIN_PAUSE_S,
             "grilla_referencia": {k: str(v) for k, v in ref.items()},
             "tolerancia_grilla_grados": ce.GRID_TOLERANCE_DEG, "commit": git_commit(),
             "user_agent": cpr.USER_AGENT}
    path = cpr.write_run_manifest(summary, extra)
    log(f"Manifiesto: {path}")
    log(json.dumps({k: summary[k] for k in ("estado", "error", "segundos", "grillas_ok")}, ensure_ascii=False))
    return 0 if summary["estado"] == "completa" else 2


def silver(log=print) -> int:
    from denguekay.data.processing import chirps_precipitation as cp

    districts = ce.load_districts()
    final = cp.daily_final_from_ee(BRONZE_CHIRPS_EE_FINAL)
    prelim = cp.daily_prelim_from_bronze(BRONZE_CHIRPS_PRELIM, districts)
    daily = cp.combine_daily(final, prelim)
    weekly, left_out = cp.weekly_by_version(daily)
    path = cp.write_silver(weekly, SILVER_CHIRPS_PRECIP)
    log(f"Silver: {path} ({len(weekly)} filas; polígonos {DISTRICT_BOUNDARIES.name})")
    log(f"Filas por versión: {weekly['version'].value_counts().to_dict()}")
    log(f"Semanas fuera (incompletas o con dos versiones): "
        f"{left_out.groupby('semana_inicio').size().to_dict() if len(left_out) else {}}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("accion", choices=["download", "silver"])
    args = parser.parse_args(argv)
    return download() if args.accion == "download" else silver()


if __name__ == "__main__":
    sys.exit(main())
