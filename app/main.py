import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import db, queries
from app.api import ApiError, plan, reports, routes, stops
from app.config import ConfigError, get_settings
from app.planner.graph import Graph, Stop, mark_circular
from app.schemas import HealthResponse

log = logging.getLogger("biyahe")

# Codes for HTTP errors SPEC Section 12 does not list; chosen here, stable.
_HTTP_CODES = {404: "not_found", 405: "method_not_allowed"}


def error_response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": code, "message": message})


def load_route_data(app: FastAPI) -> None:
    """Read route data once and keep it, with the graph, on app.state (no runtime reload)."""
    settings = get_settings()
    route_rows, stop_rows, route_stop_rows = queries.load_route_data()
    stop_map = {r["stop_id"]: Stop(r["stop_id"], r["name"], r["lat"], r["lng"]) for r in stop_rows}
    routes = {
        r["route_id"]: {
            "route_id": r["route_id"], "color": r["color"], "direction": r["direction"],
            "name": r["name"], "line": r["line"], "stops": [],
        }
        for r in route_rows
    }
    for rs in route_stop_rows:  # already ordered by route_id, seq
        routes[rs["route_id"]]["stops"].append(rs["stop_id"])
    mark_circular(routes)
    app.state.graph = Graph(
        stop_map, routes, settings.walk_radius_m, settings.transfer_radius_m,
        settings.transfer_penalty_km, settings.walk_cost_factor,
    )
    app.state.routes = routes
    app.state.stops = [r for r in stop_rows]
    log.info("Loaded %d routes and %d stops", len(routes), len(stop_map))
    if not routes:
        log.warning("Started with no route data: run the seed command, then restart the api "
                    "(docker compose restart api); route data is loaded only at startup")


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
        load_route_data(app)
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


@app.exception_handler(ApiError)
async def _api_error(request: Request, exc: ApiError):
    return error_response(exc.status, exc.code, exc.message)


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
    # From startup data only, so it stays correct while the database is down.
    route_data = "loaded" if app.state.routes else "empty"
    return {"status": "ok", "database": database, "route_data": route_data}


app.include_router(plan.router)
app.include_router(routes.router)
app.include_router(stops.router)
app.include_router(reports.router)

# Mounted last so it never shadows /health, /docs or /api/*.
app.mount("/", StaticFiles(directory=Path(__file__).parent.parent / "web", html=True), name="web")
