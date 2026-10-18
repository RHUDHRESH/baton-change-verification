"""`python -m baton rehearse`: fork the company graph, let the leaver go on the fork, list what nobody can act on.

Everything that decides an answer is a Cypher query on the fork:
  1. gate     - beliefs become (:Belief)-[:CITES]->(:Source) for refs that exist; a query promotes the ones with
                no missing refs and >= 2 sources of >= 2 kinds that are about the belief (a record or job log counts
                only if its duty is the belief's duty or one of its people is the belief's person; messages and
                tickets always count)
  2. holds    - promoted beliefs become (:Duty)-[:HOLDS]->(:Person) edges (and their own scheduled events)
  3. cover    - for each event in the 30-day window: is there a path of <= 4 hops, every edge valid at the event's
                time, ending at a person still active then?  Run once as-is, once after SET leaver.left_at.
A failure is an event covered in the first pass and not in the second. The live graph is only read (its
fingerprint before and after) and the fork is always dropped.
"""
import json
import os
from pathlib import Path

from . import graph as G
from . import load

# lane -> (relationship types a path may use, max hops, extra scope clause)
LANES = {
    "W": ("OWNER", 1, "MATCH (d)-[:OWNER]->(:Person {id: $leaver})"),  # owner-field template, leaver's duties only
    "R": ("OWNER|ROUTES_TO|SHIFT|ESCALATES_TO", 4, ""),                # every record edge
    "G": ("OWNER|ROUTES_TO|SHIFT|ESCALATES_TO|HOLDS", 4, ""),          # records + promoted beliefs
}

Q_BELIEFS = """
UNWIND $beliefs AS b
CREATE (x:Belief {id: b.id, person: b.person, duty: b.duty, duty_name: b.duty_name, kind: b.kind,
                  claim: b.claim, refs: b.sources,
                  ev_at: [e IN b.events | e.at], ev_label: [e IN b.events | e.label]})
WITH x, b
UNWIND b.sources AS ref
MATCH (s:Source {id: ref})
CREATE (x)-[:CITES]->(s)"""

Q_GATE = """
MATCH (b:Belief)
OPTIONAL MATCH (b)-[:CITES]->(s:Source)
WITH b, s, coalesce(s IS NOT NULL AND (s.people IS NULL OR s.duty = b.duty OR b.person IN s.people), false) AS about
WITH b, collect(DISTINCT s.id) AS hit,
     collect(DISTINCT CASE WHEN about THEN s.id END) AS counted,
     collect(DISTINCT CASE WHEN about THEN s.type END) AS kinds,
     collect(DISTINCT CASE WHEN s IS NOT NULL AND NOT about THEN [s.id, s.type] END) AS off
WITH b, size(counted) AS n, size(kinds) AS k, off, [r IN b.refs WHERE NOT r IN hit] AS missing
WITH b, n, k, off, missing, size(missing) = 0 AND n >= 2 AND k >= 2 AS ok
SET b.promoted = ok
RETURN b.id, ok, size(b.refs), n, k, missing, off
ORDER BY b.id"""

Q_HOLDS = """
MATCH (b:Belief {promoted: true}), (p:Person {id: b.person})
MERGE (d:Duty {id: b.duty})
  ON CREATE SET d.name = b.duty_name, d.kind = b.kind, d.from_belief = true
CREATE (d)-[:HOLDS {vf: 0, vt: $open, basis: $basis, srcs: b.refs, belief: b.id}]->(p)
WITH b, d
UNWIND range(0, size(b.ev_at) - 1) AS i
CREATE (:Event {id: b.id + '-ev' + toString(i + 1), duty: d.id, at: b.ev_at[i], label: b.ev_label[i],
                from_belief: true})-[:NEEDS]->(d)"""

Q_DEPART = "MATCH (p:Person {id: $leaver}) SET p.left_at = $leave_at"

Q_COVER = """
MATCH (c:Company)
MATCH (e:Event)-[:NEEDS]->(d:Duty)
WHERE e.at >= c.now AND e.at < c.now + c.window_days * c.day_ms
  AND ($with_beliefs OR e.from_belief IS NULL)
{scope}
WITH d, e ORDER BY e.id
WITH d, e.at AS t, collect(e)[0] AS e
OPTIONAL MATCH path = (d)-[:{types}*1..{hops}]->(who:Person)
WHERE all(r IN relationships(path) WHERE r.vf <= t AND r.vt > t)
  AND (who.left_at IS NULL OR who.left_at > t)
WITH d, t, e, collect(path) AS paths
RETURN d.id AS duty, t AS at, e.id AS event, e.label AS label, size(paths) > 0 AS covered,
       CASE WHEN any(p IN paths WHERE none(r IN relationships(p) WHERE type(r) = 'HOLDS')) THEN 'record'
            ELSE head(reduce(acc = [], p IN paths |
                   acc + [r IN relationships(p) WHERE type(r) = 'HOLDS' | r.basis])) END AS status,
       reduce(acc = [], p IN paths | acc + reduce(src = [], r IN relationships(p) |
              src + CASE WHEN type(r) = 'HOLDS' THEN r.srcs ELSE [r.rec] END)) AS sources"""


