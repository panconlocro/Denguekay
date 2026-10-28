"""Regla preregistrada del complemento de clima (comparación 20 del encargo de FE)."""

import unittest

import pandas as pd

from src.modeling import complemento_clima as cc

BLOQUES = ("temporada_2022", "temporada_2023")


def _ev(valores):
    """{semilla: {"metricas": df}} con razón MAE y RMSE por (h, bloque); ``valores[(h, bloque)] = (mae, rmse)``."""
    salida = {}
    for i, s in enumerate((17, 29, 41)):
        filas = [{"horizonte": h, "bloque": b, "razon_mae": mae + 0.01 * i, "razon_rmse": rmse + 0.01 * i}
                 for (h, b), (mae, rmse) in valores.items()]
        salida[s] = {"metricas": pd.DataFrame(filas)}
    return salida


class TestReglaConteo(unittest.TestCase):
    def _caso(self, candidata):
        ref = {(h, b): (1.0, 1.0) for h in (2, 3, 4) for b in BLOQUES}
        return cc.condicion_conteo(cc.tabla_conteo(_ev(candidata), _ev(ref))).set_index("horizonte")

    def test_mejora_exige_las_dos_razones_en_las_dos_temporadas(self):
        base = {(h, b): (1.0, 1.0) for h in (2, 3, 4) for b in BLOQUES}
        c = self._caso({**base, (2, BLOQUES[0]): (0.9, 0.9), (2, BLOQUES[1]): (0.9, 0.9)})
        self.assertTrue(c.at[2, "mejora_conteo"])
        self.assertFalse(c.at[3, "mejora_conteo"])
        c = self._caso({**base, (2, BLOQUES[0]): (0.9, 0.9), (2, BLOQUES[1]): (0.9, 1.0)})
        self.assertFalse(c.at[2, "mejora_conteo"])

    def test_umbral_estricto_y_empeora_con_una_razon(self):
        base = {(h, b): (1.0, 1.0) for h in (2, 3, 4) for b in BLOQUES}
        # Rango entre semillas = 0,02: bajar exactamente 0,02 no cuenta (estricta).
        c = self._caso({**base, (3, BLOQUES[0]): (0.98, 0.98), (3, BLOQUES[1]): (0.98, 0.98)})
        self.assertFalse(c.at[3, "mejora_conteo"])
        c = self._caso({**base, (4, BLOQUES[0]): (1.0, 1.1), (4, BLOQUES[1]): (1.0, 1.1)})
        self.assertTrue(c.at[4, "empeora_conteo"])
        c = self._caso({**base, (4, BLOQUES[0]): (1.0, 1.1), (4, BLOQUES[1]): (1.0, 1.0)})
        self.assertFalse(c.at[4, "empeora_conteo"])

    def test_decision(self):
        conteo = pd.DataFrame({"horizonte": [2, 3, 4], "mejora_conteo": [True, False, False],
                               "empeora_conteo": [False, False, False]})
        empate = pd.DataFrame({"horizonte": [2, 3, 4], "veredicto": ["empate", "compensa (empate)", "gana"]})
        self.assertEqual(cc.decidir(conteo, empate)["adoptada"], "F+A3")
        pierde = empate.assign(veredicto=["empate", "pierde", "empate"])
        d = cc.decidir(conteo, pierde)
        self.assertEqual((d["adoptada"], d["horizontes_pierde_alerta"]), ("F", [3]))
        self.assertEqual(cc.decidir(conteo.assign(empeora_conteo=[False, True, False]), empate)["adoptada"], "F")
        self.assertEqual(cc.decidir(conteo.assign(mejora_conteo=False), empate)["adoptada"], "F")

    def test_diagnostico_celda(self):
        datos = pd.DataFrame({"horizonte": 4, "bloque": "temporada_2022", "brote": [1, 1, 0, 0],
                              "probabilidad_calibrada": [0.45, 0.6, 0.1, 0.55], "probabilidad_brote": [0.2, 0.3, 0.1, 0.2]})
        otra = datos.assign(bloque="temporada_2023")
        d = cc.diagnostico_celda({17: {"datos": pd.concat([datos, otra])}}, 4, "temporada_2022").iloc[0]
        self.assertEqual((d.semanas, d.semanas_brote, d.brote_en_banda, d.brote_con_alerta), (4, 2, 1, 1))
        self.assertAlmostEqual(d.prevalencia, 0.5)
        self.assertAlmostEqual(d.probabilidad_calibrada_media, 0.425)
        self.assertAlmostEqual(d.brier_calibrado, (0.55 ** 2 + 0.4 ** 2 + 0.1 ** 2 + 0.55 ** 2) / 4)
        self.assertAlmostEqual(d.f1_050, 0.5)

    def test_columnas_a3(self):
        self.assertEqual(cc.COLUMNAS_A3, ["hum_rel_media_media5_h2", "precip_total_mm_media5_h2"])


if __name__ == "__main__":
    unittest.main()
