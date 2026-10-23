import pytest

from app.config import ConfigError, load_settings


def test_defaults():
    s = load_settings({"DATABASE_URL": "postgresql://x/y"})
    assert s.database_url == "postgresql://x/y"
    assert s.service_bbox == (15.08, 15.22, 120.50, 120.68)
    assert s.walk_radius_m == 500
    assert s.transfer_radius_m == 100
    assert s.transfer_penalty_km == 1.0
    assert s.walk_cost_factor == 2.0
    assert s.graph_mode == "cached"


def test_overrides():
    s = load_settings(
        {
            "DATABASE_URL": "postgresql://a/b",
            "SERVICE_BBOX": "1,2,3,4",
            "WALK_RADIUS_M": "250",
            "TRANSFER_RADIUS_M": "50",
            "TRANSFER_PENALTY_KM": "2.5",
            "WALK_COST_FACTOR": "3",
            "GRAPH_MODE": "rebuild",
        }
    )
    assert s.database_url == "postgresql://a/b"
    assert s.service_bbox == (1.0, 2.0, 3.0, 4.0)
    assert (s.walk_radius_m, s.transfer_radius_m) == (250, 50)
    assert (s.transfer_penalty_km, s.walk_cost_factor) == (2.5, 3)
    assert s.graph_mode == "rebuild"


@pytest.mark.parametrize(
    "env",
    [
        {"SERVICE_BBOX": "1,2,3"},
        {"SERVICE_BBOX": "a,b,c,d"},
        {"SERVICE_BBOX": "2,1,3,4"},
        {"GRAPH_MODE": "lazy"},
        {"WALK_RADIUS_M": "abc"},
        {"WALK_RADIUS_M": "-5"},
    ],
)
def test_invalid_values_fail(env):
    with pytest.raises(ConfigError):
        load_settings(env)
