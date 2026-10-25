# Open Items Register

Tracks the open items from `SPEC.md` Section 15. Status: `open`, `answered`, `deferred`.

| # | Item | Status | Answer / next step | Lives in |
|---|---|---|---|---|
| 1 | Which of the 9 route records exist in OSM | dropped | All 9 route records are hand-traced (no OSM route import); see `docs/DECISIONS.md` | n/a |
| 2 | OSM relations that match by name but not `from`/`to` | dropped | Follows from item 1 | n/a |
| 3 | Exact pin for each of the 11 named places | draft | Candidates from `waypoints.csv` in the pin table below; maintainer confirms | `data/README.md` |
| 4 | The 10 test trips and expected colors | deferred | Maintainer writes them after the data pipeline (Day 2 Track A); needed before the first trip run | `tests/test_trips.py` |
| 5 | Decisions assumed | answered | See below | `docs/DECISIONS.md` |
| 6 | `TRANSFER_PENALTY_KM`, `WALK_COST_FACTOR` | deferred | Keep defaults 1.0 and 2.0; target is a balanced trade-off between transfers and walking. Tune on Day 3 after the first run of the 10 trips, one value per run, log each run in `DECISIONS.md` | `docs/DECISIONS.md` |
| 7 | Day 1 architecture review: error-code seam, startup loader | deferred | Maintainer moved both blocking findings to Day 3 | `docs/DECISIONS.md` |

## Item 5: assumed decisions (confirmed)

1. Each color is exactly one named route. Yellow, Purple and Grey are one-way circular (`out` only); Blue, Red and Dark yellow run in two directions (9 records). Variants, if found later, get their own `route_id` and a registry entry.
2. The map page is in scope.
3. English only.
4. Reports are public immediately. Known risk: no moderation; the maintainer edits `status` in SQL. Record in `DECISIONS.md`.

## Item 3: pin table

The pin table lives in [`data/README.md`](../data/README.md#pin-table) (single source; not duplicated here). Status: draft, maintainer confirms.

Data finding: the SPEC says Purple/Grey share Checkpoint and Highway and Yellow/Blue share Pampang, but the CSV has no Checkpoint or Highway stops. Purple/Grey already share about 35 stops, so that transfer works. Yellow and Blue's two nearest stops (55 m apart) are both named `Pampang`, which creates the Yellow/Blue transfer.

Known data gaps (details in `data/README.md`): Checkpoint/Highway are not named stops; Jurio Foodhouse (`purple_out`, `grey_out`) is a placeholder pin until the maintainer supplies coordinates; blue out/back direction versus the SPEC registry (Pandan to Pampang) is unresolved.

## Day 2 Track A (route data) status

Done: `waypoints.csv`, `snap_routes.py`, `routes.geojson` (snapped 2026-10-25), `validate.py` (CI), `seed.py`, `tests/data/`, `data/README.md`. Open: maintainer's real Jurio Foodhouse pin, pin confirmations, ridden verification of the 9 routes.

## Item 4: test trips

Filled in from the maintainer's list. Target mix: at least 2 single-jeep, at least 2 transfers, 1 using the Purple/Grey shared ends, 1 using the Yellow/Blue shared end, 1 in the `back` direction.

| # | From | To | Expected colors in order |
|---|---|---|---|
| 1 | | | |

## Also before publishing

- Read the ODbL terms on the OpenStreetMap copyright page (SPEC Section 13) before the repository is made public. `routes.geojson` line geometry comes from OSRM on OSM road data.
- Pre-flight: Docker, Compose, Python, `git` and a GitHub repo with Actions enabled.
