"""Check the operational B3 vector against the frozen Release at the training cutoff."""

from pathlib import Path
from sqlite3 import SQLITE_LIMIT_VARIABLE_NUMBER
from tempfile import TemporaryDirectory
import json
import os
import unittest

import pandas as pd

from backend_support import motor_temporal
from denguekay.config.paths import V4_FROZEN, V4_STUDY_MANIFEST
from denguekay.data.ingestion.release_bundles import sha256_file
from denguekay.data.processing.district_locations import read_v4_era5
from denguekay.db.models import EpiWeek
from denguekay.db.session import transaction
from denguekay.features.b3 import GEO, NINO, WEATHER
from denguekay.features.gold_v4 import climate_table, input_paths, read_csv
from denguekay.serving.inputs import build_inputs
from denguekay.serving.load_data import persist_load
from denguekay.serving.predictors.v4_b3_live import Predictor, _geography
from denguekay.serving.v4_load import prepare_load


EXACT = ["hist_lag_a", "hist_lag_b", "hist_media_4", "hist_semanas_pos_4", "propia_semanas_desde_ultimo_caso", *GEO]


@unittest.skipUnless(os.getenv("DENGUEKAY_TEST_V4_RELEASE") == "1", "Requires the verified V4 Release bundles")
class TestV4ReleaseEquivalence(unittest.TestCase):
    def test_database_and_gold_climate_match_the_frozen_origin(self):
        spec = json.loads(V4_STUDY_MANIFEST.read_bytes())
        snapshot = V4_FROZEN / "origen.csv"
        self.assertEqual(sha256_file(snapshot), spec["archivos"][snapshot.name])
        frozen = read_csv(snapshot).set_index("ubigeo").sort_index()
        release = input_paths(release=True)
        predictor = Predictor.__new__(Predictor)
        predictor.columns = spec["columnas"]["b3_obs"]
        predictor.geography = _geography(release.geography.read_bytes())
        batch = prepare_load({"perfil_datos": "release"})
        self.assertEqual(batch.fecha_corte_datos.isoformat(), spec["corte"])

        with TemporaryDirectory() as directory:
            engine = motor_temporal(Path(directory))
            try:
                with transaction(engine) as session:
                    session.connection().connection.driver_connection.setlimit(SQLITE_LIMIT_VARIABLE_NUMBER, 32_766)
                    load = persist_load(session, batch)
                    cutoff = session.get(EpiWeek, load["id_semana_corte"])
                    inputs = build_inputs(session, cutoff, predictor.required_inputs)
                    live, missing = predictor.vectors(inputs, cutoff)
            finally:
                engine.dispose()

        self.assertEqual(missing, {})
        self.assertEqual(len(live), 65)
        live = live.rename(columns={h: f"umbral_h{h}" for h in spec["horizontes"]}).sort_index()
        pd.testing.assert_frame_equal(live[EXACT], frozen[EXACT], check_dtype=False, check_exact=True)
        approximate = frozen.columns.difference(EXACT, sort=False)
        pd.testing.assert_frame_equal(live[approximate], frozen[approximate], check_dtype=False, rtol=0, atol=1e-12)

        origins = pd.DataFrame({"ubigeo": frozen.index, "origen_cierre": pd.Timestamp(spec["corte"])})
        climate = climate_table(read_v4_era5(release.era5), read_csv(release.chirps, ("semana_inicio", "fecha_disponible")),
                                read_csv(release.enso, ("fecha_disponible",)), origins).set_axis(frozen.index)
        climate_columns = [name for _, name in WEATHER.values()] + [NINO]
        pd.testing.assert_frame_equal(climate[climate_columns], live[climate_columns], rtol=0, atol=1e-12)
