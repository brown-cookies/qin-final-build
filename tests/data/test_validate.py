"""validate.py tests. No database needed."""
import math
import subprocess
import sys
from pathlib import Path

import pytest

from data import validate
from data.snap_routes import dist_m, registry_ids
from tests.data.helpers import M_PER_DEG_LAT, clone, feature, shifted_twin, valid_collection, write

ROOT = Path(__file__).resolve().parents[2]


def run(coll):
    return validate.check_collection(coll)


def errs(coll):
    return run(coll)[0]


def has(errors, *needles):
    return any(all(n in e for n in needles) for e in errors)


def test_valid_collection_passes():
    errors, warnings, stats = run(valid_collection())
    assert errors == [] and warnings == []
    assert stats["routes"] == 9


def test_committed_geojson_is_valid():
    _data, errors, _warnings, stats = validate.check_file(validate.DEFAULT_PATH)
    assert errors == []
    assert stats["routes"] == 9


def test_script_runs_from_repo_root_and_other_cwd(tmp_path):
    for cwd in (ROOT, tmp_path):
        r = subprocess.run(
            [sys.executable, str(ROOT / "data" / "validate.py")], cwd=cwd, capture_output=True, text=True
        )
        assert r.returncode == 0, r.stdout + r.stderr
        assert "validate: ok" in r.stdout


def test_module_invocation_with_path_arg_fails_nonzero(tmp_path):
    coll = valid_collection()
    coll["features"].pop()
    p = write(tmp_path, coll)
    r = subprocess.run(
        [sys.executable, "-m", "data.validate", str(p)], cwd=ROOT, capture_output=True, text=True
    )
    assert r.returncode == 1
    assert "darkyellow_back" in r.stdout and "Traceback" not in r.stderr


# ---- file level ----

def test_file_missing(tmp_path, capsys):
    assert validate.main([str(tmp_path / "nope.geojson")]) == 1
    assert "not found" in capsys.readouterr().out


def test_file_empty(tmp_path, capsys):
    p = tmp_path / "e.geojson"
    p.write_text("  \n")
    assert validate.main([str(p)]) == 1
    assert "empty" in capsys.readouterr().out


def test_file_not_json(tmp_path, capsys):
    p = tmp_path / "j.geojson"
    p.write_text("{not json")
    assert validate.main([str(p)]) == 1
    assert "not valid JSON" in capsys.readouterr().out


@pytest.mark.parametrize(
    "body", [[], {"type": "Feature"}, {"type": "FeatureCollection"}, {"type": "FeatureCollection", "features": {}}]
)
def test_wrong_top_level(tmp_path, capsys, body):
    assert validate.main([str(write(tmp_path, body))]) == 1
    assert "FeatureCollection" in capsys.readouterr().out


def test_zero_features(tmp_path, capsys):
    assert validate.main([str(write(tmp_path, {"type": "FeatureCollection", "features": []}))]) == 1
    assert "zero features" in capsys.readouterr().out


def test_non_linestring_and_short_line():
    c = valid_collection()
    feature(c, "yellow_out")["geometry"] = {"type": "Point", "coordinates": [120.55, 15.1]}
    feature(c, "blue_out")["geometry"]["coordinates"] = [[120.55, 15.1]]
    e = errs(c)
    assert has(e, "yellow_out", "LineString")
    assert has(e, "blue_out", "at least 2 coordinates")
    feature(c, "red_out")["geometry"] = None
    assert has(errs(c), "red_out", "LineString")


def test_all_problems_reported_together_with_exit_1(tmp_path, capsys):
    c = valid_collection()
    del feature(c, "yellow_out")["properties"]["stops"][1:]
    del feature(c, "blue_out")["properties"]["stops"][1:]
    assert validate.main([str(write(tmp_path, c))]) == 1
    out = capsys.readouterr().out
    assert "yellow_out" in out and "blue_out" in out


# ---- bbox and numeric ----

def test_line_point_outside_bbox():
    c = valid_collection()
    feature(c, "red_out")["geometry"]["coordinates"][3] = [120.55, 16.0]
    assert has(errs(c), "red_out", "point 3", "SERVICE_BBOX")


def test_swapped_lat_lng_on_line_is_caught():
    c = valid_collection()
    lng, lat = feature(c, "red_out")["geometry"]["coordinates"][3]
    feature(c, "red_out")["geometry"]["coordinates"][3] = [lat, lng]
    assert has(errs(c), "red_out", "point 3")


