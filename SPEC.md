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
11. Performance and Measurement Requirements
12. Degraded and Error Conditions
13. Constraints, Conventions and Documentation Rules
14. Manual Verification Checklist and Traceability
15. Cut List and Open Items

## 1. Purpose, Deliverable and Out of Scope

**Purpose.** A commuter picks where they are and where they are going, and gets steps like "Walk to Dau Terminal, ride Yellow to Balibago Plaza, transfer to Red".

**Deliverable.** One repository, delivered as a pull request from a feature branch, containing:

- A FastAPI service with one POST endpoint that validates its input with Pydantic and writes to PostgreSQL (`POST /api/reports`), and one GET endpoint returning the most recent records (`GET /api/reports`).
- A trip planner (`GET /api/plan`) over the 12 route records (6 colors x 2 directions).
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

Offline (not at runtime):  OSM (Overpass) -> fetch_osm.py, or waypoints.csv -> snap_routes.py (OSRM)  ->  build_routes.py -> routes.geojson -> seed.py -> PostgreSQL   (Section 9)
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
| Route data (source A) | OpenStreetMap via the Overpass API (offline script only) | Existing jeepney route relations are imported first, so less has to be traced by hand | Chosen |
| Route snapping (source B) | OSRM public server (offline script only) | Snaps hand-traced waypoints to real roads; never called at runtime | Chosen |

Versions are pinned in `requirements.txt` and the Dockerfile, not duplicated here.

## 4. Current State and 3-Day Plan

Nothing is built. Route data does not exist anywhere and must be created (Section 9), so it is the critical path: **start on it on Day 1, in parallel with the code.**

| Day | Work | Done when |
|---|---|---|
| 1 | Repo skeleton, Docker/Compose, `sql/schema.sql`, `queries.py`, `/health`, reports POST/GET, tests, CI. Check OSM coverage with Overpass Turbo (Section 9.2), then hand-trace only the routes OSM lacks | CI is green on a PR; every one of the 12 route records is either found in OSM or has waypoints |
| 2 | `fetch_osm.py`, `snap_routes.py`, `build_routes.py`, `validate.py`, `seed.py`, routes/stops endpoints, planner and `/api/plan`, planner tests | The 10 test trips (Section 11) run and results are recorded |
| 3 | Map page, benchmark script, docs (README, ARCHITECTURE, DECISIONS, data/README), final checklist, PR | Section 14 checklist passes |

If Day 2 slips, cut the map page's stop search first and keep map-tap only.

## 5. Functional Requirements

Each requirement is pass/fail against a running service.

- **FR-1 Plan a trip.** `GET /api/plan` takes two points and returns ordered steps. A route is found if one exists within the walk radius at both ends (Section 10).
- **FR-2 Readable steps.** Consecutive ride edges on the same route merge into one ride step. The response includes a one-line `summary` a non-technical user can read.
- **FR-3 Browse routes.** `GET /api/routes` lists the 12 route records; `GET /api/routes/{route_id}` returns the line and stops as GeoJSON.
- **FR-4 Stop search.** `GET /api/stops?q=` returns stops whose name contains `q`, case-insensitive, to fill the map page's pickers.
- **FR-5 Submit a report (required POST).** `POST /api/reports` validates input with Pydantic and writes one row to PostgreSQL.
- **FR-6 Recent reports (required GET).** `GET /api/reports?limit=` returns the most recent reports, newest first.
- **FR-7 Seed and validate data.** `seed.py` loads `routes.geojson` into PostgreSQL and is safe to re-run (it replaces route data, never touches `report`). `validate.py` fails on bad data and runs in CI.
- **FR-8 Map page.** A static page shows the six route lines in their colors, lets the user pick origin and destination (by tapping the map or searching a stop name), and shows the plan steps.
- **FR-9 Health.** `GET /health` returns `200` when the process is up, and reports whether the database is reachable.
- **FR-10 One error shape.** Every error response is `{"error": "<code>", "message": "<plain text>"}`, including validation errors.

Non-functional:

- **NFR-1** `/api/plan` p95 latency under 200 ms on the warm in-memory graph (Section 11).
- **NFR-2** At least 8 of 10 real, known trips planned correctly (Section 11).
- **NFR-3** `docker compose up` starts API and database with no manual steps beyond a one-time seed command.
- **NFR-4** Every endpoint in this document appears in the README, and every tool in Section 3 has an entry in `DECISIONS.md`.
- **NFR-5** The page and README credit "(c) OpenStreetMap contributors".

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

