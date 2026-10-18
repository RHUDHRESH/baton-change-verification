"""Acme inbox replay from the MIT-licensed agent-memory-bench generator.

This uses a deterministic text parser, not model extraction or a model benchmark.
All answers and graph views are read from time-filtered FalkorDB queries.
"""
import re
from functools import lru_cache

from . import graph as G
from third_party.amb import world as amb

NAME = "baton_acme_amb_7_50_v2"
SOURCE = "https://github.com/zhang-liz/agent-memory-bench"
TYPES = {"owned_by": "OWNED_BY", "on_call": "ON_CALL", "member_of": "MEMBER_OF", "depends_on": "DEPENDS_ON"}


def parsed_events():
    """Read only visible inbox text and the public entity alias catalogue.

    Rules cover the pinned generator's phrasing, not arbitrary company language.
    Functional facts replace the last visible value; removed calls close edges.
    """
    w = fixture()
    names = sorted(set(w.aliases.values()))
    tokens = {n: f"E{i}" for i, n in enumerate(names)}
    reverse = {v: k for k, v in tokens.items()}
    aliases = dict(w.aliases)
    for name in names:
        if name.startswith("Team "):
            short = name.removeprefix("Team ")
            aliases[f"the {short} folks".lower()] = name
            aliases[f"{short} team".lower()] = name
    pattern = re.compile(r"(?<![\w-])(" + "|".join(re.escape(a) for a in sorted(aliases, key=len, reverse=True)) + r")(?![\w-])", re.I)
    entity = r"(E\d+)"
    state = set()
    for event in w.events:
        text = event.text.split("\n\nattached logs:\n")[0]
        text = pattern.sub(lambda m: tokens[aliases[m[0].lower()]], text)
        add, remove = [], []

        def find(regex):
            return re.search(regex, text, re.S)

        def fact(a, rel, b):
            add.append((reverse[a], rel, reverse[b]))

        m = find(r"Service catalog entry: " + entity + r"\nOwning team: " + entity + r"\nUpstream dependencies: ([^\n]+)")
        if m:
            fact(m[1], "owned_by", m[2])
            for dep in re.findall(r"E\d+", m[3]):
                fact(m[1], "depends_on", dep)
        m = find(entity + r" is live in prod .*?" + entity + r" owns it")
        if m:
            fact(m[1], "owned_by", m[2])
            calls = find(r"It calls (.*?)\.")
            for dep in re.findall(r"E\d+", calls[1] if calls else ""):
                fact(m[1], "depends_on", dep)
        m = find(entity + r" will own " + entity + r" going forward")
        if m:
            fact(m[2], "owned_by", m[1])
            calls = find(r"Depends on: ([^\n]+)")
            for dep in re.findall(r"E\d+", calls[1] if calls else ""):
                fact(m[2], "depends_on", dep)
        for regex in (r"please welcome " + entity + r", who joins " + entity,
                      entity + r" starts Monday on " + entity,
                      entity + r" is moving over.*?officially part of " + entity):
            m = find(regex)
            if m:
                fact(m[1], "member_of", m[2])
        for regex in (entity + r" is now primary on-call for " + entity,
                      entity + r" has the pager for " + entity,
                      entity + r" is covering primary for " + entity):
            m = find(regex)
            if m:
                fact(m[2], "on_call", m[1])
        m = find(r"Primary on-call for " + entity + r": " + entity)
        if m:
            fact(m[1], "on_call", m[2])
        m = find(entity + r" is taking over " + entity + r" from " + entity)
        if m:
            fact(m[2], "owned_by", m[1])
        m = find(entity + r" moves from " + entity + r" to " + entity)
        if m:
            fact(m[1], "owned_by", m[3])
        m = find(r"handed " + entity + r" off to " + entity)
        if m:
            fact(m[1], "owned_by", m[2])
        m = find(r"on-call handoff for " + entity + r"\. " + entity + r" → " + entity)
        if m:
            fact(m[1], "on_call", m[3])
        m = find(r"\[#" + entity + r"\].*?handing the pager to " + entity)
        if m:
            fact(m[1], "on_call", m[2])
        for regex in (entity + r" now calls " + entity,
                      entity + r" will take a hard dependency on " + entity,
                      entity + r" reads from " + entity):
            m = find(regex)
            if m:
                fact(m[1], "depends_on", m[2])
        for regex in (entity + r" no longer talks to " + entity,
                      entity + r", it no longer depends on " + entity):
            m = find(regex)
            if m:
                remove.append((reverse[m[1]], "depends_on", reverse[m[2]]))
        for a, rel, b in add:
            if rel in ("owned_by", "on_call"):
                remove.extend(old for old in state if old[:2] == (a, rel) and old[2] != b)
        state.difference_update(remove)
        state.update(add)
        yield event, add, remove


@lru_cache(maxsize=1)
def fixture():
    return amb.generate(7, 50)


