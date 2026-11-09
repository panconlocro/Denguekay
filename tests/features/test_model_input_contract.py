"""La lista de candidatos no debe admitir etiquetas ni columnas sin contrato."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from denguekay.features.model_input_contract import (
    NON_PREDICTORS, audit_gold_backup, gold_backup_files, predictor_families, summarize_ablations,
    validate_model_columns,
)
from denguekay.config.paths import SILVER_INTEGRATED
from denguekay.features.gold import PERSISTED_NON_PREDICTORS, persisted_columns


class ContratoXGBoostTests(unittest.TestCase):
    def test_gold_persistido_son_llaves_etiqueta_y_variables_vigentes(self):
        from denguekay.model import frozen_configs as cf

        gold = pd.DataFrame(columns=persisted_columns(2))
        familias = validate_model_columns(gold, {"columnas_no_predictoras": list(PERSISTED_NON_PREDICTORS)}, 2)
        predictoras = [c for cols in familias.values() for c in cols]
        self.assertEqual((len(predictoras), len(gold.columns)), (15, 24))  # v2 (11) + d3 of the v3 (4)
        self.assertTrue(set(predictoras).isdisjoint(PERSISTED_NON_PREDICTORS))
        self.assertEqual(set(gold), set(predictoras) | set(PERSISTED_NON_PREDICTORS))
        self.assertEqual({*familias["a3"], *familias["b3"]}, set(cf.CONFIG_2026["columnas"]) - set(cf.eh.GENERIC))
        self.assertEqual({*familias["b3"], *familias["d3"]}, set(cf.CONFIG_V3["columnas"]) - set(cf.eh.GENERIC))
        self.assertEqual(familias["base_6"], predictor_families(2)["historia"] + predictor_families(2)["calendario"])
        self.assertFalse(set(gold) & {"provincia", "distrito", "distrito_key", "log_poblacion_censo_2017"})

    def test_manifest_debe_excluir_anio_y_semana(self):
        gold = pd.DataFrame(columns=persisted_columns(2))
        declaradas = [c for c in PERSISTED_NON_PREDICTORS if c not in ("anio", "semana")]
        with self.assertRaisesRegex(ValueError, "exclusiones"):
            validate_model_columns(gold, {"columnas_no_predictoras": declaradas}, 2)

    def test_rechaza_columna_inesperada_o_etiqueta_ausente(self):
        gold = pd.DataFrame(columns=persisted_columns(2))
        for columnas in (gold.drop(columns="brote"), gold.assign(casos_lag_1=[])):
            with self.assertRaisesRegex(ValueError, "esquema gold"):
                validate_model_columns(
                    columnas, {"columnas_no_predictoras": list(PERSISTED_NON_PREDICTORS)}, 2,
                )

    def test_la_v0_y_el_estudio_03_leen_el_respaldo(self):
        from denguekay.config.paths import GOLD_BACKUP
        from denguekay.evaluation.compact_validation import run_compact_validation
        from denguekay.model.train import run_experiment
        from denguekay.serving.predictors import v0_compact_xgb as v0

        self.assertEqual(v0.GOLD_DIR, GOLD_BACKUP)
        with tempfile.TemporaryDirectory() as carpeta:
            for correr in (run_experiment, run_compact_validation):
                with self.subTest(correr=correr.__name__), self.assertRaisesRegex(FileNotFoundError, "respaldo de gold"):
                    correr(gold_dir=Path(carpeta), audit=False, validate_data=False, log_mlflow=False)

    def test_respaldo_ausente_o_alterado_da_error_explicito(self):
        with tempfile.TemporaryDirectory() as carpeta:
            raiz = Path(carpeta)
            with self.assertRaisesRegex(FileNotFoundError, "Falta el respaldo de gold"):
                gold_backup_files(raiz)
            nombres = {h: f"{SILVER_INTEGRATED.stem}_h{h}_gold.csv" for h in (2, 4)}
            registros = {}
            for h, nombre in nombres.items():
                (raiz / nombre).write_text(f"h{h}\n", encoding="utf-8")
                registros[str(h)] = {"sha256": hashlib.sha256((raiz / nombre).read_bytes()).hexdigest()}
            (raiz / "manifest_fase6.json").write_text(json.dumps({"horizontes": registros}), encoding="utf-8")
            self.assertEqual(len(gold_backup_files(raiz)), 3)
            audit_gold_backup(raiz)
            (raiz / nombres[4]).write_text("alterado\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "h=4"):
                audit_gold_backup(raiz)

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
