"""`python -m baton ask`: ask the company graph a question in plain words; get rows, sources and the Cypher that ran.

Nothing here writes Cypher on the fly. A question is routed to ONE tool from a fixed catalogue plus its arguments
(person id, duty id, day); the tool runs exactly its catalogue query with those as parameters. The router is
deterministic (names are matched against the graph's Person and Duty names and the belief file's duty names).

Every tool reasons on a GRAPH.COPY fork where the beliefs have been gated and promoted ones written as HOLDS edges
(the same preparation as the Rehearsal); the live graph is only fingerprinted and the fork is always dropped.
  owes             - duties the person holds by a record OWNER edge or a promoted belief
  breaks_if_leaves - the Rehearsal's G lane (beliefs confirmed) for that person
  why              - the evidence behind (duty)-[OWNER|HOLDS]->(person)
  who_owns         - everyone holding the duty now: record OWNER edges in force plus promoted beliefs
  covers           - who can act on the duty at its first event on day N (or the day's start), nobody removed
  none             - the graph cannot answer; say so, cite nothing
"""
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from . import graph as G
from . import load, rehearse

Q_OWES = """
MATCH (d:Duty)-[r:OWNER|HOLDS]->(p:Person {id: $person})
WITH d, collect(r) AS rs
RETURN d.id AS duty, d.name AS duty_name,
       CASE WHEN any(r IN rs WHERE type(r) = 'OWNER') THEN 'record' ELSE head([r IN rs | r.basis]) END AS status,
       reduce(acc = [], r IN rs | acc + CASE WHEN type(r) = 'HOLDS' THEN r.srcs ELSE [r.rec] END) AS sources
ORDER BY duty"""

Q_WHY = """
MATCH (d:Duty {id: $duty})-[r:OWNER|HOLDS]->(p:Person {id: $person})
WITH d, p, r, CASE WHEN type(r) = 'HOLDS' THEN r.srcs ELSE [r.rec] END AS refs
UNWIND refs AS ref
MATCH (s:Source {id: ref})
RETURN d.id AS duty, d.name AS duty_name, p.id AS person, type(r) AS via, coalesce(r.belief, r.rec) AS basis,
       s.id AS source, s.type AS type, s.text AS text
ORDER BY source"""

Q_COVERS = """
MATCH (c:Company), (d:Duty {id: $duty})
OPTIONAL MATCH (e:Event)-[:NEEDS]->(d)
WHERE e.at >= c.now + $day * c.day_ms AND e.at < c.now + ($day + 1) * c.day_ms
WITH c, d, e ORDER BY e.at, e.id
WITH c, d, collect(e)[0] AS e
WITH d, e, coalesce(e.at, c.now + $day * c.day_ms) AS t
OPTIONAL MATCH path = (d)-[:OWNER|ROUTES_TO|SHIFT|ESCALATES_TO|HOLDS*1..4]->(who:Person)
WHERE all(r IN relationships(path) WHERE r.vf <= t AND r.vt > t)
  AND (who.left_at IS NULL OR who.left_at > t)
WITH d, e, t, who, collect(path) AS paths
RETURN d.id AS duty, d.name AS duty_name, t AS at, e.id AS event, e.label AS label, who.id AS person,
       who.name AS person_name,
       CASE WHEN size(paths) = 0 THEN [] ELSE [r IN relationships(head(paths)) | type(r)] END AS via,
       reduce(acc = [], p IN paths | acc + reduce(src = [], r IN relationships(p) |
              src + CASE WHEN type(r) = 'HOLDS' THEN r.srcs ELSE [r.rec] END)) AS sources
ORDER BY person"""

Q_WHO_OWNS = """
MATCH (c:Company), (d:Duty {id: $duty})
OPTIONAL MATCH (d)-[r:OWNER|HOLDS]->(p:Person)
WHERE r.vf <= c.now AND r.vt > c.now
WITH d, p, collect(r) AS rs
RETURN d.id AS duty, d.name AS duty_name, p.id AS person, p.name AS person_name, p.left_at AS left_at,
       CASE WHEN p IS NULL THEN null WHEN any(r IN rs WHERE type(r) = 'OWNER') THEN 'record'
            ELSE head([r IN rs | r.basis]) END AS basis,
       reduce(acc = [], r IN rs | acc + CASE WHEN type(r) = 'HOLDS' THEN r.srcs ELSE [r.rec] END) AS sources
ORDER BY person"""