def connect(port):
    db = G.connect(port)
    g = db.select_graph(NAME)
    from server.control import connect as control_connect
    with control_connect(port).lock(f"baton:load:{NAME}", timeout=120, blocking_timeout=30):
        if not G.exists(db, NAME):
            try:
                w = fixture()
                services = {v for k, v in w.aliases.items() if k.startswith("the ") and k.endswith(" service")}
                entities = [{"id": n, "kind": "Service" if n in services else "Team" if n.startswith("Team ") else "Person"}
                            for n in sorted(set(w.aliases.values()))]
                g.query("UNWIND $rows AS n CREATE (:Entity {id:n.id, kind:n.kind})", {"rows": entities})
                for e, assertions, retractions in parsed_events():
                    source = f"inbox-{e.step:03d}"
                    g.query("CREATE (:Inbox {id:$id, step:$step, text:$text, kind:$kind})",
                            {"id": source, "step": e.step, "text": e.text, "kind": e.kind})
                    for a, rel, b in retractions:
                        g.query(f"MATCH (a:Entity {{id:$a}})-[r:{TYPES[rel]}]->(b:Entity {{id:$b}}) "
                                "WHERE r.until = 51 SET r.until = $step, r.retracted_by = $source",
                                {"a": a, "b": b, "step": e.step, "source": source})
                    for a, rel, b in assertions:
                        g.query(f"MATCH (a:Entity {{id:$a}}), (b:Entity {{id:$b}}) "
                                f"CREATE (a)-[:{TYPES[rel]} {{since:$step, until:51, source:$source}}]->(b)",
                                {"a": a, "b": b, "step": e.step, "source": source})
                    # Incident details are parsed from visible text, never from final_state.
                    hit = re.match(r"INCIDENT (\S+) opened by .*\nService: (.*)\nSummary: (.*)\n", e.text)
                    if hit:
                        g.query("MATCH (s:Entity {id:$service}) CREATE (i:Incident {id:$id, symptom:$symptom, "
                                "step:$step, source:$source})-[:AFFECTS]->(s)",
                                dict(id=hit[1], service=hit[2], symptom=hit[3], step=e.step, source=source))
            except Exception:
                if G.exists(db, NAME):
                    g.delete()
                raise
    return g


def snapshot(port, step=50):
    g = connect(port)
    nodes = [{"data": {"id": name, "label": name, "kind": kind}}
             for name, kind in g.ro_query("MATCH (n:Entity) RETURN n.id, n.kind ORDER BY n.id").result_set]
    rows = g.ro_query("MATCH (a:Entity)-[r]->(b:Entity) WHERE r.since <= $step AND $step < r.until "
                      "RETURN id(r), a.id, b.id, type(r), r.source, r.since ORDER BY id(r)", {"step": step}).result_set
    edges = [{"data": {"id": f"e{identity}", "source": a, "target": b, "kind": kind,
                        "label": kind, "source_id": source, "since": since}}
             for identity, a, b, kind, source, since in rows]
    inbox = [{"id": f"inbox-{e.step:03d}", "step": e.step, "kind": e.kind, "time": e.time.isoformat() + "Z",
              "text": e.text} for e in fixture().events if e.step <= step]
    questions = [{"id": q.qid, "step": q.after_step, "category": q.category, "text": q.text}
                 for q in fixture().questions if q.after_step <= step]
    return {"company": "Acme", "seed": 7, "steps": 50, "step": step, "graph": NAME, "fixture": True,
            "mode": "Scripted text parser · no model extraction", "source": SOURCE,
            "credit": "Liz Zhang · agent-memory-bench · MIT · vendored b8ccc40",
            "nodes": nodes, "edges": edges, "inbox": inbox, "questions": questions}


QUERIES = {
    "owner": "MATCH (s:Entity {id:$subject})-[r:OWNED_BY]->(t) WHERE r.since <= $step AND $step < r.until RETURN DISTINCT t.id AS answer, [r.source] AS sources",
    "oncall": "MATCH (t:Entity {id:$subject})-[r:ON_CALL]->(p) WHERE r.since <= $step AND $step < r.until RETURN DISTINCT p.id AS answer, [r.source] AS sources",
    "page": "MATCH (s:Entity {id:$subject})-[d:DEPENDS_ON]->(up)-[o:OWNED_BY]->(t)-[c:ON_CALL]->(p) WHERE all(r IN [d,o,c] WHERE r.since <= $step AND $step < r.until) RETURN DISTINCT p.id AS answer, [d.source,o.source,c.source] AS sources",
    "impact": "MATCH path=(s:Entity)-[:DEPENDS_ON*1..64]->(target:Entity {id:$subject}) WHERE s.id <> $subject AND all(r IN relationships(path) WHERE r.since <= $step AND $step < r.until) RETURN DISTINCT s.id AS answer, [r IN relationships(path) | r.source] AS sources",
    "incident": "MATCH (i:Incident)-[:AFFECTS]->(s:Entity {id:$subject}) WHERE i.step <= $step AND ($symptom = '' OR i.symptom = $symptom) RETURN DISTINCT i.id AS answer, [i.source] AS sources",
}


def ask(port, tool, subject, step, symptom=""):
    query = QUERIES[tool]
    rows = connect(port).ro_query(query, {"subject": subject, "step": step, "symptom": symptom}).result_set
    return {"tool": tool, "subject": subject, "step": step, "answers": sorted({row[0] for row in rows}),
            "sources": sorted({source for row in rows for source in row[1]}), "cypher": query}


def benchmark_question(port, qid):
    q = next((q for q in fixture().questions if q.qid == qid), None)
    if q is None:
        raise ValueError("Unknown benchmark question")
    text, symptom = q.text, ""
    if text.startswith("Which team"):
        tool, subject = "owner", text.split(" owns ")[1].removesuffix("?").removesuffix(" right now")
    elif text.startswith("Who is"):
        tool, subject = "oncall", text.split("on-call for ")[1].removesuffix(" right now?")
    elif q.category == "multihop":
        tool, subject = "page", text.split(" is down")[0]
    elif q.category == "transitive":
        tool, subject = "impact", text.removeprefix("If ").split(" goes down")[0]
    else:
        tool = "incident"
        symptom, subject = text.removeprefix("What was the incident ID for the ").removesuffix("?").split(" reported on ")
    result = ask(port, tool, subject, q.after_step, symptom)
    # Expected answers are used only for scoring, never fed into the query.
    return {**result, "question": text, "category": q.category, "expected": sorted(q.answer),
            "correct": result["answers"] == sorted(q.answer)}
