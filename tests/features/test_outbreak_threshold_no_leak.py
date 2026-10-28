"""No fuga de ``umbral_brote_casos``: el umbral de la fila t no depende de casos posteriores a t−h.

Requisito previo de la formulación S4 (fase 4 del encargo multi-horizonte),
que convierte la distribución de casos predicha en P(brote) con ese umbral.
Se prueba con el horizonte más exigente del encargo (h=1) y con h=6.
"""

import json
import unittest

import numpy as np
import pandas as pd

from denguekay.features.outbreak_label import etiquetar_brote_estacional
from denguekay.config.paths import GOLD_MANIFEST, SILVER_EPI_HISTORICAL, SILVER_INTEGRATED
from denguekay.data.calendar import mmwr_epi_week

HAY_DATOS = SILVER_INTEGRATED.exists() and GOLD_MANIFEST.exists() and SILVER_EPI_HISTORICAL.exists()


def _panel_sintetico() -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(3)
    semanas = pd.date_range("2017-01-01", "2021-12-26", freq="7D")
    cal = mmwr_epi_week(pd.Series(semanas))
    panel = pd.DataFrame({"ubigeo": "200101", "anio": cal.anio_epi.to_numpy(), "semana": cal.semana_epi.to_numpy(),
                          "semana_inicio": semanas, "casos_Dengue": rng.poisson(3, len(semanas)).astype(float)})
    historia = pd.DataFrame([{"ubigeo": "200101", "anio": y, "semana": s, "casos_Dengue": float(rng.poisson(3))}
                             for y in range(2012, 2017) for s in range(1, 53)])
    return panel, historia


def _perturbar_despues(panel: pd.DataFrame, corte: pd.Timestamp) -> pd.DataFrame:
    alterado = panel.copy()
    futuro = pd.to_datetime(alterado.semana_inicio) > corte
    alterado.loc[futuro, "casos_Dengue"] = alterado.loc[futuro, "casos_Dengue"] * 10 + 50
    return alterado


def _comprobar(caso: unittest.TestCase, panel, historia, corte, h, **regla):
    base = etiquetar_brote_estacional(panel, historia, **regla)
    otro = etiquetar_brote_estacional(_perturbar_despues(panel, corte), historia, **regla)
    fechas = pd.to_datetime(panel.semana_inicio).to_numpy()
    # Filas cuyo origen t−h cierra en o antes del corte: el umbral no puede cambiar.
    conocidas = fechas - np.timedelta64(7 * h, "D") <= np.datetime64(corte)
    np.testing.assert_array_equal(base.umbral_brote_casos.to_numpy()[conocidas],
                                  otro.umbral_brote_casos.to_numpy()[conocidas])
    # Control: la perturbación sí cambia umbrales de años posteriores.
    caso.assertFalse(np.array_equal(base.umbral_brote_casos.to_numpy()[~conocidas],
                                    otro.umbral_brote_casos.to_numpy()[~conocidas]))


class TestUmbralSinFuga(unittest.TestCase):
    def test_sintetico_varios_cortes(self):
        panel, historia = _panel_sintetico()
        for corte in pd.to_datetime(["2018-12-15", "2019-06-15", "2020-12-26"]):
            for h in (1, 6):
                with self.subTest(corte=corte.date(), h=h):
                    _comprobar(self, panel, historia, corte, h, multiplicador=1.5, minimo_casos=2)


@unittest.skipUnless(HAY_DATOS, "Requiere silver integrado e historia epi locales")
class TestUmbralSinFugaConDatos(unittest.TestCase):
    def test_panel_real(self):
        from denguekay.data.loading import load_integrated

        panel = load_integrated(SILVER_INTEGRATED)
        regla = json.loads(GOLD_MANIFEST.read_text(encoding="utf-8"))["regla_brote"]
        historia = pd.read_csv(SILVER_EPI_HISTORICAL, dtype={"ubigeo": "string"})
        primero = int(panel.anio.min())
        historia = historia.loc[historia.anio.between(primero - regla["anios_previos"], primero - 1)]
        for corte in pd.to_datetime(["2021-08-21", "2022-12-31", "2023-08-19"]):
            for h in (1, 6):
                with self.subTest(corte=corte.date(), h=h):
                    _comprobar(self, panel, historia, corte, h, multiplicador=regla["multiplicador"],
                               anios_previos=regla["anios_previos"], minimo_casos=regla["minimo_casos"])


if __name__ == "__main__":
    unittest.main()