_OFF_TOPIC = {"record": "another duty and person", "joblog": "another job and actor"}


def _reason(n_refs, n_counted, kinds, missing, off):
    if missing:
        return f"cites source(s) that do not exist: {', '.join(missing)}"
    if n_refs < 2:
        return f"only {n_refs} source cited; needs at least 2"
    not_counted = "".join(f"; {sid} is about {_OFF_TOPIC[t]}, so it does not count" for sid, t in sorted(off))
    if n_counted < 2:
        return f"only {n_counted} of {n_refs} cited sources are about this belief; needs at least 2{not_counted}"
    return (f"all {n_counted} counted sources are of {kinds} kind; needs at least 2 kinds "
            f"(message, joblog, ticket, record){not_counted}")


def gate(fork, beliefs):
    """Write beliefs onto the fork and let Cypher decide promotion. Returns the unpromoted rows."""
    rows = [{"id": b["id"], "person": b.get("person"), "duty": b.get("duty"), "duty_name": b.get("duty_name"),
             "kind": b.get("kind"), "claim": b.get("claim"), "sources": list(b.get("sources", [])),
             "events": [{"at": e["at"], "label": e.get("label")} for e in b.get("events", [])]} for b in beliefs]
    if rows:
        fork.query(Q_BELIEFS, {"beliefs": rows})
    res = fork.query(Q_GATE).result_set
    return [{"belief": bid, "reason": _reason(n, counted, kinds, missing, off)}
            for bid, ok, n, counted, kinds, missing, off in res if not ok]


def cover_query(lane):
    """The exact cover-pass Cypher for a lane (also published in `ask --catalogue`)."""
    types, hops, scope = LANES[lane]
    return Q_COVER.replace("{scope}", scope).replace("{types}", types).replace("{hops}", str(hops))


def cover(fork, lane, leaver):
    res = fork.ro_query(cover_query(lane), {"leaver": leaver, "with_beliefs": lane == "G"}).result_set
    return {(r[0], r[1]): r for r in res}


def open_session(world_dir, beliefs_file, leaver, port, cmd="rehearse"):
    """Connect, make sure the live graph exists, and read the company clock from it (the graph is the truth)."""
    w = load.read_world(world_dir)
    beliefs = json.loads(Path(beliefs_file).read_text())
    db = G.connect(port)
    live, _ = load.ensure(db, w)
    now, day_ms, leave_at = live.ro_query("MATCH (c:Company) RETURN c.now, c.day_ms, c.leave_at").result_set[0]
    if not live.ro_query("MATCH (p:Person {id: $id}) RETURN count(p)", {"id": leaver}).result_set[0][0]:
        raise SystemExit(f"baton {cmd}: no person '{leaver}' in graph {live.name}")
    return {"db": db, "live": live, "beliefs": beliefs, "leaver": leaver, "now": now, "day_ms": day_ms,
            "leave_at": leave_at}


def on_fork(s, lane, confirm, before_departure=None, after_departure=None):
    """Fork the live graph and run gate -> holds -> present pass -> [before_departure(fork)] -> depart -> departed
    pass -> [after_departure(fork, present, gone)]. The fork is always dropped; the live graph is only fingerprinted.
    Returns the pieces for the caller."""
    live = s["live"]
    hash_before = G.fingerprint(live)
    fork = G.fork(s["db"], live.name, os.getpid())
    try:
        unpromoted = gate(fork, s["beliefs"])
        fork.query(Q_HOLDS, {"open": G.OPEN, "basis": "confirmed" if confirm == "all" else "believed"})
        present = cover(fork, lane, s["leaver"])
        extra = before_departure(fork) if before_departure else None
        fork.query(Q_DEPART, {"leaver": s["leaver"], "leave_at": s["leave_at"]})
        gone = cover(fork, lane, s["leaver"])
        after = after_departure(fork, present, gone) if after_departure else None
    finally:
        fork.delete()
    return {"unpromoted": unpromoted, "present": present, "gone": gone, "extra": extra, "after": after,
            "live_hash_before": hash_before, "live_hash_after": G.fingerprint(live)}


def failures(s, present, gone):
    """Events covered while the leaver is present and not covered once they have gone."""
    out = []
    for key in sorted(present, key=lambda k: (k[1], k[0])):
        duty, at, event, label, was_covered, status, sources = present[key]
        if was_covered and not gone[key][4]:
            out.append({"duty": duty, "at": at, "day": (at - s["now"]) // s["day_ms"], "event": event,
                        "label": label, "status": status, "sources": sorted(set(sources))})
    return out


def run(world_dir, beliefs_file, leaver, lane, confirm, port):
    s = open_session(world_dir, beliefs_file, leaver, port)
    r = on_fork(s, lane, confirm)
    return {"lane": lane, "leaver": leaver, "graph": s["live"].name, "failures": failures(s, r["present"], r["gone"]),
            "unpromoted": r["unpromoted"], "live_hash_before": r["live_hash_before"],
            "live_hash_after": r["live_hash_after"]}
