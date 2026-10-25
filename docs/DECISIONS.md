# Decisions

Per tool and per cut: what, why, rejected alternative. Measured results are added when measured. Entries for the remaining SPEC Section 3 tools and Section 15 cuts are written on Day 3.

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
