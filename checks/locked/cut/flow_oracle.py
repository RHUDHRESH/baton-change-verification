"""Independent max-flow reference (locked). Plain Edmonds-Karp.
Network: S -> each duty that fails when the leaver goes (capacity 1) -> each active stayer who CAN take it (capacity 1:
a CAN record, or, for a duty known only from beliefs, being on the leaver's team) -> T (capacity = person.capacity)."""
from collections import deque
import oracle


def network(world, beliefs):
    duties = sorted({d for d, _ in oracle.expected_failures(world, beliefs, "G")})
    people = {p["id"]: p for p in world["people"]}
    ok = {pid for pid, p in people.items() if p["left_at"] is None and pid != world["leaver"]}
    cap = {}
    for d in duties:
        cap[("S", d)] = 1
    for r in world["records"]:
        if r["type"] == "CAN" and r["duty"] in duties and r["person"] in ok:
            cap[(r["duty"], r["person"])] = 1
    # duties known only from beliefs (e.g. a promise found in chat) can be taken by anyone on the leaver's team
    recorded = {x["id"] for x in world["duties"]}
    team = people[world["leaver"]].get("team")
    for d in duties:
        if d not in recorded:
            for pid in ok:
                if people[pid].get("team") == team:
                    cap[(d, pid)] = 1
    for pid in ok:
        cap[(pid, "T")] = people[pid].get("capacity", 1)
    return duties, cap


def maxflow(cap, s="S", t="T"):
    res = dict(cap)
    for (u, v) in list(cap):
        res.setdefault((v, u), 0)
    adj = {}
    for (u, v) in res:
        adj.setdefault(u, []).append(v)
    flow = 0
    while True:
        prev = {s: None}
        q = deque([s])
        while q and t not in prev:
            u = q.popleft()
            for v in adj.get(u, []):
                if v not in prev and res[(u, v)] > 0:
                    prev[v] = u
                    q.append(v)
        if t not in prev:
            return flow
        v, aug = t, float("inf")
        while prev[v] is not None:
            aug = min(aug, res[(prev[v], v)]); v = prev[v]
        v = t
        while prev[v] is not None:
            res[(prev[v], v)] -= aug; res[(v, prev[v])] += aug; v = prev[v]
        flow += aug


def without(cap, person):
    return {k: v for k, v in cap.items() if person not in k}
