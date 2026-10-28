"""Pruebas causales y geográficas de las variables espaciales de la fase 3."""

import unittest

import numpy as np
import pandas as pd

from src.modeling.vecinos_jerarquia import (
    catalogo_geografico, construir_vecinos_jerarquia, matriz_vecindad,
)


class VecinosJerarquiaTests(unittest.TestCase):
    def setUp(self):
        fechas = pd.date_range("2020-12-06", periods=9, freq="W-SUN")
        semanas = [50, 51, 52, 53, 1, 2, 3, 4, 5]
        distritos = [
            ("200101", "P1", 0.0, 0.0, 1),
            ("200102", "P1", 0.0, 1.0, 10),
            ("200201", "P2", 0.0, 3.0, 100),
            ("200202", "P2", 0.0, 6.0, 1000),
        ]
        self.panel = pd.concat([
            pd.DataFrame({"ubigeo": u, "provincia": p, "lat": lat, "lon": lon,
                "anio": [2020] * 4 + [2021] * 5, "semana": semanas,
                "semana_inicio": fechas, "casos_Dengue": np.arange(1, 10) * escala})
            for u, p, lat, lon, escala in distritos
        ], ignore_index=True)

    def test_matriz_vecindad_no_incluye_distrito_y_es_reproducible(self):
        geo = catalogo_geografico(self.panel)
        w, d = matriz_vecindad(geo, k=1)
        self.assertEqual(w.loc["200101", "200102"], 1)
        self.assertEqual(w.loc["200101", "200101"], 0)
        self.assertGreater(d.loc["200101", "200102"], 0)
        np.testing.assert_allclose(w.sum(axis=1), 1)
        w2, _ = matriz_vecindad(catalogo_geografico(
            self.panel.sample(frac=1, random_state=7)), k=1)
        pd.testing.assert_frame_equal(w, w2)

    def test_agregados_excluyen_distrito_y_toman_semana_del_origen(self):
        f = construir_vecinos_jerarquia(self.panel, horizonte=2, k=1)
        fila = f[(f.ubigeo == "200101") & (f.anio == 2021) & (f.semana == 1)].iloc[0]
        self.assertEqual(fila.origen_inicio, pd.Timestamp("2020-12-20"))
        self.assertEqual(fila.vecinos_media_casos_knn1_h2, 30)
        self.assertEqual(fila.vecinos_frac_con_casos_knn1_h2, 1)
        self.assertEqual(fila.provincia_otros_casos_h2, 30)
        self.assertEqual(fila.provincia_otros_frac_con_casos_h2, 1)
        self.assertEqual(fila.region_otros_casos_h2, 3330)
        self.assertEqual(fila.region_otros_frac_con_casos_h2, 1)
        self.assertTrue(f[(f.ubigeo == "200101") & (f.anio == 2020) &
                          (f.semana.isin([50, 51]))].iloc[:, 6:].isna().all().all())

    def test_contexto_propietario_no_usa_sus_casos(self):
        base = construir_vecinos_jerarquia(self.panel, horizonte=4, k=1)
        alterado = self.panel.copy()
        alterado.loc[(alterado.ubigeo == "200101") &
                     (alterado.semana_inicio == "2020-12-27"), "casos_Dengue"] = 999
        nuevo = construir_vecinos_jerarquia(alterado, horizonte=4, k=1)
        fila = (base.ubigeo == "200101") & (base.semana_inicio == "2021-01-24")
        columnas = [c for c in base if "casos_" in c]
        pd.testing.assert_frame_equal(base.loc[fila, columnas], nuevo.loc[fila, columnas])

    def test_cambios_posteriores_al_origen_no_afectan_h2_ni_h4(self):
        for h in (2, 4):
            with self.subTest(horizonte=h):
                base = construir_vecinos_jerarquia(self.panel, horizonte=h, k=2)
                objetivo = pd.Timestamp("2021-01-24")
                alterado = self.panel.copy()
                alterado.loc[alterado.semana_inicio > objetivo - pd.Timedelta(weeks=h),
                             "casos_Dengue"] = 999
                nuevo = construir_vecinos_jerarquia(alterado, horizonte=h, k=2)
                fila = (base.ubigeo == "200101") & (base.semana_inicio == objetivo)
                columnas = [c for c in base if "casos_" in c]
                pd.testing.assert_frame_equal(base.loc[fila, columnas], nuevo.loc[fila, columnas])

    def test_sensibilidad_k_e_inversa_no_produce_autocruce(self):
        geo = catalogo_geografico(self.panel)
        for metodo, k in (("knn", 1), ("knn", 2), ("knn_inversa", 2), ("inversa", 1)):
            with self.subTest(metodo=metodo, k=k):
                w, _ = matriz_vecindad(geo, k=k, metodo=metodo)
                np.testing.assert_allclose(w.sum(axis=1), 1)
                np.testing.assert_allclose(np.diag(w), 0)
                if metodo == "knn_inversa":
                    uniforme, _ = matriz_vecindad(geo, k=2, metodo="knn")
                    np.testing.assert_array_equal(w.to_numpy() > 0, uniforme.to_numpy() > 0)
                f = construir_vecinos_jerarquia(self.panel, 2, k=k, metodo=metodo)
                self.assertEqual(len(f), len(self.panel))
                self.assertFalse(f.duplicated(["ubigeo", "anio", "semana"]).any())

    def test_orden_de_entrada_no_cambia_variables(self):
        esperado = construir_vecinos_jerarquia(self.panel, 4, k=2)
        mezclado = construir_vecinos_jerarquia(
            self.panel.sample(frac=1, random_state=19), 4, k=2)
        pd.testing.assert_frame_equal(esperado, mezclado)

    def test_geografia_inconsistente_y_panel_incompleto_fallan(self):
        bad = self.panel.copy()
        bad.loc[0, "provincia"] = "Otro"
        with self.assertRaisesRegex(ValueError, "inconsistente"):
            construir_vecinos_jerarquia(bad, 2, k=1)
        with self.assertRaisesRegex(ValueError, "Faltan distrito-semanas"):
            construir_vecinos_jerarquia(self.panel.drop(index=0), 2, k=1)
        with self.assertRaisesRegex(ValueError, "k debe"):
            construir_vecinos_jerarquia(self.panel, 2, k=4)
        mismo_centroide = self.panel.copy()
        mismo_centroide.loc[mismo_centroide.ubigeo == "200102", "lon"] = 0.0
        with self.assertRaisesRegex(ValueError, "centroides idénticos"):
            construir_vecinos_jerarquia(mismo_centroide, 2, k=1)


if __name__ == "__main__":
    unittest.main()
