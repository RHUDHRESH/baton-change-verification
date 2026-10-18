# M05 · extract (+ lane A, "AI alone") — spec

Path convention: repo paths are relative to `/home/claude/baton/`. `amb/...` means `/tmp/claude-0/-home-claude/9e986261-4c5d-5119-82fd-cce4a3dc1af5/scratchpad/falkor/repos/agent-memory-bench/amb/...` at commit `b8ccc40348a49623949ce9754c96771ff1f2e7b0`. The writer read that commit from the clone's `.git/refs/heads/main`. The vendored `third_party/amb/world.py:1` names the same commit, and the writer checked with `cmp` that its body and `third_party/amb/LICENSE` are byte-identical to the clone.

## Status at writing (about 12:30 IST)
- `baton/extract.py`, `baton/lane_a.py` and `baton/llm.py` exist, wired at baton/__main__.py:48-61, 104-109.
- The `ai_layer` checks are **locked** (checks/locked/ai_layer/test_ai_layer.py; MANIFEST lists `ai_layer/test_ai_layer.py`). When the writer ran `pytest checks/locked/ai_layer`, 7 of 7 passed.
- Committed caches for seed 7: `fixtures/extract_cache/05b61826bd27f746-claude-haiku-via-harness-1c3281da8991580c.json` (re-keyed at about 12:40 IST, see 2_CONTRACT §4) and `fixtures/lane_a_cache/3f598e4eb3fdff1c-claude-haiku-via-harness-73ee275319743413.json`. Both have `model: "claude-haiku-via-harness"`, `prompt_version: "harness"`, `usage: null`, and a `provenance` field saying they were "Produced by a Claude Haiku subagent in Claude Code (the harness, not the API)". These are the labelled dev caches that BUILD_PLAN allows ("no key → dev cache from Claude, labelled as such", docs/BUILD_PLAN.md:69). **No GPT output is committed yet.**
- At about 12:31 IST a generator change (capability data) broke the whole-world cache keys. By about 12:40 the code had been changed to key on only what the model reads, and the seed-7 entries matched again (2_CONTRACT §4; 4_ACCEPTANCE, first failure mode).
- Remaining work: the teammate's GPT run (§6 of 2_CONTRACT), full MIT notices in the two adapted headers, and the honesty items in 4_ACCEPTANCE (X-6, X-7).

## What it is, in plain words
A model reads the company's chat, job logs and tickets and writes down "beliefs", for example "Hana reruns the warehouse job by hand" or "Hana promised Oaktree a CSV fix by 3 Nov". Each belief lists the message, log or ticket ids it came from. Baton does not trust them: the FalkorDB gate promotes a belief only if it cites at least 2 existing sources of at least 2 kinds (baton/rehearse.py:36-44). Every model answer is saved in a cache file in the repo, so judges replay it with no API key.

**Lane A ("AI alone")** gives the same model the same raw world and no graph. It answers "what breaks if X leaves, and who owns what?" directly (baton/lane_a.py:1-2, 53-71). We save that answer too, and M7 scores it. This is the "take the graph out" comparison.

The short version: "The AI reads the chat and takes notes with page numbers. The database only keeps notes that two different kinds of page back up. We also ask the AI to answer on its own, to show what goes wrong without the database."

## Why
- Track 3: "knowledge from docs, tickets and chats in one graph" and "tracing decisions back to their source" (docs/modules/00_GROUND_TRUTH.md:8).
- Track 1: "explainable results" (docs/modules/00_GROUND_TRUTH.md:9). Lane A is the evidence for Rule 2/3, "If the product still works once FalkorDB is taken out, the graph is decoration" (docs/modules/00_GROUND_TRUTH.md:11).
- The plan: "The LLM reads chat, job logs and tickets and proposes beliefs (adapted from amb). Offline replay from cache, so judges need no key." (docs/BUILD_PLAN.md:42).

## In scope
- `extract`, `lane-a`, the cache, the `fake` stand-in, and the GPT key-holder's run.
- Credit: agent-memory-bench is MIT, "Copyright (c) 2026 Liz Zhang" (third_party/amb/LICENSE:1-3; docs/modules/00_GROUND_TRUTH.md:41).

## Not in scope
- `amb-import` (checks/locked/ai_layer/test_ai_layer.py:78-90; baton/amb_import.py). It is part of the ai_layer feature but not specified in this pack.
- Scoring quality (M7). Deciding promotion in Python: the gate in FalkorDB decides (baton/rehearse.py:86-94).
- A model router for `ask` (loop/features.md:52).

## Inputs
- `world.json` bytes (baton/extract.py:55-68). Never `answer_key.json`: product code other than generate.py may not contain that string (checks/locked/rehearsal_core/test_rehearsal_core.py:223-227).

## Outputs
- `extract --out`: a JSON list of beliefs with keys exactly `{id, person, duty, duty_name, kind, claim, events, sources}` (baton/extract.py:31; test_ai_layer.py:10, 24).
- `lane-a --out`: `{model, question, failures: [{duty, at, why}], owners: [{duty, person, basis}]}` (baton/lane_a.py:4, 95-96).
- A cache file per call (2_CONTRACT §4).

## Dependencies
- M1 generator: the cache key is the bytes of what the model reads (baton/extract.py:59-68; baton/lane_a.py:39-46). Any generator change to people, duties, non-CAN records, messages, joblogs or tickets invalidates every cache.
- M2 gate (baton/rehearse.py:86-94). Demo replays the extraction for its world (baton/demo.py:19-33). The API falls back to `extract` (server/app.py:31-36).

## Owner, time, kill
- Owner: the loop + the teammate with the GPT key (docs/BUILD_PLAN.md:69).
- Time: 13:30–15:00 IST (docs/BUILD_PLAN.md:69). No new features after 15:30 (docs/BUILD_PLAN.md:72).
- Kill: "8 rounds; if not green by 15:00, ship with the seed-7 cache only" (loop/features.md:54). Fallback: the labelled Claude dev cache (docs/BUILD_PLAN.md:69).
