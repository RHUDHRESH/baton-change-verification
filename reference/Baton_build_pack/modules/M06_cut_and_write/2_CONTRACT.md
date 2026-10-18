# M06 · CONTRACT

Path prefixes: `verify/` = `/tmp/claude-0/-home-claude/9e986261-4c5d-5119-82fd-cce4a3dc1af5/scratchpad/verify/`; `docs-repo/` = `/tmp/claude-0/-home-claude/9e986261-4c5d-5119-82fd-cce4a3dc1af5/scratchpad/falkor/repos/docs/`. All other paths are relative to `/home/claude/baton/`.

Legend: **EXISTS** = copied from a file (cited). **PROPOSED** = not yet in code; the named person decides. **UNTESTED** = a command or query nobody has run; the test command is given.

---

## 1. Facts the Cut relies on (EXISTS)

| Fact | Source |
|---|---|
| maxFlow call shape: `CALL algo.maxFlow({sourceNodes:[s], targetNodes:[k], relationshipTypes:['FLOW'], capacityProperty:'cap'}) YIELD maxFlow, edges, edgeFlows` | verify/spike.py:125-128 |
| It ran through `ro_query` (read-only query) on the fork | verify/spike.py:125 |
| `edges` and `edgeFlows` hold **only edges that carry flow**, same order | docs-repo/algorithms/maxflow.mdx:59-60, docs-repo/algorithms/maxflow.mdx:190 |
| No min-cut is returned; compute it with a residual BFS | 00_GROUND_TRUTH.md:21 |
| Use one relationship type and no multi-edges | 00_GROUND_TRUTH.md:21 |
| `maxFlow` came back as a float (`3.0`) on v4.22.1, although the docs table says Integer | spike run 18 Oct (output `TYPES float 3.0`), docs-repo/algorithms/maxflow.mdx:61 |
| Fork with `GRAPH.COPY src dst`; fails if dst exists | verify/spike.py:114-115, 00_GROUND_TRUTH.md:20 |
| Product helper for forks: `fork(db, name, suffix)` makes `<name>:fork:<suffix>`, deletes a stale one first | baton/graph.py:47-53 |
| Live-graph fingerprint helper `fingerprint(g)` | baton/graph.py:39-44 |
| FalkorDB unreachable → `Unreachable` → stderr message, exit code 3 | baton/graph.py:10-11, baton/graph.py:18-27, baton/graph.py:30-32 |
| Unknown leaver → `SystemExit("baton <cmd>: no person '<id>' in graph <name>")` (exit 1) | baton/rehearse.py:115-116 |
| Failing duties of a lane: `open_session` + `on_fork` + `failures` | baton/rehearse.py:108-148, used the same way in baton/demo.py (G-lane loop) and baton/ask.py:240-242 |

### The tested algorithm (verify/spike.py:113-169), step by step
1. Fork: `GRAPH.COPY` the live graph to `<G>:fork:<hex>` (113-116).
2. Source pipes: one `(:FlowSrc {id:'S'})-[:FLOW {cap: d.load}]->(d)` per duty the leaver still holds; one `(:FlowSink {id:'T'})` (117-119).
3. Duty → person pipes: `(d)-[:FLOW {cap: c.cap}]->(p)` for each `CAN_COVER` edge of a person who is not the leaver (120-121).
4. Person → sink pipes: `(p)-[:FLOW {cap: p.spare}]->(k)` for each non-leaver with `spare > 0` who received a pipe (122-123).
5. Solve: run maxFlow; build `{edge id: flow}` from `id(edges[i])` and `edgeFlows[i]` (124-129). Read the **full** FLOW edge list separately, because maxFlow returns only flow-carrying edges (130-132).
6. Demand = sum of source-pipe capacities (134).
7. Verify: every flow ≤ capacity; flow in = flow out at every node except S and T (136-142).
8. Residual graph: forward arc if `cap - flow > 1e-9`; backward arc if `flow > 1e-9`. Edges missing from the maxFlow result have flow 0 (144-148).
9. BFS from S over the residual graph (149-154).
10. Cut = edges from a reached node to an unreached node; certificate = sum of their capacities equals maxFlow (155-157).
11. Verdict `ABSORBABLE` if maxFlow ≥ demand else `IMPOSSIBLE` (158). **The product must print `POSSIBLE`, not `ABSORBABLE`** (checks/locked/cut/test_cut.py:37).
12. N-1: copy each sink pipe's `cap` to `cap0`; for each person set their sink cap to 0, re-solve, restore from `cap0` (159-166).
13. Delete the fork; check the live graph has no `FlowSrc` (167-169).

