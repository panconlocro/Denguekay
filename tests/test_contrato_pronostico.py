"""Pruebas del contrato de disponibilidad para dos y cuatro semanas."""

import unittest

import pandas as pd

from src.validation.contrato_pronostico import auditar_origen, observaciones_disponibles


class ContratoPronosticoTests(unittest.TestCase):
    def setUp(self):
        fechas = pd.date_range("2020-12-06", periods=8, freq="W-SUN")
        self.panel = pd.DataFrame({
            "ubigeo": ["200101"] * len(fechas) + ["200102"] * len(fechas),
            "anio": [2020] * 4 + [2021] * 4 + [2020] * 4 + [2021] * 4,
            "semana": [50, 51, 52, 53, 1, 2, 3, 4] * 2,
            "semana_inicio": list(fechas) * 2,
        })

    def test_origen_cuatro_semanas_y_cruce_de_anio(self):
        audit = auditar_origen(self.panel)
        primer_distrito = audit.iloc[:8]
        self.assertTrue(primer_distrito.iloc[:4]["origen_inicio"].isna().all())
        self.assertEqual(primer_distrito.iloc[4]["origen_inicio"], pd.Timestamp("2020-12-06"))
        self.assertEqual(primer_distrito.iloc[4]["origen_cierre"], pd.Timestamp("2020-12-12"))
        self.assertEqual(int(audit["origen_inicio"].notna().sum()), 8)

    def test_origen_dos_semanas_y_cruce_de_anio(self):
        audit = auditar_origen(self.panel, horizonte=2)
        primer_distrito = audit.iloc[:8]
        self.assertTrue(primer_distrito.iloc[:2]["origen_inicio"].isna().all())
        self.assertEqual(primer_distrito.iloc[4]["origen_inicio"], pd.Timestamp("2020-12-20"))
        self.assertEqual(primer_distrito.iloc[4]["origen_cierre"], pd.Timestamp("2020-12-26"))
        self.assertEqual(int(audit["origen_inicio"].notna().sum()), 12)

    def test_dos_semanas_rechaza_t_menos_uno_y_publicacion_tardia(self):
        audit = auditar_origen(self.panel.iloc[:8], horizonte=2)
        objetivo = audit["semana_inicio"]
        origen = audit["origen_inicio"]
        permitido = observaciones_disponibles(audit, origen, origen + pd.Timedelta(days=6))
        posterior = observaciones_disponibles(
            audit, objetivo - pd.Timedelta(weeks=1),
            objetivo - pd.Timedelta(days=1))
        tardia = observaciones_disponibles(audit, origen, origen + pd.Timedelta(days=7))
        self.assertEqual(permitido.tolist(), [False] * 2 + [True] * 6)
        self.assertFalse(posterior.any())
        self.assertFalse(tardia.any())

    def test_semana_t_menos_uno_no_esta_disponible(self):
        audit = auditar_origen(self.panel.iloc[:8])
        objetivo = audit["semana_inicio"]
        origen = objetivo - pd.Timedelta(weeks=4)
        permitido = observaciones_disponibles(audit, origen, origen + pd.Timedelta(days=6))
        filtrado = observaciones_disponibles(
            audit, objetivo - pd.Timedelta(weeks=1),
            objetivo - pd.Timedelta(weeks=1) + pd.Timedelta(days=6),
        )
        self.assertEqual(permitido.tolist(), [False] * 4 + [True] * 4)
        self.assertFalse(filtrado.any())

    def test_publicacion_tardia_invalida_dato_del_origen(self):
        audit = auditar_origen(self.panel.iloc[:8])
        origen = audit["origen_inicio"]
        disponibilidad = origen + pd.Timedelta(days=7)
        self.assertFalse(observaciones_disponibles(audit, origen, disponibilidad).any())

    def test_hueco_semanal_se_rechaza(self):
        panel = self.panel.drop(index=2)
        with self.assertRaisesRegex(ValueError, "huecos"):
            auditar_origen(panel)

    def test_llave_duplicada_se_rechaza(self):
        panel = pd.concat([self.panel, self.panel.iloc[[0]]], ignore_index=True)
        with self.assertRaisesRegex(ValueError, "duplicadas"):
            auditar_origen(panel)


if __name__ == "__main__":
    unittest.main()
