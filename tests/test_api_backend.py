"""Contrato HTTP de la Tabla 2 (OE2) con SQLite migrada, filas reales y boosters XGBoost reales."""

from dataclasses import replace
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.engine import URL

from backend_soporte import datos_muestra, entorno_bd, motor_temporal
from serving_soporte import preparar_muestra
from src.api.cache import CacheLecturas
from src.api.main import crear_app
from src.db.modelos import Alerta, Ejecucion, Prediccion, VersionModelo
from src.db.sesion import crear_motor, transaccion
from src.serving.almacenamiento import AlmacenamientoLocal
from src.serving.cargar_datos import persistir_carga
from src.serving.inferencia import actualizar_alertas
from src.serving.publicar import publicar_en_bd
from src.utils.paths import ROOT

CLAVE = "clave-local-de-prueba"
UBIGEOS = ["200101", "200201", "200502"]
TABLA_2 = {("get", "/salud"), ("get", "/distritos"), ("get", "/predicciones"), ("get", "/series/{ubigeo}"),
           ("get", "/tablero/resumen"), ("get", "/mapa-riesgo"), ("get", "/alertas"), ("get", "/modelos/activo"),
           ("post", "/admin/inferencias"), ("post", "/admin/modelos/{version}/activar")}
EXTENSIONES = {("get", "/distritos/{ubigeo}"), ("get", "/observaciones"), ("get", "/alertas/{identificador}"),
               ("get", "/modelos/{identificador}"), ("get", "/modelos/{identificador}/variables")}


