# M04 · ask — spec

Path convention: repo paths are relative to `/home/claude/baton/`. Line numbers were checked on 18 Oct at about 12:40 IST. The code changes every few minutes, so re-open a file before you rely on a line.

## Status at writing
- `baton/ask.py` exists. All 17 locked ask runs pass: `checks/locked/ask/test_ask.py` (11 runs) plus `checks/locked/ask/test_ask_ratchet.py` (6 runs). The writer ran `pytest checks/locked/ask` and got "17 passed". loop/features.md:9 still says 11/11 and has not been updated yet.
- One latent bug was found at doc time: "on day -4" is routed as day 4. The checks pass by luck. See 2_CONTRACT §3.2 and 4_ACCEPTANCE A-3.

## What it is, in plain words
You type a question about the company, such as "What does Hana Sharma owe?", "Who owns the warehouse snapshot?" or "What breaks if Hana Sharma leaves?". Baton picks one query from a short, fixed list, runs it in FalkorDB on a throw-away copy of the graph, and answers with the ids of the sources it used. If the question does not fit the list, it says "That is not in the graph" and cites nothing. Nobody writes Cypher on the fly, and no model writes it either (baton/ask.py:3-5).

The short version: "It's a search box that can only ask the database a few kinds of question. It shows its working, and it says 'I don't know' when it doesn't."

## Why
- Track 3 focus points: "who owns what and who knows what" and "answers with clear sources" (docs/modules/00_GROUND_TRUTH.md:8).
- Track 1 focus points: "graph queries and algorithms as agent tools" and "explainable results" (docs/modules/00_GROUND_TRUTH.md:9). The same catalogue is what M8 (MCP) would expose (docs/BUILD_PLAN.md:44).
- "The model never writes Cypher; that is our safety story." (docs/BUILD_PLAN.md:29).

## In scope
- Tools `breaks_if_leaves`, `owes`, `why`, `who_owns`, `covers`, `none`, and `ask --catalogue` (baton/ask.py:71-78; checks/locked/ask/test_ask.py:29-78; checks/locked/ask/test_ask_ratchet.py:28, 38).
- Answers that use human names, not raw duty ids (test_ask_ratchet.py:44-52; baton/ask.py:236).
- Remaining work: the negative-day fix, then go-and-see through the API.

## Not in scope
- **A model choosing the tool.** "Not included: live-model routing quality (an offline deterministic router is checked; the model router reuses the same catalogue)" (loop/features.md:45). `ask.run` takes an `offline` argument but never reads it, and always reports `"router": "offline"` (baton/ask.py:299, 311).
- **The website's six-query list** (web/index.html:106-116) and `web/mock/ask_7.json`. They use names, labels and ids that are not in the code (4_ACCEPTANCE A-1, A-2). The web owner decides. "It picks one query from a fixed catalogue" (web/index.html:97) describes a model router that does not exist.
- Free-text, vector or text-to-Cypher search (docs/BUILD_PLAN.md:29).

## Inputs
`--world DIR` (`world.json`, baton/load.py:73-74) · `--beliefs FILE`, a JSON list in the generator's belief schema (baton/generate.py:318-321, 354-358) · `--question TEXT` · `--port P` (default 6379) · `--offline` (baton/__main__.py:40-46).

## Outputs
One JSON object: `question, tool, args, rows, sources, answer, cypher, graph, router, live_hash_before, live_hash_after` (baton/ask.py:310-322).

## Dependencies
- M2 engine: `rehearse.cover_query`, `gate`, `Q_HOLDS`, `on_fork`, `failures` (baton/rehearse.py:46-54, 86-94, 97-100, 121-139, 142-150).
- `baton/graph.py`: `connect`, `fork`, `fingerprint`, `OPEN` (baton/graph.py:7, 18-27, 39-44, 47-53).
- API: `POST /api/ask` calls the CLI without `--offline` (server/app.py:105-110). That makes no difference, because routing is always offline.

## Owner, time, kill
- Owner: the loop (docs/BUILD_PLAN.md:68). Time: 13:30–14:30 IST (docs/BUILD_PLAN.md:68).
- Kill: "8 rounds / 3 without progress; if not green by 14:30, the website shows only the Rehearsal" (loop/features.md:47). The locked checks are green, so the Ask section can ship as is.
- 15:30: "No new features" (docs/BUILD_PLAN.md:72).
