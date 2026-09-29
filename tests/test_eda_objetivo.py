"""Tests de src/eda/objetivo.py con datos sintéticos (no dependen de data/)."""

import unittest

import pandas as pd

from src.eda.objetivo import (
    brote_aumento_sostenido, brote_canal_endemico, brote_percentil_distrito, brote_umbral_tasa,
    curva_concentracion, marcar_arranque, rachas, resumen_definicion, sin_marca_previa, umbral_canal_endemico,
    unidades_para_fraccion,
)


def panel(casos, ubigeo="200101", anio=2017, poblacion=100_000):
    fechas = pd.date_range("2017-01-01", periods=len(casos), freq="7D")
    return pd.DataFrame({"ubigeo": ubigeo, "anio": anio, "semana": range(1, len(casos) + 1),
                         "semana_inicio": fechas, "casos_Dengue": casos, "poblacion": poblacion})


class ConcentracionTests(unittest.TestCase):
    def test_unidades_para_fraccion(self):
        v = pd.Series([50, 30, 10, 10])
        self.assertEqual(unidades_para_fraccion(v, 0.5), 1)
        self.assertEqual(unidades_para_fraccion(v, 0.8), 2)
        self.assertAlmostEqual(curva_concentracion(v)["prop_acumulada"].iloc[-1], 1.0)


class RachasTests(unittest.TestCase):
    def test_rachas_por_distrito(self):
        a = panel([0, 1, 1, 0, 1]).assign(m=lambda d: d["casos_Dengue"] > 0)
        b = panel([1, 1, 1, 1, 0], ubigeo="200102").assign(m=lambda d: d["casos_Dengue"] > 0)
        ep = rachas(pd.concat([a, b], ignore_index=True), "m")
        self.assertEqual(ep.groupby("ubigeo")["duracion"].apply(list).to_dict(),
                         {"200101": [2, 1], "200102": [4]})


class DefinicionesTests(unittest.TestCase):
    def test_umbral_tasa(self):
        df = panel([0, 5, 10, 20])  # población 100 000 -> tasa = casos
        self.assertEqual(brote_umbral_tasa(df, 10).tolist(), [False, False, True, True])

    def test_percentil_exige_al_menos_un_caso(self):
        df = panel([0] * 9 + [3])
        self.assertEqual(int(brote_percentil_distrito(df, 0.9).sum()), 1)
        self.assertEqual(int(brote_percentil_distrito(panel([0] * 10), 0.9).sum()), 0)

    def test_aumento_sostenido_exige_k_semanas(self):
        base = [1] * 8
        df = panel(base + [10, 30, 80, 1])  # tres semanas seguidas >= 2x la media previa
        m = brote_aumento_sostenido(df, factor=2, ventana=8, k=3, minimo=5)
        self.assertEqual(m.tolist(), [False] * 8 + [True, True, True, False])
        corto = panel(base + [10, 1, 1, 1])
        self.assertEqual(int(brote_aumento_sostenido(corto, k=3).sum()), 0)

    def test_canal_endemico_usa_solo_anios_previos(self):
        hist = pd.DataFrame({"ubigeo": "200101", "anio": [2012, 2013, 2014, 2015, 2016],
                             "semana": 1, "casos_Dengue": [2, 4, 6, 8, 10]})
        df = panel([9, 0]).assign(semana=[1, 2])
        m = brote_canal_endemico(df, hist, anios_previos=5)
        self.assertEqual(m.tolist(), [True, False])  # Q3 de 2,4,6,8,10 = 8

    def test_canal_endemico_usa_anios_previos_del_panel(self):
        # Historia 2012-2016 en cero; el panel 2017-2021 tiene 10 casos en la semana 1.
        hist = pd.DataFrame({"ubigeo": "200101", "anio": range(2012, 2017), "semana": 1, "casos_Dengue": 0})
        df = pd.concat([panel([10]).assign(anio=a, semana_inicio=pd.Timestamp(f"{a}-01-01")) for a in range(2017, 2023)],
                       ignore_index=True)
        u = umbral_canal_endemico(df, hist, anios_previos=5)
        # 2017: Q3 de cinco ceros = 0; 2022: Q3 de cinco años con 10 = 10 -> ya no es brote
        self.assertEqual((u.iloc[0], u.iloc[-1]), (0.0, 10.0))
        # 2019: Q3 de [0, 0, 0, 10, 10] = 10 -> 10 casos ya no superan el canal
        self.assertEqual(brote_canal_endemico(df, hist).tolist(), [True, True, False, False, False, False])

    def test_canal_endemico_semana_53_se_compara_con_52(self):
        hist = pd.DataFrame({"ubigeo": "200101", "anio": range(2015, 2020), "semana": 52, "casos_Dengue": 4})
        df = panel([5]).assign(anio=2020, semana=53)
        self.assertEqual(umbral_canal_endemico(df, hist).iloc[0], 4.0)

    def test_marcar_arranque_exige_ventana_completa_y_silencio(self):
        df = panel([0, 0, 0, 1, 1, 0, 0, 0, 1]).assign(m=lambda d: d["casos_Dengue"])
        a = marcar_arranque(df, "m", ventana=3, desde_rezago=1)
        # t=3: ventana t-1..t-3 = [0,0,0] -> arranque; t=4: t-1 tiene marca; t=8: ventana [0,0,0] -> arranque
        self.assertEqual(a.tolist(), [False, False, False, True, False, False, False, False, True])
        b = marcar_arranque(df, "m", ventana=3, desde_rezago=2)
        # con desde_rezago=2, t=8 mira t-2..t-4 = [0,0,1] -> no es arranque
        self.assertFalse(b.iloc[8])
        self.assertEqual(sin_marca_previa(df, "m", ventana=3).tolist()[3], True)

    def test_resumen_definicion(self):
        df = panel([0, 3, 3, 0])
        r = resumen_definicion(df, df["casos_Dengue"] > 0)
        self.assertEqual((r["filas_positivas"], r["episodios"], r["pct_casos_cubiertos"]), (2, 1, 100.0))


if __name__ == "__main__":
    unittest.main()
