"""Validate routes.geojson against SPEC 9.3. No DB, no network.

    python data/validate.py [path]     # default data/routes/routes.geojson
    python -m data.validate [path]

Prints one line per problem and exits 1 on any failure. Warnings never change the exit code.
"""
import json
import math
import sys
from pathlib import Path

# Run as a script, sys.path[0] is data/; the repo root is needed for app.config.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import load_settings  # noqa: E402
from data.snap_routes import REGISTRY, dist_m, registry_ids  # noqa: E402

DEFAULT_PATH = ROOT / "data" / "routes" / "routes.geojson"

# Fixed by SPEC 9.3, deliberately not env tunables.
MAX_STOP_COLLISION_M = 100
MAX_LINE_GAP_M = 50
MAX_STOP_TO_LINE_M = 100
NEAR_DUPLICATE_M = 30

PROPERTIES = ("route_id", "color", "direction", "name", "source", "verified_on", "osm_relation_id", "stops")
STOP_KEYS = ("stop_id", "name", "lat", "lng", "osm_node_id")


class FileProblem(Exception):
    """The file cannot be checked at all (missing, not JSON, wrong top-level shape)."""


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def load_collection(path):
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise FileProblem(f"{path}: file not found") from None
    except (OSError, UnicodeDecodeError) as exc:
        raise FileProblem(f"{path}: cannot read file ({exc})") from None
    if not text.strip():
        raise FileProblem(f"{path}: file is empty")
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise FileProblem(f"{path}: not valid JSON ({exc})") from None
    if not isinstance(data, dict) or data.get("type") != "FeatureCollection" or not isinstance(
        data.get("features"), list
    ):
        raise FileProblem(f"{path}: top level must be a FeatureCollection with a features list")
    if not data["features"]:
        raise FileProblem(f"{path}: FeatureCollection has zero features")
    return data


def _check_line(rid, geom, bbox, errors):
    """Returns the line as [(lng, lat)] when usable, else None."""
    if not isinstance(geom, dict) or geom.get("type") != "LineString":
        errors.append(f"{rid}: geometry must be a LineString")
        return None
    coords = geom.get("coordinates")
    if not isinstance(coords, list) or len(coords) < 2:
        errors.append(f"{rid}: LineString needs at least 2 coordinates")
        return None
    lat_min, lat_max, lng_min, lng_max = bbox
    line = []
    ok = True
    for i, c in enumerate(coords):
        if not (isinstance(c, (list, tuple)) and len(c) >= 2 and _num(c[0]) and _num(c[1])):
            errors.append(f"{rid}: line point {i} is not a finite [lng, lat] pair")
            ok = False
            continue
        lng, lat = c[0], c[1]
        if not (lat_min <= lat <= lat_max and lng_min <= lng <= lng_max):
            errors.append(f"{rid}: line point {i} [{lng}, {lat}] is outside SERVICE_BBOX")
            ok = False
        line.append((lng, lat))
    if not ok:
        return None
    for i in range(1, len(line)):
        gap = dist_m(line[i - 1], line[i])
        if gap > MAX_LINE_GAP_M:
            errors.append(f"{rid}: line gap of {gap:.0f} m between points {i - 1} and {i} (max {MAX_LINE_GAP_M} m)")
    return line


def _check_stops(rid, stops, line, bbox, errors):
    """Returns [(seq, stop_id, name, lat, lng)] for stops with usable coordinates."""
    lat_min, lat_max, lng_min, lng_max = bbox
    good = []
    for i, s in enumerate(stops):
        pos = i + 1
        if not isinstance(s, dict):
            errors.append(f"{rid} seq {pos}: stop must be an object")
            continue
        sid = s.get("stop_id")
        label = sid if isinstance(sid, str) and sid else "?"
        for key in STOP_KEYS:
            if key not in s:
                errors.append(f"{rid} seq {pos} stop {label}: missing property {key}")
        if "stop_id" in s and not (isinstance(sid, str) and sid.strip()):
            errors.append(f"{rid} seq {pos}: stop_id must be a non-empty string")
        if "name" in s and not (isinstance(s["name"], str) and s["name"].strip()):
            errors.append(f"{rid} seq {pos} stop {label}: name must be a non-empty string")
        if s.get("osm_node_id") is not None:
            errors.append(f"{rid} seq {pos} stop {label}: osm_node_id must be null")
        if "seq" in s and (isinstance(s["seq"], bool) or s["seq"] != pos):
            if pos == 1:
                errors.append(f"{rid} seq {pos} stop {label}: seq must start at 1, got {s['seq']!r}")
            else:
                errors.append(f"{rid} seq {pos} stop {label}: seq gap or repeat, expected {pos}, got {s['seq']!r}")
        lat, lng = s.get("lat"), s.get("lng")
        if "lat" in s and "lng" in s:
            if not (_num(lat) and _num(lng)):
                errors.append(f"{rid} seq {pos} stop {label}: lat/lng must be finite numbers")
                continue
            if not (lat_min <= lat <= lat_max and lng_min <= lng <= lng_max):
                errors.append(f"{rid} seq {pos} stop {label}: ({lat}, {lng}) is outside SERVICE_BBOX")
                continue
            if isinstance(sid, str) and sid:
                good.append((pos, sid, s.get("name"), lat, lng))
                if line is not None:
                    p = (lng, lat)
                    d = float("inf")
                    for q in line:
                        d = min(d, dist_m(p, q))
                        if d <= MAX_STOP_TO_LINE_M:
                            break
                    if d > MAX_STOP_TO_LINE_M:
                        errors.append(
                            f"{rid} seq {pos} stop {label}: {d:.0f} m from its route line (max {MAX_STOP_TO_LINE_M} m)"
                        )
    return good


