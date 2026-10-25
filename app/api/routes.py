from typing import List

from fastapi import APIRouter, Request

from app.api import ApiError
from app.schemas import ErrorResponse, RouteDetail, RouteListItem

router = APIRouter(prefix="/api")

_errors = {404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}}


@router.get("/routes", response_model=List[RouteListItem], responses=_errors)
def list_routes(request: Request):
    return [
        {k: r[k] for k in ("route_id", "color", "direction", "name")} | {"stop_count": len(r["stops"])}
        for r in request.app.state.routes.values()
    ]


@router.get("/routes/{route_id}", response_model=RouteDetail, responses=_errors)
def route_detail(route_id: str, request: Request):
    route = request.app.state.routes.get(route_id)
    if route is None:
        raise ApiError(404, "route_not_found", "No route with that id.")
    stops = request.app.state.graph.stops
    features = [{
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": route["line"]},
        "properties": {"route_id": route_id, "color": route["color"], "direction": route["direction"]},
    }]
    for seq, sid in enumerate(route["stops"], start=1):
        s = stops[sid]
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [s.lng, s.lat]},
            "properties": {"name": s.name, "seq": seq},
        })
    return {"type": "FeatureCollection", "features": features}
