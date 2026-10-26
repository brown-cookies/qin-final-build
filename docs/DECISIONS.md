# Decisions

Per tool and per cut: what, why, rejected alternative. Measured results state their hardware. Layout: SPEC Section 3 tools first (stack), then the data and planner decisions made while building, then the Section 15 cuts, measured results, and the log of bugs found along the way.

## Stack (SPEC Section 3)

### FastAPI + Pydantic
- What: FastAPI for the HTTP layer; one Pydantic model per request/response in `app/schemas.py`, unknown request fields rejected.
- Why: the build requires it; validation, the `/docs` page and response models come with it, and every error can be forced into the one `{"error", "message"}` shape through exception handlers.
- Rejected: Flask or Django (validation and docs would be extra libraries or boilerplate).

### PostgreSQL
- What: one Postgres 16 database holding `route`, `stop`, `route_stop` and `report`; route lines are `jsonb`.
- Why: the build requires it; the data is small and relational, and `report` needs a real insert with defaults (`gen_random_uuid()`, `now()`).
- Rejected: SQLite (the build names Postgres and CI should match production) and a document store for the route lines (they are read once at startup anyway).

### psycopg v3 with hand-written SQL, no ORM
- What: `psycopg` with a `psycopg_pool` pool (1 to 5 connections, bounded wait); every statement is in `app/queries.py` or `sql/schema.sql` with `%s` parameters; reads return plain dicts.
- Why: every query is visible and can be read against the schema; there are six tables worth of SQL, not enough to justify a mapping layer; parameters make injection a non-issue.
- Rejected: SQLAlchemy or any ORM (hidden queries, a second model of the schema) and an async driver (the endpoints are short and FastAPI runs sync handlers in a thread pool).
- Note: the pool is bounded by `DB_POOL_TIMEOUT_S` (not in SPEC Section 10, default 3 s) so a dead database gives `503` quickly instead of hanging a request.

### Dijkstra with `heapq`
- What and why: see the Planner entry below. It is the only algorithm in the project and the whole of it is about 50 lines.
- Rejected: A* (no benefit on a 688-node graph) and networkx.

### Leaflet + OpenStreetMap tiles, plain static page
- What: `web/index.html`, `map.js`, `style.css`, with Leaflet vendored into `web/` (no CDN) and tiles from `tile.openstreetmap.org`; served by FastAPI `StaticFiles` mounted last.
- Why: no build step, no front-end framework, one container serves everything, and the only third-party request at runtime is the browser loading tiles (allowed by hard rule 8). The page credits "(c) OpenStreetMap contributors" in the map attribution.
- Rejected: React or any bundler (SPEC cut), a CDN-hosted Leaflet (a second third-party dependency at runtime), and a separate static host (a second thing to run).

### pytest
- What: pytest with a real Postgres test database (`TEST_DATABASE_URL`, name must end in `_test`, created if missing). 233 tests: API, planner, data pipeline, config and startup, the 10 trips.
- Why: the build requires it. Planner and trips tests need no database; API and seed tests use real SQL so constraints and transactions are actually exercised.
- Rejected: mocking the database (it would not catch SQL or transaction errors) and sqlite-in-memory (different SQL).

### Docker + Compose
- What: a slim Python image running as a non-root user; Compose runs `db` and `api`, `api` waits for `db` to be healthy and restarts on exit.
- Why: `docker compose up` plus one seed command is the whole setup (NFR-2); fail-fast startup plus `restart: unless-stopped` covers the case where Postgres is slower than the API.
- Rejected: seeding automatically on container start (it would hide a bad data file behind a restart loop, and the seed must be a visible, re-runnable step).

### GitHub Actions with a Postgres service container
- What: one workflow on every push and pull request: Postgres 16 service, install pinned requirements, `pytest`, `python data/validate.py`.
- Why: the tests run against the same Postgres major version as Compose, and the data check fails the build on a bad `routes.geojson` without a database or network.
- Rejected: testcontainers or a Docker-in-Docker step (a service container is simpler) and calling OSRM from CI (hard rule 8).

