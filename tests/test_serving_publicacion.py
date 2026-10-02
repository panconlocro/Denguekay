"""Booster real en BD, publicación idempotente y alertas con historial."""

from copy import deepcopy
from datetime import date
from pathlib import Path
import tempfile
import unittest

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from backend_soporte import datos_muestra, motor_temporal
from serving_soporte import preparar_muestra
from src.db.modelos import ActivacionModelo, Alerta, EjecucionPrediccion, Prediccion, VersionModelo
from src.db.sesion import transaccion
from src.serving.artefactos import huella_json, predecir_con_version
from src.serving.cargar_datos import persistir_carga
from src.serving.modelos import reporte_servicio
from src.serving.publicacion import (activar_versiones_servicio, actualizar_alertas,
    construir_predicciones_vigentes, guardar_versiones, publicar_lote)
from src.serving.publicar import iniciar_ejecucion, publicar


class TestPublicacionReal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = tempfile.TemporaryDirectory()
        cls.datos = datos_muestra(Path(cls.base.name))
        cls.cfg, cls.protocolo, cls.futuros, cls.preparadas = preparar_muestra()

    @classmethod
    def tearDownClass(cls):
        cls.base.cleanup()

    def setUp(self):
        self.carpeta = tempfile.TemporaryDirectory()
        self.motor = motor_temporal(Path(self.carpeta.name))
        with transaccion(self.motor) as sesion:
            persistir_carga(sesion, self.datos)
            self.ejecucion_id, _ = iniciar_ejecucion(sesion, huella_json("prueba"), date(2025, 12, 27), self.protocolo.hashes)

    def tearDown(self):
        self.motor.dispose()
        self.carpeta.cleanup()

    def lote(self, sesion, **opciones):
        return publicar_lote(sesion, self.ejecucion_id, self.preparadas, self.futuros, self.protocolo,
                            (2, 4), self.cfg, None, [], 0, **opciones)

    def test_publicacion_idempotente_y_csv_original_conservado(self):
        with transaccion(self.motor) as sesion:
            primera = self.lote(sesion)
        with transaccion(self.motor) as sesion:
            segunda = self.lote(sesion)
            self.assertTrue(segunda["reutilizada"])
            self.assertFalse(primera["reutilizada"])
            self.assertEqual(primera["filas_generadas"], 24)
            self.assertEqual(sesion.scalar(select(func.count()).select_from(Prediccion)), 24)
            self.assertEqual(sesion.scalar(select(func.count()).select_from(VersionModelo)), 30)
            self.assertEqual(sesion.scalar(select(func.count()).select_from(ActivacionModelo)), 6)
            for p in sesion.scalars(select(Prediccion).where(Prediccion.tipo == "retrospectiva")):
                fuente = self.protocolo.predicciones
                base = fuente.loc[fuente.ubigeo.eq(p.ubigeo) & fuente.horizonte.eq(p.horizonte)
                                  & fuente.anio.eq(p.anio) & fuente.semana.eq(p.semana)]
                self.assertEqual(p.probabilidad, float(base.loc[base.variante.eq(self.cfg.variantes["clasificacion"]), "probabilidad_brote"].iloc[0]))
                self.assertEqual(p.casos_estimados, float(base.loc[base.variante.eq(self.cfg.variantes["regresion"]), "casos_predichos"].iloc[0]))
                self.assertEqual(p.estado_validacion, "experimental")
            for a in sesion.scalars(select(Alerta)):
                self.assertEqual(a.estado_validacion, "experimental")

    def test_artefacto_leido_de_bd_reproduce_inferencia_y_cero(self):
        with transaccion(self.motor) as sesion:
            self.lote(sesion)
        with transaccion(self.motor) as sesion:
            for p in sesion.scalars(select(Prediccion).where(Prediccion.tipo == "vigente")):
                for tipo, identificador, valor in (("clasificacion", p.version_clasificacion_id, p.probabilidad),
                    ("regresion", p.version_regresion_id, p.casos_estimados),
                    ("persistencia", p.version_persistencia_id, p.casos_persistencia)):
                    version = sesion.get(VersionModelo, identificador)
                    self.assertEqual(float(predecir_con_version(version, [p.caracteristicas])[0]), valor)
                    self.assertLessEqual(version.entrenamiento_corte, p.origen_cierre)
            baseline = sesion.scalar(select(VersionModelo).where(VersionModelo.tipo == "persistencia", VersionModelo.activa.is_(True)))
            self.assertEqual(predecir_con_version(baseline, [{baseline.columnas[0]: 0}])[0], 0)

    def test_version_historica_sin_booster_no_se_puede_reactivar(self):
        with transaccion(self.motor) as sesion:
            versiones = guardar_versiones(sesion, self.preparadas, None)
            historica = versiones[2, "clasificacion", "temporada_2023"]
            self.assertIsNone(historica.artefacto)
            self.assertIsNone(historica.mlflow_run_id)
            self.assertIsNone(historica.plataforma)
            self.assertFalse(historica.puede_activarse)
            with self.assertRaises(ValueError):
                predecir_con_version(historica, [{}])
            with self.assertRaises(ValueError):
                activar_versiones_servicio(sesion, {(2, "clasificacion", "servicio"): historica}, self.ejecucion_id)

    def test_activar_otra_version_preserva_predicciones_y_audita_cambio(self):
        with transaccion(self.motor) as sesion:
            self.lote(sesion)
            anterior = sesion.scalar(select(VersionModelo).where(VersionModelo.horizonte == 2,
                VersionModelo.tipo == "clasificacion", VersionModelo.activa.is_(True)))
            copia = deepcopy(self.preparadas[2, "clasificacion", "servicio"])
            copia.datos["huella"] = huella_json({"original": anterior.huella, "revision": "prueba de activación"})
            copia.datos["umbral_probabilidad"] = anterior.umbral_probabilidad
            versiones = guardar_versiones(sesion, {(2, "clasificacion", "servicio"): copia}, None)
            activar_versiones_servicio(sesion, versiones, self.ejecucion_id)
            activar_versiones_servicio(sesion, versiones, self.ejecucion_id)
            self.assertFalse(anterior.activa)
            self.assertEqual(sesion.scalar(select(func.count()).select_from(Prediccion)), 24)
            self.assertEqual(sesion.scalar(select(func.count()).select_from(ActivacionModelo)), 7)
            self.assertIsNotNone(sesion.scalar(select(Prediccion).where(Prediccion.version_clasificacion_id == anterior.id)))

    def test_alertas_retiran_sin_borrar_historial(self):
        with transaccion(self.motor) as sesion:
            self.lote(sesion)
            historica = sesion.scalar(select(Alerta))
            self.assertEqual(historica.estado, "retirada")
            self.assertIsNotNone(historica.fecha_retiro)
            # Estado previo para comprobar retiro; probabilidad real OOS intacta.
            historica.estado = "activa"
            historica.fecha_retiro = None
            identificador = historica.id
            nueva_id, _ = iniciar_ejecucion(sesion, huella_json("otra ejecución"), date(2025, 12, 27), {})
            sesion.flush()
            resultado = actualizar_alertas(sesion, nueva_id, (2, 4), self.cfg)
            self.assertEqual(resultado["retiradas_anteriores"], 1)
        with transaccion(self.motor) as sesion:
            retirada = sesion.get(Alerta, identificador)
            self.assertEqual(retirada.estado, "retirada")
            self.assertIsNotNone(retirada.fecha_retiro)
            self.assertIn(str(nueva_id), retirada.motivo)

    def test_alerta_activa_con_prediccion_oos_real_al_cierre_de_su_epoca(self):
        with transaccion(self.motor) as sesion:
            self.lote(sesion)
            real = sesion.scalar(select(Prediccion).where(Prediccion.probabilidad >= .5))
            identificador, _ = iniciar_ejecucion(sesion, huella_json("cierre histórico de prueba"), real.origen_cierre, {})
            campos = {c.name: getattr(real, c.name) for c in Prediccion.__table__.columns
                      if c.name not in ("id", "fecha_actualizacion", "ejecucion_id", "tipo")}
            # Representa esa semana al cierre de su época; todos los números
            # y versiones son del pronóstico OOS real, sin modificar el CSV.
            nueva = Prediccion(**campos, ejecucion_id=identificador, tipo="vigente")
            sesion.add(nueva)
            sesion.flush()
            resultado = actualizar_alertas(sesion, identificador, (2, 4), self.cfg)
            self.assertEqual(resultado["activas_nuevas"], 1)
            alerta = sesion.scalar(select(Alerta).where(Alerta.prediccion_id == nueva.id))
            self.assertEqual(alerta.estado, "activa")
            self.assertIsNone(alerta.fecha_retiro)

    def test_transaccion_rechaza_modelo_posterior_al_origen(self):
        with self.assertRaises(ValueError), transaccion(self.motor) as sesion:
            versiones = guardar_versiones(sesion, self.preparadas, None)
            versiones[2, "clasificacion", "servicio"].entrenamiento_corte = date(2026, 1, 1)
            construir_predicciones_vigentes(self.futuros, versiones, self.cfg)
        with transaccion(self.motor) as sesion:
            self.assertEqual(sesion.scalar(select(func.count()).select_from(VersionModelo)), 0)

    def test_columnas_faltantes_y_valores_no_finitos_rechazan_inferencia(self):
        version = VersionModelo(**self.preparadas[2, "clasificacion", "servicio"].datos)
        vector = self.futuros[2].iloc[0][version.columnas].to_dict()
        for cambiado in ({}, {**vector, version.columnas[0]: None}, {**vector, version.columnas[0]: np.inf}):
            with self.assertRaises(ValueError):
                predecir_con_version(version, [cambiado])
        version.columnas = list(reversed(version.columnas))
        with self.assertRaises(ValueError):
            predecir_con_version(version, [vector])

    def test_indice_impide_dos_modelos_activos_del_mismo_tipo(self):
        with self.assertRaises(IntegrityError), transaccion(self.motor) as sesion:
            versiones = guardar_versiones(sesion, self.preparadas, None)
            original = versiones[2, "clasificacion", "servicio"]
            original.activa = True
            copia = deepcopy(self.preparadas[2, "clasificacion", "servicio"])
            copia.datos.update(huella=huella_json("duplicado activo"), activa=True)
            guardar_versiones(sesion, {(2, "clasificacion", "servicio"): copia}, None)

    def test_ejecucion_en_proceso_rechaza_carrera_y_fallida_se_reintenta(self):
        with transaccion(self.motor) as sesion:
            with self.assertRaises(ValueError):
                iniciar_ejecucion(sesion, huella_json("prueba"), date(2025, 12, 27), {})
            ejecucion = sesion.get(EjecucionPrediccion, self.ejecucion_id)
            ejecucion.estado = "fallida"
            sesion.flush()
            identificador, reutilizada = iniciar_ejecucion(sesion, huella_json("prueba"), date(2025, 12, 27), {})
            self.assertEqual(identificador, self.ejecucion_id)
            self.assertIsNone(reutilizada)
            self.assertEqual(ejecucion.estado, "en_proceso")

    def test_horizonte_3_y_repetidos_no_generan_datos(self):
        for horizontes in ((3,), (), (2, 2)):
            with self.assertRaises(ValueError):
                publicar(self.motor, horizontes)

    def test_reporte_mlflow_no_declara_folds_historicos_como_nuevos(self):
        reporte = reporte_servicio(self.preparadas, self.protocolo, self.futuros, date(2025, 12, 27))
        self.assertFalse(reporte["evaluacion_generada_en_esta_corrida"])
        for bloque in reporte["horizontes"].values():
            self.assertEqual(len(bloque["variantes"]), 3)
            for variante in bloque["variantes"].values():
                self.assertNotIn("folds", variante)


if __name__ == "__main__":
    unittest.main()
