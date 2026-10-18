# M03 · Handover and demo · CONTRACT

Copied from code (`handover.py` md5 `d4637781…`, `demo.py` md5 `d1a68249…`, `__main__.py` md5 `14b34b50…`), the project-context skill and the locked checks. Line numbers were checked at 12:00 IST.

**Moving line numbers in `__main__.py`.** At about 11:58 IST the `ask` round (M4, still in progress) added an `ask` subparser and dispatch to baton/__main__.py (md5 `14b34b50…`). Lines 1–33 did not move. The demo parser is now at lines 42–46 and the dispatch at lines 54–77. The citations here use that file. If the ask round is reverted, line numbers above 33 go back (demo parser 34–38, dispatch 46–60).

## 1. `handover` CLI
```
python -m baton handover --world DIR --beliefs FILE --leaver ID --assign DUTY=PERSON [--assign ...] [--port P]
```
| Flag | Type | Default | Source |
|---|---|---|---|
| `--world` | folder | required | baton/__main__.py:28 |
| `--beliefs` | JSON list file | required | baton/__main__.py:29 |
| `--leaver` | person id | required | baton/__main__.py:30 |
| `--assign` | `DUTY=PERSON`, can repeat | `[]` | baton/__main__.py:31 |
| `--port` | int | 6379 | baton/__main__.py:32 |

There is no `--lane` or `--confirm`. Handover always runs lane G with `confirm=all` (baton/handover.py:87).

### Output (baton/handover.py:89-91), with keys sorted (baton/__main__.py:80)
| Field | Type | Meaning |
|---|---|---|
| `leaver` | str | as given |
| `graph` | str | `halden_<seed>` |
| `accepted` | list of `{duty, person}` | assignments whose guarded write created an edge (baton/handover.py:78-79) |
| `refused` | list of `{duty, person, reason}` | everything else (baton/handover.py:68, :76, :81) |
| `failures_after` | list | the same row shape as `rehearse` `failures` (2_CONTRACT of M02), computed after the acceptances and the departure (baton/handover.py:90) |
| `live_hash_before`, `live_hash_after` | str | live-graph fingerprint (baton/handover.py:91) |

The skill's contract lists only `{accepted, refused:[{duty, person, reason}], failures_after}` (.claude/skills/project-context/SKILL.md:17). The extra keys are additions.

### Refusal reasons, verbatim
| Reason | When | Source |
|---|---|---|
| `expected DUTY=PERSON, got '<raw>'` | no `=`, or an empty side | baton/handover.py:67-68 |
| `duty already has an accepted successor` | the UNIQUE constraint rejected the write | baton/handover.py:73-76 |
| `no duty '<duty>' in the graph` | the duty node does not exist on the fork | baton/handover.py:52-53 |
| `person has left or does not exist (no such person)` | the person node does not exist | baton/handover.py:54-55 |
| `person is the one leaving` | person = leaver | baton/handover.py:56-57 |
| `person has left or does not exist (left_at <ms>)` | `left_at` is not null | baton/handover.py:58 |

Observed on seed 7 at 11:37 IST: assigning to the leaver, to `ingrid.tanaka` (left), and the malformed `bad` gave the leaver, left_at and malformed reasons above.

### Exit codes
Exit 0 even when some assignments are refused (observed). Exit 3 if FalkorDB cannot be reached (baton/__main__.py:78-79, baton/graph.py:30-32). Exit 1 if the leaver is not in the graph (`baton handover: no person …`, baton/rehearse.py:115-116 with `cmd="handover"` from baton/handover.py:86). Any other `ResponseError` is re-raised and crashes with a traceback (baton/handover.py:74-75).

## 2. `demo` CLI
```
python -m baton demo [--seed N] [--port P] [--offline] [--beliefs FILE]
```
| Flag | Default | Source |
|---|---|---|
| `--seed` | 7 | baton/__main__.py:43 |
| `--port` | 6379 | baton/__main__.py:44 |
| `--offline` | false (store_true) | baton/__main__.py:45 |
| `--beliefs` | `fixtures/beliefs_seed<N>.json` | baton/__main__.py:46, baton/demo.py:21 |

### Output (baton/demo.py:51-55)
| Field | Type | Source |
|---|---|---|
| `seed` | int | |
| `offline` | bool, echoes the flag | baton/demo.py:51 |
| `graph` | str | |
| `leaver` | str | `world["leaver"]` (baton/demo.py:35) |
| `lanes.W/R/G.failures` | int, count of failing **events** | baton/demo.py:43 |
| `live_hash_before`, `live_hash_after` | str | baton/demo.py:38, :50 |
| `after_handover.failures`, `.accepted`, `.refused` | int | baton/demo.py:53-54 |
| `unpromoted` | int, the number of beliefs the gate refused in lane G | baton/demo.py:45, :55 |

The skill's contract: `{leaver, lanes:{W:{failures:int},R,G}, live_hash_before, live_hash_after, after_handover:{failures:int}}` (.claude/skills/project-context/SKILL.md:18). The other keys are additions.

Observed, seed 7 (11:37 IST): `lanes W 6, R 7, G 37`, `after_handover {accepted 6, failures 0, refused 0}`, `unpromoted 4`, hashes equal, `offline true`.

### Demo errors
| Situation | Exit | Message | Source |
|---|---|---|---|
| no cached beliefs for the seed | 4 | ``baton demo: no cached extraction for seed <N> (<path>); run `python -m baton extract` first`` (note: `extract` does not exist yet) | baton/demo.py:22-25 |
| FalkorDB down | 3 | `FalkorDB is not reachable …` | baton/graph.py:26, :30-32 |
| no active stayers | assigns = `[]`, so failures stay | baton/demo.py:48 |

