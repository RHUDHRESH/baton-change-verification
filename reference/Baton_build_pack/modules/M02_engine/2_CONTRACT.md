# M02 · Engine · CONTRACT

Every item is copied from code or a locked check. Line numbers were checked at 11:50 IST against these files: `graph.py` md5 `64689988…`, `load.py` md5 `341a3a93…`, `rehearse.py` md5 `2571a059…`, `__main__.py` md5 `14b34b50…`.

**Moving line numbers in `__main__.py`.** At about 11:58 IST the `ask` round (M4, still in progress) added an `ask` subparser and dispatch to baton/__main__.py (md5 `14b34b50…`). Lines 1–33 did not move. The demo parser is now at lines 42–46 and the dispatch at lines 54–77. The citations here use that file. If the ask round is reverted, line numbers above 33 go back (demo parser 34–38, dispatch 46–60).

**Moving line numbers in `rehearse.py`.** At about 11:41 IST the `ask` round (M4) added `cover_query(lane)` to rehearse.py (baton/rehearse.py:97-100), so everything after line 96 moved down by 4 lines. The Cypher text did not change. If that round is reverted, `cover` goes back to line 97, and every other rehearse.py citation above line 100 here should be read as 4 lower. Lines 1–96 (all the `Q_*` constants and `gate`) did not move.

## 1. CLI

### `load`
```
python -m baton load --world DIR [--port P]
```
| Flag | Type | Default | Source |
|---|---|---|---|
| `--world` | folder holding world.json | required | baton/__main__.py:16 |
| `--port` | int | 6379 | baton/__main__.py:17 |

stdout: `{"created": bool, "edges": int, "graph": "halden_<seed>", "nodes": int}` (baton/load.py:118). Seed 7, observed: first run `created true, nodes 161, edges 96`; second run `created false`, same counts.

### `rehearse`
```
python -m baton rehearse --world DIR --beliefs FILE --leaver ID [--lane W|R|G] [--confirm all|none] [--port P]
```
| Flag | Type | Default | Source |
|---|---|---|---|
| `--world` | folder | required | baton/__main__.py:20 |
| `--beliefs` | path to a JSON list of beliefs | required | baton/__main__.py:21 |
| `--leaver` | person id | required | baton/__main__.py:22 |
| `--lane` | `W`, `R` or `G` | `G` | baton/__main__.py:23 |
| `--confirm` | `all` or `none` | **`none`** | baton/__main__.py:24 |
| `--port` | int | 6379 | baton/__main__.py:25 |

stdout (baton/rehearse.py:154-156), with keys sorted (baton/__main__.py:80):
| Field | Type | Meaning |
|---|---|---|
| `lane` | str | as given |
| `leaver` | str | as given |
| `graph` | str | `halden_<seed>` |
| `failures` | list | sorted by `(at, duty)` (baton/rehearse.py:143) |
| `failures[].duty` | str | duty id |
| `failures[].at` | int, epoch ms | event time |
| `failures[].day` | int | `(at - now) // day_ms`, where `now` and `day_ms` are read from the graph's `Company` node (baton/rehearse.py:114, baton/rehearse.py:146) |
| `failures[].event` | str | event id (`ev-NNNN`, or `<belief id>-evN` for belief events) |
| `failures[].label` | str | event label |
| `failures[].status` | str | `"record"` if some covering path uses no `HOLDS` edge; otherwise the belief basis `"confirmed"` (with `--confirm all`) or `"believed"` (with `--confirm none`) (baton/rehearse.py:71-73, baton/rehearse.py:129) |
| `failures[].sources` | list of str | sorted, de-duplicated ids: `rec` ids of record edges and `srcs` of HOLDS edges on the covering paths **before** departure (baton/rehearse.py:74-75, baton/rehearse.py:147) |
| `unpromoted` | list of `{belief, reason}` | beliefs refused by the gate (baton/rehearse.py:94) |
| `live_hash_before`, `live_hash_after` | str (sha256 hex) | fingerprint of the live graph (baton/rehearse.py:125, baton/rehearse.py:137) |

The reason strings, verbatim (baton/rehearse.py:78-83):
- `cites source(s) that do not exist: <ids>`
- `only <n> source cited; needs at least 2`
- `all <n> sources are of <k> kind; needs at least 2 kinds (message, joblog, ticket, record)`

