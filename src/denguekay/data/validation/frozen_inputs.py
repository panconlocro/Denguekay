"""Report local Release files against their published checksums without writing to disk.

``verify_frozen_inputs`` checks every file of the manifests under a checkout. ``verify_version`` is the check of a
pipeline run of one version (notebook ``99_verificacion`` of ``pipelines/notebooks/V0`` to ``V3``): the silver and gold
files of its data folder against the manifest of its Release, saying for each one whether it matches, is within
floating-point tolerance, or differs because the sources republished.
"""

import argparse
from functools import cache
import json
from pathlib import Path

from denguekay.config.paths import ROOT
from denguekay.data.ingestion.release_bundles import load_manifest, manifest_path, sha256_file

VERSIONS = ("v0", "v1", "v2", "v3", "v4")


def verify_frozen_inputs(root, versions):
    digest = cache(lambda path: sha256_file(path) if path.is_file() else None)
    report = {}
    for version in versions:
        manifest = load_manifest(manifest_path(version))
        checks = []
        for bundle in manifest["paquetes"]:
            for entry in bundle["archivos"]:
                path, expected = entry["ruta"], entry["sha256"]
                observed = digest(root / path)
                status = "falta" if observed is None else ("coincide" if observed == expected else "difiere")
                checks.append({"paquete": bundle["nombre"], "ruta": path, "estado": status,
                               "sha256_esperado": expected, "sha256_obtenido": observed})
        report[version] = checks
    return report


PACKAGE_FOLDERS = (("data", "silver"), ("data", "gold"))


def _local_path(data_dir, member):
    parts = Path(member).parts
    return Path(data_dir).joinpath(*parts[1:]) if parts[:2] in PACKAGE_FOLDERS else None


def verify_version(version, *, data_dir=None, release_zip=None):
    """Compare the silver and gold files of ``version`` in ``data_dir`` with the manifest of its Release.

    The data folder is the one ``DENGUEKAY_DATA_DIR`` selects by default (``data_anteriores/<version>``). A file that
    differs is compared with the same file of the Release zip (downloaded to a temporary folder unless
    ``release_zip`` is given): Sala rows with another count, weeks that changed version, or the largest numeric gap.
    ERA5-Land and the integrated panel within 1e-12 are ``dentro_tolerancia``. Nothing is written to ``data_dir``.
    """
    from denguekay.config.paths import DATA_DIR
    from denguekay.data.validation import v4_reproducibility as audit

    data_dir = Path(data_dir) if data_dir is not None else DATA_DIR
    manifest = load_manifest(manifest_path(version))
    digest = cache(lambda path: sha256_file(path) if path.is_file() else None)
    items = []
    for bundle in manifest["paquetes"]:
        for entry in bundle["archivos"]:
            local = _local_path(data_dir, entry["ruta"])
            if local is None:
                continue
            observed = digest(local)
            state = "falta" if observed is None else ("coincide" if observed == entry["sha256"] else "difiere")
            items.append({"paquete": bundle["nombre"], "ruta": entry["ruta"], "ruta_local": str(local),
                          "regenerado": True, "estado": state, "ruta_release": entry["ruta"],
                          "sha256_esperado": entry["sha256"], "sha256_obtenido": observed})
    if not items:
        raise ValueError(f"El manifiesto de {version} no lista archivos de data/silver ni data/gold")
    comparison = _compare_differences(items, manifest, release_zip, audit)
    differing = [item["ruta"] for item in items if item["estado"] == "difiere"]
    return {"version": version, "carpeta_datos": str(data_dir), "archivos": items, "cotejo_con_release": comparison,
            "faltan": [item["ruta"] for item in items if item["estado"] == "falta"],
            "diferencias_en_fuentes": differing,
            "dentro_tolerancia": [item["ruta"] for item in items if item["estado"] == "dentro_tolerancia"],
            "exito": not any(item["estado"] == "falta" for item in items)}


def _compare_differences(items, manifest, release_zip, audit):
    pending = [item for item in items if item["estado"] == "difiere"]
    if not pending:
        return {"estado": "sin_diferencias"}
    import tempfile
    import zipfile

    from denguekay.data.ingestion import release_bundles

    try:
        with tempfile.TemporaryDirectory() as temp:
            archives = {}
            for item in pending:
                bundle = next(entry for entry in manifest["paquetes"] if entry["nombre"] == item["paquete"])
                if bundle["nombre"] not in archives:
                    zip_path = Path(release_zip) if release_zip else release_bundles.download(
                        release_bundles.release_url(manifest["repositorio"], manifest["tag"], bundle["nombre"]),
                        Path(temp) / bundle["nombre"])
                    if not release_zip:
                        release_bundles.verify_bundle(zip_path, bundle)
                    archives[bundle["nombre"]] = zipfile.ZipFile(zip_path)
                archive = archives[bundle["nombre"]]
                if item["ruta"].endswith(".csv"):
                    detail = audit.describe_difference(item["ruta"], archive.read(item["ruta"]),
                                                       Path(item["ruta_local"]))
                    item["diferencia"] = detail
                    if (item["ruta"].endswith(audit.TOLERANT) and detail.get("misma_estructura")
                            and detail["texto_igual"] and detail["nulos_iguales"]
                            and detail["diferencia_max"] <= audit.ATOL):
                        item["estado"] = "dentro_tolerancia"
            for archive in archives.values():
                archive.close()
        return {"estado": "comparado"}
    except Exception as error:  # no network or a damaged download: the verdict stays with the hashes
        return {"estado": "no_disponible", "motivo": f"{type(error).__name__}: {error}"}


def print_version_report(report):
    print(f"{report['version']}: archivos de silver y gold de {report['carpeta_datos']}")
    for item in report["archivos"]:
        print(f"  {item['ruta']}: {item['estado']}")
        detail = item.get("diferencia")
        if not detail:
            continue
        if "filas_distintas" in detail:
            print(f"    {detail['filas_distintas']} filas con conteo distinto del Release")
        elif detail.get("misma_estructura"):
            print(f"    diferencia máxima {detail['diferencia_max']:.3g}")
            if "cambios_de_version" in detail:
                first, last, count = detail["semanas_cambiadas"]
                print(f"    {detail['filas_cambiadas']} filas en {count} semanas ({first} a {last}); "
                      f"la fuente republicó: {detail['cambios_de_version']}")
        elif detail.get("misma_estructura") is False:
            print("    distinta forma (filas o columnas) que la del Release")
    comparison = report["cotejo_con_release"]
    if comparison.get("estado") == "no_disponible":
        print(f"No se pudo cotejar con el zip del Release: {comparison['motivo']}")
    print("Faltan:", report["faltan"] or "ninguno", "| difieren:", report["diferencias_en_fuentes"] or "ninguno",
          "| dentro de tolerancia:", report["dentro_tolerancia"] or "ninguno")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raiz", type=Path, default=ROOT, help="checkout donde se extrajo el Release")
    parser.add_argument("--version", choices=VERSIONS, action="append", help="versión a comprobar; se puede repetir")
    args = parser.parse_args(argv)
    report = verify_frozen_inputs(args.raiz, args.version or VERSIONS)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(any(entry["estado"] != "coincide" for checks in report.values() for entry in checks))


if __name__ == "__main__":
    raise SystemExit(main())
