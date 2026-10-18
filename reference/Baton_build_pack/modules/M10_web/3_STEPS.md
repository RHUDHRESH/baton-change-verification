# M10 · Web — STEPS

Karpathy-loop rule for this module: **checks first, a human approves them, lock, then build.** For the web the checks are the go-and-see script in step 1 plus the list in 4_ACCEPTANCE.md. Never edit `checks/locked/` or `loop/bin/` (loop/config.json lists only `baton`, `fixtures`, `Makefile`, `README.md` as paths the loop may change). One step at a time; each ends with an observable result.

Paths below are relative to `/home/claude/baton` unless absolute. Python with Playwright: system `python3` has Playwright 1.56.0 and Chromium in `/opt/pw-browsers` on this machine (checked with `python3 -m playwright --version`). The project venv does not have Playwright.

---

## Step 1 — Put the go-and-see script in the repo and get it approved
- Goal: a script that opens the page at desktop and phone width, light and dark, and prints PASS/FAIL.
- Files: copy `/tmp/claude-0/-home-claude/9e986261-4c5d-5119-82fd-cce4a3dc1af5/scratchpad/m10/go_and_see.py` to `tools/go_and_see.py` (PROPOSED path; web owner decides. Do not put it in `web/`, which is published).
- Commands:
  ```bash
  cd /home/claude/baton/web && python3 -m http.server 8790 --bind 127.0.0.1 &
  python3 /home/claude/baton/tools/go_and_see.py http://127.0.0.1:8790/ /home/claude/baton/web/_shots
  ```
- Done when: the script runs and prints a PASS/FAIL line per check. Today (no app.js) it prints 4/10 PASS: page scroll and console checks pass, "leaver line filled", "strips rendered", "clickable mark" fail. That is the expected red start.
- Agent prompt:
  > Copy scratchpad/m10/go_and_see.py to tools/go_and_see.py unchanged. Run it against `python3 -m http.server` serving web/. Paste the PASS/FAIL output. Do not change the checks. Ask the human to approve the check list in docs/modules/M10_web/4_ACCEPTANCE.md before any app.js work.

## Step 2 — Record real replay data (after M2 rehearsal is green)
- Goal: replay files with exactly the live API shape, so one renderer handles both.
- Files: `web/mock/demo_7.json`, `web/mock/handover_7.json` (overwrite the hand-written ones; PROPOSED, web owner decides).
- Commands (local API; FalkorDB on 6399 as in .claude/skills/project-context/SKILL.md:11):
  ```bash
  cd /home/claude/baton
  FALKORDB_PORT=6399 BATON_DATA=/tmp/baton_data <venv-with-fastapi>/bin/uvicorn server.app:app --port 8000 &
  curl -s "http://127.0.0.1:8000/api/demo?seed=7" > web/mock/demo_7.json
  python3 - <<'EOF'
  import json
  d = json.load(open("web/mock/demo_7.json"))
  stay = [p["id"] for p in d["people"] if p["left_at"] is None and p["id"] != d["leaver"]]
  duties = sorted({f["duty"] for f in d["lanes"]["G"]["failures"]})
  json.dump({"seed": 7, "assign": {du: stay[i % len(stay)] for i, du in enumerate(duties)}}, open("/tmp/assign_7.json", "w"))
  EOF
  curl -s -X POST -H 'content-type: application/json' -d @/tmp/assign_7.json http://127.0.0.1:8000/api/handover > web/mock/handover_7.json
  ```
  The project venv has no FastAPI. A working venv was built for this doc with `python3 -m venv v && v/bin/pip install fastapi==0.115.0 uvicorn==0.30.6 falkordb==1.8.0 redis==8.1.0` (see M11 for why redis 8.1.0, not 5.0.8).
- Done when: `python3 -c "import json;d=json.load(open('web/mock/demo_7.json'));print(d['leaver'],[len(d['lanes'][l]['failures']) for l in 'WRG'])"` prints the same numbers as the live API, and `handover_7.json` has `"failures_after": []`.
- Agent prompt:
  > Record web/mock/demo_7.json and handover_7.json from the running API with the commands in M10 3_STEPS step 2. Do not hand-edit them. Print the leaver and the W/R/G failure counts, and the length of failures_after.

