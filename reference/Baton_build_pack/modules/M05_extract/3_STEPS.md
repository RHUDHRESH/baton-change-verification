# M05 · extract (+ lane A) — build steps (remaining work)

`PY=/tmp/claude-0/-home-claude/9e986261-4c5d-5119-82fd-cce4a3dc1af5/scratchpad/venv/bin/python`. Run from `/home/claude/baton`.

## Loop rule (Karpathy loop): checks first, human approves, lock, then build
- The ai_layer checks are locked (checks/locked/ai_layer/). Never edit `checks/locked/**` or `loop/bin/**` (loop/program.md:16-19). Disputes go in `loop/disputes/` (loop/program.md:20-22).
- The loop may change only `baton`, `fixtures`, `eval`, `Makefile` and `README.md` (loop/config.json). `third_party/` is not loop-mutable, so a human adds vendored files there.
- One hypothesis per round, prediction first, keep only on a higher score with no regressions (loop/program.md:23-27). The score covers all of `checks/locked` (loop/config.json `check_command`).

## Done already (do not redo)
- `extract`, `lane-a` and `fake` are in place, and the seed-7 dev caches are committed with a provenance label. All 7 ai_layer checks passed when the writer ran them.

## Step 1 — human: two honesty decisions (5 min)
- (a) **17:00 rule.** The extract prompt says "If a date has no time, use 17:00 UTC" (baton/extract.py:161-162). That is the generator's hidden due time (baton/generate.py:341), which chat never shows (it prints only the date, baton/generate.py:128-130). Either keep it and disclose it in README/eval as "prompt written knowing the generator", or change it to a neutral rule and bump `PROMPT_VERSION` to `"v2"` (baton/extract.py:28). It does not change which duties fail, because promise due days are 3–27 days out (generate.py:340) and the leaver leaves at now + 1 day (generate.py:138). It changes only event times.
- (b) **Records in the extract prompt.** The prompt lists RECORDS with `rec-` ids and allows citing them (baton/extract.py:144, 163, 170). The gate counts "record" as a source kind (baton/load.py:96-97; checks/locked/rehearsal_core/oracle.py:29-30). So a one-message claim plus an unrelated record id passes "2 kinds". Either keep it and let M7 measure "false claims adopted", or drop records from the prompt (v2). BUILD_PLAN says the model reads "chat, job logs and tickets" (docs/BUILD_PLAN.md:42).
- Done when: the decision is written in loop/features.md under ai_layer.

## Step 2 — attribution lines (human approves wording)
- Files: `baton/extract.py`, `baton/llm.py`, `baton/lane_a.py` (lane_a reuses extract's cache functions, baton/lane_a.py:18).
- Prompt for the coding agent:
  > Add one line under the existing agent-memory-bench credit in baton/extract.py (lines 1-3) and baton/llm.py (lines 1-4): "# Copyright (c) 2026 Liz Zhang. MIT License, see third_party/amb/LICENSE. Adapted at commit b8ccc40." Do not change any code. Run python3 loop/bin/run_checks.py: the score must be unchanged.
- Done when: `grep -n "Liz Zhang" baton/*.py` shows the copyright line in both files and the score is unchanged.

## Step 3 — if (a) or (b) changed the prompt: v2
- Prediction: "score unchanged; the seed-7 dev cache still replays offline". Lookup without `--model` takes the newest entry for the world, whatever its version (baton/extract.py:96-105).
- Prompt:
  > In baton/extract.py apply the human's decision from loop/features.md (ai_layer): <paste the decision>. Bump PROMPT_VERSION to "v2". Do not touch the committed cache files. Run python3 loop/bin/run_checks.py.

## Step 4 — teammate: GPT run for seed 7
- Send the block in 2_CONTRACT §6 with `for s in 7`.
- After `git pull` here, run: `python3 loop/bin/run_checks.py`.
- Done when: `ls fixtures/extract_cache fixtures/lane_a_cache` shows a new `…-gpt-…` file in each, with prefix `05b61826bd27f746` (extract) and `3f598e4eb3fdff1c` (lane A). These are seed 7's input-sha prefixes as of about 12:45 IST (current cache file names). All locked checks must still pass. **Watch** `test_committed_seed7_cache_replays_offline_and_feeds_the_rehearsal` (test_ai_layer.py:55-65) and `test_wiring_demo_runs_end_to_end_offline` (test_rehearsal_core.py:206-216): both now replay the newest entry, the GPT one, and both need G > R. If they fail, the GPT beliefs do not reach the ghost duties. The usual cause is invented duty ids (X-2). Fix the prompt (new version) and re-run. Do not hand-edit the cache.

## Step 5 — teammate: sealed seeds (only after M7's predictions commit)
- The same block with the 30 seeds from `eval/seeds.json`. Done when 60 new files are pushed (30 extract + 30 lane_a).

## Step 6 — go and see (habit H1, loop/program.md:57-59)
- Run the 4_ACCEPTANCE commands. Then run `python -m baton demo --seed 7 --port 6399 --offline` and confirm `lanes.G.failures > lanes.R.failures` (baton/demo.py; test_rehearsal_core.py:214).