- **Route registry (the fixed set).** One color is exactly one named route, run in two directions:

  | Color | Token | Route name | `out` direction | Route IDs |
  |---|---|---|---|---|
  | Yellow | `yellow` | Villa - Pampang | Villa to Pampang | `yellow_out`, `yellow_back` |
  | Blue | `blue` | Pandan - Pampang | Pandan to Pampang | `blue_out`, `blue_back` |
  | Purple | `purple` | Checkpoint - Holy - Highway | Checkpoint to Highway | `purple_out`, `purple_back` |
  | Grey | `grey` | Checkpoint - Balibago - Highway | Checkpoint to Highway | `grey_out`, `grey_back` |
  | Red | `red` | Sapang Bato - Angeles | Sapang Bato to Angeles | `red_out`, `red_back` |
  | Dark yellow | `darkyellow` | Main Gate - Friendship | Main Gate to Friendship | `darkyellow_out`, `darkyellow_back` |

  `other` is accepted only in reports. Tokens are lowercase and never change.
- **Direction:** `out` is the route name read left to right (first place to last place); `back` is the reverse. The return trip is its own route record because its roads can differ.
- **Named places become stops.** Every place in a route's name (for example Holy on Purple, Balibago on Grey) is a named stop on that route. Purple and Grey share the Checkpoint and Highway ends, and Yellow and Blue share Pampang, so those stops must use the same `stop_id` on every route they appear on; that is what creates transfers.
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
  source     text  not null     -- 'osm' | 'memory-traced'
  verified_on date null
  osm_relation_id bigint null   -- set only when source = 'osm'

stop
  stop_id    text PK
  name       text not null
  lat        double precision not null
  lng        double precision not null
  osm_node_id bigint null       -- set only for stops taken from OSM

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

Data is the project's hardest part, so it is a contract, not a side note. Route data has two possible sources, **OpenStreetMap (OSM)** and **hand-traced waypoints**. Both are converted into the same intermediate format, so validate, seed and the planner never care where a route came from.

```
OSM (Overpass) -> fetch_osm.py     -> from_osm.geojson    \
                                                            -> build_routes.py -> routes.geojson -> validate.py -> seed.py -> PostgreSQL
waypoints.csv  -> snap_routes.py   -> from_traced.geojson /
```

### 9.1 Contract: the route Feature

`from_osm.geojson`, `from_traced.geojson` and `routes.geojson` are all GeoJSON FeatureCollections whose Features have this shape (one Feature per route record, 12 in the final file):

```json
{
  "type": "Feature",
  "geometry": {"type": "LineString", "coordinates": [[120.59, 15.16], [120.60, 15.17]]},
  "properties": {
    "route_id": "yellow_out",
    "color": "yellow",
    "direction": "out",
    "name": "Villa - Pampang",
    "source": "osm",
    "verified_on": null,
    "osm_relation_id": 0,
    "stops": [
      {"stop_id": "example_stop", "name": "Example Stop", "lat": 15.16, "lng": 120.59, "osm_node_id": 0}
    ]
  }
}
```

Values above are placeholders. `source` is `osm` or `memory-traced`. `osm_relation_id` and `osm_node_id` are `null` for traced data. Stops are in route order. These properties map one to one onto the `route`, `stop` and `route_stop` columns in Section 8.

### 9.2 Source A: OpenStreetMap (try this first)

**What OSM data looks like.** The OSM wiki's Philippines page says jeepney routes use `type=route` with `route=bus` (that value covers buses, jeepneys, multicabs and UV Express). Recommended tags are `name` ("A-B"), `ref`, `colour`, `from`, `to`, `via` and `network`. Stops are `highway=bus_stop` or `public_transport=platform` nodes with `share_taxi=yes` for jeepneys, and stop positions are `public_transport=stop_position` nodes. The general Public Transport v2 pattern for a route relation is one relation per direction, with members ordered as stop, platform, stop, platform from first to last stop, followed by the road ways with empty roles. A `route_master` relation, when present, groups the two directions. This is a convention, not a guarantee on every relation, so OSM data is checked (Section 9.4), never trusted blindly. It is not yet known which of the six Angeles routes exist in OSM; Day 1 finds out.

