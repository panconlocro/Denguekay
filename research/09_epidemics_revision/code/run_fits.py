"""Fit arms of study 09 on the 20 blocks and five seeds (cached): ``python run_fits.py ARM [ARM ...]``.

The model fits take minutes, so they run here rather than inside the notebooks, which only read the cached
predictions. Before fitting, the parity check of study 08 confirms that this path reproduces the archived
fitting function on two blocks.
"""

import argparse
import json
import time

import common as c


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("arms", nargs="+")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--sin-paridad", action="store_true", help="skip the parity check (already passed)")
    args = parser.parse_args()
    start = time.time()
    inputs, _ = c.load_inputs(validate=False)
    origins, arms, hp, schedules = c.prepare(inputs)
    unknown = [a for a in args.arms if a not in arms]
    if unknown:
        raise SystemExit(f"Unknown arms: {unknown}. Available: {sorted(arms)}")
    if not args.sin_paridad:
        c.spatial.parity(inputs, origins, arms["historia_geo"], hp)
        print("Parity with the archived fitting path verified (blocks 2008 and 2025, seed 17).", flush=True)
    c.OUTPUT.mkdir(parents=True, exist_ok=True)
    schedules.to_csv(c.OUTPUT / "placebos_donantes.csv", index=False)
    (c.OUTPUT / "brazos_columnas.json").write_text(json.dumps(arms, indent=1), encoding="utf-8")
    c.fit_arms(inputs, origins, arms, hp, args.arms, workers=args.workers)
    print(f"Done in {(time.time() - start) / 60:.1f} min", flush=True)


if __name__ == "__main__":
    main()
