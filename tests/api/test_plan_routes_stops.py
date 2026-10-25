import pytest

PLAN = "/api/plan"


def plan(client, f=(15.150, 120.590), t=(15.150, 120.600), **over):
    params = {"from_lat": f[0], "from_lng": f[1], "to_lat": t[0], "to_lng": t[1], **over}
    return client.get(PLAN, params={k: v for k, v in params.items() if v is not None})


def test_plan_one_jeep(client, world):
    r = plan(client)
    assert r.status_code == 200
    body = r.json()
    assert [s["type"] for s in body["steps"]] == ["walk", "ride", "walk"]
    assert body["steps"][1]["color"] == "yellow" and body["steps"][1]["stops_passed"] == 1
    assert set(body["steps"][0]) == {"type", "from", "to", "distance_m"}
    assert body["summary"] == "Walk to Alpha Plaza, ride Yellow to Bravo Hall, walk to your destination."


def test_plan_transfer(client, world):
    r = plan(client, t=(15.150, 120.620))
    assert r.status_code == 200
    steps = r.json()["steps"]
    assert [s["type"] for s in steps] == ["walk", "ride", "transfer", "ride", "walk"]
    assert steps[2] == {"type": "transfer", "from": "Charlie Gate", "to": "Charlie Gate", "walk_m": 0, "to_color": "red"}
    assert steps[3]["direction"] == "back"


@pytest.mark.parametrize("over", [
    {"from_lat": None}, {"to_lng": None}, {"from_lat": "abc"}, {"from_lng": ""}, {"to_lat": "nan"},
    {"to_lng": "inf"}, {"from_lat": "1e999"}, {"from_lat": 15.07}, {"from_lat": 15.23},
    {"to_lng": 120.49}, {"to_lng": 120.69},
])
def test_plan_invalid_location(client, world, over):
    r = plan(client, **over)
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_location"


def test_plan_swapped_lat_lng(client, world):
    r = plan(client, f=(120.590, 15.150))
    assert r.status_code == 400


def test_plan_bbox_edges_are_valid(client, world):
    r = plan(client, f=(15.08, 120.50), t=(15.22, 120.68))
    assert r.status_code == 404 and r.json()["error"] == "no_stop_nearby"


def test_no_stop_nearby_start_end_and_both(client, world):
    far = (15.09, 120.51)
    start = plan(client, f=far)
    end = plan(client, t=far)
    both = plan(client, f=far, t=far)
    for r in (start, end, both):
        assert r.status_code == 404 and r.json()["error"] == "no_stop_nearby"
    assert "starting point" in start.json()["message"]
    assert "destination" in end.json()["message"]
    assert "starting point" in both.json()["message"]


def test_no_route(client, world):
    r = plan(client, t=(15.200, 120.660))
    assert r.status_code == 404 and r.json()["error"] == "no_route"


def test_empty_route_data(client, empty_world):
    r = plan(client)
    assert r.status_code == 503
    assert set(r.json()) == {"error", "message"}
    assert r.json()["error"] == "route_data_unavailable"
    r = client.get("/api/routes")
    assert r.status_code == 200 and r.json() == []
    assert client.get("/api/routes/yellow_out").status_code == 404


def test_empty_route_data_invalid_location_wins(client, empty_world):
    r = plan(client, from_lat=15.5)
    assert r.status_code == 400 and r.json()["error"] == "invalid_location"


def test_empty_route_data_plan_with_db_down(client, empty_world, db_down):
    r = plan(client)
    assert r.status_code == 503 and r.json()["error"] == "route_data_unavailable"


def test_load_warns_only_when_empty(client, raw_db, caplog):
    from app import main
    from tests.api.conftest import _clear, insert_world
    _clear(raw_db)
    with caplog.at_level("INFO", logger="biyahe"):
        main.load_route_data(main.app)
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1 and warnings[0].name == "biyahe"
    text = warnings[0].getMessage()
    assert "no route data" in text and "seed" in text and "restart" in text
    caplog.clear()
    insert_world(raw_db)
    try:
        with caplog.at_level("INFO", logger="biyahe"):
            main.load_route_data(main.app)
        assert not [r for r in caplog.records if r.levelname == "WARNING"]
        assert "Loaded 4 routes" in caplog.text
    finally:
        _clear(raw_db)
        main.load_route_data(main.app)


