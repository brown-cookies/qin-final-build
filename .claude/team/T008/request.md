# T008 request (owner-decided, verbatim summary)

Day 3 midday, slice 2: map page with the six route lines. Do exactly this and nothing else.

DECIDED FIELDS (owner-confirmed):
- MESSAGE PLACEMENT: a banner over the map, for both the failed-request and empty-data messages.
- Failed request text: "We couldn't load the jeepney routes. Check your connection and refresh the page."
- Empty data text: "No route data is available."
- PANEL STRUCTURE: one empty, visible container element for the future side panel (e.g. <aside id="panel">) with no children, no text, no behavior.

Spec:
1. Files: web/index.html, web/map.js, web/style.css, plus vendored Leaflet 1.9.4 in web/ (leaflet.js, leaflet.css, marker images, BSD-2 license file). Download from npm package or official release; no CDN at runtime. No build step.
2. Map: Leaflet with OSM tiles. Show "(c) OpenStreetMap contributors" attribution on the page (NFR-4).
3. Colors defined once in map.js and used everywhere else from there:
   yellow #FACC15, blue #0052B4, purple #6A1B9A, grey #757575, red #D32F2F, darkyellow #B8860B
4. Data: fetch GET /api/routes, then GET /api/routes/{route_id} for all 9 records in parallel. Detail response is a GeoJSON FeatureCollection: one LineString plus one Point per stop (properties: name, seq). GeoJSON is [lng, lat]; Leaflet wants [lat, lng].
5. Lines colored by color group; out and back of a color share color and style.
6. Stops: small dots, drawn once per route (shared stop drawn once per route), name shown on click, display-only. No picking.
7. View: fit map to bounds of loaded lines.
8. Legend: one entry per color with names Yellow, Blue, Purple, Grey, Red, Dark yellow.
9. Failure: if /api/routes or any detail request fails, draw no lines and show failed-request banner.
10. Empty data: if /api/routes returns [], show empty-data banner.
11. Layout: desktop only, no responsive/phone CSS. Include the empty panel container, no behavior.

Constraints:
- Follow CLAUDE.md. No third-party service at runtime except OSM tiles.
- No backend changes, no new endpoints, no docs edits.
- No stop picking, taps, plan call, steps panel behavior (later slices).
- If anything is missing or conflicts with SPEC or the code, STOP and report it as a clarification. Do not assume.
- Map behavior cannot be tested by pytest; it is listed for the owner to check in a browser.

Known thing to check: slice 1 added tests/api/test_static.py asserting "Hello world" in GET /. Replacing the placeholder index.html may break it.