Spike output on 18 Oct (re-run by this writer on a fresh v4.22.1 server): `PASS min-cut capacity == maxFlow (certificate) [maxFlow=3.0 demand=4.0 cut=[('S', '/billing CODEOWNER', 1), ('S', 'EDI cut-over sign-off', 2)]]`, `VERDICT: IMPOSSIBLE (3.0/4.0)`, `N-1 ... {'Sam': 2.0, 'Arjun': 1.0, 'Mei': 3.0, 'Kenji': 3.0}`, `PASS fork deleted, live graph untouched`. With an added print, the residual-reachable set was `['Mei', 'Okta billing-admin', 'S']` and the unmet duty was `Okta billing-admin` (1 unit). So: the **cut edges** are the full pipes that prove the limit; the **gap** is the duty whose source pipe is not full, and the reachable people (Mei, no spare room) are why. Do not say "the min-cut names the gap duty" — in this run the gap duty was on the reachable side, not in the cut.

---

## 2. Flow network on the Halden graph (rules from the locked checks)

Built only on a fork. Never on the live graph.

| Element | Shape | Capacity | Rule source |
|---|---|---|---|
| source node | `(:FlowSrc {id: 'S'})` | — | label from verify/spike.py:118; id `'S'` must match the check's key `"S"` (checks/locked/cut/flow_oracle.py:14) |
| sink node | `(:FlowSink {id: 'T'})` | — | verify/spike.py:118; key `"T"` (checks/locked/cut/flow_oracle.py:27) |
| source pipe | `(:FlowSrc)-[:FLOW {cap: 1}]->(:Duty)`, one per **distinct** duty in the G-lane failures | 1 | checks/locked/cut/flow_oracle.py:9, :13-14 |
| take pipe | `(:Duty)-[:FLOW {cap: 1}]->(:Person)` if the person is active, not the leaver, and has a `CAN` record for the duty; **or** the duty is belief-only (not in world duties) and the person is on the leaver's team | 1 | checks/locked/cut/flow_oracle.py:11, :15-25 |
| drain pipe | `(:Person)-[:FLOW {cap: p.capacity}]->(:FlowSink)` for every active stayer | `capacity` (≥ 1 per checks/locked/cut/test_cut.py:26) | checks/locked/cut/flow_oracle.py:26-27 |

Node ids in `min_cut` must be the graph `id` values (`"S"`, duty ids, person ids, `"T"`), because the check looks each `(from, to)` pair up in its own capacity map (checks/locked/cut/test_cut.py:55-58).

What does not exist yet (PROPOSED, generator + loader work):
- `CAN` records in world.json `records` with at least `type`, `duty`, `person` (the fields the reference reads, checks/locked/cut/flow_oracle.py:16-17) and an `id` (every record gets one, baton/generate.py:428-429 at HEAD 85eeabd).
- `capacity` (int ≥ 1) on every person (checks/locked/cut/test_cut.py:26).
- Loading them: PROPOSED `(:Person)-[:CAN {rec: r.id}]->(:Duty)` edges and a `capacity` property on `Person` (baton/load.py:24-26 at HEAD 85eeabd creates Person today without it). Name and direction are PROPOSED; pick one and keep it. A `CAN` edge must not be added to any lane's path types (baton/rehearse.py:20-24), or the Rehearsal changes.
- Belief-only duties exist only on a fork where the gate and holds ran: `MERGE (d:Duty {id: b.duty}) ON CREATE SET ... d.from_belief = true` (baton/rehearse.py:46-50). Build the flow network on such a fork; `d.from_belief = true` is how to tell a belief-only duty in Cypher.