**Steps**

1. **Query Overpass.** Use Overpass Turbo for a first look, then `data/fetch_osm.py` for the repeatable version. The bounding box is the service area in Overpass order (south, west, north, east); this is a different order from `SERVICE_BBOX` in Section 10:

   ```
   [out:json][timeout:60];
   relation["type"="route"]["route"~"^(bus|share_taxi|minibus)$"](15.08,120.50,15.22,120.68);
   out geom;
   ```

2. **Match each relation to a registry route** (Section 7). Normalize the relation's `name` (lowercase; hyphen, en dash and em dash all become `-`; collapse spaces) and compare it with the registry names. `data/osm_overrides.csv` (`relation_id,route_id`) always wins and is how you pair relations whose names differ or are missing.
3. **Convert using this mapping:**

   | Spec field | OSM source | Rule |
   |---|---|---|
   | `route_id`, `color` | registry + overrides | Color comes from the registry. If the relation has a `colour` tag that disagrees, print a warning; the registry wins |
   | `direction` | relation `from` and `to` | `from` equals the registry's first place: `out`; otherwise `back`. If `from` is missing, the override file states the direction |
   | `line` | member ways (empty role), in relation order | Stitch end to end, flipping a way when needed. Ways marked `hail_and_ride` count as ordinary ways. If two consecutive ways are more than 50 m apart the line is broken, and the route fails validation |
   | `stops` | members with role `stop` or `platform` | A `stop` followed by its `platform` is one stop; use the platform's name and position, else the stop position's. Stops with no `name` are dropped with a warning |
   | `stop_id` | slug of the stop name | Same rule as Section 7: the same name on two routes is one stop |
   | `osm_relation_id`, `osm_node_id` | element ids | Kept for traceability |
   | `source` | none | Always `osm` |

4. **Coverage report.** `fetch_osm.py` prints one line per registry route record (12): found or missing, stop count, line connected yes or no. Missing or broken routes go to Source B. It writes the converted routes to `data/routes/from_osm.geojson`.
5. **Snapshot.** OSM changes over time. `routes.geojson` is a snapshot, and the fetch date is recorded in `data/README.md`.

Conventions above follow the OSM wiki pages "Philippines/Public transportation" and "Tag:route=bus".

### 9.3 Source B: hand-traced waypoints (for routes OSM lacks or has broken)

1. **Input (human-made):** `data/raw/waypoints.csv`

   ```csv
   route_id,seq,name,lat,lng,is_stop
   yellow_out,1,Dau Terminal,15.1650,120.5970,1
   yellow_out,2,,15.1640,120.5920,0
   yellow_out,3,Balibago Plaza,15.1620,120.5860,1
   ```

   Rows with `is_stop=1` are named boarding places. Rows with `is_stop=0` are unnamed "via" points that force the snapped line onto the road the jeep really uses. The coordinates above are placeholders. Waypoints are dropped by hand in geojson.io (OpenStreetMap base map), from memory, then exported.
2. **Snap (offline, once per data change):** `data/snap_routes.py` sends each route's waypoints, in order, to the OSRM public server and writes `data/routes/from_traced.geojson` in the Section 9.1 format with `source: "memory-traced"`. Runtime and CI never call OSRM. (OSRM itself runs on OSM road data, so a traced line follows real OSM roads.)

### 9.4 Build, validate, seed and provenance

1. **Build:** `data/build_routes.py` writes `data/routes/routes.geojson` (committed). For each of the 12 route IDs it uses the OSM version if it exists and passes validation, otherwise the traced version. A route ID listed in `data/prefer_traced.txt` (one ID per line) always uses the traced version. The build fails if any of the 12 is missing from both sources.
2. **Validate:** `data/validate.py` fails the build if any of these hold:
   - a coordinate is outside the service bounding box;
   - `seq` has gaps or does not start at 1;
   - fewer than 2 stops on a route, or a route missing for any of the 6 colors x 2 directions;
   - the same stop ID has coordinates more than 100 m apart on different routes (a likely naming collision);
   - a route line has a gap of more than 50 m between consecutive points (a broken OSM stitch);
   - a stop is more than 100 m from its own route line;
   - a Feature is missing any Section 9.1 property, or two Features share a `route_id`.

   Two different stop IDs closer than 30 m produce a warning, not a failure.
