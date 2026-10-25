"""The 10 test trips (SPEC Section 11) run through the planner on the real routes.geojson.

Builds the graph from the committed snapshot, so it needs neither the seeded DB nor the app.
Expected colors are the maintainer's, in riding order; a trip with two acceptable answers lists both.
Cost tuning is not done here: this records raw results (docs/DECISIONS.md).
"""
import json
from pathlib import Path

import pytest

from app.config import load_settings
from app.planner import search, steps
from app.planner.graph import Graph, Stop
from data import seed, validate


@pytest.fixture(autouse=True)
def clean_reports():
    """Overrides the root autouse fixture; these tests never connect to Postgres."""
    yield


def known_gap(why):
    # strict: when tuning or a data fix makes the trip pass, the XPASS fails and the mark must go.
    return pytest.mark.xfail(strict=True, reason=why)


# (from stop name, to stop name, acceptable ride-color sequences)
TRIPS = [
    ("Yellow Terminal", "HAU Main Gate", [("yellow",)]),
    ("Yellow Terminal", "Angeles University Foundation (AUF)", [("yellow", "purple")]),
    ("Yellow Terminal", "McDonalds Near Intersection Friendship", [("yellow", "grey", "red")]),
    ("HAU Main Gate", "SM Clark End", [("purple",)]),
    ("Dark Yellow Terminal", "Red Terminal", [("darkyellow",)]),
    ("Yellow Terminal", "Marquee Mall", [("yellow", "blue")]),
    ("SM Clark End", "Yellow Terminal", [("grey", "yellow"), ("purple", "yellow")]),
    pytest.param(
        "Starbucks Near AUF", "Blue End Terminal", [("purple", "blue")],
        marks=known_gap(
            "Purple meets Blue at seq 75-76, before Starbucks Near AUF (seq 80); "
            "the graph has no wrap-around edge from the end of a circular route to its start"
        ),
    ),
    ("Jenra Mall", "System Plus College", [("purple",), ("grey",)]),
    ("Marquee Mall", "SM Clark End", [("blue", "purple"), ("blue", "grey")]),
]


@pytest.fixture(scope="module")
def world():
    data = json.loads(Path(validate.DEFAULT_PATH).read_text(encoding="utf-8"))
    routes_rows, stop_rows, route_stop_rows = seed.build_rows(data["features"])
    stops = {sid: Stop(sid, name, lat, lng) for sid, name, lat, lng, _osm in stop_rows}
    routes = {
        rid: {"route_id": rid, "color": color, "direction": direction, "name": name, "stops": []}
        for rid, color, direction, name, *_ in routes_rows
    }
    for rid, _seq, sid in route_stop_rows:  # already ordered by route_id, seq
        routes[rid]["stops"].append(sid)
    s = load_settings()
    graph = Graph(stops, routes, s.walk_radius_m, s.transfer_radius_m, s.transfer_penalty_km, s.walk_cost_factor)
    return graph, {st.name: st for st in stops.values()}, s.walk_radius_m


def ride_colors(world, from_name, to_name):
    graph, by_name, radius = world
    a, b = by_name[from_name], by_name[to_name]
    near_a = graph.stops_within(a.lat, a.lng, radius)
    near_b = graph.stops_within(b.lat, b.lng, radius)
    path = search.find_path(graph, near_a, near_b)
    assert path is not None, "no path"
    result = steps.build_steps(graph, path, (a.lat, a.lng), (b.lat, b.lng))
    return tuple(st["color"] for st in result if st["type"] == "ride")


@pytest.mark.parametrize("from_name,to_name,accepted", TRIPS, ids=[f"{i}" for i in range(1, 11)])
def test_trip(world, from_name, to_name, accepted):
    got = ride_colors(world, from_name, to_name)
    assert got in accepted, f"{from_name} -> {to_name}: got {got}, expected one of {accepted}"