### What demo does, in order (baton/demo.py:29-55)
1. Find the beliefs file, or exit 4.
2. `generate.build(seed)` in memory, and write only world.json to a temp folder. The answer key never touches disk (baton/demo.py:32-34; loop/rounds/rehearsal_core-3.md "Mechanism learned").
3. `open_session` loads `halden_<seed>` if it is missing. An existing graph is used as it is.
4. `on_fork` for W, R and G, each on its own fork, then count the failures.
5. Read the stayers from the **live** graph (query below), sort the G failure duties, and assign them round-robin.
6. `handover.run(..., session=s)` reuses the same session.

## 3. Graph writes (fork only)

### Constraint setup: baton/handover.py:35-37, :40
```python
fork.query("CREATE INDEX FOR ()-[r:OWNER]-() ON (r.active_key)")
db.connection.execute_command("GRAPH.CONSTRAINT", "CREATE", fork.name, "UNIQUE", "RELATIONSHIP", "OWNER",
                              "PROPERTIES", 1, "active_key")
```
```cypher
CALL db.constraints()
```
*Plain English:* on the fork, index the `active_key` property of OWNER edges, then ask FalkorDB for a UNIQUE constraint on it. Wait until `db.constraints()` reports `OPERATIONAL`. Fail with an error if it reports `FAILED`, or after 5 s (baton/handover.py:38-46). The index has to exist first (docs/modules/00_GROUND_TRUTH.md:22). Record OWNER edges have no `active_key`, so the constraint ignores them (baton/handover.py:6-7; loop/rounds/rehearsal_core-3.md "Facts").

### Q_ACCEPT, the guarded write: baton/handover.py:20-25
```cypher
MATCH (d:Duty {id: $duty}), (p:Person {id: $person})
WHERE p.left_at IS NULL AND p.id <> $leaver
CREATE (d)-[r:OWNER {vf: $leave_at, vt: $open, basis: 'accepted', active_key: d.id, accepted_by: p.id,
                     rec: 'handover:' + d.id + '=' + p.id}]->(p)
RETURN count(r)
```
*Plain English:* in **one** query: find the duty and the person, check that the person has not left and is not the leaver, and only then draw "this person owns this duty from the leave date onward". If any check fails, MATCH/WHERE gives zero rows and nothing is created; `count(r)` is 0. If the duty already has an accepted successor, `active_key` would repeat. The engine rejects the write with "unique constraint violation" and rolls it back (loop/rounds/rehearsal_core-3.md "Facts"). `rec` gives the new edge a source id like `handover:d-x=person.y`, so `failures_after` rows can cite it.

### Q_WHY_NOT, explaining a zero-row write: baton/handover.py:27-30
```cypher
OPTIONAL MATCH (d:Duty {id: $duty})
OPTIONAL MATCH (p:Person {id: $person})
RETURN d IS NOT NULL, p IS NOT NULL, p.left_at, p.id = $leaver
```
*Plain English:* a read that only *explains* the refusal. The decision was already made by the write's WHERE (loop/rounds/rehearsal_core-3.md "Mechanism learned").

### Q_STAYERS (demo, on the live graph, read-only): baton/demo.py:17, :46
```cypher
MATCH (p:Person) WHERE p.left_at IS NULL AND p.id <> $leaver RETURN p.id ORDER BY p.id
```

### Order on the fork (make-before-break): baton/rehearse.py:128-133 via baton/handover.py:87
gate → HOLDS → present cover pass → **accept all** (constraint + Q_ACCEPT per assignment) → Q_DEPART → departed cover pass → delete fork. The successor edges exist before the leaver is marked gone.

## 4. API wrappers (server/app.py; the loop report says `/api/health`, `/api/demo?seed=7` and `/api/handover` answered against a real FalkorDB, loop/reports/rehearsal_core.md "Go and see")
| Route | Body / query | Calls | Source |
|---|---|---|---|
| `POST /api/handover` | `{"seed": int = 7, "assign": {duty: person}}` | the `handover` CLI with one `--assign` per dict entry; enriches `failures_after` | server/app.py:79-93 |
| `GET /api/demo?seed=7` | none | `rehearse` W, R, G with `--confirm all` (not the `demo` command); enriches the failures | server/app.py:63-76 |

The `assign` dict cannot hold two people for one duty, so the API cannot show the second-owner refusal. Beliefs come from `fixtures/beliefs_seed<N>.json`; otherwise the API calls `cli("extract", …)`, which does not exist (server/app.py:31-36).

## 5. Rules enforced by locked checks
- **Check 12** `test_handover_to_active_successors_clears_every_failure[7,101]` (checks/locked/rehearsal_core/test_rehearsal_core.py:160-174): assign each G failure duty round-robin to sorted stayers → `refused` is empty, the `accepted` duties equal the failure duties, and `failures_after == []`.
- **Check 13** `test_handover_refuses_departed_successor_and_second_owner` (:177-191): a departed person → refused, and the duty is still in `failures_after`. Two stayers for one duty → exactly 1 accepted and 1 refused.
- **Check 15** `test_wiring_demo_runs_end_to_end_offline` (:205-216): `leaver` matches; every lane count is an int; W and R equal the oracle counts; G > R; hashes equal; `after_handover.failures == 0`.
