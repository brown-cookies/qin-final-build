def test_health_up(client, world):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "database": "up", "route_data": "loaded"}


def test_health_up_empty(client, empty_world):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "database": "up", "route_data": "empty"}


def test_health_down_then_recovers(client, world, db_down):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "database": "down", "route_data": "loaded"}


def test_health_down_empty(client, empty_world, db_down):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "database": "down", "route_data": "empty"}


def test_health_back_up_after_recovery(client):
    assert client.get("/health").json()["database"] == "up"


def test_openapi_lists_endpoints(client):
    assert client.get("/docs").status_code == 200
    paths = client.get("/openapi.json").json()["paths"]
    assert "/health" in paths
    assert set(paths["/api/reports"]) == {"get", "post"}
