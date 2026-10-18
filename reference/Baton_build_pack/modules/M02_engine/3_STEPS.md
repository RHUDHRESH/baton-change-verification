# M02 · Engine · STEPS

M02 is **done** and its checks are green (loop/results.tsv:5). These steps are for verifying it, learning to defend it, and changing it safely.

## Loop rule (applies to every step)
Checks come first. A human approves them, they are locked, and only then does building start. Never edit `checks/locked/**`, `loop/bin/**` or `.claude/settings.json` (loop/program.md:16-21). Change only `baton`, `fixtures`, `Makefile` and `README.md` (loop/config.json "mutable_paths"). One round is one hypothesis and one commit, and the prediction is written first (loop/program.md:23-25). Keep a round only if more checks pass and none regress (loop/program.md:26-27). Before changing a shared format, update every reader in the same round (loop/program.md:60-62). `rehearse.py` is shared by `handover`, `demo` and now `ask` (baton/handover.py:18, baton/demo.py:12).

```
S=/tmp/claude-0/-home-claude/9e986261-4c5d-5119-82fd-cce4a3dc1af5/scratchpad
PY=$S/venv/bin/python
B=$S/venv/lib/python3.13/site-packages/redislite/bin
cd /home/claude/baton
```

## Step 1: Start FalkorDB v4.22.1 and load a company
- Goal: a live graph you can look at.
- Files touched: none in the repo.
- Commands (server command from .claude/skills/project-context/SKILL.md:11):
  ```
  $B/redis-server --port 6399 --daemonize yes --dir /tmp --loadmodule $S/fdb422/falkordb.so --save ''
  $PY -m baton generate --seed 7 --out $S/w7
  $PY -m baton load --world $S/w7 --port 6399
  $PY -m baton load --world $S/w7 --port 6399
  ```
- Done when: the first load prints `"created": true, "nodes": 161, "edges": 96` and the second prints `"created": false` with the same counts (observed 11:36 IST).
- Prompt for a coding agent:
  > Start the FalkorDB server with the command in the project-context skill on port 6399. Run `generate --seed 7` then `load` twice. Report both JSON lines. Do not edit files.

## Step 2: Rehearse all three lanes
- Goal: see W < R < G and read one failure with its sources.
- Commands:
  ```
  $PY -c "import json;k=json.load(open('$S/w7/answer_key.json'));json.dump(k['true_beliefs']+k['noise_beliefs'],open('$S/b7.json','w'))"
  for L in W R G; do $PY -m baton rehearse --world $S/w7 --beliefs $S/b7.json --leaver hana.sharma --lane $L --confirm all --port 6399 | $PY -c "import json,sys;d=json.load(sys.stdin);print('$L',len(d['failures']),d['live_hash_before']==d['live_hash_after'])"; done
  ```
  (Making the beliefs file from the answer key is fine *for a human looking*, outside `baton/`. The locked checks do the same thing in conftest (checks/locked/rehearsal_core/test_rehearsal_core.py:21-24). Product code must never do it.)
- Done when: it prints `W 6 True`, `R 7 True`, `G 38 True` (observed 11:36 IST). Counted as distinct duties instead of events, that is W 3, R 4, G 6 (loop/reports/rehearsal_core.md, "Interpretations").
- Prompt:
  > Run the loop above and paste its three lines. Then print the first G failure as pretty JSON and explain each field using docs/modules/M02_engine/2_CONTRACT.md §1.

## Step 3: Watch the graph decide (the "graph is the truth" demo)
- Goal: prove FalkorDB decides, not the JSON.
- Command: delete the escalation into the leaver in FalkorDB, then rehearse lane R again. This is the same edit the locked check makes (checks/locked/rehearsal_core/test_rehearsal_core.py:241):
  ```
  $PY -c "from falkordb import FalkorDB;g=FalkorDB(port=6399).select_graph('halden_7');g.query('MATCH (:Person)-[r:ESCALATES_TO]->(:Person {id:\$l}) DELETE r',{'l':'hana.sharma'})"
  $PY -m baton rehearse --world $S/w7 --beliefs $S/b7.json --leaver hana.sharma --lane R --confirm all --port 6399 | $PY -c "import json,sys;print(len(json.load(sys.stdin)['failures']))"
  ```
- Done when: the first command deletes 2 edges and the R count drops from 7 to 6 (observed 11:52 IST on seed 7). The JSON file was not touched, so the graph made the difference. The locked check `test_the_graph_is_the_source_of_truth_not_the_json` does the same on seed 303.
- Clean up afterwards: `$PY -c "from falkordb import FalkorDB;FalkorDB(port=6399).select_graph('halden_7').delete()"`, then load again.

## Step 4: Defend the queries (rule 12)
- Goal: each student can explain every query in 2_CONTRACT.md §3 without notes.
- Done when: each student answers the questions below out loud, in their own words, and matches the answer given.

