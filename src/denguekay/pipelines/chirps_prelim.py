"""
CHIRPS v3 preliminary from the CHC and the weekly silver (study 06, step b-V).

    python -u -m denguekay.pipelines.chirps_prelim download   # days without final, paced, stops at the first 429
    python -u -m denguekay.pipelines.chirps_prelim silver     # final (Earth Engine) + preliminary -> weekly silver
    python -u -m denguekay.pipelines.chirps_prelim silver --solo-final   # only the final version

    python -u -m denguekay.pipelines.chirps_prelim ftp --version prelim --desde 2026-09-27 [--hasta AAAA-MM-DD]
    python -u -m denguekay.pipelines.chirps_prelim silver-ftp --salida precip_chirps_v3_semanal_desde_2000_AAAAMMDD.csv

``download`` starts on the day after the last final month (``chirps_ee.LAST_MONTH``) and ends on the last day
listed in ``prelim/sat/AAAA/``. Global files go to a temporary folder outside data/ and are deleted once cut.

``ftp`` (2026-11-08) fetches the preliminary or the final by the CHC's FTP, from ``--desde`` to ``--hasta`` (by default
the last listed day); a day already in bronze is compared and, if revised, saved apart. ``silver-ftp`` writes the
weekly silver to a NEW file in data/silver/ (never over the one in use): the final is Earth Engine plus the FTP final
of the days Earth Engine does not have, the preliminary covers the weeks without a complete final, and each week has
one version (``combine_daily_by_week``).
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


def silver(final_only: bool = False, log=print) -> int:
    from denguekay.data.processing import chirps_precipitation as cp

    districts = ce.load_districts()
    final = cp.daily_final_from_ee(BRONZE_CHIRPS_EE_FINAL)
    # final_only: the preliminary days already in bronze stay there and do not enter the silver
    prelim = final.iloc[:0] if final_only else cp.daily_prelim_from_bronze(BRONZE_CHIRPS_PRELIM, districts)
    daily = cp.combine_daily(final, prelim)
    weekly, left_out = cp.weekly_by_version(daily)
    path = cp.write_silver(weekly, SILVER_CHIRPS_PRECIP)
    log(f"Silver: {path} ({len(weekly)} filas; polígonos {DISTRICT_BOUNDARIES.name})")
    log(f"Filas por versión: {weekly['version'].value_counts().to_dict()}")
    log(f"Semanas fuera (incompletas o con dos versiones): "
        f"{left_out.groupby('semana_inicio').size().to_dict() if len(left_out) else {}}")
    return 0


def ftp(version: str, first: date, last: date | None = None, log=print) -> int:
    """Fetch ``version`` by FTP from ``first`` to ``last`` (default: the last listed day); stops at the first error."""
    from datetime import datetime as dt

    ref = cpr.reference_grid()
    stamp = dt.now().strftime("%Y%m%d")
    with cpr.FtpSource() as source:
        listed = sorted(d for y in range(first.year, (last or date.today()).year + 1)
                        for d in source.listing(version, y))
        end = last or (listed[-1] if listed else first)
        wanted = [date.fromordinal(o) for o in range(first.toordinal(), end.toordinal() + 1)]
        missing = sorted(set(wanted) - set(listed))
        days = [d for d in wanted if d in set(listed)]
        log(f"FTP {version}: {len(days)} días por bajar de {first} a {end}; sin archivo en el servidor: {missing}")
        with tempfile.TemporaryDirectory(prefix=f"chirps_{version}_") as tmp:
            summary = cpr.download_ftp(days, version, source=source, tmp_dir=Path(tmp), ref=ref, stamp=stamp, log=log)
    extra = {"producto": f"CHIRPS v3.0 diario {version}, desagregación sat (GeoTIFF global, por FTP)",
             "servidor": cpr.FTP_HOST, "directorio": cpr.FTP_DIRS[version], "rango_pedido": [str(first), str(end)],
             "dias_sin_archivo": [str(d) for d in missing], "pausa_s": cpr.FTP_PAUSE_S,
             "grilla_referencia": {k: str(v) for k, v in ref.items()}, "tolerancia_grilla_grados": ce.GRID_TOLERANCE_DEG,
             "commit": git_commit(), "fecha_descarga": stamp}
    path = cpr.write_ftp_manifest(summary, extra, version)
    log(f"Manifiesto: {path}")
    log(json.dumps({k: summary[k] for k in ("estado", "error", "segundos", "grillas_ok")}
                   | {"guardados": len(summary["dias"]), "sin_cambios": len(summary["sin_cambios"]),
                      "revisiones": summary["revisiones"]}, ensure_ascii=False))
    return 0 if summary["estado"] == "completa" else 2


def silver_ftp(output_name: str, log=print) -> int:
    """Weekly silver from Earth Engine + FTP final + preliminary, one version per week, to a new file."""
    import pandas as pd

    from denguekay.config.paths import BRONZE_CHIRPS_FINAL_FTP, SILVER
    from denguekay.data.processing import chirps_precipitation as cp

    target = SILVER / output_name
    if target.resolve() == SILVER_CHIRPS_PRECIP.resolve():
        raise ValueError("silver-ftp no escribe sobre el silver vigente")
    districts = ce.load_districts()
    ee = cp.daily_final_from_ee(BRONZE_CHIRPS_EE_FINAL)
    ftp_final = cp.daily_from_windows(BRONZE_CHIRPS_FINAL_FTP, districts, "final", "chirps-v3.0.sat.*.tif")
    ee_days = set(ee["fecha"])
    extra_final = ftp_final[~ftp_final["fecha"].isin(ee_days)] if len(ftp_final) else ftp_final
    final = pd.concat([ee, extra_final], ignore_index=True) if len(extra_final) else ee
    prelim = cp.daily_from_windows(BRONZE_CHIRPS_PRELIM, districts, "prelim", "chirps-v3.0.prelim.*.tif")
    daily = cp.combine_daily_by_week(final, prelim)
    weekly, left_out = cp.weekly_by_version(daily)
    path = cp.write_silver(weekly, target)
    log(f"Silver nuevo: {path} ({len(weekly)} filas; final FTP fuera de Earth Engine: {extra_final['fecha'].nunique() if len(extra_final) else 0} días)")
    log(f"Filas por versión: {weekly['version'].value_counts().to_dict()}")
    log(f"Semanas fuera: {left_out.groupby('semana_inicio').size().to_dict() if len(left_out) else {}}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("accion", choices=["download", "silver", "ftp", "silver-ftp"])
    parser.add_argument("--solo-final", action="store_true", help="silver solo con la versión final de Earth Engine")
    parser.add_argument("--version", choices=["prelim", "final"], default="prelim")
    parser.add_argument("--desde", type=date.fromisoformat)
    parser.add_argument("--hasta", type=date.fromisoformat)
    parser.add_argument("--salida", help="nombre del silver nuevo en data/silver/")
    args = parser.parse_args(argv)
    if args.accion == "download":
        return download()
    if args.accion == "silver":
        return silver(final_only=args.solo_final)
    if args.accion == "ftp":
        if args.desde is None:
            parser.error("ftp necesita --desde")
        return ftp(args.version, args.desde, args.hasta)
    if not args.salida:
        parser.error("silver-ftp necesita --salida")
    return silver_ftp(args.salida)


if __name__ == "__main__":
    sys.exit(main())
