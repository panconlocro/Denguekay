"""Diccionario de variables de la V4 (HU0006-1 y HU0006-3): cada columna del modelo vigente tiene entrada completa."""

import json
import unittest
from unittest import mock

from denguekay.config.paths import V4_FROZEN, VARIABLE_DICTIONARY
from denguekay.features.b3 import GEO, NINO, WEATHER
from denguekay.model import horizon_strategies as eh
from denguekay.model import variable_dictionary as dv


class TestDiccionarioV4(unittest.TestCase):
    def test_las_16_columnas_de_la_v4_tienen_entrada_completa(self):
        columns = dv.v4_columns()
        self.assertEqual(len(columns), 16)
        table = dv.v4_dictionary()
        self.assertEqual(list(table.variable), columns)
        for field in dv.V4_FIELDS:
            with self.subTest(field=field):
                self.assertTrue(table[field].map(lambda text: bool(str(text).strip())).all())

    def test_las_columnas_coinciden_con_el_codigo_de_las_variables(self):
        columns = dv.v4_columns()
        self.assertEqual(columns[:6], eh.GENERIC)
        self.assertEqual(columns[9:12], list(GEO))
        self.assertEqual(columns[12:], [WEATHER["hum_rel_media"][1], WEATHER["precip_total_mm"][1],
                                        WEATHER["temp_media"][1], NINO])

    def test_coinciden_con_el_paquete_congelado_cuando_esta_en_disco(self):
        package = V4_FROZEN / "paquete.json"
        if not package.is_file():
            self.skipTest("el paquete congelado de la V4 no está en models/experimentos (se extrae del Release)")
        frozen = json.loads(package.read_text(encoding="utf-8"))["columnas"]["b3_obs"]
        self.assertEqual(dv.v4_columns(), frozen)

    def test_una_columna_sin_entrada_hace_fallar_el_diccionario(self):
        with self.assertRaisesRegex(ValueError, "sin entrada"):
            dv.v4_dictionary([*dv.v4_columns(), "variable_nueva"])

    def test_una_entrada_que_no_es_columna_hace_fallar_el_diccionario(self):
        with self.assertRaisesRegex(ValueError, "no son columnas"):
            dv.v4_dictionary(dv.v4_columns()[:-1])

    def test_un_campo_vacio_o_ausente_hace_fallar_el_diccionario(self):
        for field in dv.V4_FIELDS:
            for broken in ("", "   ", None):
                with self.subTest(field=field, value=broken):
                    entry = {**dv.V4_DEFINITIONS["hist_lag_a"], field: broken}
                    with mock.patch.dict(dv.V4_DEFINITIONS, {"hist_lag_a": entry}):
                        with self.assertRaisesRegex(ValueError, f"hist_lag_a.{field}"):
                            dv.v4_dictionary()
        entry = {k: v for k, v in dv.V4_DEFINITIONS["hist_lag_a"].items() if k != "rezago"}
        with mock.patch.dict(dv.V4_DEFINITIONS, {"hist_lag_a": entry}):
            with self.assertRaisesRegex(ValueError, "hist_lag_a.rezago"):
                dv.v4_dictionary()

    def test_cada_variable_tiene_un_grupo_y_el_documento_las_nombra_todas(self):
        grouped = [column for _, members in dv.V4_GROUPS for column in members]
        self.assertEqual(sorted(grouped), sorted(dv.v4_columns()))
        text = dv.v4_document()
        for column in dv.v4_columns():
            self.assertIn(f"### `{column}`", text)
        self.assertLess(text.index("## V4 vigente"), text.index("## Histórico: v2"))

    def test_el_documento_versionado_es_el_que_genera_el_codigo(self):
        committed = VARIABLE_DICTIONARY.read_bytes().decode("utf-8").replace("\r\n", "\n")
        self.assertEqual(committed, dv.v4_document().replace("\r\n", "\n"),
                         "regenere con: python -m denguekay.model.variable_dictionary")


if __name__ == "__main__":
    unittest.main()