Cypher, version tested by the doc writer (rule "same team as leaver" for **every** duty, spare 1), on FalkorDB v4.22.1, Halden seed 7, 18 Oct, via the scratch script `/tmp/claude-0/-home-claude/9e986261-4c5d-5119-82fd-cce4a3dc1af5/scratchpad/m06check/halden_cut.py` (not product code, not a check). Result: 6 failing duties, `maxFlow 3.0` (float), demand 6, min-cut = the three drain pipes `arjun.haddad→T`, `felix.petrov→T`, `tomas.duarte→T`, certificate true, fork gone, live fingerprint unchanged. That script first ran `UNWIND $d AS did MERGE (:Duty {id: did})` because it skipped the gate and holds.
```
// 1 source + sink + source pipes   ($duties = distinct failing duty ids)   [TESTED 18 Oct]
CREATE (s:FlowSrc {id: 'S'}), (k:FlowSink {id: 'T'})
WITH s UNWIND $duties AS did
MATCH (d:Duty {id: did})
CREATE (s)-[:FLOW {cap: 1}]->(d)

// 2 take pipes, same-team rule   [TESTED 18 Oct]
MATCH (:FlowSrc)-[:FLOW]->(d:Duty)
MATCH (l:Person {id: $leaver}), (p:Person)
WHERE p.left_at IS NULL AND p.id <> $leaver AND p.team = l.team
CREATE (d)-[:FLOW {cap: 1}]->(p)

// 3 drain pipes   [TESTED 18 Oct with $spare = 1]
MATCH (k:FlowSink), (p:Person)
WHERE p.id <> $leaver AND (p)<-[:FLOW]-()
CREATE (p)-[:FLOW {cap: $spare}]->(k)
```
To match the locked checks, change (UNTESTED):
- take pipes for recorded duties: `MATCH (:FlowSrc)-[:FLOW]->(d:Duty)<-[:CAN]-(p:Person) WHERE p.left_at IS NULL AND p.id <> $leaver CREATE (d)-[:FLOW {cap: 1}]->(p)`;
- take pipes for belief-only duties: the same-team query above with `AND d.from_belief = true`;
- drain pipes: every active stayer, `cap: p.capacity`: `MATCH (k:FlowSink), (p:Person) WHERE p.left_at IS NULL AND p.id <> $leaver CREATE (p)-[:FLOW {cap: p.capacity}]->(k)`.
Test command: copy the scratch script, swap in these queries, run on a seed generated after the generator change, and compare with `flow_oracle.maxflow(flow_oracle.network(w, beliefs)[1])`.

---

## 3. CLI: `cut` (shape fixed by the locked checks, checks/locked/cut/test_cut.py)
```
python -m baton cut --world DIR --beliefs FILE --leaver ID --port P
```
- Flags: exactly these four (checks/locked/cut/test_cut.py:18-19, checks/locked/cut/test_cut.py:88). Meaning as in `rehearse` (baton/__main__.py:19-25).
- Exit codes: 0 success; non-zero with "falkordb" in the output when FalkorDB is down (checks/locked/cut/test_cut.py:85-89; today `Unreachable` exits 3, baton/graph.py:30-32); 1 unknown leaver (baton/rehearse.py:115-116); 2 argparse usage error.
- Stdout: one JSON object; the CLI prints `json.dumps(out, sort_keys=True)` (baton/__main__.py, end of `main`).

Output fields:
| field | type | meaning | asserted by |
|---|---|---|---|
| `demand` | int | number of distinct broken duties | checks/locked/cut/test_cut.py:35 |
| `flow` | number | max flow from `algo.maxFlow` (float `3.0` style on v4.22.1; `3.0 == 3` is true in Python) | checks/locked/cut/test_cut.py:36, checks/locked/cut/test_cut.py:59 |
| `verdict` | `"POSSIBLE"` or `"IMPOSSIBLE"` | `POSSIBLE` iff flow equals demand | checks/locked/cut/test_cut.py:37 |
| `min_cut` | list of `{from: str, to: str}` | min-cut edges as node ids; their capacities sum to `flow` | checks/locked/cut/test_cut.py:55-59 |
| `unplaceable` | list of duty ids | non-empty when IMPOSSIBLE; subset of the broken duties | checks/locked/cut/test_cut.py:60-62 |
| `n_minus_1` | object `{person_id: number}` | for every active stayer, max flow without that person | checks/locked/cut/test_cut.py:70-73 |
| `live_hash_before`, `live_hash_after` | str | equal | checks/locked/cut/test_cut.py:80 |
| `cypher` | str | must contain `algo.maxFlow` | checks/locked/cut/test_cut.py:82 |
| `leaver`, `graph`, `cap` per cut edge | — | PROPOSED extras (allowed; the checks ignore extra keys) | — |

