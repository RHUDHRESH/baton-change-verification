# M12 · Ship — CONTRACT

Everything here is either copied from a file (cited) or `PROPOSED` text that the two team members approve. Bracketed `[...]` values must be filled from the frozen build; never from this doc, the old plan, or the mock files.

## 1. Fixed names
| Item | Value | Source |
|---|---|---|
| Freeze tag | `v-freeze` (annotated, pushed, never moved) | docs/BUILD_PLAN.md:73; scratchpad/book/BATON_FINAL_PLAN.md:189 |
| Tracks named on the form | Track 3 "Company Brain" and Track 1 "Agents That Act on Connected Data" | docs/modules/00_GROUND_TRUTH.md:8-10 |
| Company label | Halden, synthetic, "FIXTURE" | docs/modules/00_GROUND_TRUTH.md:12; baton/generate.py:449 |
| FalkorDB version | `falkordb/falkordb:v4.22.1` | docker-compose.yml:3 |
| Video length | ≤ 2:45, 6 beats, recorded from the live URL | docs/BUILD_PLAN.md:74 |

## 2. Video: 6 beats (PROPOSED, re-framed for Track 3; replaces scratchpad/book/BATON_FINAL_PLAN.md:142-151)
Record the screen of `https://<project>.vercel.app` with the "Replay data" badge **hidden** (live). If the badge shows, stop and fix M11 first, or say on screen "recorded data".

| # | Time | On screen | Words (plain; fill [ ] from the frozen build) |
|---|---|---|---|
| 1 | 0:00–0:20 | Hero: tagline, leaver line | "Every company brain knows who knows what. Baton knows who owes what, and the exact day it breaks if they leave. Here, [leaver_name] leaves on [leave_at date]." |
| 2 | 0:20–0:50 | Section 02: promoted and refused duties; open one source list | "Some work is in no system. It shows up in chat, job logs and tickets. An AI read those and proposed duties. One only enters the graph if it cites at least two sources of two different kinds. These [n] were refused, with the reason. In this demo the person's confirmation is simulated." |
| 3 | 0:50–1:35 | Section 01: three strips; click one red mark in G that W and R miss; drawer shows sources | "Same company, same month, three views. W is what an offboarding checklist sees: owner fields only. [W] problems. R adds every system record: rotas and escalation chains. [R]. G adds the duties found in chat and logs. [G]. Each red mark is a scheduled event with no path, of at most four hops, to someone still here. Click it and you see where that came from." Then the hashes: "This ran on a copy of the graph. The real graph's fingerprint is the same before and after." |
| 4 | 1:35–2:00 | Section 04 Ask (only if the locked ask checks are green), else FalkorDB Browser on graph `halden_7` | Ask: "Ask a question. The model only picks a query from a fixed list; it never writes Cypher. The answer comes with its sources." Browser fallback: "This is the graph in FalkorDB: duties, people, rotas, events, and the evidence." |
| 5 | 2:00–2:25 | Section 03: assign successors, Replay → 0; then a terminal: `docker compose stop falkordb`, `curl .../api/demo` → 503 | "Pick a successor for each duty. Replay the month on a copy: [0] left. Assign one to someone who has left and it is refused. Turn FalkorDB off and Baton cannot answer at all. The graph makes every decision." |
| 6 | 2:25–2:45 | README top on GitHub; limits line | "Synthetic company. It only checks what is already scheduled, so it is a lower bound. AI coding help is disclosed in the repo. Baton: who owes what, and the day it breaks." |

Swap-ins, only if green at 15:30 and shown working on the live URL: `algo.maxFlow` Cut verdict (beat 4 or 5); MCP tool call from an agent (beat 4, Track 1). Hero-only fallback (60 s): beats 1, 3, 5 (docs/BUILD_PLAN.md:74).

## 3. README top section (PROPOSED text; paste at the top of `README.md` and fill every [ ])
```markdown
# Baton

**Every company brain knows who knows what. Baton knows who owes what, and the exact day it breaks if they leave.**

Graph Hacks (WeMakeDevs × FalkorDB). Tracks: **Track 3 – Company Brain** and **Track 1 – Agents That Act on Connected Data**.
Live: [https://<project>.vercel.app] · Video: [unlisted link] · Code frozen at tag `v-freeze`.

When someone leaves, some of their work is written down nowhere: a job they rerun by hand, the end of an on-call
escalation chain, a promise in a ticket or a chat. Baton puts records, chat, job logs and tickets into one FalkorDB
graph. Before the person leaves, it copies the graph (`GRAPH.COPY`), marks them as gone on the copy, and checks every
event already scheduled in the next 30 days: is there still a path, of at most 4 hops with every edge valid at that
moment, to someone who can act? Each "no" comes with its sources. The copy is deleted and the real graph's
fingerprint is unchanged.

- **The model reads. The graph decides.** The AI turns text into proposed duties (JSON). It never writes Cypher.
  A proposal counts only if it cites at least 2 existing sources of at least 2 kinds; the check is a Cypher query.
- **Not a prediction.** Baton only walks what is already scheduled. It is a lower bound.
- **Same month, three views** (seed 7, frozen build): owner fields only (W) [W] · all records (R) [R] · records +
  checked duties from chat and logs (G) [G].
- **Hand-over:** a successor is accepted by one guarded write; a FalkorDB UNIQUE constraint allows one accepted
  successor per duty. Replay after hand-over: [0] failures.
- **Turn FalkorDB off and Baton refuses** (the API returns 503).

> Halden is a synthetic company (FIXTURE). In the demo, the person's confirmation is simulated (`--confirm all`).
> AI use is disclosed below.
```
Below it, in this order (rule 10, docs/modules/00_GROUND_TRUTH.md:13): setup (`docker compose up -d --build`, then `curl localhost:8000/api/health` and `/api/demo?seed=7`); the data model (copy baton/load.py:5-11, add `(:Duty)-[:HOLDS]->(:Person)` from baton/rehearse.py:6, :50); the queries the product depends on, pasted from the frozen files: `Q_GATE` (baton/rehearse.py:36-44), `Q_HOLDS` (baton/rehearse.py:46-54), `Q_DEPART` (baton/rehearse.py:56), `Q_COVER` (baton/rehearse.py:58-75), `GRAPH.COPY` (baton/graph.py:47-53), `Q_ACCEPT` and the UNIQUE constraint (baton/handover.py:20-25, :35-37), plus `algo.maxFlow` only if the Cut shipped; "We knowingly do not"; AI use; credits.

