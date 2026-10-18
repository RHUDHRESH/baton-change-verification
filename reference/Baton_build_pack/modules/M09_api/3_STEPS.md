# M09 · STEPS

Paths relative to `/home/claude/baton/`. `PY` = `/tmp/claude-0/-home-claude/9e986261-4c5d-5119-82fd-cce4a3dc1af5/scratchpad/venv/bin/python`.

## The karpathy-loop rule
Checks first; human approves; lock with `loop/bin/lock_checks.py <feature> --approved-by "..."` (loop/bin/lock_checks.py:4-6); then build. Never edit `checks/locked/**` or `loop/bin/**` (loop/program.md:17). Note: `server/`, `deploy/`, `docker-compose.yml` are **not** loop-mutable paths (loop/program.md:16, loop/config.json:7-12). API changes are human edits (or a human widens the mutable paths; that is a FIXED-rule change only a human makes).

---

### Step 1 · Run it locally once (human, 15 min)
- Goal: see the API answer, for the first time.
- Commands:
  ```
  python3 -m venv /tmp/apivenv
  /tmp/apivenv/bin/pip install -r deploy/requirements.txt
  B=/tmp/claude-0/-home-claude/9e986261-4c5d-5119-82fd-cce4a3dc1af5/scratchpad/venv/lib/python3.13/site-packages/redislite/bin
  $B/redis-server --port 6399 --daemonize yes --dir /tmp --loadmodule /tmp/claude-0/-home-claude/9e986261-4c5d-5119-82fd-cce4a3dc1af5/scratchpad/fdb422/falkordb.so --save ''
  cd /home/claude/baton && FALKORDB_PORT=6399 BATON_DATA=/tmp/baton_data /tmp/apivenv/bin/uvicorn server.app:app --port 8000
  curl -s localhost:8000/api/health
  curl -s 'localhost:8000/api/demo?seed=7' | head -c 600
  ```
  (server start line from .claude/skills/project-context/SKILL.md:11; uvicorn target from deploy/Dockerfile:10.)
- Done when: health prints `{"ok":true,"falkordb":"localhost:6399"}` and demo prints JSON with `lanes`.
- Also try `curl -s -X POST localhost:8000/api/ask -H 'Content-Type: application/json' -d '{"question":"What does <leaver name> owe?"}'` → JSON with `tool: "owes"`, `answer`, `sources`, `cypher`. And `curl -s 'localhost:8000/api/demo?seed=8'` → HTTP 500 (no beliefs for seed 8; see 1_SPEC.md).

### Step 2 · Draft API checks (agent drafts, human approves) — optional
- Files: `checks/pending/api/conftest.py` (copy of checks/locked/rehearsal_core/conftest.py), `checks/pending/api/test_api.py`.
- Problem: the check runner uses the project venv (loop/config.json:3), which has no FastAPI. Either a human installs `fastapi`, `uvicorn` and `httpx` (FastAPI's TestClient is built on httpx — general library knowledge, not checked here; httpx is not in deploy/requirements.txt) into the project venv, or the API is accepted by go-and-see only. Joyal decides.
- Names: 4_ACCEPTANCE.md §1.
- Prompt:
  > Read docs/modules/M09_api/2_CONTRACT.md. Draft checks/pending/api/test_api.py with exactly the functions in docs/modules/M09_api/4_ACCEPTANCE.md §1. Start uvicorn on a free port as a subprocess with FALKORDB_PORT set to the conftest `port` fixture and BATON_DATA set to a tmp dir; call it with urllib.request. Do not edit server/app.py. Do not touch checks/locked or loop/bin.

### Step 3 · Fix the first-load race (human edit, 5 min)
- File: `server/app.py`, function `world_dir` (server/app.py:26-37).
- Change (PROPOSED): after the beliefs block and still inside `with LOCK:`, add `cli("load", "--world", d, "--port", PORT)`. `load` leaves an existing graph alone (baton/load.py:96-97 at HEAD 85eeabd), so this is safe to call every time, but it costs one CLI call per request; cache a set of loaded seeds in memory if that is too slow.
- Done when: two parallel `curl` calls to `/api/demo?seed=7` on an empty FalkorDB both succeed and `MATCH (n:Company) RETURN count(n)` on `halden_7` returns 1.

### Step 4 · Make `extract` fail fast (human edit, 2 min)
- File: `server/app.py:36`. PROPOSED: add `"--offline"` to the `extract` call, so a cache miss exits 4 at once instead of trying a model the container has no SDK or key for. Optionally also add `"--offline"` to the `ask` call at server/app.py:110 (matches checks/locked/ask/test_ask.py:18).
- Done when: `/api/demo?seed=7` still works and `/api/demo?seed=8` returns 500 within a second with "no cached extraction" in the detail.

### Step 5 · Agree the demo shape with M10 (both owners, 10 min)
- Compare `GET /api/demo` (2_CONTRACT.md §5) with `web/mock/demo_7.json`. Either the API adds `company`, `fixture`, `ghost_duties` (PROPOSED; values must come from world.json and the CLI, not be invented), or the web stops reading them. Replace mock ids with real ids from a real run (save the real `/api/demo?seed=7` output as the new mock).
- Done when: the page renders from the live API and from the saved real response with no code change.

### Step 6 · Docker and EC2 (teammate)
- Commands (UNTESTED by us):
  ```
  docker compose build api
  docker compose up -d
  curl -s localhost:8000/api/health
  ```
- Done when: health works on EC2's public address on port 8000 and the Vercel site's `/api/health` returns the same (`web/vercel.json` must be created first, BUILD_PLAN.md:23).
- If M06's git fallback runs in the container, add git to the image (human edit to deploy/Dockerfile).

### Step 7 · Freeze (16:00)
- Tag `v-freeze` and deploy (BUILD_PLAN.md:73). No API changes after this.
