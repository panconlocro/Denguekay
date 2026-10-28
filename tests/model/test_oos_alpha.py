"""α OOS de la binomial negativa (fase 4.2 del encargo de FE): respaldo, causalidad y valor por defecto."""

import json
import unittest

import numpy as np
import pandas as pd

from denguekay.model import probabilistic_output as sp
from denguekay.config.paths import GOLD_MANIFEST, SILVER_INTEGRATED

HAY_DATOS = SILVER_INTEGRATED.exists() and GOLD_MANIFEST.exists()
H = (2, 3, 4)


def _prueba(inicio, semanas, mu, rng, bloque):
    fechas = pd.date_range(inicio, periods=semanas, freq="7D")
    y = rng.negative_binomial(1 / 0.8, 1 / (1 + 0.8 * mu), size=semanas)
    return pd.DataFrame({"semana_inicio": fechas, "casos_predichos": mu, "casos_Dengue": y, "bloque_origen": bloque})


def _sintetico(alpha_dentro=0.8):
    rng = np.random.default_rng(1)
    nombres = [("temporada_2020", "2019-08-25"), ("temporada_2021", "2020-08-23"), ("temporada_2022", "2021-08-22"),
               ("temporada_2023", "2022-08-21"), ("temporada_2024", "2023-08-20")]
    pruebas = {b: {h: _prueba(i, 52, 3.0, rng, b) for h in H} for b, i in nombres}
    cortes = {b: pd.Timestamp(i) - pd.Timedelta(days=22) for b, i in nombres}
    dentro = {b: {h: alpha_dentro for h in H} for b, _ in nombres[1:]}
    return pruebas, cortes, dentro


class TestAlfasOOS(unittest.TestCase):
    def test_detalle_y_limite(self):
        rng = np.random.default_rng(0)
        mu = np.full(5000, 4.0)
        y = rng.negative_binomial(1 / 0.5, 1 / (1 + 0.5 * mu))
        d = sp.negative_binomial_dispersion_detail(mu, y)
        self.assertTrue(d["convergio"])
        self.assertFalse(d["en_limite"])
        self.assertAlmostEqual(d["alpha"], 0.5, delta=0.08)
        self.assertEqual(sp.negative_binomial_dispersion(mu, y), d["alpha"])
        # Sin sobredispersión el óptimo se va al límite inferior.
        self.assertTrue(sp.negative_binomial_dispersion_detail(np.full(50, 2.0), np.full(50, 2.0))["en_limite"])

    def test_primer_bloque_usa_solo_el_pseudo_bloque_y_previos_acumulados(self):
        pruebas, cortes, dentro = _sintetico()
        a = sp.oos_alphas(pruebas, cortes, dentro).set_index(["bloque", "horizonte"])
        self.assertEqual(a.loc[("temporada_2021", 2), "bloques_previos"], "temporada_2020")
        self.assertEqual(a.loc[("temporada_2023", 2), "bloques_previos"],
                         "temporada_2020,temporada_2021,temporada_2022")
        self.assertNotIn("temporada_2020", a.index.get_level_values("bloque"))
        self.assertFalse(a.respaldo.any())
        self.assertTrue(np.allclose(a.alpha_usada, a.alpha_oos))

    def test_sin_fuga_casos_posteriores_al_corte(self):
        """Perturbar casos con semana objetivo no cerrada en el corte no cambia la α OOS del bloque."""
        pruebas, cortes, dentro = _sintetico()
        base = sp.oos_alphas(pruebas, cortes, dentro)
        corte = cortes["temporada_2022"]
        for h in H:
            t = pruebas["temporada_2021"][h]
            tarde = (t.semana_inicio + pd.Timedelta(days=6)).gt(corte)
            self.assertTrue(tarde.any())
            t.loc[tarde, "casos_Dengue"] += 1000
            for b in ("temporada_2022", "temporada_2023", "temporada_2024"):
                pruebas[b][h]["casos_Dengue"] += 1000
        pert = sp.oos_alphas(pruebas, cortes, dentro)
        fila = lambda df: df[df.bloque.eq("temporada_2022")].alpha_oos.to_numpy()
        np.testing.assert_array_equal(fila(base), fila(pert))

    def test_respaldo_fuera_de_rango(self):
        pruebas, cortes, dentro = _sintetico(alpha_dentro=0.05)
        a = sp.oos_alphas(pruebas, cortes, dentro)
        self.assertTrue(a.respaldo.all())
        self.assertFalse(a.en_rango.any())
        np.testing.assert_array_equal(a.alpha_usada, a.alpha_dentro_muestra)
        self.assertTrue(np.allclose(a.rango_minimo, 0.01) and np.allclose(a.rango_maximo, 0.25))

    def test_oos_solo_en_s4(self):
        with self.assertRaises(ValueError):
            sp.predict_e3({}, 17, "S2_pois", dispersion="oos")
        with self.assertRaises(ValueError):
            sp.predict_e3({}, 17, "S4_s2", dispersion="otra")


@unittest.skipUnless(HAY_DATOS, "requiere silver integrado, manifiesto y gold")
class TestConDatos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from denguekay.data.loading import load_integrated
        from denguekay.evaluation import variants as fh

        panel = load_integrated(SILVER_INTEGRATED)
        regla = json.loads(GOLD_MANIFEST.read_text(encoding="utf-8"))["regla_brote"]
        cls.matrices = fh.inputs(panel, regla)["matrices"]

    def test_oos_cambia_solo_la_probabilidad(self):
        dentro = sp.predict_e3(self.matrices, 17, "S4_s2")
        oos = sp.predict_e3(self.matrices, 17, "S4_s2", dispersion="oos")
        clave = ["ubigeo", "semana_inicio", "horizonte", "bloque"]
        a, b = dentro.sort_values(clave).reset_index(drop=True), oos.sort_values(clave).reset_index(drop=True)
        pd.testing.assert_frame_equal(a.drop(columns="probabilidad_brote"), b.drop(columns="probabilidad_brote"))
        self.assertFalse(np.allclose(a.probabilidad_brote, b.probabilidad_brote))
        alfas = oos.attrs["alfas"]
        self.assertEqual(len(alfas), 5 * 3)
        self.assertEqual(set(alfas.bloque), {"temporada_2021", "temporada_2022", "temporada_2023",
                                             "temporada_2024", "calendario_2025"})
        np.testing.assert_allclose(
            alfas.sort_values(["bloque", "horizonte"]).alpha_dentro_muestra.to_numpy(),
            dentro.attrs["alfas"].sort_values(["bloque", "horizonte"]).alpha_dentro_muestra.to_numpy())


if __name__ == "__main__":
    unittest.main()