CATALOGUE = {
    "owes": Q_OWES,
    "breaks_if_leaves": rehearse.cover_query("G"),
    "why": Q_WHY,
    "covers": Q_COVERS,
    "who_owns": Q_WHO_OWNS,
    "none": "",
}

NOT_IN_GRAPH = ("That is not in the graph. Baton can answer what someone owes, what breaks if they leave, "
                "why a duty is theirs, who owns a duty, and who covers a duty on a given day.")

# ---------------------------------------------------------------- routing (deterministic, no model, no Cypher)

STOP = {"a", "an", "the", "for", "to", "of", "on", "and", "in", "at", "by", "s", "is", "job", "duty", "task",
        "responsibility"}

PATTERNS = [
    ("breaks_if_leaves", re.compile(r"\bwhat (?:breaks|would break|will break|fails|would fail|goes wrong|stops)"
                                    r"\b.*?\bif (?P<x>.+?) (?:leaves|left|quits|goes|departs|resigns)\b")),
    ("breaks_if_leaves", re.compile(r"\bwhat if (?P<x>.+?) (?:leaves|left|quits|departs|resigns)\b")),
    ("owes", re.compile(r"\bwhat (?:does|do) (?P<x>.+?) (?:owe|own|hold|handle)\b")),
    ("owes", re.compile(r"\bwhat (?:is|are) (?P<x>.+?) (?:responsible for|on the hook for)\b")),
    ("why", re.compile(r"\bwhy (?:is|are) (?P<x>.+?) (?:job|duty|responsibility|task|problem)\b")),
    ("why", re.compile(r"\bwhy (?:does|do) (?P<x>.+?)\s*$")),
    ("covers", re.compile(r"\bwho (?:covers|handles|is covering|can cover|can act on|is on|owns|does) (?P<x>.+?) "
                          r"(?:on|at|for) day (?P<day>\d+)\b")),
    ("who_owns", re.compile(r"\bwho (?:owns|holds|handles|has|is (?:responsible|accountable) for|is the owner of|"
                            r"is in charge of|looks after) (?P<x>.+?)\s*$")),
    ("who_owns", re.compile(r"\bwhose (?:job|duty|responsibility|task) is (?P<x>.+?)\s*$")),
]


def norm(text):
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(text).lower()).split())


def _find(tokens, needle):
    """Index of the contiguous token sequence `needle` in `tokens`, or -1."""
    n = len(needle)
    for i in range(len(tokens) - n + 1):
        if n and tokens[i:i + n] == needle:
            return i
    return -1


def match_person(text, people):
    """people: [(id, name)]. Full name or id first, then a unique first name. Returns (id, span) or (None, why)."""
    toks = norm(text).split()
    hits = []
    for pid, name in people:
        for alias in (norm(name), norm(pid)):
            i = _find(toks, alias.split())
            if i >= 0:
                hits.append((len(alias.split()), i, pid))
                break
    if hits:
        n, i, pid = max(hits, key=lambda h: (h[0], -h[1]))
        return pid, (i, i + n)
    firsts = {}
    for pid, name in people:
        first = norm(name).split()[:1]
        if first and _find(toks, first) >= 0:
            firsts.setdefault(first[0], []).append(pid)
    found = sorted(pid for pids in firsts.values() for pid in pids)
    if len(found) == 1:
        first = next(k for k, v in firsts.items() if v == found)
        i = toks.index(first)
        return found[0], (i, i + 1)
    return None, ("ambiguous: " + ", ".join(found)) if found else None


def match_duty(text, duties, prefer_person=None):
    """duties: [(id, name, person_or_None)]. Exact normalised name/id wins, else best token overlap >= 0.5."""
    q = norm(text)
    qset = set(q.split()) - STOP
    scored = []
    for did, name, person in duties:
        for alias in (norm(name), norm(did)):
            aset = set(alias.split()) - STOP
            if alias and alias == q:
                score = 2.0
            elif aset and qset:
                score = len(aset & qset) / len(aset | qset)
                if alias in q or q in alias:
                    score = max(score, 0.9)
            else:
                continue
            if score >= 0.5:
                # best score, then a duty this person is said to hold, then a recorded duty, then the smallest id
                scored.append((-score, not (prefer_person and person == prefer_person), person is not None, did))
    return min(scored)[3] if scored else None


