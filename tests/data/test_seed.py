"""seed.py tests against the Postgres test DB."""
import json
from pathlib import Path

import pytest

from app import db, queries
from data import seed, validate
from tests.data.helpers import feature, shifted_twin, valid_collection, write

TABLES = ("route", "stop", "route_stop")


@pytest.fixture
def seed_db(client, raw_db, monkeypatch):
    """Gives seed.main the pool slot (the API client keeps its own pool) and cleans route data."""
    # conftest sets a 1 s pool timeout; a cold first connection can exceed it and make seed.main return 1.
    monkeypatch.setenv("DB_POOL_TIMEOUT_S", "10")
    real = db._pool
    db._pool = None
    raw_db.execute("TRUNCATE route_stop, route, stop")
    yield raw_db
    db._pool = real
    raw_db.execute("TRUNCATE route_stop, route, stop")


def snapshot(conn):
    return {
        "route": conn.execute("SELECT * FROM route ORDER BY route_id").fetchall(),
        "stop": conn.execute("SELECT * FROM stop ORDER BY stop_id").fetchall(),
        "route_stop": conn.execute("SELECT * FROM route_stop ORDER BY route_id, seq").fetchall(),
    }


def count(conn, table):
    return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def test_seed_committed_file(seed_db, capsys):
    data = json.loads(validate.DEFAULT_PATH.read_text())
    assert seed.main([]) == 0
    entries = sum(len(f["properties"]["stops"]) for f in data["features"])
    distinct = {s["stop_id"] for f in data["features"] for s in f["properties"]["stops"]}
    assert count(seed_db, "route") == 9
    assert count(seed_db, "route_stop") == entries
    assert count(seed_db, "stop") == len(distinct) < entries
    assert "seeded 9 routes" in capsys.readouterr().out


def test_seed_values_unicode_and_seq(seed_db, tmp_path):
    c = valid_collection()
    f = feature(c, "yellow_out")
    f["properties"]["stops"][0]["name"] = "Sto. Rosario's Café"
    f["properties"]["verified_on"] = "2026-10-25"
    f["properties"]["stops"].append(dict(f["properties"]["stops"][0]))  # circular return pass
    assert seed.main([str(write(tmp_path, c))]) == 0
    row = seed_db.execute("SELECT name FROM stop WHERE stop_id = 'yellow_out_a'").fetchone()
    assert row[0] == "Sto. Rosario's Café"
    seqs = seed_db.execute(
        "SELECT seq, stop_id FROM route_stop WHERE route_id = 'yellow_out' ORDER BY seq"
    ).fetchall()
    assert seqs == [(1, "yellow_out_a"), (2, "yellow_out_b"), (3, "yellow_out_c"), (4, "yellow_out_a")]
    r = seed_db.execute("SELECT line, source, verified_on, osm_relation_id FROM route WHERE route_id='yellow_out'").fetchone()
    assert r[0] == f["geometry"]["coordinates"] and r[1] == "memory-traced"
    assert str(r[2]) == "2026-10-25" and r[3] is None


def test_rerun_is_idempotent(seed_db):
    assert seed.main([]) == 0
    first = snapshot(seed_db)
    assert seed.main([]) == 0
    assert snapshot(seed_db) == first


def test_shared_stop_first_in_sorted_route_order_wins(seed_db, tmp_path):
    c = valid_collection()
    shifted_twin(c, 55)  # blue_out reuses yellow_out_a, 55 m away
    yellow_stop = feature(c, "yellow_out")["properties"]["stops"][0]
    blue_stop = feature(c, "blue_out")["properties"]["stops"][0]
    blue_stop["name"] = "Blue Name"
    c["features"].sort(key=lambda f: f["properties"]["route_id"], reverse=True)  # file order opposite
    assert validate.check_collection(c)[0] == []
    assert seed.main([str(write(tmp_path, c))]) == 0
    row = seed_db.execute("SELECT name, lat, lng FROM stop WHERE stop_id = 'yellow_out_a'").fetchone()
    assert row == ("Blue Name", blue_stop["lat"], blue_stop["lng"])  # blue_out < yellow_out
    assert row[1] != yellow_stop["lat"]


