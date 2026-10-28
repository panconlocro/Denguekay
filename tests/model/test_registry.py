"""The model registry cards agree with the package (configurations, fingerprints, states, files)."""

import json
import unittest

import yaml

from denguekay.config.paths import COMPACT_METRICS, CONFIG, MODEL_REGISTRY, ROOT
from denguekay.model import frozen_configs as fc
from denguekay.model import registry


class TestRegistry(unittest.TestCase):
    def test_every_version_has_its_cards_and_the_changelog_exists(self):
        self.assertTrue((MODEL_REGISTRY / "CHANGELOG.md").exists())
        for version in registry.VERSIONS:
            with self.subTest(version=version):
                self.assertTrue((MODEL_REGISTRY / version / "ficha.md").exists())
                self.assertEqual(registry.card(version)["version"], version)

    def test_states(self):
        states = {v: registry.card(v)["estado"] for v in registry.VERSIONS}
        self.assertEqual(states, {"v0": "servida", "v1": "reemplazada", "v2": "vigente"})
        self.assertEqual(registry.CURRENT, "v2")
        self.assertEqual(registry.SERVED, "v0")
        self.assertEqual(registry.card("v1")["reemplazada_por"], "v2")
        self.assertEqual(registry.card("v2")["reemplaza_a"], "v1")

    def test_frozen_configurations_load_from_the_package(self):
        self.assertIs(registry.configuration("v1"), fc.CONFIG_2026_V1)
        self.assertIs(registry.configuration("v2"), fc.CONFIG_2026)
        with self.assertRaises(ValueError):
            registry.configuration("v0")
        with self.assertRaises(ValueError):
            registry.card("v9")

    def test_package_history_points_to_the_cards(self):
        for name, version in (("V1", "v1"), ("V2", "v2")):
            with self.subTest(version=version):
                self.assertEqual(fc.HISTORY[name]["ficha"], f"models/registry/{version}/ficha.md")
                self.assertTrue((ROOT / fc.HISTORY[name]["ficha"]).exists())

    def test_fingerprints_match_the_package(self):
        for name, version in (("V1", "v1"), ("V2", "v2")):
            with self.subTest(version=version):
                fingerprints = registry.card(version)["huellas"]
                self.assertEqual(fingerprints["historica"]["sha256"], fc.HISTORICAL_FINGERPRINTS[name]["sha256"])
                self.assertEqual(fingerprints["historica"]["commit"], fc.HISTORICAL_FINGERPRINTS[name]["commit"])
                self.assertEqual(fingerprints["historica"]["definicion"], fc.HISTORICAL_FINGERPRINT_DEFINITION)
                self.assertEqual(fingerprints["comportamiento"]["definicion"], fc.FINGERPRINT_DEFINITION)
                self.assertEqual(fingerprints["comportamiento"]["semilla"], fc.DEPLOYMENT_SEED)
                self.assertEqual(fingerprints["comportamiento"]["por_entorno"],
                                 {setup: values[name] for setup, values in fc.REFERENCE_FINGERPRINTS.items()})

    def test_v0_matches_serving(self):
        card = registry.card("v0")
        serving = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))["serving"]
        self.assertEqual(card["configuracion"]["variantes"], serving["variantes"])
        self.assertEqual(ROOT / card["metricas_seleccion"]["archivo"], COMPACT_METRICS)
        metrics = json.loads(COMPACT_METRICS.read_text(encoding="utf-8"))
        self.assertEqual(card["gold"]["sha256_manifest"], metrics["sha256_manifest_gold"])
        for h in ("2", "4"):
            self.assertEqual(card["gold"][h]["sha256"], metrics["horizontes"][h]["sha256_gold"])
            self.assertEqual(card["gold"][h]["archivo"], metrics["horizontes"][h]["archivo_gold"])
            self.assertEqual(metrics["horizontes"][h]["seleccion_2022_2023"], serving["variantes"])


if __name__ == "__main__":
    unittest.main()
