# M10 · Web — CONTRACT

Rule: every item is copied from a file (cited `path:line`) or marked `PROPOSED (not yet in code)` with who decides. Line numbers were checked on 18 Oct during this writing pass; the loop rewrites `baton/` often, so re-open the file before trusting a line number.

## 1. Base URL
- The page calls relative paths `/api/...`. On Vercel, `/api/*` is rewritten to the EC2 API (see M11 2_CONTRACT). Locally, serve `web/` and the API from one origin, or the calls fail and the page falls back to replay data.
- The API allows any origin (CORS `*`) (server/app.py:14), so a page on another origin can also call it directly. A page served over `https` cannot call an `http://` API directly (browser mixed-content rule); this is why the Vercel rewrite exists.

## 2. API routes that exist (server/app.py)
| Method | Path | Request | Source |
|---|---|---|---|
| GET | `/api/health` | none | server/app.py:58-60 |
| GET | `/api/demo` | query `seed` (int, default 7) | server/app.py:63-64 |
| POST | `/api/handover` | JSON `{seed: int = 7, assign: {duty_id: person_id}}` | server/app.py:79-81, :84-85 |
| POST | `/api/ask` | JSON `{seed: int = 7, question: str}` | server/app.py:96-98, :101-102 |

There are no other routes. Anything else the page wants is PROPOSED (section 5).

### 2.1 `GET /api/health`
Returns `{"ok": true}` (server/app.py:60). It does **not** touch FalkorDB: in our local run it still returned `{"ok":true}` HTTP 200 after FalkorDB was stopped, while `/api/demo` returned 503. Do not use it to decide "live vs replay"; use the `/api/demo` result.

### 2.2 `GET /api/demo?seed=N`
Runs `rehearse` three times, lanes W, R, G, each with `--confirm all` (server/app.py:68-71). Response object (server/app.py:73-76):

| Field | Type | Meaning / source |
|---|---|---|
| `seed` | int | echo (server/app.py:73) |
| `now` | int, epoch ms | world start (baton/generate.py:449; base value baton/generate.py:16) |
| `day_ms` | int | 86 400 000 (baton/generate.py:13, :449) |
| `window_days` | int | 30 (baton/generate.py:15, :450) |
| `leaver` | str | person id, form `first.last`, e.g. `hana.sharma` (baton/generate.py:204, :206) |
| `leaver_name` | str | display name (server/app.py:72, :74) |
| `leave_at` | int, epoch ms | `now + 1 day` (baton/generate.py:137) |
| `people` | list of `{id: str, name: str, team: str, role: str, left_at: int or null}` | baton/generate.py:204-205 |
| `lanes` | `{W: {failures: [Failure]}, R: {...}, G: {...}}` | server/app.py:71 |
| `unpromoted` | list of `{belief: str, reason: str}` from the **G** lane run (the last loop pass) | server/app.py:75; baton/rehearse.py:94 |
| `live_hash_before`, `live_hash_after` | str, 64 hex chars (sha256), from the G lane run | server/app.py:76; baton/graph.py:39-44 |

`Failure` (built in baton/rehearse.py:146-147, enriched in server/app.py:51-54):

| Field | Type | Source |
|---|---|---|
| `duty` | str, duty id (e.g. `d-codesign-windows`) | baton/rehearse.py:146 |
| `duty_name` | str | server/app.py:52 |
| `event` | str, event id (e.g. `ev-0005`) | baton/rehearse.py:146 |
| `label` | str, event label (e.g. "Windows code-signing certificate: renewal reminder") | baton/rehearse.py:147 |
| `at` | int, epoch ms | baton/rehearse.py:146 |
| `day` | int, `(at - now) // day_ms` | baton/rehearse.py:146 |
| `status` | str: `"record"`, `"confirmed"` or `"believed"` | .claude/skills/project-context/SKILL.md:21 |
| `sources` | list of `{id: str, type: str, text: str}`; `type` is `message`, `joblog`, `ticket`, `record`, or `?` if the id is unknown | server/app.py:44-48, :53-54 |

Errors (server/app.py:21-22): CLI non-zero exit → HTTP 503 if the output mentions "falkordb", else HTTP 500; body `{"detail": "<last 800 chars of stderr>"}` (FastAPI `HTTPException`).

Measured on the current tree (local uvicorn + FalkorDB v4.22.1 module, seed 7): HTTP 200 in about 1 s; leaver `hana.sharma`; failure rows W 6, R 7, G 37; `unpromoted` 4; hashes equal. These are dev numbers, not results. Re-measure after the freeze.

### 2.3 `POST /api/handover`
Request: `{"seed": 7, "assign": {"<duty id>": "<person id>", ...}}` (server/app.py:79-81). Each pair becomes `--assign DUTY=PERSON` (server/app.py:89-90).
Response (baton/handover.py:89-91, plus server/app.py:92):

| Field | Type | Source |
|---|---|---|
| `leaver` | str | baton/handover.py:89 |
| `graph` | str, e.g. `halden_7` | baton/handover.py:89 |
| `accepted` | list of `{duty, person}` | baton/handover.py:79 |
| `refused` | list of `{duty, person, reason}`; reasons include "duty already has an accepted successor", "person is the one leaving", "person has left or does not exist (...)", "no duty '<id>' in the graph" | baton/handover.py:53-58, :68, :76 |
| `failures_after` | list of `Failure` (enriched) | baton/handover.py:90; server/app.py:92 |
| `live_hash_before`, `live_hash_after` | str | baton/handover.py:91 |

Important: the handover runs on a **fork** and the live graph is only fingerprinted (baton/handover.py:11, :87). The page must not say the real graph changed. Acceptance is the API call itself; no successor clicks anything.

