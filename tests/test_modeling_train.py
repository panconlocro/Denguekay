"""Contrato temporal y separación de objetivos del primer XGBoost."""

import unittest

import numpy as np
import pandas as pd

from src.modeling.evaluate import (
    alertas_desde_conteos, metricas_alerta, metricas_conteos,
    seleccionar_umbral_f1,
)
from src.modeling.train import (
    columnas_variantes, predecir_fold, preparar_gold, separar_anio_calendario,
    separar_temporada,
)


def panel_sintetico(horizonte: int = 2, periods: int = 20) -> pd.DataFrame:
    filas = []
    semanas = pd.date_range("2023-07-02", periods=periods, freq="W-SUN")
    for ubigeo in ("200101", "200102"):
        for i, fecha in enumerate(semanas):
            casos = 2 if i in (2, 5, 9) else 0
            filas.append({
                "ubigeo": ubigeo, "anio": int(fecha.year), "semana": int(fecha.isocalendar().week),
                "semana_inicio": fecha,
                "origen_inicio": fecha - pd.Timedelta(weeks=horizonte) if i >= horizonte else pd.NaT,
                "origen_cierre": fecha - pd.Timedelta(weeks=horizonte) + pd.Timedelta(days=6) if i >= horizonte else pd.NaT,
                "casos_Dengue": casos, "umbral_brote_casos": 0.0,
                "brote": int(casos >= 2),
                f"casos_lag_{horizonte}": float(i - horizonte) if i >= horizonte else np.nan,
                f"casos_lag_{horizonte + 1}": float(i - horizonte - 1) if i >= horizonte + 1 else np.nan,
                f"casos_media_4_h{horizonte}": 0.5 if i >= horizonte + 3 else np.nan,
                f"casos_semanas_positivas_4_h{horizonte}": 1.0 if i >= horizonte + 3 else np.nan,
                "semana_epi_seno": float(np.sin(i)),
                "semana_epi_coseno": float(np.cos(i)),
            })
    return pd.DataFrame(filas)


class EntrenamientoTests(unittest.TestCase):
    def test_variantes_no_admiten_objetivos_ni_ubigeo(self):
        variantes = columnas_variantes(4)
        self.assertEqual({k: len(v) for k, v in variantes.items()},
                         {"historia_4": 4, "historia_4_mas_2": 6})
        for cols in variantes.values():
            self.assertFalse({"brote", "casos_Dengue", "umbral_brote_casos", "ubigeo"} & set(cols))

    def test_preparacion_conserva_gold_y_excluye_solo_arranque(self):
        original = panel_sintetico()
        copia = original.copy(deep=True)
        datos, excluidas = preparar_gold(original, 2)
        pd.testing.assert_frame_equal(original, copia)
        self.assertEqual(excluidas, 10)  # 5 semanas iniciales x 2 distritos
        self.assertEqual(len(datos), 30)
        self.assertFalse(datos[columnas_variantes(2)["historia_4_mas_2"]].isna().any().any())

    def test_split_separa_etiquetas_del_primer_origen(self):
        datos, _ = preparar_gold(panel_sintetico(), 2)
        train, test, corte = separar_temporada(datos, 2024)
        self.assertEqual(corte, test.origen_cierre.min())
        self.assertTrue((train.semana_inicio + pd.Timedelta(days=6) <= corte).all())
        self.assertTrue((test.semana_inicio > train.semana_inicio.max()).all())
        self.assertEqual(test.ubigeo.nunique(), 2)

    def test_corte_calendario_no_entrena_con_etiquetas_futuras(self):
        datos, _ = preparar_gold(panel_sintetico(periods=90), 2)
        train, test, corte = separar_anio_calendario(datos, 2025)
        self.assertTrue(test.anio.eq(2025).all())
        self.assertTrue((train.semana_inicio + pd.Timedelta(days=6) <= corte).all())

    def test_etiqueta_incoherente_y_duplicados_fallan(self):
        panel = panel_sintetico()
        panel.loc[panel.casos_Dengue.eq(2).idxmax(), "brote"] = 0
        with self.assertRaisesRegex(ValueError, "etiqueta brote"):
            preparar_gold(panel, 2)
        panel = panel_sintetico()
        with self.assertRaisesRegex(ValueError, "duplicadas"):
            preparar_gold(pd.concat([panel, panel.iloc[[0]]]), 2)

    def test_nulo_fuera_del_arranque_no_se_elimina_silenciosamente(self):
        panel = panel_sintetico()
        panel.loc[panel.index[10], "casos_lag_2"] = np.nan
        with self.assertRaisesRegex(ValueError, "fuera del arranque"):
            preparar_gold(panel, 2)

    def test_regresion_y_clasificacion_tienen_salida_distinta(self):
        real = np.array([0, 4, 0, 3])
        umbral = np.array([0, 2, 0, 5])
        pred = np.array([0, 3, 2, 6])
        alertas = alertas_desde_conteos(pred, umbral, 2)
        self.assertEqual(alertas.tolist(), [False, True, True, True])
        m = metricas_alerta(np.array([0, 1, 0, 0]), alertas,
                           puntaje=np.array([0.1, 0.8, 0.7, 0.6]))
        self.assertEqual((m["vp"], m["fp"], m["fn"]), (1, 2, 0))
        self.assertAlmostEqual(metricas_conteos(real, pred)["mae"], 1.5)

    def test_sin_positivos_no_inventa_auprc(self):
        m = metricas_alerta(np.zeros(3), np.zeros(3), puntaje=np.array([0.1, 0.2, 0.3]))
        self.assertIsNone(m["auprc"])
        self.assertIsNone(m["recall"])
        with self.assertRaisesRegex(ValueError, "No hay positivos"):
            seleccionar_umbral_f1(np.zeros(3), np.array([0.1, 0.2, 0.3]))

    def test_fit_smoke_ambos_modelos(self):
        datos, _ = preparar_gold(panel_sintetico(), 2)
        train, test, _ = separar_temporada(datos, 2024)
        pred, _, _ = predecir_fold(train, test, columnas_variantes(2)["historia_4"])
        self.assertEqual(len(pred), len(test))
        self.assertTrue(np.isfinite(pred.casos_predichos).all())
        self.assertTrue(pred.probabilidad_brote.between(0, 1).all())


if __name__ == "__main__":
    unittest.main()
