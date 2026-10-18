# M09 · CONTRACT

Paths relative to `/home/claude/baton/`. Everything below is copied from `server/app.py` unless marked PROPOSED.

## 1. Process and configuration (EXISTS)
| Item | Value | Source |
|---|---|---|
| Framework | FastAPI app `app = FastAPI(title="Baton API")` | server/app.py:4, server/app.py:13 |
| CORS | all origins, methods, headers | server/app.py:14 |
| Start command (container) | `uvicorn server.app:app --host 0.0.0.0 --port 8000` | deploy/Dockerfile:10 |
| Python packages | `fastapi==0.115.0`, `uvicorn==0.30.6`, `falkordb==1.8.0`, `redis==8.1.0`, `openai>=1.40` | deploy/requirements.txt:1-5 |
| Image | `python:3.12-slim`; copies `baton`, `server`, `fixtures` (not `web`, not `checks`) | deploy/Dockerfile:1, deploy/Dockerfile:5-7 |
| `BATON_DATA` | folder for worlds; default `/tmp/baton_data`; image sets `/data` | server/app.py:9, deploy/Dockerfile:8 |
| `FALKORDB_PORT` | default `6379`; passed to the CLI as `--port` | server/app.py:10, server/app.py:75-76 |
| `FALKORDB_HOST` | default `localhost`; passed to the CLI via the environment; the CLI reads it | server/app.py:11, server/app.py:18, baton/graph.py:21 |
| Compose | `falkordb` (`falkordb/falkordb:v4.22.1`, ports `127.0.0.1:6379` and `127.0.0.1:3000`), `api` (build from `deploy/Dockerfile`, port `8000:8000`, `FALKORDB_HOST: falkordb`) | docker-compose.yml:1-15 |

## 2. How a CLI call works (EXISTS, server/app.py:17-23)
- Runs `[sys.executable, "-m", "baton", *args]` in the repo root, captures output, `timeout=300`.
- Non-zero exit → `HTTPException`: status **503** if `"falkordb"` appears (any case) in stderr+stdout, otherwise **500**; detail = last 800 characters of stderr (or stdout if stderr is empty) (server/app.py:21-22).
- Success → parsed JSON if stdout starts with `{` or `[`, otherwise the raw string (server/app.py:23).
- The CLI prints FalkorDB connection errors as `FalkorDB is not reachable at <host>:<port>: ...` and exits 3 (baton/graph.py:26, baton/graph.py:30-32), so those map to 503.

## 3. World folder (EXISTS, server/app.py:26-37)
- Folder `BATON_DATA/seed_<seed>`.
- Under a process lock: if `world.json` is missing → `generate --seed <seed> --out <folder>`.
- If `beliefs.json` is missing → copy `fixtures/beliefs_seed<seed>.json` if it exists; else run `extract --world <folder> --out <folder>/beliefs.json` (no `--offline`). The seed-7 fixture was deleted in commit `84747c6`, so this `extract` call now always runs; see 1_SPEC.md.

