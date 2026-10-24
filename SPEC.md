# Spec: Biyahe Angeles (MVP)

Working name. A web app that gives plain-language jeepney directions for Angeles City, using the six color-coded routes (yellow, blue, purple, grey, red, dark yellow; named in Section 7). This is a 3-day sprint spec, so every section is cut to the minimum that still satisfies the required build and the grading criteria. Anything not listed in Section 5 is cut (Section 15).

## Table of Contents

1. Purpose, Deliverable and Out of Scope
2. Architecture Overview
3. Stack Overview
4. Current State and 3-Day Plan
5. Functional Requirements
6. API Contracts (HTTP)
7. Data Contracts and Schemas
8. Database Schema
9. Route Data Pipeline
10. Configuration and Tunables
11. Measurement Requirements
12. Degraded and Error Conditions
13. Constraints, Conventions and Documentation Rules
14. Manual Verification Checklist and Traceability
15. Cut List and Open Items

## 1. Purpose, Deliverable and Out of Scope

**Purpose.** A commuter picks where they are and where they are going, and gets steps like "Walk to Dau Terminal, ride Yellow to Balibago Plaza, transfer to Red".

**Deliverable.** One repository, delivered as a pull request from a feature branch, containing:

- A FastAPI service with one POST endpoint that validates its input with Pydantic and writes to PostgreSQL (`POST /api/reports`), and one GET endpoint returning the most recent records (`GET /api/reports`).
- A trip planner (`GET /api/plan`) over the 9 route records (3 two-way colors x 2 directions, plus 3 one-way circular colors).
- A static map page served by the same service.
- A pytest suite that passes against a test database, a Dockerfile, a `docker-compose.yml` bringing up API and database, and a GitHub Actions workflow running the tests on every push.

**Out of scope** (see Section 15 for reasons): tricycles, buses, fares, real-time tracking, user accounts, PostGIS, Redis, a front-end framework, Tagalog UI, a moderation screen.

## 2. Architecture Overview

```
Browser (web/ static page, Leaflet map)
        |  HTTP/JSON
        v
FastAPI app
  api/      thin routers, no logic
  planner/  graph.py -> search.py -> steps.py   (pure Python, no DB calls)
  db.py     connection pool; queries.py = all hand-written SQL (no ORM)
        |                         ^
        v                         | loaded once at startup
PostgreSQL  (route, stop, route_stop, report)

Offline (not at runtime):  waypoints.csv -> snap_routes.py (OSRM)  ->  routes.geojson -> validate.py -> seed.py -> PostgreSQL   (Section 9)
```

Rules:

1. Routers only parse input, call `planner/` or `queries.py`, and shape the response. SQL lives only in `queries.py` and `sql/schema.sql`.
2. `planner/` never touches the database. It receives plain data, so it is testable without Postgres and the algorithm can be swapped in one folder.
3. The route graph is built **once at startup** and kept in memory (Section 11 measures this choice).
4. Route data is read-only at runtime. Only `report` rows are written by users, and a report never changes route data by itself; the maintainer applies fixes by hand.

## 3. Stack Overview

| Layer | Component | Why (defense line for DECISIONS.md) | Status |
|---|---|---|---|
| API | FastAPI + Pydantic | Required by the build; validation and `/docs` come free | Chosen |
| Database | PostgreSQL | Required by the build | Chosen |
| DB access | psycopg (v3) + hand-written SQL, no ORM | You see and control every query; schema is plain `CREATE TABLE`; parameterized queries only | Chosen |
| Planner | Dijkstra with `heapq` | Simple to explain and modify; costs allow a transfer penalty | Chosen |
| Map | Leaflet + OpenStreetMap tiles | No build step, free | Chosen |
| Tests | pytest | Required | Chosen |
| Packaging | Docker + Compose | Required | Chosen |
| CI | GitHub Actions with a Postgres service container | Required | Chosen |
| Route snapping | OSRM public server (offline script only) | Snaps hand-traced waypoints to real roads; never called at runtime. Replaces an OSM/Overpass route import, which was cut (Section 15) | Chosen |

