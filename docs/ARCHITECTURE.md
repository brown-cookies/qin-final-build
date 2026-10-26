# Architecture

`SPEC.md` is the source of truth for API shapes, schema and data format. This file explains how the pieces fit and why they are split this way. Decisions and rejected alternatives are in [DECISIONS.md](DECISIONS.md).

## Runtime

```
Browser (web/: index.html, map.js, style.css, vendored Leaflet)
        |  HTTP/JSON            (OSM tiles load straight from the browser, not through us)
        v
FastAPI app  (app/main.py: error handlers, lifespan, static mount)
  api/      thin routers: parse input, call planner/ or queries.py, shape the response
  planner/  graph.py -> search.py -> steps.py   (plain Python, no DB, no config imports)
  db.py     psycopg connection pool (no SQL)
  queries.py  every hand-written SQL statement (with sql/schema.sql)
        |                              ^
        v                              | read once at startup
PostgreSQL  (route, stop, route_stop, report)
```

One process, one container. Postgres is the only other runtime dependency.

### Startup (`app/main.py`, `lifespan`)

1. Read settings from env (`app/config.py`). Invalid value: log `Invalid configuration, exiting` and exit 1.
2. Open the pool and wait for a first connection. Unreachable: log `Database unreachable at startup, exiting` and exit 1. Compose restarts the container until Postgres is ready.
3. Apply `sql/schema.sql` (`CREATE TABLE IF NOT EXISTS`, idempotent).
4. `load_route_data` reads `route`, `stop`, `route_stop` once, derives which routes are circular (`mark_circular`), builds the `Graph`, and keeps routes, stops and graph on `app.state`. Zero routes logs a WARNING (see "Degraded modes").

Route data is never reloaded at runtime. After a re-seed, restart the API (`docker compose restart api`).

### Request paths

| Endpoint | Served from | If the DB is down |
|---|---|---|
| `GET /api/plan` | `app.state` graph | still works |
| `GET /api/routes`, `/api/routes/{id}` | `app.state.routes` | still works |
| `GET /api/stops` | SQL `ILIKE`; falls back to `app.state.stops` with the same semantics | still works |
| `POST /api/reports`, `GET /api/reports` | SQL | `503 database_unavailable` |
| `GET /health` | `SELECT 1` for `database`; startup data for `route_data` | `200`, `database: down` |
| `/` and other static files | `web/` via `StaticFiles`, mounted last so it never shadows `/health`, `/docs` or `/api/*` | still works |

### Errors

