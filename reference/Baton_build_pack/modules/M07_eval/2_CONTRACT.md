# M07 · eval — contract

Legend: **PENDING** = in the drafted, not yet locked `checks/pending/eval/test_eval.py` (cited). **FIXED** = existing code. **PROPOSED** = neither; the humans decide before the predictions commit, because these definitions are part of what gets pre-registered.

## 1. CLI
| Item | Status | Source |
|---|---|---|
| `python -m eval.run --seeds A-B --scales 1,4 --lanes W,R,G --port P --out DIR`, run from the repo root; exit 0 | PENDING | test_eval.py:53-56 |
| So `eval/__init__.py` and `eval/run.py` must exist (package import from `cwd=ROOT`) | PENDING (follows) | test_eval.py:53-55 |
| Extra lanes `G_ext` (extracted beliefs) and `A` (AI alone), accepted in `--lanes` | PROPOSED | |
| `--model MODEL` passed to `extract`/`lane-a --offline --model` for G_ext and A | PROPOSED | M05 2_CONTRACT §4 (lookup) |
| `generate --seed N --scale K --out DIR`; scale 1 is byte-identical to no flag; scale 8 gives ≥5× people, events and messages and keeps W<R<G | PENDING (generator) | test_eval.py:13-34 |
| Exit 2 "predictions not committed" when §6 fails (real runs only; a `--dev` flag skips it and stamps the report) | PROPOSED | |

## 2. Output `DIR/results.json` (PENDING shape + PROPOSED extras)
```
{"runs": [ {"seed": int, "scale": int, "lane": "W"|"R"|"G"|..., "exact": bool, "precision": float, "recall": float,
            "model_tokens_per_question": int|null, ...PROPOSED extras...}, ... ],
 "summary": {"W": {"recall_mean": float, "recall_ci95": [lo, hi], ...}, "R": {...}, "G": {...}}}
```
- One run per seed × scale × lane: `len(runs) == seeds × scales × lanes` (test_eval.py:58). Required keys (test_eval.py:59-60). Every `G` run must have `exact == true` (test_eval.py:61-62). `summary[lane]` has `recall_mean` and `recall_ci95` (test_eval.py:63-65). `DIR/report.md` must exist (test_eval.py:66).
- PROPOSED extras per run: `n_found`, `n_truth`, `duty_recall` (list of 0/1 per truth duty), `invented`, `false_claims_adopted` (list of 0/1 per noise belief, or null), `beliefs` ("none" | "key" | "extracted"), `status` ("ok" | "not run: <reason>").

## 3. Lanes and what each one uses (PROPOSED unless cited)
| Lane | Run | Beliefs |
|---|---|---|
| W, R | `python -m baton rehearse --world D --beliefs K --leaver L --lane W --confirm all --port P` (or `--lane R`) (flags: baton/__main__.py:19-25) | key beliefs file K (W/R ignore beliefs: oracle.py:11-21) |
| G | same with `--lane G` | **key** `true_beliefs + noise_beliefs` (as the locked checks do: test_rehearsal_core.py:21-24). This makes "every G run exact" (test_eval.py:61-62) an engine check that needs no model cache. Seeds 1000–1005 have no cache. |
| G_ext | `extract --world D --out B --offline --model M`, then rehearse `--lane G --beliefs B` | extracted (M05) |
| A | `lane-a --world D --leaver L --out A.json --offline --model M` (baton/__main__.py:55-61) | none; no graph |
- `L` = `world["leaver"]` (baton/generate.py:469).
- Worlds come from `python -m baton generate` into a temp dir. The extract and lane-A cache keys are hashes of what the model reads (baton/extract.py:59-78; baton/lane_a.py:39-46). A generator change to those parts after the GPT run makes G_ext and A "not run".
- The FalkorDB server: the check passes `--port` (test_eval.py:54). For the real run, start a fresh server like conftest.py does (checks/locked/rehearsal_core/conftest.py:18-30). A long-lived server keeps old graphs, which are never reloaded (baton/load.py:3, 101-106), and one locked check edits `halden_303` (test_rehearsal_core.py:241).

