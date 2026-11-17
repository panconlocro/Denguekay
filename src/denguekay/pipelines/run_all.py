"""Run the data pipeline of one model version from the public sources (``python -m denguekay.pipelines.run_all``).

The steps of a version are the notebooks of ``pipelines/notebooks/<VERSION>/`` (``V0`` ... ``V4``), executed in the order
of their numeric prefix with nbconvert, from the repository root. Nothing is executed in place: the executed notebook
and its log of each step go to ``pipelines/ejecuciones/<version>/<date>/`` (ignored by Git), so the versioned
notebooks stay clean. If a step fails, its failing cell and error are printed.

The downloads resume from their caches, so a run that stops (API limits, network) is resumed by running the
command again. Times: Open-Meteo and ERA5-Land are limited per hour and per day (ERA5-Land 2000 onwards takes about
4 to 5 days); CHIRPS by FTP about 10 h. ``--desde`` and ``--hasta`` run a contiguous part, ``--lista`` prints the
steps. Data regenerated from the sources may differ from the Releases (the sources revise their data); the exact
data of each model version is in its Release (docs/reproducibilidad.md).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from denguekay.config.paths import ROOT

NOTEBOOKS = ROOT / "pipelines" / "notebooks"
EXECUTIONS = ROOT / "pipelines" / "ejecuciones"
VERSIONS = ("v0", "v1", "v2", "v3", "v4")
V4_DOWNLOAD_STEPS = {"02_bronze_clima", "03_bronze_socio", "04_bronze_casos"}
# v0 to v3 capture the Sala with the case-count step itself, so it is a download too.
DOWNLOAD_STEPS = {"v4": V4_DOWNLOAD_STEPS}
OLDER_DOWNLOAD_STEPS = V4_DOWNLOAD_STEPS | {"05_bronze_sala"}


def data_dir_for(version: str) -> str | None:
    """The silver and gold of v0 to v3 are written apart (``DENGUEKAY_DATA_DIR``); V4 owns ``data/``."""
    return None if version == "v4" else f"data_anteriores/{version}"
_STEP = re.compile(r"^(\d{2})_.+\.ipynb$")


def version_folder(version: str) -> Path:
    return NOTEBOOKS / version.upper()


def all_steps(version: str) -> list[str]:
    """Every step of ``version`` (notebook names without extension) in order; raises if the version has no folder."""
    folder = version_folder(version)
    if not folder.is_dir():
        raise FileNotFoundError(f"La versión {version} no tiene carpeta de notebooks ({folder.relative_to(ROOT)})")
    return sorted(path.stem for path in folder.iterdir() if _STEP.match(path.name))


def available_steps(first: str | None = None, last: str | None = None, *, version: str = "v4") -> list[str]:
    """The steps between ``first`` and ``last`` (by prefix, e.g. ``03``) of ``version``."""
    ordered = all_steps(version)

    def index(prefix, default):
        if prefix is None:
            return default
        hits = [i for i, step in enumerate(ordered) if step.split("_")[0] == prefix or step == prefix]
        if not hits:
            raise ValueError(f"Paso desconocido: {prefix}")
        return hits[0]

    return ordered[index(first, 0): index(last, len(ordered) - 1) + 1]


def _report_failure(executed: Path, log: str) -> None:
    """Print the failing cell and the error of an executed notebook (the log tail if it was not written)."""
    try:
        notebook = json.loads(executed.read_text(encoding="utf-8"))
        for number, cell in enumerate(notebook["cells"], 1):
            for output in cell.get("outputs", []):
                if output.get("output_type") == "error":
                    print(f"  celda {number}:\n" + "".join(cell["source"])[:1500], flush=True)
                    print(f"  {output['ename']}: {output['evalue']}", flush=True)
                    return
    except (OSError, ValueError, KeyError):
        pass
    print("  " + "\n  ".join(log.strip().splitlines()[-15:]), flush=True)


def run(steps: list[str], timeout: int = -1, *, version: str = "v4", offline: bool = False,
        destination: Path | None = None) -> list[dict]:
    destination = destination or EXECUTIONS / version / time.strftime("%Y%m%d_%H%M%S")
    destination.mkdir(parents=True, exist_ok=True)
    results = []
    for step in steps:
        start = time.perf_counter()
        source = version_folder(version) / f"{step}.ipynb"
        command = [sys.executable, "-m", "jupyter", "nbconvert", "--to", "notebook", "--execute",
                   "--output-dir", str(destination), "--output", f"{step}.ipynb",
                   f"--ExecutePreprocessor.timeout={timeout}", str(source)]
        print(f"-> {step}", flush=True)
        env = dict(os.environ, DENGUEKAY_V4_OFFLINE="1" if offline else "0")
        env.pop("DENGUEKAY_DATA_DIR", None)
        if data_dir_for(version):
            env["DENGUEKAY_DATA_DIR"] = data_dir_for(version)
        done = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8",
                              errors="replace")
        log = (done.stdout or "") + (done.stderr or "")
        (destination / f"{step}.log").write_text(log, encoding="utf-8")
        results.append({"paso": step, "codigo": done.returncode, "segundos": round(time.perf_counter() - start, 1)})
        if done.returncode != 0:
            _report_failure(destination / f"{step}.ipynb", log)
            print(f"x {step} falló (registro en {destination.relative_to(ROOT)}); corrija y vuelva a correr desde "
                  f"--desde {step.split('_')[0]}", flush=True)
            break
    return results


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--desde", help="primer paso (prefijo, p. ej. 03 o 06b)")
    parser.add_argument("--hasta", help="último paso (prefijo)")
    parser.add_argument("--lista", action="store_true", help="solo muestra los pasos")
    parser.add_argument("--version", choices=VERSIONS, default="v4")
    parser.add_argument("--sin-descargas", action="store_true", help="usa el bronze disponible")
    parser.add_argument("--bronze-publicado", action="store_true", help="restaura el bronze climático publicado")
    checks = parser.add_mutually_exclusive_group()
    checks.add_argument("--verificar", action="store_true", help="V4: coteja los SHA-256 después de ejecutar")
    checks.add_argument("--solo-verificar", action="store_true", help="V4: coteja los archivos locales sin descargarlos")
    parser.add_argument("--desde-release", action="store_true", help="con --solo-verificar, coteja los insumos del Release")
    args = parser.parse_args(argv)
    v4_options = (args.verificar, args.solo_verificar, args.desde_release)
    if args.version != "v4" and any(v4_options):
        parser.error("--verificar, --solo-verificar y --desde-release requieren --version v4; "
                     "las versiones anteriores se verifican con su notebook 99_verificacion")
    if args.bronze_publicado and (args.sin_descargas or args.solo_verificar):
        parser.error("--bronze-publicado requiere una ejecución con descargas")
    if args.desde_release and not args.solo_verificar:
        parser.error("--desde-release requiere --solo-verificar")
    if args.solo_verificar:
        if args.desde or args.hasta or args.lista or args.sin_descargas:
            parser.error("--solo-verificar no ejecuta notebooks ni selecciona pasos")
        return _verify(release=args.desde_release)
    try:
        steps = available_steps(args.desde, args.hasta, version=args.version)
    except FileNotFoundError as error:
        print(error, file=sys.stderr)
        return 2
    if args.sin_descargas:
        skipped = DOWNLOAD_STEPS.get(args.version, OLDER_DOWNLOAD_STEPS)
        steps = [step for step in steps if step not in skipped]
    if args.lista:
        print("\n".join(steps))
        return 0
    if args.bronze_publicado:
        from denguekay.pipelines.v4_inputs import restore_published_bronze

        restore_published_bronze()
    results = run(steps, version=args.version, offline=args.sin_descargas)
    for r in results:
        print(f"{r['paso']}: {'ok' if r['codigo'] == 0 else 'falló'} ({r['segundos']} s)")
    status = 0 if all(r["codigo"] == 0 for r in results) and len(results) == len(steps) else 1
    if args.verificar:
        return max(status, _verify(steps=results))
    return status


def _verify(**options):
    from denguekay.data.validation.v4_reproducibility import print_result, verify_v4

    report = verify_v4(**options)
    print_result(report)
    return 0 if report["exito"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
