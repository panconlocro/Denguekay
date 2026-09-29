"""Tests de validar_panel() con paneles sintéticos (no dependen de data/)."""

import unittest

import pandas as pd

from src.eda.carga import validar_panel


def panel(n_semanas=4, distritos=("200101", "200102")):
    filas = []
    for ubigeo in distritos:
        for i in range(n_semanas):
            fecha = pd.Timestamp("2017-01-01") + pd.Timedelta(days=7 * i)
            filas.append({"ubigeo": ubigeo, "anio": 2017, "semana": i + 1,
                          "semana_inicio": fecha, "casos_Dengue": i})
    return pd.DataFrame(filas)


class ValidarPanelTests(unittest.TestCase):
    def test_panel_valido_no_reporta_problemas(self):
        self.assertEqual(validar_panel(panel()), [])

    def test_detecta_llave_duplicada(self):
        df = pd.concat([panel(), panel().head(1)], ignore_index=True)
        self.assertTrue(any("duplicada" in p for p in validar_panel(df)))

    def test_detecta_ubigeo_sin_ceros(self):
        df = panel(distritos=("20101", "200102"))
        self.assertTrue(any("6 dígitos" in p for p in validar_panel(df)))

    def test_detecta_hueco_de_semanas(self):
        df = panel().drop(index=1)
        problemas = validar_panel(df)
        self.assertTrue(any("no consecutivas" in p or "desbalanceado" in p for p in problemas))

    def test_detecta_columna_faltante(self):
        df = panel().drop(columns=["casos_Dengue"])
        self.assertTrue(any("Faltan columnas" in p for p in validar_panel(df)))


if __name__ == "__main__":
    unittest.main()
