# M10 · Web (the static site) — SPEC

Status when written (18 Oct, during the build): `web/index.html` and `web/styles.css` exist; `web/app.js` does **not** exist yet (index.html loads it at `web/index.html:138`). `web/vercel.json` does not exist yet. Another agent is building the site. This doc describes the target and the contract. It is not proof that anything works.

## What it is, in plain words
One web page. It shows a company (synthetic, "Halden"), the person who is leaving, and a month-long strip of days. Each red mark is a scheduled job, shift, renewal or promise that will have nobody able to act on it after that person leaves. Click a mark and you see the proof: the source records, chat lines, job logs or tickets behind it. Then you pick successors, press "Replay month", and the marks go away. You can also ask the company brain a question and get an answer with its sources.

The page does no reasoning. Every answer comes from the API, which runs the `python -m baton` CLI, which asks FalkorDB (server/app.py:1, server/app.py:17-23). If the API cannot be reached, the page shows recorded data and says so with a "Replay data" badge (web/index.html:18).

## Which judging focus it serves
- Track 3 "Company Brain": "who owns what", "tracing decisions back to their source", "answers with clear sources" (docs/modules/00_GROUND_TRUTH.md:8). The proof drawer and the Ask section show sources for every answer.
- Track 1: "explainable results" (docs/modules/00_GROUND_TRUTH.md:9). Each red mark opens its evidence.
- Rule 10: "live deployment preferred" (docs/modules/00_GROUND_TRUTH.md:13). This page is the live URL the video is recorded from (docs/BUILD_PLAN.md:74).

## Sections (as they exist in web/index.html)
| # | Section | Element ids | Source |
|---|---|---|---|
| top | Brand, track line, replay badge | `#badge` | web/index.html:14-20 |
| hero | Tagline, leaver line, company picker ("Company #7", "New random company") | `#leaver-line`, `#leaver-sub`, `#seed-7`, `#seed-rand`, `#seed-now` | web/index.html:23-40 |
| 01 | "Same month, three ways": three lane strips (W, R, G) across the window | `#month-sum`, `#strips` | web/index.html:42-58 |
| 02 | "Duties no system records": promoted vs refused beliefs | `#ghosts`, `#refused` | web/index.html:60-76 |
| 03 | "Hand it over": successor picker, Replay, receipt | `#handover`, `#replay`, `#reset`, `#hand-status`, `#receipt` | web/index.html:78-91 |
| 04 | "Ask the company brain": question box, example chips, answer, query catalogue | `#ask-form`, `#ask-q`, `#chips`, `#answer` | web/index.html:93-117 |
| foot | FIXTURE label, repo link (still `REPLACE_ME`) | `#repo-link` | web/index.html:120-125 |
| drawer | Proof dialog for one mark | `#drawer`, `#dr-lane`, `#dr-title`, `#dr-body`, `#dr-close` | web/index.html:127-136 |

## In scope
- Render the four sections from the API responses listed in 2_CONTRACT.md.
- Fall back to recorded replay data when any API call fails, and show the badge.
- Work at phone width (390 px) and desktop, light and dark, with no sideways page scroll.
- Screenshots and checks by Playwright ("go and see").

## Not in scope
- Any graph reasoning in JavaScript. The browser never decides what breaks.
- Writing Cypher in the browser, or showing Cypher that the product did not run (see 4_ACCEPTANCE.md anti-hallucination list).
- Logins, Slack, Okta, Jira, Gitea views.
- A cytoscape graph view. It is listed in docs/BUILD_PLAN.md:22 but index.html loads no such script (web/index.html:138 is the only script). PROPOSED, web owner decides; skip unless everything else is green.

## Inputs and outputs
- Inputs: `GET /api/demo?seed=N`, `POST /api/handover`, `POST /api/ask` (server/app.py:63, :84, :101), or the replay JSON files when the API is down.
- Outputs: the page, plus screenshots in `web/_shots/` (folder exists, empty).

## Dependencies
- M2 rehearsal engine (lanes W/R/G, failures, unpromoted): exists and returns data today (measured: see 4_ACCEPTANCE.md).
- M3 handover: the CLI dispatches `handover` (baton/__main__.py:63-65); `POST /api/handover` returned HTTP 200 in our local run.
- M4 ask: the CLI now has `ask` (baton/__main__.py:34-40, :66-74) and its checks are locked (checks/locked/ask/test_ask.py). In a local re-run after that change, `POST /api/ask` returned HTTP 200 with `tool: breaks_if_leaves`. Whether the locked ask checks pass is not known to this doc; if they are red at 14:30, hide section 04 (docs/BUILD_PLAN.md:68: "not green → web shows only the Rehearsal").
- M5 extract: **not wired**. "New random company" calls `/api/demo?seed=<new>`; for any seed without `fixtures/beliefs_seed<N>.json` the API runs `extract` (server/app.py:31-36), which the CLI does not have (its commands are generate, load, rehearse, handover, ask, demo: baton/__main__.py:11-46), so it returns HTTP 500 today (measured for seeds 12345 and 99). `baton/extract.py` exists but is not a CLI command. Only seed 7 has a cached file (`fixtures/beliefs_seed7.json`).
- M11 deploy: the live URL and the `/api/*` rewrite.

## Owner, time, kill
- Owner: the web agent (building now) + the human who records the video. Final call on PROPOSED items: the human team lead.
- Time budget: done by 15:30 "No new features" (docs/BUILD_PLAN.md:72); deployed at the 16:00 freeze (docs/BUILD_PLAN.md:73).
- Kill / fallback: "site falls back to replay data" (docs/BUILD_PLAN.md:73). If Ask is not green by 14:30, the page shows only the Rehearsal (docs/BUILD_PLAN.md:68).
