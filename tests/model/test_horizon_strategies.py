"""Pruebas de las estrategias multi-horizonte (fase 3): no fuga y coherencia."""

import json
import unittest

import numpy as np
import pandas as pd

from denguekay.model import horizon_strategies as eh
from denguekay.config.paths import GOLD_MANIFEST, SILVER_EPI_HISTORICAL, SILVER_INTEGRATED

HAY_DATOS = SILVER_INTEGRATED.exists() and GOLD_MANIFEST.exists() and SILVER_EPI_HISTORICAL.exists()


def _matriz(h: int, semanas: int = 12) -> pd.DataFrame:
    fechas = pd.date_range("2022-01-02", periods=semanas, freq="7D")
    filas = []
    for ubigeo in ("200101", "200102"):
        for i, s in enumerate(fechas):
            filas.append({"ubigeo": ubigeo, "anio": 2022, "semana": i + 1, "semana_inicio": s,
                          "origen_cierre": s - pd.Timedelta(days=7 * h - 6), "casos_Dengue": float(i),
                          "brote": int(i % 3 == 0), f"casos_lag_{h}": float(i - h),
                          f"casos_lag_{h + 1}": float(i - h - 1), f"casos_media_4_h{h}": 1.0,
                          f"casos_semanas_positivas_4_h{h}": 2.0, "semana_epi_seno": 0.0,
                          "semana_epi_coseno": 1.0, "log_poblacion_censo_2017": 9.0, "horizonte": h})
    return pd.DataFrame(filas)


class TestEstrategiasSinFuga(unittest.TestCase):
    def test_apilado_solo_usa_etiquetas_cerradas(self):
        matrices = {h: _matriz(h) for h in eh.STRATEGY_HORIZONS}
        corte = pd.Timestamp("2022-02-12")
        apiladas = eh.stack_training(matrices, corte)
        self.assertTrue((apiladas.semana_inicio + pd.Timedelta(days=6)).le(corte).all())
        self.assertEqual(sorted(apiladas.horizonte.unique()), list(eh.STRATEGY_HORIZONS))
        self.assertTrue(set(eh.GENERIC) <= set(apiladas))
        # El rezago genérico es el del horizonte de cada fila.
        for h in eh.STRATEGY_HORIZONS:
            g = apiladas[apiladas.horizonte.eq(h)]
            self.assertTrue((g.hist_lag_a == g.casos_Dengue - h).all())

    def test_tabla_origenes_alinea_objetivos(self):
        origenes = eh.origin_table(_matriz(2))
        g = origenes[origenes.ubigeo.eq("200101")].reset_index(drop=True)
        self.assertTrue((g.casos_Dengue_h3.iloc[:-1].to_numpy() == g.casos_Dengue.iloc[1:].to_numpy()).all())
        self.assertTrue((g.semana_inicio_h4.dropna() - g.semana_inicio.iloc[:len(g.semana_inicio_h4.dropna())]
                         ).dt.days.eq(14).all())
        self.assertTrue(g.casos_Dengue_h4.iloc[-2:].isna().all())

    def test_coherencia_explicada_y_parpadeo(self):
        semana = pd.Timestamp("2022-03-06")
        filas = []
        # Al pasar de h=4 a h=3 el dato nuevo es la semana w-3 (frente a w-4).
        # Distrito A: alerta aparece en h=3 y los casos de w-3 subieron → explicada.
        # Distrito B: alerta desaparece en h=3 aunque los casos de w-3 subieron → sin explicar;
        #            reaparece en h=2 → parpadeo.
        for ubigeo, alertas in (("200101", {4: False, 3: True, 2: True}),
                                ("200102", {4: True, 3: False, 2: True})):
            for h, a in alertas.items():
                filas.append({"bloque": "temporada_2022", "ubigeo": ubigeo, "semana_inicio": semana,
                              "horizonte": h, "alerta_050": a, "probabilidad_calibrada": 0.5})
        serie = pd.DataFrame([{"ubigeo": u, "semana_inicio": semana - pd.Timedelta(weeks=k), "casos_Dengue": c}
                              for u in ("200101", "200102") for k, c in ((4, 1.0), (3, 5.0), (2, 5.0), (1, 5.0))])
        r = eh.horizon_coherence(pd.DataFrame(filas), serie).iloc[0]
        self.assertEqual(r.semanas_objetivo, 2)
        self.assertEqual(r.con_cambio, 1.0)
        self.assertEqual(r.cambio_sin_explicar, 0.5)
        self.assertEqual(r.parpadeo, 0.5)

    def test_desempate_por_simplicidad_y_coherencia(self):
        base = []
        for e, valor in (("E1", 0.020), ("E3", 0.019)):
            for b in ("temporada_2022", "temporada_2023"):
                base.append({"estrategia": e, "bloque": b, "cambio_sin_explicar": valor,
                             "rango_cambio_sin_explicar": 0.005})
        self.assertEqual(eh.break_tie(["E1", "E3"], pd.DataFrame(base)),
                         {"elegida": "E3", "criterio": "simplicidad operativa"})
        base[0]["cambio_sin_explicar"] = base[1]["cambio_sin_explicar"] = 0.001
        self.assertEqual(eh.break_tie(["E1", "E3"], pd.DataFrame(base))["elegida"], "E1")
        self.assertEqual(eh.break_tie(["E1"], pd.DataFrame(base))["criterio"], "única no descartada (no hubo desempate)")