### 2.4 `POST /api/ask`
Request: `{"seed": 7, "question": "..."}` (server/app.py:96-98). Calls `ask --world --beliefs --question --port` (server/app.py:104). It does not pass `--offline` (the locked checks do, checks/locked/ask/test_ask.py:18); today that makes no difference because `ask.run` always uses the offline router (baton/ask.py:254, :266-267: `"router": "offline"`).
The CLI dispatches `ask` (baton/__main__.py:66-74). Measured locally: HTTP 200.
Response keys (baton/ask.py:265-277): `question`, `tool`, `args`, `cypher`, `graph`, `router`, `rows`, `sources`, `answer`, `live_hash_before`, `live_hash_after`. Field meanings from the **locked** checks (checks/locked/ask/test_ask.py): `tool` (str; one of `breaks_if_leaves`, `owes`, `why`, `covers`, `none`) (:29, :38, :49, :62, :71), `args` (object, e.g. `{person}` or `{duty}`) (:29, :63), `rows` (list of objects with at least `duty`) (:31, :41), `sources` (list of source **ids**, strings) (:50, :83), `answer` (str) (:72, :84), `cypher` (str, equal to the catalogue entry for `tool`) (:82). Catalogue keys: `owes`, `breaks_if_leaves`, `why`, `covers`, `none` (baton/ask.py:59-64). `sources` are **not** enriched by the API (server/app.py:104 returns the CLI output as is), so the page gets ids only; PROPOSED: run them through `enrich`-style lookup in server/app.py (API owner decides).

## 3. Replay-data fallback
- Exists now: `web/mock/demo_7.json`, `web/mock/handover_7.json`, `web/mock/ask_7.json`. They were hand-written by `scratchpad/gen_mocks.py`, not recorded from the API.
- They do **not** match the API. Differences found by comparing with a live `/api/demo?seed=7` response:
  - times are ISO strings (`"now": "2026-10-18T09:00:00Z"`); the API sends epoch-ms ints;
  - people ids are `p-priya` style and the leaver is "Priya Raman"; the generator makes `first.last` ids and seed 7's leaver is Hana Sharma;
  - extra fields not in the API: `company`, `fixture`, `ghost_duties`, `path_before`, `cypher` on each failure, `claim` on `unpromoted`;
  - the `cypher` strings use labels and types that are not in the graph (`Obligation`, `OWNER_FIELD`, `ON_CALL`, `DOES`). The real graph uses `Duty`, `Event`, `OWNER`, `ROUTES_TO`, `SHIFT`, `ESCALATES_TO`, `NEEDS` (baton/load.py:6-9, :43-63);
  - G has 4 failures in the mock; the API gave 37 rows for seed 7.
- `PROPOSED (not yet in code)`, web owner decides: replace the three mock files with **recorded** API output, same shape as section 2, so one code path renders both live and replay:
  ```bash
  curl -s "http://<API>/api/demo?seed=7" > web/mock/demo_7.json
  curl -s -X POST -H 'content-type: application/json' -d @assign_7.json "http://<API>/api/handover" > web/mock/handover_7.json
  ```
  `assign_7.json` = `{"seed":7,"assign":{...}}` built from the G failures in `demo_7.json`. Ask replay: record with `curl -s -X POST -H 'content-type: application/json' -d '{"seed":7,"question":"What breaks if <leaver_name> leaves?"}' http://<API>/api/ask > web/mock/ask_7.json` (one object per question; the current mock wraps four answers in an `answers` list, a different shape).
- Rule for the page (PROPOSED): try the live call; on network error, non-2xx, or a timeout, load the matching `web/mock/*.json`, set `#badge` visible (web/index.html:18), and keep going. Never mix live and replay data on one screen.

## 4. Page contract (element ids that app.js must fill)
Copied from web/index.html; app.js must not rename them (the Playwright checks use them).
`#badge` (:18), `#leaver-line` (:30), `#leaver-sub` (:31), `#seed-7` (:35), `#seed-rand` (:36), `#seed-now` (:37), `#month-sum` (:46), `#strips` (:55), `#ghosts` (:69), `#refused` (:73), `#handover` (:84), `#replay` (:86), `#reset` (:87), `#hand-status` (:88), `#receipt` (:90), `#ask-form` (:99), `#ask-q` (:101), `#chips` (:104), `#answer` (:105), `#repo-link` (:123), `#drawer` (:127), `#dr-lane` (:130), `#dr-close` (:131), `#dr-title` (:133), `#dr-body` (:134).
Mark classes defined in CSS: `.m-fail`, `.m-ok`, `.m-miss`; clickable marks are `button.m` (web/styles.css:118-123).

## 5. PROPOSED API additions (not yet in code; API owner decides, and each needs a check before it ships)
| Want | Why | Simplest source |
|---|---|---|
| `company`, `label` ("FIXTURE") in `/api/demo` | footer / honesty line | already in world.json (baton/generate.py:449); add in server/app.py:73 |
| `claim`, `duty_name`, `person` on each `unpromoted` row | "Refused" list needs readable text | beliefs file rows have `claim`, `duty_name`, `person` (fixtures/beliefs_seed7.json) |
| promoted ghost duties | "Promoted" list | derive in the page: G failures with `status` `confirmed`/`believed` (SKILL.md:21). No new API field needed |
| per-failure `cypher` | proof drawer | must be the exact query text the CLI ran (constant strings in baton/rehearse.py), never a hand-written string |
| catalogue list for section 04 | the `<details>` list in web/index.html:106-116 names six tools that do not match the five real ones | `python -m baton ask --catalogue` (baton/__main__.py:35, :68-69; baton/ask.py:280-281) |
