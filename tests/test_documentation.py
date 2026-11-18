"""Documentation promised by the user stories HU0003-1 and HU0018-1 to HU0018-4.

The documents are text, so what can be proved is that each one covers what its criterion lists and that what it names
exists in the repository: the modules, the commands, the environment variables of ``.env.example`` and the sections of
the operation guide."""

import contextlib
import io
import re
import unittest

import pandas as pd

from denguekay.config.paths import ROOT
from denguekay.data.processing.socio_interpolation import SOCIO_COLUMNS, build_annual_socio


def read(relative):
    return (ROOT / relative).read_text(encoding="utf-8")


def section(text, title):
    """The body of the ``## title`` section (up to the next ``## ``)."""
    match = re.search(rf"^## {re.escape(title)}.*?$(.*?)(?=^## |\Z)", text, re.S | re.M)
    assert match, f"falta la sección «{title}»"
    return match.group(1)


class TestSociodemographicProvenance(unittest.TestCase):
    """HU0003-1: district, reference year, unit and provenance of every integrated variable."""

    def test_the_annual_silver_keeps_the_district_and_the_year(self):
        wide = pd.DataFrame({"ubigeo": ["200101"], "departamento": ["PIURA"], "provincia": ["PIURA"],
                             "distrito": ["PIURA"], "distrito_key": ["PIURA"], "pob_censada_2017": [100],
                             **{f"pob_proyectada_{year}": [100 + year - 2017] for year in range(2018, 2026)},
                             "fraccion_rural_2017": [0.2], "fraccion_rural_2025": [0.4]})
        with contextlib.redirect_stdout(io.StringIO()):
            annual = build_annual_socio(wide)
        self.assertEqual(sorted(annual.anio), list(range(2017, 2026)))
        self.assertEqual(set(annual.ubigeo), {"200101"})
        self.assertEqual(set(annual.distrito), {"PIURA"})
        self.assertAlmostEqual(float(annual.loc[annual.anio.eq(2021), "fraccion_rural"].iloc[0]), 0.3)

    def test_the_pipeline_guide_gives_reference_year_unit_and_source_of_every_variable(self):
        body = section(read("docs/pipeline.md"), "Sociodemografía: año de referencia y regla temporal (HU0003-4)")
        for variable in SOCIO_COLUMNS:
            self.assertIn(f"`{variable}`", body, variable)
        for word in ("Año de referencia", "Unidad", "personas", "fracción entre 0 y 1", "INEI",
                     "data_socio_2017_2025.xlsx"):
            self.assertIn(word, body)


class TestArchitectureDocument(unittest.TestCase):
    """HU0018-1: components, dependencies, interfaces and data flow from the sources to the web application."""

    def test_the_flow_names_every_component_from_the_sources_to_the_web_application(self):
        text = read("docs/architecture.md")
        flow = section(text, "Componentes y flujo")
        for part in ("fuentes", "pipelines/notebooks", "data/silver", "data/gold", "denguekay.serving", "denguekay.db",
                     "apps/api", "apps/web", "v4_weekly", "models/registry"):
            self.assertIn(part, flow, part)
        self.assertIn("flowchart", flow)

    def test_every_component_it_names_exists_in_the_repository(self):
        for path in ("src/denguekay/data", "src/denguekay/features", "src/denguekay/model", "src/denguekay/serving",
                     "src/denguekay/db", "src/denguekay/pipelines", "apps/api", "apps/web", "models/registry"):
            self.assertTrue((ROOT / path).is_dir(), path)
        backend = read("docs/backend/arquitectura.md")
        for title in ("Contenedores y componentes", "Modelo de datos", "Secuencia: publicación",
                      "Secuencia: inferencia por la API", "Límites"):
            self.assertIn(f"## {title}", backend)

    def test_the_dependencies_and_interfaces_are_documented(self):
        text = read("docs/architecture.md")
        self.assertIn("tests/test_layout.py", text)   # the dependency direction is checked by a test
        self.assertIn("importa", text)
        self.assertTrue((ROOT / "docs/backend/openapi_v1.json").is_file())
        self.assertIn("openapi_v1.json", text)


class TestReproductionGuide(unittest.TestCase):
    """HU0018-2: rebuild the dataset, run the training or the inference and recognise versions and parameters."""

    def test_it_gives_the_commands_and_the_versioned_records(self):
        text = read("docs/reproducibilidad.md")
        for part in ("run_all --version v4", "release_bundles", "--verificar", "constraints.txt",
                     "models/registry/", "manifiesto"):
            self.assertIn(part, text, part)
        self.assertIn("denguekay.model.reproduce", text)
        for version in ("v0", "v1", "v2", "v3", "v4"):
            self.assertTrue((ROOT / "models" / "registry" / version / "ficha.json").is_file(), version)
        self.assertTrue((ROOT / "docs/modeling/reproducir_v4.md").is_file())


class TestDeploymentGuide(unittest.TestCase):
    """HU0018-3: requirements, configuration, dependencies, variables and checks after the deployment."""

    def test_every_variable_of_the_environment_template_is_documented(self):
        template = read(".env.example")
        variables = re.findall(r"^[#\s]*([A-Z][A-Z0-9_]+)=", template, re.M)
        self.assertGreaterEqual(len(variables), 8)
        guide = read("docs/backend/despliegue.md")
        for variable in variables:
            self.assertIn(f"`{variable}`", guide, variable)

    def test_it_covers_the_dependencies_the_configuration_and_the_checks_after_deploying(self):
        guide = read("docs/backend/despliegue.md")
        for part in ("requirements-api.txt", "render.yaml", "alembic upgrade head", "/api/v1/salud", "conexion_bd",
                     "Secrets de GitHub Actions"):
            self.assertIn(part, guide, part)
        self.assertTrue((ROOT / "render.yaml").is_file())
        self.assertTrue((ROOT / "requirements-api.txt").is_file())


class TestMaintenanceGuide(unittest.TestCase):
    """HU0018-4: monitoring, retraining, versioning, return to a validated version and the support responsibilities."""

    def test_the_operation_guide_covers_the_five_topics(self):
        guide = read("docs/backend/operacion.md")
        body = section(guide, "Monitoreo, versiones y responsabilidades de soporte (HU0018-4)")
        for topic in ("Monitoreo", "Reentrenamiento", "Versionamiento", "Retorno a una versión validada", "Soporte",
                      "Nicolás Miranda", "Rosa Rodríguez"):
            self.assertIn(topic, body, topic)
        self.assertIn("## Respaldo, reversión y mantenimiento", guide)
        self.assertIn("## Inferencia y activación desde la API", guide)

    def test_the_documents_it_points_to_exist(self):
        self.assertTrue((ROOT / "docs/modeling/reentrenamiento.md").is_file())
        self.assertTrue((ROOT / "models/registry/CHANGELOG.md").is_file())
        self.assertIn("activar", read("docs/backend/operacion.md"))


if __name__ == "__main__":
    unittest.main()
