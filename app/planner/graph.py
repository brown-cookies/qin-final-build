"""In-memory routing graph built from plain data. No DB or config imports."""
import math
from collections import namedtuple

Stop = namedtuple("Stop", "stop_id name lat lng")

_EARTH_M = 6371000.0


def haversine_m(lat1, lng1, lat2, lng2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * _EARTH_M * math.asin(min(1.0, math.sqrt(a)))


def at(stop_id):
    return ("at", stop_id)


def on(route_id, seq):
    return ("on", route_id, seq)


def mark_circular(routes):
    """Set routes[rid]["circular"]: a color with an `out` record and no `back` record (SPEC Section 7)."""
    colors_with_back = {r["color"] for r in routes.values() if r["direction"] == "back"}
    for r in routes.values():
        r["circular"] = r["direction"] == "out" and r["color"] not in colors_with_back


class Graph:
    """Nodes: ("at", stop_id) and ("on", route_id, seq), seq 0-based position on the route.

    adj maps node -> list of (neighbor, cost_km, kind); kind is board, ride, alight or walk.
    Query-time start/end nodes are never added here (see search.find_path).
    """

    def __init__(self, stops, routes, walk_radius_m, transfer_radius_m, transfer_penalty_km, walk_cost_factor):
        """stops: {stop_id: Stop}. routes: {route_id: {"color", "direction", "stops": [stop_id, ...], optional "circular": bool}}."""
        self.stops = stops
        self.routes = routes
        self.walk_radius_m = walk_radius_m
        self.walk_cost_factor = walk_cost_factor
        adj = {at(sid): [] for sid in stops}
        for rid, route in routes.items():
            ids = route["stops"]
            for i, sid in enumerate(ids):
                node = on(rid, i)
                adj[node] = [(at(sid), 0.0, "alight")]
                adj[at(sid)].append((node, transfer_penalty_km, "board"))
            for i in range(len(ids) - 1):
                km = self.dist_m(ids[i], ids[i + 1]) / 1000.0
                adj[on(rid, i)].append((on(rid, i + 1), km, "ride"))
            if route.get("circular") and len(ids) >= 2:  # the jeep keeps looping: last stop -> first
                km = self.dist_m(ids[-1], ids[0]) / 1000.0
                adj[on(rid, len(ids) - 1)].append((on(rid, 0), km, "ride"))
        ordered = sorted(stops)
        for i, a in enumerate(ordered):
            for b in ordered[i + 1:]:
                d = self.dist_m(a, b)
                if d <= transfer_radius_m:
                    cost = d / 1000.0 * walk_cost_factor
                    adj[at(a)].append((at(b), cost, "walk"))
                    adj[at(b)].append((at(a), cost, "walk"))
        self.adj = adj

    def dist_m(self, a, b):
        sa, sb = self.stops[a], self.stops[b]
        return haversine_m(sa.lat, sa.lng, sb.lat, sb.lng)

    def stops_within(self, lat, lng, radius_m):
        """[(stop_id, metres)] for stops at or inside radius_m, nearest first."""
        found = []
        for s in self.stops.values():
            d = haversine_m(lat, lng, s.lat, s.lng)
            if d <= radius_m:
                found.append((s.stop_id, d))
        found.sort(key=lambda x: (x[1], x[0]))
        return found
