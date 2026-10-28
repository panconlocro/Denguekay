"""``umbral_brote_futuro``: la regla de gold, también para semanas fuera del panel."""

import json
import unittest

import numpy as np
import pandas as pd

from src.modeling.etiqueta_brote import etiquetar_brote_estacional, umbral_brote_futuro
from denguekay.config.paths import GOLD, GOLD_MANIFEST, SILVER_EPI_HISTORICO, SILVER_INTEGRADO
from src.utils.calendario import semana_epi_mmwr

HAY_DATOS = SILVER_INTEGRADO.exists() and GOLD_MANIFEST.exists() and SILVER_EPI_HISTORICO.exists()


def _sintetico():
    rng = np.random.default_rng(5)
    semanas = pd.date_range("2017-01-01", "2021-12-26", freq="7D")
    cal = semana_epi_mmwr(pd.Series(semanas))
    panel = pd.concat([pd.DataFrame({"ubigeo": u, "anio": cal.anio_epi.to_numpy(), "semana": cal.semana_epi.to_numpy(),
                                     "casos_Dengue": rng.poisson(3, len(semanas)).astype(float)})
                       for u in ("200101", "200102")], ignore_index=True)
    historia = pd.DataFrame([{"ubigeo": "200101", "anio": y, "semana": s, "casos_Dengue": float(rng.poisson(3))}
                             for y in range(2012, 2017) for s in range(1, 53) if rng.random() < 0.6])
    return panel, historia


class TestSintetico(unittest.TestCase):
    def test_igual_a_la_regla_de_etiquetas_en_semanas_observadas(self):
        panel, historia = _sintetico()
        esperado = etiquetar_brote_estacional(panel, historia, multiplicador=1.5, anios_previos=5)
        obtenido = umbral_brote_futuro(panel, historia, panel, multiplicador=1.5, anios_previos=5)
        np.testing.assert_array_equal(esperado.umbral_brote_casos.to_numpy(), obtenido.to_numpy())

    def test_semanas_futuras_y_limites(self):
        panel, historia = _sintetico()
        futuro = pd.DataFrame({"ubigeo": "200102", "anio": 2022, "semana": [1, 2, 53]})
        u = umbral_brote_futuro(panel, historia, futuro, multiplicador=1.5)
        self.assertTrue(np.isfinite(u).all())
        self.assertEqual(u.iloc[2], umbral_brote_futuro(panel, historia, futuro.iloc[[2]].assign(semana=52),
                                                        multiplicador=1.5).iloc[0])
        with self.assertRaises(ValueError):
            umbral_brote_futuro(panel, historia, pd.DataFrame({"ubigeo": ["200101"], "anio": [2023], "semana": [1]}),
                                multiplicador=1.5)

    def test_no_usa_el_anio_objetivo(self):
        panel, historia = _sintetico()
        objetivos = panel[panel.anio.eq(2021)]
        base = umbral_brote_futuro(panel, historia, objetivos, multiplicador=1.5)
        alterado = panel.copy()
        alterado.loc[alterado.anio.eq(2021), "casos_Dengue"] *= 10
        np.testing.assert_array_equal(base, umbral_brote_futuro(alterado, historia, objetivos, multiplicador=1.5))


@unittest.skipUnless(HAY_DATOS, "requiere silver integrado, historia, manifiesto y gold")
class TestContraGold(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from src.eda.carga import cargar_integrado

        cls.panel = cargar_integrado(SILVER_INTEGRADO)
        cls.regla = json.loads(GOLD_MANIFEST.read_text(encoding="utf-8"))["regla_brote"]
        historia = pd.read_csv(SILVER_EPI_HISTORICO, dtype={"ubigeo": "string"})
        cls.historia = historia[historia.anio.lt(int(cls.panel.anio.min()))]

    def _umbral(self, objetivos):
        return umbral_brote_futuro(self.panel, self.historia, objetivos, multiplicador=self.regla["multiplicador"],
                                   anios_previos=self.regla["anios_previos"])

    def test_exactamente_igual_a_la_regla_de_gold(self):
        """Igualdad bit a bit con ``construir_etiquetas``, el código que genera la columna de gold."""
        from src.modeling.etiqueta_brote import ConfiguracionBroteEstacional
        from src.modeling.features import construir_etiquetas

        etiquetas = construir_etiquetas(self.panel, ConfiguracionBroteEstacional(
            self.regla["multiplicador"], self.regla["anios_previos"], self.regla["minimo_casos"]))
        np.testing.assert_array_equal(etiquetas.umbral_brote_casos.to_numpy(), self._umbral(etiquetas).to_numpy())

    def test_igual_al_csv_de_gold(self):
        """Contra el CSV de gold: k de S4 y etiqueta idénticos; el valor, salvo el redondeo de la escritura (<1e-12)."""
        from src.modeling.salida_probabilistica import umbral_conteo

        for h in (2, 4):
            with self.subTest(h=h):
                gold = pd.read_csv(GOLD / f"{SILVER_INTEGRADO.stem}_h{h}_gold.csv", dtype={"ubigeo": "string"},
                                   usecols=["ubigeo", "anio", "semana", "casos_Dengue", "umbral_brote_casos", "brote"])
                u = self._umbral(gold).to_numpy()
                np.testing.assert_allclose(u, gold.umbral_brote_casos.to_numpy(), rtol=0, atol=1e-12)
                np.testing.assert_array_equal(umbral_conteo(u), umbral_conteo(gold.umbral_brote_casos))
                brote = ((gold.casos_Dengue.to_numpy() > u) & (gold.casos_Dengue.to_numpy() >= self.regla["minimo_casos"]))
                np.testing.assert_array_equal(brote.astype(int), gold.brote.to_numpy(int))

    def test_primeras_semanas_de_2026(self):
        ubigeos = sorted(self.panel.ubigeo.unique())
        futuro = pd.DataFrame([(u, 2026, s) for u in ubigeos for s in (1, 2, 3, 4)], columns=["ubigeo", "anio", "semana"])
        u = self._umbral(futuro)
        self.assertEqual(len(u), 4 * len(ubigeos))
        self.assertTrue(np.isfinite(u).all() and (u >= 0).all())


if __name__ == "__main__":
    unittest.main()
