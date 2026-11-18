"""Quality and completeness report (HU0005-4 and HU0005-5): the measures, the thresholds and that it only reads."""

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pandas as pd

from denguekay.config.paths import DATA, UBIGEO_CATALOG
from denguekay.data.processing.epi_sala import load_ubigeo_catalog
from denguekay.data.validation import quality_report as qr

DISTRICTS = load_ubigeo_catalog(UBIGEO_CATALOG).ubigeo.tolist()
WEEKS = pd.date_range("2024-01-07", periods=4, freq="W-SUN")   # 65 districts x 4 weeks = 260 expected rows


def panel(cases=2):
    rows = [{"ubigeo": u, "anio": 2024, "semana": i + 1, "semana_inicio": w.date().isoformat(), "casos_Dengue": cases,
             "temp_media": 25.0, "precip_total_mm": 1.0, "hum_rel_media": 60.0, "poblacion": 1000}
            for u in DISTRICTS for i, w in enumerate(WEEKS)]
    return pd.DataFrame(rows)


def raw_notifications(confirmed, probable=0, other=0):
    rows = [{"departamento": "PIURA", "tipo_dx": "C", "ubigeo": "200101", "ano": 2024, "semana": 1}] * confirmed
    rows += [{"departamento": "PIURA", "tipo_dx": "P", "ubigeo": "200101", "ano": 2024, "semana": 1}] * probable
    rows += [{"departamento": "LIMA", "tipo_dx": "C", "ubigeo": "150101", "ano": 2024, "semana": 1}] * other
    return pd.DataFrame(rows)


class Inputs:
    """Writes the three inputs in a temporary folder and builds the report from them."""

    def __init__(self, folder, frame, confirmed=None):
        self.folder = Path(folder)
        frame.to_csv(self.folder / "panel.csv", index=False)
        pd.DataFrame({"ubigeo": frame.ubigeo, "anio": frame.anio, "semana": frame.semana, "casos_Dengue": 0,
                      "source": "verified"}).to_csv(self.folder / "panel.coverage.csv", index=False)
        confirmed = int(frame.casos_Dengue.sum()) if confirmed is None else confirmed
        raw_notifications(confirmed, probable=3, other=5).to_csv(self.folder / "notificaciones.csv", index=False)
        pd.DataFrame({"ubigeo": ["200101"], "anio": [2025], "semana": [1], "casos_Dengue": [1],
                      "tipo_dx": ["C"]}).to_csv(self.folder / "sala.csv", index=False)
        pd.DataFrame({"ubigeo": ["200101"], "anio": [2024], "semana": [1], "casos_Dengue": [1]}).to_csv(
            self.folder / "historia.csv", index=False)

    def report(self):
        return qr.build_report(self.folder / "panel.csv", self.folder / "notificaciones.csv", self.folder / "sala.csv",
                               history_path=self.folder / "historia.csv", meteo_path=self.folder / "no_hay_meteo.csv",
                               socio_path=self.folder / "no_hay_socio.csv",
                               climate={"enso": self.folder / "a", "chirps_ee": self.folder / "b",
                                        "chirps_final": self.folder / "c", "chirps_prelim": self.folder / "d",
                                        "era5_recent": self.folder / "e", "historical": {}, "frozen": "2026-11-12"})


