T001 | pipeline | verify iteration 1 | passed
T002 | pipeline | route/clarify | blocked_on_user
T002 | pipeline | implement (docs only) | in_progress
T002 | pipeline | verify (grep + link check) | passed
T003 | pipeline | verify iteration 1 | passed
T004 | pipeline | verify iteration 2 | passed
T004 | pipeline | minimal-planner audit (read-only) | done
T005 | pipeline | plan (empty-data signal + restart doc) | in_progress
T005 | pipeline | implement iteration 1 | in_progress
T005 | pipeline | verify iteration 1 | in_progress
T005 | pipeline | verify iteration 1 | passed
T005 | pipeline | implement iteration 2 (re-run after lost work) | in_progress
T005 | pipeline | verify iteration 2 | in_progress
T005 | pipeline | verify iteration 2 | passed
T006 | pipeline | plan (circular wrap edge, trip 8) | in_progress
T006 | pipeline | implement iteration 1 | in_progress
T006 | pipeline | implement iteration 1 (trip 8 still fails, criteria 9/10 unmet) | escalated
T007 | pipeline | plan (serve web/ at /) | in_progress
T007 | pipeline | implement iteration 1 | in_progress
T007 | pipeline | verify iteration 1 | in_progress
T007 | pipeline | verify iteration 1 (1 existing test broken by mount-last; spec conflict) | blocked_on_user
T007 | pipeline | implement iteration 2 (fix /_boom test ordering) | in_progress
T007 | pipeline | verify iteration 2 | in_progress
T007 | pipeline | verify iteration 2 (233 passed, verifier pass) | passed
T008 | pipeline | plan (map page with route lines) | in_progress
T008 | pipeline | plan (5 clarifications) | blocked_on_user
T008 | pipeline | implement iteration 1 | in_progress
T008 | pipeline | verify iteration 1 | in_progress
T008 | pipeline | verify iteration 1 (233 passed; browser checks pending owner) | passed
T008 | pipeline | verify iteration 2 (re-run on Docker stack, no code change) | in_progress
T008 | pipeline | verify iteration 2 (Docker stack, 233 passed, headless Chrome render) | passed
T008 | pipeline | owner browser check (map, popup, colors, failure + empty banners) | done
