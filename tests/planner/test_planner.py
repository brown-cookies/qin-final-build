"""Planner unit tests on hand-made graphs; no Postgres, no env setup."""
import pytest

from app.planner.graph import Graph, Stop, at, haversine_m, on
from app.planner.search import find_path
from app.planner.steps import build_steps, build_summary

WALK_R, XFER_R, PENALTY, FACTOR = 500, 100, 1.0, 2.0
M_LAT = 111194.9  # metres per degree of latitude (sphere)
LNG = 111194.9 * 0.9654  # approx metres per degree of longitude at 15.15 N


def pt(x_m, y_m):
    return (15.15 + y_m / M_LAT, 120.59 + x_m / LNG)


def mk(stops, routes, penalty=PENALTY, circular=()):
    sm = {sid: Stop(sid, name, *pt(*xy)) for sid, (name, xy) in stops.items()}
    rm = {rid: {"color": rid.rsplit("_", 1)[0], "direction": rid.rsplit("_", 1)[1], "stops": ids,
                "circular": rid in circular}
          for rid, ids in routes.items()}
    return Graph(sm, rm, WALK_R, XFER_R, penalty, FACTOR)


def trip(g, start, end):
    near_s, near_e = g.stops_within(*start, WALK_R), g.stops_within(*end, WALK_R)
    path = find_path(g, near_s, near_e)
    return path, (build_steps(g, path, start, end) if path else None)


@pytest.fixture
def g():
    stops = {
        "a": ("Alpha", (0, 0)), "b": ("Bravo", (1000, 0)), "c": ("Charlie", (2000, 0)),
        "d": ("Delta", (3000, 0)), "e": ("Echo", (4000, 0)),
        "far1": ("Far One", (0, 20000)), "far2": ("Far Two", (1000, 20000)),
    }
    routes = {
        "yellow_out": ["a", "b", "c"],
        "darkyellow_out": ["c", "d", "e"],
        "blue_out": ["far1", "far2"],
    }
    return mk(stops, routes)


def test_edge_kinds_and_costs(g):
    adj = {n: {(m, k): c for m, c, k in es} for n, es in g.adj.items()}
    assert adj[at("a")][(on("yellow_out", 0), "board")] == PENALTY
    ab = haversine_m(*pt(0, 0), *pt(1000, 0)) / 1000
    assert adj[on("yellow_out", 0)][(on("yellow_out", 1), "ride")] == pytest.approx(ab)
    assert adj[on("yellow_out", 1)][(at("b"), "alight")] == 0
    # shared stop_id c has one at-node with boarding edges to both routes
    boards = {m for (m, k) in adj[at("c")] if k == "board"}
    assert boards == {on("yellow_out", 2), on("darkyellow_out", 0)}
    assert not any(k == "walk" for (_, k) in adj[at("a")])


def test_walk_edge_within_transfer_radius():
    g2 = mk({"a": ("A", (0, 0)), "b": ("B", (80, 0)), "c": ("C", (250, 0))}, {"yellow_out": ["a", "c"]})
    walks = {n: [(m, c) for m, c, k in es if k == "walk"] for n, es in g2.adj.items() if n[0] == "at"}
    d = haversine_m(*pt(0, 0), *pt(80, 0)) / 1000
    assert walks[at("a")] == [(at("b"), pytest.approx(d * FACTOR))]
    assert walks[at("b")] == [(at("a"), pytest.approx(d * FACTOR))]
    assert walks[at("c")] == []


def test_stops_within_boundary(g):
    lat, lng = pt(0, 0)
    d = haversine_m(lat, lng, *pt(1000, 0))
    assert "b" in [s for s, _ in g.stops_within(lat, lng, d)]
    assert "b" not in [s for s, _ in g.stops_within(lat, lng, d - 0.001)]


def test_queries_do_not_affect_each_other(g):
    before = {n: list(es) for n, es in g.adj.items()}
    p1, s1 = trip(g, pt(0, 0), pt(2000, 0))
    p2, s2 = trip(g, pt(1000, 0), pt(2000, 0))
    assert g.adj == before
    assert s2[1]["from"] == "Bravo" and s2[1]["stops_passed"] == 1
    assert s1[1]["from"] == "Alpha" and s1[1]["stops_passed"] == 2


def test_one_jeep_steps_and_summary(g):
    _, steps = trip(g, pt(0, 0), pt(1000, 0))
    dist = round(haversine_m(*pt(0, 0), *pt(1000, 0)))
    assert steps == [
        {"type": "walk", "from": "Your start point", "to": "Alpha", "distance_m": 0},
        {"type": "ride", "color": "yellow", "direction": "out", "from": "Alpha", "to": "Bravo",
         "stops_passed": 1, "distance_m": dist},
        {"type": "walk", "from": "Bravo", "to": "Your destination", "distance_m": 0},
    ]
    assert build_summary(steps) == "Walk to Alpha, ride Yellow to Bravo, walk to your destination."