class TestAPIReal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Publica una vez (versiones, OOS e inferencia vigente) y guarda la BD como plantilla."""
        cls.base = tempfile.TemporaryDirectory()
        ruta = Path(cls.base.name)
        cls.cfg, cls.protocolo, cls.preparadas = preparar_muestra()
        datos = datos_muestra(ruta, cls.cfg.seleccion_experimental)
        datos = replace(datos, observaciones=[o for o in datos.observaciones if o["id_semana"] >= 202530])
        cls.almacenamiento = AlmacenamientoLocal(ruta / "storage")
        plantilla = ruta / "plantilla"
        plantilla.mkdir()
        motor = motor_temporal(plantilla)
        with transaccion(motor) as s:
            persistir_carga(s, datos)
        publicar_en_bd(motor, datos, cls.protocolo, cls.preparadas, (2, 4), cls.cfg, "run-prueba",
                       "huella-api", cls.almacenamiento, 0)
        with transaccion(motor) as s:
            # Una predicción real elevada a muy_alto para ejercitar alertas (los datos de fin de año dan riesgo bajo).
            p = s.scalar(select(Prediccion).where(Prediccion.ubigeo == "200101", Prediccion.horizonte == 2,
                                                  Prediccion.id_semana_corte == 202552))
            p.probabilidad_brote, p.nivel_riesgo = 0.8, "muy_alto"
            s.flush()
            actualizar_alertas(s, 2, 202552)
            cls.oos_corte = s.scalar(select(func.min(Prediccion.id_semana_corte)).where(Prediccion.horizonte == 2))
        motor.dispose()
        cls.plantilla = plantilla / "pruebas.db"

    @classmethod
    def tearDownClass(cls):
        cls.base.cleanup()

    def setUp(self):
        self.carpeta = tempfile.TemporaryDirectory()
        destino = Path(self.carpeta.name) / "api.db"
        shutil.copyfile(self.plantilla, destino)
        self.motor = crear_motor(URL.create("sqlite", database=str(destino)))
        self.app = crear_app(self.motor, self.cfg, clave_api=CLAVE, almacenamiento=self.almacenamiento)
        self.cliente = TestClient(self.app)
        self.cliente.__enter__()

    def tearDown(self):
        self.cliente.__exit__(None, None, None)
        self.motor.dispose()
        self.carpeta.cleanup()

    def get(self, ruta, estado=200):
        respuesta = self.cliente.get("/api/v1" + ruta)
        self.assertEqual(respuesta.status_code, estado, respuesta.text)
        self.assertGreaterEqual(float(respuesta.headers["X-Tiempo-Respuesta-ms"]), 0)
        return respuesta.json()

    def post(self, ruta, cuerpo=None, clave=CLAVE):
        cabeceras = {"X-API-Key": clave} if clave else {}
        return self.cliente.post("/api/v1" + ruta, json=cuerpo, headers=cabeceras)

    def version(self, codigo):
        with transaccion(self.motor) as s:
            return s.scalar(select(VersionModelo.id_version).where(VersionModelo.codigo == codigo))

    # --- lecturas --------------------------------------------------------------

    def test_salud_y_distritos(self):
        salud = self.get("/salud")
        self.assertEqual((salud["estado"], salud["conexion_bd"]), ("ok", True))
        self.assertEqual(salud["fecha_corte_datos"], "2025-12-27")
        distritos = self.get("/distritos")
        self.assertEqual((distritos["total"], len(distritos["elementos"])), (65, 65))
        piura = self.get("/distritos/200101")
        self.assertEqual((piura["provincia"], piura["poblacion_censo_2017"]), ("Piura", 158495))
        pagina = self.get("/distritos?pagina=2&tamano_pagina=10")
        self.assertEqual((len(pagina["elementos"]), pagina["pagina"]), (10, 2))
        self.assertEqual(pagina["elementos"][0]["ubigeo"], distritos["elementos"][10]["ubigeo"])

    def test_observaciones_cero_y_filtros(self):
        obs = self.get("/observaciones?ubigeo=200101&desde=2025-12-01&hasta=2025-12-31")
        self.assertEqual(obs["total"], 3)  # S50-S52; 2025-S53 no tiene observación
        semana = obs["elementos"][0]
        self.assertEqual(semana["semana"]["id_semana"], 202550)
        self.assertEqual((semana["fuente_casos"], semana["estado_cobertura"]), ("sala_situacional", "verificado"))
        self.assertIsNotNone(semana["temp_media_c"])
        todos = self.get("/observaciones?tamano_pagina=100")["elementos"]
        self.assertIn(0, [o["casos_dengue"] for o in todos])

    def test_predicciones_vigentes_experimentales(self):
        r = self.get("/predicciones?horizonte=4")
        self.assertEqual(r["total"], 65)
        disponibles = [p for p in r["elementos"] if p["disponible"]]
        self.assertEqual(sorted(p["ubigeo"] for p in disponibles), UBIGEOS)
        p = disponibles[0]
        self.assertEqual((p["tipo"], p["semana_corte"]["id_semana"], p["semana_objetivo"]["id_semana"]),
                         ("vigente", 202552, 202603))
        self.assertTrue(p["experimental"])
        self.assertIn(p["nivel_riesgo"], ("bajo", "medio", "alto", "muy_alto"))
        self.assertIsNotNone(p["casos_persistencia"])
        self.assertIsNotNone(p["alerta_modelo"])
        sin = next(x for x in r["elementos"] if not x["disponible"])
        self.assertIsNone(sin["probabilidad_brote"])
        self.assertTrue(sin["motivo"])
        uno = self.get("/predicciones?horizonte=4&ubigeo=200201")
        self.assertEqual([e["ubigeo"] for e in uno["elementos"]], ["200201"])

    def test_predicciones_retrospectivas_y_h3(self):
        r = self.get(f"/predicciones?horizonte=2&corte={self.oos_corte}")
        self.assertTrue(r["elementos"])
        p = r["elementos"][0]
        self.assertEqual(p["tipo"], "retrospectiva")
        self.assertIsNone(p["id_version_clasificador"])
        self.assertTrue(p["experimental"])
        self.assertIsNone(p["alerta_modelo"])
        h3 = self.get("/predicciones?horizonte=3")
        self.assertEqual((h3["disponible"], h3["motivo"], h3["elementos"]), (False, "sin modelo para h=3", []))
        vacio = self.get("/predicciones?horizonte=2&corte=201801")
        self.assertFalse(vacio["disponible"])

    def test_series_semanas_continuas(self):
        r = self.get("/series/200101?horizonte=2&desde=2025-11-30&hasta=2026-01-04")
        ids = [e["semana"]["id_semana"] for e in r["elementos"]]
        self.assertEqual(ids, [202549, 202550, 202551, 202552, 202553, 202601])
        self.assertTrue(r["elementos"][0]["observado"])
        self.assertFalse(r["elementos"][4]["observado"])  # 2025-S53 existe en el calendario sin observación
        self.assertIsNone(r["elementos"][4]["casos_dengue"])
        self.assertEqual(r["elementos"][-1]["prediccion"]["semana_corte"]["id_semana"], 202552)
        defecto = self.get("/series/200101?horizonte=2")
        self.assertEqual(len(defecto["elementos"]), 26)
        self.assertFalse(self.get("/series/200101?horizonte=3")["disponible"])

    def test_tablero_resumen(self):
        r = self.get("/tablero/resumen?horizonte=2")
        self.assertEqual((r["distritos"], r["distritos_con_prediccion"]), (65, 3))
        self.assertEqual(sum(r["niveles_riesgo"].values()), 3)
        self.assertEqual(r["alertas_activas"], 1)
        self.assertTrue(r["experimental"])
        self.assertIsNone(r["casos_estimados_region"]["valor"])  # faltan 62 distritos: no se suma parcial
        self.assertTrue(r["casos_observados_ultima_semana"]["disponible"])
        self.assertIn("experimental", r["nota"])
        self.assertFalse(self.get("/tablero/resumen?horizonte=3")["disponible"])

    def test_mapa_riesgo_geojson(self):
        r = self.get("/mapa-riesgo?horizonte=2")
        self.assertEqual(r["type"], "FeatureCollection")
        self.assertEqual(len(r["features"]), 65)
        f = next(x for x in r["features"] if x["id"] == "200101")
        self.assertEqual(f["geometry"]["type"], "Point")
        self.assertEqual(len(f["geometry"]["coordinates"]), 2)
        self.assertLess(f["geometry"]["coordinates"][0], f["geometry"]["coordinates"][1])  # [lon, lat]
        self.assertEqual(f["properties"]["nivel_riesgo"], "muy_alto")
        sin = [x for x in r["features"] if x["properties"]["estado"] == "no_disponible"]
        self.assertEqual(len(sin), 62)
        self.assertEqual(sin[0]["properties"]["nivel_riesgo_etiqueta"], "Sin datos")
        self.assertEqual(len(r["leyenda"]), 5)
        h3 = self.get("/mapa-riesgo?horizonte=3")
        self.assertEqual(h3["features"][0]["properties"]["motivo"], "sin modelo para h=3")

    def test_alertas_filtros_y_detalle(self):
        r = self.get("/alertas?horizonte=2&ubigeo=200101&nivel=muy_alto&estado=activa")
        self.assertEqual(r["total"], 1)
        a = r["elementos"][0]
        self.assertEqual((a["nivel"], a["cambio"], a["estado"]), ("muy_alto", "nueva", "activa"))
        self.assertTrue(a["experimental"])
        self.assertEqual(self.get(f"/alertas/{a['id_alerta']}")["prediccion"]["probabilidad_brote"], 0.8)
        self.assertEqual(self.get("/alertas?horizonte=4")["total"], 0)
        self.assertEqual(self.get("/alertas?nivel=alto")["total"], 0)

    def test_modelos_activo_detalle_y_variables(self):
        r = self.get("/modelos/activo")
        self.assertEqual(sorted(m["codigo"] for m in r["elementos"]),
                         ["clf-h2-v1", "clf-h4-v1", "reg-h2-v1", "reg-h4-v1"])
        self.assertTrue(all(m["seleccion"] == "experimental" and m["experimental"] for m in r["elementos"]))
        self.assertEqual(len(self.get("/modelos/activo?horizonte=2")["elementos"]), 2)
        self.assertFalse(self.get("/modelos/activo?horizonte=3")["disponible"])
        detalle = self.get(f"/modelos/{r['elementos'][0]['id_version']}")
        self.assertEqual(detalle["ruta_artefacto"], f"modelos/{detalle['codigo']}.json")
        self.assertIn("temporada_2024", detalle["metricas"]["bloques"])
        variables = self.get(f"/modelos/{detalle['id_version']}/variables")
        self.assertTrue(variables["elementos"])
        self.assertEqual(variables["elementos"][0]["rango"], 1)

    # --- escrituras ------------------------------------------------------------

    def test_inferencia_por_api_upsert(self):
        antes = self.get("/predicciones?horizonte=2")["total"]
        r = self.post("/admin/inferencias", {"horizonte": 2, "id_semana_corte": 202552})
        self.assertEqual(r.status_code, 200, r.text)
        cuerpo = r.json()
        self.assertEqual((cuerpo["predicciones"], cuerpo["disponibles"], cuerpo["experimental"]), (65, 3, True))
        self.assertEqual(self.get("/predicciones?horizonte=2")["total"], antes)
        pasado = self.post("/admin/inferencias", {"horizonte": 4, "id_semana_corte": 202540}).json()
        self.assertEqual(pasado["id_semana_objetivo"], 202544)
        self.assertEqual(self.post("/admin/inferencias", {"horizonte": 2}).json()["id_semana_corte"], 202552)
        with transaccion(self.motor) as s:
            e = s.get(Ejecucion, cuerpo["id_ejecucion"])
            self.assertEqual((e.tipo, e.detalle["origen"]), ("inferencia", "api"))

    def test_inferencia_rechazos(self):
        casos = [({"horizonte": 3}, 409, "inferencia_no_disponible"),
                 ({"horizonte": 2, "id_semana_corte": 202601}, 409, "inferencia_no_disponible"),
                 ({"horizonte": 5}, 422, "parametro_invalido"), ({}, 422, "parametro_invalido"),
                 ({"horizonte": 2, "extra": 1}, 422, "parametro_invalido")]
        for cuerpo, estado, codigo in casos:
            with self.subTest(cuerpo=cuerpo):
                r = self.post("/admin/inferencias", cuerpo)
                self.assertEqual((r.status_code, r.json()["codigo"]), (estado, codigo))
        ruta = Path(self.base.name) / "storage" / "modelos" / "clf-h2-v1.json"
        original = ruta.read_bytes()
        try:
            ruta.write_bytes(original + b" ")
            r = self.post("/admin/inferencias", {"horizonte": 2})
            self.assertEqual((r.status_code, r.json()["codigo"]), (409, "artefacto_invalido"))
        finally:
            ruta.write_bytes(original)
        with transaccion(self.motor) as s:
            self.assertEqual(s.scalar(select(func.count()).select_from(Ejecucion).where(
                Ejecucion.detalle.is_not(None), Ejecucion.tipo == "inferencia", Ejecucion.estado == "en_curso")), 0)

    def test_activacion(self):
        clf = self.version("clf-h2-v1")
        r = self.post(f"/admin/modelos/{clf}/activar")
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "no_cumple_umbrales"))
        self.assertEqual(self.post("/admin/modelos/99999/activar").status_code, 404)
        with transaccion(self.motor) as s:
            s.execute(VersionModelo.__table__.update().where(VersionModelo.horizonte == 2).values(cumple_umbrales=True))
        r = self.post(f"/admin/modelos/{clf}/activar")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["activada"]["estado"], "activa")
        self.assertIsNone(r.json()["archivada"])
        self.assertEqual(self.post(f"/admin/modelos/{clf}/activar").json()["codigo"], "ya_activa")
        self.post(f"/admin/modelos/{self.version('reg-h2-v1')}/activar")
        en_uso = self.get("/modelos/activo?horizonte=2")["elementos"]
        self.assertEqual({m["seleccion"] for m in en_uso}, {"activa"})
        inferencia = self.post("/admin/inferencias", {"horizonte": 2}).json()
        self.assertFalse(inferencia["experimental"])
        self.assertEqual(inferencia["seleccion"], "activa")
        with transaccion(self.motor) as s:
            otra = VersionModelo(**{c: getattr(s.get(VersionModelo, clf), c) for c in (
                "tarea", "horizonte", "algoritmo", "variables", "hiperparametros", "metricas", "umbral_probabilidad",
                "mlflow_run_id", "ruta_artefacto", "sha256_artefacto", "sha256_dataset")},
                codigo="clf-h2-v2", cumple_umbrales=True)
            s.add(otra)
            s.flush()
            nueva = otra.id_version
        r = self.post(f"/admin/modelos/{nueva}/activar").json()
        self.assertEqual((r["activada"]["codigo"], r["archivada"]["codigo"]), ("clf-h2-v2", "clf-h2-v1"))
        with transaccion(self.motor) as s:
            e = s.get(Ejecucion, r["id_ejecucion"])
            self.assertEqual((e.tipo, e.detalle["archivada"]), ("mantenimiento", "clf-h2-v1"))

    def test_clave_escritura_y_cors(self):
        for clave in (None, "incorrecta"):
            r = self.post("/admin/inferencias", {"horizonte": 2}, clave=clave)
            self.assertEqual(r.status_code, 401)
            self.assertEqual(set(r.json()), {"codigo", "mensaje", "detalle"})
        with TestClient(crear_app(self.motor, self.cfg, clave_api="", almacenamiento=self.almacenamiento)) as c:
            self.assertEqual(c.post("/api/v1/admin/inferencias", json={"horizonte": 2}).status_code, 503)
        for origen, permitido in ((self.cfg.cors_origen, True), ("https://origen-no-autorizado.invalid", False)):
            r = self.cliente.get("/api/v1/distritos", headers={"Origin": origen})
            self.assertEqual("access-control-allow-origin" in r.headers, permitido)

    # --- errores, caché y contrato ------------------------------------------------

    def test_404_422_formato_uniforme(self):
        casos = [("/distritos/999999", 404), ("/observaciones?ubigeo=999999", 404),
                 ("/distritos/123", 422), ("/predicciones?horizonte=1", 422), ("/predicciones", 422),
                 ("/observaciones?desde=2025-02-01&hasta=2025-01-01", 422),
                 ("/distritos?pagina=0", 422), ("/distritos?tamano_pagina=101", 422),
                 ("/alertas?estado=otro", 422), ("/alertas?nivel=medio", 422), ("/alertas/999999", 404),
                 ("/modelos/999999", 404), ("/modelos/999999/variables", 404), ("/ruta-inexistente", 404),
                 ("/series/200101?horizonte=2&desde=1980-01-01&hasta=2026-01-01", 422),
                 ("/series/999999?horizonte=2", 404)]
        for ruta, esperado in casos:
            with self.subTest(ruta=ruta):
                r = self.cliente.get("/api/v1" + ruta)
                self.assertEqual(r.status_code, esperado, r.text)
                self.assertEqual(set(r.json()), {"codigo", "mensaje", "detalle"})

    def test_cache_revision_y_bd_caida(self):
        r1 = self.cliente.get("/api/v1/distritos")
        r2 = self.cliente.get("/api/v1/distritos")
        self.assertEqual((r1.headers["X-Cache"], r2.headers["X-Cache"]), ("MISS", "HIT"))
        self.assertEqual(self.cliente.get("/api/v1/distritos", headers={"Cache-Control": "no-cache"}).headers["X-Cache"], "BYPASS")
        self.post("/admin/inferencias", {"horizonte": 2})
        self.assertEqual(self.cliente.get("/api/v1/distritos").headers["X-Cache"], "MISS")
        with self.motor.begin() as conexion:
            conexion.execute(text("DROP TABLE alerta"))
            conexion.execute(text("DROP TABLE prediccion"))
        r = self.cliente.get("/api/v1/tablero/resumen?horizonte=2")
        self.assertEqual(r.status_code, 503)
        self.assertNotIn("DROP", r.text)

    def test_openapi_contrato_tabla_2(self):
        schema = self.cliente.get("/openapi.json").json()
        rutas = {(m, p.removeprefix("/api/v1")) for p, metodos in schema["paths"].items() for m in metodos}
        self.assertEqual(rutas, TABLA_2 | EXTENSIONES)
        for ruta in ("/api/v1/admin/inferencias", "/api/v1/admin/modelos/{version}/activar"):
            self.assertIn("security", schema["paths"][ruta]["post"])
        self.assertEqual(schema["components"]["securitySchemes"]["APIKeyHeader"]["name"], "X-API-Key")
        self.assertNotIn(CLAVE, str(schema))
        ejemplo = schema["paths"]["/api/v1/predicciones"]["get"]["responses"]["200"]["content"]["application/json"]["examples"]["bd_real"]["value"]
        self.assertEqual(ejemplo["fecha_corte_datos"], "2025-12-27")
        self.assertIn("examples", schema["paths"]["/api/v1/alertas"]["get"]["responses"]["200"]["content"]["application/json"])

    def test_sin_url_503_y_url_del_entorno(self):
        with entorno_bd(""), TestClient(crear_app()) as c:
            r = c.get("/api/v1/salud")
            self.assertEqual((r.status_code, r.json()["codigo"]), (503, "bd_no_disponible"))
            self.assertEqual(c.get("/openapi.json").status_code, 200)
        with entorno_bd(str(self.motor.url)), TestClient(crear_app(almacenamiento=self.almacenamiento)) as c:
            self.assertEqual(c.get("/api/v1/salud").status_code, 200)

    def test_exportar_openapi(self):
        from src.api import exportar_openapi
        destino = Path(self.carpeta.name) / "openapi.json"
        original = exportar_openapi.OPENAPI_JSON
        exportar_openapi.OPENAPI_JSON = destino
        try:
            r = exportar_openapi.exportar(self.motor)
        finally:
            exportar_openapi.OPENAPI_JSON = original
        self.assertEqual(r["rutas"], 15)
        self.assertTrue(destino.is_file())

    def test_base_vacia_sin_cero_ficticio(self):
        with tempfile.TemporaryDirectory() as carpeta:
            motor = motor_temporal(Path(carpeta))
            try:
                with TestClient(crear_app(motor, self.cfg, almacenamiento=self.almacenamiento)) as c:
                    salud = c.get("/api/v1/salud").json()
                    self.assertIsNone(salud["fecha_corte_datos"])
                    self.assertIsNone(salud["ultima_ejecucion"])
                    self.assertEqual(c.get("/api/v1/distritos").json()["total"], 0)
                    tablero = c.get("/api/v1/tablero/resumen?horizonte=2").json()
                    self.assertFalse(tablero["disponible"])
                    self.assertIsNone(tablero["casos_observados_ultima_semana"]["valor"])
                    self.assertFalse(c.get("/api/v1/modelos/activo").json()["disponible"])
                    self.assertEqual(c.get("/api/v1/series/200101?horizonte=2").status_code, 404)
            finally:
                motor.dispose()

    def test_api_no_lee_data(self):
        codigo = '''
import sys
from pathlib import Path
from fastapi.testclient import TestClient
from src.api.main import crear_app
from src.db.sesion import crear_motor
from src.serving.almacenamiento import AlmacenamientoLocal
from src.utils.paths import DATA
motor = crear_motor(sys.argv[1])
def auditar(evento, argumentos):
    if evento == "open" and isinstance(argumentos[0], (str, bytes)):
        if Path(argumentos[0]).resolve().is_relative_to(DATA):
            raise RuntimeError("La API intentó leer data/")
sys.addaudithook(auditar)
with TestClient(crear_app(motor, clave_api="verificacion", almacenamiento=AlmacenamientoLocal(sys.argv[2]))) as c:
    assert c.get("/api/v1/mapa-riesgo?horizonte=2").status_code == 200
    assert c.get("/api/v1/series/200101?horizonte=2").status_code == 200
    r = c.post("/api/v1/admin/inferencias", json={"horizonte": 2}, headers={"X-API-Key": "verificacion"})
    assert r.status_code == 200, r.text
motor.dispose()
print("API sin lecturas de data/: OK")
'''
        proceso = subprocess.run([sys.executable, "-c", codigo, str(self.motor.url), str(Path(self.base.name) / "storage")],
                                 cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(proceso.returncode, 0, proceso.stderr)
        self.assertIn("OK", proceso.stdout)


class TestCache(unittest.TestCase):
    def test_expiracion_capacidad_y_copia_independiente(self):
        cache = CacheLecturas(ttl=10, capacidad=1)
        cache.guardar("uno", {"valor": [0]})
        copia = cache.obtener("uno")
        copia["valor"].append(1)
        self.assertEqual(cache.obtener("uno"), {"valor": [0]})
        cache.guardar("dos", {"valor": None})
        self.assertIsNone(cache.obtener("uno"))
        cache.ttl = 0
        self.assertIsNone(cache.obtener("dos"))


if __name__ == "__main__":
    unittest.main()
