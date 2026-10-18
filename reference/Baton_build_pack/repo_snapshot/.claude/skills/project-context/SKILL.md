---
name: project-context
description: Baton project facts every builder needs (entrypoints, FalkorDB quirks, schemas, traps).
---
# Baton project context

**What it is:** Track 3 (Company Brain) entry for Graph Hacks (FalkorDB). "Every company brain knows who knows what. Baton knows who owes what, and the day it breaks if they leave."

**Python:** `/tmp/claude-0/-home-claude/9e986261-4c5d-5119-82fd-cce4a3dc1af5/scratchpad/venv/bin/python` (has `falkordb` 1.8 client, redis, pytest). Package lives in `baton/` and runs as `python -m baton <cmd>`. Standard library + falkordb only; no other deps.

**FalkorDB for manual runs:** `B=/tmp/claude-0/-home-claude/9e986261-4c5d-5119-82fd-cce4a3dc1af5/scratchpad/venv/lib/python3.13/site-packages/redislite/bin; $B/redis-server --port 6399 --daemonize yes --dir /tmp --loadmodule /tmp/claude-0/-home-claude/9e986261-4c5d-5119-82fd-cce4a3dc1af5/scratchpad/fdb422/falkordb.so --save ''` ; stop with `$B/redis-cli -p 6399 shutdown nosave`. Engine is FalkorDB v4.22.1 (C engine). Checks start their own server.

**Entrypoints (contract fixed by checks/locked/rehearsal_core):**
- `generate --seed N --out DIR` -> DIR/world.json + DIR/answer_key.json (deterministic, sort keys, no timestamps from the clock).
- `load --world DIR --port P` -> graph `halden_<seed>`; if it already exists, leave it as is (the graph is the source of truth; never reload over it).
- `rehearse --world DIR --beliefs FILE --leaver ID --lane W|R|G --confirm all|none --port P` -> JSON {lane, leaver, failures:[{duty, at, day, status, sources, event}], unpromoted:[{belief, reason}], live_hash_before, live_hash_after}. Loads if graph missing. Must GRAPH.COPY to a fork whose name contains "fork", do all reasoning by Cypher on the fork, delete the fork.
- `handover --world DIR --beliefs FILE --leaver ID --assign DUTY=PERSON ... --port P` -> {accepted, refused:[{duty, person, reason}], failures_after}.
- `demo --seed N --port P --offline` -> {leaver, lanes:{W:{failures:int},R:{...},G:{...}}, live_hash_before, live_hash_after, after_handover:{failures:int}}.
- Any FalkorDB connection error: exit non-zero, message containing "FalkorDB", nothing on stdout.

**Semantics:** read `checks/locked/rehearsal_core/oracle.py` to understand the rules (you may read it, never import it or copy its code into the product; the product must do the reasoning as Cypher in FalkorDB). Lanes: W = owner-field-only template (depth 1, duties whose OWNER is the leaver); R = all record edges, paths duty-[OWNER|ROUTES_TO]->...-[SHIFT valid at t]->person-[ESCALATES_TO*]->person, max 4 hops, endpoint person active at t; G = R + promoted beliefs as HOLDS edges. A failure = an event in [now, now+30d) covered in the live graph but not in the fork where leaver.left_at = leave_at. Gate: >=2 cited sources, all exist, >=2 distinct source types (message / joblog / ticket / record). status: "record" if covered by records, else "confirmed"/"believed" per --confirm.

**FalkorDB v4.22 traps:** no `datetime()`, no `EXISTS{}`/`COUNT{}` subqueries, no label alternation, no shortestPath in MATCH. A var-length rel alias is an Edge, use `relationships(p)`. GRAPH.COPY fails if the destination exists (delete first). UNIQUE constraint on a relationship property needs an index first. Times are epoch-ms integers; "open" = 253402300799000. Tested working pattern:
```
OPTIONAL MATCH path = (d)-[:HOLDS|ROUTES_TO|SHIFT|ESCALATES_TO*1..4]->(who:Person)
WHERE all(r IN relationships(path) WHERE r.vf <= $t AND r.vt > $t) AND (who.left_at IS NULL OR who.left_at > $t)
```

**Data rules:** synthetic only (label FIXTURE). Never read answer_key.json outside generate.py; never mention "oracle" in product code.
