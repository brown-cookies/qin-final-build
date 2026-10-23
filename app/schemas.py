"""Pydantic models, one per request/response."""
from datetime import datetime
from typing import Annotated, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.config import get_settings

RouteColor = Literal["yellow", "blue", "purple", "grey", "red", "darkyellow", "other"]


class ReportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route_color: RouteColor
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    lat: Optional[float] = Field(default=None, allow_inf_nan=False)
    lng: Optional[float] = Field(default=None, allow_inf_nan=False)

    @model_validator(mode="after")
    def _check(self) -> "ReportCreate":
        # Postgres text cannot hold NUL; reject here so it is a 422, not a 500.
        if "\x00" in self.message:
            raise ValueError("message must not contain NUL characters")
        if (self.lat is None) != (self.lng is None):
            raise ValueError("lat and lng must be given together or not at all")
        if self.lat is not None:
            lat_min, lat_max, lng_min, lng_max = get_settings().service_bbox
            if not (lat_min <= self.lat <= lat_max and lng_min <= self.lng <= lng_max):
                raise ValueError("lat/lng is outside the service area")
        return self


class ReportOut(BaseModel):
    report_id: UUID
    route_color: str
    message: str
    lat: Optional[float]
    lng: Optional[float]
    status: str
    created_at: datetime


class ErrorResponse(BaseModel):
    error: str
    message: str


class HealthResponse(BaseModel):
    status: Literal["ok"]
    database: Literal["up", "down"]