### OSRM public server for route snapping (offline only)
- What: `data/snap_routes.py` sends hand-traced waypoints to the OSRM public server (driving profile) in overlapping chunks of 80 points and commits the result.
- Why: hand-placed waypoints give the intent, OSRM gives a line that follows real roads; it runs once per data change and never at runtime or in CI.
- Rejected: an OSM/Overpass route import (coverage never confirmed, see the cut below) and self-hosting OSRM (a cut, see below).
- Limit: OSRM's driving profile follows one-way streets and the roads a car would take, not necessarily the lanes a jeep uses, and the public server is a shared demo service. Every route is memory-traced and unridden, so a snapped line can be wrong where the waypoints were too sparse.

## Error shape and codes (`app/main.py`)
- What: validation errors, HTTP errors, DB outages and unhandled exceptions all go through handlers that emit `{"error", "message"}`. Statuses and codes are in SPEC Section 12; two codes are not in the SPEC and are chosen here: `not_found` (404) and `method_not_allowed` (405), plus `http_<status>` for any other Starlette error.
- Why: the front end and any client can parse one shape; unhandled exceptions return a fixed message and the details only go to the log.
- Rejected: FastAPI's default `{"detail": ...}` bodies.

## Snap: densify and join check (`data/snap_routes.py`)
- What: after OSRM, densify each line to at most 40 m between points and fail if any waypoint (vias included) is over 50 m from its snapped line.
- Why: OSRM returns sparse points on straight roads, which would trip validate's 50 m gap rule on good lines; the join check catches a real bad snap instead.
- Rejected: loosening the gap threshold in validate (hides real jumps) or trusting the snapped line unchecked.

## Validate (`data/validate.py`)
- What: stdlib-only checker for every SPEC 9.3 rule plus a 30 m near-duplicate stop warning; exit 1 with one line per problem, all problems collected; thresholds are module constants, `SERVICE_BBOX` is read from `app.config`.
- Why: it must run in CI with no DB and no network, and the failure text must tell the maintainer which route and stop to fix. Distances use haversine to the nearest densified line point, matching `snap_routes.py`.
- Rejected: JSON Schema or shapely (new dependency for 9 routes) and segment projection (the 40 m densify makes vertex distance close enough).
- Note: stop objects have no `seq` in the file (list order is the seq), so an optional `seq` is checked when present; this lets the gap and "not starting at 1" rules be tested without changing snap output.

## Seed (`data/seed.py`, SQL in `app/queries.py`)
- What: validate first, apply the idempotent schema, then DELETE `route_stop`, `route`, `stop` and INSERT `stop`, `route`, `route_stop` in one transaction; one `stop` row per `stop_id`, first occurrence in sorted `route_id` order then list order wins.
- Why: re-runnable, atomic, deterministic regardless of file order; `report` has no foreign key to `route` or `stop` and is never touched, so replacement can never be blocked. A future foreign key from `report` must not block replacement.
- Rejected: upsert per row (leaves stale routes behind) and TRUNCATE (also locks and hides partial failure); SQL inside `seed.py` (breaks hard rule 2).

