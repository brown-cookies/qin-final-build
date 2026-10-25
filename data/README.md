# Route data

Pipeline (offline, run by the maintainer; runtime and CI never call OSRM):

```
raw/waypoints.csv -> snap_routes.py (OSRM) -> routes/routes.geojson (committed) -> validate.py -> seed.py -> PostgreSQL
```

## Credit and licence

**(c) OpenStreetMap contributors**, available under the [Open Database License](https://www.openstreetmap.org/copyright).
Line geometry in `routes/routes.geojson` comes from the OSRM public server, which routes over OSM road data, so treat it as OSM-derived (ODbL conditions apply; read the terms before publishing). Stop positions are placed by hand from memory. No Google data is copied into the repository.

## Provenance

Snap date: **2026-10-25** (OSRM public server, driving profile, then densified to at most 40 m between points).

| Route record | Source | Ridden / checked on the ground |
|---|---|---|
| yellow_out | memory-traced | No (unverified) |
| blue_out | memory-traced | No (unverified) |
| blue_back | memory-traced | No (unverified) |
| purple_out | memory-traced | No (unverified) |
| grey_out | memory-traced | No (unverified) |
| red_out | memory-traced | No (unverified) |
| red_back | memory-traced | No (unverified) |
| darkyellow_out | memory-traced | No (unverified) |
| darkyellow_back | memory-traced | No (unverified) |

All 9 records are known gaps until someone rides them: `verified_on` is `null` in the file.

## Pin table

Exact boarding spot for each named place in the SPEC Section 7 registry. Stop name and coordinates are exactly as in `raw/waypoints.csv`. "Confirm" = candidate is a judgment call; "Open" = no matching stop in the CSV. This table is the single source; `docs/OPEN_ITEMS.md` links here.

| Place | Used by | Real boarding spot (name) | lat | lng | Status |
|---|---|---|---|---|---|
| Villa | Yellow | Yellow Terminal | 15.1231986 | 120.5996147 | Confirm (no stop named Villa) |
| Pampang | Yellow, Blue (shared stop) | Pampang (renamed from Yellow `BPI-BPO near Puregold` and Blue `Blue Terminal`) | 15.1379247 | 120.5889566 | Confirm. Coordinates are Blue's; Yellow's own point is 55 m away (15.1375495, 120.5892952), under the 100 m collision limit |
| Pandan | Blue | Blue End Terminal | 15.1621338 | 120.6079997 | Confirm (alt: Jollibee Pandan 15.1534383, 120.6046913) |
| Checkpoint | Purple, Grey (shared stop) | none | | | Open: no stop named Checkpoint |
| Holy | Purple | Holy Family Center | 15.1398379 | 120.5943962 | Matches (Blue shares it at 15.1397653, 120.5944138, 8 m apart) |
| Highway | Purple, Grey (shared stop) | none | | | Open: only `Mcdo near McArthur Highway` (Purple, 15.142698, 120.5965109); Grey has no match |
| Balibago | Grey | Balibago 7-Eleven Near Walking Street | 15.1676446 | 120.5897337 | Confirm (Purple shares this stop name) |
| Sapang Bato | Red | Angeles Sapangbato Terminal | 15.1417173 | 120.5879174 | Matches (Red and Purple share it) |
| Angeles | Red | Red Terminal | 15.1629156 | 120.5547028 | Confirm (Red `out` start; Dark yellow shares it) |
| Main Gate | Dark yellow | Dark Yellow Terminal | 15.1663974 | 120.5828311 | Confirm (not `HAU Main Gate`, which Dark yellow does not serve) |
| Friendship | Dark yellow | Red Terminal | 15.163142 | 120.5547793 | Confirm (Dark yellow end; 26 m from Red's coordinates, under the 100 m collision limit) |

Take coordinates from OSM, not Google. Shared stops must use one `stop_id` on every route they appear on.

When a `stop_id` appears on several routes, seed stores one `stop` row. Its name and coordinates come from the first occurrence with routes in sorted `route_id` order and stops in list order (so for Pampang, a Blue record wins over `yellow_out`).

## Known gaps

- Checkpoint and Highway are not named stops (see pin table). Purple and Grey still share about 35 other stops, so that transfer works.
- Jurio Foodhouse (`purple_out` waypoint 123, `grey_out` waypoint 98) uses a **placeholder** pin, the midpoint 15.1680300, 120.5835400. The maintainer will supply the real coordinates.
- Blue `out`/`back` direction versus the SPEC registry (Pandan to Pampang) is unresolved; the data is left as traced.
- All 9 routes are memory-traced and unverified (table above).
- Ride distance in the planner is straight-line between stops, not the snapped line length.

## Re-snap after a data change

1. Edit `raw/waypoints.csv` (add a via row on the correct road to fix a wrong line).
2. `python -m data.snap_routes --dry-run` checks waypoints against the registry with no network.
3. `python -m data.snap_routes` calls OSRM and rewrites `routes/routes.geojson`. `--reuse` re-processes the committed lines (densify, join check) with no network.
4. `python data/validate.py` (also runs in CI). Exit 1 and one line per problem on failure; lines starting with `WARNING` do not fail.
5. `docker compose run --rm api python -m data.seed` (or `python -m data.seed` with `DATABASE_URL` set). It validates first, applies `sql/schema.sql`, then replaces `route`, `stop` and `route_stop` in one transaction. It never touches `report` and is safe to re-run.

## validate.py rules

Thresholds are constants in `validate.py` (SPEC 9.3): bbox from `SERVICE_BBOX`; line gap over 50 m fails; stop over 100 m from its own line (nearest line point) fails; same `stop_id` on different routes over 100 m apart fails; two different `stop_id`s under 30 m apart warn. A `stop_id` repeated on one circular route is valid. An optional integer `seq` on stop objects is checked as 1..n in order; seed ignores it and uses list order.