3. **Seed:** `data/seed.py` replaces `route`, `stop`, `route_stop` from `routes.geojson` in one transaction: `DELETE` from `route_stop`, then `route` and `stop`, then `INSERT` `stop`, `route`, `route_stop` (foreign-key order). It never touches `report`.
4. **Provenance:** `data/README.md` records, per route, the source (`osm` or `memory-traced`), the OSM fetch date and relation ID where relevant, and whether it was ridden or checked on the ground. Unverified routes are listed as known gaps.

Fixing a wrong line: for a traced route, add a via waypoint on the correct road and re-run snap. For an OSM route, either correct it on OpenStreetMap itself (optional, then re-fetch) or list its `route_id` in `data/prefer_traced.txt` and trace it. Then re-run build, validate and seed.

## 10. Configuration and Tunables

All are environment variables with defaults; none are hardcoded constants.

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | set in compose | Postgres connection |
| `SERVICE_BBOX` | `15.08,15.22,120.50,120.68` | lat_min, lat_max, lng_min, lng_max; requests outside are rejected. Overpass wants a different order (south, west, north, east); `fetch_osm.py` converts it |
| `WALK_RADIUS_M` | 500 | Max walk from a point to a stop |
| `TRANSFER_RADIUS_M` | 100 | Stops within this distance count as one transfer point |
| `TRANSFER_PENALTY_KM` | 1.0 | Flat cost added each time you board a jeep |
| `WALK_COST_FACTOR` | 2.0 | Walking costs this many times riding, per km |
| `GRAPH_MODE` | `cached` | `cached` builds the graph at startup; `rebuild` builds it per request (benchmark only) |

The two cost values are starting guesses. They are tuned once against the 10 test trips (Section 11) and the final values and the reason go into `DECISIONS.md`.

**Planner definition** (so it can be implemented and explained exactly):

- Nodes: `at(stop)` and `on(route, seq)`.
- Edges: `at -> on` boarding costs `TRANSFER_PENALTY_KM`; `on(seq) -> on(seq+1)` riding costs the straight-line distance between the two stops in km; `on -> at` alighting costs 0; `at -> at` walking between stops within `TRANSFER_RADIUS_M` costs distance in km x `WALK_COST_FACTOR`.
- Start and end: virtual nodes connected to every stop within `WALK_RADIUS_M`, with the same walking cost.
- Search: Dijkstra. The lowest-cost path is returned. Because every boarding costs a penalty, fewer jeeps are preferred without a separate "fewest transfers" search.
- Ride distance uses straight lines between stops, not the snapped line length. This is an accepted approximation for the MVP.

## 11. Performance and Measurement Requirements

No figures exist yet; these are targets, and results are written into `docs/DECISIONS.md` when measured.

| Metric | Target | How measured |
|---|---|---|
| `/api/plan` p50 and p95 latency, warm | p95 under 200 ms | `bench/plan_bench.py`: 200 requests between random stop pairs, prints p50/p95 |
| Cached graph vs. rebuild per request | Report both numbers and the ratio | same script with `GRAPH_MODE=cached` then `rebuild` |
| Plan correctness | At least 8 of 10 | `tests/test_trips.py`: 10 trips you personally know, each with the expected colors in order |
| Page load on a phone | Under 3 s | One Lighthouse run, result saved |

The latency target is measured on the developer's machine; the number is reported with that hardware stated, not presented as production performance. If a target is missed, the real number is reported, not adjusted.

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
- **Licensing.** OpenStreetMap data and tiles are ODbL / tile-policy bound: attribution on the page and in the README (NFR-5). Route lines and stops imported from OSM live in `routes.geojson`, which makes that file OSM-derived data; the README says so and links to the OSM copyright page, and `source: "osm"` marks which routes are affected. Read the ODbL terms on the OSM site before publishing the repository, since derived databases carry conditions. Google Maps is used only as a memory aid; no Google data is copied into the repository.
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
data/       raw/waypoints.csv, osm_overrides.csv, prefer_traced.txt,
            routes/from_osm.geojson, routes/from_traced.geojson, routes/routes.geojson,
            fetch_osm.py, snap_routes.py, build_routes.py, validate.py, seed.py, README.md
