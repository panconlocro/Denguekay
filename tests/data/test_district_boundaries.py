import json
import tempfile
import unittest
from pathlib import Path

from denguekay.data.ingestion import district_boundaries as db

PACKAGE = {"license_id": "cc-by-igo", "license_title": "CC BY-IGO", "dataset_source": "IGN",
           "resources": [{"name": db.RESOURCE_NAME, "url": "https://x/y.zip", "last_modified": "2026-01-26"}]}


class TestDistrictBoundaries(unittest.TestCase):
    def test_resource_info_stops_if_the_licence_changed(self):
        self.assertEqual(db.resource_info(PACKAGE)["url"], "https://x/y.zip")
        with self.assertRaises(RuntimeError):
            db.resource_info({**PACKAGE, "license_id": "other"})

    def test_a_waf_challenge_or_an_empty_body_is_refused(self):
        with self.assertRaises(RuntimeError):
            db.check_archive_response(202, {"x-amzn-waf-action": "challenge"}, b"")
        with self.assertRaises(RuntimeError):
            db.check_archive_response(200, {}, b"<html>")
        db.check_archive_response(200, {}, b"PK...")

    def test_local_copy_is_saved_once_with_its_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in" / db.RESOURCE_NAME
            src.parent.mkdir()
            src.write_bytes(b"PKdata")
            info = db.resource_info(PACKAGE)
            path, manifest = db.register_local_copy(src, info, Path(tmp) / "bronze")
            self.assertEqual(path.read_bytes(), src.read_bytes())
            meta = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(meta["bytes"], 8)
            self.assertEqual(meta["licencia_id"], "cc-by-igo")
            with self.assertRaises(FileExistsError):
                db.register_local_copy(src, info, Path(tmp) / "bronze")


    def test_pcode_maps_to_a_six_digit_string_ubigeo(self):
        import pandas as pd

        self.assertEqual(db.pcode_to_ubigeo(pd.Series(["PE200115", "PE010101"])).tolist(), ["200115", "010101"])
        with self.assertRaises(ValueError):
            db.pcode_to_ubigeo(pd.Series(["PE2001"]))

    def test_compact_key_ignores_spaces_accents_and_the_s_suffix(self):
        self.assertEqual(db.compact_key("El Carmendela Frontera"), db.compact_key("El Carmen de la Frontera"))
        self.assertEqual(db.compact_key("Salitral_s"), db.compact_key("Salitral"))
        self.assertEqual(db.compact_key("Veintiséis de Octubre"), "VEINTISEISDEOCTUBRE")

    def _piura(self, n):
        import geopandas as gpd
        import pandas as pd
        from shapely.geometry import box

        ubigeos = [f"2001{i:02d}" for i in range(1, n + 1)]
        gdf = gpd.GeoDataFrame({"ubigeo": ubigeos, "adm3_pcode": ["PE" + u for u in ubigeos],
                                "adm3_name": [f"D{i}" for i in range(1, n + 1)], "area_sqkm": 1.0},
                               geometry=[box(-80 - 0.01 * i, -5, -79.99 - 0.01 * i, -4.99) for i in range(n)],
                               crs="EPSG:4326")
        catalog = pd.DataFrame({"provincia": "Piura", "distrito": [f"D{i}" for i in range(1, n + 1)], "ubigeo": ubigeos})
        return gdf, catalog

    def test_verify_stops_if_a_district_is_missing(self):
        gdf, catalog = self._piura(db.EXPECTED_DISTRICTS)
        report = db.verify_districts(gdf, catalog)
        self.assertTrue(report["nombre_coincide"].all())
        self.assertTrue((report["area_km2"] > 1).all())
        with self.assertRaises(ValueError):
            db.verify_districts(gdf.iloc[1:], catalog)

    def test_reference_keeps_ubigeo_as_string_and_is_not_overwritten(self):
        import geopandas as gpd

        gdf, catalog = self._piura(db.EXPECTED_DISTRICTS)
        report = db.verify_districts(gdf, catalog)
        with tempfile.TemporaryDirectory() as tmp:
            path = db.write_reference(report, Path(tmp) / "limites.geojson")
            back = gpd.read_file(path)
            self.assertEqual(back["ubigeo"].tolist(), catalog["ubigeo"].tolist())
            with self.assertRaises(FileExistsError):
                db.write_reference(report, path)


if __name__ == "__main__":
    unittest.main()