Versions are pinned in `requirements.txt` and the Dockerfile, not duplicated here.

## 4. Current State and 3-Day Plan

Nothing is built. Route data does not exist anywhere and must be created (Section 9), so it is the critical path: **start on it on Day 1, in parallel with the code.**

| Day | Work | Done when |
|---|---|---|
| 1 | Repo skeleton, Docker/Compose, `sql/schema.sql`, `queries.py`, `/health`, reports POST/GET, tests, CI. Start dropping waypoints for the 9 routes (Section 9.2) | CI is green on a PR; waypoints started |
| 2 | `snap_routes.py`, `validate.py`, `seed.py`, routes/stops endpoints, planner and `/api/plan`, planner tests | All 9 routes have waypoints and validate; the 10 test trips (Section 11) run and results are recorded |
| 3 | Map page, docs (README, ARCHITECTURE, DECISIONS, data/README), final checklist, PR | Section 14 checklist passes |

If Day 2 slips, cut the map page's stop search first and keep map-tap only.

## 5. Functional Requirements

Each requirement is pass/fail against a running service.

- **FR-1 Plan a trip.** `GET /api/plan` takes two points and returns ordered steps. A route is found if one exists within the walk radius at both ends (Section 10).
- **FR-2 Readable steps.** Consecutive ride edges on the same route merge into one ride step. The response includes a one-line `summary` a non-technical user can read.
- **FR-3 Browse routes.** `GET /api/routes` lists the 9 route records; `GET /api/routes/{route_id}` returns the line and stops as GeoJSON.
- **FR-4 Stop search.** `GET /api/stops?q=` returns stops whose name contains `q`, case-insensitive, to fill the map page's pickers.
- **FR-5 Submit a report (required POST).** `POST /api/reports` validates input with Pydantic and writes one row to PostgreSQL.
- **FR-6 Recent reports (required GET).** `GET /api/reports?limit=` returns the most recent reports, newest first.
- **FR-7 Seed and validate data.** `seed.py` loads `routes.geojson` into PostgreSQL and is safe to re-run (it replaces route data, never touches `report`). `validate.py` fails on bad data and runs in CI.
- **FR-8 Map page.** A static page shows the six route lines in their colors, lets the user pick origin and destination (by tapping the map or searching a stop name), and shows the plan steps.
- **FR-9 Health.** `GET /health` returns `200` when the process is up, and reports whether the database is reachable.
- **FR-10 One error shape.** Every error response is `{"error": "<code>", "message": "<plain text>"}`, including validation errors.

Non-functional:

- **NFR-1** At least 8 of 10 real, known trips planned correctly (Section 11).
- **NFR-2** `docker compose up` starts API and database with no manual steps beyond a one-time seed command.
- **NFR-3** Every endpoint in this document appears in the README, and every tool in Section 3 has an entry in `DECISIONS.md`.
- **NFR-4** The page and README credit "(c) OpenStreetMap contributors".

## 6. API Contracts (HTTP)

Base path `/api`, except `/health`. Interactive docs are auto-generated at `/docs`.

### 6.1 `POST /api/reports` (FR-5)

```json
{
  "route_color": "yellow | blue | purple | grey | red | darkyellow | other",
  "message": "string, required, 1-500 chars",
  "lat": "number, optional, within service bounding box",
  "lng": "number, optional, within service bounding box"
}
```

`lat` and `lng` must be given together or not at all. They mark where the problem is on the map, not where the user is. Response `201 Created`:

```json
{
  "report_id": "uuid",
  "route_color": "yellow",
  "message": "string",
  "lat": 15.16,
  "lng": 120.59,
  "status": "new",
  "created_at": "ISO-8601 datetime"
}
```

Errors: `422` (`validation_error`) for an empty or over-long message, an unknown color, one of `lat`/`lng` missing, or coordinates outside the service area.

### 6.2 `GET /api/reports?limit=10` (FR-6)