def test_report_rows_survive_seed_and_reseed(seed_db):
    seed_db.execute("INSERT INTO report (route_color, message, lat, lng) VALUES ('red', 'broken sign', 15.1, 120.6)")
    before = seed_db.execute("SELECT * FROM report").fetchall()
    assert len(before) == 1
    assert seed.main([]) == 0
    assert seed.main([]) == 0
    assert seed_db.execute("SELECT * FROM report").fetchall() == before


def test_no_foreign_key_from_report(seed_db):
    n = seed_db.execute(
        "SELECT count(*) FROM information_schema.table_constraints "
        "WHERE table_name = 'report' AND constraint_type = 'FOREIGN KEY'"
    ).fetchone()[0]
    assert n == 0


def test_failure_mid_transaction_rolls_back_via_queries(seed_db):
    assert seed.main([]) == 0
    before = snapshot(seed_db)
    routes, stops, route_stops = seed.build_rows(json.loads(validate.DEFAULT_PATH.read_text())["features"])
    route_stops.append(("yellow_out", 9999, "no_such_stop"))  # FK violation after the DELETEs and inserts
    real = db._pool
    from app.config import load_settings

    s = load_settings()
    db.init_pool(s.database_url, s.db_pool_timeout_s)
    try:
        with pytest.raises(Exception):
            queries.replace_route_data(routes, stops, route_stops)
    finally:
        db.close_pool()
        db._pool = real
    assert snapshot(seed_db) == before


def test_seed_main_exit_code_and_old_data_kept_on_db_error(seed_db, monkeypatch, caplog):
    assert seed.main([]) == 0
    before = snapshot(seed_db)
    real_build = seed.build_rows

    def bad_build(features):
        routes, stops, route_stops = real_build(features)
        return routes, stops, route_stops + [("yellow_out", 9999, "no_such_stop")]

    monkeypatch.setattr(seed, "build_rows", bad_build)
    assert seed.main([]) == 1
    assert "rolled back" in caplog.text
    assert snapshot(seed_db) == before


def test_invalid_data_refuses_and_writes_nothing(seed_db, tmp_path):
    assert seed.main([]) == 0
    before = snapshot(seed_db)
    c = valid_collection()
    feature(c, "red_out")["properties"]["stops"].pop()
    feature(c, "red_out")["properties"]["stops"].pop()
    assert seed.main([str(write(tmp_path, c))]) == 1
    assert snapshot(seed_db) == before


@pytest.mark.parametrize("content", [None, "", "{bad"])
def test_missing_or_bad_file_leaves_db_untouched(seed_db, tmp_path, content):
    assert seed.main([]) == 0
    before = snapshot(seed_db)
    p = tmp_path / "x.geojson"
    if content is not None:
        p.write_text(content)
    assert seed.main([str(p)]) == 1
    assert snapshot(seed_db) == before


def test_database_unreachable_is_one_clean_exit(seed_db, monkeypatch, caplog):
    monkeypatch.setenv("DATABASE_URL", "postgresql://biyahe:biyahe@127.0.0.1:1/none")
    monkeypatch.setenv("DB_POOL_TIMEOUT_S", "1")
    assert seed.main([]) == 1
    assert "database unreachable" in caplog.text
    # The pool's own per-retry warnings are silenced so the failure reads as one line.
    assert not [r for r in caplog.records if r.name.startswith("psycopg.pool")]
    assert db._pool is None


def test_seed_applies_schema_to_empty_database(seed_db):
    # Schema is idempotent; seeding after dropping the route tables must recreate them.
    seed_db.execute("DROP TABLE route_stop, route, stop")
    assert seed.main([]) == 0
    assert count(seed_db, "route") == 9
