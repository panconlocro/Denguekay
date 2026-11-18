"""District polygons (HU0014-1): reading, simplification, loading and the centroid fallback."""

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pandas as pd
from sqlalchemy import select

from backend_support import motor_temporal
from denguekay.config.paths import DISTRICT_BOUNDARIES, DISTRICT_COORDS, UBIGEO_CATALOG
from denguekay.data.processing.epi_sala import load_ubigeo_catalog
from denguekay.db.models import District, Province
from denguekay.db.session import transaction, upsert
from denguekay.serving import geometries
from denguekay.serving.load_data import prepare_districts

SQUARE = [[-80.0, -5.0], [-80.0, -5.1], [-80.1, -5.1], [-80.1, -5.0], [-80.0, -5.0]]


def area(ring):
    """Absolute shoelace area in square degrees."""
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:]))) / 2


def size(geometry):
    return len(json.dumps(geometry, separators=(",", ":")))


class TestSimplification(unittest.TestCase):
    def test_collinear_points_go_and_corners_stay(self):
        ring = [[-80.0, -5.0], [-80.0, -5.05], [-80.0, -5.1], [-80.1, -5.1], [-80.1, -5.0], [-80.0, -5.0]]
        simplified = geometries.simplify_ring(ring)
        self.assertEqual(len(simplified), 5)
        self.assertEqual(simplified[0], simplified[-1])
        self.assertNotIn((-80.0, -5.05), simplified)

    def test_a_deviation_above_the_tolerance_is_kept(self):
        ring = [[-80.0, -5.0], [-80.05, -4.99], [-80.1, -5.0], [-80.1, -5.1], [-80.0, -5.1], [-80.0, -5.0]]
        self.assertIn((-80.05, -4.99), geometries.simplify_ring(ring))

    def test_rejects_unclosed_rings_other_types_and_coordinates_outside_piura(self):
        with self.assertRaisesRegex(ValueError, "no cerrado"):
            geometries.simplify_geometry({"type": "Polygon", "coordinates": [SQUARE[:-1]]}, "200101")
        with self.assertRaisesRegex(ValueError, "Polygon o MultiPolygon"):
            geometries.simplify_geometry({"type": "Point", "coordinates": [-80.0, -5.0]}, "200101")
        outside = [[0.0, 0.0], [0.0, 1.0], [1.0, 1.0], [1.0, 0.0], [0.0, 0.0]]
        with self.assertRaisesRegex(ValueError, "fuera de Piura"):
            geometries.simplify_geometry({"type": "Polygon", "coordinates": [outside]}, "200101")

    def test_multipolygon_keeps_its_structure(self):
        geometry = {"type": "MultiPolygon", "coordinates": [[SQUARE], [[[x - 0.5, y] for x, y in SQUARE]]]}
        result = geometries.simplify_geometry(geometry, "200101")
        self.assertEqual((result["type"], len(result["coordinates"]), len(result["coordinates"][0][0])),
                         ("MultiPolygon", 2, 5))


class TestVersionedBoundaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.found = geometries.read_boundaries()
        cls.collection = json.loads(DISTRICT_BOUNDARIES.read_text(encoding="utf-8"))
        cls.original = {f["properties"]["ubigeo"]: f["geometry"] for f in cls.collection["features"]}

    def test_65_districts_of_the_catalog_with_string_ubigeo(self):
        catalog = load_ubigeo_catalog(UBIGEO_CATALOG)
        self.assertEqual(set(self.found), set(catalog.ubigeo))
        self.assertEqual(len(self.found), 65)
        self.assertTrue(all(isinstance(u, str) and len(u) == 6 for u in self.found))
        self.assertTrue(all(g["type"] in geometries.GEOMETRY_TYPES for g in self.found.values()))

    def test_it_is_a_light_version_of_the_same_outlines(self):
        self.assertLess(sum(size(g) for g in self.found.values()), 400_000)   # about 0.2 MB against 2.4 MB
        for ubigeo in sorted(self.found)[::22]:
            before = area(self.original[ubigeo]["coordinates"][0])
            after = area(self.found[ubigeo]["coordinates"][0])
            self.assertAlmostEqual(after / before, 1.0, delta=0.01, msg=ubigeo)

    def test_rejects_a_repeated_or_numeric_ubigeo(self):
        with TemporaryDirectory() as directory:
            repeated = deepcopy(self.collection)
            repeated["features"].append(deepcopy(repeated["features"][0]))
            numeric = deepcopy(self.collection)
            numeric["features"][0]["properties"]["ubigeo"] = 200101
            for broken, message in ((repeated, "repetido"), (numeric, "inválido")):
                path = Path(directory) / "limites.geojson"
                path.write_text(json.dumps(broken), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, message):
                    geometries.read_boundaries(path)


class TestLoading(unittest.TestCase):
    @staticmethod
    def prepared(geometry_by_ubigeo):
        catalog = load_ubigeo_catalog(UBIGEO_CATALOG)
        return prepare_districts(catalog, pd.read_csv(DISTRICT_COORDS), {}, geometry_by_ubigeo)

    def test_without_geometries_the_records_have_no_geometria_key(self):
        _, districts = self.prepared(None)
        self.assertTrue(all("geometria" not in d for d in districts))

    def test_geometries_are_stored_and_a_later_load_without_them_keeps_them(self):
        provinces, districts = self.prepared({"200101": {"type": "Polygon", "coordinates": [SQUARE]}})
        self.assertEqual(sum(d["geometria"] is not None for d in districts), 1)
        with TemporaryDirectory() as directory:
            motor = motor_temporal(Path(directory))
            try:
                with transaction(motor) as session:
                    upsert(session, Province.__table__, provinces, ["ubigeo_provincia"])
                    upsert(session, District.__table__, districts, ["ubigeo"])
                    self.assertEqual(session.get(District, "200101").geometria["type"], "Polygon")
                    self.assertIsNone(session.get(District, "200104").geometria)
                    _, legacy = self.prepared(None)   # a load that carries no geometry must not erase it
                    upsert(session, District.__table__, legacy, ["ubigeo"])
                    session.expire_all()
                    self.assertEqual(session.get(District, "200101").geometria["coordinates"][0][0], [-80.0, -5.0])
                    self.assertEqual(len(session.scalars(select(District)).all()), 65)
            finally:
                motor.dispose()

    def test_boundaries_outside_the_catalog_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "no están en el catálogo"):
            self.prepared({"999999": {"type": "Polygon", "coordinates": [SQUARE]}})


if __name__ == "__main__":
    unittest.main()
