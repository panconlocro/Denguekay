"""Contrato HTTP con SQLite migrada, subconjuntos reales y boosters XGBoost reales."""

from copy import deepcopy
from dataclasses import replace
from datetime import date
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from backend_soporte import datos_muestra, entorno_bd, motor_temporal
from serving_soporte import preparar_muestra
from src.api.cache import CacheLecturas
from src.api.main import crear_app
from src.db.modelos import (ActivacionModelo, Alerta, CargaDatos, Distrito, EjecucionPrediccion,
                            ObservacionSemanal, Prediccion, VersionModelo)
from src.db.sesion import transaccion
from src.serving.artefactos import huella_json, predecir_con_version
from src.serving.cargar_datos import persistir_carga
from src.serving.publicacion import guardar_versiones, publicar_lote
from src.serving.publicar import iniciar_ejecucion
from src.utils.paths import ROOT


class TestAPIReal(unittest.TestCase):
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
        with transaccion(self.motor) as s:
            persistir_carga(s, self.datos)
            self.ejecucion_id, _ = iniciar_ejecucion(s, huella_json("API con datos reales"),
                date(2025, 12, 27), self.protocolo.hashes)
            publicar_lote(s, self.ejecucion_id, self.preparadas, self.futuros,
                          self.protocolo, (2, 4), self.cfg, None, [], 0)
            self.ubigeo = s.scalar(select(Prediccion.ubigeo).where(Prediccion.tipo == "vigente"))
            self.modelo_id = s.scalar(select(VersionModelo.id).where(VersionModelo.horizonte == 2,
                VersionModelo.tipo == "clasificacion", VersionModelo.activa.is_(True)))
        self.app = crear_app(self.motor, self.cfg, clave_api="clave-local-de-prueba")
        self.cliente = TestClient(self.app)
        self.cliente.__enter__()

    def tearDown(self):
        self.cliente.__exit__(None, None, None)
        self.motor.dispose()
        self.carpeta.cleanup()

    def get(self, ruta):
        respuesta = self.cliente.get("/api/v1" + ruta)
        self.assertEqual(respuesta.status_code, 200, respuesta.text)
        self.assertGreaterEqual(float(respuesta.headers["X-Tiempo-Respuesta-ms"]), 0)
        return respuesta.json()

    def post(self, ruta):
        return self.cliente.post("/api/v1" + ruta, headers={"X-API-Key": "clave-local-de-prueba"})

    def conteos(self):
        with transaccion(self.motor) as s:
            return {m.__tablename__: s.scalar(select(func.count()).select_from(m))
                    for m in (VersionModelo, Prediccion, EjecucionPrediccion, ActivacionModelo, Alerta)}

    def test_salud_catalogo_paginacion_y_geojson_reales(self):
        salud = self.get("/salud")
        self.assertEqual(salud["fecha_corte_datos"], "2025-12-27")
        self.assertEqual(len(salud["versiones_activas"]), 6)
        lista = self.get("/distritos?pagina=2&tamano_pagina=10")
        self.assertEqual(lista["total"], 65)
        self.assertEqual(len(lista["elementos"]), 10)
        d = self.get(f"/distritos/{self.ubigeo}")
        self.assertIsInstance(d["ubigeo"], str)
        geo = self.get("/distritos/geojson")
        self.assertEqual(len(geo["features"]), 65)
        self.assertTrue(all(f["geometry"]["type"] == "Point" for f in geo["features"]))
        self.assertTrue(all(f["properties"]["motivo_geometria"] for f in geo["features"]))

    def test_observaciones_cero_real_no_es_faltante_y_filtros(self):
        with transaccion(self.motor) as s:
            cero = s.scalar(select(ObservacionSemanal).where(ObservacionSemanal.casos == 0))
            self.assertIsNotNone(cero)
            ruta = f"/observaciones?ubigeo={cero.ubigeo}&desde={cero.semana_inicio}&hasta={cero.semana_inicio}"
        o = self.get(ruta)["elementos"][0]
        self.assertEqual(o["casos"], 0)
        self.assertTrue(o["disponible"])
        self.assertIsNone(o["motivo"])
        self.assertEqual(o["estado_validacion"], "no_aplica")
        self.assertIsNone(o["version_modelo_id"])
        self.assertIsNone(o["horizonte"])
        self.assertFalse(self.get("/observaciones?desde=2026-01-01")["disponible"])

    def test_prediccion_coincide_con_booster_guardado_y_corte(self):
        datos = self.get(f"/predicciones?horizonte=2&ubigeo={self.ubigeo}")
        p = datos["elementos"][0]
        self.assertEqual(p["tipo_dato"], "pronosticado")
        self.assertEqual(p["estado_validacion"], "experimental")
        self.assertEqual(p["fecha_corte_datos"], "2025-12-27")
        with transaccion(self.motor) as s:
            guardada = s.get(Prediccion, p["id"])
            v = s.get(VersionModelo, p["version_modelo_id"])
            self.assertEqual(p["probabilidad"], float(predecir_con_version(v, [guardada.caracteristicas])[0]))
        filtrada = self.get(f"/predicciones?horizonte=2&semana={p['semana_inicio']}")
        self.assertEqual(filtrada["total"], 3)
        self.assertEqual(self.get("/predicciones?horizonte=2&semana=2026-02-01")["total"], 0)

    def test_mapa_todos_los_distritos_sin_rescatar_pronostico_viejo(self):
        mapa = self.get("/mapa?horizonte=2")
        self.assertEqual(len(mapa["distritos"]), 65)
        sin_datos = [d for d in mapa["distritos"] if not d["disponible"]]
        self.assertEqual(len(sin_datos), 62)
        self.assertTrue(all(d["nivel_riesgo"] == "Sin datos" and d["prediccion"]["probabilidad"] is None for d in sin_datos))
        self.assertEqual([x["desde_inclusivo"] for x in mapa["leyenda"][:4]], [0, .25, .5, .75])
        tres = self.get("/mapa?horizonte=3")
        self.assertFalse(tres["disponible"])
        self.assertIsNone(tres["semana_objetivo"])
        self.assertTrue(all(d["nivel_riesgo"] == "Sin datos" for d in tres["distritos"]))

    def test_series_huecos_mmwr_y_oos_conservado(self):
        serie = self.get(f"/series/{self.ubigeo}?horizonte=2&desde=2025-12-21&hasta=2026-01-18")
        hueco = next(e for e in serie["elementos"] if e["semana_inicio"] == "2025-12-28")
        self.assertEqual((hueco["anio"], hueco["semana_epi"]), (2025, 53))
        self.assertIsNone(hueco["observado"]["casos"])
        self.assertFalse(hueco["observado"]["disponible"])
        self.assertIsNone(hueco["pronosticado"]["probabilidad"])
        self.assertTrue(hueco["pronosticado"]["motivo"])
        with transaccion(self.motor) as s:
            p = s.scalar(select(Prediccion).where(Prediccion.tipo == "retrospectiva"))
            ruta = f"/series/{p.ubigeo}?horizonte={p.horizonte}&desde={p.semana_inicio}&hasta={p.semana_inicio}"
            valor = p.probabilidad
        historico = self.get(ruta)["elementos"][0]["pronosticado"]
        self.assertEqual(historico["tipo"], "retrospectiva")
        self.assertEqual(historico["probabilidad"], valor)

    def test_tablero_total_regional_no_confunde_parcial_con_completo(self):
        tablero = self.get("/tablero?horizonte=2")
        self.assertEqual(tablero["cobertura"]["con_magnitud"], 3)
        self.assertIsNone(tablero["indicadores"]["casos_estimados_region"]["valor"])
        self.assertTrue(tablero["indicadores"]["casos_estimados_region"]["motivo"])
        self.assertTrue(tablero["indicadores"]["casos_estimados_distritos_disponibles"]["disponible"])
        sin_datos = self.get("/tablero?horizonte=3")
        self.assertTrue(all(i["valor"] is None and not i["disponible"] for i in sin_datos["indicadores"].values()))

    def test_alertas_historial_orden_y_umbral_f1_expuestos(self):
        alertas = self.get("/alertas?estado=retirada")["elementos"]
        self.assertTrue(alertas)
        niveles = {"Muy alto": 4, "Alto": 3, "Medio": 2, "Bajo": 1}
        valores = [niveles[a["nivel"]] for a in alertas]
        self.assertEqual(valores, sorted(valores, reverse=True))
        a = self.get(f"/alertas/{alertas[0]['id']}")
        self.assertEqual(a["estado_validacion"], "experimental")
        self.assertEqual(a["indicadores"]["tipo"], "retrospectiva")
        self.assertIn("alerta_modelo", a["indicadores"])
        self.assertEqual(self.get(f"/alertas?horizonte=2&ubigeo={self.ubigeo}&estado=activa")["total"], 0)

    def test_modelos_metricas_bloques_criterios_y_variables_sin_causalidad(self):
        self.assertEqual(self.get("/modelos")["total"], 30)
        v = self.get(f"/modelos/{self.modelo_id}")
        self.assertEqual(v["criterios_validacion"]["bloques"], ["temporada_2024"])
        self.assertEqual(v["estado_validacion"], "experimental")
        self.assertTrue(v["sha256_artefacto"])
        self.assertIn("particion_temporal", v)
        variables = self.get(f"/modelos/{self.modelo_id}/variables")
        self.assertTrue(variables["elementos"])
        self.assertIn("no implican causalidad", variables["nota"])
        with transaccion(self.motor) as s:
            historico = s.scalar(select(VersionModelo.id).where(VersionModelo.origen == "retrospectiva", VersionModelo.tipo == "clasificacion"))
        self.assertFalse(self.get(f"/modelos/{historico}/variables")["disponible"])
        self.assertFalse(self.get(f"/modelos/{historico}")["puede_activarse"])

    def test_politica_no_validadas_bloquea_componentes_alertas_y_escritura(self):
        cfg = replace(self.cfg, servir_no_validadas=False)
        with TestClient(crear_app(self.motor, cfg, clave_api="clave-local-de-prueba")) as c:
            for ruta in ("/predicciones?horizonte=2", "/alertas"):
                datos = c.get("/api/v1" + ruta).json()
                for fila in datos["elementos"]:
                    p = fila.get("indicadores", fila)
                    self.assertIsNone(p["probabilidad"])
                    self.assertIsNone(p["casos_estimados"])
                    self.assertFalse(p["disponible"])
                    self.assertIn("modelo no validado", p["motivo"])
            r = c.post("/api/v1/predicciones/recalcular?horizonte=2", headers={"X-API-Key": "clave-local-de-prueba"})
            self.assertEqual(r.status_code, 409)

    def test_404_422_formato_uniforme_y_validacion_parametros(self):
        casos = [("/distritos/999999", 404), ("/observaciones?ubigeo=999999", 404),
                 ("/distritos/123", 422), ("/predicciones?horizonte=1", 422),
                 ("/predicciones?horizonte=2&semana=2026-01-05", 422),
                 ("/observaciones?desde=2025-02-01&hasta=2025-01-01", 422),
                 ("/distritos?pagina=0", 422), ("/distritos?tamano_pagina=101", 422),
                 ("/alertas?estado=otro", 422), ("/alertas/999999", 404),
                 ("/modelos/999999", 404), ("/ruta-inexistente", 404),
                 (f"/series/{self.ubigeo}?horizonte=2&desde=1980-01-01&hasta=2026-01-01", 422)]
        for ruta, esperado in casos:
            with self.subTest(ruta=ruta):
                r = self.cliente.get("/api/v1" + ruta)
                self.assertEqual(r.status_code, esperado, r.text)
                self.assertEqual(set(r.json()), {"codigo", "mensaje", "detalle"})

    def test_clave_escritura_y_cors_restringido(self):
        for cabeceras in ({}, {"X-API-Key": "incorrecta"}):
            r = self.cliente.post("/api/v1/predicciones/recalcular?horizonte=2", headers=cabeceras)
            self.assertEqual(r.status_code, 401)
            self.assertEqual(set(r.json()), {"codigo", "mensaje", "detalle"})
        with TestClient(crear_app(self.motor, self.cfg, clave_api="")) as c:
            self.assertEqual(c.post("/api/v1/predicciones/recalcular?horizonte=2").status_code, 503)
        for origen, permitido in ((self.cfg.cors_origen, True), ("https://origen-no-autorizado.invalid", False)):
            r = self.cliente.get("/api/v1/distritos", headers={"Origin": origen})
            self.assertEqual("access-control-allow-origin" in r.headers, permitido)

    def test_cache_ttl_revision_invalida_y_no_oculta_bd_caida(self):
        r1 = self.cliente.get("/api/v1/distritos")
        r2 = self.cliente.get("/api/v1/distritos")
        self.assertEqual((r1.headers["X-Cache"], r2.headers["X-Cache"]), ("MISS", "HIT"))
        self.assertEqual(r1.json(), r2.json())
        self.post("/predicciones/recalcular?horizonte=2")
        self.assertEqual(self.cliente.get("/api/v1/distritos").headers["X-Cache"], "MISS")
        with self.motor.begin() as conexion:
            conexion.execute(text("DROP TABLE activacion_modelo"))
        r = self.cliente.get("/api/v1/distritos")
        self.assertEqual(r.status_code, 503)
        self.assertNotIn("DROP", r.text)
        self.assertEqual(set(r.json()), {"codigo", "mensaje", "detalle"})

    def test_recalcular_modelo_real_conserva_historia_y_horizonte_vecino(self):
        anteriores = self.conteos()
        cuatro = self.get("/predicciones?horizonte=4")["elementos"]
        actualizacion_cuatro = self.get("/mapa?horizonte=4")["fecha_actualizacion"]
        with transaccion(self.motor) as s:
            oos = {p.id: p.probabilidad for p in s.scalars(select(Prediccion).where(Prediccion.tipo == "retrospectiva"))}
        r = self.post("/predicciones/recalcular?horizonte=2")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["filas_generadas"], 3)
        nuevos = self.get("/predicciones?horizonte=2")["elementos"]
        self.assertTrue(all(p["ejecucion_id"] == r.json()["ejecucion_id"] for p in nuevos))
        self.assertEqual(self.get("/predicciones?horizonte=4")["elementos"], cuatro)
        self.assertEqual(self.get("/mapa?horizonte=4")["fecha_actualizacion"], actualizacion_cuatro)
        with transaccion(self.motor) as s:
            for p in nuevos:
                registro = s.get(Prediccion, p["id"])
                v = s.get(VersionModelo, registro.version_regresion_id)
                self.assertEqual(p["casos_estimados"], float(predecir_con_version(v, [registro.caracteristicas])[0]))
            self.assertEqual({p.id: p.probabilidad for p in s.scalars(select(Prediccion).where(Prediccion.tipo == "retrospectiva"))}, oos)
        self.assertEqual(self.conteos()["prediccion"], anteriores["prediccion"] + 3)

    def nueva_version_real(self, corte=None):
        copia = deepcopy(self.preparadas[2, "clasificacion", "servicio"])
        copia.datos["huella"] = huella_json({"original": copia.datos["huella"], "revision": str(corte)})
        if corte:
            copia.datos["entrenamiento_corte"] = corte
        with transaccion(self.motor) as s:
            return guardar_versiones(s, {(2, "clasificacion", "servicio"): copia}, None)[2, "clasificacion", "servicio"].id

    def test_activacion_y_retorno_version_anterior_con_predicciones_y_auditoria(self):
        otra = self.nueva_version_real()
        r = self.post(f"/modelos/{otra}/activar")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(self.get(f"/modelos/{otra}")["activa"])
        self.assertFalse(self.get(f"/modelos/{self.modelo_id}")["activa"])
        self.assertTrue(all(p["version_modelo_id"] == otra for p in self.get("/predicciones?horizonte=2")["elementos"]))
        retorno = self.post(f"/modelos/{self.modelo_id}/activar")
        self.assertEqual(retorno.status_code, 200, retorno.text)
        with transaccion(self.motor) as s:
            self.assertEqual(s.scalar(select(func.count()).select_from(Prediccion)), 30)
            self.assertEqual(s.scalar(select(func.count()).select_from(ActivacionModelo)), 8)
            self.assertIsNotNone(s.scalar(select(Prediccion).where(Prediccion.version_clasificacion_id == otra)))

    def test_activacion_sin_artefacto_o_con_fuga_revierte_atomicamente(self):
        with transaccion(self.motor) as s:
            historica = s.scalar(select(VersionModelo.id).where(VersionModelo.origen == "retrospectiva", VersionModelo.tipo == "clasificacion"))
        self.assertEqual(self.post(f"/modelos/{historica}/activar").status_code, 409)
        futura = self.nueva_version_real(date(2026, 1, 1))
        conteos = self.conteos()
        r = self.post(f"/modelos/{futura}/activar")
        self.assertEqual(r.status_code, 409)
        self.assertIn("después del origen", r.json()["mensaje"])
        self.assertEqual(self.conteos(), conteos)
        self.assertTrue(self.get(f"/modelos/{self.modelo_id}")["activa"])

    def test_vector_incompleto_no_publica_ni_borra_filas(self):
        with transaccion(self.motor) as s:
            p = s.scalar(select(Prediccion).where(Prediccion.tipo == "vigente", Prediccion.horizonte == 2))
            vector = dict(p.caracteristicas)
            vector.pop(next(iter(vector)))
            p.caracteristicas = vector
        conteos = self.conteos()
        r = self.post("/predicciones/recalcular?horizonte=2")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(self.conteos(), conteos)
        self.assertEqual(self.post("/predicciones/recalcular?horizonte=3").status_code, 409)

    def test_openapi_esquemas_errores_seguridad_y_no_claves(self):
        schema = self.cliente.get("/openapi.json").json()
        self.assertEqual(len(schema["paths"]), 16)
        self.assertIn("ErrorRespuesta", schema["components"]["schemas"])
        operacion = schema["paths"]["/api/v1/predicciones/recalcular"]["post"]
        self.assertIn("security", operacion)
        self.assertEqual(schema["components"]["securitySchemes"]["APIKeyHeader"]["name"], "X-API-Key")
        self.assertNotIn("clave-local-de-prueba", str(schema))

    def test_sin_url_503_sin_crear_una_bd_alternativa(self):
        with entorno_bd(""), TestClient(crear_app()) as c:
            r = c.get("/api/v1/salud")
            self.assertEqual(r.status_code, 503)
            self.assertEqual(r.json()["codigo"], "bd_no_disponible")
            # La documentación sigue accesible sin una conexión disponible.
            self.assertEqual(c.get("/openapi.json").status_code, 200)

    def test_url_local_vida_y_exportacion_con_ejemplos_reales(self):
        from src.api.openapi import ejemplos_reales
        with entorno_bd(str(self.motor.url)), TestClient(crear_app()) as c:
            self.assertEqual(c.get("/api/v1/salud").status_code, 200)
            schema = c.get("/openapi.json").json()
            ejemplo = schema["paths"]["/api/v1/predicciones"]["get"]["responses"]["200"]["content"]["application/json"]["examples"]["bd_real"]["value"]
            self.assertEqual(ejemplo["elementos"][0]["fecha_corte_datos"], "2025-12-27")
            self.assertEqual(ejemplo["elementos"][0]["ubigeo"], self.ubigeo)
        self.post("/predicciones/recalcular?horizonte=2")
        self.post(f"/modelos/{self.modelo_id}/activar")
        with transaccion(self.motor) as s:
            ejemplos = ejemplos_reales(s, self.cfg)
            self.assertIn(("/predicciones/recalcular", "post"), ejemplos)
            self.assertIn(("/modelos/{identificador}/activar", "post"), ejemplos)

    def test_base_vacia_valores_no_disponibles_sin_cero_ficticio(self):
        with tempfile.TemporaryDirectory() as carpeta:
            motor = motor_temporal(Path(carpeta))
            try:
                with TestClient(crear_app(motor, self.cfg)) as c:
                    salud = c.get("/api/v1/salud").json()
                    self.assertIsNone(salud["fecha_corte_datos"])
                    self.assertIsNone(salud["ultima_ejecucion"])
                    self.assertFalse(c.get("/api/v1/distritos").json()["disponible"])
                    self.assertFalse(c.get("/api/v1/distritos/geojson").json()["disponible"])
                    tablero = c.get("/api/v1/tablero?horizonte=2").json()
                    self.assertTrue(all(i["valor"] is None for i in tablero["indicadores"].values()))
            finally:
                motor.dispose()

    def test_error_booster_corrupto_no_filtra_detalles_ni_publica(self):
        with transaccion(self.motor) as s:
            version = s.get(VersionModelo, self.modelo_id)
            # Corrupción deliberada del artefacto real para comprobar la reversión.
            version.artefacto = {"artefacto_corrupto": True}
        conteos = self.conteos()
        with TestClient(self.app, raise_server_exceptions=False) as c:
            r = c.post("/api/v1/predicciones/recalcular?horizonte=2", headers={"X-API-Key": "clave-local-de-prueba"})
            self.assertEqual(r.status_code, 409)
            self.assertEqual(r.json()["codigo"], "reevaluacion_no_disponible")
            self.assertIn("requiere revisión", r.json()["mensaje"])
            self.assertIsNone(r.json()["detalle"])
        self.assertEqual(self.conteos(), conteos)

    def test_api_reevalua_sin_lecturas_de_data_ni_archivos_de_models(self):
        codigo = '''
import sys
from pathlib import Path
from fastapi.testclient import TestClient
from src.api.main import crear_app
from src.db.sesion import crear_motor
from src.utils.paths import DATA, MODELS
motor = crear_motor(sys.argv[1])
def auditar(evento, argumentos):
    if evento == "open" and isinstance(argumentos[0], (str, bytes)):
        ruta = Path(argumentos[0]).resolve()
        if ruta.is_relative_to(DATA) or ruta.is_relative_to(MODELS):
            raise RuntimeError("La API intentó leer un archivo de datos o modelos")
sys.addaudithook(auditar)
with TestClient(crear_app(motor, clave_api="verificacion")) as c:
    assert c.get("/api/v1/mapa?horizonte=2").status_code == 200
    assert c.get("/api/v1/series/200101?horizonte=2").status_code == 200
    r = c.post("/api/v1/predicciones/recalcular?horizonte=2", headers={"X-API-Key": "verificacion"})
    assert r.status_code == 200, r.text
motor.dispose()
print("API sin lecturas de data/ ni archivos de models/: OK")
'''
        proceso = subprocess.run([sys.executable, "-c", codigo, str(self.motor.url)],
            cwd=ROOT, capture_output=True, text=True, timeout=30)
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
