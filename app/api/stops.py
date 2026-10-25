from typing import Annotated, List

from fastapi import APIRouter, Query, Request
from pydantic import StringConstraints

from app import db, queries
from app.schemas import ErrorResponse, StopOut

router = APIRouter(prefix="/api")

_LIMIT = 10
_errors = {422: {"model": ErrorResponse}, 500: {"model": ErrorResponse}}

Q = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


@router.get("/stops", response_model=List[StopOut], responses=_errors)
def search_stops(request: Request, q: Annotated[Q, Query(pattern=r"^[^\x00]*$")]):
    try:
        return queries.search_stops(q, _LIMIT)
    except db.DatabaseUnavailable:
        # SPEC 12: keep serving from startup data; same semantics as the SQL.
        needle = q.lower()
        hits = [s for s in request.app.state.stops if needle in s["name"].lower()]
        hits.sort(key=lambda s: (s["name"], s["stop_id"]))
        return hits[:_LIMIT]
