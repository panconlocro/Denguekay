"""Compare the V4 files of ``data/`` with the frozen study and with datos_v4.zip of the Release."""

from functools import cache
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import zipfile

import numpy as np
import pandas as pd

from denguekay.config.paths import (
    GOLD_MANIFEST, ROOT, UBIGEO_CATALOG, V4_DATA_MANIFEST, V4_FROZEN,
    V4_LIVE_GEOGRAPHY, V4_STUDY_MANIFEST, V4_VERIFICATION_REPORT,
)
from denguekay.data.ingestion import release_bundles
from denguekay.data.ingestion.release_bundles import sha256_file
from denguekay.data.validation.integrated_expectations import coverage_path
from denguekay.data.validation.v4_gold_reference import compare_gold_reference
from denguekay.features.gold_v4 import input_paths, output_paths


ATOL = 1e-12   # floating-point tolerance for ERA5-Land and the panel (the sources recompute them)
MAX_LISTED_ROWS = 500
SALA_NAME, TOLERANT = "epi_sala_semanal.csv", ("meteo_humedad_era5_land_2000_2026.csv", "meteo_socio_epi_piura_2017_2025.csv")


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
        (_relative(GOLD_MANIFEST), GOLD_MANIFEST, GOLD_MANIFEST),
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
            "regenerado": not release and actual is not None and actual not in (UBIGEO_CATALOG, archived.geography),
            "sha256_estudio": expected,
            "sha256_registro": registered,
            "estado_manifiestos": state,
            "sha256_obtenido": observed,
            "estado": _compare(expected, observed) if actual is not None else "solo_referencia",
            **({"sha256_archivo_local": local_reference, "estado_archivo_local": _compare(expected, local_reference)}
               if actual is None else {}),
        })
    return result


def _frames(name, release_bytes, local_path):
    dtype = {"ubigeo": "string"}
    kwargs = {"dtype": dtype, "float_precision": "round_trip"}
    return (pd.read_csv(io.BytesIO(release_bytes), **kwargs), pd.read_csv(local_path, **kwargs))


def describe_difference(name, release_bytes, local_path):
    """Say how a regenerated file differs from the Release: Sala rows with another count, or the largest numeric gap."""
    frozen, local = _frames(name, release_bytes, local_path)
    if name.endswith(SALA_NAME):
        key = ["ubigeo", "anio", "semana"]
        both = frozen.merge(local, on=key, how="outer", suffixes=("_release", "_local"), indicator=True,
                            validate="one_to_one")
        changed = both.loc[both._merge.ne("both") | both.casos_Dengue_release.ne(both.casos_Dengue_local)]
        rows = changed.assign(_merge=changed._merge.astype(str)).head(MAX_LISTED_ROWS)
        return {"filas_distintas": len(changed), "filas_listadas": json.loads(rows.to_json(orient="records"))}
    if list(frozen.columns) != list(local.columns) or len(frozen) != len(local):
        return {"misma_estructura": False}
    numeric = frozen.select_dtypes("number").columns
    others = [column for column in frozen.columns if column not in numeric]
    gaps = {column: float(np.nanmax(np.abs(frozen[column].to_numpy(float) - local[column].to_numpy(float))))
            for column in numeric if len(frozen)}
    same_text = bool(frozen[others].equals(local[others]))
    same_nulls = all((frozen[column].isna() == local[column].isna()).all() for column in numeric)
    return {"misma_estructura": True, "texto_igual": same_text, "nulos_iguales": same_nulls,
            "diferencia_max_por_columna": gaps,
            "diferencia_max": max(gaps.values(), default=0.0)}