## Planner (`app/planner/`)
- What: Dijkstra with `heapq` over an in-memory graph with `at(stop)` and `on(route, seq)` nodes (plus one wrap ride edge on circular routes, see the wrap entry); board costs `TRANSFER_PENALTY_KM`, ride costs straight-line km, walk edges between stops within `TRANSFER_RADIUS_M` cost km x `WALK_COST_FACTOR`; the graph is built once at startup from plain data and the planner imports no DB or config code.
- Why: boarding as a node-to-node edge makes the transfer penalty fall out of the shortest-path cost, a circular route that passes a stop twice needs no special case (the loop's closing edge is a separate decision below), and unit tests run on a hand-made graph with no Postgres.
- Rejected: a stop-to-stop graph with a penalty on route change (needs path state in Dijkstra) and networkx (new dependency for 9 routes).

## Virtual start and end, and the walk guard (`app/planner/search.py`)
- What: the query start and end are handled inside `find_path` as synthetic edges to stops within `WALK_RADIUS_M`, never stored in the shared graph; a stop reached by a walk edge can only board or finish, so walks do not chain past `TRANSFER_RADIUS_M`.
- Why: concurrent requests run in threads, so mutating shared adjacency lists would corrupt later queries; without the guard a run of 60 m hops could beat a ride, and the SPEC only intends one transfer walk.
- Rejected: adding and removing temporary nodes on the graph, and limiting chaining in `Graph` (breaks the plain edge-kind test).

## Route data at startup and the database-down split (`app/main.py`, `app/api/`)
- What: `load_route_data` reads `route`, `stop`, `route_stop` once into `app.state` (graph, routes with lines, stops); `/api/plan`, `/api/routes` and `/api/routes/{id}` serve only from it, `/api/stops` runs the ILIKE query and falls back to the in-memory list with the same semantics when the database is unreachable.
- Why: SPEC Section 12 needs these endpoints to keep working when the database drops, and route data is read-only at runtime, so a reload is a restart after a re-seed.
- Rejected: a reload endpoint (a runtime write path SPEC does not have) and per-request route queries (the endpoints would fail with the database).

## Stop search (`app/queries.py`, `app/api/stops.py`)
- What: `name ILIKE '%' || %s || '%'` with `\`, `%` and `_` escaped so `q` is a literal substring; `q` is stripped, 1 to 100 characters, no NUL; order is `name COLLATE "C"`, then `stop_id`, limit 10.
- Why: SPEC says "contains", so a user typing `%` should not match everything; the fixed collation makes the SQL order equal the Python sort used by the memory fallback.
- Rejected: passing `q` into ILIKE unescaped and a trigram index (226 stops).

## Plan input errors (`app/api/plan.py`)
- What: the four parameters are read as strings and parsed in the router, so missing, non-numeric, NaN/inf or out-of-bbox values return `400 invalid_location`, not FastAPI's 422.
- Why: SPEC Section 12 lists these under `invalid_location`; the generic handler would turn them into `validation_error`.
- Rejected: typed `float` query parameters with a custom exception handler (it would also change `/api/stops` and `/api/reports` validation).

## The 10 test trips: first run, not tuned (`tests/test_trips.py`)
- What: 10 trips with expected ride colors from the maintainer, run through the planner on `data/routes/routes.geojson` with the default costs (`TRANSFER_PENALTY_KM` 1.0, `WALK_COST_FACTOR` 2.0, `WALK_RADIUS_M` 500, `TRANSFER_RADIUS_M` 100); no database needed, deterministic.
- Result: **10 of 10 pass** (target: at least 8); trip 8 passes only because its accepted answers were widened, see the known limitation in the wrap edge entry below. Straight-line ride cost, no tuning applied. `tests/test_trips.py` also holds an 11th trip (Beeway Travel to Balibago Cebuana Lhuillier, added on reviewer feedback as the worst case for circular routes) and two assertions on the wrap edge; the 10 in the target are the original ones.
- Tuning (open item 6): `TRANSFER_PENALTY_KM` (1.0) and `WALK_COST_FACTOR` (2.0) were **never tuned**. The first run met the target at the defaults, the only miss (trip 8) is a missing planner rule and not a cost problem, and changing a value to fit a list of 10 trips would be overfitting. They stay at the SPEC starting values.
- Caveat: the 10 trips are known by one person, are all inside the parts of the map that person knows, and several of them start or end at the same terminals. Passing 10 of 10 says the planner agrees with that person's picks on those trips, not that it is right everywhere.
- Failure, trip 8 (Starbucks Near AUF to Blue End Terminal, expected Purple then Blue): Purple meets Blue at seq 75-76, before Starbucks Near AUF (seq 80). A real Purple jeep keeps looping, but the graph has no edge from the last stop of a circular route to its first, so the planner walks 491 m to a Blue stop and rides Blue only. Cost tuning cannot fix this; Yellow and Grey have the same limit. That gap is what the wrap edge below addresses; see its entry for the result after the change.
- Passing with a different color than first expected: trip 9 (Jenra Mall to System Plus College) rides Grey after an 87 m walk; both Grey and Purple were accepted. Trip 10 rides Blue then Purple.
- Rejected: counting the gap as a data fix by changing expected colors. The first run measured the gap at 25 of 1,500 pairs (engineer's measurement) and the wrap edge was added afterward (next entry).

## Empty route data signal (`app/main.py`, `app/api/plan.py`)
- What: zero routes at startup logs one WARNING, `/health` adds `route_data: loaded | empty` from startup data, and `/api/plan` returns `503 route_data_unavailable` (after `invalid_location` validation); the README, CLAUDE.md and SPEC say to restart the api after seeding.
- Why: seeding after the process started left a healthy-looking API whose plan calls blamed the user's location with `no_stop_nearby`; the restart rule above was documented but nothing signalled it.
- Rejected: a runtime reload path (see the startup decision above, no runtime write path) and having the seed command restart the container (it would need the Docker socket inside the seed container).

## Wrap edge on circular routes (`app/planner/graph.py`, `mark_circular`)
- What: for a route flagged `circular`, `Graph` adds one ride edge `on(last) -> on(0)` costing the straight-line km from the last stop to the first; a color is circular when it has an `out` record and no `back` record (yellow, purple, grey), derived by `mark_circular` at startup and by the trips test fixture, so the rule exists once.
- Why: a real jeep keeps looping, and without the edge a rider past the loop's meeting point with the destination route walked or took extra rides (Beeway Travel to Balibago Cebuana Lhuillier: 3 rides, 11.4 km before; 1 ride after). The straight-line gaps from the last to the first stop are 39 m (Yellow), 446 m (Grey) and 705 m (Purple), measured from the data.
- Measured (1,500 random ordered stop pairs, `random.Random(1)`, plan distance walk+ride metres vs a reference plan on the same data with transfer penalty 1e-6 km; AMD Ryzen 7 5700X, 15.9 GB, Python 3.12.10, Windows 11): pairs more than 20% longer than the reference: 45 before the wrap edge, 20 after; worst case 8.3x before (ARTE Cafe to Balibago 7-Eleven Near Walking Street, 11,458 m vs 1,376 m), 1.94x after (Power fill Entiero to San Jose Street, 2,272 m vs 1,169 m). This procedure is not the engineer's (the 25 of 1,500 script was not in the repo), so the numbers are not comparable to 25.
- Trip 8 (Starbucks Near AUF to Blue End Terminal): still returns Blue only, after the 491 m walk, and is accepted as a known limitation (next bullet), so the trips are 10 of 10. Riding Purple around the loop to the Blue meeting point is about 9.8 km plus two boardings against about 2.4 km plus one boarding for Blue; cost tuning is out of scope.
- Known limitation, trip 8: at the Purple/Blue meeting point the Blue jeep is always full because it starts from its terminal; nobody boards down until it has passed the circular rotunda, so the real answer is Purple to the Blue terminal, then Blue. The planner has no boardable-here rule in this spec, so trip 8 accepts `("blue",)` as well as `("purple", "blue")`.
- Rejected: a stored or hardcoded circular column or registry list (a second source of truth for what the registry already says) and treating the loop end as a walk transfer (the last stop is 39 to 705 m from the first and the rider does not leave the jeep).

## Deferred: ride highlight pair matching (`web/map.js`, `matchRide`)
- What: the front end picks the pair of same-named stops with the shortest line stretch, then rejects it if the destination index is below the origin index. Verification (T010, jsdom against the live API, not a real browser) found two defects: a tie between pairs at the same line position can keep a backward pair and show a false "No match found" (76 of 297 unique rides in 400 random trips, on `grey_out` and `purple_out`), and 13 of 297 rides highlighted a different stretch than the API's ride (for example 24 stops highlighted instead of 11).
- Why deferred: the maintainer decided there is not enough time in the sprint to fix it. It is shipped as a known limitation; the trip and steps list are still shown and nothing is hidden when it happens.
- Not decided: the matching rule. Options raised were using the API's `stops_passed` to choose the pair, dropping backward pairs before comparing, or keeping the rule. Whether `stops_passed` equals the stop-index gap was not checked.

## Map page scope (`web/`)
- What: the page draws the six lines and stop dots, takes origin and destination from two map taps (or taps on a stop dot), shows the steps and summary, and highlights each ride. Taps are locked while a request is pending and after any result, until Reset.
- Why: this covers the plan flow end to end with the least code, and the SPEC allowed cutting stop search first.
- Cut from FR-8: the **stop-name search pickers**. `GET /api/stops?q=` exists, is tested and documented, but nothing in the page calls it. FR-8 says "by tapping the map or searching a stop name"; only the first half is met.
- Not built: a report form (`POST /api/reports` is reachable only through `/docs` or curl), a "use my location" button, a responsive layout (the side panel is a fixed 320 px, so a phone-sized screen is cramped).
- Rejected: building the search pickers at the end with no time to test them in a browser.

## Cuts (SPEC Section 15)
One line each; the reasons are the SPEC's, stated as decisions.

| Cut | What we did instead | Rejected alternative |
|---|---|---|
| PostGIS | Haversine in Python for the 226 stops; plain `lat`/`lng` columns | PostGIS extension: one more thing to run and explain for 9 routes |
| Redis / response caching | Graph built once in memory; a plan costs about 1 ms (measured below) | A cache in front of an endpoint that is already fast |
| React / front-end build step | One static page with vendored Leaflet | A bundler and framework |
| Accounts, login, rate limiting | Nothing; reports are anonymous and public immediately | Auth: no personal data to protect. Known risk: no rate limit and no moderation, so reports can be spammed; the maintainer edits `status` in SQL |
| Fares, tricycles, buses, real time | Not modelled | No reliable data |
| "Use my location", landmark search | Map tap only | Browser geolocation and a geocoder (a third-party call) |
| Report moderation screen | `status` (`new`/`seen`/`fixed`) edited in SQL | An admin UI |
| Alembic migrations | Edit `sql/schema.sql`, drop the volume, re-seed | A migration tool for 4 tables |
| Self-hosted OSRM | Public server, once, offline | A second container to run for a one-off |
| Tagalog labels | English only | A translation layer and a second set of strings to keep in sync |
| OSM/Overpass route import | All 9 routes hand-traced, `osm_*` columns left null | A second source needs merge and precedence logic |

## Measured results
Hardware for every number here: AMD Ryzen 7 5700X (8 cores), 15.9 GB RAM, Windows 11, Python 3.12.10 (the repo `.venv`), planner run in-process without HTTP. Measured 2026-10-26 on the committed `routes.geojson` with default settings.

| Metric | Target (SPEC 11) | Result |
|---|---|---|
| Plan correctness, original trips | at least 8 of 10 | **10 of 10** (see trips entry; trip 8 passes on a widened answer) |
| Graph build at startup | none set | 21 ms for 688 nodes and 1,918 edges |
| Plan time in process (two `stops_within` scans, Dijkstra, steps), 1,000 random stop pairs, `random.Random(1)` | none set | p50 1.0 ms, p95 1.7 ms, max 2.5 ms; a path was found for 1,000 of 1,000 pairs |
| Test suite | all pass | 233 passed in 33 s against a local Postgres 16 |
| Longest single walk step, 1,000 random points within about 330 m of a stop | none set | 590 m; 45 walk steps were over `WALK_RADIUS_M` (see limitations) |

These are the numbers as measured. HTTP latency, concurrent load and a cold start inside Docker were **not** measured. The SPEC set no latency target, so none was missed or adjusted.

## Bugs found and fixed
What went wrong while building, found by tests, by the verifier or by running the stack. Kept so the same mistakes are not repeated.

| Bug | Found by | Fix |
|---|---|---|
| A run of 60 m stop-to-stop hops could string into a 511 m "transfer walk" (Pampang to Angeles Sapangbato Terminal, 7 hops), and a chain of hops could beat a ride | Verification of the planner against the seeded DB | Walk edges cannot chain past `TRANSFER_RADIUS_M`: a stop reached by walking may only board or finish (`("wk", id)` state in `search.py`); regression test in `tests/planner/` |
| With two or more transfers the summary dropped the middle ride | Planner work (`00f1dbd`) | `build_summary` keeps the ride between two transfers; test added |
| Riders on a circular route could not stay on the jeep past its last stop, so the planner walked or took extra rides (Beeway Travel to Balibago Cebuana Lhuillier: 3 rides, 11.4 km) | Trip 8 and a reviewer | Wrap edge `on(last) -> on(0)` on routes with no `back` record (see its entry) |
| API seeded after it started looked healthy but every plan said `no_stop_nearby`, blaming the user's location | Running the stack | `/health` `route_data`, a startup WARNING and `503 route_data_unavailable` (see its entry); the restart rule is in README, SPEC and CLAUDE.md |
| `localhost` as the Postgres host stalled on Windows (IPv6 tried first) | Running tests on Windows | Defaults use `127.0.0.1` (`8fc54c5`) |
| Mounting `web/` at `/` swallowed the test route used to prove `500 internal_error` | Verification of the static mount | The static mount is last; the test inserts its route ahead of the mount |
| Sparse OSRM points tripped the 50 m line-gap rule on good lines | Writing `snap_routes.py` | Densify to 40 m and check waypoint joins instead (see its entry) |
| Seed with an unreachable DB printed several multi-line pool log blocks before its one-line message | Verification of the seed | Cosmetic, left as is: exit code 1, no traceback, the final line is clear |
| `validate.py` printed "only 30 m apart (under 30 m)" because distances were rounded in the message | Verification of validate | Cosmetic, left as is: the check itself uses the unrounded distance |
| A timed banner shown over the persistent map-load error overwrote it and then hid it, so the load message was lost | Verification of the plan UI | **Not fixed** (see limitations) |
| Ride highlight picks the wrong stop pair, or says "No match found" on a valid ride | Verification of the plan UI | **Not fixed**, deferred (see the entry above) |

## Known limitations
Accepted for the MVP. Each is something a user or maintainer could run into.

### Route data
- **All 9 routes are hand-traced from memory and none has been ridden.** `verified_on` is `null` everywhere. Treat a plan as a best guess, not a promise that a jeep stops there (`data/README.md`).
- **Checkpoint and Highway are not named stops.** Purple and Grey still share about 35 other stops, so that transfer works.
- **Jurio Foodhouse (Purple and Grey) is a placeholder pin**, the midpoint 15.16803, 120.58354, not a real location. A plan through it goes through a made-up point.
- **Blue `out`/`back` direction versus the SPEC registry** (Pandan to Pampang) is unresolved; the data is left as traced.
- **48 stop pairs are under 30 m apart** (`validate.py` WARNING). Most are different shops on one street; a few, such as `jollibee_rizal_street` and `lorraine_technical_school` at 3.7 m, are probably the same place under two names and could be merged.
- OSRM snaps along roads a car can use; a jeep may use others.

### Planner
- **Ride distance is straight-line between stops.** It under-reports on winding roads and feeds both the cost and the `distance_m` shown.
- **No "can I board here" rule.** Every stop of a route is treated as boardable. Trip 8 is the known case: the Blue jeep at the Purple/Blue meeting point is full because it starts at its terminal, so the real answer is Purple to the Blue terminal, then Blue. The planner returns Blue only, after a 491 m walk, and the test accepts both.
- **Loops can look long.** After the wrap edge, 20 of 1,500 random stop pairs are still more than 20% longer than the reference plan (worst case 1.94x).
- **Walking can exceed `WALK_RADIUS_M`.** The radius applies to the stop you walk to; a walk of up to `TRANSFER_RADIUS_M` between two stops at the same place is folded into the same step, so a first or last walk can reach about 600 m (590 m measured).
- **Same start and end stop** gives two walk steps ("Walk to Pampang, walk to your destination") and no ride.
- **`TRANSFER_PENALTY_KM` and `WALK_COST_FACTOR` are untuned starting values.**
- **No fares, schedules, wait times or traffic.**

### API and operations
- **Route data loads once at startup.** After a re-seed the API must be restarted; until then plans use the old data (or return `503 route_data_unavailable` if it started empty).
- **Reports have no moderation, rate limit or authentication.** Anyone can post, and every report is public through `GET /api/reports` immediately.
- **Dev credentials** (`biyahe`/`biyahe`) are in `docker-compose.yml`. Postgres is bound to `127.0.0.1`, but the API port is published on all interfaces. Not suitable for a public host without changing both.
- **The Docker image copies `data/` (including `routes.geojson`)** so the seed command can run in the container; rebuild the image after changing route data.
- **CI was not observed running.** `.github/workflows/ci.yml` exists and the same commands pass locally, but SPEC checklist item 11 (a deliberately failing test turns CI red) was not exercised.

### Map page
- **Ride highlight can pick the wrong pair of stops** (`matchRide`, deferred above). On routes that pass the same place twice (Grey, Purple), in the verifier's 400 random trips 76 of 297 unique rides falsely showed "No match found" and 13 of 297 highlighted a different stretch than the API's ride. The steps list and summary are always shown. The verifier used a headless DOM against the live API, not a real browser.
- **A timed error banner can erase the persistent "could not load routes" banner.** Only reachable when route loading failed and the user then tries to plan.
- **No stop search, no report form, no mobile layout** (see the map page entry).
- Needs internet in the browser for OSM tiles; without it the lines draw on a blank background. Heavy traffic from a public deployment would not fit the OSM tile usage policy.

### Process
- Hardware and numbers above are from one machine; nothing was load-tested.
- `.claude/` (agent definitions, task specs, verifier reports, ledger) is committed. It is the working record of how the code was built, not part of the product.
