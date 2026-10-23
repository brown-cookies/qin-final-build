import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run_app(env_overrides):
    env = {**os.environ, "PYTHONPATH": str(ROOT), **env_overrides}
    return subprocess.run(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", "0"],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=60,
    )


def test_bad_database_url_exits_nonzero_with_clear_line():
    r = _run_app({"DATABASE_URL": "postgresql://biyahe:biyahe@127.0.0.1:1/none", "DB_POOL_TIMEOUT_S": "1"})
    assert r.returncode != 0
    assert "Database unreachable at startup" in r.stderr + r.stdout


def test_invalid_bbox_exits_nonzero():
    r = _run_app({"SERVICE_BBOX": "9,1,2,3"})
    assert r.returncode != 0
    assert "Invalid configuration" in r.stderr + r.stdout
