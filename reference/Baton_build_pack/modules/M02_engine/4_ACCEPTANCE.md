# M02 · Engine · ACCEPTANCE

## Locked checks that cover M02 (exact names, all in checks/locked/rehearsal_core/test_rehearsal_core.py)
| Check | Line | Status |
|---|---|---|
| `test_baton_G_matches_oracle_on_dev_seed` | :61 | passing since round 2 (loop/results.tsv:4) |
| `test_baton_G_matches_oracle_on_unseen_seeds[101,202,303]` | :69 | passing since round 2 |
| `test_records_only_lane_R_matches_oracle[7,101,202,303]` | :77 | passing since round 2 |
| `test_workflow_lane_W_matches_oracle[7,101,202,303]` | :85 | passing since round 2 |
| `test_gate_refuses_every_noise_belief_and_noise_changes_nothing` | :100 | passing since round 2 |
| `test_unconfirmed_beliefs_are_labelled_believed_not_confirmed` | :113 | passing since round 2 |
| `test_every_failure_cites_sources_that_exist` | :127 | passing since round 2 |
| `test_live_graph_untouched_and_fork_dropped` | :139 | passing since round 2 |
| `test_fails_loudly_when_falkordb_is_down` | :195 | passing since round 2 |
| `test_product_never_reads_the_answer_key_or_oracle` | :220 | passing since round 2 |
| `test_the_graph_is_the_source_of_truth_not_the_json` | :236 | passing since round 2 |

That is 19 runs, and all of them still pass after round 3 (loop/results.tsv:5, 32/32).

## Go and see (commands in 3_STEPS.md, steps 1–3)
| Command | Expected visible output (seed 7) |
|---|---|
| `load` twice | `created true, nodes 161, edges 96`, then `created false` |
| `rehearse` W / R / G with the answer-key beliefs, `--confirm all` | 6 / 7 / 38 failing events; hash before == after |
| the same with `fixtures/beliefs_seed7.json` | 6 / 7 / 37; `unpromoted` = `b-02, b-04, b-05, b-06` |
| `rehearse --port <dead>` | stderr `FalkorDB is not reachable at localhost:<port>: …`, exit 3 |
| `rehearse --leaver nobody` | `baton rehearse: no person 'nobody' in graph halden_7`, exit 1 |
| delete the ESCALATES_TO edges into the leaver, then R | 2 edges deleted; R goes from 7 to 6 |

All observed by the writer between 11:36 and 11:52 IST on a scratch FalkorDB v4.22.1 (port 6417).

## Failure modes and fallbacks
| Failure | Symptom | Fallback |
|---|---|---|
| FalkorDB down or wrong host | exit 3 with "FalkorDB" in the message; the API returns 503 (server/app.py:22) | start the container; check `FALKORDB_HOST` |
| A stale graph from an older generator | answers do not match the new world.json, because `load` never reloads over an existing graph (baton/load.py:96-97) | delete `halden_<seed>` in FalkorDB, then `load` again |
| A crash mid-rehearsal | none; the fork is deleted in `finally` (baton/rehearse.py:134-135). A fork can survive only if the process is killed hard | delete any graph named `*:fork:*` |
| A slow cover query on a big graph | not seen at this size (~0.3 s per CLI run, seed 7) | keep demo seeds small; the plan does not use the `Event.at` index (see 3_STEPS.md, step 4) |
| Kill time (historical) | not green by 14:30 | hero = Cut + reason-broken query (docs/BUILD_PLAN.md:66). Not needed: green at about 12:05 (loop/reports/rehearsal_core.md) |

## Anti-hallucination list
| Wrong assumption | Correct fact | Source |
|---|---|---|
| The engine works in Python and FalkorDB only stores data | Promotion, HOLDS, coverage, status and sources are all computed by Cypher on the fork. Python only compares the two cover results and sorts them | baton/rehearse.py:36-75, baton/rehearse.py:140-148 |
| The live graph gets the beliefs | Beliefs, CITES, HOLDS and belief events exist only on the fork, and the fork is deleted | baton/rehearse.py:126-135 |
| `--confirm` defaults to `all` | It defaults to `none`. The API passes `all` | baton/__main__.py:24; server/app.py:70 |
| `rehearse` reads now/leave_at from world.json | It reads them from the `Company` node in the graph | baton/rehearse.py:114 |
| `load` refreshes the graph | Once the graph exists, `load` returns `created: false` and changes nothing | baton/load.py:96-97 |
| Failures are counted per duty | `failures` lists events. Seed 7 G = 38 events but 6 duties | loop/reports/rehearsal_core.md |
| Every person on the path must be active | Only the endpoint must be active at t. People in the middle may have left | baton/rehearse.py:67-68 |
| Lane W walks rotas | W is `OWNER*1..1`, and only for duties whose OWNER edge points at the leaver | baton/rehearse.py:21 |
| `sources` are the evidence for *why it breaks* | They are the record ids and belief evidence on the paths that covered the event **before** departure | baton/rehearse.py:74-75, baton/rehearse.py:144-147 |
| Gate = "two independent systems" | ≥ 2 refs, all exist, ≥ 2 distinct `Source.type` values; `record` counts as a type | baton/rehearse.py:39-41 |
| There is an `ESCALATES_TO` out of the leaver | The generator never creates one (an invariant). With one, R would cover the leaver's own certs | loop/rounds/rehearsal_core-1.md |
| You can use `datetime()`, `EXISTS{}`, `COUNT{}`, label alternation or `shortestPath` in MATCH | None of them work on v4.22 | docs/modules/00_GROUND_TRUTH.md:27 |
| `falkordblite` can run the checks | The checks start a redis-server with the v4.22.1 module (`fdb422/falkordb.so`); falkordblite bundles v4.18.3 | checks/locked/rehearsal_core/conftest.py:10-11, :22; docs/modules/00_GROUND_TRUTH.md:29 |
| `FALKORDB_PORT` configures the CLI | The CLI uses `--port`; only the API reads `FALKORDB_PORT` | baton/graph.py:21; server/app.py:10 |
| Fork names are random UUIDs | `halden_<seed>:fork:<pid>`, replaced if a stale one exists | baton/graph.py:49-51; baton/rehearse.py:126 |
| HOLDS edges have real validity dates | HOLDS is `vf: 0, vt: OPEN`: a belief is treated as valid for all time | baton/rehearse.py:50 |
| The engine uses MVCC or snapshots | Never claim MVCC. Isolation comes from GRAPH.COPY | docs/modules/00_GROUND_TRUTH.md:18, :51 |
