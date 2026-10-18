# M03 · Handover and demo (`baton/handover.py`, `baton/demo.py`) · SPEC

Written 11:55 IST, 18 Oct. Status: **built and green**. Round 3 was kept at 32/32 (commit d38d0db, loop/results.tsv:5, loop/rounds/rehearsal_core-3.md "Result"). Code checked: `handover.py` md5 `d4637781…`, `demo.py` md5 `d1a68249…`.

## What it is, in plain words
**Handover.** For each duty that would break, someone who is staying says "I'll take it". Baton writes that acceptance as a new owner edge, and the database itself checks two rules:
- the person must still be at the company and must not be the leaver;
- only one accepted successor is allowed per duty.

Then Baton runs the rehearsal again and shows what is still broken. If everyone accepted, the list is empty (baton/handover.py:1-11).

**Demo.** One command tells the whole story: make the company, load it, rehearse lanes W, R and G, hand every G failure to a colleague (taking turns down the list), and show zero failures left. The beliefs come from a saved AI extraction file. No model is called (baton/demo.py:1-5).

A 14-year-old version: *"After we find what breaks, we let teammates claim each job. The database refuses anyone who has already left, and it refuses a second person for the same job. Then we check the month again: nothing breaks."*

## Which focus points it serves
- Track 1, "actions based on what the graph shows" (docs/modules/00_GROUND_TRUTH.md:9). The duties offered for handover are exactly the rehearsal's failures (baton/demo.py:47-48).
- Track 3, "who owns what" and "keeping knowledge current as things change" (docs/modules/00_GROUND_TRUTH.md:8). Ownership moves only on acceptance. A FalkorDB UNIQUE constraint enforces one owner per duty (baton/handover.py:6-8, baton/handover.py:33-46).

## In scope
- `python -m baton handover --world DIR --beliefs FILE --leaver ID --assign DUTY=PERSON ... [--port P]` (baton/__main__.py:27-32, baton/__main__.py:63-65).
- `python -m baton demo [--seed N] [--port P] [--offline] [--beliefs FILE]` (baton/__main__.py:42-46, baton/__main__.py:75-77).
- The contract from the project-context skill (.claude/skills/project-context/SKILL.md:17-18) and locked checks 12, 13 and 15 (checks/locked/rehearsal_core/test_rehearsal_core.py:160-216).

## Not in scope (not in M03 code; do not claim it)
- **Writing the handover to the live graph.** Acceptances are written on the fork, and the fork is deleted (baton/handover.py:87, baton/rehearse.py:131-135). The handover is rehearsed, not committed. A real write to the live graph is `PROPOSED (not yet in code)`; the team decides.
- An approver or manager authority check. The "authority re-check" here is: the duty exists, the person exists, `left_at IS NULL`, and the person is not the leaver (baton/handover.py:20-25). The approver-role pattern in the scratchpad `verify/spike.py` (lines 55-65) is not used.
- Closing the leaver's old OWNER edge (`SET a.vt = …`). The leaver's departure is modelled only by `left_at` (baton/rehearse.py:56).
- Gitea, Slack, a human "accept" button, read-back receipts, `algo.maxFlow` / the cut (docs/BUILD_PLAN.md:40, docs/BUILD_PLAN.md:20).
- Calling an LLM. `--offline` is accepted, but demo is always offline today (baton/demo.py:30). There is no `extract` command yet (baton/__main__.py:7-46 lists none).
- A `Makefile` with `make demo`. The file does not exist; it is `PROPOSED`. Makefile is a mutable path (loop/config.json "mutable_paths").

## Inputs and outputs
- handover: in, the same world/beliefs/leaver as rehearse plus repeated `--assign DUTY=PERSON`. Out: `{leaver, graph, accepted[], refused[], failures_after[], live_hash_before, live_hash_after}` (baton/handover.py:89-91).
- demo: in, a seed and a port, plus the cached beliefs at `fixtures/beliefs_seed<N>.json` (baton/demo.py:15, baton/demo.py:21). Out: `{seed, offline, graph, leaver, lanes:{W,R,G:{failures:int}}, live_hash_before, live_hash_after, after_handover:{failures, accepted, refused}, unpromoted:int}` (baton/demo.py:51-55).

## Dependencies
- M02: `rehearse.open_session`, `on_fork(before_departure=…)` and `failures` (baton/handover.py:86-90, baton/demo.py:36-42).
- M01: `generate.build` (baton/demo.py:32).
- `fixtures/beliefs_seed7.json` (only seed 7 exists today). The round-3 log calls it the orchestrator's file (loop/rounds/rehearsal_core-3.md).
- `redis.exceptions.ResponseError` to detect the constraint violation (baton/handover.py:15, baton/handover.py:73-76).
- Downstream: the API `/api/handover` calls the `handover` CLI (server/app.py:84-93). `/api/demo` does **not** call `baton demo`; it calls `rehearse` three times (server/app.py:63-76).

## Owner, time, kill
- Owner: the build loop (round 3 builder). The checks were approved by Rhudhresh before the code (loop/reports/rehearsal_core.md, "Integrity").
- Time: planned as "next round" (docs/BUILD_PLAN.md:39). Done at about 12:05 IST (loop/reports/rehearsal_core.md).
- Kill and fallback: the same feature as M02, so "14:30 not green → hero = Cut + reason-broken query" (docs/BUILD_PLAN.md:66). Not needed.
- Still to do: the go-and-see on the real entrypoint. The round-3 log says "Not yet done: orchestrator's go-and-see on the real entrypoint" (loop/rounds/rehearsal_core-3.md). The later report lists go-and-see facts for the CLI and the API (loop/reports/rehearsal_core.md, "Go and see").
