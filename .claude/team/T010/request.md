# T010 request: Day 3 midday (plan call, steps list, highlight and hide, errors)
Final front-end. Do exactly this and nothing else. Keep each change small enough to review line by line.

## Owner answers to OPEN fields
- RETRY AFTER FAILURE: retry is allowed (after plan errors and after "No match found") without Reset. It reuses the same two tapped points; no need to change them.
- TINT STRENGTH: alpha 0.50 (exact half) for the ride step line background tint. Text color: not specified by owner; leave inherited page text color (no new decision). Flag yellow/darkyellow readability in Verify.

## Spec (owner)
Request flow
1. Find route calls GET /api/plan with from_lat, from_lng, to_lat, to_lng from the two tapped points. No browser-side service-area check; the API returns invalid_location.
2. With fewer than two points, Find route shows the banner "Incomplete origin and destination selection." and makes no request.
3. While a request is pending: the panel shows "Finding route…", and Find route, Reset and map taps are disabled or ignored.
4. After a successful result, Find route stays disabled until Reset. After failures (plan error or "No match found"), Find route can run again without Reset.

Errors (banner over the map; clears on Reset, on the next Find route, and after 5 seconds)
5. invalid_location: "That location is outside the service area."
   no_stop_nearby: "No stops nearby."
   no_route: "No route found."
   validation_error: "The request wasn't valid. Please try again."
   route_data_unavailable: "No available routes."
   internal_error: "Something went wrong. Please try again."
   network failure: "Network failure. Refresh the page and try again."
6. After any error, all routes stay visible.

Panel order: buttons, steps list, summary.
7. Steps list, Format 1, one line per step, API wording:
   walk:     "Walk {distance} to {to}"      (meters, e.g. 180 m)
   ride:     "Ride {Color label} from {from} to {to} ({n} stops, {km} km)"   (km; singular "1 stop")
   transfer: "Transfer to {to_color label} at {from}"   (no distance when walk_m is 0; if walk_m > 0 show it in meters)
   - Color names use the legend labels (Yellow, Blue, Purple, Grey, Red, Dark yellow). Do not show direction (out/back).
   - Keep API wording for from/to incl. "Your start point" and "Your destination".
   - Ride step lines get a background tint in the route color at alpha 0.50.
8. The API's summary sentence appears under the steps.

Highlight and hide
9. On page load, store one global list: per route record, the line coordinates and each stop's name and position in order.
10. For each ride step, find its route record by color and direction. Match step from/to to stop names by exact string equality. If a name occurs more than once on that record, use the pair giving the shortest stretch of line between them.
11. Highlight the portion of that route's line between the points on the line nearest to each of the two stops, drawn thicker in the route's color.
12. Hide every other line. Keep dots only for board and alight stops of each ride. Tap markers stay visible. Legend stays at all six.
13. Wraparound rides (destination before origin in stop order) are skipped. If any ride in the trip cannot be matched or is skipped, show "No match found" in the panel and leave everything visible (no hiding).
14. When the highlight is drawn, fit the map to the highlighted segments.
15. Reset restores all lines and dots, clears steps, summary, highlight and any panel message, and returns to "pick origin".

## Constraints
- Follow CLAUDE.md. No third-party service at runtime except OSM tiles. No build step.
- Files: web/index.html, web/map.js, web/style.css only. No backend changes, no new endpoints, no docs edits.
- Do not stage or commit .claude/team/* files. Never commit or push.
- If anything is missing or conflicts with SPEC or the code, stop and ask. Do not assume.
- Do not claim done/working. Run pytest and report real output. Browser behavior is listed under Verify for the owner.
