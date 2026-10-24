# Roadmap

Source: `SPEC.md`. Plan: three calendar days. Day 1 starts with the open-items register (Day 0 block, morning) and then builds the scaffold. Days 2 and 3 carry the weight.

**Deviation from SPEC Section 4 (SPEC left unchanged by decision).** The spec starts dropping route waypoints on Day 1. Here the decisions run first thing on Day 1 (they are open items), the heavy data and planner work moves to Day 2, and tuning, map and docs go on Day 3. `SPEC.md` Section 4 is not edited for the day split, so it and this file disagree on Day 1; this file is the working plan. Everything else in the spec still governs.

Effort split (rough): Day 1 ~30% (Day 0 block ~10% + scaffold ~20%), Day 2 ~35%, Day 3 ~35%.

## Day 1, morning: Open-items register (Day 0 block)

Goal: no unknown left that can block building. Output is `docs/OPEN_ITEMS.md`: one row per item with owner, status, answer and the file where the answer lives. Timebox to about half the morning so the scaffold still lands the same day.

| # | Open item (SPEC Section 15) | Action | Answer lands in | Resolvable today? |
|---|---|---|---|---|
| 1 | ~~Which of the 12 route records exist in OSM~~ | Dropped: all 12 are hand-traced | n/a | n/a |
| 2 | ~~Relations matching by name but not `from`/`to`~~ | Dropped with item 1 | n/a | n/a |
| 3 | Exact pin for each named place (Villa, Pampang, Pandan, Checkpoint, Holy, Highway, Balibago, Sapang Bato, Angeles, Main Gate, Friendship) | Pick the real boarding spot, record lat/lng; "Highway" and "Angeles" need a specific terminal or main stop | `data/README.md` | Yes |
| 4 | The 10 test trips and expected colors | Write trips you personally know, with expected colors in order; include at least 2 single-jeep, 2 transfer, and the Purple/Grey and Yellow/Blue shared-stop cases | `tests/test_trips.py` (fixture list) | Yes, before planner work |
| 5 | Decisions assumed (4 items: one route per color, map page in scope, English only, reports public) | Confirm or change | `docs/OPEN_ITEMS.md`, `docs/DECISIONS.md` | Yes |
| 6 | `TRANSFER_PENALTY_KM` and `WALK_COST_FACTOR` final values | Cannot be set until the planner runs the 10 trips | `docs/DECISIONS.md` | **No, deferred to Day 3**; keep row open with the trigger noted |

Also today:

- Read the ODbL terms on the OSM site (SPEC Section 13) before the repo is published; note any conditions.
- Pre-flight: Docker, Compose, Python, `git` and a GitHub repo with Actions enabled all work; feature branch created.
- Budget Day 2 for tracing all 12 routes. Each costs roughly 30-45 min of waypoint dropping in geojson.io plus snapping; `out` and `back` of a color share most waypoints, so the second direction is faster.

**Block done when:** every row except #6 has an answer written down (or is dropped); the 10 trips exist as data.

## Day 1, rest of day: Scaffold

Goal: green CI on a PR with the required POST/GET working end to end. No planner, no route data dependency.

- Repo skeleton per SPEC Section 13 layout; `requirements.txt` with pinned versions.
- `app/config.py` (env vars and defaults from Section 10), `app/db.py` (connection pool, fail fast at startup if DB unreachable), `sql/schema.sql` (`CREATE TABLE IF NOT EXISTS`, applied at startup).
- `app/queries.py` (parameterized SQL only), `app/schemas.py` (Pydantic, unknown fields rejected).
- One error shape (FR-10): handlers for validation errors, HTTP errors and unhandled exceptions; `500 internal_error` never leaks details.
- `GET /health` (200 even if DB down), `POST /api/reports`, `GET /api/reports?limit=`, including 422 and 503 paths.
- `Dockerfile`, `docker-compose.yml` (API + Postgres, API restarts until DB is ready).
- pytest with a test database fixture; tests for health, report create and list, every 422 case from Section 6.1, `limit` bounds, 503 when DB is down.
- `.github/workflows/ci.yml`: Postgres service container, pytest, and a `validate.py` step (stub it to pass until data exists, then real on Day 2).
- Open the PR early as a draft.

**Day 1 done when:** the open-items block is done; `docker compose up` works with no manual steps beyond the future seed command; checklist items 2, 3, 4 pass; CI green on the PR; deliberately failing test turns CI red then green (item 11).