| Likely question from a FalkorDB engineer | Answer (with where it comes from) |
|---|---|
| Why GRAPH.COPY and not a transaction you roll back? | The rehearsal writes beliefs, HOLDS edges and a changed `left_at`, then reads. On a copy, the live graph is only ever read, and the hash proves it (baton/rehearse.py:121-137). Do not bring up MVCC; the ground-truth file forbids claiming it (docs/modules/00_GROUND_TRUTH.md:18). |
| What does the copy cost? | Not measured separately. A full `rehearse` CLI run on seed 7 (161 nodes, 96 edges) took about 0.3 s wall time, Python start-up included (observed 11:50 IST, 3 runs). The full locked suite ran in 8.5 s (loop/last_score.json). Do not quote numbers for bigger graphs. |
| Why `*1..4` and not shortestPath? | We need *any* valid path, with a per-edge time filter. `shortestPath` inside MATCH is not supported on v4.22 (docs/modules/00_GROUND_TRUTH.md:27). The 4-hop limit is the rule the checks use (checks/locked/rehearsal_core/oracle.py:4; .claude/skills/project-context/SKILL.md:21). The planted on-call chain duty→rota→departed person→leaver is 3 hops (`ROUTES_TO`, `SHIFT`, `ESCALATES_TO`). |
| Variable-length matching uses trail semantics. Does that change the answer? | Round 2 argued it does not: any walk of ≤ 4 valid hops to an active person contains a simple path of ≤ 4 hops (loop/rounds/rehearsal_core-2.md, "Mechanism"). It is also checked: the results equal the independent BFS oracle on 4 locked seeds, and on 29 seeds × 3 lanes in a scratch run (loop/rounds/rehearsal_core-2.md, "Facts"). |
| Why can people in the middle of a path have left? | That is the point. A stale rota slot still routes to the escalation target. Only the endpoint must be active (baton/rehearse.py:67-68; oracle rule at checks/locked/rehearsal_core/oracle.py:71-75). |
| Why `relationships(path)` and not `r` from `[r*1..4]`? | On v4.22 a variable-length relationship alias is a single Edge, so we use `relationships(p)` (docs/modules/00_GROUND_TRUTH.md:27). |
| Do your queries use indexes? | Id lookups do: `EXPLAIN` of `MATCH (p:Person {id:…})` shows `Node By Index Scan` (observed). The cover query does **not** use the `Event.at` index: its plan starts with `Node By Label Scan | (d:Duty)` and filters the window afterwards (observed 11:50 IST via `g.explain(rehearse.cover_query('G'), …)`). At this size it does not matter. Say so honestly if asked. |
| How does the gate count sources without EXISTS{} or COUNT{}? | Those are not supported on v4.22 (docs/modules/00_GROUND_TRUTH.md:27). CITES edges are created only to Source nodes that MATCH, and then `count(c)` is compared with `size(b.refs)` (baton/rehearse.py:32-41). |
| Two sources from one generator: are they "independent"? | The rule only checks *types* (message, joblog, ticket, record). In the demo one generator wrote everything. Say that plainly (scratchpad book/BATON_FINAL_PLAN.md, Q&A 9). |
| Why are times integers? | v4.22 has no `datetime()`. Epoch-ms integers compare correctly (docs/modules/00_GROUND_TRUTH.md:27-28). |
| What stops the model from writing Cypher? | The model never writes Cypher. Query text comes only from constants in the code. Lane parts come from the fixed `LANES` table, and user values go in as parameters (baton/rehearse.py:20-24, baton/rehearse.py:100-104). |
| Where does "now" come from? | From the `Company` node in the graph, not from the clock and not from the JSON (baton/rehearse.py:114). |

- Prompt for a coding agent (to quiz the students):
  > Using only docs/modules/M02_engine/2_CONTRACT.md and the code it cites, ask me 10 questions a FalkorDB engineer would ask about these queries, one at a time. After each answer, tell me what I got wrong, citing the file and line.

## Step 5: Change the engine (only through a new locked check)
- Goal: any later change, for example counting duties instead of events for the story (loop/reports/rehearsal_core.md, "Interpretations"), keeps 32/32.
- Files touched: `baton/rehearse.py` (shared!), plus every caller: `baton/handover.py`, `baton/demo.py`, and whatever `ask` adds.
- Commands: write the check in `checks/pending/<feature>/` → a human approves → `python3 loop/bin/lock_checks.py <feature> --approved-by "<who: what they said>"` (loop/bin/lock_checks.py:4) → round file → edit → `python3 loop/bin/run_checks.py`.
- Done when: the score has not gone down and the round is logged as `keep`.
- Kill: no new features after 15:30 IST (docs/BUILD_PLAN.md:72).
- Prompt:
  > You are a feature-builder. Read loop/program.md, loop/features.md, the project-context skill and loop/last_score.json. Write ONE hypothesis to the round file before editing. Do not change any Q_* query text unless the hypothesis needs it. Keep the fork pattern: fingerprint → GRAPH.COPY → work → delete in finally → fingerprint. Never write to the live graph after load. Never read answer_key.json. Never write the word "oracle" in baton/. Run python3 loop/bin/run_checks.py and report.
