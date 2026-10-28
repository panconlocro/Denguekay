"""Publicación OE2: versiones candidatas, booster en Storage con hash, OOS e inferencia vigente."""

from dataclasses import replace
from pathlib import Path
import hashlib
import tempfile
import unittest

from sqlalchemy import func, select

from backend_soporte import datos_muestra, motor_temporal
from serving_soporte import CORTE, preparar_muestra
from src.db.modelos import Ejecucion, ImportanciaVariable, ParametroSistema, Prediccion, VersionModelo
from src.db.sesion import transaccion
from src.serving import parametros
from src.serving.almacenamiento import AlmacenamientoLocal
from src.serving.cargar_datos import persistir_carga
from src.serving.modelos import (VersionPreparada, cumple_umbrales, guardar_versiones, reporte_servicio,
                                 ruta_artefacto, siguiente_codigo)
from src.serving.publicar import publicacion_existente, publicar, publicar_en_bd


class TestPublicacion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory()
        cls.cfg, cls.protocolo, cls.preparadas = preparar_muestra()
        datos = datos_muestra(Path(cls.fixture.name), cls.cfg.seleccion_experimental)
        cls.datos = replace(datos, observaciones=[o for o in datos.observaciones if o["id_semana"] >= 202530])

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def setUp(self):
        self.carpeta = tempfile.TemporaryDirectory()
        self.motor = motor_temporal(Path(self.carpeta.name))
        self.almacenamiento = AlmacenamientoLocal(Path(self.carpeta.name) / "storage")
        with transaccion(self.motor) as s:
            persistir_carga(s, self.datos)

    def tearDown(self):
        self.motor.dispose()
        self.carpeta.cleanup()

    def guardar(self, preparadas=None):
        with transaccion(self.motor) as s:
            versiones = guardar_versiones(s, preparadas or self.preparadas, "run-prueba",
                                          parametros.criterios_aceptacion(s), self.almacenamiento)
            return {k: (v.codigo, v.id_version) for k, v in versiones.items()}

    def test_versiones_candidatas_con_artefacto_y_hash(self):
        codigos = self.guardar()
        self.assertEqual(codigos[2, "clasificacion"][0], "clf-h2-v1")
        self.assertEqual(codigos[4, "regresion"][0], "reg-h4-v1")
        with transaccion(self.motor) as s:
            for v in s.scalars(select(VersionModelo)):
                with self.subTest(codigo=v.codigo):
                    self.assertEqual(v.estado, "candidata")
                    self.assertFalse(v.cumple_umbrales)  # métricas reales de 2024 no cumplen
                    self.assertEqual(v.ruta_artefacto, f"modelos/{v.codigo}.json")
                    contenido = self.almacenamiento.leer(v.ruta_artefacto)
                    self.assertEqual(hashlib.sha256(contenido).hexdigest(), v.sha256_artefacto)
                    self.assertEqual(v.mlflow_run_id, "run-prueba")
                    self.assertIn("temporada_2024", v.metricas["bloques"])
                    self.assertEqual(v.reproducibilidad["entrenamiento_corte"], str(CORTE))
            self.assertGreater(s.scalar(select(func.count()).select_from(ImportanciaVariable)), 0)

    def test_mismo_artefacto_reutiliza_y_otro_crea_nueva_version(self):
        primera = self.guardar()
        self.assertEqual(self.guardar(), primera)
        clave = (2, "clasificacion")
        original = self.preparadas[clave]
        distinta = VersionPreparada({**original.datos, "sha256_artefacto": "b" * 64}, original.artefacto + b" ", [])
        nuevas = self.guardar({clave: distinta})
        self.assertEqual(nuevas[clave][0], "clf-h2-v2")
        with transaccion(self.motor) as s:
            self.assertEqual(siguiente_codigo(s, "clasificacion", 2), "clf-h2-v3")

    def test_storage_compartido_no_sobrescribe_artefactos_ajenos(self):
        ajeno = b'{"booster": "de otra BD"}'
        self.almacenamiento.guardar("modelos/clf-h2-v1.json", ajeno)
        codigos = self.guardar()
        with transaccion(self.motor) as s:
            v = s.get(VersionModelo, codigos[2, "clasificacion"][1])
            self.assertTrue(v.ruta_artefacto.startswith("modelos/clf-h2-v1-"))
            self.assertEqual(hashlib.sha256(self.almacenamiento.leer(v.ruta_artefacto)).hexdigest(), v.sha256_artefacto)
        self.assertEqual(self.almacenamiento.leer("modelos/clf-h2-v1.json"), ajeno)
        self.assertEqual(ruta_artefacto(self.almacenamiento, "clf-h2-v1", ajeno), "modelos/clf-h2-v1.json")

    def test_cumple_umbrales_lee_la_bd(self):
        metricas = self.preparadas[2, "clasificacion"].datos["metricas"]
        alerta = metricas["bloques"]["temporada_2024"]["clasificacion"]["alerta_directa"]
        with transaccion(self.motor) as s:
            criterios = parametros.criterios_aceptacion(s)
            self.assertEqual(criterios["bloques"], ["temporada_2024"])
            self.assertFalse(cumple_umbrales("clasificacion", metricas, criterios))
            p = s.get(ParametroSistema, "umbrales_aceptacion")
            p.valor = {**p.valor, "recall": alerta["recall"], "precision": alerta["precision"], "f1": alerta["f1"]}
            s.flush()
            self.assertTrue(cumple_umbrales("clasificacion", metricas, parametros.criterios_aceptacion(s)))

    def test_publicacion_en_bd_completa(self):
        r = publicar_en_bd(self.motor, self.datos, self.protocolo, self.preparadas, (2, 4), self.cfg,
                           "run-prueba", "huella-prueba", self.almacenamiento, 0)
        self.assertEqual(len(r["versiones"]), 4)
        self.assertTrue(all(v["estado"] == "candidata" for v in r["versiones"]))
        self.assertTrue(r["oos"])
        self.assertEqual([v["id_semana_corte"] for v in r["inferencias_vigentes"]], [202552, 202552])
        self.assertTrue(all(v["experimental"] for v in r["inferencias_vigentes"]))
        with transaccion(self.motor) as s:
            e = s.get(Ejecucion, r["id_ejecucion"])
            self.assertEqual((e.tipo, e.estado), ("reentrenamiento", "exitosa"))
            self.assertEqual(publicacion_existente(s, "huella-prueba").id_ejecucion, e.id_ejecucion)
            self.assertIsNone(publicacion_existente(s, "otra"))
            vigentes = s.scalar(select(func.count()).select_from(Prediccion).where(Prediccion.id_semana_corte == 202552))
            self.assertEqual(vigentes, 130)

    def test_reporte_mlflow_no_declara_folds_historicos_como_nuevos(self):
        reporte = reporte_servicio(self.preparadas, self.protocolo, CORTE)
        self.assertFalse(reporte["evaluacion_generada_en_esta_corrida"])
        self.assertEqual(set(reporte["horizontes"]), {"2", "4"})
        variante = reporte["horizontes"]["2"]["variantes"]["base_6_poblacion_2017_clasificacion"]
        self.assertEqual(variante["corte_ajuste_servicio"], str(CORTE))

    def test_publicar_valida_horizontes_antes_de_leer_fuentes(self):
        for horizontes, mensaje in (((3,), "horizonte 3"), ((2, 2), "no repetidos"), ((), "no repetidos")):
            with self.subTest(horizontes=horizontes), self.assertRaisesRegex(ValueError, mensaje):
                publicar(self.motor, horizontes, cfg=self.cfg, almacenamiento=self.almacenamiento)


if __name__ == "__main__":
    unittest.main()