Every error is `{"error": "<code>", "message": "<plain text>"}`. `main.py` registers handlers for `RequestValidationError` (422 `validation_error`), `ApiError` (the router's own code and status), Starlette `HTTPException` (`not_found`, `method_not_allowed`, `http_<n>`), `DatabaseUnavailable` (503) and a catch-all (500 `internal_error`; details are logged, never returned). Codes and statuses: SPEC Section 12.

## Planner

Pure functions over plain data (`app/planner/`). Inputs are a `{stop_id: Stop}` map, a routes dict (`color`, `direction`, ordered `stops`, `circular`) and four numbers from config. Nothing in the package imports `app.db`, `app.queries` or `app.config`, so `tests/planner/` and `tests/test_trips.py` run without Postgres.

**Nodes.** `("at", stop_id)` is a person standing at a stop. `("on", route_id, i)` is a person sitting on a jeep at position `i` (0-based) of that route.

**Edges** (`graph.py`; costs in km-equivalents):

| Edge | Cost |
|---|---|
| `at(stop) -> on(route, i)` board | `TRANSFER_PENALTY_KM` (flat, every boarding) |
| `on(route, i) -> on(route, i+1)` ride | straight-line km between the two stops |
| `on(route, i) -> at(stop)` alight | 0 |
| `at(a) -> at(b)` walk, only if within `TRANSFER_RADIUS_M` | km x `WALK_COST_FACTOR` |
| `on(route, last) -> on(route, 0)` wrap, circular routes only | straight-line km from last stop to first |

A route is circular when its color has an `out` record and no `back` record (Yellow, Purple, Grey). That is derived at startup from the registry data, not stored.

**Query** (`search.py`, `find_path`). The start and end points are synthetic nodes handled inside the search: `START` links to every stop within `WALK_RADIUS_M`, and each such stop links to `END` at walking cost. They are never added to the shared graph, because requests run in threads and mutating shared adjacency lists would corrupt other queries. Dijkstra with `heapq` returns the lowest-cost node path. A stop reached by a walk edge is tagged `("wk", id)` and may only board or finish, so walks cannot chain past `TRANSFER_RADIUS_M`.

**Steps** (`steps.py`, `build_steps`). The node path becomes `walk`, `ride` and `transfer` steps: consecutive ride edges on one route merge into one `ride` (with `stops_passed` and summed distance), a board after an alight becomes a `transfer` (with the walk between the two stops), and the first and last `walk` steps are measured from and to the user's actual points. `build_summary` writes the one-line text.

**What the cost model means.** Because every boarding costs a flat penalty, fewer jeeps are preferred without a separate "fewest transfers" search. Walking is twice as expensive per km as riding. Both values are starting guesses and were not tuned (DECISIONS.md, "The 10 test trips").

### Properties to keep in mind

- Ride distance is the straight line between consecutive stops, not the length of the snapped road line. It under-reports on winding stretches and is used both for cost and for the `distance_m` shown to the user.
- The planner does not know which stops a jeep will actually pick up at (a full jeep, a terminal-only boarding point). It treats every stop of every route as boardable.
- A route that passes the same place twice (circular) has two `on` nodes for the same `stop_id`. That needs no special case in the graph.
- Total walking at either end can exceed `WALK_RADIUS_M`: the radius limits the walk to the first or last *stop*, and a transfer-radius walk of up to `TRANSFER_RADIUS_M` between two stops at the same place is folded into the same step. Measured: single walk steps up to 590 m with the defaults.

## Data and schema

```
data/raw/waypoints.csv -> data/snap_routes.py (OSRM, offline) -> data/routes/routes.geojson (committed)
                       -> data/validate.py (CI, no DB) -> data/seed.py -> PostgreSQL (route, stop, route_stop)
```

- `snap_routes.py` is the only step that uses the network, and it is never run by CI or at runtime. It snaps each route's waypoints to roads, densifies lines to at most 40 m between points, fails if any registry route has no waypoints, and fails if any waypoint is over 50 m from its snapped line.
- `validate.py` checks `routes.geojson` against SPEC 9.3 using the standard library only. One line per problem, exit 1 on failure; `WARNING` lines (stops under 30 m apart) do not fail.
- `seed.py` validates first, applies the schema, then `queries.replace_route_data` deletes and re-inserts `route_stop`, `route`, `stop` in one transaction. `report` is never touched, so the seed is safe to re-run and a failure rolls back to the old data.

Tables (`sql/schema.sql`, exact DDL): `route` (line as `jsonb` `[[lng, lat], ...]`), `stop`, `route_stop` (`(route_id, seq)` primary key, `seq` 1-based), and `report` (the only user-written table, no foreign keys to the others). There are no migrations: change the file, drop the volume, re-seed.

## Front end (`web/`)

A single static page, no build step. Leaflet is vendored in `web/` so the page loads no script from a CDN. `map.js` loads `/api/routes` and one `/api/routes/{id}` per route, draws the six colors (the only place colors are defined) and a stop dot per stop, and keeps a per-route record with the line projected into map space. The user taps the map (or a stop dot) twice to set origin and destination; **Find route** calls `/api/plan`, lists the steps, and highlights each ride by matching the step's `from`/`to` stop names back to the route record and cutting the line between them. Errors from the API map to short messages in a banner or panel. The page only reads; it has no report form.

## Packaging and CI

- `Dockerfile`: `python:3.12.12-slim-bookworm`, pinned `requirements.txt`, non-root user, `uvicorn` on 8000.
- `docker-compose.yml`: `db` (`postgres:16.13-alpine`, healthcheck, named volume `pgdata`) and `api` (waits for `db` healthy, `restart: unless-stopped`, healthcheck on `/health`). Host ports follow `API_PORT` / `POSTGRES_PORT`; Postgres is bound to `127.0.0.1` only.
- `.github/workflows/ci.yml`: Postgres 16 service container, `pip install`, `pytest`, `python data/validate.py`, on every push and pull request.

## Degraded modes

| Situation | Behaviour |
|---|---|
| DB unreachable at startup | Exit 1 with one clear log line; compose restarts |
| DB drops while running | Plan, routes, stops and the static page keep working; reports return `503`; `/health` reports `database: down` |
| API started before the seed | `/health` shows `route_data: empty`, `/api/plan` returns `503 route_data_unavailable`, `/api/routes` returns `[]`, a WARNING is logged at startup. Restart the API after seeding |
| Invalid env value | Exit 1 with `Invalid configuration` |
| Unhandled exception | `500 internal_error`, details only in the log |
