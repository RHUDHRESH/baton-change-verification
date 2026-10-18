# M07 · eval (sealed) — spec

Path convention: repo paths are relative to `/home/claude/baton/`. `amb/...` = the agent-memory-bench clone at commit `b8ccc40` (see M05 1_SPEC).

## Status at writing (about 12:35 IST)
- No `eval/` folder exists yet (`ls eval` failed).
- Drafted, **not locked** checks exist in `checks/pending/eval/test_eval.py`. They define the CLI (`python -m eval.run ...`), the output files, and a new generator flag `--scale` (test_eval.py:13-81). This pack follows those checks. Everything beyond them is marked PROPOSED.

## What it is, in plain words
We make 30 new companies that nobody has looked at. Before running anything, we write in git what we expect. Then we run each way of answering "what breaks when the leaver goes?" on every company and grade them all against the same locked reference checker:
- **W**: only the owner fields.
- **R**: all the records.
- **G**: records plus AI beliefs that passed the gate.
- **A**: the AI alone, with no graph.

We also grow the company 4–8 times bigger to check that Baton stays exact and fast. We count how many model tokens each lane spends per question. We report averages with 95% error bars, and we say plainly where we lose.

The short version: "We write our guess down first, then test on companies we've never seen and bigger ones, and grade everyone with the same answer sheet. If the AI on its own beats us at something, we say so."

## Why
- The plan: "Sealed eval: 30 unseen companies. W/R/G are scored against the independent checker; lane A (AI alone, same model and data) and false-claim adoption are scored too. Predictions are committed first, results come with bootstrap CIs, and we report where we lose." (docs/BUILD_PLAN.md:43). Also: "Predictions are committed to git before the run." (docs/BUILD_PLAN.md:56).
- The drafted checks add: "Baton stays exact as the company grows, and costs ~no model tokens per question after one extraction, while the AI-alone lane must re-read everything" (checks/pending/eval/test_eval.py:1-3). That is a hypothesis to measure, not a fact to claim.
- Rule 2/3: "If the product still works once FalkorDB is taken out, the graph is decoration" (docs/modules/00_GROUND_TRUTH.md:11). Lane A is the "graph taken out" run.
- Track focus: no new feature. It backs "answers with clear sources" (docs/modules/00_GROUND_TRUTH.md:8) and "explainable results" (docs/modules/00_GROUND_TRUTH.md:9) with numbers. Judging criteria are not published (docs/modules/00_GROUND_TRUTH.md:15).

## Where it lives (a deliberate change from BUILD_PLAN)
- BUILD_PLAN names `baton/eval.py` (docs/BUILD_PLAN.md:43). The drafted checks put the harness in `eval/` at the repo root as a package run with `python -m eval.run` (test_eval.py:2-3, 53). It must live outside `baton/`, because it imports the locked reference, and any `baton/*.py` containing "oracle" fails a locked check (checks/locked/rehearsal_core/test_rehearsal_core.py:220-225). The eval may read `answer_key.json`; the product never does.
- `eval` is in the loop's `mutable_paths` (loop/config.json; loop/program.md:16-19), so the loop can build it under locked checks. Owner for the sealed run: "me" (docs/BUILD_PLAN.md:71).
- `generate --scale` (test_eval.py:13-34) is a generator change. It belongs with M1 and is listed here only because the eval checks need it.

## In scope
- `eval/run.py` and helpers, `eval/PREDICTIONS.md`, the sealed run, and `report.md`.
- Metrics: `exact` (agreement with the reference), `precision`, `recall`, `model_tokens_per_question` (test_eval.py:60). PROPOSED extras: duty-level recall across all lanes, invented duties, false claims adopted (BUILD_PLAN asks for false-claim adoption, docs/BUILD_PLAN.md:43).
- 95% cluster-bootstrap CIs adapted from amb/analyze.py:65-78.

## Not in scope
- Any live model call. Those happen only in M05's key-holder run (M05 2_CONTRACT §6), after the predictions commit.
- Tuning prompts, generator or engine on sealed seeds. A change after sealing voids the seal.
- The old prediction families in BATON_FINAL_PLAN §9 ("nested-group reach", "grants that should end"). The generator has no groups or grants (baton/generate.py:176-189).

## Inputs
- Seeds and scales; the CLI (`generate`, `rehearse`, `extract`, `lane-a`); the caches `fixtures/extract_cache/` and `fixtures/lane_a_cache/` (baton/extract.py:30; baton/lane_a.py:21); the locked reference `expected_failures`, `promoted`, `source_index` (checks/locked/rehearsal_core/oracle.py:24-40, 80-97).

## Outputs
- `--out DIR/results.json` and `DIR/report.md` (test_eval.py:57, 66). For the real run, PROPOSED `--out eval/results/sealed`, committed after `eval/PREDICTIONS.md` (test_eval.py:69-81).

## Dependencies
- M2 rehearse (green), M05 offline replay, M1 `--scale`, and the teammate's caches for the sealed seeds. Without those caches, lanes G_ext and A are "not run" (pre-registered fallback).

## Owner, time, kill
- Owner: "me" (docs/BUILD_PLAN.md:71).
- Time: 15:00–15:45 IST (docs/BUILD_PLAN.md:71). The predictions commit comes **before** the teammate's sealed run, because running lane A is running a lane.
- Kill: "fewer seeds; still report" (docs/BUILD_PLAN.md:71). 15:30: "No new features" (docs/BUILD_PLAN.md:72).