### Exit codes and errors
| Situation | Exit | Output | Source |
|---|---|---|---|
| OK | 0 | JSON on stdout | baton/__main__.py:80-81 |
| FalkorDB not reachable | 3 | stderr `FalkorDB is not reachable at <host>:<port>: <error>`, nothing on stdout | baton/graph.py:26, baton/graph.py:30-32 |
| Leaver id not in the graph | 1 | `baton rehearse: no person '<id>' in graph halden_<seed>` (raised as `SystemExit` with a string) | baton/rehearse.py:115-116 (exit 1 observed) |
| Bad or missing flag | 2 | argparse usage on stderr | observed for a missing `--beliefs` |

### Environment
- `FALKORDB_HOST`, default `localhost` (baton/graph.py:21). Connect timeout 3 s (baton/graph.py:23). The CLI has **no** `FALKORDB_PORT` variable; the port comes only from `--port`. `FALKORDB_PORT` is read only by server/app.py:10.

## 2. Graph model (`halden_<seed>`)

Graph name: `halden_<seed>` (baton/graph.py:14-15). Forks are named `halden_<seed>:fork:<pid>` (baton/graph.py:49, baton/rehearse.py:126).

### Nodes on the live graph (written once by `load`)
| Label | Properties | Source |
|---|---|---|
| `Company` | `id:'company', name, seed, label, now, day_ms, window_days, leave_at` | baton/load.py:20-22 |
| `Person` | `id, name, team, role, left_at` | baton/load.py:24-26 |
| `Duty` | `id, name, kind` | baton/load.py:28-30 |
| `Rota` | `id` | baton/load.py:32-34 |
| `Source` | `id, type ('message'|'joblog'|'ticket'|'record'), text, author, at` | baton/load.py:36-38, baton/load.py:80-89 |
| `Event` | `id, duty, at, label` | baton/load.py:40-43 |

Every record is also a `Source` of type `record`. Its text is generated from the record, for example `"<duty> is owned by <person>"` (baton/load.py:70-77, baton/load.py:87-88).

### Edges on the live graph
Every edge except `NEEDS` carries `vf` (valid from), `vt` (valid to) and `rec` (the id of the record that justifies it). Validity means `vf <= t < vt`. `OPEN = 253_402_300_799_000` (baton/graph.py:7).
| Pattern | vf | vt | Source |
|---|---|---|---|
| `(:Duty)-[:OWNER]->(:Person)` | `coalesce(since, 0)` | OPEN | baton/load.py:45-48 |
| `(:Duty)-[:ROUTES_TO]->(:Rota)` | 0 | OPEN | baton/load.py:50-53 |
| `(:Rota)-[:SHIFT]->(:Person)` | `from` | `to` | baton/load.py:55-58 |
| `(:Person)-[:ESCALATES_TO]->(:Person)` | 0 | OPEN | baton/load.py:60-63 |
| `(:Event)-[:NEEDS]->(:Duty)` | n/a | n/a | baton/load.py:43 |

### Indexes (range indexes, created once at load)
`Person.id`, `Duty.id`, `Rota.id`, `Source.id`, `Event.at` (baton/load.py:18, baton/load.py:98-99). Observed: `EXPLAIN` of `MATCH (p:Person {id:'…'})` shows `Node By Index Scan`.

### Added on the fork only (never on the live graph)
| Pattern | Properties | Source |
|---|---|---|
| `(:Belief)` | `id, person, duty, duty_name, kind, claim, refs, ev_at, ev_label, promoted` | baton/rehearse.py:28-30, baton/rehearse.py:42 |
| `(:Belief)-[:CITES]->(:Source)` | (none) | baton/rehearse.py:32-34 |
| `(:Duty {from_belief:true})` | for belief duties not in the world, created by MERGE | baton/rehearse.py:48-49 |
| `(:Duty)-[:HOLDS]->(:Person)` | `vf:0, vt:OPEN, basis, srcs, belief` | baton/rehearse.py:50 |
| `(:Event {from_belief:true})-[:NEEDS]->(:Duty)` | `id:'<belief>-evN', duty, at, label` | baton/rehearse.py:52-54 |
| `Person.left_at` of the leaver | set to `Company.leave_at` | baton/rehearse.py:56, baton/rehearse.py:132 |

## 3. The Cypher, verbatim, with plain English

All queries below are copied from the code. All of them pass the locked checks on FalkorDB v4.22.1 (32/32, loop/results.tsv:5). Parameters are passed separately; the model never writes Cypher.

