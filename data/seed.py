"""Load routes.geojson into PostgreSQL (SPEC 9.3). Re-runnable; never touches report.

    python -m data.seed [path]     # default data/routes/routes.geojson
    docker compose run --rm api python -m data.seed

Validation runs first and a failure writes nothing. SQL lives in app/queries.py.
"""
import json
import logging
import sys
from pathlib import Path

import psycopg

from app import db, queries
from app.config import load_settings
from data import validate

log = logging.getLogger("biyahe.seed")


def build_rows(features):
    """Plain-data rows for queries.replace_route_data.

    A stop_id shared by routes gets one row: the first occurrence wins, with features
    in sorted route_id order and stops in list order (deterministic, file order is irrelevant).
    """
    ordered = sorted(features, key=lambda f: f["properties"]["route_id"])
    routes, stops, route_stops = [], {}, []
    for feat in ordered:
        p = feat["properties"]
        rid = p["route_id"]
        routes.append(
            (rid, p["color"], p["direction"], p["name"], json.dumps(feat["geometry"]["coordinates"]),
             p["source"], p["verified_on"], p["osm_relation_id"])
        )
        for seq, s in enumerate(p["stops"], start=1):
            stops.setdefault(s["stop_id"], (s["stop_id"], s["name"], s["lat"], s["lng"], s["osm_node_id"]))
            route_stops.append((rid, seq, s["stop_id"]))
    return routes, list(stops.values()), route_stops


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    path = Path(argv[0]) if argv else validate.DEFAULT_PATH
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    # The pool logs a multi-line warning per retry while the DB is down; our own line says it once.
    logging.getLogger("psycopg.pool").setLevel(logging.ERROR)

    try:
        data, errors, warnings, _stats = validate.check_file(path)
    except validate.FileProblem as exc:
        log.error("seed: refusing to run, %s", exc)
        return 1
    for w in warnings:
        log.warning("seed: %s", w)
    if errors:
        for e in errors:
            log.error("seed: validation: %s", e)
        log.error("seed: refusing to run, %d validation problem(s); database untouched", len(errors))
        return 1

    routes, stops, route_stops = build_rows(data["features"])
    settings = load_settings()
    try:
        db.init_pool(settings.database_url, settings.db_pool_timeout_s)
    except db.DatabaseUnavailable as exc:
        log.error("seed: database unreachable, nothing written (%s)", exc)
        return 1
    try:
        queries.apply_schema()
        queries.replace_route_data(routes, stops, route_stops)
    except db.DatabaseUnavailable as exc:
        log.error("seed: database unavailable, rolled back (%s)", exc)
        return 1
    except psycopg.Error as exc:
        log.error("seed: database error, rolled back, old data kept (%s)", exc)
        return 1
    finally:
        db.close_pool()
    print(f"seeded {len(routes)} routes, {len(stops)} stops, {len(route_stops)} route_stop rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
