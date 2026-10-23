def test_health_up(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "database": "up"}


def test_health_down_then_recovers(client, db_down):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "database": "down"}


def test_health_back_up_after_recovery(client):
    assert client.get("/health").json()["database"] == "up"


def test_openapi_lists_endpoints(client):
    assert client.get("/docs").status_code == 200
    paths = client.get("/openapi.json").json()["paths"]
    assert "/health" in paths
    assert set(paths["/api/reports"]) == {"get", "post"}
