"""`python -m baton load`: turn world.json into the company graph `halden_<seed>` in FalkorDB
(`halden_<seed>_x<N>` for a world generated with --scale N).

Once the graph exists it is the source of truth: loading again leaves it exactly as it is.

Shape (every edge carries its source record id in `rec` and a validity window vf <= t < vt, epoch ms):
  (:Duty)-[:OWNER {vf: since, vt: OPEN}]->(:Person)
  (:Duty)-[:ROUTES_TO]->(:Rota)-[:SHIFT {vf: from, vt: to}]->(:Person)
  (:Person)-[:ESCALATES_TO]->(:Person)
  (:Person {capacity})-[:CAN]->(:Duty)   capability (who could take a duty on); never part of a cover path
  (:Event {at})-[:NEEDS]->(:Duty)        scheduled obligations
  (:Source {type: message|joblog|ticket|record, duty, people})   the evidence a belief may cite; a record or job
                                 log is about one duty (its duty / job) and some people (person, from/to, actor)
  (:Company {seed, now, day_ms, window_days, leave_at})
"""
import json
from pathlib import Path

from . import graph as G

INDEXES = [("Person", "id"), ("Duty", "id"), ("Rota", "id"), ("Source", "id"), ("Event", "at")]

Q_COMPANY = """
CREATE (:Company {id: 'company', name: $c.company, seed: $c.seed, label: $c.label, now: $c.now,
                  day_ms: $c.day_ms, window_days: $c.window_days, leave_at: $c.leave_at})"""

Q_PEOPLE = """
UNWIND $rows AS p
CREATE (:Person {id: p.id, name: p.name, team: p.team, role: p.role, left_at: p.left_at,
                 capacity: coalesce(p.capacity, 1)})"""

Q_DUTIES = """
UNWIND $rows AS d
CREATE (:Duty {id: d.id, name: d.name, kind: d.kind})"""

Q_ROTAS = """
UNWIND $rows AS id
CREATE (:Rota {id: id})"""

Q_SOURCES = """
UNWIND $rows AS s
CREATE (:Source {id: s.id, type: s.type, text: s.text, author: s.author, at: s.at, duty: s.duty, people: s.people})"""

Q_EVENTS = """
UNWIND $rows AS e
MATCH (d:Duty {id: e.duty})
CREATE (:Event {id: e.id, duty: e.duty, at: e.at, label: e.label})-[:NEEDS]->(d)"""

Q_OWNER = """
UNWIND $rows AS r
MATCH (d:Duty {id: r.duty}), (p:Person {id: r.person})
CREATE (d)-[:OWNER {vf: coalesce(r.since, 0), vt: $open, rec: r.id}]->(p)"""

Q_ROUTES_TO = """
UNWIND $rows AS r
MATCH (d:Duty {id: r.duty}), (o:Rota {id: r.rota})
CREATE (d)-[:ROUTES_TO {vf: 0, vt: $open, rec: r.id}]->(o)"""

Q_SHIFT = """
UNWIND $rows AS r
MATCH (o:Rota {id: r.rota}), (p:Person {id: r.person})
CREATE (o)-[:SHIFT {vf: r.from, vt: r.to, rec: r.id}]->(p)"""

Q_ESCALATES_TO = """
UNWIND $rows AS r
MATCH (a:Person {id: r.from_person}), (b:Person {id: r.to_person})
CREATE (a)-[:ESCALATES_TO {vf: 0, vt: $open, rec: r.id}]->(b)"""

Q_CAN = """
UNWIND $rows AS r
MATCH (p:Person {id: r.person}), (d:Duty {id: r.duty})
CREATE (p)-[:CAN {vf: 0, vt: $open, rec: r.id}]->(d)"""


def read_world(world_dir):
    return json.loads((Path(world_dir) / "world.json").read_text())


def _record_text(r):
    if r["type"] == "OWNER":
        return f"{r['duty']} is owned by {r['person']}"
    if r["type"] == "ROUTES_TO":
        return f"{r['duty']} routes to {r['rota']}"
    if r["type"] == "SHIFT":
        return f"{r['person']} is on {r['rota']}"
    if r["type"] == "CAN":
        return f"{r['person']} can take on {r['duty']}"
    return f"{r['from_person']} escalates to {r['to_person']}"


def _sources(w):
    out = [{"id": m["id"], "type": "message", "text": m["text"], "author": m["author"], "at": m["at"]}
           for m in w.get("messages", [])]
    out += [{"id": j["id"], "type": "joblog", "text": f"{j['job']} {j['status']}", "author": j["actor"],
             "at": j["at"], "duty": j["job"], "people": [j["actor"]]} for j in w.get("joblogs", [])]
    out += [{"id": t["id"], "type": "ticket", "text": t["text"], "author": t["author"], "at": t["at"]}
            for t in w.get("tickets", [])]
    out += [{"id": r["id"], "type": "record", "text": _record_text(r), "author": None, "at": None,
             "duty": r.get("duty"), "people": [r[k] for k in ("person", "from_person", "to_person") if r.get(k)]}
            for r in w["records"]]
    return out


def _ensure_unlocked(db, w):
    """Create graph halden_<seed> from world `w` unless it already exists. Returns (graph, created)."""
    name = G.graph_name(w["seed"], w.get("scale", 1))
    g = db.select_graph(name)
    if G.exists(db, name):
        return g, False
    for label, prop in INDEXES:
        g.query(f"CREATE INDEX FOR (n:{label}) ON (n.{prop})")
    g.query(Q_COMPANY, {"c": {k: w[k] for k in ("company", "seed", "label", "now", "day_ms", "window_days",
                                                 "leave_at")}})
    rotas = sorted({r["rota"] for r in w["records"] if r["type"] in ("ROUTES_TO", "SHIFT")})
    for q, rows in ((Q_PEOPLE, w["people"]), (Q_DUTIES, w["duties"]), (Q_ROTAS, rotas), (Q_SOURCES, _sources(w)),
                    (Q_EVENTS, w["events"])):
        g.query(q, {"rows": rows})
    for rtype, q in (("OWNER", Q_OWNER), ("ROUTES_TO", Q_ROUTES_TO), ("SHIFT", Q_SHIFT),
                     ("ESCALATES_TO", Q_ESCALATES_TO), ("CAN", Q_CAN)):
        g.query(q, {"rows": [r for r in w["records"] if r["type"] == rtype], "open": G.OPEN})
    return g, True


def ensure(db, w):
    """Serialize first import so readers never observe a half-built company."""
    name = G.graph_name(w["seed"], w.get("scale", 1))
    with db.connection.lock(f"baton:load:{name}", timeout=300, blocking_timeout=60):
        existed = G.exists(db, name)
        try:
            return _ensure_unlocked(db, w)
        except Exception:
            if not existed and G.exists(db, name):
                db.select_graph(name).delete()
            raise


def run(world_dir, port):
    w = read_world(world_dir)
    db = G.connect(port)
    g, created = ensure(db, w)
    n = g.ro_query("MATCH (n) RETURN count(n)").result_set[0][0]
    e = g.ro_query("MATCH ()-[r]->() RETURN count(r)").result_set[0][0]
    return {"graph": g.name, "created": created, "nodes": n, "edges": e}