## Step 3 — Write `web/app.js` (data layer)
- Goal: one `load(path, opts)` that tries the API and falls back to replay.
- Files: `web/app.js` (new).
- Rules: fetch `/api/...` with a timeout (AbortController, about 20 s for `/api/demo`; Vercel waits at most 120 s for the origin, see M11). On any error or non-2xx, fetch `mock/<name>_7.json`, unhide `#badge`, remember "replay mode" for the whole page. Time values are epoch-ms ints; format with `new Date(ms)` in UTC (the generator's base date is UTC, baton/generate.py:16).
- Done when: with no API (static server only) the page fills `#leaver-line` and shows the badge; with the API up, the badge stays hidden.
- Agent prompt:
  > Write web/app.js. Read docs/modules/M10_web/2_CONTRACT.md first and use only the fields listed there. Fetch /api/demo?seed=7; on failure load mock/demo_7.json and unhide #badge. Do not invent fields (no `company`, `ghost_duties`, `path_before`, `cypher` unless the response has them). Times are epoch-ms ints. Keep every element id from web/index.html. No external libraries.

## Step 4 — Section 01: the month strips and the proof drawer
- Goal: three rows (W, R, G) × `window_days` columns from `now`; a red `button.m.m-fail` on each failure's `day`; a dashed `.m-miss` in the W or R row for a G failure (same `event`) that this lane does not list (legend: "Breaks, but this view cannot see it", web/index.html:51).
- Files: `web/app.js`.
- Drawer: on click, open `#drawer` (it is a `<dialog>`, web/index.html:127) with `duty_name`, `label`, the day, `status`, and every `sources[]` item as `type` + `text`. Show Cypher only if the API sends it (2_CONTRACT §5).
- Done when: go-and-see "at least one clickable mark" and "proof drawer opens with text" pass at both widths.
- Agent prompt:
  > In web/app.js render #strips from lanes.W/R/G.failures. Column index = failure.day (0..window_days-1). Use classes from web/styles.css (.grid, .c-label, .c-day, .m, .m-fail, .m-miss, .wk for weekends). A click opens #drawer and lists sources as "type · text". Run tools/go_and_see.py and paste the output.

## Step 5 — Section 02: ghost duties
- Goal: "Promoted" = G failures whose `status` is not `record`, grouped by duty; "Refused" = `unpromoted` rows (`belief` + `reason`).
- Done when: `#ghosts` and `#refused` are non-empty for seed 7 (the API gave 4 unpromoted rows).
- Agent prompt:
  > Fill #ghosts from G failures with status confirmed/believed (group by duty, show sources). Fill #refused from `unpromoted` (show the belief id and the reason text exactly). Do not claim a person said yes: the API runs with --confirm all (server/app.py:70); label it "confirmation simulated in the demo".

## Step 6 — Section 03: handover and replay
- Goal: one row per failing G duty with a `<select>` of active people (`left_at` null, not the leaver). "Replay month" posts `/api/handover`; show `accepted`, `refused` with reasons, and the new `failures_after` count; turn marks green (`.m-ok`).
- Done when: replay with every duty assigned shows 0 failures after; assigning a duty to the leaver shows a refusal with the reason "person is the one leaving" (baton/handover.py:57).
- Agent prompt:
  > Build #handover from G failures (unique duties). POST {seed, assign} to /api/handover (replay: mock/handover_7.json). Render #receipt with accepted, refused (reason text verbatim), failures_after length, and the two live hashes with "unchanged" if equal. Never say the real graph changed: the handover runs on a fork (baton/handover.py:11).

## Step 7 — Section 04: Ask (only if the locked ask checks are green by 14:30)
- Goal: post `/api/ask`; show `answer`, `sources`, `tool`, `cypher`.
- If not green: hide the section (docs/BUILD_PLAN.md:68). Either way, fix the catalogue list (web/index.html:106-116) to the five real tools from `python -m baton ask --catalogue` (`owes`, `breaks_if_leaves`, `why`, `covers`, `none`, baton/ask.py:59-64); today it lists six names that do not exist. `sources` come back as ids only; show them as ids or look them up in the `/api/demo` failures' source objects.
- Done when: a chip question returns an answer with at least one source, live or labelled replay.

## Step 8 — Footer and final pass
- Replace `https://github.com/REPLACE_ME/baton` (web/index.html:123) with the real repo URL.
- Run go-and-see against the local page, then against the Vercel URL after M11:
  ```bash
  python3 tools/go_and_see.py https://<project>.vercel.app/ web/_shots
  ```
- Done when: all checks PASS on the live URL and the badge is hidden (live data).
