"""Regla estacional parametrizada sin años futuros ni ceros inventados en salida."""

import unittest

import pandas as pd

from src.modeling.etiqueta_brote import etiquetar_brote_estacional


class EtiquetaBroteTests(unittest.TestCase):
    def setUp(self):
        self.historia = pd.DataFrame([
            {"ubigeo": u, "anio": y, "semana": 1, "casos_Dengue": v}
            for u, valores in (("200101", [0, 0, 0, 0, 0]),
                               ("200102", [1, 2, 3, 4, 5]))
            for y, v in zip(range(2012, 2017), valores)
        ])
        self.panel = pd.DataFrame([
            {"ubigeo": "200101", "anio": 2017, "semana": 1, "casos_Dengue": 1},
            {"ubigeo": "200102", "anio": 2017, "semana": 1, "casos_Dengue": 6},
            {"ubigeo": "200101", "anio": 2018, "semana": 1, "casos_Dengue": 2},
            {"ubigeo": "200102", "anio": 2018, "semana": 1, "casos_Dengue": 7},
        ])

    def test_media_desviacion_y_piso(self):
        a = etiquetar_brote_estacional(self.panel, self.historia, multiplicador=1.5)
        b = etiquetar_brote_estacional(self.panel, self.historia, multiplicador=2)
        self.assertEqual(a.loc[0, "umbral_brote_casos"], 0)
        self.assertEqual(a.loc[0, "brote"], 1)
        self.assertGreater(a.loc[1, "umbral_brote_casos"], 5)
        self.assertLess(a.loc[1, "umbral_brote_casos"], 6)
        self.assertEqual(a.loc[1, "brote"], 1)
        self.assertEqual(b.loc[1, "brote"], 0)
        piso = etiquetar_brote_estacional(self.panel, self.historia, multiplicador=1.5, minimo_casos=2)
        self.assertEqual(piso.loc[0, "brote"], 0)
        self.assertEqual(piso.loc[2, "brote"], 1)
        self.assertEqual(len(a), len(self.panel))
        self.assertFalse(a.duplicated(["ubigeo", "anio", "semana"]).any())

    def test_solo_anos_anteriores_y_misma_semana(self):
        antes = etiquetar_brote_estacional(self.panel, self.historia, multiplicador=2)
        cambiado = self.panel.copy()
        cambiado.loc[cambiado.anio.eq(2018), "casos_Dengue"] += 1000
        despues = etiquetar_brote_estacional(cambiado, self.historia, multiplicador=2)
        pd.testing.assert_frame_equal(antes.iloc[:2], despues.iloc[:2])
        # La referencia de 2018 sí incorpora 2017 y descarta 2012.
        self.assertAlmostEqual(antes.loc[2, "umbral_brote_casos"], 0.2 + 2 * (0.2 ** 0.5))
        self.assertGreater(antes.loc[3, "umbral_brote_casos"], antes.loc[1, "umbral_brote_casos"])

    def test_semana_53_comparte_referencia_52(self):
        historia = self.historia.copy()
        historia["semana"] = 52
        historia = pd.concat([historia, pd.DataFrame([{"ubigeo": "200101", "anio": 2016,
            "semana": 53, "casos_Dengue": 3}])], ignore_index=True)
        panel = self.panel.iloc[:2].copy()
        panel["semana"] = 53
        salida = etiquetar_brote_estacional(panel, historia, multiplicador=2)
        self.assertGreater(salida.loc[0, "umbral_brote_casos"], 0)
        self.assertEqual(salida.loc[0, "brote"], 0)

    def test_historia_o_casos_invalidos_fallan(self):
        with self.assertRaisesRegex(ValueError, "Faltan años"):
            etiquetar_brote_estacional(self.panel, self.historia[self.historia.anio.ne(2012)], multiplicador=2)
        with self.assertRaisesRegex(ValueError, "llaves duplicadas"):
            etiquetar_brote_estacional(self.panel, pd.concat([self.historia, self.historia.iloc[[0]]]), multiplicador=2)
        malo = self.panel.copy()
        malo.loc[0, "casos_Dengue"] = -1
        with self.assertRaisesRegex(ValueError, "casos inválidos"):
            etiquetar_brote_estacional(malo, self.historia, multiplicador=2)


if __name__ == "__main__":
    unittest.main()
