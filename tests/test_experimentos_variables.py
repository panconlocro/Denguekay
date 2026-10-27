"""Pruebas de los experimentos de variables (fase 2 del encargo de FE sobre E3·S4_s2)."""

import json
import unittest

import numpy as np
import pandas as pd

from src.modeling import estrategias_horizonte as eh
from src.modeling import experimentos_variables as ev
from src.modeling import salida_probabilistica as sp
from src.utils.paths import GOLD_MANIFEST, SILVER_EPI_HISTORICO, SILVER_INTEGRADO

HAY_DATOS = SILVER_INTEGRADO.exists() and GOLD_MANIFEST.exists() and SILVER_EPI_HISTORICO.exists()


def _origenes_sinteticos(n=60, seed=0):
    rng = np.random.default_rng(seed)
    semanas = pd.date_range("2018-01-07", periods=n, freq="7D")
    return pd.DataFrame({"semana_inicio": semanas, f"semana_inicio_h{ev.H_ULTIMO}": semanas + pd.Timedelta(weeks=2),
                         "a": rng.normal(size=n), "b": rng.normal(size=n) * 3 + 1, "c": rng.normal(size=n)})


class TestCp1(unittest.TestCase):
    def test_estandarizacion_y_carga_solo_con_entrenamiento(self):
        o = _origenes_sinteticos()
        corte = o.semana_inicio.iloc[30]
        cp1 = ev.Cp1PorBloque(["c", "a", "b"], "cp1")
        base = cp1.ajustar(o, corte)
        alterado = o.copy()
        despues = ~ev.filas_entrenamiento(o, corte)
        alterado.loc[despues, ["a", "b", "c"]] = alterado.loc[despues, ["a", "b", "c"]] * 10 + 5
        otro = cp1.ajustar(alterado, corte)
        for clave in ("media", "de", "carga"):
            np.testing.assert_allclose(base[clave], otro[clave])
        self.assertEqual(base["filas_ajuste"], int((~despues).sum()))
        np.testing.assert_allclose(cp1(o, corte).loc[~despues, "cp1"], cp1(alterado, corte).loc[~despues, "cp1"])

    def test_signo_fijo_y_varianza(self):
        o = _origenes_sinteticos()
        ajuste = ev.Cp1PorBloque(["a", "b", "c"], "cp1").ajustar(o, o.semana_inicio.max() + pd.Timedelta(weeks=4))
        self.assertGreaterEqual(ajuste["carga"][0], 0)
        self.assertTrue(0 < ajuste["varianza_explicada"] <= 1)


class TestLectura(unittest.TestCase):
    def test_senal_de_temporada(self):
        t = pd.DataFrame({"horizonte": [2, 3, 4, 2],
                          "mejora_f1_050": [True, True, False, True],
                          "mejora_antelacion": [False, True, False, False],
                          "mejora_recall_nuevos": [False, False, False, True]})
        self.assertEqual(ev.marcar_senal_temporada(t).posible_senal_de_temporada.tolist(), [True, False, False, False])

    def test_recall_nuevos_exige_ambas_temporadas_sobre_el_rango(self):
        def resumen(valores, rango):
            filas = [{"horizonte": 2, "bloque": b, "tipo": "brote_nuevo", "semanas": 10, "recall_mediana": v,
                      "recall_minimo": v - rango / 2, "recall_maximo": v + rango / 2}
                     for b, v in zip(("temporada_2022", "temporada_2023"), valores)]
            return {"recall_por_tipo": pd.DataFrame(filas)}
        sube = ev.mejora_recall_nuevos(resumen((0.30, 0.30), 0.02), resumen((0.10, 0.10), 0.02))
        self.assertTrue(sube.mejora_recall_nuevos.iloc[0])
        solo_una = ev.mejora_recall_nuevos(resumen((0.30, 0.11), 0.02), resumen((0.10, 0.10), 0.02))
        self.assertFalse(solo_una.mejora_recall_nuevos.iloc[0])


@unittest.skipUnless(HAY_DATOS, "requiere silver integrado, manifiesto y gold")
class TestConDatos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from src.eda.carga import cargar_integrado
        from src.modeling import fe_hiperparametros as fh

        panel = cargar_integrado(SILVER_INTEGRADO)
        regla = json.loads(GOLD_MANIFEST.read_text(encoding="utf-8"))["regla_brote"]
        cls.matrices = fh.insumos(panel, regla)["matrices"]

    def test_preparar_bloque_identidad_no_cambia_nada(self):
        base = sp.predecir_e3(self.matrices, 17, "S4_s2")
        otra = sp.predecir_e3(self.matrices, 17, "S4_s2", preparar_bloque=lambda o, corte: o)
        np.testing.assert_array_equal(base.casos_predichos, otra.casos_predichos)
        np.testing.assert_array_equal(base.probabilidad_brote, otra.probabilidad_brote)

    def test_interseccion_clima_de_gold(self):
        origenes, excluidas = ev.origenes_con(self.matrices, ["hum_rel_media_media5_h2", "precip_total_mm_media5_h2"])
        self.assertEqual(excluidas["filas"], 65)
        self.assertTrue(excluidas["ultima"] < "2018-01-01")
        self.assertFalse(origenes[["hum_rel_media_media5_h2", "precip_total_mm_media5_h2"]].isna().any().any())

    def test_cp1_anual_sin_fuga_en_el_bloque_2022(self):
        """Alterar fracciones anuales posteriores a la temporada 2022 no cambia las predicciones de 2021–2022.

        Si la estandarización o el CP1 usaran filas fuera del entrenamiento del bloque, cambiarían.
        """
        fracciones = [c for c in eh.tabla_origenes(self.matrices[2]) if c.startswith("fraccion_") and c.endswith("_anual")]
        self.assertEqual(len(fracciones), 15)
        origenes, _ = ev.origenes_con(self.matrices, fracciones)
        pruebas, corte = eh._cortes_comunes(self.matrices, "temporada", 2022)
        fin_2022 = max(p.semana_inicio.max() for p in pruebas.values())
        alterado = origenes.copy()
        despues = alterado.semana_inicio.gt(fin_2022)
        alterado.loc[despues, fracciones] = alterado.loc[despues, fracciones] + 0.3
        cols = [*eh.GENERICAS, "socio_anual_cp1"]
        a = sp.predecir_e3(self.matrices, 17, "S4_s2", columnas=cols, origenes=origenes,
                           preparar_bloque=ev.Cp1PorBloque(fracciones, "socio_anual_cp1"))
        b = sp.predecir_e3(self.matrices, 17, "S4_s2", columnas=cols, origenes=alterado,
                           preparar_bloque=ev.Cp1PorBloque(fracciones, "socio_anual_cp1"))
        sel = a.bloque.isin(["temporada_2021", "temporada_2022"])
        np.testing.assert_array_equal(a.loc[sel, "casos_predichos"], b.loc[sel, "casos_predichos"])
        np.testing.assert_array_equal(a.loc[sel, "probabilidad_brote"], b.loc[sel, "probabilidad_brote"])
        self.assertFalse(np.allclose(a.loc[~sel, "casos_predichos"], b.loc[~sel, "casos_predichos"]))

if __name__ == "__main__":
    unittest.main()
