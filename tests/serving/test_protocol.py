"""Importación de OOS y serialización contrastadas con salidas reales."""

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from serving_soporte import protocolo_muestra
from denguekay.db.models import ModelVersion
from denguekay.model.train import fit_models, counts_from_log1p, evaluate_fold
from denguekay.evaluation.compact_validation import compact_variants
from denguekay.serving.storage import AlmacenamientoLocal
from denguekay.serving.artifacts import predecir_con_version, serializar_booster, sha256_bytes
from denguekay.serving.protocol import verificar_bloque


class TestContratoProtocolo(unittest.TestCase):
    def setUp(self):
        self.protocolo = protocolo_muestra()
        pred = self.protocolo.predicciones
        self.pred = pred.loc[pred.horizonte.eq(2) & pred.variante.eq("base_6_poblacion_2017")].copy()
        real = self.protocolo.datos[2]
        self.real = real.merge(self.pred[["ubigeo", "anio", "semana"]], on=["ubigeo", "anio", "semana"])
        cast = self.pred.copy()
        cast[["probabilidad_brote", "casos_predichos"]] = cast[["probabilidad_brote", "casos_predichos"]].astype("float32")
        original = self.protocolo.particiones[2, "base_6_poblacion_2017", "temporada_2023"]["fold"]
        self.fold = evaluate_fold(cast, horizon=2, variant="base_6_poblacion_2017", block="temporada_2023",
            kind=original["tipo"], cutoff=pd.Timestamp(original["corte_ajuste"]),
            n_training=original["n_entrenamiento"], classification_threshold=original["clasificacion"]["umbral_probabilidad"])

    def verificar(self, pred, real=None, fold=None):
        verificar_bloque(pred, self.real if real is None else real, self.fold if fold is None else fold,
                         2, "base_6_poblacion_2017")

    def test_metricas_calculadas_del_subconjunto_y_fechas_coinciden(self):
        self.verificar(self.pred)

    def test_no_acepta_cobertura_fecha_observado_o_persistencia_alterados(self):
        with self.assertRaises(ValueError):
            self.verificar(self.pred.iloc[:-1])
        for c in ("origen_cierre", "casos_Dengue", "casos_lag_2"):
            modificado = self.pred.copy()
            modificado.loc[modificado.index[0], c] += pd.Timedelta(days=7) if c == "origen_cierre" else 1
            with self.subTest(c=c), self.assertRaises(ValueError):
                self.verificar(modificado)
        fold = deepcopy(self.fold)
        fold["regresion"]["conteos"]["mae"] += 1
        with self.assertRaises(ValueError):
            self.verificar(self.pred, fold=fold)

    def test_inferencia_del_json_igual_a_estimadores_originales(self):
        datos = self.protocolo.datos[2]
        cols = compact_variants(2)["base_6_poblacion_2017"]
        reg, cls = fit_models(datos, cols)
        # El servicio predice en CPU; en GPU el estimador difiere en ~1 ULP de float32.
        reg.set_params(device="cpu")
        cls.set_params(device="cpu")
        vectores = datos.iloc[-6:][cols]
        with tempfile.TemporaryDirectory() as carpeta:
            almacenamiento = AlmacenamientoLocal(Path(carpeta))
            for tarea, modelo, esperado in (("clasificacion", cls, cls.predict_proba(vectores)[:, 1]),
                ("regresion", reg, counts_from_log1p(reg.predict(vectores)))):
                contenido = serializar_booster(modelo)
                ruta = f"modelos/{tarea}.json"
                almacenamiento.guardar(ruta, contenido)
                version = ModelVersion(codigo=tarea, tarea=tarea, variables=cols, ruta_artefacto=ruta,
                                        sha256_artefacto=sha256_bytes(contenido))
                np.testing.assert_array_equal(predecir_con_version(version, vectores.to_dict("records"), almacenamiento), esperado)

    def test_casos_reales_entre_umbral_f1_y_05_no_son_alertas_visibles(self):
        umbral = self.fold["clasificacion"]["umbral_probabilidad"]
        discrepantes = self.pred.loc[self.pred.probabilidad_brote.ge(umbral) & self.pred.probabilidad_brote.lt(.5)]
        self.assertGreater(len(discrepantes), 0)


if __name__ == "__main__":
    unittest.main()
