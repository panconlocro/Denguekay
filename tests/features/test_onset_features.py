"""No fuga y reproducción de las variables del bloque B (fase 2b del encargo de FE sobre E3·S4_s2)."""

import json
import unittest

import numpy as np
import pandas as pd

from denguekay.model import horizon_strategies as eh
from denguekay.features import onset_features as fi
from denguekay.model import probabilistic_output as sp
from denguekay.features.outbreak_label import label_seasonal_outbreak
from denguekay.data.calendar import mmwr_epi_week
from denguekay.config.paths import GOLD, GOLD_MANIFEST, SILVER_EPI_HISTORICAL, SILVER_INTEGRATED

HAY_DATOS = SILVER_INTEGRATED.exists() and GOLD_MANIFEST.exists() and SILVER_EPI_HISTORICAL.exists()
TODAS = [c for f in ("B1", "B2", "B3", "B5") for c in fi.COLUMNS[f]]


def _alterar(panel, serie, desde):
    panel, serie = panel.copy(), serie.copy()
    fp = pd.to_datetime(panel.semana_inicio) > desde
    fs = pd.to_datetime(serie.semana_inicio) > desde
    panel.loc[fp, "casos_Dengue"] = panel.loc[fp, "casos_Dengue"] * 3 + 7
    for c in fi.B5_CLIMATE:
        panel.loc[fp, c] = panel.loc[fp, c] + 5
    serie.loc[fs, "casos_Dengue"] = serie.loc[fs, "casos_Dengue"] * 3 + 7
    serie.loc[fs, "brote"] = 1 - serie.loc[fs, "brote"]
    return panel, serie


def _sintetico():
    """6 distritos en 2 provincias, 2017–2019, con clima y etiquetas de la regla de gold."""
    rng = np.random.default_rng(11)
    semanas = pd.date_range("2017-01-01", "2019-12-29", freq="7D")
    cal = mmwr_epi_week(pd.Series(semanas))
    filas = []
    for i in range(6):
        u = f"2001{i:02d}"
        base = pd.DataFrame({"ubigeo": u, "provincia": "P1" if i < 3 else "P2", "distrito": f"D{i}",
                             "lat": -5.0 - 0.1 * i, "lon": -80.0 + 0.07 * i ** 1.3,
                             "anio": cal.anio_epi.to_numpy(), "semana": cal.semana_epi.to_numpy(),
                             "semana_inicio": semanas, "casos_Dengue": rng.poisson(2 + i, len(semanas)).astype(float)})
        for c in fi.B5_CLIMATE:
            base[c] = rng.normal(25 if c.startswith("temp") else 60, 3, len(semanas))
        filas.append(base)
    panel = pd.concat(filas, ignore_index=True)
    panel["ubigeo"] = panel.ubigeo.astype("string")
    historia = pd.DataFrame([{"ubigeo": f"2001{i:02d}", "anio": y, "semana": s, "casos_Dengue": float(rng.poisson(2))}
                             for i in range(6) for y in range(2012, 2017) for s in range(1, 53)])
    etiquetas = label_seasonal_outbreak(panel, historia, multiplicador=1.5, anios_previos=5, minimo_casos=2)
    serie = panel[["ubigeo", "anio", "semana", "semana_inicio", "casos_Dengue"]].merge(
        etiquetas[["ubigeo", "anio", "semana", "brote"]], on=["ubigeo", "anio", "semana"])
    return panel, serie, historia


class TestSintetico(unittest.TestCase):
    def test_no_fuga_por_perturbacion(self):
        panel, serie, historia = _sintetico()
        corte, desde = pd.Timestamp("2018-12-29"), pd.Timestamp("2019-03-02")
        base = fi.weekly_table(panel, serie, historia, corte)
        otro = fi.weekly_table(*_alterar(panel, serie, desde), historia, corte)
        sel = base.semana_inicio <= desde
        pd.testing.assert_frame_equal(base.loc[sel, TODAS].reset_index(drop=True), otro.loc[sel, TODAS].reset_index(drop=True))
        self.assertFalse(np.allclose(base.loc[~sel, "propia_pendiente_4"], otro.loc[~sel, "propia_pendiente_4"], equal_nan=True))

    def test_temporada_2017_usa_la_historia(self):
        panel, serie, historia = _sintetico()
        t = fi.previous_season(serie, historia).set_index(["ubigeo", "temporada"])
        h = historia.assign(temporada=lambda d: np.where(d.semana >= 35, d.anio + 1, d.anio))
        esperado = np.log1p(h[(h.ubigeo == "200100") & (h.temporada == 2016)].casos_Dengue.sum())
        self.assertAlmostEqual(t.loc[("200100", 2017), fi.PREVIOUS_SEASON_COLUMN], esperado)
        sin_hist = fi.previous_season(serie, historia[historia.anio < 2015]).set_index(["ubigeo", "temporada"])
        self.assertTrue(np.isnan(sin_hist.loc[("200100", 2017), fi.PREVIOUS_SEASON_COLUMN]))


