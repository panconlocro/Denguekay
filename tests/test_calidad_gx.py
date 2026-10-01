"""Las suites de Great Expectations aceptan datos válidos y detectan errores típicos."""

import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from src.modeling.features import columnas_gold
from src.processing.socio_interpolacion import SOCIO_COLUMNS
from src.validation.calidad_gx import ValidacionDatosError, obtener_contexto, validar_dataframe
from src.validation.expectations_gold import expectativas_gold
from src.validation.expectations_integrado import WEATHER_COLUMNS, expectativas_integrado_gx

UBIGEOS = ["200101", "200102"]


def gold_sintetico(h: int = 2, semanas: int = 60) -> pd.DataFrame:
    filas = []
    fechas = pd.date_range("2023-07-02", periods=semanas, freq="W-SUN")
    for ubigeo in UBIGEOS:
        for i, fecha in enumerate(fechas):
            con_origen = i >= h
            fila = {c: 0.3 for c in columnas_gold(h, con_brote=True)}
            fila.update({
                "provincia": "Piura", "distrito": "Piura", "distrito_key": "PIURA", "ubigeo": ubigeo,
                "anio": int(fecha.year), "semana": int(fecha.isocalendar().week), "semana_inicio": fecha,
                "casos_Dengue": 3 if i == 5 else 0, "umbral_brote_casos": 1.0, "brote": int(i == 5),
                "origen_inicio": fecha - pd.Timedelta(weeks=h) if con_origen else pd.NaT,
                "origen_cierre": fecha - pd.Timedelta(weeks=h) + pd.Timedelta(days=6) if con_origen else pd.NaT,
                "semana_epi_seno": float(np.sin(i)), "semana_epi_coseno": float(np.cos(i)),
                "casos_semanas_positivas_4_h2": 1.0, "hum_rel_media_media5_h2": 80.0,
                "log_poblacion_censo_2017": 9.0, "log_poblacion_anual": 9.1,
                "socio_2017_disponible_al_origen": True,
                "socio_fracciones_interpoladas_con_2025": True,
            })
            filas.append(fila)
    return pd.DataFrame(filas)[columnas_gold(h, con_brote=True)]


def integrado_sintetico() -> pd.DataFrame:
    fechas = pd.date_range("2023-07-02", periods=4, freq="W-SUN")
    filas = []
    for ubigeo in UBIGEOS:
        for fecha in fechas:
            fila = {"provincia": "Piura", "distrito": "Piura", "lat": -5.2, "lon": -80.6,
                    "ubigeo": ubigeo, "anio": int(fecha.year),
                    "semana": int(fecha.isocalendar().week), "semana_inicio": fecha,
                    "temp_media": 25.0, "temp_max": 31.0, "temp_min": 20.0,
                    "precip_total_mm": 5.0, "lluvia_total_mm": 5.0, "hum_rel_media": 70.0,
                    "viento_max": 20.0, "radiacion_total": 150.0, "et0_total": 30.0,
                    "casos_Dengue": 1}
            fila.update({c: 0.4 for c in SOCIO_COLUMNS})
            fila["poblacion"] = 5000
            filas.append(fila)
    return pd.DataFrame(filas)


class SuitesGXTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.contexto = obtener_contexto(Path(cls._tmp.name))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def validar_gold(self, datos, lanzar=False):
        return validar_dataframe(datos, nombre_suite="gold_h2_test", expectativas=expectativas_gold(2, UBIGEOS),
                                 nombre_activo="gold_h2_test", contexto=self.contexto,
                                 lanzar=lanzar, actualizar_docs=False)

    def fallidas(self, resumen):
        return {(f["expectativa"], f.get("column") or str(f.get("column_list") or f.get("column_A")))
                for f in resumen["fallidas"]}

    def test_gold_valido_pasa(self):
        resumen = self.validar_gold(gold_sintetico())
        self.assertTrue(resumen["exito"], resumen["fallidas"])
        self.assertGreater(resumen["evaluadas"], 50)

    def test_gold_detecta_llave_ubigeo_etiqueta_y_fuga(self):
        datos = gold_sintetico()
        datos = pd.concat([datos, datos.iloc[[0]]], ignore_index=True)        # llave duplicada
        datos.loc[1, "ubigeo"] = "20101"                                       # ubigeo sin cero
        datos.loc[2, "brote"] = 2                                              # etiqueta inválida
        datos.loc[3, "fraccion_rural_2017"] = 1.5                              # fracción fuera de [0, 1]
        datos.loc[4, "origen_cierre"] = datos.loc[4, "semana_inicio"]          # fuga temporal
        fallidas = self.fallidas(self.validar_gold(datos))
        esperadas = {
            ("expect_compound_columns_to_be_unique", "['ubigeo', 'anio', 'semana']"),
            ("expect_column_values_to_match_regex", "ubigeo"),
            ("expect_column_values_to_be_in_set", "brote"),
            ("expect_column_values_to_be_between", "fraccion_rural_2017"),
            ("expect_column_pair_values_a_to_be_greater_than_b", "semana_inicio"),
        }
        self.assertTrue(esperadas <= fallidas, fallidas)

    def test_gold_detecta_columna_faltante_y_lanza(self):
        datos = gold_sintetico().drop(columns=["brote"])
        with self.assertRaises(ValidacionDatosError) as error:
            self.validar_gold(datos, lanzar=True)
        self.assertFalse(error.exception.resumen["exito"])

    def test_integrado_valido_y_errores_fisicos(self):
        kwargs = dict(nombre_suite="integrado_test", expectativas=expectativas_integrado_gx(UBIGEOS),
                      nombre_activo="integrado_test", contexto=self.contexto,
                      lanzar=False, actualizar_docs=False)
        self.assertTrue(validar_dataframe(integrado_sintetico(), **kwargs)["exito"])
        datos = integrado_sintetico()
        datos.loc[0, "temp_min"] = 35.0              # mínima mayor que máxima
        datos.loc[1, "hum_rel_media"] = 120.0         # humedad imposible
        datos.loc[2, "casos_Dengue"] = -1             # casos negativos
        datos.loc[3, "lat"] = 10.0                    # fuera de Piura
        fallidas = self.fallidas(validar_dataframe(datos, **kwargs))
        self.assertIn(("expect_column_pair_values_a_to_be_greater_than_b", "temp_max"), fallidas)
        self.assertIn(("expect_column_values_to_be_between", "hum_rel_media"), fallidas)
        self.assertIn(("expect_column_values_to_be_between", "casos_Dengue"), fallidas)
        self.assertIn(("expect_column_values_to_be_between", "lat"), fallidas)
        self.assertTrue(set(WEATHER_COLUMNS) <= set(datos))


if __name__ == "__main__":
    unittest.main()
