"""Write and execute the study notebooks (``python notebook_tools.py run <notebook>``)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import nbformat

NOTEBOOKS = Path(__file__).resolve().parents[1] / "notebooks"
KERNEL = "denguekay-09"  # .venv/bin/python -m ipykernel install --sys-prefix --name denguekay-09

SETUP = '''import os
import sys
from pathlib import Path

os.environ.update({"DENGUEKAY_XGB_DEVICE": "cpu", "DENGUEKAY_XGB_NJOBS": "2", "OMP_NUM_THREADS": "2",
                   "OPENBLAS_NUM_THREADS": "1", "VECLIB_MAXIMUM_THREADS": "1", "MLFLOW_DISABLE_AGENT_HINT": "1"})
STUDY = Path.cwd().parent
sys.path.insert(0, str(STUDY / "code"))

import numpy as np
import pandas as pd

import common as c

pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 40)
pd.set_option("display.max_colwidth", 60)'''


def write(name: str, cells: list[tuple[str, str]]) -> Path:
    notebook = nbformat.v4.new_notebook()
    notebook.metadata["kernelspec"] = {"name": KERNEL, "display_name": "Denguekay (.venv)", "language": "python"}
    for kind, text in cells:
        cell = nbformat.v4.new_markdown_cell(text) if kind == "md" else nbformat.v4.new_code_cell(text)
        notebook.cells.append(cell)
    NOTEBOOKS.mkdir(parents=True, exist_ok=True)
    path = NOTEBOOKS / name
    nbformat.write(notebook, path)
    return path


def run(path: Path) -> None:
    subprocess.run([sys.executable, "-m", "nbconvert", "--to", "notebook", "--execute", "--inplace",
                    "--ExecutePreprocessor.timeout=-1", f"--ExecutePreprocessor.kernel_name={KERNEL}", str(path)],
                   check=True)


if __name__ == "__main__":
    if sys.argv[1] == "run":
        run(NOTEBOOKS / sys.argv[2])
