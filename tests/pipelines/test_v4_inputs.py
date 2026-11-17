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
        old_pandas = tuple(int(part) for part in pd.__version__.split(".")[:2]) < (3, 1)
        with TemporaryDirectory() as temp:
            path = Path(temp) / "coords.csv"
            path.write_text(text, encoding="utf-8")
            with patch.object(v4_inputs, "DISTRICT_COORDS", path):
                coords = v4_inputs.read_district_coords()
            default = pd.read_csv(path)
            exact = pd.read_csv(path, float_precision="round_trip") if old_pandas else None
        pd.testing.assert_frame_equal(coords, default)      # always the default parser of the installed pandas
        if old_pandas:
            # pandas 3.0.x (constraints.txt): the default parser gives the latitude written in datos_v4.zip, not the
            # exact one. From 3.1 the parser is always exact, so there is nothing to tell apart.
            self.assertEqual(repr(float(coords.lat.iloc[0])), "-4.899699038183599")
            self.assertNotEqual(coords.lat.iloc[0], exact.lat.iloc[0])


if __name__ == "__main__":
    unittest.main()
