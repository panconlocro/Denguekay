"""
Detached run of the CHIRPS v3 download (cells A and B of pipelines/notebooks/03c_ingesta_chirps.ipynb).

From the repository (or worktree) root, with its .venv:

    python -u -m denguekay.pipelines.chirps_download [--start 2000-01-01] [--end 2025-12-31]

First checks one day of 2000 and one of 2025 (same -9999 sea mask, pixel size, centroids with data) and stops if
they differ; then downloads the missing days into data/bronze/chirps/v3_sat/final/ and leaves the run manifest.
Writes nothing else.
"""

import argparse
from datetime import date, datetime

import pandas as pd

from denguekay.config.paths import BRONZE_CHIRPS_FINAL, DISTRICT_COORDS
from denguekay.data.ingestion.chirps import check_sample_days, download_final

SAMPLE_DAYS = (date(2000, 1, 15), date(2025, 1, 15))


def main(argv=None) -> dict:
    parser = argparse.ArgumentParser(description="Descarga CHIRPS v3 diario (final sat) para Piura.")
    parser.add_argument("--start", default="2000-01-01")
    parser.add_argument("--end", default="2025-12-31")
    args = parser.parse_args(argv)
    print("Inicio:", datetime.now().isoformat(timespec="seconds"), "| destino:", BRONZE_CHIRPS_FINAL, flush=True)
    districts = pd.read_csv(DISTRICT_COORDS)
    check = check_sample_days(list(SAMPLE_DAYS), districts)
    print("Verificación inicial:", check["ok"], check["problemas"], flush=True)
    if not check["ok"]:
        raise SystemExit("La verificación inicial falló: no se descarga nada.")
    summary = download_final(args.start, args.end)
    print("Fin:", datetime.now().isoformat(timespec="seconds"), "| estado:", summary["estado"], flush=True)
    return summary


if __name__ == "__main__":
    main()