def route(question, people, duties):
    """Return (tool, args) chosen by the fixed patterns; ('none', {...}) if the question does not fit the graph."""
    q = norm(question)
    for tool, pat in PATTERNS:
        m = pat.search(q)
        if not m:
            continue
        x = m.group("x")
        if tool in ("owes", "breaks_if_leaves"):
            pid, _ = match_person(x, people)
            if pid:
                return tool, {"person": pid}
            return "none", {"reason": f"no person matching '{x}'"}
        if tool == "why":
            pid, span = match_person(x, people)
            if not pid:
                return "none", {"reason": f"no person in '{x}'"}
            toks = x.split()
            rest = toks[:span[0]] + toks[span[1]:]
            for verb in ("own", "owns", "hold", "holds", "handle", "handles", "have", "has"):
                if verb in rest[:1]:
                    rest = rest[1:]
            did = match_duty(" ".join(rest), duties, prefer_person=pid)
            if did:
                return "why", {"duty": did, "person": pid}
            return "none", {"reason": f"no duty matching '{' '.join(rest)}'"}
        if tool == "who_owns":
            did = match_duty(x, duties)
            if did:
                return "who_owns", {"duty": did}
            return "none", {"reason": f"no duty matching '{x}'"}
        if tool == "covers":
            did = match_duty(x, duties)
            if did:
                return "covers", {"duty": did, "day": int(m.group("day"))}
            return "none", {"reason": f"no duty matching '{x}'"}
    return "none", {}


# ---------------------------------------------------------------- running a catalogue tool on a fork

def _on_fork(s, tool, params):
    live = s["live"]
    before = G.fingerprint(live)
    fork = G.fork(s["db"], live.name, os.getpid())
    try:
        rehearse.gate(fork, s["beliefs"])
        fork.query(rehearse.Q_HOLDS, {"open": G.OPEN, "basis": "confirmed"})
        res = fork.ro_query(CATALOGUE[tool], params)
        cols = [c[1] if isinstance(c, (list, tuple)) else c for c in res.header]
        rows = [dict(zip(cols, r)) for r in res.result_set]
    finally:
        fork.delete()
    return rows, before, G.fingerprint(live)