Returns a JSON array of the shape above, newest first. `limit` is an integer from 1 to 50, default 10; out of range returns `422`.

### 6.3 `GET /api/plan?from_lat=&from_lng=&to_lat=&to_lng=` (FR-1, FR-2)

Response `200`:

```json
{
  "steps": [
    {"type": "walk", "from": "Your start point", "to": "Dau Terminal", "distance_m": 180},
    {"type": "ride", "color": "yellow", "direction": "out", "from": "Dau Terminal", "to": "Balibago Plaza", "stops_passed": 4, "distance_m": 3200},
    {"type": "transfer", "from": "Balibago Plaza", "to": "Balibago Plaza", "walk_m": 0, "to_color": "red"},
    {"type": "ride", "color": "red", "direction": "back", "from": "Balibago Plaza", "to": "SM Clark", "stops_passed": 3, "distance_m": 2100},
    {"type": "walk", "from": "SM Clark", "to": "Your destination", "distance_m": 90}
  ],
  "summary": "Walk to Dau Terminal, ride Yellow to Balibago Plaza, transfer to Red, get off at SM Clark, walk to your destination."
}
```

The example values are placeholders. Errors: see Section 12.

### 6.4 `GET /api/routes` and `GET /api/routes/{route_id}` (FR-3)

List item: `{"route_id": "yellow_out", "color": "yellow", "direction": "out", "name": "string", "stop_count": 12}`.

Detail: a GeoJSON FeatureCollection with one `LineString` feature (the route line) and one `Point` feature per stop in order (`properties`: `name`, `seq`). Unknown `route_id` returns `404` (`route_not_found`).

### 6.5 `GET /api/stops?q=` (FR-4)

Returns `[{"stop_id": "dau_terminal", "name": "Dau Terminal", "lat": 15.165, "lng": 120.597}]`, up to 10 matches. Empty `q` returns `422`.

### 6.6 `GET /health` (FR-9)

`200 {"status": "ok", "database": "up | down"}`. It returns `200` even when the database is down, so the process can be told apart from the database.

## 7. Data Contracts and Schemas

- **Route registry (the fixed set).** One color is exactly one named route. Yellow, Purple and Grey are one-way circular routes and have only `out`; Blue, Red and Dark yellow run in two directions:

  | Color | Token | Route name | `out` direction | Route IDs |
  |---|---|---|---|---|
  | Yellow | `yellow` | Villa - Pampang | Terminal, around the loop, to where the jeep ends (one-way circular; the name is only a label) | `yellow_out` |
  | Blue | `blue` | Pandan - Pampang | Pandan to Pampang | `blue_out`, `blue_back` |
  | Purple | `purple` | Checkpoint - Holy - Highway | Terminal, around the loop, to where the jeep ends (one-way circular) | `purple_out` |
  | Grey | `grey` | Checkpoint - Balibago - Highway | Terminal, around the loop, to where the jeep ends (one-way circular) | `grey_out` |
  | Red | `red` | Sapang Bato - Angeles | Sapang Bato to Angeles | `red_out`, `red_back` |
  | Dark yellow | `darkyellow` | Main Gate - Friendship | Main Gate to Friendship | `darkyellow_out`, `darkyellow_back` |

  `other` is accepted only in reports. Tokens are lowercase and never change.
- **Direction:** `out` is the route name read left to right (first place to last place); `back` is the reverse. The return trip is its own route record because its roads can differ. A one-way circular route (Yellow, Purple, Grey) has only `out`: its single line starts at the terminal and ends where the jeep ends, and it may pass the same real place twice. Both passes are `route_stop` rows with the same `stop_id` and different `seq` (the primary key is `(route_id, seq)`, so no schema change).
- **Named places become stops.** Every place in a route's name (for example Holy on Purple, Balibago on Grey) is a named stop on that route. Purple and Grey share the Checkpoint and Highway stops, and Yellow and Blue share Pampang, so those stops must use the same `stop_id` on every route they appear on; that is what creates transfers.
- **Map colors:** defined once in `web/map.js`. Yellow and dark yellow must be visibly different (for example `#FACC15` and `#B8860B`).
- **Route ID:** `{color}_{direction}`, for example `yellow_out`. Lowercase, permanent. Split on the last underscore to separate color and direction.
- **Stop ID:** lowercase slug of the stop name, for example `dau_terminal`. The same real place keeps the same ID on every route, which is what makes transfers work.
- **Coordinates:** WGS84, `lat` then `lng` in JSON bodies; GeoJSON uses `[lng, lat]` as the standard requires.
- **Pydantic models** live in `app/schemas.py`, one per request/response above. Unknown request fields are rejected.