### 3.1 load.py

**Indexes**: baton/load.py:98-99
```python
for label, prop in INDEXES:
    g.query(f"CREATE INDEX FOR (n:{label}) ON (n.{prop})")
```
*Plain English:* make lookups by id (and events by time) fast. The label and property come from the fixed list on line 18, never from user input.

**Q_COMPANY**: baton/load.py:20-22
```cypher
CREATE (:Company {id: 'company', name: $c.company, seed: $c.seed, label: $c.label, now: $c.now,
                  day_ms: $c.day_ms, window_days: $c.window_days, leave_at: $c.leave_at})
```
*Plain English:* store the company clock in the graph: what "now" is, how long a day is, the window, and when the leaver goes. Rehearse reads these from the graph, not from the JSON file.

**Q_PEOPLE**: baton/load.py:24-26
```cypher
UNWIND $rows AS p
CREATE (:Person {id: p.id, name: p.name, team: p.team, role: p.role, left_at: p.left_at})
```
*Plain English:* one Person node per person. `left_at` is null for people still here.

**Q_DUTIES**: baton/load.py:28-30
```cypher
UNWIND $rows AS d
CREATE (:Duty {id: d.id, name: d.name, kind: d.kind})
```
*Plain English:* one node per thing that must get done.

**Q_ROTAS**: baton/load.py:32-34
```cypher
UNWIND $rows AS id
CREATE (:Rota {id: id})
```
*Plain English:* one node per on-call rota. The list of rota ids comes from the ROUTES_TO and SHIFT records (baton/load.py:102).

**Q_SOURCES**: baton/load.py:36-38
```cypher
UNWIND $rows AS s
CREATE (:Source {id: s.id, type: s.type, text: s.text, author: s.author, at: s.at})
```
*Plain English:* every chat message, job log row, ticket and record becomes a Source node. A belief can only cite something that exists here.

**Q_EVENTS**: baton/load.py:40-43
```cypher
UNWIND $rows AS e
MATCH (d:Duty {id: e.duty})
CREATE (:Event {id: e.id, duty: e.duty, at: e.at, label: e.label})-[:NEEDS]->(d)
```
*Plain English:* each scheduled moment is attached to the duty it needs.

**Q_OWNER**: baton/load.py:45-48
```cypher
UNWIND $rows AS r
MATCH (d:Duty {id: r.duty}), (p:Person {id: r.person})
CREATE (d)-[:OWNER {vf: coalesce(r.since, 0), vt: $open, rec: r.id}]->(p)
```
*Plain English:* "this person owns this duty, from the date in the record, with no end date." `rec` remembers which record said so.

**Q_ROUTES_TO**: baton/load.py:50-53
```cypher
UNWIND $rows AS r
MATCH (d:Duty {id: r.duty}), (o:Rota {id: r.rota})
CREATE (d)-[:ROUTES_TO {vf: 0, vt: $open, rec: r.id}]->(o)
```
*Plain English:* "pages for this duty go to this rota", always.

**Q_SHIFT**: baton/load.py:55-58
```cypher
UNWIND $rows AS r
MATCH (o:Rota {id: r.rota}), (p:Person {id: r.person})
CREATE (o)-[:SHIFT {vf: r.from, vt: r.to, rec: r.id}]->(p)
```
*Plain English:* "this person is on this rota for this one week only."

**Q_ESCALATES_TO**: baton/load.py:60-63
```cypher
UNWIND $rows AS r
MATCH (a:Person {id: r.from_person}), (b:Person {id: r.to_person})
CREATE (a)-[:ESCALATES_TO {vf: 0, vt: $open, rec: r.id}]->(b)
```
*Plain English:* "if A does not answer, it goes to B."

**Counts**: baton/load.py:116-117
```cypher
MATCH (n) RETURN count(n)
MATCH ()-[r]->() RETURN count(r)
```

### 3.2 graph.py

**Fingerprint**: baton/graph.py:41-42 (both run with `ro_query`, so they are read-only)
```cypher
MATCH (n) RETURN labels(n), properties(n)
MATCH (a)-[r]->(b) RETURN a.id, type(r), properties(r), b.id
```
*Plain English:* read every node and edge with all their properties, sort the rows, and hash them with sha256 (baton/graph.py:43-44). The same hash before and after a rehearsal means the live graph was not changed.

