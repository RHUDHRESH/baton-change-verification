"""`python -m baton cut`: can the people who stay absorb everything the leaver held?

On a GRAPH.COPY fork (beliefs gated, promoted ones written as HOLDS, the leaver departed: exactly what `rehearse`
does) Baton takes the G-lane failures and builds a flow network in the fork, one relationship type only:

  (:FlowNode {name: 'S'}) -[:FLOW {cap: 1}]-> (:FlowNode {duty id})       every duty that breaks when they leave
  (duty)  -[:FLOW {cap: 1}]-> (:FlowNode {person id})                      a stayer who CAN take it (CAN edge), or,
                                                                           for a duty known only from beliefs, a
                                                                           stayer on the leaver's team
  (person)-[:FLOW {cap: person.capacity}]-> (:FlowNode {name: 'T'})        how much more each stayer can absorb

FalkorDB's algo.maxFlow gives the flow (POSSIBLE when it equals the demand). It gives no min cut, so the cut is read
off the residual graph (BFS from S over edges with spare capacity or reverse flow); by max-flow/min-cut duality its
capacity equals the flow, which is the certificate: those edges are why no more can be placed. The N-1 sweep re-runs
maxFlow with each stayer's edge to T at capacity 0 (what if they are also unavailable). The fork is always dropped.
"""
from collections import defaultdict, deque

from . import rehearse

Q_SOURCE_SINK = "CREATE (:FlowNode {name: 'S', kind: 'source'}), (:FlowNode {name: 'T', kind: 'sink'})"

Q_DUTIES = """
MATCH (s:FlowNode {name: 'S'})
UNWIND $duties AS did
MATCH (d:Duty {id: did})
CREATE (s)-[:FLOW {cap: 1}]->(:FlowNode {name: d.id, kind: 'duty'})"""

Q_STAYERS = """
MATCH (t:FlowNode {name: 'T'}), (p:Person)
WHERE p.left_at IS NULL AND p.id <> $leaver
CREATE (:FlowNode {name: p.id, kind: 'person'})-[:FLOW {cap: coalesce(p.capacity, 1)}]->(t)"""

Q_CAN = """
MATCH (dn:FlowNode {kind: 'duty'}), (d:Duty {id: dn.name})<-[:CAN]-(p:Person), (pn:FlowNode {kind: 'person'})
WHERE pn.name = p.id
MERGE (dn)-[f:FLOW]->(pn) ON CREATE SET f.cap = 1"""

Q_TEAM = """
MATCH (l:Person {id: $leaver})
MATCH (dn:FlowNode {kind: 'duty'}), (d:Duty {id: dn.name})
WHERE d.from_belief = true
MATCH (p:Person), (pn:FlowNode {kind: 'person'})
WHERE pn.name = p.id AND p.team = l.team
MERGE (dn)-[f:FLOW]->(pn) ON CREATE SET f.cap = 1"""

Q_MAXFLOW = """
MATCH (s:FlowNode {name: 'S'}), (t:FlowNode {name: 'T'})
CALL algo.maxFlow({sourceNodes: [s], targetNodes: [t], relationshipTypes: ['FLOW'], capacityProperty: 'cap'})
YIELD maxFlow, edges, edgeFlows
RETURN maxFlow, [i IN range(0, size(edges) - 1) | [id(edges[i]), edgeFlows[i]]]"""

Q_EDGES = "MATCH (u:FlowNode)-[e:FLOW]->(v:FlowNode) RETURN id(e), id(u), id(v), u.name, v.name, e.cap"

Q_SET_SINK_CAP = """
MATCH (p:FlowNode {kind: 'person', name: $person})-[e:FLOW]->(:FlowNode {name: 'T'})
SET e.cap = $cap"""


def _num(x):
    return int(x) if float(x).is_integer() else x


def solve(fork):
    """algo.maxFlow on the fork. Returns (flow, {edge id: flow}, edges)."""
    mf, pairs = fork.ro_query(Q_MAXFLOW).result_set[0]
    flows = {eid: f for eid, f in pairs}
    edges = fork.ro_query(Q_EDGES).result_set
    return _num(mf or 0), flows, edges


def min_cut(flows, edges):
    """Residual BFS from S; the cut is every edge from the reached side to the rest."""
    adj, src = defaultdict(list), None
    for eid, u, v, un, vn, cap in edges:
        x = flows.get(eid, 0)
        if cap - x > 1e-9:
            adj[u].append(v)
        if x > 1e-9:
            adj[v].append(u)
        if un == "S":
            src = u
    if src is None:
        return []
    seen, q = {src}, deque([src])
    while q:
        n = q.popleft()
        for m in adj[n]:
            if m not in seen:
                seen.add(m)
                q.append(m)
    return sorted(({"from": un, "to": vn, "cap": _num(cap)} for eid, u, v, un, vn, cap in edges
                   if u in seen and v not in seen), key=lambda e: (e["from"], e["to"]))


def network(fork, duties, leaver):
    fork.query(Q_SOURCE_SINK)
    fork.query(Q_DUTIES, {"duties": duties})
    fork.query(Q_STAYERS, {"leaver": leaver})
    fork.query(Q_CAN)
    fork.query(Q_TEAM, {"leaver": leaver})


def run(world_dir, beliefs_file, leaver, port):
    s = rehearse.open_session(world_dir, beliefs_file, leaver, port, cmd="cut")

    def flow_on_fork(fork, present, gone):
        duties = sorted({f["duty"] for f in rehearse.failures(s, present, gone)})
        network(fork, duties, leaver)
        flow, flows, edges = solve(fork)
        cut = min_cut(flows, edges)
        into = defaultdict(float)
        for eid, u, v, un, vn, cap in edges:
            if un == "S":
                into[vn] += flows.get(eid, 0)
        caps = {un: cap for eid, u, v, un, vn, cap in edges if vn == "T"}  # every active stayer has one
        sweep = {}
        for pid in sorted(caps):
            fork.query(Q_SET_SINK_CAP, {"person": pid, "cap": 0})
            sweep[pid] = solve(fork)[0]
            fork.query(Q_SET_SINK_CAP, {"person": pid, "cap": caps[pid]})
        return {"duties": duties, "flow": flow, "min_cut": cut, "n_minus_1": sweep,
                "unplaceable": sorted(d for d in duties if into[d] < 1e-9) if flow < len(duties) else [],
                "edges": len(edges)}

    r = rehearse.on_fork(s, "G", "none", after_departure=flow_on_fork)
    a = r["after"]
    demand = len(a["duties"])
    cut_cap = sum(e["cap"] for e in a["min_cut"])
    return {"leaver": leaver, "graph": s["live"].name, "verdict": "POSSIBLE" if a["flow"] == demand else "IMPOSSIBLE",
            "demand": demand, "flow": a["flow"], "duties": a["duties"], "min_cut": a["min_cut"],
            "certificate": {"cut_capacity": cut_cap, "equals_flow": cut_cap == a["flow"]},
            "unplaceable": a["unplaceable"], "n_minus_1": a["n_minus_1"], "flow_edges": a["edges"],
            "cypher": Q_MAXFLOW.strip(), "live_hash_before": r["live_hash_before"],
            "live_hash_after": r["live_hash_after"]}