@unittest.skipUnless(HAY_DATOS, "Requiere silver integrado, historia epi y gold locales")
class TestEstrategiasConDatos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from denguekay.data.loading import load_integrated
        from src.modeling.etiqueta_brote import ConfiguracionBroteEstacional
        from src.modeling.features import construir_etiquetas

        cls.panel = load_integrated(SILVER_INTEGRATED)
        regla = json.loads(GOLD_MANIFEST.read_text(encoding="utf-8"))["regla_brote"]
        cls.etiquetas = construir_etiquetas(cls.panel, ConfiguracionBroteEstacional(
            regla["multiplicador"], regla["anios_previos"], regla["minimo_casos"]))
        cls.matrices = {h: eh.horizon_matrix(cls.panel, cls.etiquetas, h) for h in eh.STRATEGY_HORIZONS}

    def test_matrices_causales_para_cada_h(self):
        for h in (1, 5, 6):
            m = eh.horizon_matrix(self.panel, self.etiquetas, h)
            self.assertTrue((m.semana_inicio > m.origen_cierre).all())
        for h, m in self.matrices.items():
            self.assertTrue((m.semana_inicio > m.origen_cierre).all())
            self.assertTrue(((m.semana_inicio - m.origen_cierre).dt.days == 7 * h - 6).all())

    def test_alterar_etiquetas_futuras_no_cambia_predicciones_de_2022(self):
        alteradas = {}
        for h, m in self.matrices.items():
            m = m.copy()
            futuro = m.semana_inicio >= pd.Timestamp("2021-08-29")  # desde la temporada 2022
            m.loc[futuro, "brote"] = 1 - m.loc[futuro, "brote"]
            m.loc[futuro, "casos_Dengue"] = m.loc[futuro, "casos_Dengue"] * 3 + 7
            alteradas[h] = m
        for nombre in ("E2", "E3"):
            with self.subTest(estrategia=nombre):
                base = eh.STRATEGIES[nombre](self.matrices, 17)
                otra = eh.STRATEGIES[nombre](alteradas, 17)
                sel = base.bloque.isin(["temporada_2021", "temporada_2022"])
                np.testing.assert_allclose(base.loc[sel, "probabilidad_brote"], otra.loc[sel, "probabilidad_brote"])
                np.testing.assert_allclose(base.loc[sel, "casos_predichos"], otra.loc[sel, "casos_predichos"])
                # Control: los bloques posteriores sí cambian.
                self.assertFalse(np.allclose(base.loc[~sel, "probabilidad_brote"], otra.loc[~sel, "probabilidad_brote"]))


if __name__ == "__main__":
    unittest.main()
