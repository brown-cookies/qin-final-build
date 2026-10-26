# Open Items Register

Tracks the open items from `SPEC.md` Section 15 and what remains after the sprint. Status: `open`, `answered`, `deferred`, `dropped`. Last reviewed 2026-10-26.

## SPEC Section 15 items

| # | Item | Status | Answer / next step | Lives in |
|---|---|---|---|---|
| 1 | Which of the 9 route records exist in OSM | dropped | All 9 route records are hand-traced (no OSM route import) | `docs/DECISIONS.md` |
| 2 | OSM relations that match by name but not `from`/`to` | dropped | Follows from item 1 | n/a |
| 3 | Exact pin for each of the 11 named places | open | Candidates are in the pin table; the maintainer has not confirmed them. Checkpoint and Highway have no stop; Jurio Foodhouse is a placeholder | `data/README.md` |
| 4 | The 10 test trips and expected colors | answered | 10 trips plus one regression trip are in `tests/test_trips.py`; 10 of 10 original trips pass | `tests/test_trips.py`, `docs/DECISIONS.md` |
| 5 | Decisions assumed | answered | See below | `docs/DECISIONS.md` |
| 6 | `TRANSFER_PENALTY_KM`, `WALK_COST_FACTOR` | answered | Kept at 1.0 and 2.0, not tuned: the target was met at the defaults and the one miss is not a cost problem | `docs/DECISIONS.md` |

### Item 5: assumed decisions (confirmed)

1. Each color is exactly one named route. Yellow, Purple and Grey are one-way circular (`out` only); Blue, Red and Dark yellow run in two directions (9 records). Variants, if found later, get their own `route_id` and a registry entry.
2. The map page is in scope.
3. English only.
4. Reports are public immediately. Known risk: no moderation; the maintainer edits `status` in SQL.

## Before publishing

- [ ] Read the ODbL terms on the OpenStreetMap copyright page (SPEC Section 13). `routes.geojson` line geometry comes from OSRM on OSM road data. Then choose a project license (README says none yet).
- [ ] Confirm CI runs green on GitHub (checklist item 11 was not exercised: push a deliberately failing test, see it go red, fix it).
- [x] Screenshots of the map page are in the README (`docs/images/`).
- [ ] Remove or change the dev database credentials and the all-interfaces API port before any public deployment.

## Data

- [ ] Real coordinates for Jurio Foodhouse (`purple_out` waypoint 123, `grey_out` waypoint 98); then re-snap, validate, seed.
- [ ] Confirm or correct the pin table and decide what "Checkpoint" and "Highway" mean as stops.
- [ ] Resolve Blue `out`/`back` versus the SPEC registry (Pandan to Pampang).
- [ ] Ride the 9 routes and set `verified_on` per route; update the provenance table.
- [ ] Review the 48 near-duplicate stop warnings; merge the ones that are the same place (for example `jollibee_rizal_street` and `lorraine_technical_school`, 3.7 m).

## Product and code

| Item | Status | Notes |
|---|---|---|
| Ride highlight pair matching (`matchRide` in `web/map.js`) | deferred | Wrong pair or false "No match found" on Grey and Purple. Options raised: choose the pair with the API's `stops_passed`, drop backward pairs before comparing, or keep the rule. Check first whether `stops_passed` equals the stop-index gap |
| Timed banner overwrites the persistent load-error banner | open | Low severity; restore the load message when a timed banner expires |
| Stop-name search pickers on the map page (FR-8) | open | `/api/stops` is ready; the page does not call it |
| Report form on the map page | open | Not required by the SPEC |
| Boardable-here rule (trip 8) | open | Needs a data model for stops where a jeep is full, not just a planner change |
| Walk limit applies to the first/last stop only | open | Total walk can reach about 600 m; decide whether to count the stop-to-stop walk against `WALK_RADIUS_M` |
| Same start and end stop returns two walk steps | open | Cosmetic |
| Seed with an unreachable DB prints pool log blocks before its one-line message | open | Cosmetic |
| `validate.py` warning text rounds distances ("30 m apart (under 30 m)") | open | Cosmetic |
| HTTP latency and load measurements | open | Only in-process planner timing was measured |
| Responsive layout for phones | open | Side panel is a fixed 320 px |
