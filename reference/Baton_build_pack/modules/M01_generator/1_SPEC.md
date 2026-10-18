# M01 · Generator (`baton/generate.py`) · SPEC

Written 11:40 IST, 18 Oct. Status: **done**. Round 1 was kept with 9/32 checks passing (loop/results.tsv:3). The engine rounds after it brought the total to 28/32 (loop/results.tsv:4).

## What it is, in plain words
The generator makes up a small, fake company called Halden. It writes down what that company's systems would hold: people, their duties, who owns what, on-call rotas, a calendar of scheduled events, chat messages, job logs and customer tickets. The same seed always gives exactly the same company (baton/generate.py:6, baton/generate.py:135).

It never writes down what breaks when someone leaves. It only plants **schedules**: cert expiry dates, job run times, rota weeks and promise due dates. The engine (M02) has to work out the failures itself, by walking the graph (baton/generate.py:5).

It also writes a separate answer key. The key lists the "beliefs" that a careful reader of the chat would form, split into true ones and planted noise (baton/generate.py:4-5, baton/generate.py:456-458). Only the locked checks read the key. The product must never read it (checks/locked/rehearsal_core/test_rehearsal_core.py:220-227).

## Why it matters for the event
- Rule 6 says the data must be public, synthetic or our own. Halden is synthetic and every world carries the label `FIXTURE` (docs/modules/00_GROUND_TRUTH.md:12, baton/generate.py:449).
- Track 3 asks for "knowledge from docs, tickets and chats in one graph" (docs/modules/00_GROUND_TRUTH.md:8). The generator is where the chats, job logs and tickets come from.
- It answers the obvious judge question "you planted the failures". The world holds schedules only, and a locked check makes sure no answer-key words leak into world.json (checks/locked/rehearsal_core/test_rehearsal_core.py:41-43).

## In scope
- `python -m baton generate --seed N --out DIR` (baton/__main__.py:11-13, baton/__main__.py:54-56).
- Writes `DIR/world.json` and `DIR/answer_key.json` (baton/generate.py:471-472).
- `generate.build(seed)` returns `(world, answer_key)` in memory. The demo (M03) uses this function directly (baton/generate.py:462-464, baton/demo.py:32).
- The planted shapes, listed in 2_CONTRACT.md §4.

## Not in scope
- Working out failures. That is M02's job.
- Calling any AI model. The generator uses only the Python standard library: `json`, `random`, `datetime`, `pathlib` (baton/generate.py:8-11).
- Making the beliefs file that the demo uses. That is `fixtures/beliefs_seed7.json`, and the generator did not write it (its ids look like `b-01`, while the generator writes `blf-NN`, see baton/generate.py:444). Who wrote it: the round-3 log calls it "the orchestrator's fixtures/beliefs_seed7.json" (loop/rounds/rehearsal_core-3.md). The future `extract` module (M5) is meant to produce such files (docs/BUILD_PLAN.md:42).

## Inputs and outputs
- Input: an integer seed. Nothing else, not even the clock. `now` is a fixed date: Friday 2026-10-23 00:00 UTC (baton/generate.py:16).
- Output: two JSON files, written with sorted keys and an indent of 1 (baton/generate.py:471-472). On stdout it prints a short summary: seed, folder, leaver, graph name, counts, number of beliefs (baton/generate.py:473-476).

## Dependencies
- Upstream: none.
- Downstream: M02 reads world.json (baton/load.py:66-67). M03 calls `generate.build` (baton/demo.py:32). The web API calls `generate` through the CLI (server/app.py:29-30). The locked checks call it for seeds 7, 11, 12, 101, 202 and 303 (checks/locked/rehearsal_core/test_rehearsal_core.py:9, checks/locked/rehearsal_core/test_rehearsal_core.py:30).

## Owner, time, kill
- Owner: the build loop (the feature-builder agent, round 1). A human approved the checks before the build (checks/locked/MANIFEST.json, "history"). BUILD_PLAN names no single person for this module.
- Time budget: spent. Round 1 finished at 05:58 (loop/results.tsv:3).
- Kill time and fallback: none needed, it is done. **Freeze rule:** do not change the generator's output after the fixture beliefs exist (see 3_STEPS.md, step 3). Any change shifts the ids that `fixtures/beliefs_seed7.json` cites.