class TestCompleteness(unittest.TestCase):
    def build(self, frame, confirmed=None):
        with TemporaryDirectory() as directory:
            return Inputs(directory, frame, confirmed).report()

    def test_a_complete_panel_is_conforming(self):
        report = self.build(panel())
        self.assertEqual(report["estado"], "conforme")
        self.assertEqual(report["completitud"]["filas_esperadas"], 260)
        self.assertEqual((report["completitud"]["completitud"], report["completitud"]["filas_ausentes"]), (1.0, 0))
        self.assertEqual(report["no_conformidades"], [])
        self.assertEqual(set(report["completitud"]["por_variable"]), set(qr.MANDATORY.values()))

    def test_exactly_95_percent_passes_and_one_row_less_fails(self):
        frame = panel()
        at_limit = self.build(frame.iloc[:-13])           # 247 / 260 = 0.95
        self.assertEqual(at_limit["completitud"]["completitud"], 0.95)
        self.assertTrue(at_limit["completitud"]["cumple"])
        below = self.build(frame.iloc[:-14], confirmed=int(frame.iloc[:-14].casos_Dengue.sum()))   # 246 / 260
        self.assertFalse(below["completitud"]["cumple"])
        self.assertEqual(below["estado"], "no conforme")
        self.assertEqual(below["completitud"]["filas_ausentes"], 14)

    def test_a_null_in_a_mandatory_column_makes_the_row_incomplete_and_names_the_variable(self):
        frame = panel()
        frame.loc[frame.index[:30], "temp_media"] = None   # 30 of 260 rows: 88.5 %
        report = self.build(frame)
        self.assertEqual(report["completitud"]["filas_completas"], 230)
        self.assertEqual(report["estado"], "no conforme")
        self.assertEqual(report["no_conformidades"][0]["variables_afectadas"], ["temp_media"])
        self.assertEqual(report["completitud"]["por_variable"]["temp_media"]["nulos"], 30)

    def test_a_missing_row_counts_against_every_variable_and_duplicates_are_reported(self):
        frame = pd.concat([panel().iloc[1:], panel().iloc[[5]]], ignore_index=True)
        report = self.build(frame, confirmed=int(frame.casos_Dengue.sum()))
        self.assertEqual(report["completitud"]["filas_ausentes"], 1)
        self.assertEqual(report["duplicados"], {"llave_ubigeo_anio_semana": 1, "llave_ubigeo_semana_inicio": 1})
        keys = {"ubigeo", "semana_inicio"}   # the key of an absent row is the expected one; every other column is null
        by_variable = report["completitud"]["por_variable"]
        self.assertTrue(all(v["nulos"] == (0 if k in keys else 1) for k, v in by_variable.items()))

    def test_coverage_by_district_has_the_65_districts(self):
        report = self.build(panel())
        coverage = report["cobertura_por_distrito"]
        self.assertEqual(set(coverage), set(DISTRICTS))
        self.assertEqual(coverage["200101"]["semanas_presentes"], 4)
        self.assertEqual(coverage["200101"]["completitud"], 1.0)
        self.assertEqual(coverage["200101"]["casos_verificados"], 1.0)


class TestTraceability(unittest.TestCase):
    """HU0001-3 (repeated keys), HU0003-2 (territorial correspondence) and HU0002-1 (climate sources)."""

    def test_the_report_records_the_duplicate_control_of_each_epidemiological_source(self):
        with TemporaryDirectory() as directory:
            report = Inputs(directory, panel()).report()
        controls = {c["fuente"]: c for c in report["control_duplicados_fuente_epidemiologica"]}
        self.assertEqual(len(controls), 3)
        self.assertTrue(all(c["resultado"] == "sin duplicados" and c["regla_aplicada"] for c in controls.values()))
        self.assertIn("se suman", controls["Histórico confirmado (CSV epidemiológico, hasta 2024)"]["regla_aplicada"])
        self.assertIn("se detienen", controls["Sala Situacional confirmada (desde 2025)"]["regla_aplicada"])

    def test_repeated_keys_of_the_history_are_added_up_and_repeated_keys_of_the_sala_are_a_nonconformity(self):
        with TemporaryDirectory() as directory:
            inputs = Inputs(directory, panel())
            pd.DataFrame({"ubigeo": ["200101", "200101"], "anio": [2024, 2024], "semana": [1, 1],
                          "casos_Dengue": [1, 2]}).to_csv(Path(directory) / "historia.csv", index=False)
            pd.DataFrame({"ubigeo": ["200101"] * 2, "anio": [2025, 2025], "semana": [1, 1], "casos_Dengue": [1, 1],
                          "tipo_dx": ["C", "C"]}).to_csv(Path(directory) / "sala.csv", index=False)
            report = inputs.report()
        history, sala, _ = report["control_duplicados_fuente_epidemiologica"]
        self.assertEqual((history["claves_repetidas"], history["filas_con_llave_repetida"]), (1, 2))
        self.assertEqual(history["ejemplos"], [{"ubigeo": "200101", "anio": 2024, "semana": 1, "filas": 2}])
        self.assertEqual(sala["resultado"], "con duplicados")
        self.assertEqual(report["estado"], "no conforme")
        self.assertTrue(any("HU0001-3" in n["criterio"] and "Sala" in n["criterio"] for n in report["no_conformidades"]))
        self.assertIn("Ejemplos de claves repetidas en Sala", qr.to_markdown(report))

    def test_the_territorial_section_names_the_districts_without_correspondence(self):
        meteo = pd.DataFrame({"provincia": ["Piura", "Piura"], "distrito": ["Piura", "Catacaos"],
                              "distrito_key": ["PIURA", "CATACAOS"]})
        socio = pd.DataFrame({"ubigeo": ["200101", "200104"], "distrito_key": ["PIURA", "CASTILLA"]})
        result = qr.territorial_correspondence(panel(), DISTRICTS, meteo, socio)
        self.assertFalse(result["cumple"])
        self.assertEqual(result["meteo_vs_socio"]["solo_en_meteo"], ["CATACAOS"])
        self.assertEqual(result["meteo_vs_socio"]["solo_en_socio"], ["CASTILLA"])
        self.assertTrue(qr.territorial_correspondence(panel(), DISTRICTS)["cumple"])
        unknown = panel().assign(ubigeo="209999")
        self.assertEqual(qr.territorial_correspondence(unknown, DISTRICTS)["en_panel_sin_catalogo"], ["209999"])

    def test_a_panel_district_outside_the_catalogue_is_a_nonconformity_with_the_district(self):
        with TemporaryDirectory() as directory:
            frame = panel()
            frame.loc[frame.ubigeo.eq("200101"), "ubigeo"] = "209999"
            report = Inputs(directory, frame).report()
        item = next(n for n in report["no_conformidades"] if "HU0003-2" in n["criterio"])
        self.assertEqual(item["valor"]["en_panel_sin_catalogo"], ["209999"])
        self.assertIn("209999", qr.to_markdown(report))

    def test_the_markdown_has_the_three_sections(self):
        with TemporaryDirectory() as directory:
            text = qr.to_markdown(Inputs(directory, panel()).report())
        for title in ("## Control de duplicados de la fuente epidemiológica (HU0001-3)",
                      "## Correspondencia territorial (HU0003-2)",
                      "## Fuentes climáticas: producto y fecha de extracción (HU0002-1)"):
            self.assertIn(title, text)