## 8. Database Schema

PostgreSQL, defined in plain SQL in `sql/schema.sql` (`CREATE TABLE IF NOT EXISTS ...`) and applied at startup. There is no migration tool. To change the schema, drop the database volume and re-seed. The block below is the logical design; `schema.sql` is its exact form.

```
route
  route_id   text PK            -- 'yellow_out'
  color      text  not null     -- one of the six
  direction  text  not null     -- 'out' | 'back'
  name       text  not null     -- 'Villa - Pampang' (from the Section 7 registry)
  line       jsonb not null     -- [[lng,lat], ...] snapped road line
  source     text  not null     -- always 'memory-traced'
  verified_on date null
  osm_relation_id bigint null   -- always null (no OSM import)

stop
  stop_id    text PK
  name       text not null
  lat        double precision not null
  lng        double precision not null
  osm_node_id bigint null       -- always null (no OSM import)

route_stop
  route_id   text FK -> route
  seq        integer not null   -- starts at 1, no gaps
  stop_id    text FK -> stop
  PK (route_id, seq)

report
  report_id  uuid PK default gen_random_uuid()
  route_color text not null
  message    text not null
  lat        double precision null
  lng        double precision null
  status     text not null default 'new'   -- 'new' | 'seen' | 'fixed' (edited by maintainer in SQL)
  created_at timestamptz not null default now()
  INDEX (created_at DESC)
```

Relationships: a route has many `route_stop` rows; a stop appears on many routes. `report` stands alone and is the only table users write to.

## 9. Route Data Pipeline

Data is the project's hardest part, so it is a contract, not a side note. All 9 route records are **hand-traced from memory as waypoints** and snapped to roads by OSRM. There is no OSM route import (cut, Section 15): OSM coverage of Angeles jeepney routes was never confirmed, and a second source would need merge, override and precedence logic that 9 routes do not justify.

```
waypoints.csv  -> snap_routes.py (OSRM) -> routes.geojson (committed) -> validate.py -> seed.py -> PostgreSQL
```

### 9.1 Contract: the route Feature

`routes.geojson` is a GeoJSON FeatureCollection whose Features have this shape (one Feature per route record, 9 in the final file):

```json
{
  "type": "Feature",
  "geometry": {"type": "LineString", "coordinates": [[120.59, 15.16], [120.60, 15.17]]},
  "properties": {
    "route_id": "yellow_out",
    "color": "yellow",
    "direction": "out",
    "name": "Villa - Pampang",
    "source": "memory-traced",
    "verified_on": null,
    "osm_relation_id": null,
    "stops": [
      {"stop_id": "example_stop", "name": "Example Stop", "lat": 15.16, "lng": 120.59, "osm_node_id": null}
    ]
  }
}
```

Values above are placeholders. `source` is always `memory-traced`. `osm_relation_id` and `osm_node_id` are always `null`; the columns stay in `sql/schema.sql` so no schema change is needed, and they are the hook if an OSM import is added later. Stops are in route order. These properties map one to one onto the `route`, `stop` and `route_stop` columns in Section 8.

### 9.2 Input: hand-traced waypoints

