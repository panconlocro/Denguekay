"""Mediciones HTTP sobre BD migrada y artefactos reales, sin tiempos simulados."""

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import numpy as np
from sqlalchemy import func, select

import test_api_backend as soporte_api
from backend_soporte import entorno_bd
from src.api.benchmark import ejecutar_benchmark, main, medir_caso, percentil
from src.db.modelos import Ejecucion, ObservacionSemanal, Prediccion, VersionModelo
from src.db.sesion import transaccion
from src.utils.paths import ROOT, SERVING_MODELS


class TestBenchmarkReal(unittest.TestCase):
    # Comparte la preparación ya contrastada: las filas y boosters proceden de fixtures reales.
    setUp = soporte_api.TestAPIReal.setUp
    tearDown = soporte_api.TestAPIReal.tearDown

    def conteos(self):
        with transaccion(self.motor) as s:
            return {m.__tablename__: s.scalar(select(func.count()).select_from(m))
                    for m in (VersionModelo, Prediccion, Ejecucion)}

    @classmethod
    def setUpClass(cls):
        soporte_api.TestAPIReal.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        soporte_api.TestAPIReal.tearDownClass.__func__(cls)

    def test_todas_las_operaciones_cache_y_escrituras_preservan_historia(self):
        antes = self.conteos()
        reporte = ejecutar_benchmark(self.cliente, repeticiones=2, calentamiento=1,
            incluir_escrituras=True, clave_api="clave-local-de-prueba")
        # La activación no se mide (exige cumple_umbrales): la cobertura se declara incompleta.
        self.assertEqual([o["ruta"] for o in reporte["no_medidos"]], ["/admin/modelos/{version}/activar"])
        self.assertFalse(reporte["cobertura_completa"])
        self.assertTrue(reporte["cumple_sla_medido"])
        self.assertEqual(reporte["fecha_corte_datos"], "2025-12-27")
        self.assertEqual(len(reporte["resultados"]), 50)
        self.assertEqual(len(reporte["versiones_en_uso"]), 4)
        for r in reporte["resultados"]:
            self.assertEqual(r["http"], {"200": 2})
            self.assertEqual(r["errores"], 0)
            self.assertTrue(all(t > 0 for t in r["duraciones_ms"]))
            self.assertAlmostEqual(r["p95_ms"], float(np.percentile(r["duraciones_ms"], 95)))
        despues = self.conteos()
        self.assertEqual(antes["version_modelo"], despues["version_modelo"])
        self.assertEqual(antes["prediccion"], despues["prediccion"])  # UPSERT: no duplica
        self.assertEqual(despues["ejecucion"] - antes["ejecucion"], 4)
        bypass = [r for r in reporte["resultados"] if r["ruta"].startswith("/mapa") and r["modo"] == "sin_cache_lecturas"]
        self.assertTrue(all(r["cache"] == {"BYPASS": 2} for r in bypass))
        caliente = [r for r in reporte["resultados"] if r["ruta"].startswith("/mapa") and r["modo"] == "cache_habilitada"]
        self.assertTrue(all(r["cache"] == {"HIT": 2} for r in caliente))

    def test_solo_lecturas_declara_cobertura_parcial_y_no_modifica_bd(self):
        antes = self.conteos()
        r = ejecutar_benchmark(self.cliente, horizontes=(2,), repeticiones=2, calentamiento=0)
        self.assertFalse(r["cobertura_completa"])
        self.assertFalse(r["cumple_sla_completo"])
        self.assertTrue(r["cumple_sla_medido"])
        self.assertEqual(len(r["no_medidos"]), 2)  # inferencia h=2 y activación
        self.assertEqual(antes, self.conteos())

    def test_errores_http_y_limite_incumplido_no_se_ocultan(self):
        r = medir_caso(self.cliente, "POST", "/admin/inferencias",
            "escritura", 2, 0, "clave-incorrecta", 5, {"horizonte": 2})
        self.assertEqual(r["errores"], 2)
        self.assertEqual(r["http"], {"401": 2})
        self.assertFalse(r["cumple_sla"])
        lento = ejecutar_benchmark(self.cliente, horizontes=(2,), repeticiones=2,
            calentamiento=0, limite=1e-12)
        self.assertFalse(lento["cumple_sla_medido"])

    def test_parametros_invalidos_y_percentil_sin_mediciones(self):
        for kwargs in ({"repeticiones": 1}, {"calentamiento": -1}, {"limite": float("nan")},
                       {"horizontes": (3,)}, {"horizontes": (2, 2)}, {"horizontes": ()},
                       {"incluir_escrituras": True}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                ejecutar_benchmark(self.cliente, **kwargs)
        with self.assertRaises(ValueError):
            percentil([], .95)

    def test_cli_real_exporta_y_bd_no_configurada_falla(self):
        SERVING_MODELS.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=SERVING_MODELS) as carpeta:
            ruta = Path(carpeta) / "medicion.json"
            with entorno_bd(str(self.motor.url)), redirect_stdout(StringIO()),                     mock.patch("src.api.main.AlmacenamientoLocal", return_value=self.almacenamiento):
                salida = main(["--horizontes", "2", "--repeticiones", "2", "--calentamiento", "0",
                               "--salida", str(ruta.relative_to(ROOT))])
            self.assertEqual(salida, 0)
            reporte = json.loads(ruta.read_text())
            self.assertIn("BD real", reporte["transporte"])
            self.assertFalse(reporte["incluye_escrituras"])
            with entorno_bd(""), redirect_stdout(StringIO()):
                self.assertEqual(main(["--salida", str(ruta.relative_to(ROOT))]), 1)
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["--url", "https://usuario:clave@example.invalid"]), 1)
            with redirect_stdout(StringIO()), self.assertRaises(SystemExit):
                main(["--salida", "data/medicion.json"])

    def test_tablero_casos_observados_de_la_ultima_semana(self):
        r = self.cliente.get("/api/v1/tablero/resumen?horizonte=2").json()["casos_observados_ultima_semana"]
        with transaccion(self.motor) as s:
            semana = s.scalar(select(func.max(ObservacionSemanal.id_semana)))
            casos = s.scalars(select(ObservacionSemanal.casos_dengue).where(ObservacionSemanal.id_semana == semana)).all()
        self.assertEqual(r["valor"], sum(c for c in casos if c is not None))
        self.assertTrue(r["disponible"])
        sin_modelo = self.cliente.get("/api/v1/tablero/resumen?horizonte=3").json()
        self.assertTrue(sin_modelo["casos_observados_ultima_semana"]["disponible"])
        self.assertFalse(sin_modelo["disponible"])
