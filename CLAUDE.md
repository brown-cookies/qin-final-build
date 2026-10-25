# CLAUDE.md

Guidance for Claude Code in this repo. `SPEC.md` is the source of truth for API shapes, schema and data format. If code and spec disagree, one is a bug: fix it in the same PR. Do not silently drift from the spec.

## What this is

Biyahe Angeles (working name): plain-language jeepney directions for Angeles City over six color-coded routes (yellow, blue, purple, grey, red, darkyellow), 9 route records (yellow, purple, grey: one-way circular, `out` only; blue, red, darkyellow: `out`/`back`). 3-day sprint MVP. Anything not in SPEC Section 5 is cut (Section 15). Do not add cut items (PostGIS, Redis, ORM, front-end framework, accounts, Tagalog UI, moderation screen, Alembic, self-hosted OSRM).

Day-by-day plan: `roadmap.md`. Open items: `docs/OPEN_ITEMS.md`.

## Stack

FastAPI + Pydantic, PostgreSQL, psycopg v3 with hand-written SQL (no ORM), Dijkstra via `heapq`, Leaflet + OSM tiles (no build step), pytest, Docker + Compose, GitHub Actions with a Postgres service container. Pin versions in `requirements.txt` and the Dockerfile only.

## Layout

```
app/        main.py, config.py, db.py, queries.py, schemas.py
  api/      plan.py, routes.py, stops.py, reports.py
  planner/  graph.py, search.py, steps.py
sql/        schema.sql
web/        index.html, map.js, style.css
data/       raw/waypoints.csv, routes/routes.geojson,
            snap_routes.py, validate.py, seed.py, README.md
tests/      api/, planner/, data/, test_trips.py
docs/       ARCHITECTURE.md, DECISIONS.md, OPEN_ITEMS.md
```

## Hard rules

1. **Routers are thin.** `app/api/*` only parse input, call `planner/` or `queries.py`, shape the response. No logic.
2. **SQL only in `app/queries.py` and `sql/schema.sql`.** Always driver parameters (`%s`). Never format or concatenate user input into SQL. Stop search: `name ILIKE '%' || %s || '%'`. Multi-statement writes (seed) run in one transaction.
3. **`planner/` never touches the DB.** It takes plain data. Graph is built once at startup and kept in memory.
4. **Route data is read-only at runtime.** Only `report` rows are user-written. `seed.py` replaces `route`/`stop`/`route_stop`, never `report`, and is re-runnable.
5. **One error shape everywhere**, including validation errors: `{"error": "<code>", "message": "<plain text>"}`. Codes and statuses are in SPEC Section 12. 4xx = caller's fault, 5xx = ours. Unhandled exceptions: `500 internal_error`, log details, never return them.
6. **Pydantic models live in `app/schemas.py`**, one per request/response. Reject unknown request fields.
7. **Config via env vars with defaults** (SPEC Section 10). No hardcoded tunables. No secrets committed.
8. **Runtime calls no third-party service** except the browser loading OSM tiles. OSRM is an offline script only; CI never calls it.
9. **No migrations.** Schema change = edit `sql/schema.sql`, drop the volume, re-seed.

## Easy-to-get-wrong details

- Coordinate order: JSON bodies use `lat` then `lng`; GeoJSON uses `[lng, lat]`.
- `SERVICE_BBOX` is `lat_min,lat_max,lng_min,lng_max`.
- Route ID is `{color}_{direction}`, lowercase, permanent. Split on the **last** underscore (`darkyellow_out` -> `darkyellow`, `out`).
- Same real place = same `stop_id` on every route (lowercase slug of name). That is what creates transfers. Purple/Grey share Checkpoint and Highway; Yellow/Blue share Pampang.
- `/health` returns `200` even when the DB is down (`database: down`). `/api/plan`, `/api/routes`, `/api/stops` keep working from startup data if the DB drops; `/api/reports` returns `503 database_unavailable`. DB down at startup: exit with a clear log line.
- `lat`/`lng` in a report come together or not at all, and mark the problem location, not the user.
- Ride distance in the planner is straight-line between stops (accepted MVP approximation).
- Report `status` is `new|seen|fixed`; maintainer edits it in SQL.

## Data pipeline

```
waypoints.csv -> snap_routes.py (OSRM) -> routes.geojson (committed) -> validate.py -> seed.py
```

- All 9 routes are hand-traced from memory as waypoints; there is no OSM route import. `snap_routes.py` fails if any registry route ID has no waypoints.
- `validate.py` runs in CI. Failures are in SPEC Section 9.3 (bbox, seq gaps, <2 stops, stop-ID collisions >100 m, line gaps >50 m, stop >100 m from line, missing properties, duplicate IDs).
- `routes.geojson` is a snapshot; its line geometry comes from OSRM, which runs on OSM road data (ODbL). Record the snap date and per-route provenance in `data/README.md`. Credit "(c) OpenStreetMap contributors" on the page and in the README.

## Commands

Keep this block accurate.

```
docker compose up                      # API (:8000) + Postgres; schema applied at startup
                                       # host ports: API_PORT / POSTGRES_PORT override 8000 / 5432
# seed: Day 2, not yet available (will be: docker compose run --rm api python -m data.seed)
pytest                                 # needs a Postgres test DB: TEST_DATABASE_URL, db name must end in _test
                                       # (default postgresql://biyahe:biyahe@localhost:5432/biyahe_test; created if
                                       # missing; `docker compose up db` provides the server)
python data/validate.py                # Day 1 stub (exits 0); real checks Day 2; also runs in CI
```

## Working conventions

- Work on a feature branch; deliver as one PR. CI (tests + `validate.py`) must be green.
- Match surrounding code style. Keep comments sparse and explain why, not what.
- Docs set: `README.md`, `SPEC.md`, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md` (per tool and per cut: what, why, rejected alternative, 3 lines; plus measured results), `data/README.md`. Every SPEC Section 3 tool needs a `DECISIONS.md` entry; every endpoint needs a README row (NFR-3).
- Report measured numbers as measured, with hardware stated. Do not adjust a missed target.
- Done = SPEC Section 14 checklist passes. Check items against a running service, not just tests.
