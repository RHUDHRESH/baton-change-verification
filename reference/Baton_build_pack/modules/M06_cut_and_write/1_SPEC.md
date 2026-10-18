# M06 · The Accountability Cut and the real write — SPEC

Paths are relative to `/home/claude/baton/`. `verify/` = `/tmp/claude-0/-home-claude/9e986261-4c5d-5119-82fd-cce4a3dc1af5/scratchpad/verify/`.

Status at 12:15 IST, 18 Oct (git HEAD `85eeabd`):
- **Commit checks are drafted, not locked**: `checks/pending/commit_write/test_commit_write.py` (5 check functions, appeared ~11:55 IST).
- **Cut checks are locked** (commit `85eeabd`, "lock checks for cut (manifest v6)", ~12:00 IST): `checks/locked/cut/test_cut.py` (7 check functions) and the independent reference `checks/locked/cut/flow_oracle.py`. Byte-identical to the draft this doc was written from (same md5).
- **Cut charter** (loop/features.md, section `### cut`): entrypoint `python -m baton cut --world DIR --beliefs FILE --leaver ID --port P`; "world.json gains CAN records and people[].capacity; extraction/lane-A caches must therefore be keyed on the inputs each step actually reads, so existing caches stay valid"; kill "6 rounds; if not green by 14:30, the Cut stays as the tested spike shown in the README only".
- **No product code**: no `baton/cut.py`; the CLI has no `cut` or `commit` command (baton/__main__.py parser, checked 12:00).
- **No world data for the Cut yet**: the locked checks need `CAN` records and a `capacity` on every person (checks/locked/cut/test_cut.py:23-26). At HEAD `85eeabd` `baton/generate.py` has neither. At 12:20 IST a loop round was editing `generate.py` (uncommitted) to add them from a separate `random.Random(f"halden-capability-{seed}")`, numbered after every other record — the approach this doc recommends. Re-check `git log -3` before building.
- The maths is tested in a scratch spike (verify/spike.py:113-169), not in the product.

## What it is, in plain words

**Part 1. The Cut.** The Rehearsal (M02) tells us *which* duties break when someone leaves. The Cut answers the next question: *can the people who stay actually take all of them?*

Think of water pipes.
- Water starts at one tap, `S`.
- A pipe goes from `S` to each duty that breaks. Size 1: each broken duty needs one taker.
- A pipe goes from each duty to each person who is allowed and able to take it. Size 1.
- A pipe goes from each person to the drain, `T`. Its size is that person's capacity: how many extra duties they can take.

FalkorDB's `algo.maxFlow` pushes as much water as it can from `S` to `T`.
- **What flows:** duties being handed to people. One unit = one duty placed with one person.
- **What a capacity means:** the most units a pipe can carry. `S → duty`: the duty needs 1 taker. `duty → person`: that person may take it (1) or the pipe does not exist. `person → T`: how many duties that person can still absorb.
- **"IMPOSSIBLE 3/4"** means: 4 duties break, and at most 3 of them can be placed with the people who stay, whatever you try. One duty has nobody who can take it. If all 4 can be placed, the verdict is **POSSIBLE** (that exact word is in the locked check, checks/locked/cut/test_cut.py:37).
- **The proof (certificate):** after the flow we find the *minimum cut*: a set of pipes that separates `S` from `T` and whose sizes add up to exactly the flow. Then nobody can find a better assignment. That turns "IMPOSSIBLE" from an opinion into a proof (checked by checks/locked/cut/test_cut.py:50-59).
- **The gap:** the duties whose `S → duty` pipe is not full. The locked checks call them `unplaceable` and require them whenever the verdict is IMPOSSIBLE (checks/locked/cut/test_cut.py:60-62).
- **N-1 sweep:** for each person who stays, pretend they are also away and run max flow again. If the number drops, that person is a single point of failure. Grid operators do this for power lines: "N-1 for people" (checks/locked/cut/test_cut.py:65-73).

