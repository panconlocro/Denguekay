"""Publicación OE2: versiones candidatas, booster en Storage con hash, OOS e inferencia vigente."""

from dataclasses import replace
from pathlib import Path
import hashlib
import tempfile
import unittest

from sqlalchemy import func, select

from backend_soporte import datos_muestra, motor_temporal
from serving_soporte import CORTE, preparar_muestra
from denguekay.db.models import Run, VariableImportance, SystemParameter, Prediction, ModelVersion
from denguekay.db.session import transaction
from denguekay.serving import parameters as parametros
from denguekay.serving.storage import LocalStorage
from denguekay.serving.load_data import persist_load
from denguekay.serving.models import (PreparedVersion, meets_thresholds, save_versions, service_report,
                                 artifact_path, next_code)
from denguekay.serving.publish import existing_publication, publish, publish_to_db


class TestPublicacion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory()
        cls.cfg, cls.protocolo, cls.preparadas = preparar_muestra()
        datos = datos_muestra(Path(cls.fixture.name), cls.cfg.seleccion_experimental)
        cls.data = replace(datos, observaciones=[o for o in datos.observaciones if o["id_semana"] >= 202530])

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def setUp(self):
        self.carpeta = tempfile.TemporaryDirectory()
        self.motor = motor_temporal(Path(self.carpeta.name))
        self.almacenamiento = LocalStorage(Path(self.carpeta.name) / "storage")
        with transaction(self.motor) as s:
            persist_load(s, self.data)

    def tearDown(self):
        self.motor.dispose()
        self.carpeta.cleanup()

    def save(self, preparadas=None):
        with transaction(self.motor) as s:
            versiones = save_versions(s, preparadas or self.preparadas, "run-prueba",
                                          parametros.acceptance_criteria(s), self.almacenamiento)
            return {k: (v.codigo, v.id_version) for k, v in versiones.items()}

    def test_versiones_candidatas_con_artefacto_y_hash(self):
        codigos = self.save()
        self.assertEqual(codigos[2, "clasificacion"][0], "clf-h2-v1")
        self.assertEqual(codigos[4, "regresion"][0], "reg-h4-v1")
        with transaction(self.motor) as s:
            for v in s.scalars(select(ModelVersion)):
                with self.subTest(codigo=v.codigo):
                    self.assertEqual(v.estado, "candidata")
                    self.assertFalse(v.cumple_umbrales)  # métricas reales de 2024 no cumplen
                    self.assertEqual(v.ruta_artefacto, f"modelos/{v.codigo}.json")
                    contenido = self.almacenamiento.read(v.ruta_artefacto)
                    self.assertEqual(hashlib.sha256(contenido).hexdigest(), v.sha256_artefacto)
                    self.assertEqual(v.mlflow_run_id, "run-prueba")
                    self.assertIn("temporada_2024", v.metricas["bloques"])
                    self.assertEqual(v.reproducibilidad["entrenamiento_corte"], str(CORTE))
            self.assertGreater(s.scalar(select(func.count()).select_from(VariableImportance)), 0)

    def test_mismo_artefacto_reutiliza_y_otro_crea_nueva_version(self):
        primera = self.save()
        self.assertEqual(self.save(), primera)
        clave = (2, "clasificacion")
        original = self.preparadas[clave]
        distinta = PreparedVersion({**original.data, "sha256_artefacto": "b" * 64}, original.artifact + b" ", [])
        nuevas = self.save({clave: distinta})
        self.assertEqual(nuevas[clave][0], "clf-h2-v2")
        with transaction(self.motor) as s:
            self.assertEqual(next_code(s, "clasificacion", 2), "clf-h2-v3")

    def test_storage_compartido_no_sobrescribe_artefactos_ajenos(self):
        ajeno = b'{"booster": "de otra BD"}'
        self.almacenamiento.save("modelos/clf-h2-v1.json", ajeno)
        codigos = self.save()
        with transaction(self.motor) as s:
            v = s.get(ModelVersion, codigos[2, "clasificacion"][1])
            self.assertTrue(v.ruta_artefacto.startswith("modelos/clf-h2-v1-"))
            self.assertEqual(hashlib.sha256(self.almacenamiento.read(v.ruta_artefacto)).hexdigest(), v.sha256_artefacto)
        self.assertEqual(self.almacenamiento.read("modelos/clf-h2-v1.json"), ajeno)
        self.assertEqual(artifact_path(self.almacenamiento, "clf-h2-v1", ajeno), "modelos/clf-h2-v1.json")

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

    def test_publicacion_en_bd_completa(self):
        r = publish_to_db(self.motor, self.data, self.protocolo, self.preparadas, (2, 4), self.cfg,
                           "run-prueba", "huella-prueba", self.almacenamiento, 0)
        self.assertEqual(len(r["versiones"]), 4)
        self.assertTrue(all(v["estado"] == "candidata" for v in r["versiones"]))
        self.assertTrue(r["oos"])
        self.assertEqual([v["id_semana_corte"] for v in r["inferencias_vigentes"]], [202552, 202552])
        self.assertTrue(all(v["experimental"] for v in r["inferencias_vigentes"]))
        with transaction(self.motor) as s:
            e = s.get(Run, r["id_ejecucion"])
            self.assertEqual((e.tipo, e.estado), ("reentrenamiento", "exitosa"))
            self.assertEqual(existing_publication(s, "huella-prueba").id_ejecucion, e.id_ejecucion)
            self.assertIsNone(existing_publication(s, "otra"))
            vigentes = s.scalar(select(func.count()).select_from(Prediction).where(Prediction.id_semana_corte == 202552))
            self.assertEqual(vigentes, 130)

    def test_reporte_mlflow_no_declara_folds_historicos_como_nuevos(self):
        reporte = service_report(self.preparadas, self.protocolo, CORTE)
        self.assertFalse(reporte["evaluacion_generada_en_esta_corrida"])
        self.assertEqual(set(reporte["horizontes"]), {"2", "4"})
        variante = reporte["horizontes"]["2"]["variantes"]["base_6_poblacion_2017_clasificacion"]
        self.assertEqual(variante["corte_ajuste_servicio"], str(CORTE))

    def test_publicar_valida_horizontes_antes_de_leer_fuentes(self):
        for horizontes, mensaje in (((3,), "horizonte 3"), ((2, 2), "no repetidos"), ((), "no repetidos")):
            with self.subTest(horizontes=horizontes), self.assertRaisesRegex(ValueError, mensaje):
                publish(self.motor, horizontes, cfg=self.cfg, storage=self.almacenamiento)


if __name__ == "__main__":
    unittest.main()
