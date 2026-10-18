# 00 · Ground truth (read this before any module doc)

Every module doc in this pack must agree with this file. If a doc and this file disagree, this file wins.
If something is not in this file, in the repo, or in a cited test, **it is not a fact**. Mark it `UNVERIFIED`.

## A. The event (checked 18 Oct 2026 on wemakedevs.org/hackathons/falkordb and /rules)
- Graph Hacks: Context for AI Agents (WeMakeDevs × FalkorDB). Submissions close **18 Oct 2026, 23:59 IST**. Our internal submit time is **21:00 IST**.
- Track 3 "Company Brain": "Build an agent that understands how a company works. Connect people, teams, projects, documents, and decisions in one graph, so the agent can answer questions and get work done across all of it." Focus: knowledge from docs, tickets and chats in one graph; who owns what and who knows what; tracing decisions back to their source; keeping knowledge current as things change; answers with clear sources. Prize: M6 Mac Mini.
- Track 1 "Agents That Act on Connected Data": multi-hop reasoning, graph queries and algorithms as agent tools, tool selection through MCP, actions based on what the graph shows, explainable results.
- Multiple tracks are allowed: "You may enter any or all of them, and you must name every track you are entering when you submit." **We enter Track 3 and Track 1.**
- Rule 2/3: FalkorDB must be the primary graph DB and support a central part of the product. "If the product still works once FalkorDB is taken out, the graph is decoration."
- Rule 6: data must be public, synthetic or our own. Ours: synthetic company "Halden" (label: FIXTURE).
- Rule 10: public repo; README with setup, the graph data model, and "the Cypher queries or graph algorithms the product depends on"; demo video; live deployment preferred (otherwise full local setup + video); name the tracks.
- Rules 11–13: AI coding assistants allowed but must be disclosed. Projects entirely AI-generated without meaningful participant contribution may be rejected. Participants must be able to explain the graph model, queries, architecture and decisions.
- Judging criteria, weights and judges: **not published**. Do not claim them.

## B. FalkorDB facts (tested by us on the C engine v4.22.1 unless marked)
- Pin `falkordb/falkordb:v4.22.1`. `:latest` will move to the Rust 6.x engine. Do **not** claim MVCC.
- Tested and working (files in the scratchpad `verify/` folder):
  - `GRAPH.COPY src dst`. Fails if dst exists, so delete it first. (`spike.py`, `forecast_spike.py`, `hero_check.py`)
  - `CALL algo.maxFlow({sourceNodes:[s], targetNodes:[k], relationshipTypes:['FLOW'], capacityProperty:'cap'}) YIELD maxFlow, edges, edgeFlows`. Takes one relationship type and no multi-edges. Returns only edges that carry flow and **no min-cut**: compute the cut yourself with a residual BFS. Float capacities work. (`spike.py` lines 113–166)
  - `GRAPH.CONSTRAINT CREATE <g> UNIQUE RELATIONSHIP ACCOUNTABLE_FOR PROPERTIES 1 active_key` needs `CREATE INDEX FOR ()-[a:ACCOUNTABLE_FOR]-() ON (a.active_key)` first. (`spike.py` line 34)
  - A single-query commit with an authority re-check inside the write query. (`spike.py`)
  - A variable-length path with per-edge time validity:
    `OPTIONAL MATCH path=(d)-[:A|B|C*1..4]->(who:Person) WHERE all(r IN relationships(path) WHERE r.vf <= $t AND r.vt > $t)`. (`hero_check.py`, `native_spike.py`)
  - A read-only ACL user: `ACL SETUSER agent on >pw +GRAPH.RO_QUERY +GRAPH.EXPLAIN +GRAPH.LIST +INFO +PING ~halden_*`. The documented `%R~` form breaks RO_QUERY. (`acl_check.py`)
- Not supported in v4.22: `datetime()`, `EXISTS{}`, `COUNT{}`, label alternation, `shortestPath` inside MATCH. A var-length relationship alias is an Edge: use `relationships(p)`.
- Times are epoch-ms integers. "Open" end = `253402300799000`.
- falkordblite 0.10.0 bundles v4.18.3, which has **no maxFlow**. Do not use it for M6.

## C. The product contract (the locked checks are the law)
- Locked checks: `checks/locked/rehearsal_core/` (17 checks, 32 runs). Independent reference: `checks/locked/rehearsal_core/oracle.py`.
- Drafted (not locked) checks: `checks/pending/ask/`.
- CLI contract and semantics: `.claude/skills/project-context/SKILL.md`.
- API contract: `server/app.py`. Web contract: the brief in the M10 docs and the `web/` folder.
- Loop rules: `loop/program.md`. Feature charter: `loop/features.md`. Round history: `loop/results.tsv`.

## D. Reused open source (licences checked locally 18 Oct)
| Project | Licence | Use |
|---|---|---|
| agent-memory-bench (Liz Zhang, FalkorDB DevRel) | MIT, "Copyright (c) 2026 Liz Zhang" | Adapt `amb/extract.py` and `amb/llm.py` patterns for M5 and the bootstrap CI for M7, keeping the MIT notice and crediting her in the README |
| falkordb-py | MIT | Client |
| FalkorDB-MCPServer | MIT | Reference only for M8 (we use the official `mcp` Python SDK) |
| GraphRAG-SDK | Apache-2.0 | Not used |
| falkordb-browser | SSPL | Run the container only; never copy code |
| QueryWeaver | AGPL | Do not use |

Never copy code from another hackathon entry (orion, lineage, keystone, threadline, tombstone, cairn, strata, …).

## E. Words we never write
"predicts failures", "autopilot", "production-ready", "replaces Okta", MVCC, "credentials are the #1 breach vector", unlabelled vendor statistics, any claim about rival entries, "guaranteed".

## F. Status at pack time (11:35 IST)
- M1 generator: done (round 1 kept, 9/32).
- M2 engine: round 2 in progress.
- Web: in progress.
- Everything else: not started.

**Docs describe the target and the contract. They are not proof that something works. Only a passing check or a recorded run is proof.**
