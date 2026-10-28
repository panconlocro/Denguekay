"""El preregistro de la fase 1 queda fijo: ids, columnas y número de comparaciones."""

import unittest

from src.modeling import preregistro_fe as pr
from src.modeling.contrato_xgboost import familias_predictoras
from src.modeling.diagnostico_inicios import ETIQUETAS


class TestPreregistro(unittest.TestCase):
    def test_ids_y_comparaciones(self):
        self.assertEqual([v["id"] for v in pr.VARIANTES], ["A1", "A2", "A3", "A4", "A5", "A6", "A7",
                                                           "B1", "B2", "B3", "B4", "B5"])
        c = pr.comparaciones()
        self.assertEqual((c["bloque_A"], c["bloque_B"], c["combinada"], c["total"]), (7, 7, 2, 16))
        self.assertEqual((c["fase3_hiperparametros"], c["fase4"], c["complemento_clima"], c["total_encargo"]),
                         (1, 2, 1, 20))

    def test_columnas_de_gold_existen_en_el_contrato(self):
        gold = {c for cols in familias_predictoras(2).values() for c in cols}
        for v in pr.VARIANTES:
            if v["bloque"] == "A" and v["id"] != "A7":
                with self.subTest(v["id"]):
                    self.assertTrue(set(v["columnas"]) <= gold)

    def test_variables_nuevas_diagnosticadas_tienen_etiqueta(self):
        for v in pr.VARIANTES:
            if v["id"] in ("B1", "B2", "B3"):
                with self.subTest(v["id"]):
                    self.assertTrue(set(v["columnas"]) <= set(ETIQUETAS))

    def test_sin_columnas_repetidas_entre_variantes(self):
        todas = [c for v in pr.VARIANTES for c in v["columnas"]]
        self.assertEqual(len(todas), len(set(todas)))


if __name__ == "__main__":
    unittest.main()