@unittest.skipUnless(HAY_DATOS, "requiere silver integrado, historia, manifiesto y gold")
class TestConDatos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from denguekay.data.loading import load_integrated
        from denguekay.evaluation import variants as fh

        cls.panel = load_integrated(SILVER_INTEGRATED)
        cls.rule = json.loads(GOLD_MANIFEST.read_text(encoding="utf-8"))["regla_brote"]
        ins = fh.insumos(cls.panel, cls.rule)
        cls.series, cls.matrices = ins["serie"], ins["matrices"]
        cls.history = pd.read_csv(SILVER_EPI_HISTORICAL, dtype={"ubigeo": "string"})
        cls.vi = fi.OnsetFeatures(cls.panel, cls.series, cls.history, cls.rule)
        cls.origins = eh.origin_table(cls.matrices[2])

    def test_no_fuga_por_perturbacion_en_origenes(self):
        """Alterar casos, brote y clima posteriores a D no cambia ninguna variable B de orígenes ≤ D (h=2, 3, 4)."""
        corte, desde = pd.Timestamp("2019-06-01"), pd.Timestamp("2019-06-08")
        familias = ["B1", "B2", "B3", "B4", "B5"]
        base = self.vi.origins(self.origins, familias, corte)
        panel, serie = _alterar(self.panel, self.series, desde)
        otro = fi.OnsetFeatures(panel, serie, self.history, self.rule).origins(self.origins, familias, corte)
        sel = pd.to_datetime(base.origen_cierre) <= desde
        cols = [c for f in familias for c in fi.COLUMNS[f]]
        pd.testing.assert_frame_equal(base.loc[sel, cols], otro.loc[sel, cols])
        self.assertFalse(base.loc[~sel, cols].equals(otro.loc[~sel, cols]))

    def test_b2_y_b5_ajustados_por_bloque(self):
        """Datos posteriores a la temporada 2022 no cambian las predicciones de 2021–2022."""
        familias = ["B2", "B5"]
        cols = [*eh.GENERIC, *fi.COLUMNS["B2"], *fi.COLUMNS["B5"]]
        pruebas, corte = eh._common_cutoffs(self.matrices, "temporada", 2022)
        fin_2022 = max(p.semana_inicio.max() for p in pruebas.values())
        o = self.vi.origins(self.origins, familias, corte).dropna(subset=cols).reset_index(drop=True)
        a = sp.predict_e3(self.matrices, 17, "S4_s2", columns=cols, origins=o,
                           prepare_block=self.vi.prepare_block(familias))
        panel, serie = _alterar(self.panel, self.series, fin_2022)
        otro = fi.OnsetFeatures(panel, serie, self.history, self.rule)
        b = sp.predict_e3(self.matrices, 17, "S4_s2", columns=cols, origins=o,
                           prepare_block=otro.prepare_block(familias))
        sel = a.bloque.isin(["temporada_2021", "temporada_2022"])
        np.testing.assert_array_equal(a.loc[sel, "casos_predichos"], b.loc[sel, "casos_predichos"])
        self.assertFalse(np.allclose(a.loc[~sel, "casos_predichos"], b.loc[~sel, "casos_predichos"]))

    def test_reproduce_gold_en_el_origen(self):
        """Nivel y fracción con casos de vecinos, provincia y región coinciden con las columnas _h2 de gold."""
        semanal = self.vi.weekly(pd.Timestamp("2021-08-28"))
        extra = ["vecinos_log_media_casos", "vecinos_frac_con_casos", "provincia_log_otros_casos",
                 "provincia_otros_frac_con_casos", "region_log_otros_casos", "region_otros_frac_con_casos"]
        estado = fi.di.estado_semanal(self.panel, self.series, pd.Timestamp("2021-08-28"))
        o = fi.add(self.origins, estado, extra)
        pares = {"vecinos_media_casos_knn5_h2": ("vecinos_log_media_casos", np.log1p),
                 "vecinos_frac_con_casos_knn5_h2": ("vecinos_frac_con_casos", None),
                 "provincia_otros_casos_h2": ("provincia_log_otros_casos", np.log1p),
                 "provincia_otros_frac_con_casos_h2": ("provincia_otros_frac_con_casos", None),
                 "region_otros_casos_h2": ("region_log_otros_casos", np.log1p),
                 "region_otros_frac_con_casos_h2": ("region_otros_frac_con_casos", None)}
        for gold, (nuestra, f) in pares.items():
            with self.subTest(gold=gold):
                esperado = o[gold].to_numpy(float)
                np.testing.assert_allclose(o[nuestra].to_numpy(float), f(esperado) if f else esperado, rtol=0, atol=1e-12)
        self.assertEqual(len(semanal), len(self.panel))

    def test_b4_sin_nulos_al_final_del_panel(self):
        o = self.vi.origins(self.origins, ["B4"], pd.Timestamp("2021-08-28"))
        self.assertFalse(o[fi.COLUMNS["B4"]].isna().any().any())


if __name__ == "__main__":
    unittest.main()
