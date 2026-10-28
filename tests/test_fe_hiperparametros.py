"""Pruebas de la envoltura del encargo de FE e hiperparámetros sobre E3·S4_s2."""

import json
import unittest

import numpy as np
import pandas as pd

from src.modeling import estrategias_horizonte as eh
from src.modeling import fe_hiperparametros as fh
from src.modeling import salida_probabilistica as sp
from denguekay.config.paths import GOLD, GOLD_MANIFEST, SILVER_EPI_HISTORICO, SILVER_INTEGRADO

HAY_DATOS = SILVER_INTEGRADO.exists() and GOLD_MANIFEST.exists() and SILVER_EPI_HISTORICO.exists()


class TestComparacion(unittest.TestCase):
    def setUp(self):
        self.guardada = [{"horizonte": 2, "bloque": "temporada_2022", "f1_050": 0.68176, "brier": 0.05, "auprc": None},
                         {"horizonte": 2, "bloque": "temporada_2023", "f1_050": 0.71, "brier": 0.06, "auprc": None}]

    def test_igualdad_al_redondeo(self):
        nueva = pd.DataFrame(self.guardada).assign(f1_050=lambda t: t.f1_050 + 1e-5)
        cruce = fh.comparar_reproduccion(nueva, self.guardada)
        self.assertTrue(cruce.coincide.all())

    def test_diferencia_mayor_se_reporta(self):
        nueva = pd.DataFrame(self.guardada)
        nueva.loc[0, "brier"] += 0.002
        cruce = fh.comparar_reproduccion(nueva, self.guardada)
        fallas = cruce[~cruce.coincide]
        self.assertEqual(fallas[["bloque", "metrica"]].values.tolist(), [["temporada_2022", "brier"]])
        self.assertAlmostEqual(fallas.diferencia_absoluta.iloc[0], 0.002)

    def test_metrica_faltante_no_coincide(self):
        nueva = pd.DataFrame(self.guardada).drop(columns="brier")
        cruce = fh.comparar_reproduccion(nueva, self.guardada)
        self.assertEqual(set(cruce.loc[~cruce.coincide, "metrica"]), {"brier"})


class TestHuellaPredicciones(unittest.TestCase):
    def test_no_depende_del_orden_y_si_de_los_valores(self):
        pred = pd.DataFrame({"ubigeo": ["200101", "200102", "200101"], "anio": [2022] * 3, "semana": [1, 1, 2],
                             "horizonte": [2, 2, 2], "bloque": ["temporada_2022"] * 3, "semilla": [17] * 3,
                             "casos_predichos": [1.5, 0.25, 3.0],
                             "semana_inicio": pd.to_datetime(["2022-01-02", "2022-01-02", "2022-01-09"])})
        base = fh.huella_predicciones(pred)
        self.assertEqual(base, fh.huella_predicciones(pred.iloc[::-1][list(reversed(pred.columns))]))
        otra = pred.copy()
        otra.loc[1, "casos_predichos"] += 1e-9
        self.assertNotEqual(base, fh.huella_predicciones(otra))


class TestAntecedentes(unittest.TestCase):
    def test_delta_y_elegida(self):
        def fold(bloque, f1_reg, f1_cls):
            return {"bloque": bloque, "regresion": {"alerta_derivada": {"f1": f1_reg}},
                    "clasificacion": {"alerta_directa": {"f1": f1_cls}}}
        base = ["a", "b"]
        d = {"horizontes": {"2": {"elegidas_solo_validacion": {"regresion": "mas_x", "clasificacion": "base_6"},
                                  "variantes": {
                                      "base_6": {"columnas": base, "folds_validacion": [fold("t1", 0.5, 0.4), fold("t2", 0.7, 0.6)]},
                                      "mas_x": {"columnas": [*base, "x"], "folds_validacion": [fold("t1", 0.6, 0.4), fold("t2", 0.8, 0.5)]}}}}}
        t = fh.antecedentes_s1({"nb": d}).set_index("variante")
        self.assertEqual(t.at["mas_x", "columnas_agregadas"], ["x"])
        self.assertAlmostEqual(t.at["mas_x", "delta_f1_val_reg_vs_base_6"], 0.1)
        self.assertAlmostEqual(t.at["mas_x", "delta_f1_val_cls_vs_base_6"], -0.05)
        self.assertEqual(t.at["mas_x", "elegida_en_validacion"], "regresion")
        self.assertEqual(t.at["base_6", "elegida_en_validacion"], "clasificacion")


@unittest.skipUnless(HAY_DATOS, "requiere silver integrado, manifiesto y gold")
class TestConDatos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from src.eda.carga import cargar_integrado

        cls.panel = cargar_integrado(SILVER_INTEGRADO)
        regla = json.loads(GOLD_MANIFEST.read_text(encoding="utf-8"))["regla_brote"]
        cls.ins = fh.insumos(cls.panel, regla)

    def test_argumentos_opcionales_reproducen_la_version_por_defecto(self):
        m = self.ins["matrices"]
        por_defecto = sp.predecir_e3(m, 17, "S4_s2")
        explicita = sp.predecir_e3(m, 17, "S4_s2", columnas=list(eh.GENERICAS),
                                   origenes=eh.tabla_origenes(m[2]), hiperparametros={})
        np.testing.assert_array_equal(por_defecto.casos_predichos, explicita.casos_predichos)
        np.testing.assert_array_equal(por_defecto.probabilidad_brote, explicita.probabilidad_brote)
        otra = sp.predecir_e3(m, 17, "S4_s2", hiperparametros={"max_depth": 5})
        self.assertFalse(np.allclose(por_defecto.casos_predichos, otra.casos_predichos))

    def test_columna_ausente_falla(self):
        with self.assertRaises(ValueError):
            sp.predecir_e3(self.ins["matrices"], 17, "S4_s2", columnas=[*eh.GENERICAS, "no_existe"])

    def test_inventario_de_gold_h2(self):
        gold = pd.read_csv(GOLD / f"{SILVER_INTEGRADO.stem}_h2_gold.csv", dtype={"ubigeo": "string"},
                           parse_dates=["semana_inicio"])
        inv = fh.inventario_candidatas(gold, self.ins["matrices"][2])
        self.assertEqual(len(inv), 34)
        self.assertEqual(int(inv.en_base_6.sum()), 6)
        self.assertTrue(inv.columna.str.endswith(("_h2", "_2017", "_anual", "lag_2", "lag_3", "seno", "coseno")).all())


if __name__ == "__main__":
    unittest.main()
