# M06 · STEPS

Paths are relative to `/home/claude/baton/` unless absolute. `PY` = `/tmp/claude-0/-home-claude/9e986261-4c5d-5119-82fd-cce4a3dc1af5/scratchpad/venv/bin/python`.

## The karpathy-loop rule (read first)
1. Checks first. Cut checks are locked in `checks/locked/cut/`; commit checks are drafted in `checks/pending/commit_write/`.
2. A human approves them. Then they are locked with `loop/bin/lock_checks.py <feature> --approved-by "<who: 'words' (date)>"` (loop/bin/lock_checks.py:4-6). Locking moves `checks/pending/<feature>/` to `checks/locked/<feature>/` and records hashes (loop/bin/lock_checks.py:9-11).
3. Only then build. One hypothesis per round, keep or revert by score (loop/program.md:23-27).
4. Never edit `checks/locked/**` or `loop/bin/**` (loop/program.md:17). If a check looks wrong, write `loop/disputes/<check>.md` (loop/program.md:20-22).
5. The loop may change only `baton`, `fixtures`, `Makefile`, `README.md` (loop/program.md:16). `docker-compose.yml`, `server/`, `web/` are human edits.
6. Note: `run_checks.py` counts skipped tests as failing (loop/bin/run_checks.py:9-10). So a locked check must not depend on Gitea being up unless Gitea runs wherever checks run.

---

### Steps 0–1 · Cut checks reviewed and locked — DONE
- Locked in commit `85eeabd` ("lock checks for cut (manifest v6)", ~12:00 IST). Files: `checks/locked/cut/test_cut.py`, `flow_oracle.py`, `oracle.py`, `conftest.py`.
- Charter decision on the cache trap: "extraction/lane-A caches must therefore be keyed on the inputs each step actually reads, so existing caches stay valid" (loop/features.md, `### cut`). Step 2 must do that re-keying.

### Step 2 · Generator and loader data (loop round 1)
- Goal: `test_world_has_capability_and_capacity_data` and `test_both_verdicts_occur_across_seeds` pass; all 32 rehearsal_core runs, 11 ask runs and the ai_layer checks still pass.
- Files: `baton/generate.py`, `baton/load.py`, `baton/extract.py` (its `_record_line` and its cache key), `baton/lane_a.py` (its cache key).
- Rules for the change:
  1. Add `CAN` records `{type: "CAN", duty, person}` and `capacity` (int ≥ 1) on every person.
  2. Use a **separate** `random.Random` (e.g. seeded from `seed` plus a constant) after the main world is built, so existing choices do not shift (main generator: one `random.Random(seed)`, baton/generate.py:135 at HEAD 85eeabd).
  3. Existing `rec-` ids are numbered by sorted JSON (baton/generate.py:428-429 at HEAD 85eeabd). Give CAN records their own prefix (e.g. `can-0001`) numbered separately, so existing record ids stay the same. PROPOSED.
  4. Teach `load._record_text` (baton/load.py:70-77 at HEAD 85eeabd) and `extract._record_line` (baton/extract.py:115-122 at HEAD 85eeabd) the new type before anything else, or loading crashes with `KeyError: 'from_person'`.
  5. Do not add CAN edges to any lane (baton/rehearse.py:20-24).
  6. Re-key the extraction and lane-A caches on the inputs each step reads (per the charter), so the committed seed-7 caches still hit and the locked ai_layer checks stay green (checks/locked/ai_layer/test_ai_layer.py:55-58).
  7. Data must be facts of the world (who has access or skill), never "who will fail". The generator "never plants failures" (BUILD_PLAN.md:36).
- Done when: `PY loop/bin/run_checks.py` shows the two data checks green and no regressions.
- Prompt:
  > Karpathy loop round. Read loop/program.md, docs/modules/M06_cut_and_write/1_SPEC.md ("Traps") and checks/locked/cut/test_cut.py + flow_oracle.py. Add CAN records and person capacity to baton/generate.py using a separate random.Random so every existing id and choice stays the same; number CAN records with their own prefix. Update baton/load.py `_record_text` and baton/extract.py `_record_line` for the new record type. Load CAN as (:Person)-[:CAN {rec}]->(:Duty) and Person.capacity. Do not add CAN to any rehearsal lane. Both verdicts must occur across seeds 7, 101, 202, 303 by world facts alone. Run the full locked suite; predict which checks flip first. Never edit checks/locked or loop/bin.

