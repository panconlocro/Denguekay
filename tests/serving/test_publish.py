"""Publicación OE2: paquete en Storage con hashes, versiones candidatas, OOS e inferencia vigente opcional."""

from dataclasses import replace
from pathlib import Path
import hashlib
import json
import tempfile
import unittest

from sqlalchemy import func, select

from backend_support import datos_muestra, motor_temporal
from serving_support import CORTE, fijar_seleccion, sample_package, preparar_muestra
from denguekay.db.models import Run, VariableImportance, SystemParameter, Prediction, ModelVersion
from denguekay.db.session import transaction
from denguekay.serving import parameters as parametros
from denguekay.serving.artifacts import InvalidArtifact
from denguekay.serving.storage import LocalStorage
from denguekay.serving.load_data import persist_load
from denguekay.serving.models import meets_thresholds, next_code, save_versions, thresholds
from denguekay.serving.package import MANIFEST_NAME, file_path, package_code, save_package
from denguekay.serving.predictors import v0_compact_xgb as v0
from denguekay.serving.publish import existing_publication, publish, publish_to_db


class TestPublicacion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory()
        cls.cfg, cls.protocolo, cls.preparadas = preparar_muestra()
        cls.paquete = sample_package(cls.cfg, cls.protocolo, cls.preparadas)
        datos = datos_muestra(Path(cls.fixture.name))
        cls.data = replace(datos, observaciones=[o for o in datos.observaciones if o["id_semana"] >= 202530])

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def setUp(self):
        self.carpeta = tempfile.TemporaryDirectory()
        self.motor = motor_temporal(Path(self.carpeta.name))
        self.storage = LocalStorage(Path(self.carpeta.name) / "storage")
        with transaction(self.motor) as s:
            persist_load(s, self.data)
        # Since phase 4 load_data does not seed the selection: the v0 tests set it (as publish would).
        fijar_seleccion(self.motor)

    def tearDown(self):
        self.motor.dispose()
        self.carpeta.cleanup()

    def save(self, paquete=None):
        paquete = paquete or self.paquete
        with transaction(self.motor) as s:
            cumple = thresholds(paquete, parametros.acceptance_criteria(s))
            ruta, sha = save_package(self.storage, paquete, cumple)
            versiones = save_versions(s, paquete, ruta, sha, "run-prueba", cumple)
            return {k: (v.codigo, v.id_version) for k, v in versiones.items()}

    def test_versiones_candidatas_apuntan_al_manifiesto(self):
        codigos = self.save()
        self.assertEqual(codigos[2, "clasificacion"][0], "clf-h2-v1")
        self.assertEqual(codigos[4, "regresion"][0], "reg-h4-v1")
        ruta = file_path(self.paquete.code, MANIFEST_NAME)
        with transaction(self.motor) as s:
            versiones = list(s.scalars(select(ModelVersion)))
            self.assertEqual(len(versiones), 4)
            for v in versiones:
                with self.subTest(codigo=v.codigo):
                    self.assertEqual(v.estado, "candidata")
                    self.assertFalse(v.cumple_umbrales)  # métricas reales de 2024 no cumplen
                    self.assertEqual(v.ruta_artefacto, ruta)  # las cuatro filas comparten el paquete (M3)
                    self.assertEqual(hashlib.sha256(self.storage.read(ruta)).hexdigest(), v.sha256_artefacto)
                    self.assertEqual(v.mlflow_run_id, "run-prueba")
                    self.assertIn("temporada_2024", v.metricas["bloques"])
                    self.assertEqual(v.reproducibilidad["entrenamiento_corte"], str(CORTE))
            self.assertGreater(s.scalar(select(func.count()).select_from(VariableImportance)), 0)
        manifiesto = json.loads(self.storage.read(ruta))
        self.assertEqual((manifiesto["tipo_predictor"], manifiesto["horizontes"], manifiesto["nivel_intervalo"]),
                         ("v0_compact_xgb", [2, 4], None))
        for nombre, entrada in manifiesto["archivos"].items():
            with self.subTest(archivo=nombre):
                self.assertEqual(hashlib.sha256(self.storage.read(entrada["ruta"])).hexdigest(), entrada["sha256"])
        self.assertEqual(set(manifiesto["archivos"]), {f"h{h}_{t}.json" for h in (2, 4) for t in v0.TASKS})

    def test_mismo_paquete_reutiliza_y_otro_crea_versiones_nuevas(self):
        primera = self.save()
        self.assertEqual(self.save(), primera)
        archivos = {**self.paquete.files, "h2_clasificacion.json": self.paquete.files["h2_clasificacion.json"] + b" "}
        distinto = replace(self.paquete, files=archivos, code=package_code(v0.CODE_PREFIX, archivos))
        self.assertNotEqual(distinto.code, self.paquete.code)
        nuevas = self.save(distinto)
        self.assertEqual(nuevas[2, "clasificacion"][0], "clf-h2-v2")
        with transaction(self.motor) as s:
            self.assertEqual(next_code(s, "clf-h2-v"), "clf-h2-v3")

    def test_storage_compartido_no_sobrescribe_contenido_ajeno(self):
        ajeno = b'{"manifiesto": "de otra BD"}'
        manifiesto = file_path(self.paquete.code, MANIFEST_NAME)
        self.storage.save(manifiesto, ajeno)
        codigos = self.save()
        with transaction(self.motor) as s:
            v = s.get(ModelVersion, codigos[2, "clasificacion"][1])
            self.assertTrue(v.ruta_artefacto.startswith(f"modelos/{self.paquete.code}/manifest-"))
            self.assertEqual(hashlib.sha256(self.storage.read(v.ruta_artefacto)).hexdigest(), v.sha256_artefacto)
        self.assertEqual(self.storage.read(manifiesto), ajeno)
        booster = file_path(self.paquete.code, "h4_regresion.json")
        self.storage.save(booster, b"otro booster")
        with self.assertRaisesRegex(InvalidArtifact, "no se sobrescribe"):
            self.save()
        self.assertEqual(self.storage.read(booster), b"otro booster")

    def test_cumple_umbrales_lee_la_bd(self):
        metricas = self.preparadas[2, "clasificacion"].data["metricas"]
        alerta = metricas["bloques"]["temporada_2024"]["clasificacion"]["alerta_directa"]
        with transaction(self.motor) as s:
            criterios = parametros.acceptance_criteria(s)
            self.assertEqual(criterios["bloques"], ["temporada_2024"])
            self.assertFalse(meets_thresholds("clasificacion", metricas, criterios))
            p = s.get(SystemParameter, "umbrales_aceptacion")
            p.valor = {**p.valor, "recall": alerta["recall"], "precision": alerta["precision"], "f1": alerta["f1"]}
            s.flush()
            self.assertTrue(meets_thresholds("clasificacion", metricas, parametros.acceptance_criteria(s)))

    def test_publicacion_registra_versiones_y_oos_sin_inferir(self):
        """Decisión D2 (P3 de la fase 3): la publicación no hace la inferencia vigente salvo que se pida."""
        r = publish_to_db(self.motor, self.data, self.paquete, "run-prueba", "huella-prueba", self.storage, 0)
        self.assertEqual(len(r["versiones"]), 4)
        self.assertTrue(all(v["estado"] == "candidata" for v in r["versiones"]))
        self.assertTrue(r["oos"])
        self.assertEqual(r["inferencias_vigentes"], [])
        self.assertEqual(r["paquete"]["tipo_predictor"], "v0_compact_xgb")
        with transaction(self.motor) as s:
            e = s.get(Run, r["id_ejecucion"])
            self.assertEqual((e.tipo, e.estado), ("reentrenamiento", "exitosa"))
            self.assertEqual(existing_publication(s, "huella-prueba").id_ejecucion, e.id_ejecucion)
            self.assertIsNone(existing_publication(s, "otra"))
            self.assertEqual(s.scalar(select(func.count()).select_from(Prediction).where(
                Prediction.id_semana_corte == 202552)), 0)

    def test_publicacion_con_inferencia_vigente(self):
        r = publish_to_db(self.motor, self.data, self.paquete, "run-prueba", "huella-prueba", self.storage, 0,
                          servir_no_validadas=True, run_inference=True)
        self.assertEqual([v["id_semana_corte"] for v in r["inferencias_vigentes"]], [202552, 202552])
        self.assertTrue(all(v["experimental"] for v in r["inferencias_vigentes"]))
        self.assertEqual({v["paquete"] for v in r["inferencias_vigentes"]}, {self.paquete.code})
        with transaction(self.motor) as s:
            vigentes = s.scalar(select(func.count()).select_from(Prediction).where(Prediction.id_semana_corte == 202552))
            self.assertEqual(vigentes, 130)

    def test_reporte_mlflow_no_declara_folds_historicos_como_nuevos(self):
        reporte = v0.service_report(self.preparadas, self.protocolo, CORTE)
        self.assertFalse(reporte["evaluacion_generada_en_esta_corrida"])
        self.assertEqual(set(reporte["horizontes"]), {"2", "4"})
        variante = reporte["horizontes"]["2"]["variantes"]["base_6_poblacion_2017_clasificacion"]
        self.assertEqual(variante["corte_ajuste_servicio"], str(CORTE))

    def test_publicar_valida_horizontes_y_opciones_antes_de_leer_fuentes(self):
        for horizontes, mensaje in (((3,), "horizonte 3"), ((2, 2), "no repetidos"), ((), "no repetidos")):
            with self.subTest(horizontes=horizontes), self.assertRaisesRegex(ValueError, mensaje):
                publish(self.motor, horizontes, cfg=self.cfg, storage=self.storage)
        with self.assertRaisesRegex(ValueError, "protocolo compacto"):
            v0.validate((2,), {"variantes": {"clasificacion": "otra", "regresion": "base_6"}})


if __name__ == "__main__":
    unittest.main()
