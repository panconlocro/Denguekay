"""Aplanado de reportes y registro anidado de experimentos en MLflow."""

import os
import tempfile
import unittest
from pathlib import Path

from src.modeling.seguimiento_mlflow import (
    folds_de_variante, metricas_fold, parametros_variante, registrar_reporte,
    resumen_variante, seleccionadas_por_horizonte,
)


def fold(bloque: str, tipo: str, f1_cls: float, f1_reg: float, *, calibracion: bool = False) -> dict:
    alerta = {"n": 10, "positivos": 2, "vp": 1, "fp": 1, "fn": 1, "vn": 7,
              "precision": 0.5, "recall": 0.5, "auprc": 0.4}
    salida = {
        "horizonte": 2, "variante": "base", "bloque": bloque, "tipo": tipo,
        "corte_ajuste": "2021-08-21", "n_entrenamiento": 100, "n_prueba": 10,
        "positivos_entrenamiento": 5,
        "regresion": {"conteos": {"mae": 1.0, "rmse": 2.0, "mae_log1p": 0.3, "sesgo_medio": 0.1},
                      "alerta_derivada": {**alerta, "f1": f1_reg}},
        "clasificacion": {"umbral_probabilidad": 0.2, "alerta_directa": {**alerta, "f1": f1_cls},
                          "brier": 0.05},
        "persistencia": {"conteos": {"mae": 1.5, "rmse": 2.5, "mae_log1p": 0.4, "sesgo_medio": 0.0},
                         "alerta_derivada": {**alerta, "f1": None, "auprc": None}},
    }
    if calibracion:
        salida["calibracion"] = {"filas": 50, "positivos": 4, "ultima_etiqueta_cerrada": "2021-08-21",
                                 "seleccion_umbral": {"umbral": 0.3, "f1_validacion_agregado": 0.6}}
    return salida


def reporte_sintetico() -> dict:
    return {
        "experimento": "prueba", "version_xgboost": "3.x", "sha256_manifest_gold": "abc",
        "parametros": {"max_depth": 3, "learning_rate": 0.05},
        "horizontes": {"2": {
            "archivo_gold": "no_existe.csv", "sha256_gold": "def", "filas_gold": 100,
            "variantes": {
                "base": {"columnas": ["a", "b"], "seleccion_umbral": {"umbral": 0.2, "f1_validacion_agregado": 0.5},
                         "folds_validacion": [fold("temporada_2022", "validacion", 0.4, 0.6),
                                              fold("temporada_2023", "validacion", 0.6, 0.8)],
                         "folds_prueba": [fold("temporada_2024", "prueba_principal", 0.7, 0.7)]},
                "mas_x": {"columnas": ["a", "b", "x"],
                          "folds": [fold("temporada_2022", "seleccion", 0.5, 0.5, calibracion=True)],
                          "sensibilidad_2025": fold("calendario_2025", "sensibilidad", 0.0, 0.0)},
            },
            "elegidas_solo_validacion": {"regresion": "base", "clasificacion": "mas_x"},
        }},
    }


class AplanadoTests(unittest.TestCase):
    def test_metricas_fold_usa_prefijos_y_omite_nulos(self):
        metricas, params = metricas_fold(fold("temporada_2022", "validacion", 0.4, 0.6, calibracion=True))
        self.assertEqual(metricas["cls_f1"], 0.4)
        self.assertEqual(metricas["reg_f1"], 0.6)
        self.assertEqual(metricas["reg_mae"], 1.0)
        self.assertEqual(metricas["cls_brier"], 0.05)
        self.assertEqual(metricas["cal_umbral"], 0.3)
        self.assertNotIn("pers_f1", metricas)  # None no se registra
        self.assertEqual(params["bloque"], "temporada_2022")
        self.assertEqual(params["cal_ultima_etiqueta_cerrada"], "2021-08-21")

    def test_encuentra_folds_con_cualquier_nombre(self):
        variantes = reporte_sintetico()["horizontes"]["2"]["variantes"]
        self.assertEqual(len(folds_de_variante(variantes["base"])), 3)
        self.assertEqual({f["bloque"] for f in folds_de_variante(variantes["mas_x"])},
                         {"temporada_2022", "calendario_2025"})

    def test_media_solo_de_validacion_y_por_bloque(self):
        folds = folds_de_variante(reporte_sintetico()["horizontes"]["2"]["variantes"]["base"])
        resumen = resumen_variante(folds)
        self.assertAlmostEqual(resumen["validacion_media.cls_f1"], 0.5)
        self.assertAlmostEqual(resumen["validacion_media.reg_f1"], 0.7)
        self.assertEqual(resumen["validacion_media.n_bloques"], 2)
        self.assertEqual(resumen["temporada_2024.cls_f1"], 0.7)  # prueba no se promedia

    def test_seleccion_y_parametros_de_variante(self):
        bloque = reporte_sintetico()["horizontes"]["2"]
        self.assertEqual(seleccionadas_por_horizonte(bloque),
                         {"base": ["regresion"], "mas_x": ["clasificacion"]})
        por_familia = {"variantes": {"base": {}, "fija_a": {}, "anual_b": {}},
                       "elegidas_solo_validacion": {"fija": {"regresion": "fija_a", "clasificacion": "base"},
                                                    "anual": {"regresion": "anual_b", "clasificacion": "base"}},
                       "ganadora_por_temporada": {"fija": {"regresion": {"temporada_2021": "fija_a"}}}}
        self.assertEqual(seleccionadas_por_horizonte(por_familia),
                         {"fija_a": ["fija:regresion"], "base": ["fija:clasificacion", "anual:clasificacion"],
                          "anual_b": ["anual:regresion"]})
        params, metricas = parametros_variante(bloque["variantes"]["base"])
        self.assertEqual(params["n_columnas"], "2")
        self.assertEqual(metricas["seleccion_umbral.umbral"], 0.2)