The number "3/4" is the tested spike's toy result (`VERDICT: IMPOSSIBLE (3.0/4.0)`, verify/spike.py:158, re-run on 18 Oct). **It is not a Halden number.** Halden numbers come from the product run and must never be typed into the page or the video by hand.

**Part 2. The real write.** After successors accept duties, Baton does the work for real. A drafted feature, `commit_write` (checks/pending/commit_write/test_commit_write.py, not locked), defines it:
1. Write the accepted successors into the **live** graph. The database enforces one successor per duty and refuses people who have left (checks/pending/commit_write/test_commit_write.py:1-3, :83-93).
2. Then write the new owners into a file in a **git repository** and commit it (`--repo DIR`), and read it back into a receipt (checks/pending/commit_write/test_commit_write.py:60-72).
3. Nothing reaches the repository if the graph write fails or FalkorDB is down (checks/pending/commit_write/test_commit_write.py:93, :96-103).
4. Report whether the leaver is now "ready to leave": every broken duty has a successor (checks/pending/commit_write/test_commit_write.py:53, :79-80).

This differs from today's `handover`, which accepts successors **on a fork only**; the live graph never changes (baton/handover.py:1, baton/handover.py:87, baton/rehearse.py:134-135). `commit` is the first command that changes the live graph on purpose; the drafted check expects `live_hash_before != live_hash_after` (checks/pending/commit_write/test_commit_write.py:54).

**Gitea.** BUILD_PLAN names a local Gitea server as "a real system to write to: CODEOWNERS and on-call rota files, read back over its API" (BUILD_PLAN.md:20), with the git repository as the fallback (BUILD_PLAN.md:70). The drafted checks only test the git repository. So: build the git path first (it is the checked contract); Gitea is an extra target, accepted by go-and-see only (PROPOSED; Gitea REST facts in 2_CONTRACT.md §4).

## Which track focus it serves
- Track 1: "graph queries and algorithms as agent tools", "actions based on what the graph shows", "explainable results" (00_GROUND_TRUTH.md:9). The Cut is the algorithm; the write is the action; the certificate is the explanation.
- Track 3: "who owns what", "keeping knowledge current as things change" (00_GROUND_TRUTH.md:8).
- Rule 2/3: the verdict is computed by `algo.maxFlow` inside FalkorDB (00_GROUND_TRUTH.md:11, 00_GROUND_TRUTH.md:21). The locked check asserts the output's `cypher` contains `algo.maxFlow` (checks/locked/cut/test_cut.py:82).

