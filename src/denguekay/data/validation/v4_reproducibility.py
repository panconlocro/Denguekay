"""Compare V4 medallion or Release inputs with the frozen study and registry."""

from functools import cache
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from denguekay.config.paths import (
    GOLD_MANIFEST, ROOT, UBIGEO_CATALOG, V4_DATA_MANIFEST, V4_FROZEN, V4_GOLD, V4_GOLD_MANIFEST,
    V4_LIVE_GEOGRAPHY, V4_STUDY_MANIFEST, V4_VERIFICATION_REPORT,
)
from denguekay.data.ingestion.release_bundles import sha256_file
from denguekay.data.validation.integrated_expectations import coverage_path
from denguekay.features.gold_v4 import input_paths


def _relative(path):
    return path.relative_to(ROOT).as_posix()


def _compare(expected, actual):
    if actual is None:
        return "falta"
    return "coincide" if expected == actual else "difiere"


def _entries(release, study, registry, digest):
    archived = input_paths(release=True)
    selected = input_paths(release=release)
    entries = [
        (_relative(archived.panel), archived.panel, selected.panel),
        (_relative(archived.history), archived.history, selected.history),
        (_relative(archived.sala), archived.sala, selected.sala),
        (_relative(coverage_path(archived.panel)), coverage_path(archived.panel), coverage_path(selected.panel)),
        (_relative(archived.era5), archived.era5, selected.era5),
        (_relative(GOLD_MANIFEST), GOLD_MANIFEST, GOLD_MANIFEST if release else None),
        (_relative(UBIGEO_CATALOG), UBIGEO_CATALOG, UBIGEO_CATALOG),
        (archived.chirps.name, archived.chirps, selected.chirps),
        (archived.enso.name, archived.enso, selected.enso),
        ("geografia", archived.geography, selected.geography),
    ]
    if {name for name, _, _ in entries} != set(study):
        raise ValueError("V4 verification does not map every frozen study input")
    result = []
    for name, reference, actual in entries:
        expected = study[name]
        registered = registry.get(_relative(reference))
        observed = digest(actual) if actual is not None else None
        local_reference = digest(reference) if actual is None else None
        state = ("solo_archivo" if registered is None and reference == UBIGEO_CATALOG
                 else _compare(expected, registered))
        result.append({
            "insumo": name,
            "ruta": _relative(actual) if actual is not None else None,
            "ruta_release": _relative(reference),
            "sha256_estudio": expected,
            "sha256_registro": registered,
            "estado_manifiestos": state,
            "sha256_obtenido": observed,
            "estado": _compare(expected, observed) if actual is not None else "solo_referencia",
            **({"sha256_archivo_local": local_reference, "estado_archivo_local": _compare(expected, local_reference)}
               if actual is None else {}),
        })
    return result


def _check_gold(profile, inputs, digest, cutoff):
    actual = digest(V4_GOLD)
    if not V4_GOLD_MANIFEST.is_file() or actual is None:
        return {"estado": "falta", "ruta": _relative(V4_GOLD), "sha256_obtenido": actual}
    lineage = json.loads(V4_GOLD_MANIFEST.read_bytes())
    expected_inputs = {item["ruta"]: item["sha256_obtenido"] for item in inputs
                       if item["ruta"] and item["ruta"] != _relative(GOLD_MANIFEST)}
    valid = (lineage.get("fuentes") == expected_inputs and all(expected_inputs.values())
             and lineage.get("origen_insumos") == profile and lineage.get("corte_etiquetas") == cutoff
             and lineage.get("archivo") == V4_GOLD.name and lineage.get("sha256") == actual)
    return {"estado": "coincide" if valid else "difiere", "ruta": _relative(V4_GOLD),
            "sha256_obtenido": actual, "sha256_manifest_local": lineage.get("sha256"),
            "archivo_manifest_local": _relative(V4_GOLD_MANIFEST),
            "sha256_publicado": None}


def verify_v4(*, release=False, steps=None):
    """Verify canonical inputs; keep the new elevation and legacy h2 evidence separate."""
    study = json.loads(V4_STUDY_MANIFEST.read_bytes())
    registry = json.loads(V4_DATA_MANIFEST.read_bytes())
    registered = {member["ruta"]: member["sha256"] for bundle in registry["paquetes"] for member in bundle["archivos"]}
    digest = cache(lambda path: sha256_file(path) if path.is_file() else None)
    inputs = _entries(release, study["fuentes"], registered, digest)
    model = [
        {"archivo": file, "sha256_estudio": expected,
         "sha256_registro": registered.get(_relative(V4_FROZEN / file)),
         "estado": _compare(expected, registered.get(_relative(V4_FROZEN / file)))}
        for file, expected in study["archivos"].items()
    ]
    profile = "release" if release else "fuentes"
    gold = _check_gold(profile, inputs, digest, study["corte"])
    candidate_geo = digest(V4_LIVE_GEOGRAPHY)
    report = {
        "version": registry["version"], "perfil": profile, "referencia": registry["tag"],
        "manifiesto_estudio": _relative(V4_STUDY_MANIFEST), "manifiesto_release": _relative(V4_DATA_MANIFEST),
        "corte_etiquetas": study["corte"], "insumos": inputs, "archivos_modelo_en_manifiestos": model,
        "geografia_consulta_nueva": {"ruta": _relative(V4_LIVE_GEOGRAPHY), "sha256_obtenido": candidate_geo,
                                    "sha256_esperado": study["fuentes"]["geografia"],
                                    "estado": _compare(study["fuentes"]["geografia"], candidate_geo)},
        "gold": gold, "pasos_ejecutados": steps,
    }
    report["coinciden_insumos_verificados"] = all(item["estado"] in {"coincide", "solo_referencia"}
                                                 and item["estado_manifiestos"] in {"coincide", "solo_archivo"}
                                                 for item in inputs)
    report["exito"] = (report["coinciden_insumos_verificados"]
                       and all(item["estado"] == "coincide" for item in model) and gold["estado"] == "coincide"
                       and (steps is None or (bool(steps) and all(step["codigo"] == 0 for step in steps))))
    V4_VERIFICATION_REPORT.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=V4_VERIFICATION_REPORT.parent) as temp:
        output = Path(temp) / V4_VERIFICATION_REPORT.name
        output.write_bytes((json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        output.replace(V4_VERIFICATION_REPORT)
    return report


def print_result(report):
    for entry in report["insumos"]:
        print(f"{entry['insumo']}: {entry['estado']} (esperado {entry['sha256_estudio']}, "
              f"obtenido {entry['sha256_obtenido'] or entry.get('sha256_archivo_local') or '-'}, "
              f"manifiestos {entry['estado_manifiestos']})")
    print(f"Elevación de consulta nueva: {report['geografia_consulta_nueva']['estado']}")
    print(f"Gold V4 contra su manifiesto local: {report['gold']['estado']}")
    print(f"Informe: {_relative(V4_VERIFICATION_REPORT)}")
