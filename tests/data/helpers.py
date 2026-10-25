"""Builds a small valid FeatureCollection in memory; tests mutate copies of it."""
import copy
import json
import math

from data.snap_routes import REGISTRY, registry_ids

# 0.0003 deg of longitude is about 32 m at this latitude, under the 50 m line-gap limit.
LNG0, LNG_STEP, N_POINTS = 120.55, 0.0003, 20
STOP_POINTS = (2, 10, 18)
M_PER_DEG_LAT = 2 * math.pi * 6371000 / 360


def make_feature(route_id, lat):
    color, direction = route_id.rsplit("_", 1)
    line = [[round(LNG0 + i * LNG_STEP, 6), lat] for i in range(N_POINTS)]
    stops = [
        {"stop_id": f"{route_id}_{k}", "name": f"{route_id} {k}", "lat": lat, "lng": line[i][0], "osm_node_id": None}
        for k, i in zip("abc", STOP_POINTS)
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


def valid_collection():
    # One route per 0.01 deg of latitude (about 1.1 km), so stops of different routes never meet.
    feats = [make_feature(rid, round(15.09 + 0.012 * i, 6)) for i, rid in enumerate(registry_ids())]
    return {"type": "FeatureCollection", "features": feats}


def feature(coll, route_id):
    return next(f for f in coll["features"] if f["properties"]["route_id"] == route_id)


def shifted_twin(c, dlat_m):
    """Replace blue_out with yellow_out moved north; its first stop reuses yellow's first stop_id."""
    y = feature(c, "yellow_out")
    b = feature(c, "blue_out")
    dlat = dlat_m / M_PER_DEG_LAT
    b["geometry"]["coordinates"] = [[lng, lat + dlat] for lng, lat in y["geometry"]["coordinates"]]
    stops = clone(y["properties"]["stops"])
    for i, s in enumerate(stops):
        s["lat"] += dlat
        s["stop_id"] = f"blue_out_{'abc'[i]}"
    stops[0]["stop_id"] = y["properties"]["stops"][0]["stop_id"]
    b["properties"]["stops"] = stops


def write(tmp_path, coll, name="routes.geojson"):
    p = tmp_path / name
    p.write_text(json.dumps(coll), encoding="utf-8")
    return p


def clone(coll):
    return copy.deepcopy(coll)
