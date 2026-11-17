"""Gold of earlier versions: the column sets and horizons ``generate_gold`` can persist."""

import unittest

from denguekay.features import gold
from denguekay.features.outbreak_label import SeasonalOutbreakConfig


class TestColumnSets(unittest.TestCase):
    def test_v2_is_v3_without_d3(self):
        v3 = gold.persisted_columns(2)
        v2 = gold.persisted_columns(2, columns="v2")
        self.assertEqual((len(v2), len(v3)), (20, 24))
        self.assertEqual([c for c in v3 if c not in v2], list(gold.cl.D3_COLUMNS))
        self.assertEqual([c for c in v3 if c in v2], v2)

    def test_default_is_the_current_gold(self):
        self.assertEqual(gold.HORIZONS, (2,))
        self.assertEqual(gold.persisted_columns(2), gold.persisted_columns(2, columns="v3"))

    def test_horizon_must_be_one_of_the_persisted(self):
        with self.assertRaises(ValueError):
            gold.persisted_columns(4)
        self.assertIn("casos_lag_4", gold.persisted_columns(4, horizons=(2, 4)))

    def test_unknown_column_set_is_rejected(self):
        with self.assertRaises(ValueError):
            gold.persisted_columns(2, columns="candidatas")   # the candidates are not a persisted schema
        with self.assertRaises(ValueError):
            gold.generate_gold(outbreak=SeasonalOutbreakConfig(multiplicador=1.5), columns="v9")

    def test_candidate_horizons_are_validated(self):
        with self.assertRaises(ValueError):
            gold.generate_gold(outbreak=SeasonalOutbreakConfig(multiplicador=1.5), columns="candidatas",
                               horizons=(2, 9))


if __name__ == "__main__":
    unittest.main()
