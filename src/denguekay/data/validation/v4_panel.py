"""Validate the coverage and district-week grain shared by V4 gold and serving."""

import pandas as pd

from denguekay.config.paths import UBIGEO_CATALOG
from denguekay.data.processing.epi_sala import load_ubigeo_catalog
from denguekay.data.validation.integrated_expectations import validate_complete, validate_geography


def validate_confirmed_panel(panel, coverage):
    if coverage is None:
        raise ValueError("Missing epidemiological coverage for the confirmed panel")
    validate_complete(panel, coverage)
    validate_geography(panel)
    codes = load_ubigeo_catalog(UBIGEO_CATALOG).ubigeo
    weeks = pd.to_datetime(panel.semana_inicio)
    if (set(panel.ubigeo) != set(codes) or panel.duplicated(["ubigeo", "semana_inicio"]).any()
            or not panel.groupby("semana_inicio").size().eq(len(codes)).all()
            or set(weeks) != set(pd.date_range(weeks.min(), weeks.max(), freq="W-SUN"))):
        raise ValueError("Incomplete confirmed district-week panel")