def test_stop_outside_bbox_and_swapped():
    c = valid_collection()
    s = feature(c, "red_out")["properties"]["stops"][0]
    s["lat"], s["lng"] = s["lng"], s["lat"]
    assert has(errs(c), "red_out", "seq 1", "SERVICE_BBOX")


def test_bbox_comes_from_env(monkeypatch):
    monkeypatch.setenv("SERVICE_BBOX", "15.0,15.1,120.0,120.1")
    assert has(errs(valid_collection()), "SERVICE_BBOX")


@pytest.mark.parametrize("bad", ["x", None, float("nan"), float("inf"), True, [], {}])
def test_bad_line_values(bad):
    c = valid_collection()
    feature(c, "grey_out")["geometry"]["coordinates"][4] = [bad, 15.1]
    assert has(errs(c), "grey_out", "point 4")


@pytest.mark.parametrize("bad", ["x", None, float("nan"), float("-inf"), True])
def test_bad_stop_coordinates(bad):
    c = valid_collection()
    feature(c, "grey_out")["properties"]["stops"][1]["lat"] = bad
    assert has(errs(c), "grey_out", "seq 2", "finite")


def test_missing_stop_lat():
    c = valid_collection()
    del feature(c, "grey_out")["properties"]["stops"][1]["lat"]
    assert has(errs(c), "grey_out", "missing property lat")


# ---- seq ----

def test_explicit_seq_gap():
    c = valid_collection()
    stops = feature(c, "red_out")["properties"]["stops"]
    for i, s in enumerate(stops):
        s["seq"] = i + 1
    stops[2]["seq"] = 4
    assert has(errs(c), "red_out", "seq 3", "gap")


def test_explicit_seq_not_starting_at_1():
    c = valid_collection()
    for i, s in enumerate(feature(c, "red_out")["properties"]["stops"]):
        s["seq"] = i + 2
    assert has(errs(c), "red_out", "seq 1", "start at 1")


def test_explicit_valid_seq_passes():
    c = valid_collection()
    for i, s in enumerate(feature(c, "red_out")["properties"]["stops"]):
        s["seq"] = i + 1
    assert errs(c) == []


# ---- stops count, registry ----

def test_fewer_than_two_stops():
    c = valid_collection()
    feature(c, "red_out")["properties"]["stops"] = feature(c, "red_out")["properties"]["stops"][:1]
    assert has(errs(c), "red_out", "at least 2 stops")


def test_stops_not_a_list():
    c = valid_collection()
    feature(c, "red_out")["properties"]["stops"] = "nope"
    assert has(errs(c), "red_out", "stops must be a list")


def test_missing_registry_route_is_named():
    c = valid_collection()
    c["features"] = [f for f in c["features"] if f["properties"]["route_id"] != "darkyellow_back"]
    assert has(errs(c), "darkyellow_back", "missing from file")


@pytest.mark.parametrize("rid", ["yellow_back", "purple_back", "grey_back", "orange_out", "nounderscore", "dark_yellow_out"])
def test_invalid_route_ids(rid):
    c = valid_collection()
    f = clone({"f": feature(c, "red_out")})["f"]
    f["properties"]["route_id"] = rid
    c["features"].append(f)
    assert has(errs(c), rid)


def test_darkyellow_splits_on_last_underscore():
    assert "darkyellow_out" in registry_ids()
    assert errs(valid_collection()) == []


def test_color_direction_name_must_match():
    c = valid_collection()
    p = feature(c, "red_out")["properties"]
    p["color"], p["direction"], p["name"] = "blue", "back", "Wrong"
    e = errs(c)
    assert has(e, "red_out", "color") and has(e, "red_out", "direction") and has(e, "red_out", "name")


# ---- properties ----

@pytest.mark.parametrize("key", ["route_id", "color", "direction", "name", "source", "verified_on", "osm_relation_id", "stops"])
def test_missing_property_named(key):
    c = valid_collection()
    del feature(c, "red_out")["properties"][key]
    assert has(errs(c), "missing property", key)


@pytest.mark.parametrize("key", ["stop_id", "name", "lat", "lng", "osm_node_id"])
def test_missing_stop_property_named(key):
    c = valid_collection()
    del feature(c, "red_out")["properties"]["stops"][0][key]
    assert has(errs(c), "missing property", key)