def _check_properties(props, errors):
    """Returns the route_id when it is usable as a label, else None."""
    rid = props.get("route_id")
    label = rid if isinstance(rid, str) and rid else "(no route_id)"
    for key in PROPERTIES:
        if key not in props:
            errors.append(f"{label}: missing property {key}")
    if "route_id" in props and not (isinstance(rid, str) and rid):
        errors.append(f"{label}: route_id must be a non-empty string")
        return None
    if not isinstance(rid, str):
        return None
    if "_" not in rid:
        errors.append(f"{rid}: route_id must look like {{color}}_{{direction}}")
        return rid
    color, direction = rid.rsplit("_", 1)
    if color not in REGISTRY:
        errors.append(f"{rid}: unknown color {color!r}")
    elif direction not in REGISTRY[color][1]:
        allowed = "/".join(REGISTRY[color][1])
        errors.append(f"{rid}: {color} has no {direction!r} route (allowed: {allowed})")
    else:
        if "color" in props and props["color"] != color:
            errors.append(f"{rid}: color {props['color']!r} does not match route_id")
        if "direction" in props and props["direction"] != direction:
            errors.append(f"{rid}: direction {props['direction']!r} does not match route_id")
        if "name" in props and props["name"] != REGISTRY[color][0]:
            errors.append(f"{rid}: name {props['name']!r} should be {REGISTRY[color][0]!r}")
    if "source" in props and props["source"] != "memory-traced":
        errors.append(f"{rid}: source must be 'memory-traced', got {props['source']!r}")
    if props.get("osm_relation_id") is not None:
        errors.append(f"{rid}: osm_relation_id must be null")
    return rid


def check_collection(data):
    """Returns (errors, warnings, stats) for a parsed FeatureCollection."""
    bbox = load_settings().service_bbox
    errors, warnings = [], []
    seen_ids = set()
    occurrences = []  # (route_id, stop_id, lat, lng)
    n_stops = 0

    for idx, feat in enumerate(data["features"]):
        if not isinstance(feat, dict) or not isinstance(feat.get("properties"), dict):
            errors.append(f"feature {idx}: must be an object with a properties object")
            continue
        props = feat["properties"]
        rid = _check_properties(props, errors)
        label = rid or f"feature {idx}"
        if rid is not None:
            if rid in seen_ids:
                errors.append(f"{rid}: duplicate route_id")
            seen_ids.add(rid)
        line = _check_line(label, feat.get("geometry"), bbox, errors)
        stops = props.get("stops")
        if "stops" not in props:
            continue
        if not isinstance(stops, list):
            errors.append(f"{label}: stops must be a list")
            continue
        if len(stops) < 2:
            errors.append(f"{label}: needs at least 2 stops, has {len(stops)}")
        n_stops += len(stops)
        for pos, sid, _name, lat, lng in _check_stops(label, stops, line, bbox, errors):
            occurrences.append((label, sid, lat, lng))

    for rid in registry_ids():
        if rid not in seen_ids:
            errors.append(f"{rid}: missing from file (registry route)")

    # Same stop_id on different routes must be the same place.
    by_id = {}
    for rid, sid, lat, lng in occurrences:
        by_id.setdefault(sid, []).append((rid, lat, lng))
    for sid, occ in sorted(by_id.items()):
        for i in range(len(occ)):
            for j in range(i + 1, len(occ)):
                (r1, la1, ln1), (r2, la2, ln2) = occ[i], occ[j]
                if r1 == r2:
                    continue
                d = dist_m((ln1, la1), (ln2, la2))
                if d > MAX_STOP_COLLISION_M:
                    errors.append(
                        f"{r1} / {r2} stop {sid}: same stop_id {d:.0f} m apart (max {MAX_STOP_COLLISION_M} m)"
                    )

    # Different stop_ids that are almost the same place: warn only.
    distinct = sorted({(sid, lat, lng) for _r, sid, lat, lng in occurrences})
    warned = set()
    for i in range(len(distinct)):
        for j in range(i + 1, len(distinct)):
            (s1, la1, ln1), (s2, la2, ln2) = distinct[i], distinct[j]
            if s1 == s2 or (s1, s2) in warned:
                continue
            d = dist_m((ln1, la1), (ln2, la2))
            if d < NEAR_DUPLICATE_M:
                warned.add((s1, s2))
                warnings.append(f"WARNING stops {s1} and {s2} are only {d:.0f} m apart (under {NEAR_DUPLICATE_M} m)")

    stats = {"routes": len(seen_ids), "stops": len(by_id), "stop_entries": n_stops}
    return errors, warnings, stats


def check_file(path=DEFAULT_PATH):
    """Returns (data, errors, warnings, stats); raises FileProblem for file-level failures."""
    data = load_collection(path)
    errors, warnings, stats = check_collection(data)
    return data, errors, warnings, stats


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    path = Path(argv[0]) if argv else DEFAULT_PATH
    try:
        _data, errors, warnings, stats = check_file(path)
    except FileProblem as exc:
        print(f"FAIL {exc}")
        return 1
    for w in warnings:
        print(w)
    for e in errors:
        print(f"ERROR {e}")
    if errors:
        print(f"validate: FAILED with {len(errors)} problem(s), {len(warnings)} warning(s)")
        return 1
    print(
        f"validate: ok, {stats['routes']} routes, {stats['stops']} distinct stops "
        f"({stats['stop_entries']} route stop entries), {len(warnings)} warning(s)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
