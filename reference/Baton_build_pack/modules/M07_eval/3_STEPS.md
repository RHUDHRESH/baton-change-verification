# M07 · eval — build steps

`PY=/tmp/claude-0/-home-claude/9e986261-4c5d-5119-82fd-cce4a3dc1af5/scratchpad/venv/bin/python`. Run from `/home/claude/baton`.

## Loop rule (Karpathy loop): checks first, human approves, lock, then build
- The drafted checks are `checks/pending/eval/test_eval.py`. A human reads them (list in 4_ACCEPTANCE), approves, and locks: `python3 loop/bin/lock_checks.py eval --approved-by "<name>: '<words>' (<date time>)"` (loop/bin/lock_checks.py:4).
- Never edit `checks/locked/**` or `loop/bin/**` (loop/program.md:16-19).
- `eval` is in the loop's `mutable_paths` (loop/config.json, added at about 12:45 IST; loop/program.md:16-19 lists it too), so the loop may build it. The `--scale` generator change is in `baton/`.
- The pre-registration commit is the second lock: nothing that can change a result may change after it.

## Step 0 — human: lock + decisions
- Decide the PROPOSED items in 2_CONTRACT (§3 lane definitions, §4 scoring, §5 alignment, §7 seeds and scales).
- Remove any drafted check you do not want before locking.
- Done when: `checks/locked/eval/test_eval.py` exists, and `$PY -m pytest checks/locked/eval -q -p no:cacheprovider` shows 6 tests, 7 runs (one is parametrised over seeds 11 and 12), all failing except possibly `test_predictions_were_committed_before_any_results`, which fails until PREDICTIONS.md is committed.

## Step 1 — generator `--scale` (loop; M1 owner reviews)
- Prediction: "`test_scale_1_is_byte_identical_to_the_default_generator`, `test_scale_grows_the_company_and_keeps_every_planted_shape[11,12]` and `test_baton_is_exact_on_a_large_company_and_fast` flip."
- Done when: those 4 runs pass and all 32 rehearsal_core runs still pass. Scale 1 must not change a byte. Changes to what the model reads would make every committed cache miss (baton/extract.py:59-78).
- Prompt:
  > Add `--scale K` (int, default 1) to `python -m baton generate` (baton/__main__.py:11-13; baton/generate.py:481-495). With K == 1 the output must be byte-identical to today: run the exact same code path and draw nothing extra from the RNG. With K > 1, add more people, duties, events and messages (≥5× people, events and messages at K=8) using the same planting helpers, so every planted shape is kept and the reference still gives W < R < G with all true beliefs promoted and no noise promoted (checks/pending/eval/test_eval.py:20-34). Generator only; never mention "oracle" in baton/.

## Step 2 — eval/stats.py + eval/align.py (no check needed beyond Step 4; unit-test locally)
- Prompt:
  > Create eval/__init__.py (empty), eval/stats.py and eval/align.py at /home/claude/baton/eval/. stats.py: boot_ci(groups, n=2000) adapted from agent-memory-bench amb/analyze.py:65-78 (clone: /tmp/claude-0/-home-claude/9e986261-4c5d-5119-82fd-cce4a3dc1af5/scratchpad/falkor/repos/agent-memory-bench), with random.Random(0) instead of numpy (amb/analyze.py:25) and a linear-interpolation percentile at p/100*(k-1); paired_diff_ci (ours). Use the header in docs/modules/M07_eval/2_CONTRACT.md §8. align.py: implement §5 exactly. Standard library only.
- Done when: `$PY -c "import sys; sys.path.insert(0,'.'); from eval.stats import boot_ci, percentile; print(boot_ci([[1.0],[1.0]]), percentile([1,2,3,4],50))"` prints `(1.0, 1.0, 1.0) 2.5`.

## Step 3 — eval/run.py
- Prediction: "`test_eval_harness_reports_exactness_with_confidence_intervals` flips."
- Done when: `$PY -m eval.run --seeds 1000-1005 --scales 1,4 --lanes W,R,G --port <p> --out /tmp/evtest` exits 0, `results.json` has 36 runs, and every G run has `exact: true`.
- Prompt:
  > Create eval/run.py per docs/modules/M07_eval/2_CONTRACT.md §1–§4 and §8–§9. Parse --seeds (ranges and commas), --scales, --lanes, --port, --out, --model and --dev. For each seed × scale: `python -m baton generate --seed s --scale k --out <tmp>` as a subprocess. Write the key beliefs (true + noise) to a file. For each lane, run the CLI as a subprocess (§3), score with the locked reference (`sys.path.insert(0, ROOT/"checks/locked/rehearsal_core"); import oracle`) and eval/align.py, and append a run dict with at least seed, scale, lane, exact, precision, recall and model_tokens_per_question. Missing caches for G_ext/A → a run with status "not run: no cache" (still counted in runs). Write results.json (summary per lane: recall_mean, recall_ci95 via eval/stats.boot_ci, cluster = (seed, scale)) and report.md. Unless --dev, refuse with exit 2 if eval/PREDICTIONS.md is missing, uncommitted or modified (`git status --porcelain -- eval/PREDICTIONS.md`), and print the predictions commit hash into report.md. Never copy reference code; import it.

## Step 4 — humans: predictions + seal (the second lock)
- Write `eval/PREDICTIONS.md` (2_CONTRACT §6). Optionally write `eval/seeds.json` (seal).
- Commands: `git add eval/PREDICTIONS.md eval/seeds.json && git commit -m "eval: predictions (before any results)" && git push`
- Done when: `test_predictions_were_committed_before_any_results` passes.

## Step 5 — teammate: sealed caches
- The M05 2_CONTRACT §6 block with the sealed seeds. After `git pull`, `fixtures/extract_cache` and `fixtures/lane_a_cache` each have 30 more files whose names contain the model id (name format: baton/extract.py:75-78).

## Step 6 — the real run, once
- Commands: start a fresh FalkorDB (conftest-style, checks/locked/rehearsal_core/conftest.py:18-30), then `$PY -m eval.run --seeds <sealed list> --scales 1 --lanes W,R,G,G_ext,A --model <MODEL> --port <p> --out eval/results/sealed`, plus a W/R/G-only scale run (e.g. `--scales 4,8 --out eval/results/scale`).
- Then `git add eval/results && git commit -m "eval: results"`. This commit must be a descendant of the predictions commit (test_eval.py:78-81).
- Lanes that fail on some seeds: report them, do not re-run with changes. "Fewer seeds; still report" (docs/BUILD_PLAN.md:71).
