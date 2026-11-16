"""Run the whole data pipeline from the public sources, in order (``python -m denguekay.pipelines.run_all``).

Each step is a notebook of ``pipelines/notebooks/`` executed in place with nbconvert, from the repository root, so the
order and the outputs are the same as running them by hand:

    01 districts · 02 Open-Meteo and ERA5-Land · 03 meteo silver · 03b Niño 1+2 · 03c CHIRPS (if present) · 04 socio
    (Drive) · 05 socio silver · 06 epi CSV (Drive) · 06b Sala Situacional · 07 epi silver · 08 and 09 merges · 10 gold

The downloads resume from their caches, so a run that stops (API limits, network) is resumed by running the
command again. Times: Open-Meteo and ERA5-Land are limited per hour and per day (ERA5-Land 2000 onwards takes about
4 to 5 days); CHIRPS by FTP about 10 h. ``--desde`` and ``--hasta`` run a contiguous part, ``--lista`` prints the
steps. Data regenerated from the sources may differ from the Releases (the sources revise their data); the exact
data of each model version is in its Release (docs/reproducibilidad.md).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

from denguekay.config.paths import ROOT

NOTEBOOKS = ROOT / "pipelines" / "notebooks"
STEPS = ["01_ingesta_distritos", "02_ingesta_meteo", "03_bronze_to_silver_meteo", "03b_ingesta_enso",
         "03c_ingesta_chirps", "04_ingesta_socio", "05_bronze_to_silver_socio", "06_ingesta_epi", "06b_ingesta_sala",
         "07_bronze_to_silver_epi", "08_silver_merge_meteo_socio", "09_silver_merge_epi", "10_silver_to_gold"]
V4_STEPS = ["01b_geografia_v4", "02b_ingesta_meteo_v4", "03d_silver_clima_v4", "04_ingesta_socio",
            "05b_socio_v4", "06_ingesta_epi", "06c_sala_confirmados_v4", "07b_historico_confirmados_v4",
            "08b_meteo_socio_v4", "09b_integrado_confirmados_v4", "11_silver_to_gold_v4"]
V4_DOWNLOAD_STEPS = {"02b_ingesta_meteo_v4", "04_ingesta_socio", "06_ingesta_epi"}


def available_steps(first: str | None = None, last: str | None = None, *, version: str = "v3") -> list[str]:
    """The steps between ``first`` and ``last`` (by prefix, e.g. ``03`` or ``06b``) whose notebook exists."""
    ordered = V4_STEPS if version == "v4" else STEPS

    def index(prefix, default):
        if prefix is None:
            return default
        hits = [i for i, s in enumerate(ordered) if s.split("_")[0] == prefix or s == prefix]
        if not hits:
            raise ValueError(f"Paso desconocido: {prefix}")
        return hits[0]

    chosen = ordered[index(first, 0): index(last, len(ordered) - 1) + 1]
    if version == "v4":
        missing = [step for step in chosen if not (NOTEBOOKS / f"{step}.ipynb").is_file()]
        if missing:
            raise FileNotFoundError(f"Faltan notebooks requeridos de V4: {', '.join(missing)}")
    return [s for s in chosen if (NOTEBOOKS / f"{s}.ipynb").exists()]


def run(steps: list[str], timeout: int = -1, *, version: str = "v3", offline: bool = False) -> list[dict]:
    results = []
    for step in steps:
        start = time.perf_counter()
        command = [sys.executable, "-m", "jupyter", "nbconvert", "--to", "notebook", "--execute",
                   "--stdout" if version == "v4" else "--inplace",
                   f"--ExecutePreprocessor.timeout={timeout}", str(NOTEBOOKS / f"{step}.ipynb")]
        print(f"→ {step}", flush=True)
        if version == "v4":
            env = dict(os.environ, DENGUEKAY_V4_OFFLINE="1" if offline else "0")
            done = subprocess.run(command, cwd=ROOT, env=env, stdout=subprocess.DEVNULL)
        else:
            done = subprocess.run(command, cwd=ROOT)
        results.append({"paso": step, "codigo": done.returncode, "segundos": round(time.perf_counter() - start, 1)})
        if done.returncode != 0:
            print(f"✗ {step} falló; corrija y vuelva a correr desde --desde {step.split('_')[0]}", flush=True)
            break
    return results


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--desde", help="primer paso (prefijo, p. ej. 03 o 06b)")
    parser.add_argument("--hasta", help="último paso (prefijo)")
    parser.add_argument("--lista", action="store_true", help="solo muestra los pasos")
    parser.add_argument("--version", choices=("v3", "v4"), default="v3")
    parser.add_argument("--sin-descargas", action="store_true", help="V4: usa el bronze disponible")
    parser.add_argument("--bronze-publicado", action="store_true", help="V4: restaura el bronze climático publicado")
    checks = parser.add_mutually_exclusive_group()
    checks.add_argument("--verificar", action="store_true", help="V4: coteja los SHA-256 después de ejecutar")
    checks.add_argument("--solo-verificar", action="store_true", help="V4: coteja los archivos locales sin descargarlos")
    parser.add_argument("--desde-release", action="store_true", help="con --solo-verificar, coteja los insumos del Release")
    args = parser.parse_args(argv)
    v4_options = (args.sin_descargas, args.bronze_publicado, args.verificar, args.solo_verificar, args.desde_release)
    if args.version != "v4" and any(v4_options):
        parser.error("Las opciones de fuentes y verificación requieren --version v4")
    if args.bronze_publicado and (args.sin_descargas or args.solo_verificar):
        parser.error("--bronze-publicado requiere una ejecución con descargas")
    if args.desde_release and not args.solo_verificar:
        parser.error("--desde-release requiere --solo-verificar")
    if args.solo_verificar:
        if args.desde or args.hasta or args.lista or args.sin_descargas:
            parser.error("--solo-verificar no ejecuta notebooks ni selecciona pasos")
        return _verify(release=args.desde_release)
    steps = available_steps(args.desde, args.hasta, version=args.version)
    if args.sin_descargas:
        steps = [step for step in steps if step not in V4_DOWNLOAD_STEPS]
    missing = [] if args.version == "v4" else [s for s in STEPS if not (NOTEBOOKS / f"{s}.ipynb").exists()]
    if args.lista:
        print("\n".join(steps + [f"(no está en esta rama: {s})" for s in missing]))
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