def cerrar_motores_mlflow(carpeta):
    """En Windows, MLflow deja abierta su mlflow.db y el directorio temporal no se puede borrar.

    Se cierran solo los motores SQLAlchemy de la carpeta de la prueba; no cambia src/modeling.
    """
    import gc
    from sqlalchemy.engine import Engine

    for objeto in gc.get_objects():
        base = (objeto.url.database or "").replace("\\", "/").lower() if isinstance(objeto, Engine) else ""
        if base and Path(carpeta).as_posix().lower() in base:
            objeto.dispose()


class RegistroTests(unittest.TestCase):
    def test_registra_padre_variantes_y_folds_anidados(self):
        import mlflow

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            uri = f"sqlite:///{(tmp / 'mlflow.db').as_posix()}"
            salida = tmp / "salida"
            salida.mkdir()
            (salida / "predicciones.csv").write_text("a\n1\n", encoding="utf-8")
            (salida / "xgb_h2_base_regresion_temporada_2024.json").write_text("{}", encoding="utf-8")
            metricas = tmp / "reporte.json"
            metricas.write_text("{}", encoding="utf-8")
            anterior = os.environ.pop("MLFLOW_TRACKING_URI", None)
            try:
                run_id = registrar_reporte(
                    "prueba", reporte_sintetico(), metricas_path=metricas, salida_dir=salida,
                    calidad_datos={"exito": True, "suites": {"gold_h2": {"porcentaje_exito": 100.0, "fallidas_n": 0}}},
                    tracking_uri=uri)
                runs = mlflow.search_runs(experiment_names=["denguekay/prueba"])
                cliente = mlflow.MlflowClient(tracking_uri=uri)
                artefactos_padre = {a.path for a in cliente.list_artifacts(run_id)}
                fold_2024 = runs[runs["tags.mlflow.runName"] == "h2 · base · temporada_2024"].iloc[0]
                modelos = [a.path for a in cliente.list_artifacts(fold_2024.run_id, "modelos")]
            finally:
                if anterior is not None:
                    os.environ["MLFLOW_TRACKING_URI"] = anterior
                cerrar_motores_mlflow(tmp)
            # 1 padre + 2 variantes + 5 folds
            self.assertEqual(len(runs), 8)
            self.assertEqual(runs["tags.nivel"].value_counts().to_dict(), {"fold": 5, "variante": 2})
            variantes = runs[runs["tags.nivel"] == "variante"]
            folds = runs[runs["tags.nivel"] == "fold"]
            self.assertTrue((variantes["tags.mlflow.parentRunId"] == run_id).all())
            self.assertTrue(folds["tags.mlflow.parentRunId"].isin(set(variantes.run_id)).all())
            self.assertEqual(modelos, ["modelos/xgb_h2_base_regresion_temporada_2024.json"])
            self.assertTrue({"reporte", "salidas", "calidad_datos"} <= artefactos_padre)
            variante = runs[runs["tags.mlflow.runName"] == "h2 · base"].iloc[0]
            self.assertAlmostEqual(variante["metrics.validacion_media.cls_f1"], 0.5)
            self.assertEqual(variante["tags.seleccionada_en_validacion"], "regresion")
            self.assertTrue((tmp / "mlartifacts").exists())


if __name__ == "__main__":
    unittest.main()
