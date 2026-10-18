# M05 · extract (+ lane A) — contract

Legend: **FIXED** = in a locked check or current code (cited; lines checked at about 12:45 IST, re-open before relying on them). **PROPOSED** = not in code; the decider is named. This module adds no Cypher: beliefs reach FalkorDB only through the existing gate (baton/rehearse.py:26-54).

## 1. CLI (FIXED)
| Command | Flags | Source |
|---|---|---|
| `python -m baton extract` | `--world` (required), `--out` (required), `--model`, `--offline`, `--cache-dir` (default `fixtures/extract_cache`) | baton/__main__.py:48-53; test_ai_layer.py:16, 35, 49-50, 58 |
| `python -m baton lane-a` | `--world`, `--leaver`, `--out` (all required), `--model`, `--offline`, `--cache-dir` (default `fixtures/lane_a_cache`) | baton/__main__.py:55-61; test_ai_layer.py:71 |
| Default model when none is given and a live call is needed: env `BATON_MODEL`, else `claude-haiku-4-5` | | baton/extract.py:120-121 |
| `--model fake`: deterministic scripted stand-in, never a model | | baton/llm.py:16-17, 117-168 |

### Exit codes and messages (FIXED)
| Code | When | Message | Source |
|---|---|---|---|
| 0 | ok; stdout = `{out, model, prompt_version, cached, cache_file, beliefs, usage}` (extract) or `{..., failures, owners}` (lane-a) | | extract.py:213-214; lane_a.py:101-103 |
| 4 | `--offline` and no cache entry for this exact input (and model, if given); `--out` not written | extract: "no cached extraction for this world (model …)"; lane-a: "no cached AI-alone answer for this world and leaver …" | extract.py:196-198; lane_a.py:82-84; __main__.py:121-123; test_ai_layer.py:41-43, 50-52 |
| 5 | real model, but no key in the environment or the SDK is not installed | "model X needs OPENAI_API_KEY in the environment …" / "the openai package is not installed" | llm.py:55-63, 80-83; __main__.py:124-126 |

## 2. Belief output (FIXED)
- A list written with `json.dumps(obj, indent=1, sort_keys=True)`, no trailing newline, built from the cache entry on both the first run and replays. That is why replay is byte-identical (extract.py:114-117, 212; test_ai_layer.py:36).
- Keys exactly `id, person, duty, duty_name, kind, claim, events, sources` (extract.py:31). `_normalise` sets `id = b-NN` in model order and coerces types (extract.py:177-187). It does **not** drop beliefs with unknown persons or sources; the gate refuses those (rehearse.py:36-44, 78-83).
- `events`: `[{at: int epoch ms, label}]` (extract.py:40-42, 182).

## 3. Model call (FIXED, baton/llm.py:74-109) and what it adapts from amb
| Baton | Adapted from | Change |
|---|---|---|
| `with_rate_limit_retry` (llm.py:41-52) | amb/llm.py:25-36 | identical logic |
| `provider` (llm.py:35-38) | amb/llm.py:39-40 | adds `fake` |
| `PRICES` subset (llm.py:19-27) | amb/llm.py:5-21 | 6 rows copied, the "long" tiers dropped. The values match amb for these 6 rows (writer compared them by eye) |
| `_usage` (llm.py:66-71) | amb/llm.py:47-62, 94-101 | simpler: input/output/cache_read only; `usd: None` for unknown models instead of KeyError (amb/llm.py:57) |
| OpenAI call (llm.py:84-91): `responses.create(model, input, text={"format": {"type": "json_schema", "name", "schema", "strict": True}}, store=False, max_output_tokens=16000)` | amb/extract.py:123-133 | no `reasoning=` argument; 16000 instead of 8000 tokens |
| Anthropic call (llm.py:97-105): `messages.create(..., output_config={"format": {"type": "json_schema", "schema"}})` | amb/extract.py:135-146 | no `effort` |
| SDK import inside the call (llm.py:80-83, 93-96) | amb/run.py:47-53 | missing SDK → `ModelUnavailable` (exit 5) |
| Cache: path keyed by a hash, replay if present, else call and store (extract.py:75-111, 191-212) | amb/extract.py:89-114 | one JSON file per call instead of a JSONL per dataset; key on the model's input, not a dataset name |
| `PROMPT_VERSION = "v1"` (extract.py:28; lane_a.py:20) | amb/extract.py:18 | — |
| Strict schema style: all properties required, `additionalProperties: false` (extract.py:33-47; lane_a.py:23-36) | amb/extract.py:31-65 | belief / lane-A shapes |
| Prompt rule list (extract.py:151-174) | amb/extract.py:68-86 | Baton wording |
| Scripted stand-in `fake_beliefs`, `fake_lane_a` (llm.py:117-168) | amb/fake.py:1-6, 103-110 (the idea) | Baton-specific scripted logic |

Unparseable model output raises `ValueError` (llm.py:106-109). amb instead records an empty result with an error string (amb/extract.py:148-151).

