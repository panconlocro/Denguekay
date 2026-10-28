"""La lista de candidatos no debe admitir etiquetas ni columnas sin contrato."""

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from denguekay.features.model_input_contract import (
    NON_PREDICTORS, predictor_families, summarize_ablations,
    validate_model_columns,
)
from denguekay.features.gold import gold_columns


class ContratoXGBoostTests(unittest.TestCase):
    def test_familias_particionan_gold_sin_fuga_para_ambos_horizontes(self):
        for h in (2, 4):
            with self.subTest(horizonte=h):
                gold = pd.DataFrame(columns=gold_columns(h, with_outbreak=True))
                familias = validate_model_columns(
                    gold, {"columnas_no_predictoras": list(NON_PREDICTORS)}, h,
                )
                predictoras = [c for cols in familias.values() for c in cols]
                self.assertEqual(len(predictoras), 34)
                self.assertTrue(set(predictoras).isdisjoint(NON_PREDICTORS))
                self.assertEqual(set(gold), set(predictoras) | set(NON_PREDICTORS))
                self.assertIn(f"casos_lag_{h}", predictoras)
                self.assertNotIn(f"casos_lag_{6 - h}", predictoras)

    def test_manifest_debe_excluir_anio_y_semana(self):
        gold = pd.DataFrame(columns=gold_columns(4, with_outbreak=True))
        declaradas = [c for c in NON_PREDICTORS if c not in ("anio", "semana")]
        with self.assertRaisesRegex(ValueError, "exclusiones"):
            validate_model_columns(gold, {"columnas_no_predictoras": declaradas}, 4)

    def test_rechaza_columna_inesperada_o_etiqueta_ausente(self):
        gold = pd.DataFrame(columns=gold_columns(2, with_outbreak=True))
        for columnas in (gold.drop(columns="brote"), gold.assign(casos_lag_1=[])):
            with self.assertRaisesRegex(ValueError, "esquema gold"):
                validate_model_columns(
                    columnas, {"columnas_no_predictoras": list(NON_PREDICTORS)}, 2,
                )

    def test_horizonte_invalido(self):
        with self.assertRaisesRegex(ValueError, "horizonte"):
            predictor_families(7)

    def test_ablacion_compara_mismo_corte_y_referencia(self):
        base = {"horizonte": 4, "temporada": 2024, "modelo": "historia_calendario",
                "mae_casos": 6.0, "n_entrenamiento": 100, "n_prueba": 20,
                "primera_semana_prueba": "2023-08-27", "corte_ajuste": "2023-08-05"}
        clima = {**base, "modelo": "historia_calendario_clima", "mae_casos": 5.5}
        socio_clima = {**base, "modelo": "mas_clima", "mae_casos": 5.5}
        socio_completo = {**base, "modelo": "mas_clima_poblacion_y_eje_anual",
                         "mae_casos": 5.4}
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta)
            (ruta / "fase4_clima.json").write_text(json.dumps({"resultados": [base, clima]}))
            social = ruta / "fase5_sociodemografia.json"
            social.write_text(json.dumps({"resultados": [base, socio_clima, socio_completo]}))
            resumen = summarize_ablations(ruta)
            self.assertEqual(resumen["clima"]["4"]["historia_calendario_clima"]
                             ["delta_mae_casos_por_temporada"]["2024"], -0.5)
            self.assertEqual(resumen["sociodemografia"]["4"]
                             ["mas_clima_poblacion_y_eje_anual"]["referencia"], "mas_clima")
            self.assertEqual(resumen["sociodemografia"]["4"]
                             ["mas_clima_poblacion_y_eje_anual"]
                             ["delta_mae_casos_por_temporada"]["2024"], -0.1)
            social.write_text(json.dumps({"resultados": [
                base, socio_clima, {**socio_completo, "n_prueba": 19},
            ]}))
            with self.assertRaisesRegex(ValueError, "cortes/filas distintos"):
                summarize_ablations(ruta)


if __name__ == "__main__":
    unittest.main()
