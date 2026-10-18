# M06 · ACCEPTANCE

Paths relative to `/home/claude/baton/`. `verify/` = `/tmp/claude-0/-home-claude/9e986261-4c5d-5119-82fd-cce4a3dc1af5/scratchpad/verify/`. `PY` = the project venv python.

## 1. Checks

**Locked** (commit `85eeabd`, ~12:00 IST): `checks/locked/cut/test_cut.py`, listed in checks/locked/MANIFEST.json `files`. Exact function names:

| Check function | Line | What it asserts |
|---|---|---|
| `test_world_has_capability_and_capacity_data` | checks/locked/cut/test_cut.py:22-26 | world.json has `CAN` records; every person has int `capacity` ≥ 1 (seeds 7, 101, 202, 303) |
| `test_flow_and_verdict_match_the_reference` | checks/locked/cut/test_cut.py:29-37 | `demand` = number of broken duties; `flow` = reference max flow; `verdict` is `POSSIBLE` iff flow = demand, else `IMPOSSIBLE` |
| `test_both_verdicts_occur_across_seeds` | checks/locked/cut/test_cut.py:40-46 | across the 4 seeds the reference finds both verdicts (a world property; no product call) |
| `test_min_cut_is_a_certificate` | checks/locked/cut/test_cut.py:49-62 | every `min_cut` edge is in the reference network and their capacities sum to `flow`; if IMPOSSIBLE, `unplaceable` is non-empty and only broken duties |
| `test_n_minus_1_sweep_matches_the_reference` | checks/locked/cut/test_cut.py:65-73 | keys = all active stayers; each value = reference max flow without that person (seeds 7, 202) |
| `test_cut_runs_on_a_fork_and_leaves_the_live_graph_alone` | checks/locked/cut/test_cut.py:76-82 | equal live hashes; no graph with "fork" in its name; `cypher` contains `algo.maxFlow` |
| `test_cut_fails_loudly_when_falkordb_is_down` | checks/locked/cut/test_cut.py:85-89 | non-zero exit and "falkordb" in the output |

Beliefs used by the checks: answer-key true + noise beliefs written to `beliefs_cut.json` (checks/locked/cut/test_cut.py:12-15), not the extraction cache.

**Drafted, not locked**: `checks/pending/commit_write/test_commit_write.py`:
| Check function | Line | What it asserts |
|---|---|---|
| `test_full_handover_is_written_to_the_live_graph_and_rehearsal_goes_green` | checks/pending/commit_write/test_commit_write.py:48-57 | all broken duties committed; `ready_to_leave` true, `still_uncovered` empty; live hashes differ; a later `rehearse --lane G` has no failures |
| `test_external_file_is_committed_and_read_back_into_the_receipt` | checks/pending/commit_write/test_commit_write.py:60-72 | `external.verified` true; `external.commit` = new repo HEAD; `git show HEAD:<file>` contains duty and person; `read_back` = `[{duty, person}]` |
| `test_partial_handover_is_written_but_not_ready_to_leave` | checks/pending/commit_write/test_commit_write.py:75-80 | one assignment → `ready_to_leave` false; `still_uncovered` = the other broken duties |
| `test_database_refuses_a_second_successor_and_a_departed_person` | checks/pending/commit_write/test_commit_write.py:83-93 | second successor and departed person both in `refused`; `committed` empty; repo HEAD unchanged |
| `test_nothing_reaches_the_repo_when_falkordb_is_down` | checks/pending/commit_write/test_commit_write.py:96-103 | non-zero exit, "falkordb" in output, repo HEAD unchanged |

The Gitea path is **not** a check: skipped tests count as failures (loop/bin/run_checks.py:9-10) and Gitea does not run where the checks run. Gitea is accepted by go-and-see.

## 2. Go and see (commands and what you should see)

Start FalkorDB v4.22.1 for manual runs (.claude/skills/project-context/SKILL.md:11), port 6399.