## 4. Scoring (PROPOSED definitions; the check only fixes the key names)
Reference: `sys.path.insert(0, str(ROOT/"checks/locked/rehearsal_core")); import oracle` (an import, not a copy).
- `exact` = the lane's `{(duty, at)}` == `oracle.expected_failures(w, beliefs_used, lane_for_ref)` (oracle.py:80-97). `lane_for_ref` is W, R or G; G_ext is compared with lane G and the extracted beliefs. Not defined for A (no engine): use `null`. NOTE: the check needs `exact` as a key on every run (test_eval.py:60), and requires it true only for G (test_eval.py:62).
- Truth `T` = `oracle.expected_failures(w, key["true_beliefs"], "G")`. Noise never promotes (test_rehearsal_core.py:57), so adding it changes nothing.
- `precision` = |found ∩ T| / |found| (1.0 if nothing is found and T is empty; 0.0 if nothing is found and T is not empty). `recall` = |found ∩ T| / |T|, at `(duty, at)` pair level for W, R, G. For G_ext and A, the ids and times are free, so use the duty level after alignment (§5), and say so in the report.
- `model_tokens_per_question`: W, R, G = 0, because no model is called at question time (extraction is a one-time cost, reported separately as M05's `usage`). A = input + output tokens from the lane-A cache `usage` (baton/llm.py:66-71), or `null` when usage is null (the seed-7 dev caches have `usage: null`). G_ext = 0 per question, plus the extraction tokens reported once per world.
- `false_claims_adopted` (per noise belief n): A → 1 if an `owners` entry aligns to n.duty with `person == n.person`, or n.person is the leaver and a `failures` entry aligns to n.duty. G_ext → 1 if an extracted belief with person n.person aligns to n.duty and is not in rehearse's `unpromoted` (baton/rehearse.py:94). G (key) → 1 if n.id is not in `unpromoted`. W/R → `null` (they read no chat; report "n/a", not 0).

## 5. Duty alignment (PROPOSED; needed for G_ext and A)
`align(duty, sources, person)`:
1. If `duty` is a world duty id or a key belief duty id → return it.
2. Else, among key beliefs (true + noise) with that person, take those sharing at least one source id. A unique largest overlap → return its duty.
3. Else → `None` (counts as invented).

Sources: G_ext → the extracted belief's `sources` list (baton/extract.py:31). A → lane A gives free text only (`failures[].why`, `owners[].basis`; baton/lane_a.py:23-36), so take every id matching `\b(?:msg|log|tkt|rec)-\d{4}\b` (ids are 4-digit zero-padded: baton/generate.py:444). Person: the leaver for A failures, the entry's person for A owners.

## 6. Pre-registration (PENDING rule + PROPOSED enforcement)
- PENDING: `eval/PREDICTIONS.md` must be committed. It must contain "%" or "0.". If `eval/results` has ever been committed, the first commit touching it must be a strict descendant of the first commit of PREDICTIONS.md (test_eval.py:69-81).
- PROPOSED content of PREDICTIONS.md (written by the humans; this pack gives no numbers): seed rule and the sealed seed list; scales; lanes; `MODEL` and M05 `PROMPT_VERSION`; §3–§5 definitions (or the commit hash of this file); for each lane × metric, a value or range with a probability; and the fallback "if no sealed caches by 15:30, G_ext and A are not run".
- PROPOSED seal: `eval/seeds.json` with sha256 of each sealed `world.json` and `answer_key.json`, plus sha256 of `baton/generate.py`, committed with PREDICTIONS.md. `eval.run` re-generates and refuses on mismatch ("generator changed after sealing").
- PROPOSED order check: record the predictions commit, HEAD, and the commit that added the sealed caches in report.md, so `git merge-base --is-ancestor <pred> <cache>` is checkable. Cache entries carry a wall-clock `created` (baton/extract.py:110), which proves nothing on its own.

## 7. Seeds
- **Already seen (exclude from the sealed set):** 7, 101, 202, 303 (test_rehearsal_core.py:9); 11, 12 (test_rehearsal_core.py:30; test_eval.py:20); 21 (test_eval.py:39); 1000–1005 (test_eval.py:53); 7, 202 (checks/locked/ask/test_ask.py:8); 101, 202, 303 (checks/locked/ai_layer/test_ai_layer.py:14, 30, 47); **1–59 and 9001–9030** (generated by this doc writer at doc time; for 9001–9030 it also computed reference failure counts). Add any seed seen in `fixtures/`, `loop/rounds/` or other module docs.
- Choice: the humans write a start S in PREDICTIONS.md. Sealed = the first 30 non-excluded seeds from S. Scales for the sealed run: PROPOSED `1` only (the caches are per world; scale > 1 worlds would need their own GPT run). Scale > 1 is measured for W/R/G only.

## 8. Confidence intervals — adapted from amb/analyze.py
- Cluster = world. amb: "resampling whole worlds keeps correlated questions together" (amb/analyze.py:3-4). Group per world as `per_world` does (amb/analyze.py:122-126). A world = (seed, scale).
- `boot_ci(groups, n=2000)`: drop empty groups; return the mean of all values; one group → NaN interval; else resample `len(groups)` groups with replacement n times, take each concatenation's mean, and report the 2.5th and 97.5th percentiles (amb/analyze.py:65-78).
- Changes: `random.Random(0)` instead of `np.random.default_rng(0)` (amb/analyze.py:25), `rng.randrange(len(groups))` picks, and a linear-interpolation percentile at position `p/100·(k−1)`, which is numpy's default method. There is no numpy in the scratch venv (checked at doc time), and the project is stdlib + falkordb. Bit-exact equality with amb's numbers is not expected.
- `recall_ci95` = `[lo, hi]` of `boot_ci` over per-world recall lists (each world's group = 0/1 per truth item). PROPOSED: JSON cannot hold NaN in strict parsers, so write `null` for a NaN bound.
- Ours, not amb's: a paired G_ext − A difference CI (resample worlds, mean of per-world differences). Label it "ours".
- File header for `eval/stats.py`: `# Adapted from https://github.com/zhang-liz/agent-memory-bench (commit b8ccc40), amb/analyze.py lines 25, 65-78, 122-126. Copyright (c) 2026 Liz Zhang. MIT License, see third_party/amb/LICENSE.` (pattern: third_party/amb/world.py:1-2).

## 9. report.md
A table per lane (and per scale): runs, exact k/n, precision, recall mean [95% CI], duty recall [CI], invented, false claims adopted [CI] or n/a, and model tokens per question. Then "Where we lose": every metric where A or R matches or beats G/G_ext, in words. Then "Not run", then the three commit hashes. None of the banned words (docs/modules/00_GROUND_TRUTH.md:51).