def _when(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%a %d %b %Y %H:%M UTC")


def _list(xs, n=6):
    xs = list(xs)
    more = f" and {len(xs) - n} more" if len(xs) > n else ""
    return ", ".join(xs[:n]) + more


def _duties_phrase(n):
    return f"{n} dut{'y' if n == 1 else 'ies'}"


def run_tool(s, tool, args, names, duty_names):
    """Execute `tool` with `args`. Returns (rows, sources, answer, hashes). Answers name people and duties, never ids."""
    who = names.get(args.get("person"), args.get("person"))
    dname = duty_names.get(args.get("duty"), "that duty")
    if tool == "breaks_if_leaves":
        s2 = dict(s, leaver=args["person"])
        r = rehearse.on_fork(s2, "G", "all")
        rows = rehearse.failures(s2, r["present"], r["gone"])
        for row in rows:
            row["duty_name"] = duty_names.get(row["duty"]) or "an unnamed duty"
        duties = sorted({x["duty_name"] for x in rows})
        answer = (f"If {who} leaves, {_duties_phrase(len({x['duty'] for x in rows}))} lose everyone able to act "
                  f"on them ({len(rows)} scheduled event{'s' if len(rows) != 1 else ''} in the next 30 days): "
                  f"{_list(duties)}." if rows else f"Nothing scheduled in the next 30 days breaks if {who} leaves.")
        return rows, [x for row in rows for x in row["sources"]], answer, (r["live_hash_before"],
                                                                           r["live_hash_after"])
    rows, h0, h1 = _on_fork(s, tool, args)
    if tool == "owes":
        for row in rows:
            row["sources"] = sorted(set(row["sources"]))
            row["duty_name"] = row["duty_name"] or duty_names.get(row["duty"]) or "an unnamed duty"
        answer = (f"{who} owes {_duties_phrase(len(rows))}: "
                  + _list(f"{r['duty_name']} ({r['status']})" for r in rows) + "." if rows
                  else f"The graph shows nothing {who} owes.")
        return rows, [x for row in rows for x in row["sources"]], answer, (h0, h1)
    if tool == "why":
        if rows:
            dname = rows[0]["duty_name"] or dname
            answer = (f"{dname} is {who}'s because of {len(rows)} source{'s' if len(rows) != 1 else ''}: "
                      + _list(f"{r['source']} ({r['type']})" for r in rows) + ".")
        else:
            answer = f"The graph has no record or promoted belief that makes {dname} {who}'s job."
        return rows, [r["source"] for r in rows], answer, (h0, h1)
    if tool == "who_owns":
        found = [r for r in rows if r["person"]]
        for r in found:
            r["sources"] = sorted(set(r["sources"]))
            r["duty_name"] = r["duty_name"] or dname
        if not found:
            answer = (f"Nobody holds {dname} right now: there is no record owner, and no belief about it passed "
                      f"the evidence gate.")
        else:
            def label(r):
                gone = r["left_at"] is not None and r["left_at"] <= s["now"]
                return (f"{r['person_name']} ({'record' if r['basis'] == 'record' else 'confirmed from chat'}"
                        + (f"; left on {_when(r['left_at'])}" if gone else "") + ")")
            answer = f"{found[0]['duty_name']} is held by {_list(label(r) for r in found)}."
        return found, [x for r in found for x in r["sources"]], answer, (h0, h1)
    # covers
    found = [r for r in rows if r["person"]]
    for r in found:
        r["sources"] = sorted(set(r["sources"]))
    for r in found:
        r["duty_name"] = r["duty_name"] or dname
    if not rows:
        answer = f"{dname} is not in the graph."
    else:
        r0 = rows[0]
        at = f"{r0['label']} at {_when(r0['at'])}" if r0["event"] else f"start of day {args['day']}"
        answer = (f"On day {args['day']} ({at}), {_list(r['person_name'] for r in found)} can act on {r0['duty_name'] or dname}."
                  if found else f"Nobody can act on {r0['duty_name'] or dname} on day {args['day']} ({at}).")
    return found, [x for r in found for x in r["sources"]], answer, (h0, h1)


def run(world_dir, beliefs_file, question, port, offline=True):
    w = load.read_world(world_dir)
    beliefs = json.loads(Path(beliefs_file).read_text())
    db = G.connect(port)
    live, _ = load.ensure(db, w)
    now, day_ms, leave_at = live.ro_query("MATCH (c:Company) RETURN c.now, c.day_ms, c.leave_at").result_set[0]
    people = [tuple(r) for r in live.ro_query("MATCH (p:Person) RETURN p.id, p.name ORDER BY p.id").result_set]
    duties = [(r[0], r[1], None) for r in live.ro_query("MATCH (d:Duty) RETURN d.id, d.name ORDER BY d.id").result_set]
    duties += [(b["duty"], b.get("duty_name") or b["duty"], b.get("person")) for b in beliefs if b.get("duty")]
    tool, args = route(question, people, duties)
    names = dict(people)
    out = {"question": question, "tool": tool, "args": args, "cypher": CATALOGUE[tool], "graph": live.name,
           "router": "offline"}
    if tool == "none":
        h = G.fingerprint(live)
        reason = args.get("reason")
        out.update(rows=[], sources=[], answer=NOT_IN_GRAPH + (f" ({reason})" if reason else ""),
                   live_hash_before=h, live_hash_after=h)
        return out
    s = {"db": db, "live": live, "beliefs": beliefs, "leaver": args.get("person"), "now": now, "day_ms": day_ms,
         "leave_at": leave_at}
    duty_names = {did: name for did, name, _ in reversed(duties) if name and name != did}
    rows, sources, answer, (h0, h1) = run_tool(s, tool, args, names, duty_names)
    out.update(rows=rows, sources=sorted(set(sources)), answer=answer, live_hash_before=h0, live_hash_after=h1)
    return out


def catalogue():
    return dict(CATALOGUE)
