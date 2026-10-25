"""Snap hand-traced waypoints to roads with OSRM and write routes.geojson.

Offline script (SPEC 9.2). Runtime and CI never call OSRM.

    python -m data.snap_routes            # snap and write data/routes/routes.geojson
    python -m data.snap_routes --dry-run  # check waypoints against the registry, no network
    python -m data.snap_routes --reuse    # re-process the committed lines (densify, join check), no network
"""
import argparse
import csv
import json
import math
import re
import sys
import time
import urllib.request
from pathlib import Path

OSRM_URL = "https://router.project-osrm.org/route/v1/driving/{coords}"
# Public server rejects long requests; routes are split into overlapping chunks.
CHUNK = 80
PAUSE_S = 1.0
# OSRM returns few points on straight roads; densify so validate.py's 50 m line-gap
# rule (SPEC 9.3) only trips on real jumps, which the join check below catches instead.
MAX_STEP_M = 40
# Every waypoint, vias included, must land this close to the snapped line.
MAX_JOIN_M = 50

HERE = Path(__file__).parent
WAYPOINTS = HERE / "raw" / "waypoints.csv"
OUT = HERE / "routes" / "routes.geojson"

# SPEC Section 7 registry: color -> (name, directions)
REGISTRY = {
    "yellow": ("Villa - Pampang", ("out",)),
    "blue": ("Pandan - Pampang", ("out", "back")),
    "purple": ("Checkpoint - Holy - Highway", ("out",)),
    "grey": ("Checkpoint - Balibago - Highway", ("out",)),
    "red": ("Sapang Bato - Angeles", ("out", "back")),
    "darkyellow": ("Main Gate - Friendship", ("out", "back")),
}


def slug(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def registry_ids():
    return [f"{color}_{d}" for color, (_, dirs) in REGISTRY.items() for d in dirs]


def load_waypoints(path=WAYPOINTS):
    routes = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            routes.setdefault(row["route_id"], []).append(row)
    for rows in routes.values():
        rows.sort(key=lambda r: int(r["seq"]))
    return routes


def check_registry(routes):
    expected = registry_ids()
    missing = [r for r in expected if r not in routes]
    extra = [r for r in routes if r not in expected]
    if missing or extra:
        sys.exit(f"snap_routes: missing waypoints for {missing}, unknown route IDs {extra}")


def dist_m(a, b):
    """Haversine distance in metres between (lng, lat) pairs."""
    p1, p2 = math.radians(a[1]), math.radians(b[1])
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b[0] - a[0]) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def densify(line, max_step=MAX_STEP_M):
    out = [line[0]]
    for a, b in zip(line, line[1:]):
        n = math.ceil(dist_m(a, b) / max_step)
        for i in range(1, n):
            t = i / n
            out.append([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t])
        out.append(b)
    return out


def check_joins(route_id, rows, line):
    bad = []
    for r in rows:
        wp = (float(r["lng"]), float(r["lat"]))
        d = min(dist_m(wp, q) for q in line)
        if d > MAX_JOIN_M:
            bad.append(f"seq {r['seq']} {r['name'] or '(via)'}: {d:.0f} m")
    if bad:
        sys.exit(f"snap_routes: {route_id} waypoints far from snapped line: " + "; ".join(bad))


def snap_chunk(points):
    coords = ";".join(f"{lng},{lat}" for lat, lng in points)
    url = OSRM_URL.format(coords=coords) + "?overview=full&geometries=geojson&continue_straight=false"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                data = json.load(resp)
            if data.get("code") != "Ok":
                raise RuntimeError(f"OSRM code {data.get('code')}: {data.get('message')}")
            return data["routes"][0]["geometry"]["coordinates"]
        except Exception as exc:
            if attempt == 2:
                raise RuntimeError(f"OSRM request failed: {exc}") from exc
            time.sleep(3 * (attempt + 1))


def snap_route(rows):
    points = [(float(r["lat"]), float(r["lng"])) for r in rows]
    line = []
    start = 0
    while start < len(points) - 1:
        end = min(start + CHUNK, len(points))
        piece = snap_chunk(points[start:end])
        line.extend(piece if not line else piece[1:])
        start = end - 1
        time.sleep(PAUSE_S)
    return line


def feature(route_id, rows, line):
    color, direction = route_id.rsplit("_", 1)
    stops = [
        {
            "stop_id": slug(r["name"]),
            "name": r["name"],
            "lat": float(r["lat"]),
            "lng": float(r["lng"]),
            "osm_node_id": None,
        }
        for r in rows
        if r["is_stop"] == "1"
    ]
    return {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": line},
        "properties": {
            "route_id": route_id,
            "color": color,
            "direction": direction,
            "name": REGISTRY[color][0],
            "source": "memory-traced",
            "verified_on": None,
            "osm_relation_id": None,
            "stops": stops,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="validate input only, no network")
    parser.add_argument("--reuse", action="store_true", help="reuse lines already in routes.geojson, no network")
    args = parser.parse_args()

    routes = load_waypoints()
    check_registry(routes)
    for rid in registry_ids():
        rows = routes[rid]
        n_stops = sum(r["is_stop"] == "1" for r in rows)
        print(f"{rid}: {len(rows)} points, {n_stops} stops")
    if args.dry_run:
        print("dry run ok; OSRM not called")
        return

    existing = {}
    if args.reuse:
        for f in json.loads(OUT.read_text())["features"]:
            existing[f["properties"]["route_id"]] = f["geometry"]["coordinates"]

    features = []
    for rid in registry_ids():
        line = existing[rid] if args.reuse else snap_route(routes[rid])
        line = densify(line)
        check_joins(rid, routes[rid], line)
        print(f"snapped {rid}: {len(line)} line points")
        features.append(feature(rid, routes[rid], line))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"type": "FeatureCollection", "features": features}))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
