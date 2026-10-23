from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

VALID = {"route_color": "yellow", "message": "Jeep skips this corner", "lat": 15.16, "lng": 120.59}
FIELDS = {"report_id", "route_color", "message", "lat", "lng", "status", "created_at"}


def count(raw_db):
    return raw_db.execute("SELECT count(*) FROM report").fetchone()[0]


def assert_error(r, status, code):
    assert r.status_code == status
    body = r.json()
    assert set(body) == {"error", "message"}
    assert body["error"] == code
    assert isinstance(body["message"], str) and body["message"]


# --- POST success ---

def test_create_report(client, raw_db):
    r = client.post("/api/reports", json=VALID)
    assert r.status_code == 201
    body = r.json()
    assert set(body) == FIELDS
    UUID(body["report_id"])
    datetime.fromisoformat(body["created_at"])
    assert body["status"] == "new"
    assert (body["route_color"], body["message"], body["lat"], body["lng"]) == (
        "yellow", VALID["message"], 15.16, 120.59)
    row = raw_db.execute("SELECT report_id::text, route_color, message, lat, lng, status FROM report").fetchall()
    assert len(row) == 1
    assert row[0] == (body["report_id"], "yellow", VALID["message"], 15.16, 120.59, "new")


def test_create_without_coordinates_gives_nulls(client):
    r = client.post("/api/reports", json={"route_color": "other", "message": "x"})
    assert r.status_code == 201
    assert r.json()["lat"] is None and r.json()["lng"] is None


def test_explicit_null_pair_is_absent(client):
    r = client.post("/api/reports", json={"route_color": "red", "message": "x", "lat": None, "lng": None})
    assert r.status_code == 201


@pytest.mark.parametrize("n", [1, 500])
def test_message_length_edges_accepted(client, n):
    assert client.post("/api/reports", json={"route_color": "red", "message": "a" * n}).status_code == 201


def test_multibyte_and_sql_metacharacters_roundtrip(client):
    msg = "Kuya, 'bayad' po; DROP TABLE report; -- \U0001F699 ñ"
    r = client.post("/api/reports", json={"route_color": "blue", "message": msg})
    assert r.status_code == 201 and r.json()["message"] == msg
    assert client.get("/api/reports").json()[0]["message"] == msg


def test_message_stripped(client):
    r = client.post("/api/reports", json={"route_color": "blue", "message": "  hi  "})
    assert r.json()["message"] == "hi"


@pytest.mark.parametrize("lat,lng", [(15.08, 120.50), (15.22, 120.68), (15.08, 120.68), (15.22, 120.50)])
def test_bbox_edges_accepted(client, lat, lng):
    r = client.post("/api/reports", json={**VALID, "lat": lat, "lng": lng})
    assert r.status_code == 201


# --- POST validation ---

BAD_BODIES = {
    "empty message": {"route_color": "red", "message": ""},
    "whitespace message": {"route_color": "red", "message": "   "},
    "501 chars": {"route_color": "red", "message": "a" * 501},
    "nul char": {"route_color": "red", "message": "a\u0000b"},
    "pink": {"route_color": "pink", "message": "x"},
    "uppercase": {"route_color": "YELLOW", "message": "x"},
    "lat only": {"route_color": "red", "message": "x", "lat": 15.16},
    "lng only": {"route_color": "red", "message": "x", "lng": 120.59},
    "lat with null lng": {"route_color": "red", "message": "x", "lat": 15.16, "lng": None},
    "lat below": {**VALID, "lat": 15.0799},
    "lat above": {**VALID, "lat": 15.2201},
    "lng below": {**VALID, "lng": 120.4999},
    "lng above": {**VALID, "lng": 120.6801},
    "swapped": {**VALID, "lat": 120.59, "lng": 15.16},
    "zeros": {**VALID, "lat": 0, "lng": 0},
    "non-numeric lat": {**VALID, "lat": "abc"},
    "non-numeric lng": {**VALID, "lng": "abc"},
    "missing message": {"route_color": "red"},
    "missing color": {"message": "x"},
    "extra field": {**VALID, "extra": 1},
}


@pytest.mark.parametrize("body", BAD_BODIES.values(), ids=BAD_BODIES.keys())
def test_invalid_bodies_422(client, raw_db, body):
    assert_error(client.post("/api/reports", json=body), 422, "validation_error")
    assert count(raw_db) == 0


@pytest.mark.parametrize("content", ["not json", "{", ""])
def test_malformed_body_422(client, raw_db, content):
    r = client.post("/api/reports", content=content, headers={"Content-Type": "application/json"})
    assert_error(r, 422, "validation_error")
    assert count(raw_db) == 0


# --- GET ---

def seed(raw_db, n):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(n):
        raw_db.execute(
            "INSERT INTO report (route_color, message, created_at) VALUES ('red', %s, %s)",
            (f"m{i}", base + timedelta(minutes=i)),
        )


def test_list_empty(client):
    r = client.get("/api/reports")
    assert r.status_code == 200 and r.json() == []


def test_list_newest_first_default_limit(client, raw_db):
    seed(raw_db, 12)
    r = client.get("/api/reports")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 10
    assert [b["message"] for b in body] == [f"m{i}" for i in range(11, 1, -1)]
    assert set(body[0]) == FIELDS


def test_list_limit_50_returns_all_up_to_50(client, raw_db):
    seed(raw_db, 12)
    assert len(client.get("/api/reports?limit=50").json()) == 12
    assert len(client.get("/api/reports?limit=1").json()) == 1


def test_post_then_get_lists_it_first(client):
    client.post("/api/reports", json={"route_color": "red", "message": "first"})
    created = client.post("/api/reports", json={"route_color": "red", "message": "second"}).json()
    assert client.get("/api/reports").json()[0]["report_id"] == created["report_id"]


@pytest.mark.parametrize("limit", ["0", "51", "-1", "abc", ""])
def test_limit_out_of_range_422(client, limit):
    assert_error(client.get(f"/api/reports?limit={limit}"), 422, "validation_error")


# --- DB down ---

def test_post_503_when_db_down(client, db_down):
    assert_error(client.post("/api/reports", json=VALID), 503, "database_unavailable")


def test_get_503_when_db_down(client, db_down):
    assert_error(client.get("/api/reports"), 503, "database_unavailable")


def test_malformed_request_still_422_when_db_down(client, db_down):
    assert_error(client.post("/api/reports", json={"route_color": "pink", "message": "x"}), 422, "validation_error")
    assert_error(client.get("/api/reports?limit=0"), 422, "validation_error")


def test_recovers_after_db_down(client):
    assert client.get("/api/reports").status_code == 200
