# M01 · Generator · ACCEPTANCE

## Locked checks that cover M01 (exact names)
| Check | Line | Status |
|---|---|---|
| `test_generate_is_deterministic_and_seed_sensitive` | checks/locked/rehearsal_core/test_rehearsal_core.py:28 | passing since round 1 (loop/results.tsv:3) |
| `test_world_holds_schedules_not_failures_and_has_every_planted_shape[7,101,202,303]` | checks/locked/rehearsal_core/test_rehearsal_core.py:39 | passing since round 1 |
| `test_each_lane_sees_strictly_more_W_then_R_then_G[7,101,202,303]` | checks/locked/rehearsal_core/test_rehearsal_core.py:93 | passing since round 1 |
| `test_product_never_reads_the_answer_key_or_oracle` (source-scan half) | checks/locked/rehearsal_core/test_rehearsal_core.py:223-227 | the whole check passes since round 2 (loop/last_score.json) |

## Go and see
```
$PY -m baton generate --seed 7 --out $S/a && $PY -m baton generate --seed 7 --out $S/b && cmp $S/a/world.json $S/b/world.json && echo SAME
grep -c -i "answer_key\|true_beliefs\|noise_beliefs\|expected_failures" $S/a/world.json   # expect 0
```
Expected: `SAME`, then `0`. For seed 7 the summary line shows `"leaver": "hana.sharma"` and `"beliefs": 6` (observed 11:36 IST).

## Failure modes and fallbacks
| Failure | What you see | Fallback |
|---|---|---|
| A generator change renumbers ids | the demo's G count changes, or `after_handover.failures` stops being 0 | revert the round (loop/program.md:26-27); rebuild `fixtures/beliefs_seed7.json` against the new ids |
| A seed where W = R or R = G | `test_each_lane_sees_strictly_more…` fails for that seed | revert; round 1 checked seeds 0–59 plus 7/11/12/101/202/303 (loop/rounds/rehearsal_core-1.md) |
| Someone adds a clock call | the determinism check fails | remove it; dates come only from `BASE_NOW` (baton/generate.py:16) |

## Anti-hallucination list
| Wrong assumption | Correct fact | Source |
|---|---|---|
| Times are ISO strings | Times are epoch-ms integers | baton/generate.py:13-16; docs/modules/00_GROUND_TRUTH.md:28 |
| Person ids look like `p-priya` (as in `web/mock/demo_7.json`) | Ids are `first.last`, for example `hana.sharma`. The web mock is hand-written and does not match real output | baton/generate.py:204; web/mock/demo_7.json |
| `now` is today's date | `now` is fixed at Fri 2026-10-23 00:00 UTC for every seed | baton/generate.py:16 |
| The leaver leaves at `now` | `leave_at = now + 1 day` | baton/generate.py:137 |
| world.json lists the failures | It lists only schedules. There is no failure field, and a check forbids `expected_failures` | checks/locked/rehearsal_core/test_rehearsal_core.py:42-43 |
| The product may read answer_key.json "just for ids" | Never. Only `generate.py` may even contain the string | checks/locked/rehearsal_core/test_rehearsal_core.py:226-227 |
| Belief ids are always `blf-NN` | The generator writes `blf-NN`. The demo fixture uses `b-NN`. The product accepts any string id | baton/generate.py:444; fixtures/beliefs_seed7.json; baton/rehearse.py:88 |
| The generator uses an LLM to write chat | No. The chat comes from fixed templates (`T_GHOST_MSG`, `T_PROMISE_MSG`, …) and `random.Random(seed)` | baton/generate.py:67-118, baton/generate.py:135 |
| "Two independent sources" means two different systems or authors | The gate rule is: at least 2 sources, all exist, at least 2 distinct **types** (message, joblog, ticket, record). In the demo one generator wrote all of them; say so plainly | .claude/skills/project-context/SKILL.md:21; scratchpad book/BATON_FINAL_PLAN.md Q&A 9 |
| Every seed has an orphan duty | Only when 2 or more people have already left | baton/generate.py:251 |
| `window_days` events stop at 30 days | Job runs go up to `end + 10 days`, and the out-of-window cert is 35–90 days out. That is on purpose: the window filter is tested | baton/generate.py:228, baton/generate.py:291 |