### Step 3 · Build `baton/cut.py` (loop rounds)
- Goal: the remaining cut checks (2_CONTRACT.md §3).
- Files: `baton/cut.py` (new); `baton/__main__.py` (add a `cut` sub-parser with `--world --beliefs --leaver --port`, like the `rehearse` parser at baton/__main__.py:19-25, and a dispatch branch inside the existing `try:` so `Unreachable` still exits 3).
- Design:
  1. `s = rehearse.open_session(world, beliefs, leaver, port, cmd="cut")` (baton/rehearse.py:108-118).
  2. Broken duties: `r = rehearse.on_fork(s, "G", "all")`; `rows = rehearse.failures(s, r["present"], r["gone"])`; `duties = sorted({x["duty"] for x in rows})` (same pattern as baton/ask.py:241-242).
  3. Flow fork: `G.fork(s["db"], s["live"].name, "cut")` (baton/graph.py:47-53), then `rehearse.gate(fork, s["beliefs"])` and `fork.query(rehearse.Q_HOLDS, {"open": G.OPEN, "basis": "confirmed"})` (the same preparation ask uses, baton/ask.py:210-212) so belief-only duties exist. Delete the fork in `finally` (as baton/ask.py:216-217).
  4. Build the network with the Cypher in 2_CONTRACT.md §2 (check-aligned version).
  5. Solve with the maxFlow query from verify/spike.py:125-128; read the full FLOW list (verify/spike.py:130-131).
  6. Residual BFS + min-cut (verify/spike.py:144-155). `unplaceable` = source pipes not full.
  7. N-1 for every active stayer: set that person's drain pipe to 0, re-solve, restore (verify/spike.py:159-166). This equals the check's "remove the person" (checks/locked/cut/flow_oracle.py:59-60), because a person with no drain can pass no flow.
  8. `cypher` field: the exact maxFlow query text. Fingerprints before/after (baton/graph.py:39-44).
- Done when: all locked cut checks pass, no regressions.
- Prompt:
  > Karpathy loop round. Read docs/modules/M06_cut_and_write/2_CONTRACT.md §1–§3 and /tmp/claude-0/-home-claude/9e986261-4c5d-5119-82fd-cce4a3dc1af5/scratchpad/verify/spike.py lines 113-169. Implement baton/cut.py and the `cut` sub-command with output keys demand, flow, verdict ("POSSIBLE"/"IMPOSSIBLE"), min_cut [{from,to}], unplaceable, n_minus_1, live_hash_before, live_hash_after, cypher. All flow reasoning is Cypher + `CALL algo.maxFlow` on a fork; Python only walks the residual graph from the edges and flows FalkorDB returned. One relationship type FLOW; no duplicate edges; node ids "S" and "T". Standard library + falkordb only. Never import or mention the reference checker. Write your prediction first.

### Step 4 · `commit`: live graph + git repo + receipt (lock checks, then loop rounds)
- Checks: drafted in `checks/pending/commit_write/` (5 functions, see 4_ACCEPTANCE.md). A human reviews and locks them: `PY loop/bin/lock_checks.py commit_write --approved-by "..."`.
- Files: `baton/commit.py` (new, PROPOSED name), `baton/__main__.py` (a `commit` sub-parser with `--world --beliefs --leaver --repo --port --assign`, repeatable `--assign` like the handover parser at baton/__main__.py:27-32).
- Design (PROPOSED):
  1. Live graph: create (once) the index + UNIQUE constraint on `OWNER.active_key` on the **live** graph, the same commands handover runs on its fork (baton/handover.py:33-46). Then run the guarded `Q_ACCEPT` per assignment on the live graph (baton/handover.py:20-25); catch the unique-constraint error as a refusal (baton/handover.py:71-77) and use `_why_not` for reasons (baton/handover.py:49-58).
  2. Only if at least one row was committed: write the file into `--repo`, `git add`, `git -c user.name=Baton -c user.email=baton@example.invalid commit`, then `git rev-parse HEAD` and `git show HEAD:<file>`; parse it back into `read_back`.
  3. `still_uncovered` / `ready_to_leave`: run the G-lane rehearsal after the write (as `rehearse.run` does, baton/rehearse.py:151-156) and list duties still failing.
  4. Live hashes: fingerprint before and after (baton/graph.py:39-44); they must differ after a commit.
  5. FalkorDB down: `G.connect` raises `Unreachable` before anything touches the repo (baton/graph.py:18-27).
- Note the `rehearse` session reloads nothing: `load.ensure` leaves an existing graph as it is (baton/load.py:96-97 at HEAD 85eeabd), so the committed OWNER edges persist into later rehearsals.
- Done when: the locked commit_write checks pass with no regressions, and by hand:
  ```
  git init /tmp/halden-ops && git -C /tmp/halden-ops -c user.name=t -c user.email=t@t commit -q --allow-empty -m init
  PY -m baton commit --world W --beliefs B.json --leaver <id> --repo /tmp/halden-ops --port 6399 --assign <duty>=<person>
  git -C /tmp/halden-ops log --oneline -1 ; git -C /tmp/halden-ops show HEAD:<external.file>
  ```
  shows the commit sha from `external.commit` and the duty and person.