**Fork**: baton/graph.py:47-53. This is not Cypher; it is the client call `Graph.copy(clone)`, which sends `GRAPH.COPY <src> <dst>` (falkordb-py `graph.py:149-160`, in the scratchpad clone). A stale fork with the same name is deleted first, because GRAPH.COPY fails if the target exists (docs/modules/00_GROUND_TRUTH.md:20). The fork is deleted with `Graph.delete()` in a `finally` block (baton/rehearse.py:134-135).

### 3.3 rehearse.py

**Session reads**: baton/rehearse.py:114-115
```cypher
MATCH (c:Company) RETURN c.now, c.day_ms, c.leave_at
MATCH (p:Person {id: $id}) RETURN count(p)
```
*Plain English:* read the clock from the graph and make sure the leaver exists.

**Q_BELIEFS** (on the fork): baton/rehearse.py:26-34
```cypher
UNWIND $beliefs AS b
CREATE (x:Belief {id: b.id, person: b.person, duty: b.duty, duty_name: b.duty_name, kind: b.kind,
                  claim: b.claim, refs: b.sources,
                  ev_at: [e IN b.events | e.at], ev_label: [e IN b.events | e.label]})
WITH x, b
UNWIND b.sources AS ref
MATCH (s:Source {id: ref})
CREATE (x)-[:CITES]->(s)
```
*Plain English:* write each belief as a node. `refs` remembers every id it *claims* to cite. A `CITES` edge is drawn only to sources that really exist, because `MATCH` finds nothing for a made-up id, so no edge is drawn for it.

**Q_GATE**: baton/rehearse.py:36-44
```cypher
MATCH (b:Belief)
OPTIONAL MATCH (b)-[c:CITES]->(s:Source)
WITH b, count(c) AS found, count(DISTINCT s.type) AS kinds, collect(DISTINCT s.id) AS hit
WITH b, kinds, [r IN b.refs WHERE NOT r IN hit] AS missing,
     size(b.refs) >= 2 AND found = size(b.refs) AND kinds >= 2 AS ok
SET b.promoted = ok
RETURN b.id, ok, size(b.refs), kinds, missing
ORDER BY b.id
```
*Plain English:* a belief is promoted only when all three are true:
1. It cites at least 2 sources.
2. Every cited id was found. "Claimed" equals "found": if a ref has no CITES edge, `found` is smaller than `size(b.refs)`.
3. The sources it cites come in at least 2 different types.

The query also returns which refs are missing, so the CLI can say why a belief was refused.

**Q_HOLDS**: baton/rehearse.py:46-54
```cypher
MATCH (b:Belief {promoted: true}), (p:Person {id: b.person})
MERGE (d:Duty {id: b.duty})
  ON CREATE SET d.name = b.duty_name, d.kind = b.kind, d.from_belief = true
CREATE (d)-[:HOLDS {vf: 0, vt: $open, basis: $basis, srcs: b.refs, belief: b.id}]->(p)
WITH b, d
UNWIND range(0, size(b.ev_at) - 1) AS i
CREATE (:Event {id: b.id + '-ev' + toString(i + 1), duty: d.id, at: b.ev_at[i], label: b.ev_label[i],
                from_belief: true})-[:NEEDS]->(d)
```
*Plain English:* for each promoted belief, draw "this person holds this duty". If the duty is new (for example a customer promise found only in chat), create it. Add the belief's own dates (a promise due date, for example) as events. `basis` is `confirmed` when `--confirm all`, otherwise `believed` (baton/rehearse.py:129). `srcs` keeps the evidence ids, so a failure can cite them.

**Q_DEPART**: baton/rehearse.py:56
```cypher
MATCH (p:Person {id: $leaver}) SET p.left_at = $leave_at
```
*Plain English:* on the fork only, the leaver leaves at `Company.leave_at`.

