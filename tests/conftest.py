import os

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.conninfo import conninfo_to_dict, make_conninfo

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://biyahe:biyahe@127.0.0.1:5432/biyahe_test"
)
_dbname = conninfo_to_dict(TEST_DATABASE_URL).get("dbname", "")
if not _dbname.endswith("_test"):
    raise RuntimeError(
        f"TEST_DATABASE_URL must name a database ending in _test, got {_dbname!r}")

# Must be set before app modules read settings.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("DB_POOL_TIMEOUT_S", "1")

from app import db, main  # noqa: E402


def _ensure_test_database() -> None:
    admin = make_conninfo(TEST_DATABASE_URL, dbname="postgres")
    with psycopg.connect(admin, autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (_dbname,)).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{_dbname}"')


@pytest.fixture(scope="session")
def client():
    _ensure_test_database()
    # Server errors become 500 responses instead of re-raising in the test.
    with TestClient(main.app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture(autouse=True)
def clean_reports(client):
    with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as conn:
        conn.execute("TRUNCATE report")
    yield


@pytest.fixture
def raw_db():
    with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as conn:
        yield conn


@pytest.fixture
def db_down(client):
    """Swap the live pool for one aimed at a dead port; restores it afterwards."""
    real = db._pool
    dead = db.make_pool("postgresql://biyahe:biyahe@127.0.0.1:1/none", 0.5)
    db._pool = dead
    yield
    db._pool = real
    dead.close(timeout=0)
