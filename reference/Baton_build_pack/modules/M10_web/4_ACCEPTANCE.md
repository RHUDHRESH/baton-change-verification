# M10 · Web — ACCEPTANCE

## 1. Checks
There are no locked or drafted pytest checks for the web (checks/locked/ has only `rehearsal_core`; checks/pending/ has only `ask`). The web is accepted by the go-and-see script plus a human look.

Go-and-see script: `scratchpad/m10/go_and_see.py` (to be copied to `tools/go_and_see.py`, PROPOSED). Check names it prints, for each of `desktop-light` (1280×900) and `phone-dark` (390×844):
1. `leaver line filled` — `#leaver-line` no longer says "Loading".
2. `month strips rendered` — `#strips` has text.
3. `no sideways page scroll` — `document.scrollingElement.scrollWidth <= innerWidth`.
4. `no console errors` — no uncaught page errors; "Failed to load resource" (an expected 404/502 on `/api/*` in replay mode) is ignored.
5. `at least one clickable mark` — `#strips button.m` count > 0.
6. `proof drawer opens with text` — after clicking the first mark, `#drawer[open] #dr-body` has text.
It also prints `INFO ... replay badge visible = true/false` and writes `desktop-light.png`, `desktop-light-drawer.png`, `phone-dark.png`, `phone-dark-drawer.png`.

Status at writing: script tested on the current `web/` (no app.js): 4/10 PASS (checks 3 and 4 pass at both sizes; 1, 2, 5 fail as expected).

## 2. Go and see (commands and what you should see)
| # | Do | Expect |
|---|---|---|
| 1 | Serve `web/` with no API (`python3 -m http.server 8790` in web/), run the script | All PASS, `replay badge visible = True` |
| 2 | Run the API locally (M10 3_STEPS step 2) behind the same origin, or run against the Vercel URL | All PASS, `replay badge visible = False` |
| 3 | `curl -s https://<project>.vercel.app/api/demo?seed=7 \| python3 -c "import json,sys;d=json.load(sys.stdin);print(d['leaver'],[len(d['lanes'][l]['failures']) for l in 'WRG'])"` | Same leaver and counts the page shows in section 01 |
| 4 | Stop FalkorDB on EC2 (`docker compose stop falkordb`), reload the page | Badge "Replay data" appears; the page still works. `/api/demo` returns 503 (server/app.py:22). Start it again after (`docker compose start falkordb`) |
| 5 | Click a red mark | Drawer lists sources with type and text; no Cypher unless the API sent it |
| 6 | Section 03: assign every duty, press Replay | Receipt: accepted N, refused 0, failures after 0, live hash unchanged |
| 7 | Section 03: assign one duty to the leaver | That row is refused with "person is the one leaving" (baton/handover.py:57) |
| 8 | Open the page on a phone (or 390 px) | No sideways page scroll; the month strip scrolls inside its frame (web/styles.css `.strips { overflow-x: auto }`) |

## 3. Failure modes and fallbacks
| Failure | What the user sees | Fallback |
|---|---|---|
| API down / Vercel rewrite fails / EC2 stopped | badge "Replay data" | recorded `web/mock/*.json` (docs/BUILD_PLAN.md:73) |
| `/api/demo` slow on first call (generate + load) | spinner | timeout in app.js, then replay; pre-warm with one `curl` after each deploy (M11) |
| "New random company" | HTTP 500 today: no cached beliefs and no `extract` command (server/app.py:31-36; baton/__main__.py:11-46) | disable the button, or show "needs the extractor" until M5 is green |
| `/api/ask` | 200 in the latest local run; was 500 before `ask` was added | if locked ask checks are red at 14:30, hide section 04 (docs/BUILD_PLAN.md:68) |
| Mock data and live data differ in shape | page breaks only in one mode | record replay from the API (3_STEPS step 2) |