**Risk:** the open-items block eats the day. Mitigation: if it runs long, finish item 4 (the 10 trips) and defer the rest of the pins to the start of Day 2; the scaffold must not slip, since Day 2 depends on it.

## Day 2: Data pipeline, planner and API (heaviest)

Goal: 12 valid route records in the database and `/api/plan` returning real answers. Split in two tracks; do data first since it is the critical path.

**Track A: route data (morning)**

- `data/raw/waypoints.csv` for all 12 routes, then `data/snap_routes.py` (OSRM, offline) writing `routes.geojson` directly; fails if any of the 12 has no waypoints.
- `data/validate.py`: all Section 9.3 checks plus the 30 m near-duplicate stop warning; wire into CI for real.
- `data/seed.py`: one transaction, FK-safe order, never touches `report`; confirm re-run is safe.
- Tests in `tests/data/` for validate failures (seq gap, out-of-bbox, stop ID collision, line gap, missing property).
- Start `data/README.md` provenance table as routes land.

**Track B: planner and endpoints (afternoon)**

- `app/planner/graph.py`: nodes `at(stop)` / `on(route, seq)`; board, ride, alight, walk edges; virtual start/end nodes within `WALK_RADIUS_M`; built once at startup.
- `app/planner/search.py`: Dijkstra with `heapq`; returns lowest-cost path.
- `app/planner/steps.py`: merge consecutive same-route ride edges, insert transfer steps, build the one-line `summary`.
- `GET /api/plan` with `invalid_location`, `no_stop_nearby` (says which end), `no_route`.
- `GET /api/routes`, `GET /api/routes/{route_id}` (GeoJSON line plus ordered stops, 404 `route_not_found`), `GET /api/stops?q=` (parameterized ILIKE, empty `q` 422).
- Planner unit tests with a tiny fixture graph (no Postgres); API tests for routes, stops, plan and the 503/200 split when the DB is down.
- First run of `tests/test_trips.py` over the 10 trips; record raw results, do not tune yet.

**Done when:** `snap_routes.py` and `validate.py` pass with all 12 IDs; checklist items 5, 6, 7, 8, 10, 14 pass; the 10 trips run and results are recorded.

**Risk:** tracing 12 routes eats the morning. Mitigation: trace `out` first, derive `back` by reversing the waypoints and adjusting where the return road differs. If Track A overruns, stop at "all 12 present and valid" and push planner polish to Day 3 morning.

## Day 3: Tune, map, measure, document, ship (heaviest)

Goal: checklist passes and the PR is mergeable.

Morning, make it correct:

- Tune `TRANSFER_PENALTY_KM` and `WALK_COST_FACTOR` against the 10 trips (closes open item #6); fix data gaps (add via waypoints, re-run snap) rather than bending the cost model. Need at least 8 of 10; list failures as known data gaps.
- Checklist item 9: stop the DB container; `/api/plan` 200, `/api/reports` 503, `/health` `database: down`.

Midday, front end:

- `web/index.html`, `web/map.js`, `web/style.css`: Leaflet with OSM tiles, six route lines in colors defined once in `map.js` (Yellow `#FACC15` vs dark yellow `#B8860B` visibly different), origin/destination by map tap, stop-name search pickers, plan steps shown, OSM attribution on the page (NFR-4).
- Served as static files by the same FastAPI service. Cut stop search first if time is short; keep map-tap.

Afternoon, measure and document:

- Docs: finish `README.md` (screenshot, confirm commands and endpoint table against `/docs`), `docs/ARCHITECTURE.md` (diagram plus planner definition), `docs/DECISIONS.md` (every Section 3 tool and every Section 15 cut: what, why, rejected alternative, 3 lines), `data/README.md` (provenance, fetch date, known gaps).
- Run the full Section 14 checklist (items 1-14) against a running stack; fix SPEC or code where they disagree.
- Final: CI green, PR description summarizing results, known gaps and measured numbers.

**Done when:** all 14 checklist items pass, NFR-1 to NFR-4 are met or honestly reported as missed, PR is ready for review.

## Cut order if time runs short

1. Map page stop-name search (keep map-tap).
2. Tracing the remaining routes: only if the shortfall is reported as a known data gap and the "all 12 present" rule is explicitly waived in SPEC. Otherwise this one does not get cut, because `snap_routes.py` and `validate.py` require all 12.

Never cut: the required POST/GET, validation, tests, Dockerfile, Compose, CI.
