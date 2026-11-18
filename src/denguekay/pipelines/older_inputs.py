"""Silver and gold steps of v0 to v3 that V4 does not have: notified cases and the gold each version persisted.

The notebooks of ``pipelines/notebooks/V0`` to ``V3`` call these functions; the climate, socioeconomic and
meteo-socio steps are shared with V4 (``pipelines.v4_inputs``). Every path comes from ``config.paths``, so the output
goes where ``DENGUEKAY_DATA_DIR`` points (``data_anteriores/<version>``) and never over ``data/``.
"""

from hashlib import sha256
import subprocess
import sys

import pandas as pd

from denguekay.config.paths import (
    BRONZE_EPI_EXCEL, GOLD, GOLD_BACKUP, ROOT, SILVER_EPI_HISTORICAL, SILVER_INTEGRATED, SILVER_INTEGRATED_BASE,
    SILVER_METEO_SOCIO,
)
from denguekay.data.processing.epi_cases_legacy import build_weekly_cases, deduplicate_cases, load_raw
from denguekay.data.processing.merge import merge_with_epi
from denguekay.features.gold import generate_gold
from denguekay.features.outbreak_label import SeasonalOutbreakConfig

OUTBREAK_RULE = SeasonalOutbreakConfig(multiplicador=1.5, anios_previos=5, minimo_casos=2)
# What each version persisted: the column set and horizons of ``features.gold.generate_gold``.
VERSION_GOLD = {"v0": ("candidatas", (2, 4)), "v1": ("candidatas", (2, 4)), "v2": ("v2", (2,)), "v3": ("v3", (2,))}
CRLF = "\r\n"   # the frozen files were written on Windows


def historical_silver():
    """Weekly notified cases per district from the Excel of Drive (``epi_piura_semanal.csv`` of v1 to v3)."""
    cases = deduplicate_cases(build_weekly_cases(load_raw(BRONZE_EPI_EXCEL)))
    SILVER_EPI_HISTORICAL.parent.mkdir(parents=True, exist_ok=True)
    cases.to_csv(SILVER_EPI_HISTORICAL, index=False, lineterminator=CRLF)
    return {"archivo": SILVER_EPI_HISTORICAL.name, "filas": len(cases)}


def integrate_notified():
    """Meteo + socio + notified cases, then the updater fills the 2025 weeks from the Sala (notified definition)."""
    meteo_socio = pd.read_csv(SILVER_METEO_SOCIO, dtype={"ubigeo": "string"})
    cases = pd.read_csv(SILVER_EPI_HISTORICAL, dtype={"ubigeo": "string"})
    base = merge_with_epi(meteo_socio, cases)
    SILVER_INTEGRATED.parent.mkdir(parents=True, exist_ok=True)
    base.to_csv(SILVER_INTEGRATED_BASE, index=False, lineterminator=CRLF)
    subprocess.run([sys.executable, "-m", "denguekay.pipelines.weekly_update", "--input", str(SILVER_INTEGRATED_BASE),
                    "--output", str(SILVER_INTEGRATED), "--casos", "notificados"], cwd=ROOT, check=True)
    return {"archivo": SILVER_INTEGRATED.name, "filas": len(pd.read_csv(SILVER_INTEGRATED))}


def generate_version_gold(version):
    """The gold ``version`` persisted. v0 and v1 write ``gold/respaldo_pre_b3`` (h=2 and h=4 with every candidate and
    its ``SHA256SUMS.txt``); v2 and v3 write ``gold/`` (h=2; v3 adds the ERA5-Land d3 columns)."""
    columns, horizons = VERSION_GOLD[version]
    folder = GOLD_BACKUP if columns == "candidatas" else GOLD
    summary = generate_gold(SILVER_INTEGRATED, folder, outbreak=OUTBREAK_RULE, columns=columns, horizons=horizons)
    if columns == "candidatas":
        names = sorted(path.name for path in folder.iterdir() if path.suffix in (".csv", ".json"))
        lines = [f"{sha256((folder / name).read_bytes()).hexdigest()}  {name}\n" for name in names]
        (folder / "SHA256SUMS.txt").write_bytes("".join(lines).encode("utf-8"))
    return {h: {key: value for key, value in item.items() if key in ("archivo", "filas", "columnas", "sha256")}
            for h, item in summary.items()}