## 4. Cache (FIXED)
- **Key = what the model is shown, not the whole world.**
  - extract hashes `extract_input(w)`: clock; people id/name/team/role/left_at; duties; records except `CAN`; messages; joblogs; tickets. It is serialised as compact canonical JSON (extract.py:59-68).
  - lane A hashes `lane_a_input(w)`: the world without `CAN` records and without `people[].capacity`. It is serialised the way the generator writes world.json (lane_a.py:39-46).
  - So capability data added later by M6 does not invalidate the caches (extract.py:9-16; lane_a.py:5-9).
- File name `<input_sha16>-<model>-<key16>.json`, `key16 = sha256(input bytes + model + PROMPT_VERSION [+ leaver for lane A])[:16]` (extract.py:75-78; lane_a.py:78, 89).
- Entry (extract): `{model, prompt_version, input_sha, beliefs, usage, created}` (extract.py:209-211, 108-111). Entry (lane A): `{model, prompt_version, input_sha, leaver, answer, usage, created}` (lane_a.py:97-99).
- The committed seed-7 extract entry was re-keyed from the old whole-world sha to the input sha. Its `provenance` says "Verified that this input for seed 7 is identical to the world the entry was produced from. Contents unchanged" (fixtures/extract_cache/05b61826bd27f746-claude-haiku-via-harness-1c3281da8991580c.json). The seed-7 lane-A entry kept its file name, because `lane_a_input` of today's seed-7 world serialises to the old world bytes (both are prefixed `3f598e4eb3fdff1c`).
- Lookup (extract.py:81-105): with `--model`, the exact key; offline without exact match, the newest entry of that model for this input. Without `--model`, the newest entry for this input, any model. "Newest" = the largest wall-clock `created` string, then the file name (extract.py:104, 110). Every candidate must carry the full `input_sha` (extract.py:86, 92, 100). A live call with `--model` uses `exact_only` (extract.py:195; lane_a.py:80-81).

## 5. Lane A prompt and output (FIXED)
- Prompt: a JSON description, the question (leaver id, `leave_at`, window), answer instructions, then `json.dumps(w, sort_keys=True)` of `lane_a_input` (lane_a.py:53-71, 76). The same raw world minus capability data, and no graph.
- `leave_at` = `world["leave_at"]` if the leaver is the world's leaver, else `world["now"]` (lane_a.py:87).
- Output to `--out`: `{model, question, failures, owners}` (lane_a.py:95-96, 100). The locked check needs keys ⊇ {model, failures, owners}, failures ⊇ {duty, at} (test_ai_layer.py:73-75). `failures[].why` and `owners[].basis` are free text, so cited ids sit inside the text (lane_a.py:23-36).

## 6. The GPT key-holder's run (uses only existing flags; PROPOSED as the procedure, humans approve)
On the teammate's laptop, inside the cloned repo, at the commit the humans name. FalkorDB is not needed: `generate`, `extract` and `lane-a` never call `graph.connect` (falkordb is imported lazily inside `connect`, baton/graph.py:18-20). `MODEL` is the teammate's GPT model id; this pack does not know which models they can use (UNVERIFIED). It must start with `gpt-` to go to OpenAI (llm.py:38).
```
python3 -m venv .venv && . .venv/bin/activate && pip install openai
export OPENAI_API_KEY=...            # typed in the shell only; never written to a repo file
MODEL=gpt-...                        # teammate fills in
for s in 7; do                       # later, after eval/PREDICTIONS.md is committed: the sealed seeds
  python -m baton generate --seed $s --out /tmp/baton_w$s
  python -m baton extract --world /tmp/baton_w$s --out /tmp/baton_w$s/beliefs.json --model $MODEL
  L=$(python -c "import json;print(json.load(open('/tmp/baton_w$s/world.json'))['leaver'])")
  python -m baton lane-a --world /tmp/baton_w$s --leaver $L --out /tmp/baton_w$s/lane_a.json --model $MODEL
done
git add fixtures/extract_cache fixtures/lane_a_cache && git commit -m "LLM cache ($MODEL)" && git push
```
- amb pins `openai>=3.24.0` (amb pyproject.toml:14). Older versions are UNVERIFIED; prefer that pin.
- After the push, `extract --offline` without `--model` picks the newest entry, which will be the GPT one (§4). Demo and API switch automatically. The eval passes `--model $MODEL` explicitly.
- Cost: PRICES has rows for `gpt-5.4-mini`, `gpt-6-luna` and `gpt-6.1-sol` (llm.py:24-26). Any other model records `usd: null`.

## 7. Attribution (current headers, a URL check, and a PROPOSED fix)
- Current headers: baton/extract.py:1-3 and baton/llm.py:1-4 credit "agent-memory-bench by Liz Zhang (MIT), https://github.com/zhang-liz/agent-memory-bench". That URL matches the clone's `origin` (`url = https://github.com/zhang-liz/agent-memory-bench.git` in its `.git/config`).
- third_party/amb/world.py:1 now names the same zhang-liz URL. An earlier version said FalkorDB/agent-memory-bench; it was corrected while this pack was being written.
- PROPOSED (before freeze): the MIT terms require "the above copyright notice and this permission notice" in substantial portions (third_party/amb/LICENSE:5-13). Add one line to both headers: `# Copyright (c) 2026 Liz Zhang. MIT License, see third_party/amb/LICENSE. Adapted at commit b8ccc40.` This follows third_party/amb/world.py:2. Optionally list the exact amb lines from the §3 table.