1. Tested maths, toy graph (works today):
   ```
   PY /tmp/claude-0/-home-claude/9e986261-4c5d-5119-82fd-cce4a3dc1af5/scratchpad/verify/spike.py 6399
   ```
   See (observed 18 Oct): `PASS min-cut capacity == maxFlow (certificate)`, `VERDICT: IMPOSSIBLE  (3.0/4.0)`, `N-1 ... {'Sam': 2.0, 'Arjun': 1.0, 'Mei': 3.0, 'Kenji': 3.0}`, `PASS fork deleted, live graph untouched`. Warning: the spike deletes and recreates graph `halden_s42` on that server (verify/spike.py:15-18).
2. Halden Cut (after step 3):
   ```
   PY -m baton generate --seed 7 --out /tmp/w7
   PY -m baton extract --world /tmp/w7 --out /tmp/w7/b.json --offline   # only if the extract command exists and the cache matches this world
   PY -m baton cut --world /tmp/w7 --beliefs /tmp/w7/b.json --leaver <world.json "leaver"> --port 6399
   ```
   See: JSON with `demand`, `flow`, `verdict`, `min_cut`, `unplaceable`, `n_minus_1`, `cypher` (containing `algo.maxFlow`), equal live hashes. Write the numbers down; they are the only Halden numbers you may quote. (The doc writer's same-team scratch run on the pre-change seed-7 world gave 3 of 6; the drafted rules differ, so expect a different number.)
3. No fork left: `redis-cli -p 6399 GRAPH.LIST` shows no name containing `fork`.
4. Commit (after step 4): output has `committed`, `ready_to_leave`, `external.verified: true`; `git -C <repo> log --oneline -1` shows `external.commit`; `git -C <repo> show HEAD:<external.file>` shows the duty and person. Then `rehearse --lane G` on the same world shows fewer (or zero) failures, because the live graph changed.
5. Gitea (optional, steps 5–6): open `http://127.0.0.1:3001/baton/halden-ops` and see the file with the same commit sha as the receipt.

## 3. Failure modes and fallbacks
| Failure | Fallback |
|---|---|
| maxFlow missing ("unknown procedure" or similar) | You are on falkordblite or the wrong engine. Use FalkorDB v4.22.1 (00_GROUND_TRUTH.md:18, 00_GROUND_TRUTH.md:29). |
| `test_min_cut_is_a_certificate` fails | Bug in residual arcs or in the edge list. Compare with verify/spike.py:144-157 line by line. Usual cause: using only the maxFlow `edges` list (flow-carrying edges) as the whole network. |
| Duplicate FLOW edges between the same nodes | De-duplicate the duty list in Python before the source-pipe query (00_GROUND_TRUTH.md:21: no multi-edges). |
| Belief-only duties missing from the flow fork | Build the network on a fork where the gate and holds ran (baton/rehearse.py:46-50; the ask preparation at baton/ask.py:210-212). |
| Verdict is always POSSIBLE | Eligibility too wide (any active person, as handover uses at baton/handover.py:21-22). Revisit the rule with Joyal. |
| Not green by 15:30 | Show the tested spike result labelled "toy graph, tested on FalkorDB v4.22.1", or drop the Cut beat (BUILD_PLAN.md:72). |
| Gitea does not start, or the API returns 401/404/422 | Keep the local git receipt (the checked path, BUILD_PLAN.md:70). Say "git repository" in the video, not "Gitea". |
| git missing in the API container | Install it in deploy/Dockerfile (human edit) or run `commit` on the host. |
| `commit` run twice in a demo | The second run is refused (one successor per duty) and the live graph keeps the first. Use a fresh seed string or reload the graph for each take. |

## 4. Anti-hallucination list
| Likely wrong assumption | Correct fact | Source |
|---|---|---|
| falkordblite can run maxFlow | falkordblite 0.10.0 bundles v4.18.3 with **no** maxFlow | 00_GROUND_TRUTH.md:29 |
| maxFlow returns the min-cut | It returns `maxFlow, edges, edgeFlows` (and `nodes`); no cut. Compute it with a residual BFS | 00_GROUND_TRUTH.md:21, docs-repo algorithms/maxflow.mdx:36-38 |
| `edges` lists every edge in the network | Only edges with positive flow | maxflow.mdx:59, maxflow.mdx:190 |
| `maxFlow` is an integer | Returned `3.0` (float) on v4.22.1; compare with a tolerance | spike run 18 Oct |
| Pass several relationship types | Use one type (`FLOW`) and no multi-edges | 00_GROUND_TRUTH.md:21 |
| The min-cut edges are "the gap duties" | Cut edges are the full pipes that prove the limit. The gap = source pipes not full; the stuck people = residual-reachable people | spike re-run 18 Oct (reachable `['Mei', 'Okta billing-admin', 'S']`) |
| Halden has `CAN_COVER`, `spare`, `load` | Those are the spike's names. The drafted checks want `CAN` records and person `capacity`; neither exists in the generator yet. Halden Person today: `id, name, team, role, left_at`; Duty: `id, name, kind` | verify/spike.py:46-47, checks/locked/cut/test_cut.py:25-26, baton/load.py:24-30 at HEAD 85eeabd |
| The verdict words are ABSORBABLE / IMPOSSIBLE | The checks want `POSSIBLE` / `IMPOSSIBLE` | checks/locked/cut/test_cut.py:37 |
| The output keys are `max_flow`, `cut` | The checks read `flow`, `min_cut`, `unplaceable`, `demand`, `n_minus_1`, `cypher` | checks/locked/cut/test_cut.py:35-37, :55-62, :71-73, :82 |
| A new record type loads fine | `load._record_text` and `extract._record_line` treat unknown types as ESCALATES_TO and crash on `from_person` | baton/load.py:70-77 at HEAD 85eeabd, baton/extract.py:115-122 at HEAD 85eeabd |
| Changing the generator is harmless | It renumbers `rec-` ids (sorted-JSON numbering) and changes world bytes, which misses the extraction cache the locked ai_layer check replays | baton/generate.py:428-429 at HEAD 85eeabd, baton/extract.py:9-11 at HEAD 85eeabd, checks/locked/ai_layer/test_ai_layer.py:55-58 |
| N-1 must delete the person from the fork | Setting their drain pipe to 0 gives the same max flow as removing them, and is what the spike tested | verify/spike.py:159-166, checks/locked/cut/flow_oracle.py:59-60 |
| "IMPOSSIBLE 3/4" is a Halden result | It is the spike's toy result. Halden numbers come from the product run | spike output 18 Oct |
| `handover` changes the live graph | `handover` runs on a fork that is deleted. Only the drafted `commit` writes the live graph | baton/handover.py:87, baton/rehearse.py:134-135, checks/pending/commit_write/test_commit_write.py:1-3 |
| The commit's external system is Gitea | The drafted checks use a local git repository (`--repo`); Gitea is optional | checks/pending/commit_write/test_commit_write.py:12-18, :43 |
| Use `requests` for Gitea | Package rule: standard library + falkordb only | .claude/skills/project-context/SKILL.md:9 |
| Gitea file `content` is plain text | "Content must be base64 encoded" | docs.gitea.com/api/operations/repo-create-file/ |
| `PUT` without `sha` updates an existing file | `sha` is the existing blob id; leave it empty only to create | docs.gitea.com/api/operations/repo-update-file/ |
| Gitea uses SQLite by default | `DB_TYPE` default is `mysql`; set `sqlite3` | docs.gitea.com/administration/config-cheat-sheet |
| Gitea can use host port 3000 | FalkorDB already maps `127.0.0.1:3000` | docker-compose.yml:4 |
| Gitea enforces our CODEOWNERS | Not claimed and not tested. We only write and read a file | — |
| `datetime()` for commit messages or file dates | Not in FalkorDB v4.22; use the company clock (epoch ms) | 00_GROUND_TRUTH.md:27-28 |
