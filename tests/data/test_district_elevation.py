"""Check district coordinate reconciliation and replay of a raw response."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from denguekay.data.ingestion.district_elevation import district_points, elevation_reference


class TestDistrictElevation(unittest.TestCase):
    def test_repository_coordinates_reconcile_to_all_ubigeos(self):
        points = district_points()
        self.assertEqual(len(points), 65)
        self.assertIn("200608", set(points.ubigeo))
        self.assertTrue(points.ubigeo.str.fullmatch(r"\d{6}").all())

    def test_replay_rejects_tampered_elevations(self):
        points = district_points()
        response = Mock(content=('{"elevation":[' + ','.join(['50'] * len(points)) + ']}').encode())
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            output = folder / "reference.csv"
            with patch("denguekay.data.ingestion.district_elevation.requests.get", return_value=response) as get:
                online = elevation_reference(folder=folder, output=output)
                offline = elevation_reference(offline=True, folder=folder, output=output)
                self.assertTrue(online.equals(offline))
                self.assertEqual(get.call_count, 1)
            next(p for p in folder.glob("*.json") if not p.name.endswith(".request.json")).write_bytes(b"{}")
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                elevation_reference(offline=True, folder=folder, output=output)
