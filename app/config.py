"""Environment-driven settings (SPEC Section 10). The only place defaults live."""
import math
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Mapping, Optional


class ConfigError(ValueError):
    """Raised for an invalid environment value; startup turns it into a log line and exit."""


@dataclass(frozen=True)
class Settings:
    database_url: str
    # lat_min, lat_max, lng_min, lng_max
    service_bbox: tuple
    walk_radius_m: float
    transfer_radius_m: float
    transfer_penalty_km: float
    walk_cost_factor: float
    # Not in SPEC Section 10: bounds every wait for a pooled connection so a dead DB
    # yields 503 instead of a hang.
    db_pool_timeout_s: float


def _number(env: Mapping[str, str], name: str, default: str) -> float:
    raw = env.get(name, default)
    try:
        value = float(raw)
    except ValueError:
        raise ConfigError(f"{name} must be a number, got {raw!r}") from None
    if not math.isfinite(value) or value <= 0:
        raise ConfigError(f"{name} must be a positive finite number, got {raw!r}")
    return value


def _bbox(raw: str) -> tuple:
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) != 4:
        raise ConfigError("SERVICE_BBOX must be lat_min,lat_max,lng_min,lng_max (4 values)")
    try:
        lat_min, lat_max, lng_min, lng_max = (float(p) for p in parts)
    except ValueError:
        raise ConfigError(f"SERVICE_BBOX values must be numbers, got {raw!r}") from None
    if not all(math.isfinite(v) for v in (lat_min, lat_max, lng_min, lng_max)):
        raise ConfigError("SERVICE_BBOX values must be finite")
    if lat_min >= lat_max or lng_min >= lng_max:
        raise ConfigError("SERVICE_BBOX needs lat_min < lat_max and lng_min < lng_max")
    return (lat_min, lat_max, lng_min, lng_max)


def load_settings(env: Optional[Mapping[str, str]] = None) -> Settings:
    env = os.environ if env is None else env
    return Settings(
        # Local dev default only; compose and CI set their own.
        database_url=env.get("DATABASE_URL", "postgresql://biyahe:biyahe@127.0.0.1:5432/biyahe"),
        service_bbox=_bbox(env.get("SERVICE_BBOX", "15.08,15.22,120.50,120.68")),
        walk_radius_m=_number(env, "WALK_RADIUS_M", "500"),
        transfer_radius_m=_number(env, "TRANSFER_RADIUS_M", "100"),
        transfer_penalty_km=_number(env, "TRANSFER_PENALTY_KM", "1.0"),
        walk_cost_factor=_number(env, "WALK_COST_FACTOR", "2.0"),
        db_pool_timeout_s=_number(env, "DB_POOL_TIMEOUT_S", "3"),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()
