"""Pruebas del protocolo preregistrado de la fase 2, incluida la no fuga."""

import unittest

import numpy as np
import pandas as pd

from src.modeling import protocolo_arquitectura as pa


def _bloques(semilla: int = 0) -> pd.DataFrame:
    """Tres temporadas sintéticas de 30 semanas para dos distritos, h=2."""
    rng = np.random.default_rng(semilla)
    filas = []
    for k, bloque in enumerate(["temporada_2021", "temporada_2022", "temporada_2023"]):
        semanas = pd.date_range(pd.Timestamp("2021-01-03") + pd.Timedelta(weeks=52 * k), periods=30, freq="7D")
        for ubigeo in ("200101", "200102"):
            for s in semanas:
                p = float(rng.uniform())
                filas.append({
                    "ubigeo": ubigeo, "anio": s.year, "semana": s.isocalendar().week,
                    "semana_inicio": s, "origen_cierre": s - pd.Timedelta(days=8),
                    "horizonte": 2, "bloque": bloque, "casos_Dengue": 0.0,
                    "brote": int(rng.uniform() < p), "umbral_brote_casos": 1.0,
                    "persistencia": 0.0, "probabilidad_brote": p,
                })
    return pd.DataFrame(filas)


class TestCalibracionSinFuga(unittest.TestCase):
    def test_2021_sin_calibrador_y_cortes_cronologicos(self):
        datos, registro = pa.calibrar_cronologicamente(_bloques())
        self.assertTrue(datos.loc[datos.bloque.eq("temporada_2021"), "probabilidad_calibrada"].isna().all())
        self.assertTrue(datos.loc[datos.bloque.ne("temporada_2021"), "probabilidad_calibrada"].notna().all())
        usados = registro.dropna(subset=["ultima_etiqueta_usada"])
        self.assertTrue((usados.ultima_etiqueta_usada <= usados.corte).all())

    def test_alterar_bloque_evaluado_y_futuro_no_cambia_calibracion(self):
        base = _bloques()
        calibrada, _ = pa.calibrar_cronologicamente(base)
        alterada = base.copy()
        # Se invierten etiquetas y probabilidades de 2023: no pueden afectar 2022.
        m = alterada.bloque.eq("temporada_2023")
        alterada.loc[m, "brote"] = 1 - alterada.loc[m, "brote"]
        # Y las etiquetas de 2022 (bloque evaluado) tampoco pueden afectar su propia calibración.
        m22 = alterada.bloque.eq("temporada_2022")
        alterada.loc[m22, "brote"] = 1 - alterada.loc[m22, "brote"]
        recalibrada, _ = pa.calibrar_cronologicamente(alterada)
        sel = calibrada.bloque.eq("temporada_2022")
        np.testing.assert_allclose(calibrada.loc[sel, "probabilidad_calibrada"],
                                   recalibrada.loc[sel, "probabilidad_calibrada"])

    def test_excluye_etiquetas_no_cerradas_al_corte(self):
        datos = _bloques()
        # El último origen de 2021 queda después del primer origen de 2022 si se adelanta 2022.
        m = datos.bloque.eq("temporada_2022")
        datos.loc[m, "semana_inicio"] -= pd.Timedelta(weeks=24)
        datos.loc[m, "origen_cierre"] -= pd.Timedelta(weeks=24)
        _, registro = pa.calibrar_cronologicamente(datos)
        fila = registro.set_index("bloque").loc["temporada_2022"]
        self.assertGreater(fila.etiquetas_no_cerradas, 0)
        self.assertLessEqual(fila.ultima_etiqueta_usada, fila.corte)

    def test_rechaza_origen_no_anterior_y_ubigeo_numerico(self):
        datos = _bloques()
        malo = datos.copy()
        malo.loc[0, "origen_cierre"] = malo.loc[0, "semana_inicio"]
        with self.assertRaisesRegex(ValueError, "Fuga temporal"):
            pa.validar_predicciones(malo)
        malo = datos.copy()
        malo["ubigeo"] = malo.ubigeo.astype(int)
        with self.assertRaisesRegex(ValueError, "seis dígitos"):
            pa.validar_predicciones(malo)

    def test_calibradores_monotonos_en_rango(self):
        rng = np.random.default_rng(1)
        p = rng.uniform(size=500)
        y = (rng.uniform(size=500) < p ** 2).astype(int)
        q = np.linspace(0, 1, 101)
        for metodo in ("platt", "isotonica"):
            c = pa.ajustar_calibrador(p, y, metodo)(q)
            self.assertTrue(((c >= 0) & (c <= 1)).all())
            self.assertTrue((np.diff(c) >= -1e-12).all())