**Q_COVER**: baton/rehearse.py:58-75 (template). `{scope}`, `{types}` and `{hops}` are filled from the fixed `LANES` table (baton/rehearse.py:20-24) by `str.replace` (baton/rehearse.py:100). They are never filled from user input. Rendered for lane **G**:
```cypher
MATCH (c:Company)
MATCH (e:Event)-[:NEEDS]->(d:Duty)
WHERE e.at >= c.now AND e.at < c.now + c.window_days * c.day_ms
  AND ($with_beliefs OR e.from_belief IS NULL)

WITH d, e ORDER BY e.id
WITH d, e.at AS t, collect(e)[0] AS e
OPTIONAL MATCH path = (d)-[:OWNER|ROUTES_TO|SHIFT|ESCALATES_TO|HOLDS*1..4]->(who:Person)
WHERE all(r IN relationships(path) WHERE r.vf <= t AND r.vt > t)
  AND (who.left_at IS NULL OR who.left_at > t)
WITH d, t, e, collect(path) AS paths
RETURN d.id AS duty, t AS at, e.id AS event, e.label AS label, size(paths) > 0 AS covered,
       CASE WHEN any(p IN paths WHERE none(r IN relationships(p) WHERE type(r) = 'HOLDS')) THEN 'record'
            ELSE head(reduce(acc = [], p IN paths |
                   acc + [r IN relationships(p) WHERE type(r) = 'HOLDS' | r.basis])) END AS status,
       reduce(acc = [], p IN paths | acc + reduce(src = [], r IN relationships(p) |
              src + CASE WHEN type(r) = 'HOLDS' THEN r.srcs ELSE [r.rec] END)) AS sources
```
Lane **R** is the same with `[:OWNER|ROUTES_TO|SHIFT|ESCALATES_TO*1..4]`. Lane **W** uses `[:OWNER*1..1]` and adds the scope line `MATCH (d)-[:OWNER]->(:Person {id: $leaver})` after the WHERE (baton/rehearse.py:21). `$with_beliefs` is true only for G (baton/rehearse.py:104).

*Plain English, line by line:*
1. Take every event inside `[now, now + 30 days)`, using the clock stored in the graph. Belief events count only in lane G.
2. (W only) Keep only duties whose OWNER edge points at the leaver. This is the "owner field" view a normal offboarding checklist uses.
3. If a duty has two events at the same moment, keep one row (the lowest event id).
4. Look for any path from the duty to a person, at most 4 steps, using only the lane's edge types. **Every** edge on the path must be valid at that event's time, and the person at the **end** must not have left by then. People in the middle may have left. That is how "the rota still lists Ingrid, who left, and her escalation goes to Hana" works: the path passes through Ingrid and ends at Hana.
5. `covered` means at least one such path exists. `status` is `record` if some path uses only record edges; otherwise it is the basis of the belief edge. `sources` lists the record ids and belief evidence ids on those paths.

This query runs with `ro_query` on the fork (baton/rehearse.py:104), once before departure and once after (baton/rehearse.py:130-133).

**The failure rule (Python, comparing two Cypher results)**: baton/rehearse.py:140-148. An event is a failure if `covered` was true before departure and false after. Its sources are the ones from the *before* pass: the evidence for who was covering it.

## 4. Pipeline order (baton/rehearse.py:121-137)
`fingerprint(live)` → `GRAPH.COPY` → Q_BELIEFS + Q_GATE → Q_HOLDS → Q_COVER (present) → optional callback (M03 uses it) → Q_DEPART → Q_COVER (gone) → `fork.delete()` in `finally` → `fingerprint(live)`.

## 5. Contract rules enforced by locked checks
- Lane G, R and W sets of `(duty, at)` equal the independent oracle on seeds 7, 101, 202 and 303 (checks/locked/rehearsal_core/test_rehearsal_core.py:61-88).
- Every noise belief is in `unpromoted` with a reason, no true belief is, and noise does not change the failures (checks/locked/rehearsal_core/test_rehearsal_core.py:100-109).
- `--confirm none` → belief-only failures have status `believed`. `--confirm all` → only `record` or `confirmed`. Same pairs either way (checks/locked/rehearsal_core/test_rehearsal_core.py:113-123).
- Every failure has non-empty sources that exist, and `day == (at-now)//day_ms` (checks/locked/rehearsal_core/test_rehearsal_core.py:127-135).
- The live people, node count, edge count and hash are unchanged, and no graph whose name contains "fork" is left (checks/locked/rehearsal_core/test_rehearsal_core.py:139-157).
- FalkorDB down → non-zero exit, "falkordb" in the output, no `"failures"` on stdout (checks/locked/rehearsal_core/test_rehearsal_core.py:195-202).
- Deleting an ESCALATES_TO edge in FalkorDB changes the R answer (checks/locked/rehearsal_core/test_rehearsal_core.py:236-246).
