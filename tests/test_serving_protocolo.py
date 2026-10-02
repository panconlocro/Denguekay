"""Importación de OOS y serialización contrastadas con salidas reales."""

from copy import deepcopy
import unittest

import numpy as np
import pandas as pd

from serving_soporte import protocolo_muestra
from src.db.modelos import VersionModelo
from src.modeling.train import ajustar_modelos, conteos_desde_log1p, evaluar_fold
from src.modeling.validacion_temporal_compacta import variantes_compactas
from src.serving.artefactos import predecir_con_version, serializar_booster
from src.serving.protocolo import verificar_bloque


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
        self.fold = evaluar_fold(cast, horizonte=2, variante="base_6_poblacion_2017", bloque="temporada_2023",
            tipo=original["tipo"], corte=pd.Timestamp(original["corte_ajuste"]),
            n_entrenamiento=original["n_entrenamiento"], umbral_clasificacion=original["clasificacion"]["umbral_probabilidad"])

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
        cols = variantes_compactas(2)["base_6_poblacion_2017"]
        reg, cls = ajustar_modelos(datos, cols)
        vectores = datos.iloc[-6:][cols]
        for tipo, modelo, esperado in (("clasificacion", cls, cls.predict_proba(vectores)[:, 1]),
            ("regresion", reg, conteos_desde_log1p(reg.predict(vectores)))):
            version = VersionModelo(tipo=tipo, columnas=cols, artefacto=serializar_booster(modelo))
            np.testing.assert_array_equal(predecir_con_version(version, vectores.to_dict("records")), esperado)

    def test_casos_reales_entre_umbral_f1_y_05_no_son_alertas_visibles(self):
        umbral = self.fold["clasificacion"]["umbral_probabilidad"]
        discrepantes = self.pred.loc[self.pred.probabilidad_brote.ge(umbral) & self.pred.probabilidad_brote.lt(.5)]
        self.assertGreater(len(discrepantes), 0)


if __name__ == "__main__":
    unittest.main()
