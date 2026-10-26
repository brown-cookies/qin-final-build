from app.main import app


def assert_shape(r, status, code):
    assert r.status_code == status
    body = r.json()
    assert set(body) == {"error", "message"}
    assert body["error"] == code


def test_unknown_path_404(client):
    assert_shape(client.get("/nope"), 404, "not_found")


def test_wrong_method_405(client):
    assert_shape(client.delete("/api/reports"), 405, "method_not_allowed")
    assert_shape(client.post("/health"), 405, "method_not_allowed")


def test_unhandled_exception_500_does_not_leak(client, caplog):
    secret = "secret-internal-detail-42"

    @app.get("/_boom")
    def boom():
        raise RuntimeError(secret)

    # The "/" static mount is a catch-all, so a route added now must go ahead of it.
    app.router.routes.insert(0, app.router.routes.pop())
    try:
        r = client.get("/_boom")
    finally:
        app.router.routes[:] = [x for x in app.router.routes if getattr(x, "path", "") != "/_boom"]
    assert_shape(r, 500, "internal_error")
    assert secret not in r.text and "Traceback" not in r.text
    assert secret in caplog.text