def compare_with_release(inputs, registry, release_zip=None):
    """Compare each regenerated file that differs with the same file of ``datos_v4.zip`` (downloaded if not given).

    A file of ERA5-Land or the panel whose only differences are floating-point noise below ``ATOL`` becomes
    ``dentro_tolerancia``. Returns the notes of the comparison; the entries of ``inputs`` are updated in place."""
    pending = [item for item in inputs if item["regenerado"] and item["estado"] == "difiere" and item["ruta"]]
    if not pending:
        return {"estado": "sin_diferencias"}
    bundle = next((entry for entry in registry["paquetes"] if entry.get("nombre") == "datos_v4.zip"), None)
    try:
        with TemporaryDirectory() as temp:
            zip_path = Path(release_zip) if release_zip else None
            if zip_path is None:
                if bundle is None:
                    raise ValueError("datos_v4.zip no está en el manifiesto del Release")
                zip_path = release_bundles.download(
                    release_bundles.release_url(registry["repositorio"], registry["tag"], bundle["nombre"]),
                    Path(temp) / bundle["nombre"])
                release_bundles.verify_bundle(zip_path, bundle)
            with zipfile.ZipFile(zip_path) as archive:
                for item in pending:
                    if item["ruta_release"] not in archive.namelist() or not item["ruta"].endswith(".csv"):
                        continue
                    detail = describe_difference(item["ruta"], archive.read(item["ruta_release"]), ROOT / item["ruta"])
                    item["diferencia"] = detail
                    if (item["ruta"].endswith(TOLERANT) and detail.get("misma_estructura") and detail["texto_igual"]
                            and detail["nulos_iguales"] and detail["diferencia_max"] <= ATOL):
                        item["estado"] = "dentro_tolerancia"
        return {"estado": "comparado"}
    except Exception as error:  # no network, or a damaged download: the verdict stays with the hashes
        return {"estado": "no_disponible", "motivo": f"{type(error).__name__}: {error}"}


def _check_gold(profile, inputs, digest, cutoff):
    gold, manifest = output_paths(profile == "release")
    actual = digest(gold)
    if not manifest.is_file() or actual is None:
        return {"estado": "falta", "ruta": _relative(gold), "sha256_obtenido": actual}
    lineage = json.loads(manifest.read_bytes())
    expected_inputs = {item["ruta"]: item["sha256_obtenido"] for item in inputs
                       if item["ruta"] and item["ruta"] != _relative(GOLD_MANIFEST)}
    valid = (lineage.get("fuentes") == expected_inputs and all(expected_inputs.values())
             and lineage.get("origen_insumos") == profile and lineage.get("corte_etiquetas") == cutoff
             and lineage.get("archivo") == gold.name and lineage.get("sha256") == actual)
    reference = compare_gold_reference(gold) if profile == "release" else None
    reference_status = reference["estado"] if reference else "coincide"
    return {"estado": reference_status if valid else "difiere", "ruta": _relative(gold),
            "sha256_obtenido": actual, "sha256_manifest_local": lineage.get("sha256"),
            "archivo_manifest_local": _relative(manifest),
            "estado_manifiesto_local": "coincide" if valid else "difiere", "referencia_independiente": reference}


