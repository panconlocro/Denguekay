"""Serve the real API against isolated test fixtures, never the user's database.

Run from the repository root: .venv/bin/python apps/web/e2e/serve_api.py.
Requires the project's full test dependencies. Port 18000 is for verification only.
"""

import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests"), str(ROOT)]
os.environ["DATABASE_URL"] = ""
os.environ["DENGUEKAY_XGB_DEVICE"] = "cpu"
os.environ["DENGUEKAY_XGB_NJOBS"] = "2"

from api.test_api import TestAPIReal  # noqa: E402
from apps.api.main import create_app  # noqa: E402
from denguekay.db.session import make_engine  # noqa: E402
from sqlalchemy.engine import URL  # noqa: E402
import uvicorn  # noqa: E402

if __name__ == "__main__":
    TestAPIReal.setUpClass()
    engine = make_engine(URL.create("sqlite", database=str(TestAPIReal.plantilla)))
    try:
        # Read-only browser: no usable write key, and no inference endpoint is invoked.
        app = create_app(engine, TestAPIReal.cfg, api_key="", storage=TestAPIReal.storage)
        uvicorn.run(app, host="127.0.0.1", port=18000, log_level="warning")
    finally:
        engine.dispose()
        TestAPIReal.tearDownClass()
