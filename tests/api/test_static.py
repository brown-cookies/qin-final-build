def test_root_serves_placeholder_page(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert 'id="map"' in r.text


def test_health_still_json(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_docs_still_served(client):
    assert client.get("/docs").status_code == 200


def test_api_routes_not_shadowed(client):
    r = client.get("/api/routes")
    assert r.status_code in (200, 503)
    assert r.headers["content-type"].startswith("application/json")


def test_unknown_path_uses_error_shape(client):
    r = client.get("/nope")
    assert r.status_code == 404
    body = r.json()
    assert body["error"] == "not_found"
    assert isinstance(body["message"], str)
