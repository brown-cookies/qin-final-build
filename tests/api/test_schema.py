from pathlib import Path

import psycopg

from app import queries


def test_schema_applies_twice_and_creates_tables(client, raw_db):
    queries.apply_schema()
    queries.apply_schema()
    rows = raw_db.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
    ).fetchall()
    assert {"route", "stop", "route_stop", "report"} <= {r[0] for r in rows}


def test_schema_apply_keeps_report_rows(client, raw_db):
    raw_db.execute("INSERT INTO report (route_color, message) VALUES ('red', 'keep me')")
    queries.apply_schema()
    assert raw_db.execute("SELECT count(*) FROM report").fetchone()[0] == 1


def test_report_defaults_and_index(client, raw_db):
    row = raw_db.execute(
        "INSERT INTO report (route_color, message) VALUES ('red', 'x') "
        "RETURNING report_id, status, created_at"
    ).fetchone()
    assert row[0] is not None and row[1] == "new" and row[2] is not None
    idx = raw_db.execute("SELECT indexdef FROM pg_indexes WHERE tablename = 'report'").fetchall()
    assert any("created_at DESC" in i[0] for i in idx)


def test_sql_only_in_queries_and_schema():
    root = Path(__file__).resolve().parents[2]
    forbidden = ("SELECT ", "INSERT ", "UPDATE ", "DELETE ", "CREATE TABLE")
    for path in [root / "app" / "main.py", *(root / "app" / "api").glob("*.py")]:
        text = path.read_text()
        for word in forbidden:
            assert word not in text, f"{word!r} in {path}"
