"""Contract v1 with data: every endpoint of Table 2 and the extensions validates against its schema.

It runs with h=2, 3 and 4 on a migrated SQLite with the published backend fixtures (real rows and
real XGBoost boosters). In the fixtures h=3 has no model, and a test removes h=4 from the
experimental selection to show that the served horizons come from the database.
"""

from dataclasses import replace
from pathlib import Path
import shutil
import tempfile
import unittest

from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.engine import URL

from backend_support import datos_muestra, motor_temporal
from serving_support import preparar_muestra
from apps.api.contract import CONTRACT_HEADER, CONTRACT_VERSION
from apps.api.main import create_app
from apps.api import schemas as s
from denguekay.db.models import Alert, ModelVersion, Prediction, SystemParameter
from denguekay.db.session import make_engine, transaction
from denguekay.serving.inference import update_alerts
from denguekay.serving.load_data import persist_load
from denguekay.serving.publish import publish_to_db
from denguekay.serving.storage import LocalStorage

KEY = "clave-contrato-v1"
HORIZONS = (2, 3, 4)


class TestContractV1(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = tempfile.TemporaryDirectory()
        folder = Path(cls.base.name)
        cls.cfg, protocol, prepared = preparar_muestra()
        data = datos_muestra(folder, cls.cfg.seleccion_experimental)
        data = replace(data, observaciones=[o for o in data.observaciones if o["id_semana"] >= 202530])
        cls.storage = LocalStorage(folder / "storage")
        template = folder / "plantilla"
        template.mkdir()
        engine = motor_temporal(template)
        with transaction(engine) as session:
            persist_load(session, data)
        publish_to_db(engine, data, protocol, prepared, (2, 4), cls.cfg, "run-contrato", "huella-contrato",
                      cls.storage, 0)
        with transaction(engine) as session:
            # One real prediction raised to muy_alto so that an alert exists to validate.
            p = session.scalar(select(Prediction).where(Prediction.ubigeo == "200101", Prediction.horizonte == 2,
                                                        Prediction.id_semana_corte == 202552))
            p.probabilidad_brote, p.nivel_riesgo = 0.8, "muy_alto"
            session.flush()
            update_alerts(session, 2, 202552)
        engine.dispose()
        cls.template = template / "pruebas.db"

    @classmethod
    def tearDownClass(cls):
        cls.base.cleanup()

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        target = Path(self.folder.name) / "api.db"
        shutil.copyfile(self.template, target)
        self.engine = make_engine(URL.create("sqlite", database=str(target)))
        self.client = TestClient(create_app(self.engine, self.cfg, api_key=KEY, storage=self.storage))
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.engine.dispose()
        self.folder.cleanup()

    def call(self, method, path, model, status=200, body=None):
        """Request, check the status and the contract header, and validate the body against ``model``."""
        headers = {"X-API-Key": KEY, "Cache-Control": "no-cache"}
        r = self.client.request(method, "/api/v1" + path, json=body, headers=headers)
        self.assertEqual(r.status_code, status, f"{method} {path}: {r.text}")
        self.assertEqual(r.headers[CONTRACT_HEADER], CONTRACT_VERSION)
        return model.model_validate(r.json())

    def get(self, path, model, status=200):
        return self.call("GET", path, model, status)

    def test_every_endpoint_validates_with_h2_h3_h4(self):
        self.get("/salud", s.SaludRespuesta)
        self.get("/configuracion", s.ConfiguracionRespuesta)
        self.get("/distritos", s.Pagina[s.DistritoRespuesta])
        self.get("/distritos/200101", s.DistritoRespuesta)
        self.get("/observaciones?ubigeo=200101", s.Pagina[s.ObservacionRespuesta])
        for h in HORIZONS:
            with self.subTest(horizonte=h):
                self.get(f"/predicciones?horizonte={h}", s.Pagina[s.PrediccionRespuesta])
                self.get(f"/series/200101?horizonte={h}", s.SeriesRespuesta)
                self.get(f"/tablero/resumen?horizonte={h}", s.TableroRespuesta)
                self.get(f"/mapa-riesgo?horizonte={h}", s.MapaRiesgoRespuesta)
                self.get(f"/alertas?horizonte={h}", s.Pagina[s.AlertaRespuesta])
                self.get(f"/modelos/activo?horizonte={h}", s.ModelosActivosRespuesta)
        in_use = self.get("/modelos/activo", s.ModelosActivosRespuesta).elementos
        self.get(f"/modelos/{in_use[0].id_version}", s.ModeloDetalle)
        self.get(f"/modelos/{in_use[0].id_version}/variables", s.VariablesRespuesta)
        alert = self.get("/alertas?horizonte=2", s.Pagina[s.AlertaRespuesta]).elementos[0]
        self.get(f"/alertas/{alert.id_alerta}", s.AlertaRespuesta)
        for h in (2, 4):
            self.call("POST", "/admin/inferencias", s.InferenciaRespuesta, body={"horizonte": h})
        error = self.call("POST", "/admin/inferencias", s.ErrorRespuesta, 409, {"horizonte": 3})
        self.assertEqual((error.codigo, error.mensaje), ("inferencia_no_disponible", "sin modelo para h=3"))
        error = self.call("POST", f"/admin/modelos/{in_use[0].id_version}/activar", s.ErrorRespuesta, 409)
        self.assertEqual(error.codigo, "no_cumple_umbrales")
        self.get("/distritos/999999", s.ErrorRespuesta, 404)

    def test_configuration_comes_from_the_database(self):
        c = self.get("/configuracion", s.ConfiguracionRespuesta)
        self.assertEqual((c.version_contrato, c.horizontes_disponibles, c.horizonte_por_defecto),
                         (CONTRACT_VERSION, [2, 4], 4))
        by_h = {x.horizonte: x for x in c.horizontes}
        self.assertEqual((by_h[3].disponible, by_h[3].motivo, by_h[3].semana_corte_vigente), (False, "sin modelo para h=3", None))
        self.assertEqual(by_h[2].semana_corte_vigente.id_semana, 202552)
        self.assertTrue(c.experimental and by_h[2].experimental)
        self.assertEqual([n.nivel for n in c.niveles], ["bajo", "medio", "alto", "muy_alto"])
        self.assertEqual((c.cortes_riesgo.medio, c.cortes_riesgo.alto, c.cortes_riesgo.muy_alto), (0.25, 0.5, 0.75))
        mapa = self.get("/mapa-riesgo?horizonte=2", s.MapaRiesgoRespuesta)
        self.assertEqual(c.leyenda, mapa.leyenda)

    def test_horizon_without_model(self):
        """h=3 has no model in the fixtures; dropping h=4 from the selection makes it a horizon without model too."""
        h3 = self.get("/predicciones?horizonte=3", s.Pagina[s.PrediccionRespuesta])
        self.assertEqual((h3.disponible, h3.motivo, h3.total), (False, "sin modelo para h=3", 0))
        mapa = self.get("/mapa-riesgo?horizonte=3", s.MapaRiesgoRespuesta)
        self.assertEqual({f.properties.motivo for f in mapa.features}, {"sin modelo para h=3"})
        self.assertFalse(self.get("/series/200101?horizonte=3", s.SeriesRespuesta).disponible)
        self.assertEqual(self.get("/tablero/resumen?horizonte=3", s.TableroRespuesta).motivo, "sin modelo para h=3")
        with transaction(self.engine) as session:
            row = session.get(SystemParameter, "seleccion_experimental")
            row.valor = {k: v for k, v in row.valor.items() if k != "4"}
        c = self.get("/configuracion", s.ConfiguracionRespuesta)
        self.assertEqual(c.horizontes_disponibles, [2])
        self.assertEqual({x.horizonte: x.motivo for x in c.horizontes}[4], "sin modelo para h=4")
        activos = self.get("/modelos/activo?horizonte=4", s.ModelosActivosRespuesta)
        self.assertEqual((activos.disponible, activos.motivo), (False, "sin modelo para h=4"))
        self.assertEqual(self.get("/series/200101?horizonte=4", s.SeriesRespuesta).motivo, "sin modelo para h=4")

    def test_intervals_are_null_with_reason(self):
        page = self.get("/predicciones?horizonte=2", s.Pagina[s.PrediccionRespuesta])
        for p in page.elementos:
            self.assertEqual((p.casos_intervalo_inferior, p.casos_intervalo_superior, p.nivel_intervalo), (None, None, None))
            self.assertEqual(p.motivo_intervalo, "La versión del modelo no estima intervalos de casos" if p.disponible
                             else "Predicción no disponible")
        f = self.get("/mapa-riesgo?horizonte=2", s.MapaRiesgoRespuesta).features[0]
        self.assertIsNone(f.properties.casos_intervalo_inferior)

    def test_missing_default_horizon_is_503(self):
        with transaction(self.engine) as session:
            session.execute(text("DELETE FROM parametro_sistema WHERE clave = 'horizonte_por_defecto'"))
        error = self.get("/configuracion", s.ErrorRespuesta, 503)
        self.assertEqual(error.codigo, "parametros_no_configurados")

    def test_contract_header_on_errors_and_versions_kept_apart(self):
        r = self.client.get("/api/v1/ruta-inexistente")
        self.assertEqual((r.status_code, r.headers[CONTRACT_HEADER]), (404, CONTRACT_VERSION))
        self.assertIn(CONTRACT_HEADER, self.client.get("/api/v1/salud", headers={"Origin": self.cfg.cors_origen})
                      .headers["access-control-expose-headers"])
        salud = self.get("/salud", s.SaludRespuesta)
        self.assertNotEqual(salud.version_api, CONTRACT_VERSION)
        self.assertEqual(self.client.get("/openapi.json").json()["info"]["version"], CONTRACT_VERSION)

    def test_geometry_accepts_point_polygon_and_multipolygon(self):
        properties = self.get("/mapa-riesgo?horizonte=2", s.MapaRiesgoRespuesta).features[0].properties.model_dump()
        ring = [[-80.6, -5.2], [-80.5, -5.2], [-80.5, -5.1], [-80.6, -5.2]]
        for geometry in ({"type": "Point", "coordinates": [-80.6, -5.2]},
                         {"type": "Polygon", "coordinates": [ring]},
                         {"type": "MultiPolygon", "coordinates": [[ring], [ring]]}):
            with self.subTest(tipo=geometry["type"]):
                f = s.FeatureDistrito.model_validate({"type": "Feature", "id": "200101", "geometry": geometry,
                                                      "properties": properties})
                self.assertEqual(f.geometry.type, geometry["type"])
        with self.assertRaises(ValidationError):
            s.FeatureDistrito.model_validate({"type": "Feature", "id": "200101", "properties": properties,
                                              "geometry": {"type": "LineString", "coordinates": ring}})

    def test_selection_reads_versions_not_code(self):
        """Removing the h=2 versions from the database also removes h=2 from the served horizons."""
        with transaction(self.engine) as session:
            session.execute(Alert.__table__.delete())
            session.execute(Prediction.__table__.update().values(id_version_clasificador=None, id_version_regresor=None))
            session.execute(text("DELETE FROM importancia_variable"))
            session.execute(ModelVersion.__table__.delete().where(ModelVersion.horizonte == 2))
        self.assertEqual(self.get("/configuracion", s.ConfiguracionRespuesta).horizontes_disponibles, [4])


if __name__ == "__main__":
    unittest.main()
