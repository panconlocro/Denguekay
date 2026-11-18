"""Source, product and extraction date of the climate sources (HU0002-1)."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from denguekay.data.validation.climate_provenance import CAPTURE_KIND, FREEZE_KIND, climate_sources


def write(path, content=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TestClimateSources(unittest.TestCase):
    def build(self, folder):
        folder = Path(folder)
        write(folder / "enso" / "sstoi_20261103.indices")
        write(folder / "enso" / "sstoi_20261117.indices")
        write(folder / "enso" / "otro.txt")
        write(folder / "ee" / "manifiesto_ee_20261106T120943.json",
              json.dumps({"estado": "completa", "escrito_utc": "2026-11-06T17:09:43+00:00"}))
        write(folder / "final" / "manifiesto_ftp_final_a.json",
              json.dumps({"estado": "completa", "fecha_descarga": "20261108"}))
        write(folder / "final" / "manifiesto_ftp_final_b.json",
              json.dumps({"estado": "completa", "fecha_descarga": "20261117T164911601418Z"}))
        write(folder / "prelim" / "manifiesto_ftp_prelim_a.json",
              json.dumps({"estado": "detenida_429", "fecha_descarga": "20261201"}))
        write(folder / "recent" / "2026-11-10" / "distrito_001.parquet")
        write(folder / "recent" / "2026-11-12" / "distrito_001.parquet")
        write(folder / "cache" / "distrito_001.parquet")
        return {row["fuente"]: row for row in climate_sources(
            enso=folder / "enso", chirps_ee=folder / "ee", chirps_final=folder / "final",
            chirps_prelim=folder / "prelim", era5_recent=folder / "recent",
            historical={"Open-Meteo (caché)": folder / "cache", "ERA5-Land (caché vacía)": folder / "vacia"},
            frozen="2026-11-12")}

    def test_each_source_takes_its_date_from_where_the_pipeline_leaves_it(self):
        with TemporaryDirectory() as directory:
            rows = self.build(directory)
        self.assertEqual(rows["NOAA CPC"]["fecha_extraccion"], "2026-11-17")
        self.assertEqual(rows["NOAA CPC"]["capturas"], 2)
        self.assertEqual(rows["CHIRPS v3 (Earth Engine)"]["fecha_extraccion"], "2026-11-06")
        self.assertEqual(rows["CHIRPS v3 (FTP del CHC)"]["fecha_extraccion"], "2026-11-17")
        self.assertEqual(rows["ERA5-Land (semanas recientes)"]["fecha_extraccion"], "2026-11-12")
        self.assertEqual(rows["NOAA CPC"]["tipo_de_fecha"], CAPTURE_KIND)
        self.assertTrue(all(r["producto"] and r["referencia"] for r in rows.values()))

    def test_a_stopped_download_does_not_count_and_a_source_without_captures_says_so(self):
        with TemporaryDirectory() as directory:
            rows = self.build(directory)
        stopped = rows["CHIRPS v3 preliminar (FTP del CHC)"]
        self.assertEqual((stopped["fecha_extraccion"], stopped["tipo_de_fecha"]), (None, "sin capturas"))

    def test_historical_caches_show_the_freeze_date_marked_as_such(self):
        with TemporaryDirectory() as directory:
            rows = self.build(directory)
        cache = rows["Open-Meteo (caché)"]
        self.assertEqual((cache["fecha_extraccion"], cache["tipo_de_fecha"]), ("2026-11-12", FREEZE_KIND))
        self.assertIn("model/v4", cache["tipo_de_fecha"])
        self.assertEqual(rows["ERA5-Land (caché vacía)"]["tipo_de_fecha"], "sin capturas")


if __name__ == "__main__":
    unittest.main()
