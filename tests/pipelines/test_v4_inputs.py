"""The V4 silver reads the coordinates the way the frozen Release files were written."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import pandas as pd

from denguekay.pipelines import v4_inputs


class TestDistrictCoords(unittest.TestCase):
    def test_arenal_keeps_the_latitude_of_the_release(self):
        text = "provincia,distrito,lat,lon,distrito_key,id_distrito\nPaita,Arenal,-4.8996990381835985,-81.02889919655017,ARENAL,30\n"
        with TemporaryDirectory() as temp:
            path = Path(temp) / "coords.csv"
            path.write_text(text, encoding="utf-8")
            with patch.object(v4_inputs, "DISTRICT_COORDS", path):
                latitude = v4_inputs.read_district_coords().lat.iloc[0]
            exact = pd.read_csv(path, float_precision="round_trip").lat.iloc[0]
        self.assertEqual(repr(float(latitude)), "-4.899699038183599")   # as written in datos_v4.zip
        self.assertNotEqual(latitude, exact)                     # the exact parser would break the ERA5-Land match


if __name__ == "__main__":
    unittest.main()