## 4. Design rules (from web/styles.css and web/index.html)
- Colour only through tokens on `:root` (web/styles.css:1-25); dark values under `@media (prefers-color-scheme: dark)` guarded by `:root:not([data-theme="light"])` (web/styles.css:27-35) and again under `:root[data-theme="dark"]` (web/styles.css:36-42). `body` has an explicit background (web/styles.css:46-48).
- System fonts only (`--serif`, `--sans`, `--mono`, web/styles.css:20-22). No web fonts, no external scripts today.
- Phone: 16 px side gutter (`.wrap`, web/styles.css:50), 40 px from 720 px (web/styles.css:51); `body { overflow-x: hidden }` (web/styles.css:48); narrow layout under 760 px (web/styles.css:182-183).
- Meaning is never colour alone: red mark has "×", green has "✓", "cannot see" is a dashed outline (web/index.html:49-51; web/styles.css:118-120).
- Motion off under `prefers-reduced-motion` (web/styles.css:336).
- Words: plain, short. Never: "predicts failures", "autopilot", "production-ready", "replaces Okta", MVCC, "guaranteed" (docs/modules/00_GROUND_TRUTH.md:51).

## 5. Anti-hallucination list (what a coding agent will likely get wrong)
| Likely wrong assumption | Correct fact | Source |
|---|---|---|
| Times are ISO strings like the mock | `now`, `leave_at`, `at`, `left_at` are epoch-ms ints | baton/generate.py:13-16, :449-450 |
| Seed 7's leaver is Priya Raman | Seed 7's leaver is `hana.sharma` (Hana Sharma) in the current generator; Priya is only in the hand-written mock | live `/api/demo?seed=7`; baton/generate.py:206 |
| Person ids look like `p-priya` | ids are `first.last` | baton/generate.py:204 |
| The mock's Cypher is real | It uses `Obligation`, `OWNER_FIELD`, `ON_CALL`, `DOES`, which do not exist in the graph. Real labels/types: `Duty`, `Event`, `Person`, `Rota`, `Source`, `OWNER`, `ROUTES_TO`, `SHIFT`, `ESCALATES_TO`, `NEEDS` | baton/load.py:6-9, :21-63 |
| `/api/demo` has `ghost_duties`, `company`, `path_before`, `cypher` | It has none of these | server/app.py:73-76 |
| `/api/health` proves FalkorDB is up | It returns `{"ok": true}` without touching FalkorDB | server/app.py:58-60; measured |
| A person said "yes" to each ghost duty | The demo runs with `--confirm all` | server/app.py:70 |
| "A duty only enters the graph with two independent sources and the person's own yes" (current copy, web/index.html:64) | The gate is: at least 2 cited sources, all exist, at least 2 source kinds (rehearse.py Q_GATE). A promoted belief becomes a `HOLDS` edge with basis `confirmed` under `--confirm all`, or `believed` under `--confirm none`; it still enters the fork's graph either way. Rewrite the copy to say exactly that | baton/rehearse.py:36-44, :46-50, :129 |
| Handover changes the real graph | It runs on a fork; the live graph is only fingerprinted | baton/handover.py:11, :87 |
| `sources` in `/api/demo` are id strings | They are `{id, type, text}` objects after `enrich` | server/app.py:53-54 |
| `sources` in `/api/ask` are objects | They are id strings; the API does not enrich them | checks/locked/ask/test_ask.py:50, :83; server/app.py:104 |
| The six tool names in the catalogue list are real | There are five: `owes`, `breaks_if_leaves`, `why`, `covers`, `none` | web/index.html:109-114; baton/ask.py:59-64 |
| Any seed works | Only seeds with `fixtures/beliefs_seed<N>.json` work until `extract` exists; today only seed 7 | server/app.py:31-36; fixtures/ |
| `unpromoted` covers all lanes | It comes from the last (G) lane run | server/app.py:68-75 |
| cytoscape.js is on the page | No script besides app.js is loaded | web/index.html:138 |
