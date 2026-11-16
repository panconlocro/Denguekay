"""Report local Release files against their published checksums without writing to disk."""

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