1. **Input (human-made):** `data/raw/waypoints.csv`

   ```csv
   route_id,seq,name,lat,lng,is_stop
   yellow_out,1,Dau Terminal,15.1650,120.5970,1
   yellow_out,2,,15.1640,120.5920,0
   yellow_out,3,Balibago Plaza,15.1620,120.5860,1
   ```

   Rows with `is_stop=1` are named boarding places. Rows with `is_stop=0` are unnamed "via" points that force the snapped line onto the road the jeep really uses. The coordinates above are placeholders. Waypoints are dropped by hand in geojson.io (OpenStreetMap base map), from memory, then exported. `stop_id` is the lowercase slug of the stop name (Section 7), so the same place on two routes becomes one stop.
2. **Snap (offline, once per data change):** `data/snap_routes.py` sends each route's waypoints, in order, to the OSRM public server and writes `data/routes/routes.geojson` in the Section 9.1 format. It fails if any registry route ID (Section 7) has no waypoints. Runtime and CI never call OSRM. (OSRM itself runs on OSM road data, so the line follows real OSM roads.)

### 9.3 Validate, seed and provenance

1. **Validate:** `data/validate.py` fails the build if any of these hold:
   - a coordinate is outside the service bounding box;
   - `seq` has gaps or does not start at 1;
   - fewer than 2 stops on a route, or a route in the Section 7 registry that is missing (all 6 colors have `out`; only Blue, Red and Dark yellow also have `back`);
   - the same stop ID has coordinates more than 100 m apart on different routes (a likely naming collision);
   - a route line has a gap of more than 50 m between consecutive points (a bad snap);
   - a stop is more than 100 m from its own route line;
   - a Feature is missing any Section 9.1 property, or two Features share a `route_id`.

   Two different stop IDs closer than 30 m produce a warning, not a failure.
2. **Seed:** `data/seed.py` replaces `route`, `stop`, `route_stop` from `routes.geojson` in one transaction: `DELETE` from `route_stop`, then `route` and `stop`, then `INSERT` `stop`, `route`, `route_stop` (foreign-key order). It never touches `report`.
3. **Provenance:** `data/README.md` records the snap date and, per route, whether it was ridden or checked on the ground. Unverified routes are listed as known gaps.

Fixing a wrong line: add a via waypoint on the correct road and re-run snap. Then re-run validate and seed.

## 10. Configuration and Tunables

All are environment variables with defaults; none are hardcoded constants.

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | set in compose | Postgres connection |
| `SERVICE_BBOX` | `15.08,15.22,120.50,120.68` | lat_min, lat_max, lng_min, lng_max; requests outside are rejected. |
| `WALK_RADIUS_M` | 500 | Max walk from a point to a stop |
| `TRANSFER_RADIUS_M` | 100 | Stops within this distance count as one transfer point |
| `TRANSFER_PENALTY_KM` | 1.0 | Flat cost added each time you board a jeep |
| `WALK_COST_FACTOR` | 2.0 | Walking costs this many times riding, per km |

The two cost values are starting guesses. They are tuned once against the 10 test trips (Section 11) and the final values and the reason go into `DECISIONS.md`.

**Planner definition** (so it can be implemented and explained exactly):

- Nodes: `at(stop)` and `on(route, seq)`.
- Edges: `at -> on` boarding costs `TRANSFER_PENALTY_KM`; `on(seq) -> on(seq+1)` riding costs the straight-line distance between the two stops in km; `on -> at` alighting costs 0; `at -> at` walking between stops within `TRANSFER_RADIUS_M` costs distance in km x `WALK_COST_FACTOR`.
- Start and end: virtual nodes connected to every stop within `WALK_RADIUS_M`, with the same walking cost.
- Search: Dijkstra. The lowest-cost path is returned. Because every boarding costs a penalty, fewer jeeps are preferred without a separate "fewest transfers" search.
- Ride distance uses straight lines between stops, not the snapped line length. This is an accepted approximation for the MVP.

## 11. Measurement Requirements

No figures exist yet; these are targets, and results are written into `docs/DECISIONS.md` when measured.

| Metric | Target | How measured |
|---|---|---|
| Plan correctness | At least 8 of 10 | `tests/test_trips.py`: 10 trips you personally know, each with the expected colors in order |

