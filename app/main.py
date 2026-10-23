import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import db, queries
from app.api import reports
from app.config import ConfigError, get_settings
from app.schemas import HealthResponse

log = logging.getLogger("biyahe")

# Codes for HTTP errors SPEC Section 12 does not list; chosen here, stable.
_HTTP_CODES = {404: "not_found", 405: "method_not_allowed"}


def error_response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": code, "message": message})


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO)
    try:
        settings = get_settings()
    except ConfigError as exc:
        log.error("Invalid configuration, exiting: %s", exc)
        raise SystemExit(1)
    try:
        db.init_pool(settings.database_url, settings.db_pool_timeout_s)
        queries.apply_schema()
    except db.DatabaseUnavailable as exc:
        log.error("Database unreachable at startup, exiting: %s", exc)
        db.close_pool()
        raise SystemExit(1)
    yield
    db.close_pool()


app = FastAPI(title="Biyahe Angeles", lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def _validation_error(request: Request, exc: RequestValidationError):
    parts = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"])
        msg = str(err["msg"]).removeprefix("Value error, ")
        parts.append(f"{loc}: {msg}" if loc else msg)
    return error_response(422, "validation_error", "; ".join(parts) or "Invalid request")


@app.exception_handler(StarletteHTTPException)
async def _http_error(request: Request, exc: StarletteHTTPException):
    code = _HTTP_CODES.get(exc.status_code, f"http_{exc.status_code}")
    return error_response(exc.status_code, code, str(exc.detail))


@app.exception_handler(db.DatabaseUnavailable)
async def _db_unavailable(request: Request, exc: db.DatabaseUnavailable):
    return error_response(503, "database_unavailable", "The database is temporarily unavailable. Try again shortly.")


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):
    log.error("Unhandled exception on %s %s", request.method, request.url.path, exc_info=exc)
    return error_response(500, "internal_error", "Something went wrong on our side.")


@app.get("/health", response_model=HealthResponse)
def health():
    try:
        queries.ping()
        database = "up"
    except db.DatabaseUnavailable:
        database = "down"
    return {"status": "ok", "database": database}


app.include_router(reports.router)
