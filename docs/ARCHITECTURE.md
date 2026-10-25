# Architecture

See SPEC.md Section 2 for the runtime diagram and Section 10 for the planner definition. Day 3 expands this file.

## Route data pipeline (offline)

```
data/raw/waypoints.csv -> data/snap_routes.py (OSRM) -> data/routes/routes.geojson (committed)
                       -> data/validate.py (CI, no DB) -> data/seed.py -> PostgreSQL (route, stop, route_stop)
```

- `snap_routes.py` snaps hand-traced waypoints, densifies lines to at most 40 m and checks every waypoint is within 50 m of its line. It is the only step that uses the network.
- `validate.py` checks `routes.geojson` against SPEC 9.3 with the standard library only. It prints one line per problem, exits 1 on failure; warnings do not fail.
- `seed.py` validates, applies `sql/schema.sql`, then calls `queries.replace_route_data`, which replaces `route_stop`, `route`, `stop` in one transaction. `report` is never touched. Seed SQL lives in `app/queries.py`.