class TestDiscards(unittest.TestCase):
    def test_the_records_outside_the_panel_are_discarded_and_the_excluded_ones_are_apart(self):
        frame = panel(cases=2)                                   # 520 cases in the panel
        with TemporaryDirectory() as directory:
            report = Inputs(directory, frame, confirmed=540).report()   # 20 records never reached the panel
        discards = report["observaciones_descartadas"]
        self.assertEqual((discards["registros_originales"], discards["descartados"]), (540, 20))
        self.assertAlmostEqual(discards["proporcion_descartada"], 20 / 540, places=6)
        self.assertTrue(discards["cumple"])
        self.assertEqual(discards["excluidos_por_definicion"],
                         {"piura_no_confirmadas": 3, "otros_departamentos_o_fuera_del_periodo": 5})

    def test_more_than_5_percent_discarded_is_not_conforming_and_it_names_the_cases(self):
        with TemporaryDirectory() as directory:
            report = Inputs(directory, panel(cases=2), confirmed=600).report()   # 80 of 600 = 13 %
        self.assertFalse(report["observaciones_descartadas"]["cumple"])
        self.assertEqual(report["estado"], "no conforme")
        self.assertEqual(report["no_conformidades"][0]["variables_afectadas"], ["casos"])

    def test_a_panel_with_more_cases_than_records_is_reported_as_excess_not_as_a_negative_discard(self):
        with TemporaryDirectory() as directory:
            report = Inputs(directory, panel(cases=2), confirmed=500).report()
        year = report["observaciones_descartadas"]["por_anio"][0]
        self.assertEqual((year["descartados"], year["exceso_en_el_panel"]), (0, 20))


class TestOutputAndReadOnly(unittest.TestCase):
    def test_zero_assigned_cases_are_measured_apart(self):
        with TemporaryDirectory() as directory:
            report = Inputs(directory, panel(), confirmed=520).report()
        before = report["casos_antes_de_asignar_ceros"]
        self.assertEqual((before["filas"], before["con_registro_de_casos_en_la_fuente"]), (260, 1))
        self.assertEqual(before["cero_asignado_en_la_union"], 259)

    def test_it_writes_json_and_markdown_outside_data_and_never_changes_its_inputs(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            inputs = Inputs(folder, panel())
            before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir()}
            report = inputs.report()
            written = qr.write_report(report, folder / "salida")
            self.assertEqual({p.name for p in written}, {"calidad_datos_v4.json", "calidad_datos_v4.md"})
            self.assertEqual(before, {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir()
                                      if p.is_file()})
            self.assertEqual(json.loads(written[0].read_text(encoding="utf-8"))["estado"], "conforme")
            text = written[1].read_text(encoding="utf-8")
            self.assertIn("Completitud 100,00 %", text)
            self.assertIn("conforme", text)

    def test_the_non_conforming_markdown_lists_the_affected_variables(self):
        frame = panel()
        frame.loc[frame.index[:30], "hum_rel_media"] = None
        with TemporaryDirectory() as directory:
            text = qr.to_markdown(Inputs(directory, frame).report())
        self.assertIn("**no conforme**", text)
        self.assertIn("variables afectadas: hum_rel_media", text)

    def test_it_refuses_to_write_inside_data(self):
        with self.assertRaisesRegex(ValueError, "nunca se escribe en data/"):
            qr.write_report({}, DATA / "silver")
        with self.assertRaisesRegex(ValueError, "nunca se escribe en data/"):
            qr.write_report({}, DATA)


if __name__ == "__main__":
    unittest.main()
