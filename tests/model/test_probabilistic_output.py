"""Pruebas de las formulaciones de salida (fase 4): S4 binomial negativa y no fuga."""

import json
import unittest

import numpy as np
import pandas as pd
from scipy import stats

from denguekay.model import horizon_strategies as eh
from denguekay.model import probabilistic_output as sp
from denguekay.config.paths import GOLD_MANIFEST, SILVER_EPI_HISTORICAL, SILVER_INTEGRATED

HAY_DATOS = SILVER_INTEGRATED.exists() and GOLD_MANIFEST.exists() and SILVER_EPI_HISTORICAL.exists()


class TestBinomialNegativa(unittest.TestCase):
    def test_umbral_conteo_reproduce_regla_de_gold(self):
        umbral = np.array([0.0, 0.4, 1.0, 1.7, 2.0, 5.3])
        k = sp.umbral_conteo(umbral)
        np.testing.assert_array_equal(k, [2, 2, 2, 2, 3, 6])
        for u, kk in zip(umbral, k):
            for casos in range(10):
                self.assertEqual(casos >= kk, casos > u and casos >= 2)

    def test_dispersion_recupera_alpha(self):
        rng = np.random.default_rng(0)
        mu = rng.uniform(0.5, 20, 20000)
        alpha = 0.6
        r = 1 / alpha
        y = rng.negative_binomial(r, r / (r + mu))
        self.assertAlmostEqual(sp.dispersion_binomial_negativa(mu, y), alpha, delta=0.05)

    def test_probabilidad_coincide_con_scipy_y_poisson_limite(self):
        mu, u = np.array([3.0, 10.0]), np.array([4.2, 1.0])
        p = sp.probabilidad_binomial_negativa(mu, 1e-6, u)
        np.testing.assert_allclose(p, stats.poisson.sf(sp.umbral_conteo(u) - 1, mu), rtol=1e-4)
        self.assertTrue(((p >= 0) & (p <= 1)).all())

    def test_margen_persistencia(self):
        np.testing.assert_allclose(sp.margen_persistencia([0, 1.5]), np.log([0.5, 2.0]))
        with self.assertRaises(ValueError):
            sp.margen_persistencia([-1])

    def test_conteo_de_modelos(self):
        self.assertEqual(sp.MODELOS[("E3", "S4_s2")], 1)
        self.assertEqual(sp.MODELOS[("E1", "S4_s2")], 3)
        self.assertEqual(sp.MODELOS[("E1", "S1")], 6)


@unittest.skipUnless(HAY_DATOS, "Requiere silver integrado, historia epi y gold locales")
class TestFormulacionesConDatos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from denguekay.data.loading import cargar_integrado
        from src.modeling.etiqueta_brote import ConfiguracionBroteEstacional
        from src.modeling.features import construir_etiquetas

        panel = cargar_integrado(SILVER_INTEGRATED)
        regla = json.loads(GOLD_MANIFEST.read_text(encoding="utf-8"))["regla_brote"]
        etiquetas = construir_etiquetas(panel, ConfiguracionBroteEstacional(
            regla["multiplicador"], regla["anios_previos"], regla["minimo_casos"]))
        cls.matrices = {h: eh.matriz_horizonte(panel, etiquetas, h) for h in eh.HORIZONTES_ESTRATEGIA}

    def test_s1_reproduce_fase_3(self):
        for nombre, referencia in (("E1", eh.predecir_e1(self.matrices, 17, eh.HORIZONTES_ESTRATEGIA)),
                                   ("E3", eh.predecir_e3(self.matrices, 17))):
            with self.subTest(estrategia=nombre):
                nueva = sp.PREDICTORES[nombre](self.matrices, 17, "S1")
                np.testing.assert_array_equal(referencia.probabilidad_brote, nueva.probabilidad_brote)
                np.testing.assert_array_equal(referencia.casos_predichos, nueva.casos_predichos)

    def test_s4_y_s3_sin_fuga_por_perturbacion_del_futuro(self):
        alteradas = {}
        for h, m in self.matrices.items():
            m = m.copy()
            futuro = m.semana_inicio >= pd.Timestamp("2021-08-29")
            m.loc[futuro, "casos_Dengue"] = m.loc[futuro, "casos_Dengue"] * 3 + 7
            m.loc[futuro, "brote"] = 1 - m.loc[futuro, "brote"]
            alteradas[h] = m
        for estrategia in ("E1", "E3"):
            for formulacion in ("S4_s3", "S5_spw"):
                with self.subTest(estrategia=estrategia, formulacion=formulacion):
                    base = sp.PREDICTORES[estrategia](self.matrices, 17, formulacion)
                    otra = sp.PREDICTORES[estrategia](alteradas, 17, formulacion)
                    sel = base.bloque.isin(["temporada_2021", "temporada_2022"])
                    np.testing.assert_allclose(base.loc[sel, "probabilidad_brote"], otra.loc[sel, "probabilidad_brote"])
                    np.testing.assert_allclose(base.loc[sel, "casos_predichos"], otra.loc[sel, "casos_predichos"])
                    self.assertFalse(np.allclose(base.loc[~sel, "casos_predichos"], otra.loc[~sel, "casos_predichos"]))

    def test_s4_parametros_solo_con_entrenamiento_del_bloque(self):
        """Altera toda etiqueta que cierra después del corte de 2022 de cada horizonte.

        Cubre la dispersión de la binomial negativa (ajustada con el entrenamiento
        del bloque) y el modelo de conteo: las predicciones de 2022 no cambian.
        """
        alteradas = {}
        for h, m in self.matrices.items():
            _, _, corte = eh.separar(m, "temporada", 2022)
            m = m.copy()
            despues = (m.semana_inicio + pd.Timedelta(days=6)) > corte
            m.loc[despues, "casos_Dengue"] = m.loc[despues, "casos_Dengue"] * 5 + 11
            alteradas[h] = m
        for estrategia in ("E1", "E3"):
            for formulacion in ("S4_s2", "S4_s3"):
                with self.subTest(estrategia=estrategia, formulacion=formulacion):
                    base = sp.PREDICTORES[estrategia](self.matrices, 17, formulacion)
                    otra = sp.PREDICTORES[estrategia](alteradas, 17, formulacion)
                    sel = base.bloque.eq("temporada_2022")
                    np.testing.assert_allclose(base.loc[sel, "probabilidad_brote"], otra.loc[sel, "probabilidad_brote"])
                    self.assertFalse(np.allclose(base.loc[~sel, "probabilidad_brote"], otra.loc[~sel, "probabilidad_brote"]))

    def test_recall_por_tipo_semana(self):
        serie = pd.DataFrame({"ubigeo": "200101", "semana_inicio": pd.date_range("2022-01-02", periods=14, freq="7D"),
                              "brote": [0] * 9 + [1, 1, 1, 0, 0]})
        datos = serie.assign(horizonte=2, bloque="temporada_2022", probabilidad_calibrada=0.5,
                             alerta_050=[False] * 9 + [False, True, True, False, False])
        r = sp.recall_por_tipo_semana(datos, serie).set_index("tipo")
        self.assertEqual(r.loc["brote_nuevo", "semanas"], 2)
        self.assertEqual(r.loc["brote_nuevo", "recall"], 0.5)
        self.assertEqual(r.loc["en_curso", "recall"], 1.0)


if __name__ == "__main__":
    unittest.main()
