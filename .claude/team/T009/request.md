# T009 request: Day 3 midday, slice 3 (map taps, markers, panel buttons, reset)
Branch: feat/map-tap-points (slice 2 merged). Makes NO API call.

Spec (owner-decided):
1. Files: web/index.html, web/map.js, web/style.css only. Build on existing slice 2 code; do not rewrite it.
2. Tap flow: first tap on map sets origin, second sets destination, further taps ignored until Reset. A tap on a stop dot counts as a tap and sets the point to (A) THE DOT'S OWN POSITION (owner confirmed A). The dot click must not also fire the map click handler (no double count).
3. Markers: Leaflet default marker (vendored web/images/) at each chosen point. Origin and destination use the same icon.
4. Stop dots: name popup opens on hover (mouseover), not on click.
5. Panel (existing empty <aside id="panel">): two buttons inside, at the top.
   - "Find route": present, enabled, does nothing.
   - "Reset": clears both markers, returns to "pick origin" state.
6. Not in slice: no /api/plan call, no loading state, no banner changes (banner not cleared/hidden), no steps list, no highlighting, no stop-data storage.
7. Desktop only, no responsive CSS.

Constraints: follow CLAUDE.md; no third-party service except OSM tiles; no build step; no backend changes, no new endpoints, no docs edits; do not stage/commit .claude/team/*; never commit or push. If anything is missing or conflicts with SPEC/code, stop and ask; do not assume.
Run pytest and report real output incl. failures. Tap behavior cannot be tested by pytest.
