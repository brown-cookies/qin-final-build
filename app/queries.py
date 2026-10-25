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


def replace_route_data(routes: list, stops: list, route_stops: list) -> None:
    """Replace route, stop and route_stop in one transaction; never touches report.

    routes: (route_id, color, direction, name, line_json, source, verified_on, osm_relation_id)
    stops: (stop_id, name, lat, lng, osm_node_id); route_stops: (route_id, seq, stop_id).
    Any error rolls everything back (db.connection() commits only on success).
    """
    with db.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM route_stop")
            cur.execute("DELETE FROM route")
            cur.execute("DELETE FROM stop")
            cur.executemany(
                "INSERT INTO stop (stop_id, name, lat, lng, osm_node_id) VALUES (%s, %s, %s, %s, %s)",
                stops,
            )
            cur.executemany(
                "INSERT INTO route (route_id, color, direction, name, line, source, verified_on, osm_relation_id) "
                "VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s)",
                routes,
            )
            cur.executemany(
                "INSERT INTO route_stop (route_id, seq, stop_id) VALUES (%s, %s, %s)",
                route_stops,
            )


def load_route_data() -> tuple:
    """(routes, stops, route_stops) as dicts, read once at startup. route.line is [[lng, lat], ...]."""
    with db.connection() as conn:
        cur = conn.cursor(row_factory=dict_row)
        cur.execute("SELECT route_id, color, direction, name, line FROM route ORDER BY route_id")
        routes = cur.fetchall()
        cur.execute("SELECT stop_id, name, lat, lng FROM stop ORDER BY stop_id")
        stops = cur.fetchall()
        cur.execute("SELECT route_id, seq, stop_id FROM route_stop ORDER BY route_id, seq")
        route_stops = cur.fetchall()
    return routes, stops, route_stops


def search_stops(q: str, limit: int) -> list:
    """Literal, case-insensitive substring match; \\, % and _ in q are escaped."""
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    with db.connection() as conn:
        cur = conn.cursor(row_factory=dict_row)
        cur.execute(
            "SELECT stop_id, name, lat, lng FROM stop WHERE name ILIKE '%%' || %s || '%%' "
            'ORDER BY name COLLATE "C", stop_id COLLATE "C" LIMIT %s',
            (escaped, limit),
        )
        return cur.fetchall()


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
