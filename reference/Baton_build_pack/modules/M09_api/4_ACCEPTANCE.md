# M09 · ACCEPTANCE

Paths relative to `/home/claude/baton/`.

## 1. Checks
**No locked or drafted API checks exist** (locked: rehearsal_core, ask, ai_layer, cut; pending: commit_write, eval — checks/locked/MANIFEST.json `files`, `ls checks/pending`, 12:15). The API is indirectly covered: every route runs CLI commands whose behaviour the locked rehearsal_core checks define (checks/locked/rehearsal_core/test_rehearsal_core.py). Names below are PROPOSED (3_STEPS.md step 2).

`checks/pending/api/test_api.py` (PROPOSED):
| Check function | What it asserts |
|---|---|
| `test_api_health_ok` | `GET /api/health` → 200, `ok` true and `falkordb` = `<host>:<port>`; with FalkorDB down → 503 |
| `test_api_demo_matches_cli_rehearse_per_lane` | for seed 7, each `lanes[X].failures` (duty, at) set equals `python -m baton rehearse --lane X --confirm all` |
| `test_api_demo_sources_carry_type_and_text` | every source object has `id`, `type` in {message, joblog, ticket, record}, non-empty `text` |
| `test_api_demo_live_hash_unchanged` | `live_hash_before == live_hash_after` |
| `test_api_handover_clears_failures` | assigning every G-failure duty round-robin to active stayers gives `refused == []` and `failures_after == []` (same idea as checks/locked/rehearsal_core/test_rehearsal_core.py:162-174) |
| `test_api_returns_503_when_falkordb_down` | with `FALKORDB_PORT` pointing at a dead port, `/api/demo` → 503 |
| `test_api_first_load_is_not_duplicated` | two parallel first `/api/demo` calls → one `Company` node in `halden_7` (after 3_STEPS.md step 3) |

## 2. Go and see
| Command | Expected |
|---|---|
| `curl -s localhost:8000/api/health` | `{"ok":true,"falkordb":"<host>:<port>"}`; 503 if FalkorDB is down |
| `curl -s 'localhost:8000/api/demo?seed=7'` | JSON with `seed`, `leaver`, `leaver_name`, `people`, `lanes` (W, R, G lists), `unpromoted`, equal hashes |
| `curl -s -X POST localhost:8000/api/handover -H 'Content-Type: application/json' -d '{"seed":7,"assign":{"<duty>":"<person>"}}'` | JSON with `accepted`, `refused`, `failures_after` |
| `curl -s -X POST localhost:8000/api/ask -H 'Content-Type: application/json' -d '{"question":"What does <leaver name> owe?"}'` | JSON with `tool: "owes"`, `rows`, `sources` (ids), `answer`, `cypher` |
| `curl -s -X POST localhost:8000/api/ask -H 'Content-Type: application/json' -d '{"question":"What is the CEO'"'"'s favourite colour?"}'` | `tool: "none"`, empty `rows` and `sources`, answer starting "That is not in the graph." |
| `curl -s 'localhost:8000/api/demo?seed=8'` | HTTP 500: no cached extraction for seed 8, so `extract` tries a model and fails on the missing key (exit 5); after 3_STEPS step 4 it fails at once with "no cached extraction" (exit 4) |
| stop FalkorDB, then `curl -s -o /dev/null -w '%{http_code}' 'localhost:8000/api/demo?seed=7'` | `503` |

## 3. Failure modes and fallbacks
| Failure | Fallback |
|---|---|
| `ModuleNotFoundError: fastapi` | Install deploy/requirements.txt in a separate venv (3_STEPS.md step 1) |
| 503 right after `docker compose up` | FalkorDB still starting (`depends_on` does not wait, docker-compose.yml:14). Retry |
| 500 on `/api/ask` | Read the detail; `ask` itself is green (loop/features.md:9). Web shows replay answers if the API is down (BUILD_PLAN.md:49) |
| 500 on seeds other than 7 | Beliefs exist only for seed 7. Use seed 7 |
| Demo slow | Three CLI subprocesses, each forks and fingerprints the graph (server/app.py:74-77, baton/rehearse.py:125-137). Cache the response per seed if needed (PROPOSED) |
| EC2 or Vercel down at video time | Site falls back to replay data (BUILD_PLAN.md:73) |

## 4. Anti-hallucination list
| Likely wrong assumption | Correct fact | Source |
|---|---|---|
| The API has its own logic | It shells out to `python -m baton` for every decision | server/app.py:1, server/app.py:17-23 |
| `/api/demo` runs the CLI `demo` command | It runs `rehearse` three times; no handover | server/app.py:74-77 |
| `/api/demo` lanes hold counts | They hold lists of enriched rows; the CLI `demo` holds counts | server/app.py:77, baton/demo.py (`lanes[lane] = {"failures": len(rows)}`) |
| `ask` is missing | It exists and is green | baton/__main__.py:34-40, loop/features.md:9 |
| `fixtures/beliefs_seed7.json` feeds the API | Deleted in commit `84747c6`; beliefs now come from `extract` and its cache | `git log -- fixtures/beliefs_seed7.json` |
| `/api/ask` sources are objects with text | They are a list of ids; only demo/handover rows are enriched | baton/ask.py:322, server/app.py:110 |
| `BATON_OFFLINE` switches offline mode | No code reads it | docker-compose.yml:12; grep 18 Oct |
| The container can call the default model | Default is `claude-haiku-4-5` (Anthropic); compose passes only `OPENAI_API_KEY` and requirements install only `openai` | baton/extract.py:106-107 at HEAD 85eeabd, docker-compose.yml:8-12, deploy/requirements.txt:5 |
| Live hashes look like `sha256:...` | Plain 64-char hex from `hexdigest()` | baton/graph.py:44 |
| Person ids look like `p-sam` | Dotted lower-case names, e.g. `hana.sharma` | baton/generate.py:204 at HEAD 85eeabd |
| The image contains the website or checks | It copies only `baton`, `server`, `fixtures` | deploy/Dockerfile:5-7 |
| FastAPI is in the project venv | It is not; only in deploy/requirements.txt | `import fastapi` failed 18 Oct; deploy/requirements.txt:1 |
| `/api/health` only says the web server is up | It pings FalkorDB and returns 503 if it is down | server/app.py:58-66 |
| `POST /api/handover` writes to Gitea | It does not; it rehearses on a fork. The Gitea write is PROPOSED in M06 | server/app.py:90-99, baton/handover.py:87 |
| Port 3000 is free for another service | FalkorDB's container maps `127.0.0.1:3000` | docker-compose.yml:4 |
