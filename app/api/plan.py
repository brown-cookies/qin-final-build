import math
from typing import Optional

from fastapi import APIRouter, Request

from app.api import ApiError
from app.config import get_settings
from app.planner import search, steps
from app.schemas import ErrorResponse, PlanResponse

router = APIRouter(prefix="/api")

_errors = {400: {"model": ErrorResponse}, 404: {
    "model": ErrorResponse}, 500: {"model": ErrorResponse}, 503: {"model": ErrorResponse}}


def _point(lat_raw: Optional[str], lng_raw: Optional[str], label: str) -> tuple:
    bad = ApiError(400, "invalid_location",
                   f"The {label} needs a valid latitude and longitude inside the service area.")
    try:
        lat, lng = float(lat_raw), float(lng_raw)
    except (TypeError, ValueError):
        raise bad from None
    if not (math.isfinite(lat) and math.isfinite(lng)):
        raise bad
    lat_min, lat_max, lng_min, lng_max = get_settings().service_bbox
    if not (lat_min <= lat <= lat_max and lng_min <= lng <= lng_max):
        raise bad
    return lat, lng


@router.get("/plan", response_model=PlanResponse, responses=_errors)
def plan(
    request: Request,
    from_lat: Optional[str] = None,
    from_lng: Optional[str] = None,
    to_lat: Optional[str] = None,
    to_lng: Optional[str] = None,
):
    start = _point(from_lat, from_lng, "starting point")
    end = _point(to_lat, to_lng, "destination")
    if not request.app.state.routes:
        raise ApiError(503, "route_data_unavailable",
                       "Route data is not loaded. The service needs a restart or re-seed.")
    graph = request.app.state.graph
    radius = get_settings().walk_radius_m
    near_start = graph.stops_within(start[0], start[1], radius)
    if not near_start:
        raise ApiError(404, "no_stop_nearby",
                       "No jeepney stop is near your starting point.")
    near_end = graph.stops_within(end[0], end[1], radius)
    if not near_end:
        raise ApiError(404, "no_stop_nearby",
                       "No jeepney stop is near your destination.")
    path = search.find_path(graph, near_start, near_end)
    if path is None:
        raise ApiError(
            404, "no_route", "No jeepney route connects your starting point and your destination.")
    result = steps.build_steps(graph, path, start, end)
    return {"steps": result, "summary": steps.build_summary(result)}