def test_two_jeep_steps_and_summary(g):
    _, steps = trip(g, pt(0, 0), pt(4000, 0))
    d1 = round(haversine_m(*pt(0, 0), *pt(1000, 0)) + haversine_m(*pt(1000, 0), *pt(2000, 0)))
    d2 = round(haversine_m(*pt(2000, 0), *pt(3000, 0)) + haversine_m(*pt(3000, 0), *pt(4000, 0)))
    assert steps == [
        {"type": "walk", "from": "Your start point", "to": "Alpha", "distance_m": 0},
        {"type": "ride", "color": "yellow", "direction": "out", "from": "Alpha", "to": "Charlie",
         "stops_passed": 2, "distance_m": d1},
        {"type": "transfer", "from": "Charlie", "to": "Charlie", "walk_m": 0, "to_color": "darkyellow"},
        {"type": "ride", "color": "darkyellow", "direction": "out", "from": "Charlie", "to": "Echo",
         "stops_passed": 2, "distance_m": d2},
        {"type": "walk", "from": "Echo", "to": "Your destination", "distance_m": 0},
    ]
    assert build_summary(steps) == (
        "Walk to Alpha, ride Yellow to Charlie, transfer to Dark yellow, get off at Echo, walk to your destination."
    )


def test_three_jeep_summary_keeps_the_middle_ride():
    stops = {
        "a": ("Alpha", (0, 0)), "b": ("Bravo", (1000, 0)), "c": ("Charlie", (2000, 0)),
        "d": ("Delta", (3000, 0)), "e": ("Echo", (4000, 0)), "f": ("Foxtrot", (5000, 0)),
    }
    routes = {"yellow_out": ["a", "b", "c"], "darkyellow_out": ["c", "d", "e"], "red_out": ["e", "f"]}
    _, steps = trip(mk(stops, routes), pt(0, 0), pt(5000, 0))
    assert [s["type"] for s in steps] == ["walk", "ride", "transfer", "ride", "transfer", "ride", "walk"]
    assert build_summary(steps) == (
        "Walk to Alpha, ride Yellow to Charlie, transfer to Dark yellow, get off at Echo, "
        "transfer to Red, get off at Foxtrot, walk to your destination."
    )


def test_transfer_by_walking_between_stops():
    g2 = mk(
        {"a": ("A", (0, 0)), "b": ("B", (1000, 0)), "c": ("C", (1060, 0)), "d": ("D", (2000, 0))},
        {"yellow_out": ["a", "b"], "red_out": ["c", "d"]},
    )
    _, steps = trip(g2, pt(0, 0), pt(2000, 0))
    assert steps[2]["type"] == "transfer"
    assert steps[2]["walk_m"] == round(haversine_m(*pt(1000, 0), *pt(1060, 0)))
    assert (steps[2]["from"], steps[2]["to"], steps[2]["to_color"]) == ("B", "C", "red")


def test_penalty_makes_single_longer_jeep_win():
    stops = {"p": ("P", (0, 0)), "n": ("N", (1500, 1000)), "q": ("Q", (3000, 0)), "t": ("T", (1500, 0))}
    routes = {"yellow_out": ["p", "n", "q"], "red_out": ["p", "t"], "blue_out": ["t", "q"]}
    _, steps = trip(mk(stops, routes), pt(0, 0), pt(3000, 0))
    assert [s["type"] for s in steps] == ["walk", "ride", "walk"]
    assert steps[1]["color"] == "yellow"
    _, steps0 = trip(mk(stops, routes, penalty=0.0), pt(0, 0), pt(3000, 0))
    assert [s["type"] for s in steps0] == ["walk", "ride", "transfer", "ride", "walk"]


def test_disconnected_gives_no_path(g):
    path, steps = trip(g, pt(0, 0), pt(0, 20000))
    assert path is None and steps is None


def test_circular_route_follows_seq_order():
    stops = {"a": ("A", (0, 0)), "b": ("B", (1000, 0)), "c": ("C", (1000, 1000)), "d": ("D", (0, 1000))}
    g2 = mk(stops, {"purple_out": ["a", "b", "c", "a", "d"]})
    _, steps = trip(g2, pt(1000, 1000), pt(0, 1000))
    assert steps[1]["from"] == "C" and steps[1]["to"] == "D" and steps[1]["stops_passed"] == 2
    # from A the later pass (seq 3) is cheaper than riding all the way round
    _, steps = trip(g2, pt(0, 0), pt(0, 1000))
    assert steps[1]["stops_passed"] == 1
    assert steps[1]["distance_m"] == 1000


def test_same_stop_both_ends_has_no_ride(g):
    _, steps = trip(g, pt(0, 0), pt(10, 0))
    assert [s["type"] for s in steps] == ["walk", "walk"]
    assert build_summary(steps) == "Walk to Alpha, walk to your destination."


def test_walk_edges_do_not_chain_past_transfer_radius():
    # c1..c3 are each within XFER_R of the next, but c1 to c3 is not
    g2 = mk(
        {"a": ("A", (0, 0)), "b": ("B", (1000, 0)), "c1": ("C1", (1060, 0)),
         "c2": ("C2", (1120, 0)), "c3": ("C3", (1180, 0)), "d": ("D", (2000, 0))},
        {"yellow_out": ["a", "b"], "red_out": ["c3", "d"]},
    )
    path, _ = trip(g2, pt(0, 0), pt(2000, 0))
    assert path is None


