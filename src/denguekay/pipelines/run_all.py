"""Run the whole data pipeline from the public sources, in order (``python -m denguekay.pipelines.run_all``).

Each step is a notebook of ``pipelines/notebooks/`` executed in place with nbconvert, from the repository root, so the
order and the outputs are the same as running them by hand:

    01 districts · 02 Open-Meteo and ERA5-Land · 03 meteo silver · 03b Niño 1+2 · 03c CHIRPS (if present) · 04 socio
    (Drive) · 05 socio silver · 06 epi Excel (Drive) · 06b Sala Situacional · 07 epi silver · 08 and 09 merges · 10 gold

The downloads resume from their caches, so a run that stops (API limits, network) is resumed by running the
command again. Times: Open-Meteo and ERA5-Land are limited per hour and per day (ERA5-Land 2000 onwards takes about
4 to 5 days); CHIRPS by FTP about 10 h. ``--desde`` and ``--hasta`` run a contiguous part, ``--lista`` prints the
steps. Data regenerated from the sources may differ from the Releases (the sources revise their data); the exact
data of each model version is in its Release (docs/reproducibilidad.md).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time

from denguekay.config.paths import ROOT

NOTEBOOKS = ROOT / "pipelines" / "notebooks"
STEPS = ["01_ingesta_distritos", "02_ingesta_meteo", "03_bronze_to_silver_meteo", "03b_ingesta_enso",
         "03c_ingesta_chirps", "04_ingesta_socio", "05_bronze_to_silver_socio", "06_ingesta_epi", "06b_ingesta_sala",
         "07_bronze_to_silver_epi", "08_silver_merge_meteo_socio", "09_silver_merge_epi", "10_silver_to_gold"]


def available_steps(first: str | None = None, last: str | None = None) -> list[str]:
    """The steps between ``first`` and ``last`` (by prefix, e.g. ``03`` or ``06b``) whose notebook exists."""
    def index(prefix, default):
        if prefix is None:
            return default
        hits = [i for i, s in enumerate(STEPS) if s.split("_")[0] == prefix or s == prefix]
        if not hits:
            raise ValueError(f"Paso desconocido: {prefix}")
        return hits[0]

    chosen = STEPS[index(first, 0): index(last, len(STEPS) - 1) + 1]
    return [s for s in chosen if (NOTEBOOKS / f"{s}.ipynb").exists()]


def run(steps: list[str], timeout: int = -1) -> list[dict]:
    results = []
    for step in steps:
        start = time.perf_counter()
        command = [sys.executable, "-m", "jupyter", "nbconvert", "--to", "notebook", "--execute", "--inplace",
                   f"--ExecutePreprocessor.timeout={timeout}", str(NOTEBOOKS / f"{step}.ipynb")]
        print(f"→ {step}", flush=True)
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
    args = parser.parse_args(argv)
    steps = available_steps(args.desde, args.hasta)
    missing = [s for s in STEPS if not (NOTEBOOKS / f"{s}.ipynb").exists()]
    if args.lista:
        print("\n".join(steps + [f"(no está en esta rama: {s})" for s in missing]))
        return 0
    results = run(steps)
    for r in results:
        print(f"{r['paso']}: {'ok' if r['codigo'] == 0 else 'falló'} ({r['segundos']} s)")
    return 0 if all(r["codigo"] == 0 for r in results) and len(results) == len(steps) else 1


if __name__ == "__main__":
    raise SystemExit(main())