def test_routes_list(client, world):
    r = client.get("/api/routes")
    assert r.status_code == 200
    assert r.json() == [
        {"route_id": "blue_out", "color": "blue", "direction": "out", "name": "Blue", "stop_count": 2},
        {"route_id": "purple_out", "color": "purple", "direction": "out", "name": "Purple", "stop_count": 3},
        {"route_id": "red_back", "color": "red", "direction": "back", "name": "Red", "stop_count": 2},
        {"route_id": "yellow_out", "color": "yellow", "direction": "out", "name": "Yellow", "stop_count": 3},
    ]


def test_route_detail(client, world):
    r = client.get("/api/routes/yellow_out")
    assert r.status_code == 200
    feats = r.json()["features"]
    assert r.json()["type"] == "FeatureCollection"
    assert feats[0]["geometry"]["type"] == "LineString"
    assert feats[0]["geometry"]["coordinates"][0] == [120.590, 15.150]
    assert [f["properties"] for f in feats[1:]] == [
        {"name": "Alpha Plaza", "seq": 1}, {"name": "Bravo Hall", "seq": 2}, {"name": "Charlie Gate", "seq": 3},
    ]
    assert feats[1]["geometry"] == {"type": "Point", "coordinates": [120.590, 15.150]}


def test_route_detail_repeated_stop(client, world):
    feats = client.get("/api/routes/purple_out").json()["features"]
    assert [(f["properties"]["name"], f["properties"]["seq"]) for f in feats[1:]] == [
        ("Papa Loop", 1), ("Quebec Loop", 2), ("Papa Loop", 3),
    ]


@pytest.mark.parametrize("rid", ["nope", "YELLOW_OUT", "x'%20OR%201=1--", "a%2Fb", "yellow_out;DROP"])
def test_route_not_found(client, world, rid):
    r = client.get(f"/api/routes/{rid}")
    assert r.status_code == 404
    assert r.json()["error"] == ("not_found" if "%2F" in rid else "route_not_found")


def test_route_unknown_code(client, world):
    assert client.get("/api/routes/nope").json()["error"] == "route_not_found"


def test_stops_partial_case_insensitive(client, world):
    r = client.get("/api/stops", params={"q": "  LOOP "})
    assert r.status_code == 200
    assert r.json() == [
        {"stop_id": "p", "name": "Papa Loop", "lat": 15.1, "lng": 120.54},
        {"stop_id": "q", "name": "Quebec Loop", "lat": 15.1, "lng": 120.55},
    ]


def test_stops_cap_and_order(client, raw_db):
    raw_db.execute("TRUNCATE route_stop, route, stop")
    extra = [(f"s{i:02d}", f"Stop {i:02d}", 15.15, 120.59) for i in range(12)]
    for sid, name, lat, lng in reversed(extra):
        raw_db.execute("INSERT INTO stop (stop_id, name, lat, lng) VALUES (%s, %s, %s, %s)", (sid, name, lat, lng))
    try:
        r = client.get("/api/stops", params={"q": "stop"})
        assert [s["name"] for s in r.json()] == [f"Stop {i:02d}" for i in range(10)]
    finally:
        raw_db.execute("TRUNCATE route_stop, route, stop")


def test_stops_no_match_and_special_chars(client, world, raw_db):
    assert client.get("/api/stops", params={"q": "zzzz"}).json() == []
    raw_db.execute("INSERT INTO stop (stop_id, name, lat, lng) VALUES ('pct', '50% Off_Stop', 15.15, 120.59)")
    for q in ["%", "_", "'", "\\", "\"; DROP TABLE stop;--", "é"]:
        assert client.get("/api/stops", params={"q": q}).status_code == 200
    assert [s["stop_id"] for s in client.get("/api/stops", params={"q": "%"}).json()] == ["pct"]
    assert [s["stop_id"] for s in client.get("/api/stops", params={"q": "_"}).json()] == ["pct"]
    assert client.get("/api/stops", params={"q": "a%a"}).json() == []


@pytest.mark.parametrize("params", [{}, {"q": ""}, {"q": "   "}, {"q": "x" * 101}, {"q": "a\x00b"}])
def test_stops_validation(client, world, params):
    r = client.get("/api/stops", params=params)
    assert r.status_code == 422 and r.json()["error"] == "validation_error"


def test_db_down_split(client, world, db_down):
    assert plan(client).status_code == 200
    assert client.get("/api/routes").status_code == 200
    assert client.get("/api/routes/yellow_out").status_code == 200
    r = client.get("/api/stops", params={"q": "loop"})
    assert r.status_code == 200 and [s["stop_id"] for s in r.json()] == ["p", "q"]
    r = client.get("/api/reports")
    assert r.status_code == 503 and r.json()["error"] == "database_unavailable"
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["database"] == "down"