If a target is missed, the real number is reported, not adjusted.

## 12. Degraded and Error Conditions

| Condition | Response |
|---|---|
| Coordinates missing, non-numeric, or outside `SERVICE_BBOX` on `/api/plan` | `400` `invalid_location` |
| No stop within `WALK_RADIUS_M` of the start or the end | `404` `no_stop_nearby` (message says which end) |
| Stops exist at both ends but no path connects them | `404` `no_route` |
| Request body or query fails validation | `422` `validation_error` |
| Unknown `route_id` | `404` `route_not_found` |
| Database unreachable on `/api/reports` | `503` `database_unavailable` |
| Database unreachable on `/api/plan`, `/api/routes`, `/api/stops` | **Still served** if the graph and route data were loaded at startup; this is the practical benefit of the in-memory graph |
| Database unreachable at startup | The process exits with a clear log line (fail fast); compose restarts it once the database is ready |
| Unhandled exception | `500` `internal_error`, details logged, never returned to the client |

Status rule: `4xx` means the caller's input is wrong; `5xx` means our fault.

## 13. Constraints, Conventions and Documentation Rules

- **Data boundary.** No accounts, no logins, no personal data. A report's optional pin marks a problem location, not the user. No third-party service is called at runtime other than loading OpenStreetMap map tiles in the browser.
- **Licensing.** OpenStreetMap data and tiles are ODbL / tile-policy bound: attribution on the page and in the README (NFR-4). Route line geometry in `routes.geojson` comes from OSRM, which runs on OSM road data; the README says so and links to the OSM copyright page. Stop positions are placed by hand. Read the ODbL terms on the OSM site before publishing the repository, since derived databases carry conditions. Google Maps is used only as a memory aid; no Google data is copied into the repository.
- **Secrets.** Credentials come from environment variables; nothing sensitive is committed.
- **SQL rules (no ORM).** Every query uses driver parameters (`%s` placeholders); user input is never formatted or concatenated into SQL text. The stop search passes `q` as a parameter (`name ILIKE '%' || %s || '%'`). Each multi-statement write (the seed) runs in one transaction. Reads in `queries.py` return plain dicts or tuples, and Pydantic models in `schemas.py` shape the API response.
- **Source of truth.** This file governs API shapes, schema and data format. If code and this spec disagree, one of them is a bug and the PR must fix it.
- **Folder layout** (one job per folder):

```
app/        main.py, config.py, db.py, queries.py, schemas.py
  api/      plan.py, routes.py, stops.py, reports.py
  planner/  graph.py, search.py, steps.py
sql/        schema.sql
web/        index.html, map.js, style.css
data/       raw/waypoints.csv, routes/routes.geojson,
            snap_routes.py, validate.py, seed.py, README.md
tests/      api/, planner/, data/, test_trips.py
docs/       README.md (or root), ARCHITECTURE.md, DECISIONS.md
Dockerfile, docker-compose.yml, requirements.txt, .github/workflows/ci.yml
```

- **Docs set.** `README.md` (what it is, one-command run, screenshot, endpoint table, OSM credit), `SPEC.md` (this file), `ARCHITECTURE.md` (the diagram in Section 2 plus the planner in Section 10), `DECISIONS.md` (per tool and per cut: what, why, rejected alternative, 3 lines each, plus measured results), `data/README.md`.
- **Docs stay consistent with code.** CI runs `validate.py` and the test suite; the README endpoint table is checked by hand against `/docs` in the final checklist.

## 14. Manual Verification Checklist and Traceability

