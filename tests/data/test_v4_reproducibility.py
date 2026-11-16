"""The V4 audit distinguishes drift, missing inputs and obsolete gold lineage."""

import hashlib
import json
import lzma
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from denguekay.data.validation.integrated_expectations import coverage_path
from denguekay.data.validation import v4_gold_reference as reference
from denguekay.data.validation import v4_reproducibility as audit
from denguekay.features.gold_v4 import GoldInputs


class TestV4Reproducibility(unittest.TestCase):
    def test_verifies_both_profiles_and_reports_drift_without_rewriting_inputs(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            relative = lambda p: p.relative_to(root).as_posix()
            frozen = GoldInputs(*(root / "archivado" / name for name in
                                  ("panel.csv", "historia.csv", "sala.csv", "era5.csv", "chirps.csv", "enso.csv", "geo.csv")))
            live = GoldInputs(*(root / "actual" / path.name for path in vars(frozen).values()))
            catalog, h2, model = root / "catalogo.csv", root / "manifest_fase6.json", root / "modelo"
            hashes = {}
            for path in (*vars(frozen).values(), *vars(live).values(), coverage_path(frozen.panel),
                         coverage_path(live.panel), catalog, h2):
                path.parent.mkdir(parents=True, exist_ok=True)
                payload = path.name.encode()
                path.write_bytes(payload)
                hashes[relative(path)] = hashlib.sha256(payload).hexdigest()
            output, local, verify = root / "gold.csv", root / "manifest_v4.json", root / "cotejo.json"
            study, registry = root / "estudio.json", root / "registro.json"
            names = [relative(path) for path in
                     (frozen.panel, frozen.history, frozen.sala, coverage_path(frozen.panel), frozen.era5, h2, catalog)]
            sources = {name: hashes[name] for name in names}
            sources.update({key: hashes[relative(path)] for key, path in
                            ((frozen.enso.name, frozen.enso), (frozen.chirps.name, frozen.chirps), ("geografia", frozen.geography))})
            study.write_text(json.dumps({"corte": "2026-10-17", "fuentes": sources, "archivos": {"test.ubj": "a"}}))
            registered = {key: value for key, value in hashes.items()
                          if not key.startswith("actual/") and key != relative(catalog)}
            registered["modelo/test.ubj"] = "a"
            registry.write_text(json.dumps({"version": "v4", "tag": "model/v4", "paquetes": [
                {"archivos": [{"ruta": key, "sha256": value} for key, value in registered.items()]}]}))
            output.write_bytes(b"recalculated")
            expected = hashlib.sha256(output.read_bytes()).hexdigest()

            def write_local_manifest(profile, paths):
                inputs = [*vars(paths).values(), coverage_path(paths.panel), catalog]
                local.write_text(json.dumps({"fuentes": {relative(path): hashlib.sha256(path.read_bytes()).hexdigest()
                                                        for path in inputs},
                                             "origen_insumos": profile, "corte_etiquetas": "2026-10-17",
                                             "archivo": output.name, "sha256": expected}))

            with patch.multiple(audit, ROOT=root, V4_STUDY_MANIFEST=study, V4_DATA_MANIFEST=registry, V4_FROZEN=model,
                                V4_LIVE_GEOGRAPHY=root / "new_geo.csv", UBIGEO_CATALOG=catalog, GOLD_MANIFEST=h2,
                                V4_SOURCE_GOLD=root, V4_VERIFICATION_REPORT=verify), \
                    patch.object(audit, "input_paths", side_effect=lambda release: frozen if release else live), \
                    patch.object(audit, "output_paths", return_value=(output, local)), \
                    patch.object(audit, "compare_gold_reference", return_value={"estado": "dentro_tolerancia"}) as compare:
                write_local_manifest("release", frozen)
                self.assertTrue(audit.verify_v4(release=True)["exito"])
                compare.return_value = {"estado": "difiere"}
                failure = audit.verify_v4(release=True)
                self.assertFalse(failure["exito"])
                self.assertEqual(failure["gold"]["estado_manifiesto_local"], "coincide")
                frozen.sala.write_bytes(b"changed Release")
                write_local_manifest("release", frozen)
                compare.return_value = {"estado": "dentro_tolerancia"}
                self.assertFalse(audit.verify_v4(release=True)["exito"])
                write_local_manifest("fuentes", live)
                self.assertTrue(audit.verify_v4()["exito"])
                self.assertFalse(audit.verify_v4(steps=[{"codigo": 1}])["exito"])
                live.sala.write_bytes(b"revised")
                self.assertFalse(audit.verify_v4()["exito"])
                write_local_manifest("fuentes", live)
                refreshed = audit.verify_v4(steps=[{"codigo": 0}])
                self.assertTrue(refreshed["exito"])
                self.assertFalse(refreshed["coinciden_insumos_verificados"])
                self.assertEqual(refreshed["diferencias_en_fuentes"], [relative(frozen.sala)])
                original_catalog = catalog.read_bytes()
                catalog.write_bytes(b"changed frozen catalog")
                write_local_manifest("fuentes", live)
                self.assertFalse(audit.verify_v4()["exito"])
                catalog.write_bytes(original_catalog)
                write_local_manifest("fuentes", live)
                live.enso.unlink()
                report = audit.verify_v4()
                observed = {item["insumo"]: item["estado"] for item in report["insumos"]}
                self.assertEqual(observed[relative(frozen.sala)], "difiere")
                self.assertEqual(observed[frozen.enso.name], "falta")
                self.assertEqual(observed[relative(h2)], "solo_referencia")
                self.assertEqual(report["gold"]["estado"], "difiere")
                self.assertFalse(report["exito"])
                self.assertEqual(live.sala.read_bytes(), b"revised")
                self.assertEqual(json.loads(verify.read_bytes()), report)

    def test_reference_distinguishes_rounding_from_changes(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            gold = root / "gold.csv"
            fixture = {"filas": 1, "atol": 1e-12, "sha256_columnas": {"macOS ARM64": {
                "ubigeo": reference.column_digest(["012345"]), "value": reference.column_digest(["1.0"]),
            }}}
            (root / "referencia.json").write_text(json.dumps(fixture), encoding="utf-8")
            with lzma.open(root / "flotantes.csv.xz", "wt", encoding="utf-8") as expected:
                expected.write("value\n1.0\n")
            with patch.object(reference, "V4_GOLD_REFERENCE", root):
                for row, state in (("012345,1.0", "coincide"), ("012345,1.0000000000000002", "dentro_tolerancia"),
                                   ("012345,1.000000000002", "difiere"), ("012345,nan", "difiere"),
                                   ("123456,1.0", "difiere")):
                    with self.subTest(row=row):
                        gold.write_text(f"ubigeo,value\n{row}\n", encoding="utf-8")
                        self.assertEqual(reference.compare_gold_reference(gold)["estado"], state)
