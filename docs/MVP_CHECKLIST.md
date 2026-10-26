# MVP Checklist: intended vs current

Compares what `SPEC.md` set out to deliver with what the system does today. Checked 2026-10-26 against the rebuilt Docker stack, `pytest` (233 passed) and `python data/validate.py`.

Legend: `[x]` done and verified, `[~]` partly done (the gap is stated), `[ ]` not done.

**Summary:** 38 done, 3 partly done, 19 not done (a few not-done items repeat in sections 5 to 10, so the real number of distinct gaps is lower). Everything the SPEC calls required (the POST/GET, validation, tests, Docker, Compose, CI file, the planner and the data pipeline) works. What is missing is mostly the front end's extras, real-world verification of the route data, and publishing steps.

## 1. Deliverable (SPEC Section 1)

- [x] `POST /api/reports` validates with Pydantic and writes to PostgreSQL
- [x] `GET /api/reports` returns the most recent records
- [x] Trip planner `GET /api/plan` over the 9 route records
- [x] Static map page served by the same service: loads and plans trips, but see FR-8 below
- [x] pytest suite passing against a test database (233 passed)
- [x] Dockerfile and `docker-compose.yml` bring up API and database
- [x] GitHub Actions workflow running the tests on every push: the file exists and the same commands pass locally, but it has never been seen running on GitHub

## 2. Functional requirements (SPEC Section 5)

- [x] **FR-1** Plan a trip
- [x] **FR-2** Readable steps: same-route rides merge, one-line `summary`
- [x] **FR-3** `GET /api/routes` (9 records) and `/api/routes/{route_id}` (GeoJSON line plus stops)
- [] **FR-4** Stop search: the endpoint works, but nothing on the map page uses it
- [x] **FR-5** Submit a report
- [x] **FR-6** Recent reports, newest first
- [x] **FR-7** `seed.py` is re-runnable and never touches `report`; `validate.py` runs in CI
- [~] **FR-8** Map page: six colored lines, tap-to-set origin and destination, steps and highlight all work. **Missing:** searching a stop name to pick a point. The ride highlight can also pick the wrong stop pair on Grey and Purple
- [x] **FR-9** `/health` returns 200 and reports `database` and `route_data`
- [x] **FR-10** One error shape everywhere, including validation errors

## 3. Non-functional requirements

- [x] **NFR-1** At least 8 of 10 trips: 10 of 10 pass (trip 8 only on a widened answer)
- [x] **NFR-2** `docker compose up`, then one seed command and a restart
- [x] **NFR-3** Every endpoint is in the README and every SPEC Section 3 tool is in `DECISIONS.md`
- [x] **NFR-4** "(c) OpenStreetMap contributors" is on the map and in the README

## 4. Manual verification checklist (SPEC Section 14)

- [x] 1. Stack starts, seed, restart; `/health` shows `up` and `loaded`; page loads
- [x] 2. Valid report returns 201 and is listed first
- [x] 3. Empty message, unknown color, only `lat`, out-of-area coordinates all return 422 in the error shape
- [x] 4. `limit=0` and `limit=51` return 422
- [x] 5. 9 routes listed; `yellow_out` has a line and stops; unknown ID returns 404
- [x] 6. Stop search works; empty `q` returns 422
- [x] 7. Single-jeep and transfer trips return the right steps
- [x] 8. Outside the area returns 400; far from any stop returns 404 `no_stop_nearby`
- [x] 9. Database stopped: plan 200, reports 503, health `down`
- [x] 10. Bad `seq` in the data makes `validate.py` fail (exit 1)
- [ ] 11. Deliberately failing test turns CI red, then green: **not done**, needs a push to GitHub
- [x] 12. Trips test passes (10 of 10)
- [x] 13. README endpoint table matches `/docs`
- [x] 14. All 9 route IDs present and valid; removing a route makes `snap_routes.py` fail naming it

## 5. Route data

- [x] All 9 route records traced, snapped, validated and seeded (226 stops)
- [ ] **None of the 9 routes has been ridden or checked on the ground** (`verified_on` is null everywhere)
- [ ] Real coordinates for Jurio Foodhouse (Purple and Grey use a placeholder midpoint)
- [ ] Checkpoint and Highway as named stops (neither exists as a stop)
- [ ] Pin table confirmed by the maintainer
- [ ] Blue `out`/`back` direction versus the SPEC registry (Pandan to Pampang) resolved
- [~] Near-duplicate stops: 48 pairs under 30 m apart are flagged but not reviewed

## 6. Planner quality

- [x] Dijkstra with transfer penalty, walk edges, wrap edge for circular routes
- [~] `TRANSFER_PENALTY_KM` and `WALK_COST_FACTOR`: left at the defaults on purpose, never tuned
- [ ] A rule for stops where a full jeep does not pick up (trip 8's real answer)
- [ ] Ride distance from the snapped line instead of straight lines
- [ ] Total walk kept within `WALK_RADIUS_M` (it can reach about 590 m)

## 7. Documentation set (SPEC Section 13)

- [x] `README.md`, `SPEC.md`, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, `data/README.md`, `docs/OPEN_ITEMS.md`
- [x] Measured numbers with hardware stated (plan correctness, graph build, plan time)
- [x] Screenshots of the map page in the README (`docs/images/`)
- [ ] **Project license chosen** (after reading the ODbL terms)
- [ ] HTTP latency and load measured (only in-process planner time was)

## 8. Cut on purpose (not expected in the MVP)

These are in the SPEC cut list, so they are not gaps: PostGIS, Redis, a front-end framework, accounts and rate limiting, fares/tricycles/buses/real time, "use my location", a moderation screen, Alembic, self-hosted OSRM, Tagalog labels, an OSM route import.

## 9. Before this is public

- [ ] Read the ODbL terms; then pick a license
- [ ] Confirm CI is green on GitHub
- [ ] Change the dev database credentials and the all-interfaces API port
- [ ] Decide what to do about unmoderated, unlimited public reports
- [x] Add the screenshot

## 10. Not required by the SPEC, but you will probably want

- [ ] A report form on the map page (reports can only be sent through `/docs` or curl)
- [ ] A layout that works on a phone (the side panel is a fixed 320 px)
- [ ] Fix the timed banner overwriting the "could not load routes" banner
- [ ] Fix the ride highlight pair matching (deferred; see `docs/OPEN_ITEMS.md`)
