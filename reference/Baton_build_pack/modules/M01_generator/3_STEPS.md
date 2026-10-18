# M01 · Generator · STEPS

M01 is **done**. These steps are for checking it, explaining it, and changing it safely if a human asks for that.

## Loop rule (applies to every step)
Checks come first. A human approves them, they are locked, and only then does building start. Never edit `checks/locked/**`, `loop/bin/**` or `.claude/settings.json` (loop/program.md:16-21, .claude/settings.json "deny"). A builder may change only `baton`, `fixtures`, `Makefile` and `README.md` (loop/config.json "mutable_paths"). One round is one hypothesis and one commit, with the prediction written before any code (loop/program.md:23-25). New checks go to `checks/pending/<feature>/` and are locked with `python3 loop/bin/lock_checks.py <feature> --approved-by "<who and what they said>"` (loop/bin/lock_checks.py:4).

Set these once per shell:
```
S=/tmp/claude-0/-home-claude/9e986261-4c5d-5119-82fd-cce4a3dc1af5/scratchpad
PY=$S/venv/bin/python
cd /home/claude/baton
```

## Step 1: See the world with your own eyes
- Goal: both students can say what is in world.json without looking at code.
- Files touched: none (output goes to the scratchpad).
- Commands:
  ```
  $PY -m baton generate --seed 7 --out $S/w7
  $PY -c "import json;w=json.load(open('$S/w7/world.json'));print(w['leaver'],w['now'],w['leave_at']);[print(k,json.dumps(w[k][0])) for k in ('people','duties','records','events','messages','joblogs','tickets')]"
  ```
- Done when: the first command prints `"leaver": "hana.sharma"` and counts `people 9, duties 11, records 22, events 74` (observed 11:36 IST). The second prints one sample row of each list.
- Prompt for a coding agent:
  > Run `python -m baton generate --seed 7 --out <tmp>` with the project venv. Print one example row from each list in world.json. Do not read answer_key.json in any product code. Do not edit any file.

## Step 2: Re-run the generator's locked checks
- Goal: prove nothing has drifted.
- Files touched: none.
- Command (this only reads; it does not write the loop's score files):
  ```
  PYTHONDONTWRITEBYTECODE=1 $PY -m pytest checks/locked -q -p no:cacheprovider -k "generate or world_holds or strictly_more"
  ```
- Done when: 9 passed (1 determinism + 4 world-shape + 4 W<R<G; checks/locked/rehearsal_core/test_rehearsal_core.py:28, :39, :93).
- Prompt:
  > Run the pytest command above and report the pass count. If anything fails, do not edit checks. Report the failing test name and its assertion message.

## Step 3: Change the generator (only if a human asks)
- Goal: a change to the company story (for example more stale shifts, which round 1 suggested in loop/rounds/rehearsal_core-1.md) without breaking anything downstream.
- Files touched: `baton/generate.py`, and also `fixtures/beliefs_seed7.json`.
- Why both: ids are numbered after sorting (baton/generate.py:423-433). Adding one message renumbers every `msg-NNNN` after it. `fixtures/beliefs_seed7.json` cites ids such as `msg-0009`, `log-0002` and `tkt-0003`, and the demo reads that file (baton/demo.py:21). After a change, those citations may point at the wrong row or at nothing. H2 in loop/program.md:60-62 says to update every reader in the same round.
- Commands:
  1. Write the round file first: `loop/rounds/rehearsal_core-<n>.md` with Hypothesis, Predicted to flip and Mechanism (loop/program.md:23-25).
  2. Edit, then run the full score: `python3 loop/bin/run_checks.py` (loop/program.md:14).
  3. Check the fixture still lines up: `$PY -m baton demo --seed 7 --port <p> --offline` must still print `after_handover.failures 0` and G > R.
- Done when: the score has not dropped, test 15 (`test_wiring_demo_runs_end_to_end_offline`) still passes, and the round is logged.
- Kill: after 15:30 IST there are no new features (docs/BUILD_PLAN.md:72). After the 16:00 freeze, do not touch the generator at all (docs/BUILD_PLAN.md:73).
- Prompt:
  > You are a feature-builder in the Karpathy loop. Read loop/program.md, loop/features.md, .claude/skills/project-context/SKILL.md and loop/last_score.json. Write one hypothesis to loop/rounds/rehearsal_core-<n>.md BEFORE editing. Change only baton/generate.py (and fixtures/ if ids moved). Keep every choice driven by random.Random(seed) and BASE_NOW, never the clock. Keep the invariant: the leaver has no outgoing ESCALATES_TO. Never write "expected_failures", "answer_key", "true_beliefs" or "noise_beliefs" into world.json. Run python3 loop/bin/run_checks.py and report.

## Step 4: Be ready to explain it (rule 12)
- Goal: each student can answer, without notes: "Did you plant the failures?", "Why is the answer key separate?", "Why does the leaver never escalate to anyone?"
- Done when: each student answers all three using 2_CONTRACT.md §4 and §5. The planted list covers schedules only. The key is read only by the checks (checks/locked/rehearsal_core/test_rehearsal_core.py:220-227). The escalation invariant is in loop/rounds/rehearsal_core-1.md.