def verify_v4(*, release=False, steps=None, release_zip=None):
    """Verify canonical inputs; keep the new elevation and legacy h2 evidence separate."""
    study = json.loads(V4_STUDY_MANIFEST.read_bytes())
    registry = json.loads(V4_DATA_MANIFEST.read_bytes())
    registered = {member["ruta"]: member["sha256"] for bundle in registry["paquetes"] for member in bundle["archivos"]}
    digest = cache(lambda path: sha256_file(path) if path.is_file() else None)
    inputs = _entries(release, study["fuentes"], registered, digest)
    comparison = compare_with_release(inputs, registry, release_zip)
    model = [
        {"archivo": file, "sha256_estudio": expected,
         "sha256_registro": registered.get(_relative(V4_FROZEN / file)),
         "estado": _compare(expected, registered.get(_relative(V4_FROZEN / file)))}
        for file, expected in study["archivos"].items()
    ]
    profile = "release" if release else "fuentes"
    gold = _check_gold(profile, inputs, digest, study["corte"])
    candidate_geo = digest(V4_LIVE_GEOGRAPHY)
    destination = V4_VERIFICATION_REPORT
    report = {
        "version": registry["version"], "perfil": profile, "referencia": registry["tag"],
        "ruta_informe": _relative(destination),
        "manifiesto_estudio": _relative(V4_STUDY_MANIFEST), "manifiesto_release": _relative(V4_DATA_MANIFEST),
        "corte_etiquetas": study["corte"], "insumos": inputs, "archivos_modelo_en_manifiestos": model,
        "geografia_consulta_nueva": {"ruta": _relative(V4_LIVE_GEOGRAPHY), "sha256_obtenido": candidate_geo,
                                    "sha256_esperado": study["fuentes"]["geografia"],
                                    "estado": _compare(study["fuentes"]["geografia"], candidate_geo)},
        "gold": gold, "pasos_ejecutados": steps, "cotejo_con_release": comparison,
    }
    registry_matches = all(item["estado_manifiestos"] in {"coincide", "solo_archivo"} for item in inputs)
    matched = {"coincide", "solo_referencia"}
    report["coinciden_insumos_verificados"] = registry_matches and all(item["estado"] in matched for item in inputs)
    drift = [item["insumo"] for item in inputs if item["regenerado"] and item["estado"] == "difiere"]
    report["diferencias_en_fuentes"] = drift
    report["dentro_tolerancia"] = [item["insumo"] for item in inputs if item["estado"] == "dentro_tolerancia"]
    inputs_valid = all(item["estado"] in matched | {"dentro_tolerancia"} or item["insumo"] in drift for item in inputs)
    report["exito"] = (registry_matches and inputs_valid and all(item["estado"] == "coincide" for item in model)
                       and gold["estado"] in {"coincide", "dentro_tolerancia"}
                       and (steps is None or (bool(steps) and all(step["codigo"] == 0 for step in steps))))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=destination.parent) as temp:
        output = Path(temp) / destination.name
        output.write_bytes((json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        output.replace(destination)
    return report


def print_result(report):
    for entry in report["insumos"]:
        print(f"{entry['insumo']}: {entry['estado']} (esperado {entry['sha256_estudio']}, "
              f"obtenido {entry['sha256_obtenido'] or entry.get('sha256_archivo_local') or '-'}, "
              f"manifiestos {entry['estado_manifiestos']})")
    for entry in report["insumos"]:
        detail = entry.get("diferencia")
        if not detail:
            continue
        if "filas_distintas" in detail:
            print(f"  {entry['insumo']}: {detail['filas_distintas']} filas con conteo distinto del Release")
        elif detail.get("misma_estructura"):
            print(f"  {entry['insumo']}: diferencia máxima {detail['diferencia_max']:.3g} ({entry['estado']})")
    comparison = report.get("cotejo_con_release", {})
    if comparison.get("estado") == "no_disponible":
        print(f"No se pudo cotejar con datos_v4.zip: {comparison['motivo']}")
    print(f"Elevación de consulta nueva: {report['geografia_consulta_nueva']['estado']}")
    gold = report["gold"]
    print(f"Gold V4 contra su manifiesto local: {gold.get('estado_manifiesto_local', gold['estado'])}")
    if reference := gold.get("referencia_independiente"):
        print(f"Gold V4 contra la referencia independiente: {reference['estado']}")
        if "motivo" in reference:
            print(reference["motivo"])
        else:
            for name, result in reference["columnas"].items():
                if result["estado"] != "coincide":
                    print(f"  {name}: {result['estado']} (dif. máx. {result.get('diferencia_max_abs', '-')})")
    if report["exito"] and report["diferencias_en_fuentes"]:
        print("Verificación completada con diferencias en los insumos regenerados.")
    print(f"Informe: {report['ruta_informe']}")
