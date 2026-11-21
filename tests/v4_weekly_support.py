"""Synthetic environment of the weekly V4 update: frozen package, temporary SQLite database, no network and no data/.

It reuses the synthetic bundle of ``tests/serving/test_demo_b3_v4.py`` and the assembly of ``TestLivePublication`` in
``tests/serving/test_v4_live.py``. ``LiveCase.batch(cutoff)`` builds the load of the observations up to a cutoff
week; each cutoff has its own hashes so that the loads are not taken for the same one.
"""

from contextlib import ExitStack
from dataclasses import replace
from datetime import date
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import pandas as pd

from backend_support import motor_temporal
from serving.test_demo_b3_v4 import synthetic_bundle
from denguekay.config.paths import CONFIG, UBIGEO_CATALOG
from denguekay.data.calendar import mmwr_epi_week
from denguekay.data.processing.epi_sala import load_ubigeo_catalog
from denguekay.pipelines import v4_weekly
from denguekay.serving import load_data
from denguekay.serving.demo_b3_v4 import prepare_observations
from denguekay.serving.predictors import v4_b3_live as v4
from denguekay.serving.settings import service_settings
from denguekay.serving.storage import LocalStorage

FIRST_CUTOFF = date(2025, 1, 18)   # week 3 of 2025 (id 202503)
NEXT_CUTOFF = date(2025, 1, 25)    # week 4 of 2025 (id 202504)


def week_of(cutoff):
    return int(load_data.week_id(*mmwr_epi_week(pd.Series([pd.Timestamp(cutoff) - pd.Timedelta(days=6)])).iloc[0]))


class LiveCase(unittest.TestCase):
    """Base class: package published in a temporary database, ready to run the weekly update."""

    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        folder = self.root / "model"
        folder.mkdir()
        synthetic_bundle(folder)
        self.districts = load_ubigeo_catalog(UBIGEO_CATALOG).ubigeo.tolist()
        geo = self.root / "geografia.csv"
        pd.DataFrame({"ubigeo": self.districts, "lat": -5.0, "lon": -80.0, "elevacion_dem90": 100}).to_csv(
            geo, index=False)
        package = folder / "paquete.json"
        config = json.loads(package.read_text())
        config["fuentes"] = {"geografia": hashlib.sha256(geo.read_bytes()).hexdigest()}
        package.write_text(json.dumps(config), encoding="utf-8")
        manifest = self.root / "manifest.json"
        manifest.write_text(json.dumps({"paquetes": [{"archivos": [{
            "ruta": package.relative_to(self.root).as_posix(), "sha256": hashlib.sha256(package.read_bytes()).hexdigest(),
        }]}]}), encoding="utf-8")
        self.template, _ = prepare_observations(folder, config, "a" * 64)
        self.motor = motor_temporal(self.root)
        self.addCleanup(self.motor.dispose)
        self.storage = LocalStorage(self.root / "storage")
        self.base = self.root / "actualizacion_semanal"
        self.cfg = service_settings(CONFIG, environ={})
        self.current = self.batch(FIRST_CUTOFF)
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.multiple(v4, V4_FROZEN=folder, V4_DATA_MANIFEST=manifest, V4_GEOGRAPHY=geo,
                                           ROOT=self.root))
        stack.enter_context(patch.object(v4, "prepare_load", side_effect=lambda options: self.current))
        stack.enter_context(patch.object(v4, "source_hashes", side_effect=lambda options: self.current.hashes))
        stack.enter_context(patch("denguekay.serving.publish.log_report", return_value="test"))
        # ``publish`` writes its report under ``models/serving/ejecuciones/<huella>/``: the tests use their own folder.
        stack.enter_context(patch("denguekay.serving.publish.SERVING_RUNS", self.root / "ejecuciones"))
        self.cutoff = week_of(FIRST_CUTOFF)
        self.published = self.cutoff + 2   # the Sala has two provisional weeks more than the cutoff
        self.calls = []

    def batch(self, cutoff):
        weeks = pd.Series(pd.date_range("2019-01-06", cutoff, freq="W-SUN"))
        calendar = mmwr_epi_week(weeks)
        observations = [
            {"ubigeo": u, "id_semana": load_data.week_id(w.anio_epi, w.semana_epi), "casos_dengue": 4,
             "brote": False, "umbral_brote_casos": 4, "casos_solo_confirmados": True,
             "fuente_casos": "sala_situacional", "estado_cobertura": "verificado"}
            for w in calendar.itertuples() for u in self.districts
        ]
        nino = [{"mes": date(2024, 12, 1), "fecha_disponible": date(2025, 1, 10), "anomalia": -0.5}]
        hashes = {**self.template.hashes, "sala_operativa": f"corte-{cutoff.isoformat()}"}
        return replace(self.template, observaciones=observations, fecha_corte_datos=cutoff, nino12=nino,
                       hashes=hashes)

    def steps(self, **changes):
        """Default steps with the data ones replaced; ``self.calls`` records the order and the arguments."""
        def record(name, result=None):
            def step(*args, **kwargs):
                self.calls.append((name, args, kwargs))
                return result() if callable(result) else result
            return step

        values = dict(
            missing_files=lambda: [], ensure_release=record("release", {}), sala=record("sala", {}),
            expected_cutoff=record("corte", lambda: (self.cutoff, self.published, [self.cutoff + 1, self.cutoff + 2])),
            climate=record("clima", {}), captures=lambda: {"sala": {"2025": "2025_prueba"}},
            code_fingerprint=lambda: "f" * 64, package_version=lambda: "0.0.0-prueba")
        values.update(changes)
        return v4_weekly.Steps(**values)

    def run_weekly(self, options=None, **changes):
        return v4_weekly.run(options or v4_weekly.Options(inicial=True), motor=self.motor, cfg=self.cfg,
                             storage=self.storage, steps=self.steps(**changes), base=self.base)