Display string for the web and video (PROPOSED): `f"{verdict} {flow:g}/{demand}"`, e.g. `IMPOSSIBLE 3/4`.

How to get `unplaceable` (PROPOSED): duties whose `S → duty` pipe carries less than its capacity (flow 0 for unit pipes; a pipe missing from maxFlow's `edges` carries 0, maxflow.mdx:190). In the spike these were on the residual-reachable side, **not** in the min-cut (spike re-run 18 Oct: reachable `['Mei', 'Okta billing-admin', 'S']`).

---

## 4. CLI: `commit` (shape fixed by the drafted checks, checks/pending/commit_write/test_commit_write.py)
```
python -m baton commit --world DIR --beliefs FILE --leaver ID --repo REPO_DIR --port P --assign DUTY=PERSON [--assign ...]
```
Flags exactly as the check calls them (checks/pending/commit_write/test_commit_write.py:39-45). `--repo` is an existing git repository with at least one commit (the check makes one with `git init` + an empty commit, checks/pending/commit_write/test_commit_write.py:12-18).

Output fields:
| field | type | meaning | asserted by |
|---|---|---|---|
| `committed` | list of `{duty, person, ...}` | successors written to the **live** graph | checks/pending/commit_write/test_commit_write.py:52, :87, :92 |
| `refused` | list of `{duty, person, reason}` | second successor for a duty, departed person, ...; nothing refused reaches the repo | checks/pending/commit_write/test_commit_write.py:90-93 |
| `ready_to_leave` | bool | true iff no broken duty is left uncovered | checks/pending/commit_write/test_commit_write.py:53, :79 |
| `still_uncovered` | list of duty ids | broken duties still without a successor | checks/pending/commit_write/test_commit_write.py:53, :80 |
| `live_hash_before`, `live_hash_after` | str | must **differ** after a successful commit (the live graph changed) | checks/pending/commit_write/test_commit_write.py:54 |
| `external` | object | receipt from the git repository: `verified` (bool), `commit` (= new `git rev-parse HEAD`), `file` (path in the repo), `read_back` (list of `{duty, person}` parsed back from the committed file) | checks/pending/commit_write/test_commit_write.py:66-72 |

Behaviour the checks require:
- After a full commit, `rehearse --lane G` on the same world shows **no** failures (checks/pending/commit_write/test_commit_write.py:55-57). So the live-graph write must be something the G-lane cover query follows (its path types are `OWNER|ROUTES_TO|SHIFT|ESCALATES_TO|HOLDS`, baton/rehearse.py:23). The existing guarded `Q_ACCEPT` writes an `OWNER` edge with `active_key` (baton/handover.py:20-25) under a UNIQUE constraint on `OWNER.active_key` (baton/handover.py:33-46); reusing it on the live graph is the obvious route (PROPOSED).
- A second commit for a duty that already has a successor is refused, and so is a departed person (checks/pending/commit_write/test_commit_write.py:83-92). Note the constraint today is created **on the fork** (baton/handover.py:35-37); on the live graph it must be created once and survive (PROPOSED).
- The file content must contain the duty id and person id (checks/pending/commit_write/test_commit_write.py:69-71). Format and file name are free (PROPOSED: `CODEOWNERS`-style lines, or `oncall/rota.json`).
- If FalkorDB is down: non-zero exit, "falkordb" in the output, repo HEAD unchanged (checks/pending/commit_write/test_commit_write.py:96-103).
- The checks isolate graphs by giving each test world a unique `seed` string (checks/pending/commit_write/test_commit_write.py:28-30), so `halden_<seed>` differs per test.
- HTTP or git calls must use the standard library (`subprocess`, `urllib`) (.claude/skills/project-context/SKILL.md:9).
- Use `git -c user.name=... -c user.email=...` so commits work without a global git config (the check itself does this, checks/pending/commit_write/test_commit_write.py:16).

### Gitea target (PROPOSED extension; no checks; owner: Joyal)
Two ways, pick one:
- (a) `--repo` is a local clone of the Gitea repo; after the local commit, `git push` it. Simple; uses only git.
- (b) A REST target: write the same file with the endpoints below and read it back. Receipt rule: `commit` = `FileResponse.commit.sha`; `verified` = sha256 of decoded read-back bytes equals what was sent and read-back `last_commit_sha` equals `commit`.
Write rule for (b): `GET` the file; 404 → `POST` (create); 200 → `PUT` with its `sha`. PROPOSED env names: `GITEA_URL`, `GITEA_USER`, `GITEA_PASSWORD` (never print the password).

### Gitea REST endpoints (checked 18 Oct 2026 against docs.gitea.com; never run by us → UNTESTED)
Base URL: `<GITEA_URL>/api/v1` (the docs' example URL is `https://gitea.com/api/v1/user/repos`). Auth: HTTP Basic is one of the listed schemes (docs.gitea.com/api/operations/user-create-token/).

| Purpose | Method and path | Body (fields we use) | Success | Source |
|---|---|---|---|---|
| create repo | `POST /user/repos` | `name` (required), `auto_init`, `default_branch`, `private` | 201; 409 if it exists | docs.gitea.com/api/operations/create-current-user-repo/ |
| create file | `POST /repos/{owner}/{repo}/contents/{filepath}` | `content` (required, "Content must be base64 encoded"), `message`, `branch` | 201 `FileResponse` | docs.gitea.com/api/operations/repo-create-file/ |
| update file | `PUT /repos/{owner}/{repo}/contents/{filepath}` | `content` (required, base64), `sha` ("The blob ID (SHA) for the file that already exists to update, or leave it empty to create a new file"), `message`, `branch` | 200 or 201 `FileResponse` | docs.gitea.com/api/operations/repo-update-file/ |
| read back | `GET /repos/{owner}/{repo}/contents/{filepath}?ref=<branch>` | — | 200 `ContentsResponse`: `content`, `encoding`, `sha`, `last_commit_sha`, `path`, … ; 404 if missing | docs.gitea.com/api/operations/repo-get-contents/ |
| (optional) token | `POST /users/{username}/tokens` | `name` (required), `scopes` | 201 `AccessToken` (`sha1`, `token_last_eight`, …) | docs.gitea.com/api/operations/user-create-token/ |

`FileResponse` has top-level `commit`, `content`, `verification`; `commit.sha` and `content.sha` exist (docs.gitea.com/api/operations/repo-create-file/). Read-back `content` is base64; decode with `base64.b64decode` (it skips non-alphabet characters such as newlines by default).

### Gitea server (PROPOSED compose service; UNTESTED)
From the official docs (docs.gitea.com/installation/install-with-docker, docs.gitea.com/administration/config-cheat-sheet, checked 18 Oct):
- Image in the docs' compose example: `docker.gitea.com/gitea:28.1.0`. The task brief said `gitea/gitea`; that Docker Hub name was not checked. Run `docker pull <image:tag>` before pinning.
- Web port inside the container: 3000 (`HTTP_PORT` default 3000). Data volume: `/data`.
- Env vars map to `app.ini` as `GITEA__<section>__<KEY>`.
- `[database] DB_TYPE` defaults to `mysql`; allowed values include `sqlite3` → set `GITEA__database__DB_TYPE=sqlite3`.
- `[security] INSTALL_LOCK` default `false`; "When set to true, the installation page is not accessible" → set `GITEA__security__INSTALL_LOCK=true`. The install page itself does not say this skips setup; UNTESTED.
- `[repository] DEFAULT_BRANCH` default `main`.
- Admin user: `gitea admin user create --username <u> --password <p> --email <e> --admin --must-change-password=false` (docs.gitea.com/administration/command-line). Running it inside the container as user `git` (`docker compose exec -u git gitea ...`) is not in the docs; UNTESTED.
- Host port clash: `falkordb` already maps `127.0.0.1:3000` (docker-compose.yml:4). Map Gitea to another host port, e.g. `127.0.0.1:3001:3000`.

### Git in the container
The git path is the **checked** contract, not just a fallback. The API image is `python:3.12-slim` (deploy/Dockerfile:1) and installs only Python packages (deploy/Dockerfile:4); git is probably not in it. Check with `docker compose exec api git --version`; if missing, add it to the image (human edit) or run `commit` on the host.