## 4. Enrichment (EXISTS, server/app.py:40-55)
For each row: adds `duty_name` (from `world.duties[].name`, or the belief's `duty_name`), and replaces `sources` (list of ids) with a list of objects:
| field | type | value |
|---|---|---|
| `id` | str | the source id |
| `type` | str | `"message"`, `"joblog"`, `"ticket"`, `"record"`, or `"?"` if unknown |
| `text` | str | message/ticket text; for a joblog `x.get("text")` or `"<job> run by <actor>: <status>"`; for a record, `key=value` pairs except `id`; `""` if unknown |
Source: server/app.py:44-54.

## 5. Routes (EXISTS)

### `GET /api/health` (server/app.py:58-66)
Pings FalkorDB at `FALKORDB_HOST:FALKORDB_PORT`. Success: `{"ok": true, "falkordb": "<host>:<port>"}`. Failure: HTTP 503 with detail `FalkorDB is not reachable at <host>:<port>: <error>`. It does not call the CLI.

### `GET /api/demo?seed=7` (server/app.py:69-82)
Query: `seed` int, default 7.
Runs `rehearse` three times (lanes `W`, `R`, `G`, all with `--confirm all`, the world's `leaver`).
Response:
| field | type | source |
|---|---|---|
| `seed` | int | request |
| `now`, `day_ms`, `window_days`, `leave_at` | int | world.json (baton/generate.py:449-450 at HEAD 85eeabd) |
| `leaver` | str | world.json |
| `leaver_name` | str | `people[leaver].name` |
| `people` | list of `{id, name, team, role, left_at}` | world.json (baton/generate.py:204-205 at HEAD 85eeabd) |
| `lanes` | `{"W": {"failures": [row]}, "R": {...}, "G": {...}}` | each row = rehearse failure `{duty, at, day, event, label, status, sources}` (baton/rehearse.py:146-147) + enrichment (§4) |
| `unpromoted` | list of `{belief, reason}` | from the **last** call (lane G) (server/app.py:81, baton/rehearse.py:94) |
| `live_hash_before`, `live_hash_after` | str (hex sha256) | from the last call (server/app.py:82, baton/graph.py:44) |

Note: `lanes.<X>.failures` is a **list of rows** here, while the CLI `demo` command returns an **int** count (`lanes[lane] = {"failures": len(rows)}` in baton/demo.py `run`). Do not mix them up.

### `POST /api/handover` (server/app.py:85-99)
Body (pydantic `Handover`): `seed: int = 7`, `assign: dict` (duty id → person id) (server/app.py:85-87).
Runs `handover` with one `--assign duty=person` per entry (server/app.py:94-97).
Response: the CLI JSON `{leaver, graph, accepted:[{duty, person}], refused:[{duty, person, reason}], failures_after:[row], live_hash_before, live_hash_after}` (baton/handover.py:89-91), with `failures_after` enriched (server/app.py:98).
Note: a dict cannot hold two people for one duty, so the "second owner refused" case (checks/locked/rehearsal_core/test_rehearsal_core.py:188-191) cannot be sent through this route.

### `POST /api/ask` (server/app.py:102-110)
Body (pydantic `Ask`): `seed: int = 7`, `question: str`.
Runs `ask --world --beliefs --question --port` and returns its JSON unchanged (no enrichment): `{question, tool, args, cypher, graph, router, rows, sources, answer, live_hash_before, live_hash_after}` (baton/ask.py:310-323). `tool` ∈ `owes`, `breaks_if_leaves`, `why`, `covers`, `who_owns`, `none` (baton/ask.py:71-78). `sources` is a sorted list of source **ids** (baton/ask.py:322), not the `{id, type, text}` objects the other routes return. For `none`, `rows` and `sources` are empty and `answer` starts "That is not in the graph." (baton/ask.py:80-81, baton/ask.py:312-317).
The locked checks call `ask` with `--offline` (checks/locked/ask/test_ask.py:18); the API does not. Today this changes nothing (the router is deterministic either way, baton/ask.py:299, baton/ask.py:310-311). PROPOSED: pass `--offline` anyway, so a future model router never runs by surprise.

## 6. Status codes
| Code | When | Source |
|---|---|---|
| 200 | CLI succeeded | FastAPI default |
| 422 | body or query fails pydantic validation | FastAPI default behaviour; not run by us (UNTESTED) |
| 500 | CLI failed without "falkordb" in its output (for example: no beliefs for the seed, `extract` cache miss or no model key, unknown leaver) | server/app.py:22 |
| 503 | CLI failed with "falkordb" in its output | server/app.py:22 |

## 7. PROPOSED additions (not in code; owner: Joyal)
- `GET /api/cut?seed=7` → `cli("cut", ...)` (M06 contract).
- `POST /api/write` with body `{seed, assign}` → run `handover`, save its JSON, then `cli("write", "--handover", file, "--target", ...)` (M06 contract).
- Load the graph inside the lock in `world_dir` (1_SPEC.md gap 2).
- A `gitea` service in compose with host port other than 3000 (M06 2_CONTRACT.md).
