"""Conservative source relevance checks; a citation is never proof by itself."""
import re

STOP = {"a", "an", "the", "for", "to", "of", "and", "on", "by", "with", "from", "in", "is", "this",
        "that", "d", "job", "promise", "duty", "fix", "review", "report", "support", "task"}


def words(value):
    return {w for w in re.findall(r"[a-z0-9]+", str(value or "").lower()) if len(w) >= 3 and w not in STOP}


def relevant(source, belief, person, duty):
    # RT-02: source existence/type diversity cannot establish subject relevance.
    # Structured facts must concern the duty AND person; text needs independent
    # person attribution plus at least two specific terms from the duty topic.
    if source.get("type") not in ("message", "ticket"):
        return source.get("duty") == belief.get("duty") and belief.get("person") in (source.get("people") or [])
    text = " ".join(str(source.get(k) or "") for k in ("text", "author"))
    tokens = words(text)
    pname = str(person.get("name") or "")
    attributable = source.get("author") == person.get("id") or bool(words(pname) & tokens)
    if not attributable:
        return False
    # A known duty's graph name is authoritative, not a model-supplied alias.
    topics = [words(belief.get("duty")), words(duty.get("name") if duty else belief.get("duty_name"))]
    grounded = [len(topic & tokens) >= max(2, (len(topic) + 1) // 2) for topic in topics]
    return any(grounded) if duty else all(grounded)


def relevant_refs(fork, beliefs):
    sources = {row[0]["id"]: row[0] for row in fork.ro_query("MATCH (s:Source) RETURN properties(s)").result_set}
    people = {row[0]["id"]: row[0] for row in fork.ro_query("MATCH (p:Person) RETURN properties(p)").result_set}
    duties = {row[0]["id"]: row[0] for row in fork.ro_query("MATCH (d:Duty) RETURN properties(d)").result_set}
    return [[ref for ref in b.get("sources", []) if ref in sources and b.get("person") in people
             and relevant(sources[ref], b, people[b["person"]], duties.get(b.get("duty")))] for b in beliefs]
