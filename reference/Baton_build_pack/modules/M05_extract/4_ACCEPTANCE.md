# M05 · extract (+ lane A) — acceptance

## Locked checks (checks/locked/ai_layer/test_ai_layer.py) — 7/7 passing when the writer ran them
| Test function | In this module's scope | What it proves |
|---|---|---|
| `test_fake_model_extraction_is_deterministic_and_well_formed` | yes | two fake runs give identical bytes; keys exactly KEYS; persons real; sources exist (test_ai_layer.py:13-26) |
| `test_offline_replays_the_cache_byte_for_byte_and_never_guesses` | yes | replay is byte-identical; a changed world misses → exit 4, "no cached extraction", no file (test_ai_layer.py:29-43) |
| `test_real_model_offline_without_cache_fails_clearly` | yes | `--model gpt-5.4-mini --offline` with an empty cache → exit 4 (test_ai_layer.py:46-52) |
| `test_committed_seed7_cache_replays_offline_and_feeds_the_rehearsal` | yes | default offline replay for seed 7; G > R with those beliefs (test_ai_layer.py:55-65) |
| `test_ai_alone_lane_replays_from_cache_with_its_schema` | yes | lane-a replay has `model`, `failures` (`duty`, `at`) and `owners` (test_ai_layer.py:68-75) |
| `test_amb_import_is_deterministic_loadable_and_credited` | no (amb-import, not specified here) | (test_ai_layer.py:78-90) |
| `test_product_never_shows_the_truth_to_the_model` | shared | no `amb_truth` in baton/*.py except amb_import.py (test_ai_layer.py:93-97) |

Also binding: `test_product_never_reads_the_answer_key_or_oracle` (test_rehearsal_core.py:220-232) and `test_wiring_demo_runs_end_to_end_offline` (test_rehearsal_core.py:206-216).

## Go and see
```
PY=/tmp/claude-0/-home-claude/9e986261-4c5d-5119-82fd-cce4a3dc1af5/scratchpad/venv/bin/python
W=/tmp/x7; $PY -m baton generate --seed 7 --out $W
env -u OPENAI_API_KEY -u ANTHROPIC_API_KEY $PY -m baton extract --world $W --out $W/b.json --offline
env -u OPENAI_API_KEY -u ANTHROPIC_API_KEY $PY -m baton lane-a --world $W --leaver hana.sharma --out $W/a.json --offline
env -u OPENAI_API_KEY -u ANTHROPIC_API_KEY $PY -m baton extract --world $W --out $W/c.json --model gpt-5.4-mini; echo "exit=$?"
$PY -m baton rehearse --world $W --beliefs $W/b.json --leaver hana.sharma --lane G --confirm none --port 6399 | $PY -c "import json,sys; o=json.load(sys.stdin); print(len(o['failures']), [u['reason'] for u in o['unpromoted']])"
```
Expected:
- extract prints `"cached": true` and `"model": "claude-haiku-via-harness"` (until a GPT entry is newer).
- lane-a prints `"cached": true`.
- The third command prints the "needs OPENAI_API_KEY" message and `exit=5` (llm.py:55-63).
- rehearse prints a failure count and refusal reasons such as "only 1 source cited; needs at least 2" (wording at baton/rehearse.py:78-83). Doc-time scratch run with these dev beliefs: the reference gives 37 G failures for seed 7. That is not a check; re-measure.

## Failure modes and fallbacks
| Failure | Fallback |
|---|---|
| **Observed at about 12:31 IST (since fixed by keying on the model's input, see below):** `baton/generate.py` changed (records gained capacity data: seed 7 went from 22 to 44 records). Seed 7's `world.json` sha is now `c11219d2…`, not `3f598e4e…`, so both committed seed-7 caches miss. `extract --offline` exits 4 with "no cached extraction for this world (model any)", and `lane-a --offline` exits 4 too (doc-writer run). Old ids keep their meaning: the 17 messages, 23 joblogs, 3 tickets and the first 22 records have the same content, so the old citations still resolve. | Re-run the extraction on the new world (teammate GPT run, or a new Claude dev run labelled as such). Or re-key the old entries to the new world sha, with `provenance` saying "extracted from the pre-capacity world; ids verified unchanged". The humans decide. Re-run `python3 loop/bin/run_checks.py` afterwards: `test_committed_seed7_cache_replays_offline_and_feeds_the_rehearsal` and `test_wiring_demo_runs_end_to_end_offline` depend on it. **Fix applied at about 12:40 IST:** cache keys now cover only what the model reads (extract.py:59-68; lane_a.py:39-46), and the extract entry was re-keyed with a provenance note. A generator change to anything the model reads still invalidates every cache, so freeze the generator before the GPT run. |
| No GPT key or teammate by 15:00 | Ship the labelled Claude dev cache (docs/BUILD_PLAN.md:69; loop/features.md:54). README and video say "Claude dev cache, not GPT". |
| After the GPT push, G ≤ R for seed 7 (two locked checks fail) | The GPT beliefs miss the ghost duty ids. Fix the prompt with a new `PROMPT_VERSION` and re-run on the laptop. Until then, revert the GPT cache commit so the dev cache is newest again. |
| GPT run returns 400 (schema or argument) | Read the error. A likely cause is a strict-schema rule. Adjust `SCHEMA` (extract.py:33-47), bump the version, re-run. UNVERIFIED which rule. |
| A false claim is promoted (the model over-cites) | Report it in M7 as "false claims adopted (G)". Never filter in Python. |

## Anti-hallucination list
| # | Wrong assumption | Correct fact | Source |
|---|---|---|---|
| X-1 | "Show the model the answer key to help it." | Never; only world.json. "answer_key" may appear only in generate.py. | test_rehearsal_core.py:223-227 |
| X-2 | "Any duty id the model invents is fine." | Ghost-job events hang on the world duty id (`d-job-…`). A new id MERGEs a new Duty with no events, so the ghost failure is lost. The prompt already says to reuse DUTIES ids. | generate.py:301-303; rehearse.py:46-54; extract.py:157-158 |
| X-3 | "Filter beliefs with bad sources in Python." | `_normalise` keeps them; the gate refuses them with a reason. | extract.py:177-187; rehearse.py:36-44, 78-83 |
| X-4 | "The cache key is seed + model." | It is sha256 of the model's input (extract: `extract_input`, canonical compact JSON; lane A: `lane_a_input`, generator-style JSON) + model + version (+ leaver). A change to anything the model reads misses. | extract.py:59-78; lane_a.py:39-46, 78 |
| X-5 | "`--offline` without `--model` replays the model I meant." | It replays the newest entry for that input, any model, by wall-clock `created`. Pass `--model` in the eval. | extract.py:81-105, 110 |
| X-6 | "Records in the prompt are harmless." | A cited record counts as a second source kind, so an unrelated `rec-` id can promote a one-line claim. Decision pending (3_STEPS Step 1b). | extract.py:144, 163, 170; oracle.py:29-30 |
| X-7 | "17:00 UTC is a neutral default." | It is the generator's hidden due time, so disclose it or neutralise it. | extract.py:161-162; generate.py:341 |
| X-8 | "The committed seed-7 caches are GPT outputs." | They are Claude Haiku subagent outputs through Claude Code, `usage: null`, labelled in `provenance`. | fixtures/extract_cache/05b61826bd27f746-…json; fixtures/lane_a_cache/3f598e4eb3fdff1c-…json |
| X-9 | "amb's prices cover our model." | Only 6 rows were copied; unknown models give `usd: null`. Do not invent a price. | llm.py:19-27, 66-71 |
| X-10 | "`import openai` at module top." | The SDK is imported inside the call; offline needs no SDK. The scratch venv has neither openai nor numpy (pip list at doc time). | llm.py:80-83 |
| X-11 | "Fake output is a result." | Fake is "a few lines of deterministic Python" whose output "must never be reported as a result". | llm.py:11-12; amb/fake.py:4-5 |
| X-12 | "Put the key in a repo .env." | The key stays in the teammate's shell; no secrets in logs or commits. | loop/program.md:40 |
| X-13 | "Lane A may see beliefs or the graph." | Lane A = same model, raw world JSON (minus capability data), no graph. | lane_a.py:1-2, 39-42, 60-71; docs/BUILD_PLAN.md:43 |
| X-14 | "Lane A cites sources in a list." | Its cited ids are inside free-text `why` / `basis`. | lane_a.py:23-36 |
| X-15 | "The API still uses fixtures/beliefs_seed<N>.json." | That file no longer exists. The API falls back to `extract` (replays if cached, else needs a key; exit 5 → HTTP 500). | server/app.py:31-36, 22; __main__.py:124-126 |