- Prompt:
  > Karpathy loop round. Read loop/program.md, docs/modules/M06_cut_and_write/2_CONTRACT.md §4 and checks/locked/commit_write/test_commit_write.py. Implement `python -m baton commit` exactly to that contract: guarded OWNER writes on the LIVE graph with a UNIQUE constraint on OWNER.active_key (reuse baton/handover.py's Q_ACCEPT and constraint code), then a git commit of a file listing duty and person into --repo, read back with git into `external`. Nothing may reach the repo if no row was committed or FalkorDB is down. Standard library + falkordb only. Write your prediction first. Never edit checks/locked or loop/bin.

### Step 5 · Gitea service (human, 15 min, UNTESTED commands)
- Files: `docker-compose.yml` (human edit; not a mutable path).
- Add (PROPOSED; check the image tag with `docker pull` first):
  ```yaml
  gitea:
    image: docker.gitea.com/gitea:28.1.0      # tag from docs.gitea.com install page, 18 Oct; verify
    environment:
      USER_UID: "1000"
      USER_GID: "1000"
      GITEA__database__DB_TYPE: sqlite3
      GITEA__security__INSTALL_LOCK: "true"
    ports: ["127.0.0.1:3001:3000"]            # 3000 is taken by falkordb (docker-compose.yml:4)
    volumes: ["gitea-data:/data"]
    restart: unless-stopped
  ```
  plus a top-level `volumes: {gitea-data: {}}`, and (for option b) `GITEA_URL: http://gitea:3000`, `GITEA_USER`, `GITEA_PASSWORD` in the `api` service environment (docker-compose.yml:8-12).
- Commands (UNTESTED):
  ```
  docker compose up -d gitea
  docker compose exec -u git gitea gitea admin user create --username baton --password "$GITEA_PASSWORD" --email baton@example.invalid --admin --must-change-password=false
  curl -sS -u "baton:$GITEA_PASSWORD" -H 'Content-Type: application/json' -X POST http://127.0.0.1:3001/api/v1/user/repos -d '{"name":"halden-ops","auto_init":true,"default_branch":"main"}'
  ```
- Done when: the last command returns HTTP 201 with a repository JSON (or 409 if it already exists), and `http://127.0.0.1:3001/baton/halden-ops` opens in a browser.
- If `exec -u git` fails, try without `-u git`; record what worked in this file's folder notes for the team.

### Step 6 · Gitea target (optional, after step 5 works by hand; no checks)
- Goal: the same receipt from Gitea, by option (a) `git push` of the `--repo` clone, or (b) REST (2_CONTRACT.md §4 "Gitea target").
- Hand test first (UNTESTED):
  ```
  C=$(base64 -w0 CODEOWNERS)
  curl -sS -u "baton:$GITEA_PASSWORD" -H 'Content-Type: application/json' -X POST \
    http://127.0.0.1:3001/api/v1/repos/baton/halden-ops/contents/CODEOWNERS \
    -d "{\"content\":\"$C\",\"message\":\"Baton handover\",\"branch\":\"main\"}"
  curl -sS -u "baton:$GITEA_PASSWORD" "http://127.0.0.1:3001/api/v1/repos/baton/halden-ops/contents/CODEOWNERS?ref=main"
  ```
  Expect 201 with `commit.sha`, then 200 with `content` (base64), `sha`, `last_commit_sha`.
- Python: `urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers={"Authorization": "Basic " + base64.b64encode(f"{u}:{p}".encode()).decode(), "Content-Type": "application/json"})`. Decode read-back with `base64.b64decode(content)` (it ignores newlines by default).
- On any HTTP or connection error: print a clear message to stderr and keep the local git receipt. Do not silently claim Gitea; the receipt must say which system was written.
- Done when: the Gitea web page shows the file and the same commit sha as the receipt.

### Step 7 · Wire to the API and web (human; M09/M10 owners)
- PROPOSED routes in `server/app.py` (not there now): `GET /api/cut?seed=7` calling `cli("cut", ...)`, and `POST /api/commit` calling `cli("commit", ...)`. Follow the existing `cli()` pattern (server/app.py:17-23). Careful: `commit` changes the live graph, so a public demo route needs a reset story (PROPOSED: a fresh seed string per visitor, as the checks do).
- Done when: the web shows `IMPOSSIBLE n/m` (or `POSSIBLE n/n`), the `unplaceable` duties, the N-1 row, and the Gitea commit sha with a link.

### Step 8 · Go and see (both students)
- Run the commands in 4_ACCEPTANCE.md §2 and watch the output with your own eyes. Write down facts (numbers, shas) separately from opinions (loop/program.md:28-30).
