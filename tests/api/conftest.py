import json

import pytest

from app import main

STOPS = [
    ("a", "Alpha Plaza", 15.150, 120.590),
    ("b", "Bravo Hall", 15.150, 120.600),
    ("c", "Charlie Gate", 15.150, 120.610),
    ("d", "Delta Market", 15.150, 120.620),
    ("x", "Xray Corner", 15.200, 120.650),
    ("y", "Yankee Cross", 15.200, 120.660),
    ("p", "Papa Loop", 15.100, 120.540),
    ("q", "Quebec Loop", 15.100, 120.550),
    ("z", "Zulu Lonely", 15.120, 120.560),
]
ROUTES = {
    "yellow_out": ("yellow", "out", "Yellow", ["a", "b", "c"]),
    "red_back": ("red", "back", "Red", ["c", "d"]),
    "blue_out": ("blue", "out", "Blue", ["x", "y"]),
    "purple_out": ("purple", "out", "Purple", ["p", "q", "p"]),
}


def insert_world(conn, extra_stops=()):
    for sid, name, lat, lng in [*STOPS, *extra_stops]:
        conn.execute("INSERT INTO stop (stop_id, name, lat, lng) VALUES (%s, %s, %s, %s)", (sid, name, lat, lng))
    by_id = {s[0]: s for s in STOPS}
    for rid, (color, direction, name, ids) in ROUTES.items():
        line = [[by_id[i][3], by_id[i][2]] for i in ids]
        conn.execute(
            "INSERT INTO route (route_id, color, direction, name, line, source) VALUES (%s, %s, %s, %s, %s::jsonb, 'test')",
            (rid, color, direction, name, json.dumps(line)),
        )
        for seq, sid in enumerate(ids, start=1):
            conn.execute("INSERT INTO route_stop (route_id, seq, stop_id) VALUES (%s, %s, %s)", (rid, seq, sid))


def _clear(conn):
    conn.execute("TRUNCATE route_stop, route, stop")


@pytest.fixture
def world(client, raw_db):
    _clear(raw_db)
    insert_world(raw_db)
    main.load_route_data(main.app)
    yield
    _clear(raw_db)
    main.load_route_data(main.app)


@pytest.fixture
def empty_world(client, raw_db):
    _clear(raw_db)
    main.load_route_data(main.app)
    yield