def test_nullable_present_null_is_fine_and_non_null_fails():
    c = valid_collection()
    assert errs(c) == []
    p = feature(c, "red_out")["properties"]
    p["osm_relation_id"] = 5
    p["stops"][0]["osm_node_id"] = 7
    p["source"] = "ridden"
    e = errs(c)
    assert has(e, "osm_relation_id") and has(e, "osm_node_id") and has(e, "source")


def test_empty_stop_id_and_name():
    c = valid_collection()
    stops = feature(c, "red_out")["properties"]["stops"]
    stops[0]["stop_id"] = ""
    stops[1]["name"] = 5
    e = errs(c)
    assert has(e, "red_out", "seq 1", "stop_id") and has(e, "red_out", "seq 2", "name")


def test_duplicate_route_id():
    c = valid_collection()
    c["features"].append(clone({"f": feature(c, "red_out")})["f"])
    assert has(errs(c), "red_out", "duplicate route_id")


def test_feature_without_properties_object():
    c = valid_collection()
    c["features"].append({"type": "Feature", "geometry": None, "properties": None})
    assert has(errs(c), "feature 9")


# ---- shared stops: collision and near duplicates ----

def test_collision_over_100m_fails_and_exactly_100_passes():
    c = valid_collection()
    shifted_twin(c, 100.01)
    assert has(errs(c), "yellow_out", "blue_out", "yellow_out_a", "apart")
    c = valid_collection()
    shifted_twin(c, 99.99)
    assert not has(errs(c), "apart")


def test_real_world_pampang_55m_passes():
    c = valid_collection()
    shifted_twin(c, 55)
    assert not has(errs(c), "apart")


def test_near_duplicate_warns_but_exit_zero(tmp_path, capsys):
    c = valid_collection()
    shifted_twin(c, 20)
    errors, warnings, _ = run(c)
    assert errors == []
    assert warnings and all(w.startswith("WARNING") for w in warnings)
    assert validate.main([str(write(tmp_path, c))]) == 0
    assert "WARNING" in capsys.readouterr().out


def test_exactly_30m_apart_does_not_warn_but_just_under_does():
    c = valid_collection()
    shifted_twin(c, 30.01)
    assert not any("blue_out_b" in w for w in run(c)[1])
    c = valid_collection()
    shifted_twin(c, 29.99)
    assert any("blue_out_b" in w for w in run(c)[1])


def test_warnings_still_printed_when_there_is_a_failure(tmp_path, capsys):
    c = valid_collection()
    shifted_twin(c, 20)
    feature(c, "red_out")["properties"]["stops"].pop()
    feature(c, "red_out")["properties"]["stops"].pop()
    assert validate.main([str(write(tmp_path, c))]) == 1
    out = capsys.readouterr().out
    assert "WARNING" in out and "ERROR" in out


def test_circular_repeat_stop_is_valid_without_warning():
    c = valid_collection()
    stops = feature(c, "yellow_out")["properties"]["stops"]
    stops.append(dict(stops[0]))
    errors, warnings, _ = run(c)
    assert errors == [] and warnings == []


def test_circular_repeat_checked_against_line_for_each_occurrence():
    c = valid_collection()
    stops = feature(c, "yellow_out")["properties"]["stops"]
    far = dict(stops[0])
    far["lat"] += 0.002  # about 220 m off the line
    stops.append(far)
    assert has(errs(c), "yellow_out", "seq 4", "route line")


# ---- line gap, stop to line ----

def set_gap(c, rid, meters):
    pts = feature(c, rid)["geometry"]["coordinates"]
    lat = pts[9][1]
    pts[10][0] = pts[9][0] + meters / (M_PER_DEG_LAT * math.cos(math.radians(lat)))
    assert abs(dist_m(pts[9], pts[10]) - meters) < 0.001


def test_line_gap_over_50m_fails_and_under_passes():
    c = valid_collection()
    set_gap(c, "red_out", 50.01)
    assert has(errs(c), "red_out", "gap", "points 9 and 10")
    c = valid_collection()
    set_gap(c, "red_out", 49.99)
    assert errs(c) == []


def test_stop_over_100m_from_line_fails_and_under_passes():
    c = valid_collection()
    feature(c, "red_out")["properties"]["stops"][1]["lat"] += 100.05 / M_PER_DEG_LAT
    assert has(errs(c), "red_out", "red_out_b", "route line")
    c = valid_collection()
    feature(c, "red_out")["properties"]["stops"][1]["lat"] += 99.95 / M_PER_DEG_LAT
    assert errs(c) == []