class TestReglas(unittest.TestCase):
    def test_niveles_riesgo_cerrados_a_la_izquierda(self):
        niveles = pa.niveles_riesgo(pd.Series([0.0, 0.2499, 0.25, 0.4999, 0.5, 0.75, 1.0]))
        self.assertEqual(list(niveles.astype(str)),
                         ["bajo", "bajo", "medio", "medio", "alto", "muy_alto", "muy_alto"])

    def test_bootstrap_y_diferencia_pareada(self):
        medias = pa.bootstrap_estratificado(np.ones(10), np.array([0, 1] * 5), n=50)
        self.assertTrue(np.allclose(medias, 1))
        tabla = pd.DataFrame({"horizonte": 2, "bloque": ["temporada_2022"] * 3 + ["temporada_2023"] * 3,
                              "ubigeo": ["200101"] * 6, "inicio": pd.date_range("2022-01-02", periods=6, freq="7D"),
                              "alerta_050": [3, 0, np.nan, 2, 2, -1]})
        dif = pa.diferencia_antelacion(tabla, tabla, "alerta_050").iloc[0]
        self.assertEqual((dif.diferencia, dif.ic95_inferior, dif.ic95_superior), (0.0, 0.0, 0.0))

    def _metricas(self, f1_22, f1_23, brier=0.1):
        return pd.DataFrame({"horizonte": 2, "bloque": list(pa.BLOQUES_SELECCION),
                             "f1_050": [f1_22, f1_23], "auprc": [0.5, 0.5],
                             "brier": [brier, brier], "razon_mae": [1.0, 1.0]})

    def _dif(self, inf, sup, d22, d23):
        return pd.DataFrame([{"horizonte": 2, "diferencia": (d22 + d23) / 2, "ic95_inferior": inf,
                              "ic95_superior": sup, "diferencia_temporada_2022": d22,
                              "diferencia_temporada_2023": d23}])

    def test_regla_de_decision(self):
        ref = self._metricas(0.50, 0.70)
        rangos = pd.DataFrame({"horizonte": 2, "bloque": list(pa.BLOQUES_SELECCION),
                               "f1_050": 0.02, "auprc": 0.02, "brier": 0.002, "razon_mae": 0.02})
        neutra = self._dif(-0.05, 0.05, 0.0, 0.0)
        veredicto = lambda cand, dif=neutra: pa.decidir(cand, ref, rangos, dif).veredicto.iloc[0]
        self.assertEqual(veredicto(self._metricas(0.53, 0.73)), "gana")
        self.assertEqual(veredicto(self._metricas(0.53, 0.71)), "empate")      # solo una temporada
        self.assertEqual(veredicto(self._metricas(0.47, 0.70)), "empate")       # empeora solo en 2022
        self.assertEqual(veredicto(self._metricas(0.47, 0.67)), "pierde")       # empeora en ambas
        self.assertEqual(veredicto(self._metricas(0.50, 0.70), self._dif(0.01, 0.10, 0.05, 0.06)), "gana")
        self.assertEqual(veredicto(self._metricas(0.47, 0.67), self._dif(0.01, 0.10, 0.05, 0.06)),
                         "compensa (empate)")
        self.assertEqual(veredicto(self._metricas(0.53, 0.73, brier=0.11)), "compensa (empate)")

    def test_regla_simetrica(self):
        """A pierde frente a B si y solo si B gana frente a A (y compensa/empate son espejo)."""
        rng = np.random.default_rng(11)
        espejo = {"gana": "pierde", "pierde": "gana", "empate": "empate", "compensa (empate)": "compensa (empate)"}
        vistos = set()
        for _ in range(3000):
            a, b = {}, {}
            for m in ("f1_050", "auprc", "brier", "razon_mae"):
                a[m] = rng.uniform(0.4, 0.6, 2)
                b[m] = a[m] + rng.choice([-0.05, -0.01, 0.0, 0.01, 0.05], 2)
            ma = pd.DataFrame({"horizonte": 2, "bloque": list(pa.BLOQUES_SELECCION), **a})
            mb = pd.DataFrame({"horizonte": 2, "bloque": list(pa.BLOQUES_SELECCION), **b})
            rangos = pd.DataFrame({"horizonte": 2, "bloque": list(pa.BLOQUES_SELECCION),
                                   "f1_050": 0.02, "auprc": 0.02, "brier": 0.02, "razon_mae": 0.02})
            centro = rng.choice([-0.08, 0.0, 0.08])
            d22, d23 = centro + rng.choice([-0.03, 0.03], 2)
            ab = self._dif(centro - 0.05, centro + 0.05, d22, d23)
            ba = self._dif(-centro - 0.05, -centro + 0.05, -d22, -d23)
            v_ab = pa.decidir(ma, mb, rangos, ab).veredicto.iloc[0]
            v_ba = pa.decidir(mb, ma, rangos, ba).veredicto.iloc[0]
            self.assertEqual(v_ba, espejo[v_ab])
            vistos.add(v_ab)
        self.assertEqual(vistos, set(espejo))  # la prueba recorrió los cuatro veredictos

    def test_umbral_empate_rellena_h3_con_el_mayor(self):
        r2 = pd.DataFrame({"horizonte": 2, "bloque": ["temporada_2022"], "f1_050": [0.01]})
        r4 = pd.DataFrame({"horizonte": 4, "bloque": ["temporada_2022"], "f1_050": [0.03]})
        u = pa.umbral_empate(r2, r4).set_index("horizonte")
        self.assertEqual(u.loc[3, "f1_050"], 0.03)
        self.assertEqual(u.loc[2, "f1_050"], 0.01)


if __name__ == "__main__":
    unittest.main()
