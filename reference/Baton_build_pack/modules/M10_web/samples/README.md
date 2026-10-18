# Real API samples (captured 18 Oct, about 12:25 IST, from a local run against FalkorDB v4.22.1)

These files are **real responses** from `server/app.py` running against a real FalkorDB with the seed-7 company and its cached AI extraction. **Build the frontend against these files.** The hand-written files in `web/mock/` are out of date: wrong names (Priya instead of Hana Sharma), wrong counts and invented fields. Delete them.

| File | Request |
|---|---|
| `api_demo_seed7.json` | `GET /api/demo?seed=7` |
| `api_handover_seed7.json` | `POST /api/handover {"seed":7,"assign":{"d-job-warehouse-snapshot":"felix.petrov","d-tls-ledger":"ingrid.tanaka"}}` |
| `api_ask_breaks_seed7.json` | `POST /api/ask {"seed":7,"question":"What breaks if Hana Sharma leaves?"}` |
| `api_ask_owes_seed7.json` | `POST /api/ask {"seed":7,"question":"What does Hana Sharma owe?"}` |
| `api_ask_why_seed7.json` | `POST /api/ask {"seed":7,"question":"Why is Warehouse snapshot to cold storage Hana Sharma's job?"}` |

## Facts the UI must respect
- Lane counts in `lanes.*.failures` are **events**: W 6, R 7, G 37. The daily warehouse job alone has 29 events. Show **duties** as the headline number (count distinct `duty` values per lane) and draw one mark per event on that duty's row of the timeline.
- `status` is one of `record` (from a system of record), `confirmed` (a gate-passed AI belief, person said yes), or `believed` (gate-passed, not yet confirmed). Use one colour per status, plus a text label.
- `sources[]` carries `{id, type, text}` with type `record | message | joblog | ticket`. Quote the text in the proof drawer.
- `unpromoted[]` lists beliefs the gate refused, each with its `reason`. Show them as "what the AI claimed but couldn't prove".
- `live_hash_before == live_hash_after` shows the real graph was untouched. Show it as a badge.
- In the handover sample, `ingrid.tanaka` is refused because she has already left. That is a good demo moment: the database refuses, not the UI.
- Not in the API yet: per-row Cypher, a `ghost_duties` list, and person names on lane rows. Derive ghost duties as G rows whose status is `confirmed` or `believed`. For the proof drawer, use `cypher` from `/api/ask` (breaks_if_leaves) or `GET`-able catalogue text from `python -m baton ask --catalogue`.
- `/api/health` returns 503 with a FalkorDB message when the database is down. Show that loudly. Never fall back silently to old data without a visible "replay data" badge.