"We knowingly do not" (PROPOSED, re-framed): connect Slack, Okta or Jira (fragile sign-ins, no extra proof, docs/BUILD_PLAN.md:30); predict events that are not scheduled; claim MVCC or scale (one synthetic company, v4.22.1 C engine, docs/modules/00_GROUND_TRUTH.md:18); store real chat text (all text is synthetic). Add any feature that was cut at 15:30.

## 4. AI-use disclosure (PROPOSED text; rules 11–13, docs/modules/00_GROUND_TRUTH.md:14). Fill the [ ] honestly.
```markdown
## AI use
We used AI coding assistants, as the rules allow, and we disclose it here.
- **Claude (Anthropic), through Claude Code**, wrote most of the code in `baton/`, `server/` and `web/`, and drafted
  these docs, inside a "Karpathy loop": we wrote plain-language checks first, a team member approved and locked them
  (`checks/locked/MANIFEST.json` records who approved and when), then the agent built until they passed.
  [Round log: `loop/results.tsv` is git-ignored (.gitignore:2), so either commit an exported copy and link it here, or
  delete this sentence.]
- **[GPT model name / none]** was used [once, with a team member's key, to extract proposed duties from the synthetic
  chat and logs; the output is cached in `fixtures/` so the demo needs no key] / [not used; the cached extraction in
  `fixtures/` was produced by Claude and is labelled as such].
- **What we did ourselves:** [chose the problem and the Track 3 framing; designed the W/R/G lanes and the two-source
  rule; approved every locked check; ran and recorded the demo; checked every claim in this README against the
  frozen build; …].
- The AI never writes Cypher at run time. All Cypher in the product is fixed text in the repo.
```

## 5. Credit (PROPOSED text)
```markdown
## Credits
- **agent-memory-bench** by Liz Zhang (FalkorDB DevRel), MIT licence, "Copyright (c) 2026 Liz Zhang" —
  https://github.com/zhang-liz/agent-memory-bench (commit b8ccc40). Adapted in `baton/llm.py` and `baton/extract.py`
  (MIT notice kept in each file header); `amb/world.py` vendored unchanged in `third_party/amb/` with its LICENSE.
  Our "departure" question type extends her benchmark idea.
- **falkordb-py** (MIT) client; **FastAPI**, **uvicorn**; **FalkorDB** server run as the official Docker image.
```
Sources: licence and copyright line (scratchpad/falkor/repos/agent-memory-bench/LICENSE:1-3; third_party/amb/LICENSE:1-3); repo URL and commit (`git remote -v` and `git log` of that clone: `zhang-liz/agent-memory-bench`, `b8ccc40 Add MIT license`; the GitHub page loads, MIT, not a fork, checked 18 Oct); adapted files (baton/llm.py:1-4; baton/extract.py:1-3; third_party/amb/world.py:1); planned use (docs/modules/00_GROUND_TRUTH.md:41; docs/BUILD_PLAN.md:17). The locked check `test_amb_import_is_deterministic_loadable_and_credited` requires a vendored file naming "Liz Zhang" and a LICENSE under `third_party/` (checks/locked/ai_layer/test_ai_layer.py:78-90).

**URL mismatch to fix before the freeze:** baton/llm.py:1, baton/extract.py:2 and third_party/amb/world.py:1 give the URL `https://github.com/zhang-liz/agent-memory-bench`. We could not load that page (fetch error, 18 Oct); the clone we used comes from `https://github.com/zhang-liz/agent-memory-bench`. Use the zhang-liz URL in the README, and change the three headers to it unless someone confirms the FalkorDB URL exists (loop owner for `baton/`; human for `third_party/`).

## 6. Submission form content
Only these items are required by the rules as we have them (docs/modules/00_GROUND_TRUTH.md:10, :13-14): public repo URL, demo video, live URL (preferred), every track entered named, AI use disclosed. Exact form field names: UNVERIFIED (we have not seen the form). Placeholder at 18:30 with the same tracks; final at 21:00.
