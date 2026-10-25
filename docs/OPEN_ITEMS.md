# Open Items Register

Tracks the open items from `SPEC.md` Section 15. Status: `open`, `answered`, `deferred`.

| # | Item | Status | Answer / next step | Lives in |
|---|---|---|---|---|
| 1 | Which of the 12 route records exist in OSM | dropped | All 12 routes are hand-traced (no OSM route import); see `docs/DECISIONS.md` | n/a |
| 2 | OSM relations that match by name but not `from`/`to` | dropped | Follows from item 1 | n/a |
| 3 | Exact pin for each of the 11 named places | open | See pin table below | `data/README.md` |
| 4 | The 10 test trips and expected colors | open | Written before planner work | `tests/test_trips.py` |
| 5 | Decisions assumed | answered | See below | `docs/DECISIONS.md` |
| 6 | `TRANSFER_PENALTY_KM`, `WALK_COST_FACTOR` | deferred | Keep defaults 1.0 and 2.0; target is a balanced trade-off between transfers and walking. Tune on Day 3 after the first run of the 10 trips, one value per run, log each run in `DECISIONS.md` | `docs/DECISIONS.md` |

## Item 5: assumed decisions (confirmed)

1. Each color is exactly one named route. Yellow, Purple and Grey are one-way circular (`out` only); Blue, Red and Dark yellow run in two directions (9 records). Variants, if found later, get their own `route_id` and a registry entry.
2. The map page is in scope.
3. English only.
4. Reports are public immediately. Known risk: no moderation; the maintainer edits `status` in SQL. Record in `DECISIONS.md`.

## Item 3: pin table

| Place | Used by | Real boarding spot (name) | lat | lng |
|---|---|---|---|---|
| Villa | Yellow | | | |
| Pampang | Yellow, Blue (shared stop) | | | |
| Pandan | Blue | | | |
| Checkpoint | Purple, Grey (shared stop) | | | |
| Holy | Purple | | | |
| Highway | Purple, Grey (shared stop) | | | |
| Balibago | Grey | | | |
| Sapang Bato | Red | | | |
| Angeles | Red | | | |
| Main Gate | Dark yellow | | | |
| Friendship | Dark yellow | | | |

Take coordinates from OSM, not Google. Shared stops must use one `stop_id` on every route they appear on.

## Item 4: test trips

Filled in from the maintainer's list. Target mix: at least 2 single-jeep, at least 2 transfers, 1 using the Purple/Grey shared ends, 1 using the Yellow/Blue shared end, 1 in the `back` direction.

| # | From | To | Expected colors in order |
|---|---|---|---|
| 1 | | | |

## Also before publishing

- Read the ODbL terms on the OpenStreetMap copyright page (SPEC Section 13) before the repository is made public. `routes.geojson` line geometry comes from OSRM on OSM road data.
- Pre-flight: Docker, Compose, Python, `git` and a GitHub repo with Actions enabled.