## In scope
- Generator: add `CAN` records and person `capacity` (required by checks/locked/cut/test_cut.py:23-26).
- Loader: read the new record type without crashing (see traps below).
- `baton/cut.py` + `cut` CLI command, matching the locked checks.
- `commit` CLI command per the drafted commit_write checks (live graph write + git repo commit + read-back receipt).
- Optional Gitea target (PROPOSED; no checks).
- A Gitea service in `docker-compose.yml` (PROPOSED; human edit, the file is outside the loop's mutable paths, loop/program.md:16).

## Not in scope
- Changing the live graph on accept.
- Gitea enforcing CODEOWNERS on pull requests. We only write and read a file.
- Okta, Jira Cloud, Slack (BUILD_PLAN.md:30). Any LLM in the Cut (BUILD_PLAN.md:29).

## Inputs
- `cut`: `--world DIR --beliefs FILE --leaver ID --port P` (checks/locked/cut/test_cut.py:18-19).
- `commit`: `--world --beliefs --leaver --repo DIR --port P --assign DUTY=PERSON ...` (checks/pending/commit_write/test_commit_write.py:39-45).

## Outputs
- `cut`: one JSON object (fields in 2_CONTRACT.md §3, taken from the locked checks).
- `commit`: one JSON object with `committed`, `refused`, `ready_to_leave`, `still_uncovered`, `external`, live hashes (2_CONTRACT.md §4).

## Dependencies
- M01 generator (new data), M02 rehearse (failing duties: baton/rehearse.py:108-148), M03 handover (accepted list).
- FalkorDB **v4.22.1**. falkordblite 0.10.0 bundles v4.18.3 with no maxFlow (00_GROUND_TRUTH.md:29). The checks start the v4.22.1 module (checks/locked/cut/conftest.py is a byte copy of checks/locked/rehearsal_core/conftest.py, whose lines 10-11 pick `fdb422/falkordb.so`).
- M09 API / M10 web to show it (no `/api/cut` route exists; PROPOSED).

## Rules the locked checks fix
From checks/locked/cut/flow_oracle.py:2-3 and :8-28:
1. Broken duties = distinct duties in the reference G-lane failures, using the answer-key true + noise beliefs (checks/locked/cut/flow_oracle.py:9; checks/locked/cut/test_cut.py:14). Each gets an `S → duty` pipe of 1.
2. `duty → person` pipe of 1 if the person is active (`left_at` null), not the leaver, and either has a `CAN` record for that duty, or the duty is known only from beliefs (not in `world["duties"]`) and the person is on the leaver's team (checks/locked/cut/flow_oracle.py:11, :15-25).
3. `person → T` pipe of `person["capacity"]` for every active stayer (default 1 in the reference if missing) (checks/locked/cut/flow_oracle.py:26-27).
4. N-1: remove one stayer entirely and recompute (checks/locked/cut/flow_oracle.py:59-60); keys = all active stayers (checks/locked/cut/test_cut.py:70-71).
5. Across seeds 7, 101, 202, 303 both verdicts must occur (checks/locked/cut/test_cut.py:40-46). This is a property of the generated worlds.

## Traps found while documenting (must be handled in the same round as the generator change)
1. `load._record_text` treats every record that is not OWNER/ROUTES_TO/SHIFT as ESCALATES_TO and reads `from_person` (baton/load.py:70-77 at HEAD 85eeabd). A `CAN` record would raise `KeyError` while building Source nodes (baton/load.py:87-88 at HEAD 85eeabd). `extract._record_line` has the same fall-through (baton/extract.py:115-122 at HEAD 85eeabd).
2. Record ids are numbered after sorting all records by their JSON text (baton/generate.py:428-42 at HEAD 85eeabd9 at HEAD 85eeabd). Adding `CAN` records **renumbers** existing `rec-` ids, which beliefs cite as sources.
3. Any new `rng` call in the main stream shifts every later random choice (baton/generate.py:13 at HEAD 85eeabd5 at HEAD 85eeabd seeds one `random.Random(seed)`). Draw Cut data from a separate `random.Random` after the main world is built.
4. The extraction cache is keyed on the exact world.json bytes (baton/extract.py:9-11 at HEAD 85eeabd). Any generator change misses the committed seed-7 cache, and the **locked** check `test_committed_seed7_cache_replays_offline_and_feeds_the_rehearsal` runs `extract --offline` on seed 7 (checks/locked/ai_layer/test_ai_layer.py:55-58). A miss exits 4 (baton/extract.py:180-182 at HEAD 85eeabd). **The cut charter's answer:** re-key the extraction and lane-A caches on the inputs each step actually reads, so existing caches stay valid (loop/features.md, `### cut`). That re-keying must land in the same round as the generator change, and the locked ai_layer checks must stay green. At 12:20 IST an uncommitted round was doing exactly this: the new `extract.py` docstring keys the cache on `extract_input` ("every record except CAN capability records"), so "data the model never sees (capability, capacity) cannot invalidate it", and the seed-7 cache file was being renamed to the new key.

## Owner, time, kill
- Owner: the loop (BUILD_PLAN.md:70). Compose edit for Gitea: a human.
- Time: 14:30–15:30 IST (BUILD_PLAN.md:70). No new features after 15:30 (BUILD_PLAN.md:72).
- Kill: Cut — "6 rounds; if not green by 14:30, the Cut stays as the tested spike shown in the README only" (loop/features.md `### cut`; BUILD_PLAN.md:70 gives 14:30–15:30, the charter is stricter). Write — "Gitea fails → write to the git repo file + read-back" (BUILD_PLAN.md:70).