1. Run `docker compose up`, then the seed command. `GET /health` returns `200` with `database: up`; the map page loads and shows six colored lines.
2. `POST /api/reports` with a valid body returns `201`; `GET /api/reports` lists it first.
3. `POST /api/reports` with an empty message, unknown color, only `lat`, or out-of-area coordinates returns `422` in the Section 12 error shape.
4. `GET /api/reports?limit=0` and `limit=51` both return `422`.
5. `GET /api/routes` returns 9 records; `GET /api/routes/yellow_out` returns a line plus at least 2 stops; an unknown ID returns `404`.
6. `GET /api/stops?q=` with a lowercase partial name returns matches; empty `q` returns `422`.
7. A known single-jeep trip returns one ride step; a known transfer trip returns ride, transfer, ride.
8. A point outside the service area returns `400`; a point far from any stop returns `404 no_stop_nearby`.
9. Stop the database container: `/api/plan` still returns `200`, `/api/reports` returns `503`, `/health` shows `database: down`.
10. Add a bad row to `waypoints.csv` (gap in `seq`) and run `validate.py`: it fails; CI would fail the build.
11. Push a deliberately failing test: CI fails. Fix it: CI passes.
12. Run `tests/test_trips.py`: at least 8 of 10 trips pass; failures are listed in the docs as known data gaps.
13. Compare README's endpoint table to `/docs`: every endpoint matches. Every Section 3 tool has a `DECISIONS.md` entry.
14. Run `snap_routes.py` then `validate.py`: `routes.geojson` holds all 9 route IDs, each with `source: "memory-traced"`, and validation passes. Remove one route's rows from `waypoints.csv` and re-run: `snap_routes.py` fails naming the missing ID.

| Requirement | Verified by |
|---|---|
| FR-1, FR-2 | 7, 12 |
| FR-3 | 5 |
| FR-4 | 6 |
| FR-5 | 2, 3 |
| FR-6 | 2, 4 |
| FR-7 | 1, 10, 14 |
| FR-8 | 1 |
| FR-9 | 1, 9 |
| FR-10 | 3, 8 |
| NFR-1 | 12 |
| NFR-2 | 1 |
| NFR-3 | 13 |
| NFR-4 | 1 (visual check) |

## 15. Cut List and Open Items

**Cut for the 3-day sprint** (each gets a one-line reason in `DECISIONS.md`):

| Cut | Reason |
|---|---|
| PostGIS | Plain latitude/longitude and a small distance function are enough for 9 routes; one less extension to run and explain |
| Redis / response caching | The in-memory graph already removes the slow part; add only if a measured need appears |
| React / front-end build step | A static page with Leaflet is easier to modify and defend |
| Accounts, login, rate limiting | No personal data to protect; reports cannot change route data |
| Fares, tricycles, buses, real-time | No reliable data |
| "Use my location" button, landmark search beyond stop names | Map tap and stop-name search cover the use case |
| Report moderation screen | Maintainer edits `status` in SQL |
| Alembic migrations | Drop the volume and re-seed |
| Self-hosted OSRM | The public server is used once, offline |
| Tagalog labels | English first |
| OSM/Overpass route import (`fetch_osm.py`, `build_routes.py`, overrides, `prefer_traced.txt`) | OSM coverage was never confirmed; a second source needs merge and precedence logic that 9 routes do not justify. All 9 are traced; the `osm_*` columns stay null |

**Decisions assumed (change before Day 1 if wrong):**

1. **Confirmed:** each color is exactly one named route; Yellow, Purple and Grey are one-way circular (`out` only); Blue, Red and Dark yellow run in two directions (Section 7 registry). Nothing is assumed about variants; if you later find one, give it its own `route_id` and add it to the registry.
2. The map page is in scope.
3. English only.
4. Reports are public immediately.

**Open items:**

- `TRANSFER_PENALTY_KM` and `WALK_COST_FACTOR` final values: set after the first run of the 10 test trips.
- Exact pin for each named place in the Section 7 registry (Villa, Pampang, Pandan, Checkpoint, Holy, Highway, Balibago, Sapang Bato, Angeles, Main Gate, Friendship): decide the real boarding spot for each and write it in `data/README.md`. "Highway" and "Angeles" are broad names, so pick the actual terminal or main stop you mean.
- The 10 test trips and their expected colors: write them before building the planner, so the planner is tuned against a fixed list.