tests/      api/, planner/, data/, test_trips.py
bench/      plan_bench.py
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
5. `GET /api/routes` returns 12 records; `GET /api/routes/yellow_out` returns a line plus at least 2 stops; an unknown ID returns `404`.
6. `GET /api/stops?q=` with a lowercase partial name returns matches; empty `q` returns `422`.
7. A known single-jeep trip returns one ride step; a known transfer trip returns ride, transfer, ride.
8. A point outside the service area returns `400`; a point far from any stop returns `404 no_stop_nearby`.
9. Stop the database container: `/api/plan` still returns `200`, `/api/reports` returns `503`, `/health` shows `database: down`.
10. Add a bad row to `waypoints.csv` (gap in `seq`) and run `validate.py`: it fails; CI would fail the build.
11. Push a deliberately failing test: CI fails. Fix it: CI passes.
12. Run `bench/plan_bench.py` in both `GRAPH_MODE` values; p95 under 200 ms in `cached`; both results recorded in `DECISIONS.md`.
13. Run `tests/test_trips.py`: at least 8 of 10 trips pass; failures are listed in the docs as known data gaps.
14. Compare README's endpoint table to `/docs`: every endpoint matches. Every Section 3 tool has a `DECISIONS.md` entry.
15. Run `fetch_osm.py`: it prints a coverage line for each of the 12 route records (found or missing, stop count, line connected). Any route marked found has `source: "osm"` and a non-null `osm_relation_id` in `from_osm.geojson`.
16. Run `build_routes.py` and `validate.py` with one route taken from OSM and one hand-traced: both appear in `routes.geojson`, all 12 IDs are present, and validation passes. Then list an OSM route in `prefer_traced.txt` and confirm the build switches it to the traced version.

| Requirement | Verified by |
|---|---|
| FR-1, FR-2 | 7, 13 |
| FR-3 | 5 |
| FR-4 | 6 |
| FR-5 | 2, 3 |
| FR-6 | 2, 4 |
| FR-7 | 1, 10, 15, 16 |
| FR-8 | 1 |
| FR-9 | 1, 9 |
| FR-10 | 3, 8 |
| NFR-1 | 12 |
| NFR-2 | 13 |
| NFR-3 | 1 |
| NFR-4 | 14 |
| NFR-5 | 1 (visual check) |

## 15. Cut List and Open Items

**Cut for the 3-day sprint** (each gets a one-line reason in `DECISIONS.md`):

| Cut | Reason |
|---|---|
| PostGIS | Plain latitude/longitude and a small distance function are enough for 12 routes; one less extension to run and explain |
| Redis / response caching | The in-memory graph already removes the slow part; add only if the benchmark shows a need |
| React / front-end build step | A static page with Leaflet is easier to modify and defend |
| Accounts, login, rate limiting | No personal data to protect; reports cannot change route data |
| Fares, tricycles, buses, real-time | No reliable data |
| "Use my location" button, landmark search beyond stop names | Map tap and stop-name search cover the use case |
| Report moderation screen | Maintainer edits `status` in SQL |
| Alembic migrations | Drop the volume and re-seed |
| Self-hosted OSRM | The public server is used once, offline |
| Tagalog labels | English first |

**Decisions assumed (change before Day 1 if wrong):**

1. **Confirmed:** each color is exactly one named route in two directions (Section 7 registry). Nothing is assumed about variants; if you later find one, give it its own `route_id` and add it to the registry.
2. The map page is in scope.
3. English only.
4. Reports are public immediately.

**Open items:**

- Which of the 12 route records exist in OSM: found out on Day 1 with the Section 9.2 query. The coverage result decides how much hand-tracing is needed; record it in `data/README.md`.
- OSM relations that match a route by name but not by `from`/`to`: resolved case by case in `data/osm_overrides.csv`.
- `TRANSFER_PENALTY_KM` and `WALK_COST_FACTOR` final values: set after the first run of the 10 test trips.
- Exact pin for each named place in the Section 7 registry (Villa, Pampang, Pandan, Checkpoint, Holy, Highway, Balibago, Sapang Bato, Angeles, Main Gate, Friendship): decide the real boarding spot for each and write it in `data/README.md`. "Highway" and "Angeles" are broad names, so pick the actual terminal or main stop you mean.
- The 10 test trips and their expected colors: write them before building the planner, so the planner is tuned against a fixed list.