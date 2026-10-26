# T010 owner answers (resolve spec.xml clarifications 1-14). These override spec.xml where they differ.
A. Step fields: exactly SPEC 6.3 names. stops_passed = "{n} stops". Ride km = distance_m/1000, max 2 decimals. Walk meters rounded.
   Transfer: walk_m 0 -> "Transfer to {Color} at {from}"; walk_m > 0 -> "Transfer to {Color} at {from} (walk {n} m)". Only {from} shown even if from != to.
   Walk: "Walk 180 m to Dau Terminal" format.
B. May change drawRoute/load to fill global list (route_id, color, direction, line coords, stops by seq incl. repeated first/last on circular routes) and keep layer refs for hide/restore.
   May add: origin/destination prompt, panel message element, steps container, summary container.
   Prompt text: "Tap the map to set your origin" / "Tap the map to set your destination". Hidden while request pending; removed after a result; stays hidden after failure (returns only on Reset).
   One shared "locked" check inside setPoint (covers pending + after result + after failure). Taps ignored until Reset.
C. Banner 5s clear + clear on Reset/next Find route apply ONLY to plan banners and "Incomplete origin and destination selection."; map-load messages stay persistent and are not cleared by Reset.
   "No match found": panel only (no banner); cleared on Reset and next Find route; ALSO disappears after 5 seconds; steps and summary stay visible after it disappears. Retry after it re-fetches /api/plan.
   Plan with no ride steps: show steps+summary, hide nothing, fit nothing.
   Wraparound = destination stop index lower than origin index within chosen pair -> skipped -> "No match found". Pair crossing a circular seam (using repeated end stop with higher index) is NOT wraparound.
   Disabled button is enough vs double clicks; no extra guard.
   Unlisted failures: 404 route_not_found -> "Route doesn't exist." ; 503 database_unavailable -> internal_error text ("Something went wrong. Please try again."); unknown error code -> same; non-JSON body -> same. Unexpected 200 shape: no handling (contract defined).
D. Highlight weight 8, existing fitBounds padding, tint alpha 0.50 of route hex (rgba), inherited text color.
