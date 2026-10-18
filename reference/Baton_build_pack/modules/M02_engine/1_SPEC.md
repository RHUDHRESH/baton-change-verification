# M02 · Engine (`baton/graph.py`, `baton/load.py`, `baton/rehearse.py`) · SPEC

Written 11:45 IST, 18 Oct. Status: **done**. Round 2 was kept at 28/32 (loop/results.tsv:4). Round 3 built M03 on top of it and reached 32/32 (loop/results.tsv:5). The feature `rehearsal-core` is marked `accepted` (loop/features.md:8). The code was not changed after round 3.

## What it is, in plain words
1. **Load.** Turn world.json into a graph in FalkorDB called `halden_<seed>`. People, duties, rotas, events and every piece of evidence become nodes. Ownership, rota routing, shifts and escalation become edges, and each edge has a "valid from / valid to" time (baton/load.py:1-12). If the graph already exists, leave it alone, because from then on the graph is the truth, not the file (baton/load.py:3, baton/load.py:96-97).
2. **Rehearse.** Make a full copy of the graph (a "fork") with `GRAPH.COPY`. On the fork:
   - Write the AI's beliefs and let one Cypher query decide which of them have enough evidence (the "gate").
   - Turn the accepted beliefs into `HOLDS` edges.
   - For every scheduled event in the next 30 days, ask: "is there a path of at most 4 hops, every edge valid at that moment, to a person who is still active then?"
   - Mark the leaver as gone and ask the same question again.

   Every event that was covered before and is not covered after is a **failure**, and it carries the sources that proved who was covering it. Then delete the fork. The live graph is only read (baton/rehearse.py:1-10).

A 14-year-old version: *"We copy the company's map, rub out one person, and check every appointment for the next month. If an appointment now has no road to anyone who can turn up, we list it, with the receipts."*

## Which focus points it serves
- Track 3: "who owns what", "tracing decisions back to their source", "keeping knowledge current as things change", "answers with clear sources" (docs/modules/00_GROUND_TRUTH.md:8). Every failure lists the record or evidence ids it rests on (baton/rehearse.py:74-75). Edit the graph and the answer changes (checks/locked/rehearsal_core/test_rehearsal_core.py:236-246).
- Track 1: "multi-hop reasoning, graph queries … as agent tools, … explainable results" (docs/modules/00_GROUND_TRUTH.md:9). The cover query is a variable-length path of up to 4 hops with a time check on every edge (baton/rehearse.py:66-68).
- Rules 2/3: FalkorDB is central. If you take it out, nothing gets decided. Without it the CLI exits with code 3 (baton/graph.py:30-32; checks/locked/rehearsal_core/test_rehearsal_core.py:195-202).

## In scope
- `python -m baton load` and `python -m baton rehearse` (baton/__main__.py:15-25, baton/__main__.py:57-62).
- The shared pieces used by M03 and later modules: `open_session`, `on_fork`, `failures` (baton/rehearse.py:108-148), and in graph.py `connect`, `fingerprint`, `fork` (baton/graph.py:18-53).
- Three lanes (baton/rehearse.py:20-24):
  - **W**: owner field only, 1 hop, and only duties the leaver owns.
  - **R**: all record edges.
  - **G**: records plus beliefs that passed the gate.

## Not in scope
- Handover and demo (M03).
- `ask` (M4, checks locked at 11:40, `checks/locked/ask/`).
- Producing beliefs with an LLM (`extract`, M5). `algo.maxFlow` / the cut (M6). The MCP server.
- Writing anything to the live graph after the first load.

## Inputs and outputs
- `load`: in, a folder holding world.json; out, `{graph, created, nodes, edges}` (baton/load.py:112-118).
- `rehearse`: in, a world folder, a beliefs file (a JSON list), the leaver id, the lane, the confirm mode and the port. Out: `{lane, leaver, graph, failures[], unpromoted[], live_hash_before, live_hash_after}` (baton/rehearse.py:151-156). Field details are in 2_CONTRACT.md.

## Dependencies
- Upstream: M01 world.json (baton/load.py:66-67). The `falkordb` Python client (baton/graph.py:20), plus `redis.exceptions` in M03 (baton/handover.py:15). FalkorDB v4.22.1 pinned (docker-compose.yml:3).
- Downstream: M03 handover and demo (baton/handover.py:18, baton/demo.py:12). The API calls `rehearse` three times for `/api/demo` (server/app.py:68-71).

## Owner, time, kill
- Owner: the build loop (round 2 builder). The checks were approved by Rhudhresh before any code (loop/reports/rehearsal_core.md, "Integrity").
- Time: planned "now–13:30 rehearsal_core green" (docs/BUILD_PLAN.md:66). It actually went green at about 12:05 (loop/reports/rehearsal_core.md).
- Kill time and fallback (no longer needed): "14:30 not green → hero = Cut + reason-broken query" (docs/BUILD_PLAN.md:66).
- From now on: changes only through a new locked check and a loop round. Nothing new after 15:30 (docs/BUILD_PLAN.md:72), and the freeze is at 16:00 (docs/BUILD_PLAN.md:73).