# Wrap edge: a 1 km square loop a -> b -> c -> d, closed by d -> a when flagged circular.
SQUARE = {"a": ("Alpha", (0, 0)), "b": ("Bravo", (1000, 0)), "c": ("Charlie", (1000, 1000)), "d": ("Delta", (0, 1000))}


def seg(*ids):
    """Sum of straight-line segments through the stops, in metres."""
    return sum(haversine_m(*pt(*SQUARE[x][1]), *pt(*SQUARE[y][1])) for x, y in zip(ids, ids[1:]))


def loop(circular=True):
    return mk(SQUARE, {"purple_out": ["a", "b", "c", "d"]}, circular=("purple_out",) if circular else ())


def test_wrap_edge_on_circular_only():
    g2 = mk({**SQUARE, "e": ("Echo", (5000, 0)), "f": ("Foxtrot", (6000, 0))},
            {"purple_out": ["a", "b", "c", "d"], "blue_out": ["e", "f"]}, circular=("purple_out",))
    wrap = [(m, c, k) for m, c, k in g2.adj[on("purple_out", 3)] if m == on("purple_out", 0)]
    assert wrap == [(on("purple_out", 0), pytest.approx(seg("d", "a") / 1000), "ride")]
    assert not any(m == on("blue_out", 0) for m, _, _ in g2.adj[on("blue_out", 1)])
    assert len(g2.adj[on("purple_out", 3)]) == 2  # alight + wrap, nothing else


def test_wrap_needs_two_stops():
    g1 = mk({"a": ("Alpha", (0, 0))}, {"purple_out": ["a"]}, circular=("purple_out",))
    assert [k for _, _, k in g1.adj[on("purple_out", 0)]] == ["alight"]
    g0 = mk({"a": ("Alpha", (0, 0))}, {"purple_out": []}, circular=("purple_out",))
    assert g0.adj[at("a")] == []


def test_wrap_when_last_and_first_are_the_same_stop():
    g2 = mk({"a": ("Alpha", (0, 0)), "b": ("Bravo", (1000, 0))}, {"purple_out": ["a", "b", "a"]},
            circular=("purple_out",))
    assert (on("purple_out", 0), 0.0, "ride") in g2.adj[on("purple_out", 2)]
    # board at the last stop (a), alight at b: ride a -> wrap(a, 0 m) -> b; the wrap counts as one passed
    path, steps = trip(g2, pt(0, 0), pt(1000, 0))
    assert path is not None  # does not crash on the zero-length edge


def test_ride_across_the_wrap():
    g4 = loop()
    path, steps = trip(g4, pt(1000, 1000), pt(1000, 0))  # board Charlie, alight Bravo
    assert on("purple_out", 3) in path and on("purple_out", 0) in path
    rides = [s for s in steps if s["type"] == "ride"]
    assert len(rides) == 1
    r = rides[0]
    # edges: c->d, d->a (wrap), a->b = 3
    assert (r["from"], r["to"], r["color"], r["direction"]) == ("Charlie", "Bravo", "purple", "out")
    assert r["stops_passed"] == 3
    assert r["distance_m"] == round(seg("c", "d", "a", "b"))
    assert build_summary(steps) == "Walk to Charlie, ride Purple to Bravo, walk to your destination."


def test_ride_from_last_stop_to_first_is_one_edge():
    path, steps = trip(loop(), pt(0, 1000), pt(0, 0))  # Delta -> Alpha
    rides = [s for s in steps if s["type"] == "ride"]
    assert len(rides) == 1
    assert (rides[0]["from"], rides[0]["to"], rides[0]["stops_passed"]) == ("Delta", "Alpha", 1)
    assert rides[0]["distance_m"] == round(seg("d", "a"))


def test_wrap_needed_only_with_flag():
    start, end = pt(1000, 1000), pt(1000, 0)
    path, steps = trip(loop(circular=False), start, end)
    assert path is None  # Bravo is 1 km behind Charlie, beyond walking range
    path, steps = trip(loop(), start, end)
    assert [s["type"] for s in steps] == ["walk", "ride", "walk"]


def test_wrap_not_used_when_direct_path_is_cheaper():
    path, steps = trip(loop(), pt(0, 0), pt(1000, 1000))  # Alpha -> Charlie, forward
    assert on("purple_out", 0) in path
    assert not any(a == on("purple_out", 3) and b == on("purple_out", 0) for a, b in zip(path, path[1:]))
    ride = [s for s in steps if s["type"] == "ride"][0]
    assert ride["stops_passed"] == 2 and ride["distance_m"] == round(seg("a", "b", "c"))


def test_ride_continues_past_the_wrap_in_order():
    path, steps = trip(loop(), pt(0, 1000), pt(1000, 1000))  # Delta -> wrap -> Alpha -> Bravo -> Charlie
    ride = [s for s in steps if s["type"] == "ride"][0]
    assert ride["stops_passed"] == 3
    assert ride["distance_m"] == round(seg("d", "a", "b", "c"))
