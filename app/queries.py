"""All hand-written SQL lives here (plus sql/schema.sql). Values go in as %s parameters only."""
from pathlib import Path
from typing import Optional

from psycopg.rows import dict_row

from app import db

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "sql" / "schema.sql"


def apply_schema() -> None:
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with db.connection() as conn:
        conn.execute(sql)


def ping() -> None:
    with db.connection() as conn:
        conn.execute("SELECT 1")


def insert_report(
    route_color: str, message: str, lat: Optional[float], lng: Optional[float]
) -> dict:
    with db.connection() as conn:
        cur = conn.cursor(row_factory=dict_row)
        cur.execute(
            "INSERT INTO report (route_color, message, lat, lng) "
            "VALUES (%s, %s, %s, %s) "
            "RETURNING report_id, route_color, message, lat, lng, status, created_at",
            (route_color, message, lat, lng),
        )
        return cur.fetchone()


def list_reports(limit: int) -> list:
    with db.connection() as conn:
        cur = conn.cursor(row_factory=dict_row)
        # report_id breaks created_at ties so the order is stable.
        cur.execute(
            "SELECT report_id, route_color, message, lat, lng, status, created_at "
            "FROM report ORDER BY created_at DESC, report_id DESC LIMIT %s",
            (limit,),
        )
        return cur.fetchall()
