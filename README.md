# Biyahe Angeles

Plain-language jeepney directions for Angeles City. Pick where you are and where you are going, and get steps like:

> Walk to Dau Terminal, ride Yellow to Balibago Plaza, transfer to Red, get off at SM Clark, walk to your destination.

Working name. Covers the six color-coded routes, where Yellow, Purple and Grey are one-way circular routes and Blue, Red and Dark Yellow run in two directions (9 route records): Yellow, Blue, Purple, Grey, Red and Dark Yellow. See [SPEC.md](SPEC.md) for the full specification.

> **Status:** MVP complete, built in a 3-day sprint (plan: [docs/roadmap.md](docs/roadmap.md)). The planner, API, data pipeline, tests and map page work; the routes are hand-traced and not yet ridden, and a few things were left out on purpose. Read [Limitations](#limitations) before relying on a plan.

![Map page on first load: the six route lines, the legend and the prompt to tap an origin](docs/images/map-page-initial-load.png)

_First load: the six routes in their colors, with the panel asking for an origin._

![A planned trip: Red, then Grey, then Blue, with the steps listed and the three rides highlighted on the map](docs/images/map-page-sample-route.png)

_A planned trip with two transfers. Each ride is highlighted on the map and listed in the panel, followed by the one-line summary._

## Routes

| Color | Route | `out` direction |
|---|---|---|
| Yellow | Villa - Pampang | Villa to Pampang |
| Blue | Pandan - Pampang | Pandan to Pampang |
| Purple | Checkpoint - Holy - Highway | Checkpoint to Highway |
| Grey | Checkpoint - Balibago - Highway | Checkpoint to Highway |
| Red | Sapang Bato - Angeles | Sapang Bato to Angeles |
| Dark yellow | Main Gate - Friendship | Main Gate to Friendship |

Route IDs are `{color}_{direction}`, for example `yellow_out`, `darkyellow_back`.

## Quick start

Requires Docker with Compose.

```bash
docker compose up                                  # API + PostgreSQL
docker compose run --rm api python -m data.seed    # one-time: load route data (validates first, safe to re-run)
docker compose restart api                         # required after seeding: route data is loaded once at startup
```

Then open:

- Map page: <http://localhost:8000/>
- Interactive API docs: <http://localhost:8000/docs>
- Health: <http://localhost:8000/health>

Host ports can be moved with `API_PORT` and `POSTGRES_PORT` if 8000 or 5432 is taken. If `/health` shows `route_data: empty`, the API started before the seed: run the restart line above.

### Using the map page

Tap the map (or a stop dot) to set your origin, then your destination, then press **Find route**. The page lists the steps and highlights each ride on the map; **Reset** clears the trip. Hovering a stop dot shows its name. The page does not yet have stop-name search or a report form: use `/api/stops` and `/api/reports` (or `/docs`) for those.

### Run the tests

```bash
pytest
```

233 tests. They run against a test PostgreSQL database (`TEST_DATABASE_URL`, default `postgresql://biyahe:biyahe@127.0.0.1:5432/biyahe_test`; `docker compose up db` provides the server). Use `127.0.0.1`, not `localhost`: on Windows `localhost` tries IPv6 first and stalls. `tests/planner/` and `tests/test_trips.py` do not need Postgres. CI runs the same suite plus `data/validate.py` on every push (GitHub Actions with a Postgres service container).

## API

Base path `/api`, except `/health`. Errors always have the shape `{"error": "<code>", "message": "<plain text>"}`.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/plan?from_lat=&from_lng=&to_lat=&to_lng=` | Plan a trip; returns ordered steps and a one-line `summary` |
| `GET` | `/api/routes` | List the 9 route records |
| `GET` | `/api/routes/{route_id}` | Route line and ordered stops as GeoJSON |
| `GET` | `/api/stops?q=` | Stop-name search (case-insensitive, up to 10) |
| `POST` | `/api/reports` | Submit a route problem report (validated, stored in PostgreSQL) |
| `GET` | `/api/reports?limit=10` | Most recent reports, newest first (`limit` 1-50) |
| `GET` | `/health` | `200` when the process is up; `database: up \| down`, `route_data: loaded \| empty` (`empty` means restart the API after seeding) |

Error codes: `invalid_location` (400), `no_stop_nearby` (404), `no_route` (404), `route_not_found` (404), `validation_error` (422), `database_unavailable` (503), `route_data_unavailable` (503, `/api/plan` when no route data was loaded at startup), `internal_error` (500). Details in [SPEC.md](SPEC.md) Sections 6 and 12.

### Example: plan a trip

```bash
curl 'localhost:8000/api/plan?from_lat=15.1379&from_lng=120.5890&to_lat=15.1655&to_lng=120.5590'
```

Returns `{"steps": [...], "summary": "..."}`. Steps are `walk`, `ride` and `transfer` objects (SPEC Section 6.3). All four parameters are required and must be inside `SERVICE_BBOX`; anything else is `400 invalid_location`. `404 no_stop_nearby` says whether the starting point or the destination has no stop within `WALK_RADIUS_M`; `404 no_route` means stops exist at both ends but no jeep connects them.

### Example: routes and stops

```bash
curl localhost:8000/api/routes                  # 9 items, ordered by route_id
curl localhost:8000/api/routes/yellow_out       # GeoJSON: the line, then one Point per stop in order
curl 'localhost:8000/api/stops?q=pampang'       # literal, case-insensitive match; %, _ and quotes are plain text
```

Route data is read once at startup, so `/api/plan`, `/api/routes` and `/api/stops` keep working if the database goes down; after a re-seed, restart the API. `q` is required (empty or whitespace-only is `422`).

### Example: submit a report

```bash
curl -X POST localhost:8000/api/reports \
  -H 'Content-Type: application/json' \
  -d '{"route_color": "yellow", "message": "Jeep no longer stops at this corner", "lat": 15.16, "lng": 120.59}'
```

`route_color` is one of `yellow | blue | purple | grey | red | darkyellow | other`. `lat` and `lng` mark where the problem is and must be given together or not at all.

## Configuration

Environment variables, all with defaults:

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | set in compose | Postgres connection |
| `SERVICE_BBOX` | `15.08,15.22,120.50,120.68` | `lat_min,lat_max,lng_min,lng_max`; requests outside are rejected |
| `WALK_RADIUS_M` | `500` | Max walk from a point to a stop |
| `TRANSFER_RADIUS_M` | `100` | Stops within this distance count as one transfer point |
| `TRANSFER_PENALTY_KM` | `1.0` | Flat cost each time you board a jeep |
| `WALK_COST_FACTOR` | `2.0` | Walking costs this many times riding, per km |

## How it works

FastAPI serves a JSON API and a static Leaflet map page. A pure-Python planner (Dijkstra) runs over an in-memory graph built once at startup from route data in PostgreSQL; a plan takes about 1 ms (measured in process on a Ryzen 7 5700X, see DECISIONS). Reports are the only user-written data. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the layers, the planner definition and degraded modes, and [docs/DECISIONS.md](docs/DECISIONS.md) for why each tool was chosen, what was cut, measured results and the bugs found along the way.

```
SPEC.md                    what to build (source of truth)
docs/ARCHITECTURE.md       how it fits together
docs/DECISIONS.md          why, cuts, measurements, bugs, known limitations
docs/OPEN_ITEMS.md         what is still open
data/README.md             route provenance, pin table, data gaps
```

## Route data

Route data is created offline and committed as `data/routes/routes.geojson`. All 9 routes are hand-traced waypoints, snapped to roads with OSRM (offline script). Provenance per route, the snap date, the pin table and known gaps are in [data/README.md](data/README.md).

Check the data with `python data/validate.py` (no database or network; exits non-zero on any problem; also runs in CI). Load it with `python -m data.seed`, which validates first, then replaces the route tables in one transaction. Re-seeding is safe and never touches reports.

## Limitations

Short list; the full list with numbers is in [docs/DECISIONS.md](docs/DECISIONS.md#known-limitations).

- **Jeepneys only.** No fares, tricycles, buses, schedules, real-time tracking, accounts or Tagalog UI.
- **The routes are unverified.** All 9 are traced from memory and snapped to roads; none has been ridden. A plan is a best guess, not a promise that a jeep will stop where it says. One pin (Jurio Foodhouse) is a placeholder, and Checkpoint and Highway are not named stops ([data/README.md](data/README.md)).
- **The planner is simple.** Ride distance is a straight line between stops, and it assumes every stop is boardable (a jeep that is already full at a stop is not modelled). Walking at either end can reach about 600 m although `WALK_RADIUS_M` is 500, because a short stop-to-stop walk is added to it.
- **Measured against 10 trips only.** 10 of 10 pass, one of them on a widened answer. The cost values were not tuned.
- **Route data loads once at startup.** Restart the API after seeding.
- **Reports are public and unmoderated**, with no rate limit.
- **Map page gaps.** No stop search, no report form, not laid out for phones. The ride highlight can pick the wrong stop pair, or say "No match found", on Grey and Purple rides that pass the same place twice; the steps list is always right.
- **Not production-ready.** Dev database credentials are in `docker-compose.yml`, CI has not been observed running on GitHub, and nothing was load-tested.

## Attribution and license

Map tiles and route data derived from OpenStreetMap: **(c) OpenStreetMap contributors**, available under the [Open Database License](https://www.openstreetmap.org/copyright). Route line geometry in `data/routes/routes.geojson` comes from OSRM, which runs on OSM road data, so treat it as OSM-derived and subject to ODbL conditions.

**Project license: not chosen yet.** Decide after reading the ODbL terms (SPEC Section 13), since `routes.geojson` is OSM-derived and carries ODbL conditions. Leaflet in `web/` is BSD-2-Clause (`web/LICENSE`).
