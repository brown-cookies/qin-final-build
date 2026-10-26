# T008 owner answers:
1. Edit the single assertion in tests/api/test_static.py::test_root_serves_placeholder_page (e.g. assert HTML containing the map container id). Change nothing else in tests.
2. Circular routes: one dot per distinct stop name per route (dedupe by name within a route).
3. Unknown color token: not handled.
4. No README/DECISIONS/docs edits; attribution on the page only.
5. Attribution: literal "(c) OpenStreetMap contributors" via tile layer attribution, link to https://www.openstreetmap.org/copyright allowed, Leaflet prefix as is.
Also: legend still renders when empty-data banner is shown; draw only after all 9 detail requests succeed.
