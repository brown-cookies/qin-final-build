from typing import List

from fastapi import APIRouter, Query

from app import queries
from app.schemas import ErrorResponse, ReportCreate, ReportOut

router = APIRouter(prefix="/api")

_errors = {
    422: {"model": ErrorResponse},
    503: {"model": ErrorResponse},
    500: {"model": ErrorResponse},
}


@router.post("/reports", response_model=ReportOut, status_code=201, responses=_errors)
def create_report(body: ReportCreate):
    return queries.insert_report(body.route_color, body.message, body.lat, body.lng)


@router.get("/reports", response_model=List[ReportOut], responses=_errors)
def recent_reports(limit: int = Query(10, ge=1, le=50)):
    return queries.list_reports(limit)
